"""Credential management DTOs; no model/Node or secret-hash traversal."""

from contextlib import contextmanager
from datetime import datetime
from uuid import UUID

import strawberry
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.utils import timezone
from graphql import GraphQLError
from rest_framework.exceptions import APIException

from opencontractserver.constants.users import (
    AUTOMATION_CREDENTIAL_DEFAULT_DAYS,
    AUTOMATION_CREDENTIAL_PAGE_SIZE,
)
from opencontractserver.users.services import automation_credentials as credentials


@strawberry.type
class AutomationCredentialMetadata:
    id: UUID
    user_id: strawberry.ID
    username: str
    name: str
    scopes: list[str]
    corpus_ids: list[strawberry.ID] | None
    expires_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime
    rotated_at: datetime | None
    status: str


@strawberry.type
class AutomationCredentialPage:
    items: list[AutomationCredentialMetadata]
    total_count: int


@strawberry.type
class AutomationCredentialSecret:
    credential: AutomationCredentialMetadata
    token: str


@strawberry.type
class AutomationCredentialChoice:
    id: strawberry.ID
    label: str


@strawberry.type
class AutomationCredentialChoicePage:
    items: list[AutomationCredentialChoice]
    total_count: int


def _metadata(credential):
    values = credentials.metadata(credential)
    values["user_id"] = strawberry.ID(str(values["user_id"]))
    if values["corpus_ids"] is not None:
        values["corpus_ids"] = [strawberry.ID(str(pk)) for pk in values["corpus_ids"]]
    status = "active"
    if credential.revoked_at is not None:
        status = "revoked"
    elif credential.expires_at is not None and credential.expires_at <= timezone.now():
        status = "expired"
    elif not credential.user.is_active:
        status = "inactive principal"
    return AutomationCredentialMetadata(
        **values, username=credential.user.username, status=status
    )


@contextmanager
def _management(info):
    actor = info.context.user
    credentials.require_management(actor)
    info.context.automation_credential_management = True
    try:
        yield actor
    except (ValueError, ValidationError, ObjectDoesNotExist, APIException):
        raise GraphQLError("Invalid credential operation or arguments.") from None


def q_credentials(
    info: strawberry.Info,
    limit: int = AUTOMATION_CREDENTIAL_PAGE_SIZE,
    offset: int = 0,
) -> AutomationCredentialPage:
    with _management(info) as actor:
        rows, total = credentials.list_credentials(actor, limit=limit, offset=offset)
        return AutomationCredentialPage(
            items=[_metadata(row) for row in rows], total_count=total
        )


def q_credential(info: strawberry.Info, id: UUID) -> AutomationCredentialMetadata:
    with _management(info) as actor:
        return _metadata(credentials.inspect_credential(actor, id))


def q_scopes(info: strawberry.Info) -> list[str]:
    with _management(info) as actor:
        return credentials.management_scopes(actor)


def q_choices(
    info: strawberry.Info,
    kind: str,
    search: str = "",
    limit: int = AUTOMATION_CREDENTIAL_PAGE_SIZE,
    offset: int = 0,
) -> AutomationCredentialChoicePage:
    with _management(info) as actor:
        rows, total = credentials.management_choices(
            actor, kind=kind, search=search, limit=limit, offset=offset
        )
        return AutomationCredentialChoicePage(
            items=[
                AutomationCredentialChoice(id=strawberry.ID(pk), label=label)
                for pk, label in rows
            ],
            total_count=total,
        )


def m_mint(
    info: strawberry.Info,
    name: str,
    scopes: list[str],
    user_id: strawberry.ID | None = None,
    corpus_ids: list[strawberry.ID] | None = None,
    all_corpuses: bool = False,
    expires_days: int = AUTOMATION_CREDENTIAL_DEFAULT_DAYS,
) -> AutomationCredentialSecret:
    with _management(info) as actor:
        credential, token = credentials.mint_for_user(
            actor,
            user_id=user_id,
            name=name,
            scopes=scopes,
            corpus_ids=corpus_ids,
            all_corpuses=all_corpuses,
            expires_days=expires_days,
        )
        return AutomationCredentialSecret(credential=_metadata(credential), token=token)


def m_rotate(info: strawberry.Info, id: UUID) -> AutomationCredentialSecret:
    with _management(info) as actor:
        credential, token = credentials.rotate(id, actor=actor)
        return AutomationCredentialSecret(credential=_metadata(credential), token=token)


def m_revoke(info: strawberry.Info, id: UUID) -> AutomationCredentialMetadata:
    with _management(info) as actor:
        return _metadata(credentials.revoke(id, actor=actor))


QUERY_FIELDS = {
    "automation_credentials": strawberry.field(
        resolver=q_credentials, name="automationCredentials"
    ),
    "automation_credential": strawberry.field(
        resolver=q_credential, name="automationCredential"
    ),
    "automation_credential_scopes": strawberry.field(
        resolver=q_scopes, name="automationCredentialScopes"
    ),
    "automation_credential_choices": strawberry.field(
        resolver=q_choices, name="automationCredentialChoices"
    ),
}
MUTATION_FIELDS = {
    "mint_automation_credential": strawberry.mutation(
        resolver=m_mint, name="mintAutomationCredential"
    ),
    "rotate_automation_credential": strawberry.mutation(
        resolver=m_rotate, name="rotateAutomationCredential"
    ),
    "revoke_automation_credential": strawberry.mutation(
        resolver=m_revoke, name="revokeAutomationCredential"
    ),
}
