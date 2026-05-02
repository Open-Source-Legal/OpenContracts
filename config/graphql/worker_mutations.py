"""
GraphQL mutations for managing worker accounts and corpus access tokens.

Superusers can manage all worker accounts and tokens.
Corpus creators can create/revoke tokens scoped to their own corpuses.
"""

import logging

import graphene
from graphql import GraphQLError
from graphql_jwt.decorators import login_required, user_passes_test

from config.graphql.worker_types import (
    CorpusAccessTokenCreatedType,
    WorkerAccountType,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.worker_uploads.models import (
    CorpusAccessToken,
    WorkerAccount,
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
        user = info.context.user

        try:
            account = WorkerAccount.create_with_user(
                name=name,
                description=description,
                creator=user,
            )
        except ValueError as e:
            raise GraphQLError(str(e))

        logger.info(f"Worker account created: {account.name} by user {user.id}")

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
        try:
            account = WorkerAccount.objects.get(id=worker_account_id)
        except WorkerAccount.DoesNotExist:
            raise GraphQLError("Worker account not found.")

        account.is_active = False
        account.save(update_fields=["is_active"])

        logger.info(
            f"Worker account deactivated: {account.name} "
            f"by user {info.context.user.id}"
        )

        return DeactivateWorkerAccount(ok=True)


class ReactivateWorkerAccount(graphene.Mutation):
    """Reactivate a previously deactivated worker account. Superuser only."""

    class Arguments:
        worker_account_id = graphene.Int(required=True)

    ok = graphene.Boolean()

    @user_passes_test(lambda user: user.is_superuser)
    def mutate(root, info, worker_account_id) -> "ReactivateWorkerAccount":
        try:
            account = WorkerAccount.objects.get(id=worker_account_id)
        except WorkerAccount.DoesNotExist:
            raise GraphQLError("Worker account not found.")

        account.is_active = True
        account.save(update_fields=["is_active"])

        logger.info(
            f"Worker account reactivated: {account.name} "
            f"by user {info.context.user.id}"
        )

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
        user = info.context.user

        try:
            corpus = Corpus.objects.get(id=corpus_id)
        except Corpus.DoesNotExist:
            raise GraphQLError("Corpus not found.")

        if not user.is_superuser and (not corpus.creator or corpus.creator != user):
            raise GraphQLError("Permission denied.")

        try:
            account = WorkerAccount.objects.get(id=worker_account_id)
        except WorkerAccount.DoesNotExist:
            raise GraphQLError("Worker account not found.")

        token, plaintext_key = CorpusAccessToken.create_token(
            worker_account=account,
            corpus=corpus,
            expires_at=expires_at,
            rate_limit_per_minute=rate_limit_per_minute,
        )

        logger.info(
            f"Corpus access token created: worker={account.name}, "
            f"corpus={corpus.id}, token_id={token.id}, by user {user.id}"
        )

        return CreateCorpusAccessTokenMutation(
            ok=True,
            token=CorpusAccessTokenCreatedType(
                id=token.id,
                key=plaintext_key,
                worker_account_name=account.name,
                corpus_id=corpus.id,
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
        user = info.context.user

        qs = CorpusAccessToken.objects.select_related("corpus").filter(id=token_id)
        if not user.is_superuser:
            qs = qs.filter(corpus__creator=user)
        token = qs.first()
        if token is None:
            raise GraphQLError("Not found or permission denied.")

        token.is_active = False
        token.save(update_fields=["is_active"])

        logger.info(
            f"Corpus access token revoked: token_id={token.id}, " f"by user {user.id}"
        )

        return RevokeCorpusAccessTokenMutation(ok=True)
