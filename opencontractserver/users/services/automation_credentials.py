"""Credential lifecycle and shared scope checks; never confer user permissions."""

from __future__ import annotations

import hashlib
import logging
import secrets
from enum import Enum

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied

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


def corpus_pk(value):
    """Accept raw corpus PKs or correctly typed Relay IDs, fail closed otherwise."""
    try:
        if str(value).isdigit():
            return int(value)
        type_name, pk = from_global_id(str(value))
        if type_name == "CorpusType" and pk.isdigit():
            return int(pk)
    except (ValueError, TypeError, UnicodeError):
        pass
    raise PermissionDenied(DENIED)


def _digest(secret):
    return hashlib.sha256(secret.encode()).hexdigest()


def _new_secret(credential):
    secret = secrets.token_urlsafe(32)
    credential.secret_hash = _digest(secret)
    return f"{credential.pk}.{secret}"


def mint(*, user, name, scopes, corpus_ids, expires_at=None):
    scopes = sorted(set(scopes))
    if not user.is_active:
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
    credential = AutomationCredential(
        user=user,
        name=name,
        scopes=scopes,
        corpus_ids=corpus_ids,
        expires_at=expires_at,
    )
    token = _new_secret(credential)
    credential.save()
    audit("minted", credential)
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


def audit(event, credential):
    logger.info(
        "Automation credential %s credential_id=%s actor_id=%s",
        event,
        credential.pk,
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
def rotate(credential_id):
    credential = (
        AutomationCredential.objects.select_for_update()
        .select_related("user")
        .get(pk=credential_id)
    )
    _validate(credential)
    token = _new_secret(credential)
    credential.rotated_at = timezone.now()
    credential.save(update_fields=["secret_hash", "rotated_at"])
    audit("rotated", credential)
    return credential, token


@transaction.atomic
def revoke(credential_id):
    credential = AutomationCredential.objects.select_for_update().get(pk=credential_id)
    if credential.revoked_at is None:
        credential.revoked_at = timezone.now()
        credential.save(update_fields=["revoked_at"])
        audit("revoked", credential)
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
    audit("authenticated", credential)
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
