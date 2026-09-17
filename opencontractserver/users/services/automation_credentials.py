"""Credential lifecycle and shared scope checks; never confer user permissions."""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import timedelta
from enum import Enum

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied

from opencontractserver.constants.users import (
    AUTOMATION_CREDENTIAL_DEFAULT_DAYS,
    AUTOMATION_CREDENTIAL_MAX_PAGE_SIZE,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.users.models import AutomationCredential
from opencontractserver.utils.ids import from_global_id

logger = logging.getLogger(__name__)
DENIED = "Automation credential does not permit this operation."
INVALID = "Invalid automation credential."


class Scope(str, Enum):
    CORPUS_READ = "corpus:read"
    CORPUS_CREATE = "corpus:create"
    CORPUS_CONFIGURE = "corpus:configure"
    CORPUS_PUBLISH = "corpus:publish"
    DOCUMENT_IMPORT = "document:import"
    INGESTION_READ = "ingestion:read"
    INGESTION_REPAIR = "ingestion:repair"
    AUTHORITY_ADMIN = "authority:admin"
    PIPELINE_READ = "pipeline:read"
    PIPELINE_CONFIGURE = "pipeline:configure"


SELF_SERVICE_SCOPES = frozenset(
    {
        Scope.CORPUS_READ,
        Scope.CORPUS_CONFIGURE,
        Scope.CORPUS_PUBLISH,
        Scope.DOCUMENT_IMPORT,
        Scope.INGESTION_REPAIR,
    }
)


def corpus_pk(value):
    """Accept raw corpus PKs or correctly typed Relay IDs, fail closed otherwise."""
    try:
        if str(value).isdigit():
            return int(value)
        type_name, pk = from_global_id(str(value))
        if type_name == "CorpusType" and pk.isdigit():
            return int(pk)
    except (ValueError, TypeError, UnicodeError):
        raise PermissionDenied(DENIED) from None
    raise PermissionDenied(DENIED)


def _digest(secret):
    return hashlib.sha256(secret.encode()).hexdigest()


def _new_secret(credential):
    secret = secrets.token_urlsafe(32)
    credential.secret_hash = _digest(secret)
    return f"{credential.pk}.{secret}"


def expiry_from_days(days=AUTOMATION_CREDENTIAL_DEFAULT_DAYS):
    if days <= 0:
        raise ValueError("Lifetime must be positive.")
    try:
        return timezone.now() + timedelta(days=days)
    except OverflowError:
        raise ValueError("Lifetime is too large.") from None


def require_management(actor, *, lock=False):
    if not (
        actor is not None
        and actor.is_authenticated
        and actor.is_active
        and getattr(actor, "automation_credential", None) is None
    ):
        raise PermissionDenied("An active login is required.")
    if lock:
        current = (
            get_user_model().objects.select_for_update().filter(pk=actor.pk).first()
        )
        return require_management(current)
    return actor


def management_scopes(actor):
    require_management(actor)
    return [
        scope.value
        for scope in Scope
        if actor.is_superuser or scope in SELF_SERVICE_SCOPES
    ]


def _management_corpuses(actor):
    queryset = Corpus.objects.all()
    return queryset if actor.is_superuser else queryset.filter(creator_id=actor.pk)


def _managed_credentials(actor):
    queryset = AutomationCredential.objects.select_related("user")
    return queryset if actor.is_superuser else queryset.filter(user_id=actor.pk)


def _require_issuance(actor, *, user_id, scopes, corpus_ids):
    """Interactive callers may only obtain secrets for their own account."""
    if user_id != actor.pk:
        raise PermissionDenied(DENIED)
    if actor.is_superuser:
        return
    if set(scopes) - SELF_SERVICE_SCOPES or not corpus_ids:
        raise PermissionDenied(DENIED)
    # Keep ownership stable until mint/rotate commits. Evaluate the rows: a
    # count() would not acquire the FOR UPDATE locks. Order locks by corpus ID.
    owned_ids = list(
        _management_corpuses(actor)
        .filter(pk__in=corpus_ids)
        .order_by("pk")
        .select_for_update()
        .values_list("pk", flat=True)
    )
    if len(owned_ids) != len(corpus_ids):
        raise PermissionDenied(DENIED)


def _page(queryset, limit, offset):
    if not 1 <= limit <= AUTOMATION_CREDENTIAL_MAX_PAGE_SIZE or offset < 0:
        raise ValueError("Invalid page bounds.")
    return list(queryset[offset : offset + limit]), queryset.count()


def list_credentials(actor, *, limit, offset):
    require_management(actor)
    return _page(
        _managed_credentials(actor).order_by("-created_at", "id"),
        limit,
        offset,
    )


def inspect_credential(actor, credential_id):
    require_management(actor)
    return _managed_credentials(actor).get(pk=credential_id)


def management_choices(actor, *, kind, search, limit, offset):
    require_management(actor)
    queryset: QuerySet
    if kind == "principal":
        queryset = get_user_model().objects.filter(pk=actor.pk, is_active=True)
        query = Q(username__icontains=search) | Q(name__icontains=search)
        label = "username"
    elif kind == "corpus":
        queryset = _management_corpuses(actor)
        query = Q(title__icontains=search)
        label = "title"
    else:
        raise ValueError("Invalid choice kind.")
    if search.isdecimal():
        query |= Q(pk=int(search))
    rows, total = _page(queryset.filter(query).order_by("pk"), limit, offset)
    return [(str(row.pk), getattr(row, label)) for row in rows], total


def mint_for_user(actor, *, user_id, all_corpuses, corpus_ids, expires_days, **kwargs):
    require_management(actor)
    # Retain the optional ID for existing API clients, never as a principal selector.
    if user_id is not None and str(user_id) != str(actor.pk):
        raise PermissionDenied(DENIED)
    if (all_corpuses and corpus_ids is not None) or (
        not all_corpuses and not corpus_ids
    ):
        raise ValueError("Select corpuses or explicitly allow all corpuses.")
    return mint(
        actor=actor,
        user=actor,
        corpus_ids=None if all_corpuses else corpus_ids,
        expires_at=expiry_from_days(expires_days),
        **kwargs,
    )


@transaction.atomic
def mint(*, user, name, scopes, corpus_ids, expires_at=None, actor=None):
    if actor is not None:
        actor = require_management(actor, lock=True)
        if user.pk != actor.pk:
            raise PermissionDenied(DENIED)
        user = actor
    else:
        # Trusted operator/CLI path. Re-read under lock to catch deactivation.
        user = get_user_model().objects.select_for_update().filter(pk=user.pk).first()
    scopes = sorted(set(scopes))
    if user is None or not user.is_active:
        raise ValueError("Principal must be active.")
    if not name.strip() or len(name) > 100:
        raise ValueError("Name must contain 1–100 characters.")
    if not scopes or set(scopes) - {scope.value for scope in Scope}:
        raise ValueError("Supply at least one valid operation scope.")
    if expires_at is not None and expires_at <= timezone.now():
        raise ValueError("Expiry must be in the future.")
    if corpus_ids is not None:
        corpus_ids = sorted({corpus_pk(pk) for pk in corpus_ids})
        if Corpus.objects.filter(pk__in=corpus_ids).count() != len(corpus_ids):
            raise ValueError("Unknown corpus.")
    if actor is not None:
        _require_issuance(actor, user_id=user.pk, scopes=scopes, corpus_ids=corpus_ids)
    credential = AutomationCredential(
        user=user,
        name=name,
        scopes=scopes,
        corpus_ids=corpus_ids,
        expires_at=expires_at,
    )
    token = _new_secret(credential)
    credential.save()
    audit("minted", credential, actor=actor)
    return credential, token


def metadata(credential):
    """Explicit projection: neither the secret nor its hash is inspectable."""
    return {
        field: getattr(credential, field)
        for field in (
            "id",
            "user_id",
            "name",
            "scopes",
            "corpus_ids",
            "expires_at",
            "revoked_at",
            "created_at",
            "rotated_at",
        )
    }


def audit(event, credential, *, actor=None):
    logger.info(
        "Automation credential %s credential_id=%s actor_id=%s principal_id=%s",
        event,
        credential.pk,
        actor.pk if actor is not None else None,
        credential.user_id,
    )


def _validate(credential):
    if (
        credential.revoked_at is not None
        or not credential.user.is_active
        or (
            credential.expires_at is not None
            and credential.expires_at <= timezone.now()
        )
    ):
        raise AuthenticationFailed(INVALID)


@transaction.atomic
def rotate(credential_id, *, actor=None):
    if actor is not None:
        actor = require_management(actor, lock=True)
    queryset = AutomationCredential.objects.select_for_update(
        of=("self",)
    ).select_related("user")
    if actor is not None:
        queryset = queryset.filter(user_id=actor.pk)
    credential = queryset.get(pk=credential_id)
    _validate(credential)
    if actor is not None:
        _require_issuance(
            actor,
            user_id=credential.user_id,
            scopes=credential.scopes,
            corpus_ids=credential.corpus_ids,
        )
    token = _new_secret(credential)
    credential.rotated_at = timezone.now()
    credential.save(update_fields=["secret_hash", "rotated_at"])
    audit("rotated", credential, actor=actor)
    return credential, token


@transaction.atomic
def revoke(credential_id, *, actor=None):
    if actor is not None:
        actor = require_management(actor, lock=True)
    queryset = AutomationCredential.objects.select_for_update()
    if actor is not None and not actor.is_superuser:
        queryset = queryset.filter(user_id=actor.pk)
    credential = queryset.get(pk=credential_id)
    if credential.revoked_at is None:
        credential.revoked_at = timezone.now()
        credential.save(update_fields=["revoked_at"])
        audit("revoked", credential, actor=actor)
    return credential


def authenticate_token(token):
    try:
        credential_id, secret = token.split(".", 1)
        credential = AutomationCredential.objects.select_related("user").get(
            pk=credential_id
        )
    except (AutomationCredential.DoesNotExist, ValueError, TypeError):
        raise AuthenticationFailed(INVALID) from None
    # UUIDField reports malformed UUIDs as ValidationError, handled by the adapter.
    if not secrets.compare_digest(credential.secret_hash, _digest(secret)):
        raise AuthenticationFailed(INVALID)
    _validate(credential)
    credential.user.automation_credential = credential
    audit("authenticated", credential, actor=credential.user)
    return credential


def require_scope(user, scope, corpus_id=None):
    """No-op for JWT/session/worker actors; automation only narrows access.

    Authentication loads a fresh row on each request. Global/unbound operations
    require explicit all-corpus authorization, including corpus creation.
    """
    credential = getattr(user, "automation_credential", None)
    if credential is None:
        return
    if scope not in credential.scopes:
        raise PermissionDenied(DENIED)
    if credential.corpus_ids is not None and (
        corpus_id is None or corpus_pk(corpus_id) not in credential.corpus_ids
    ):
        raise PermissionDenied(DENIED)


def require_import(user, kind, metadata):
    """Same capability checks for direct imports and every chunked stage."""
    target = (
        metadata.get("corpus_id")
        if kind in ("zip_to_corpus", "corpus_export")
        else metadata.get("add_to_corpus_id")
    )
    target = target if target is not None and str(target).strip() else None
    require_scope(user, Scope.DOCUMENT_IMPORT, target)
    if kind == "corpus_export":
        require_scope(
            user, Scope.CORPUS_CONFIGURE if target else Scope.CORPUS_CREATE, target
        )
        # Export contents can publish documents/labels/annotations. The archive
        # is interpreted asynchronously, so require publication authority up front.
        require_scope(user, Scope.CORPUS_PUBLISH, target)
    elif metadata.get("make_public"):
        require_scope(user, Scope.CORPUS_PUBLISH, target)
