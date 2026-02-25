"""
GraphQL mutations and types for managing worker accounts and corpus access tokens.

Only superusers can create/manage worker accounts and tokens.
"""

import logging

import graphene
from graphql import GraphQLError
from graphql_jwt.decorators import user_passes_test

from opencontractserver.corpuses.models import Corpus
from opencontractserver.worker_uploads.models import (
    CorpusAccessToken,
    WorkerAccount,
)

logger = logging.getLogger(__name__)


# ============================================================================
# GraphQL Types
# ============================================================================


class WorkerAccountType(graphene.ObjectType):
    id = graphene.Int()
    name = graphene.String()
    description = graphene.String()
    is_active = graphene.Boolean()
    created = graphene.DateTime()
    token_count = graphene.Int()
    creator_username = graphene.String()


class CorpusAccessTokenType(graphene.ObjectType):
    id = graphene.Int()
    # Only show the key prefix after creation; full key shown only on creation
    key_prefix = graphene.String()
    worker_account_name = graphene.String()
    corpus_id = graphene.Int()
    corpus_title = graphene.String()
    expires_at = graphene.DateTime()
    is_active = graphene.Boolean()
    rate_limit_per_minute = graphene.Int()
    created = graphene.DateTime()
    upload_count = graphene.Int()


class CorpusAccessTokenCreatedType(graphene.ObjectType):
    """Returned only on token creation — includes the full key."""

    id = graphene.Int()
    key = graphene.String(
        description="Full token key. Store securely — shown only once."
    )
    worker_account_name = graphene.String()
    corpus_id = graphene.Int()
    expires_at = graphene.DateTime()
    rate_limit_per_minute = graphene.Int()
    created = graphene.DateTime()


class WorkerDocumentUploadType(graphene.ObjectType):
    id = graphene.String()
    status = graphene.String()
    corpus_id = graphene.Int()
    corpus_title = graphene.String()
    worker_account_name = graphene.String()
    error_message = graphene.String()
    created = graphene.DateTime()
    processing_started = graphene.DateTime()
    processing_finished = graphene.DateTime()


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
    def mutate(root, info, name, description=""):
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
    def mutate(root, info, worker_account_id):
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


class CreateCorpusAccessTokenMutation(graphene.Mutation):
    """
    Create a scoped access token granting a worker upload access to a corpus.

    Returns the full token key — it is only shown once. Superuser only.
    """

    class Arguments:
        worker_account_id = graphene.Int(required=True)
        corpus_id = graphene.Int(required=True)
        expires_at = graphene.DateTime(required=False, default_value=None)
        rate_limit_per_minute = graphene.Int(required=False, default_value=0)

    ok = graphene.Boolean()
    token = graphene.Field(CorpusAccessTokenCreatedType)

    @user_passes_test(lambda user: user.is_superuser)
    def mutate(
        root,
        info,
        worker_account_id,
        corpus_id,
        expires_at=None,
        rate_limit_per_minute=0,
    ):
        try:
            account = WorkerAccount.objects.get(id=worker_account_id)
        except WorkerAccount.DoesNotExist:
            raise GraphQLError("Worker account not found.")

        try:
            corpus = Corpus.objects.get(id=corpus_id)
        except Corpus.DoesNotExist:
            raise GraphQLError("Corpus not found.")

        token, plaintext_key = CorpusAccessToken.create_token(
            worker_account=account,
            corpus=corpus,
            expires_at=expires_at,
            rate_limit_per_minute=rate_limit_per_minute,
        )

        logger.info(
            f"Corpus access token created: worker={account.name}, "
            f"corpus={corpus.id}, token_id={token.id}, by user {info.context.user.id}"
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
    """Revoke a corpus access token. Superuser only."""

    class Arguments:
        token_id = graphene.Int(required=True)

    ok = graphene.Boolean()

    @user_passes_test(lambda user: user.is_superuser)
    def mutate(root, info, token_id):
        try:
            token = CorpusAccessToken.objects.get(id=token_id)
        except CorpusAccessToken.DoesNotExist:
            raise GraphQLError("Token not found.")

        token.is_active = False
        token.save(update_fields=["is_active"])

        logger.info(
            f"Corpus access token revoked: token_id={token.id}, "
            f"by user {info.context.user.id}"
        )

        return RevokeCorpusAccessTokenMutation(ok=True)
