"""
GraphQL mutations for managing worker accounts and corpus access tokens.

Superusers can manage all worker accounts and tokens.
Corpus creators can create/revoke tokens scoped to their own corpuses.

All permission and lifecycle logic lives in
:mod:`opencontractserver.worker_uploads.services`; the mutations forward
arguments to the service and project the result onto the GraphQL output
type.
"""

import logging

import graphene
from graphql import GraphQLError
from graphql_jwt.decorators import login_required, user_passes_test

from config.graphql.worker_types import (
    CorpusAccessTokenCreatedType,
    WorkerAccountType,
)
from opencontractserver.worker_uploads.services import (
    CorpusAccessTokenService,
    WorkerAccountService,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Mutations
# ============================================================================


class CreateWorkerAccount(graphene.Mutation):
    """Create a new worker service account. Superuser only."""

    class Arguments:
        name = graphene.String(required=True)
        description = graphene.String(default_value="")

    ok = graphene.Boolean()
    worker_account = graphene.Field(WorkerAccountType)

    @user_passes_test(lambda user: user.is_superuser)
    def mutate(root, info, name, description="") -> "CreateWorkerAccount":
        result = WorkerAccountService.create_worker_account(
            info.context.user,
            name=name,
            description=description,
            request=info.context,
        )
        if not result.ok:
            raise GraphQLError(result.error)

        account = result.value
        assert account is not None  # narrowed by ``result.ok`` invariant
        return CreateWorkerAccount(
            ok=True,
            worker_account=WorkerAccountType(
                id=account.id,
                name=account.name,
                description=account.description,
                is_active=account.is_active,
                created=account.created,
            ),
        )


class DeactivateWorkerAccount(graphene.Mutation):
    """Deactivate a worker account (revokes all its tokens implicitly). Superuser only."""

    class Arguments:
        worker_account_id = graphene.Int(required=True)

    ok = graphene.Boolean()

    @user_passes_test(lambda user: user.is_superuser)
    def mutate(root, info, worker_account_id) -> "DeactivateWorkerAccount":
        result = WorkerAccountService.set_active(
            info.context.user,
            worker_account_id,
            active=False,
            request=info.context,
        )
        if not result.ok:
            raise GraphQLError(result.error)
        return DeactivateWorkerAccount(ok=True)


class ReactivateWorkerAccount(graphene.Mutation):
    """Reactivate a previously deactivated worker account. Superuser only."""

    class Arguments:
        worker_account_id = graphene.Int(required=True)

    ok = graphene.Boolean()

    @user_passes_test(lambda user: user.is_superuser)
    def mutate(root, info, worker_account_id) -> "ReactivateWorkerAccount":
        result = WorkerAccountService.set_active(
            info.context.user,
            worker_account_id,
            active=True,
            request=info.context,
        )
        if not result.ok:
            raise GraphQLError(result.error)
        return ReactivateWorkerAccount(ok=True)


class CreateCorpusAccessTokenMutation(graphene.Mutation):
    """
    Create a scoped access token granting a worker upload access to a corpus.

    Returns the full token key — it is only shown once.
    Allowed for superusers and the corpus creator.
    """

    class Arguments:
        worker_account_id = graphene.Int(required=True)
        corpus_id = graphene.Int(required=True)
        expires_at = graphene.DateTime(required=False, default_value=None)
        rate_limit_per_minute = graphene.Int(required=False, default_value=0)

    ok = graphene.Boolean()
    token = graphene.Field(CorpusAccessTokenCreatedType)

    @login_required
    def mutate(
        root,
        info,
        worker_account_id,
        corpus_id,
        expires_at=None,
        rate_limit_per_minute=0,
    ) -> "CreateCorpusAccessTokenMutation":
        result = CorpusAccessTokenService.create_token(
            info.context.user,
            worker_account_id=worker_account_id,
            corpus_id=corpus_id,
            expires_at=expires_at,
            rate_limit_per_minute=rate_limit_per_minute,
            request=info.context,
        )
        if not result.ok:
            raise GraphQLError(result.error)

        assert result.value is not None  # narrowed by ``result.ok`` invariant
        token, plaintext_key = result.value
        return CreateCorpusAccessTokenMutation(
            ok=True,
            token=CorpusAccessTokenCreatedType(
                id=token.id,
                key=plaintext_key,
                worker_account_name=token.worker_account.name,
                corpus_id=token.corpus_id,
                expires_at=token.expires_at,
                rate_limit_per_minute=token.rate_limit_per_minute,
                created=token.created,
            ),
        )


class RevokeCorpusAccessTokenMutation(graphene.Mutation):
    """Revoke a corpus access token. Allowed for superusers and the corpus creator."""

    class Arguments:
        token_id = graphene.Int(required=True)

    ok = graphene.Boolean()

    @login_required
    def mutate(root, info, token_id) -> "RevokeCorpusAccessTokenMutation":
        result = CorpusAccessTokenService.revoke_token(
            info.context.user, token_id, request=info.context
        )
        if not result.ok:
            raise GraphQLError(result.error)
        return RevokeCorpusAccessTokenMutation(ok=True)
