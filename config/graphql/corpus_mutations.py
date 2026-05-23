"""
GraphQL mutations for corpus CRUD, visibility, fork, and action operations.
"""

import logging
from typing import Any

import graphene
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import DatabaseError, IntegrityError, transaction
from django.utils import timezone
from graphql_jwt.decorators import login_required, user_passes_test
from graphql_relay import from_global_id, to_global_id

from config.graphql.base import DRFDeletion, DRFMutation
from config.graphql.graphene_types import (
    CorpusActionExecutionType,
    CorpusActionType,
    CorpusType,
)
from config.graphql.ratelimits import RateLimits, graphql_ratelimit
from config.graphql.serializers import CorpusSerializer
from config.telemetry import record_event
from opencontractserver.analyzer.models import Analyzer
from opencontractserver.corpuses.models import (
    Corpus,
    CorpusAction,
    CorpusActionTemplate,
)
from opencontractserver.corpuses.services import CorpusService
from opencontractserver.documents.models import Document
from opencontractserver.extracts.models import Fieldset
from opencontractserver.tasks import fork_corpus
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.corpus_collector import collect_corpus_objects
from opencontractserver.utils.permissioning import (
    get_for_user_or_none,
    set_permissions_for_obj_to_user,
)

logger = logging.getLogger(__name__)


class SetCorpusVisibility(graphene.Mutation):
    """
    Set corpus visibility (public/private).

    Requires one of:
    - User is the corpus creator (owner), OR
    - User has PERMISSION permission on the corpus, OR
    - User is superuser

    Security notes:
    - Permission check prevents users from escalating access
    - Uses existing make_corpus_public_task for cascading public visibility
    - Making private only affects the corpus flag (child objects remain public)
    """

    class Arguments:
        corpus_id = graphene.ID(
            required=True, description="ID of the corpus to change visibility for"
        )
        is_public = graphene.Boolean(
            required=True, description="True to make public, False to make private"
        )

    ok = graphene.Boolean()
    message = graphene.String()

    @login_required
    @graphql_ratelimit(rate=RateLimits.WRITE_MEDIUM)
    def mutate(root, info, corpus_id, is_public) -> "SetCorpusVisibility":
        user = info.context.user

        # IDOR protection: same response whether the global ID is malformed,
        # the corpus doesn't exist, the caller can't READ it, or the caller
        # can READ but lacks PERMISSION. ``get_for_user_or_none`` enforces the
        # READ gate; ``CorpusService.set_visibility`` adds the PERMISSION check.
        not_found_msg = "Corpus not found or you don't have permission"

        try:
            corpus_pk = from_global_id(corpus_id)[1]
        except Exception:
            return SetCorpusVisibility(ok=False, message=not_found_msg)

        corpus = get_for_user_or_none(Corpus, corpus_pk, user)
        if corpus is None:
            return SetCorpusVisibility(ok=False, message=not_found_msg)

        result = CorpusService.set_visibility(
            user, corpus, is_public, request=info.context
        )
        return SetCorpusVisibility(
            ok=result.ok,
            message=result.value if result.ok else result.error,
        )


class CreateCorpusMutation(DRFMutation):
    class IOSettings:
        pk_fields = ["label_set", "categories"]
        serializer = CorpusSerializer
        model = Corpus
        graphene_model = CorpusType

    class Arguments:
        title = graphene.String(required=False)
        description = graphene.String(required=False)
        icon = graphene.String(required=False)
        label_set = graphene.String(required=False)
        preferred_embedder = graphene.String(required=False)
        slug = graphene.String(required=False)
        categories = graphene.List(
            graphene.ID, required=False, description="Category IDs to assign"
        )
        license = graphene.String(
            required=False, description="SPDX license identifier (e.g. CC-BY-4.0)"
        )
        license_link = graphene.String(
            required=False,
            description="URL to full license text (required for CUSTOM license)",
        )

    @classmethod
    def mutate(cls, root, info, *args, **kwargs) -> "CreateCorpusMutation":
        # Pre-fill the install-wide default LabelSet when the caller didn't
        # pick one, so corpuses created through the API land with a usable
        # starter palette. We default here (mutation layer) rather than in
        # Corpus.save() to keep direct ORM creates in tests/scripts opt-in.
        if not kwargs.get("label_set"):
            from opencontractserver.annotations.models import LabelSet

            default_labelset = (
                LabelSet.objects.visible_to_user(info.context.user)
                .filter(is_default=True)
                .first()
            )
            if default_labelset is not None:
                kwargs["label_set"] = to_global_id("LabelSetType", default_labelset.pk)

        result = super().mutate(root, info, *args, **kwargs)

        if result.ok and result.obj_id:
            obj_pk = from_global_id(result.obj_id)[1]
            corpus = cls.IOSettings.model.objects.get(pk=obj_pk)
            # Grant creator full permissions including PERMISSION to manage access
            CorpusService.grant_creator_permissions(
                info.context.user, corpus, request=info.context
            )

        return result


class UpdateCorpusMutation(DRFMutation):
    class IOSettings:
        lookup_field = "id"
        pk_fields = ["label_set", "categories"]
        serializer = CorpusSerializer
        model = Corpus
        graphene_model = CorpusType

    class Arguments:
        id = graphene.String(required=True)
        title = graphene.String(required=False)
        description = graphene.String(required=False)
        icon = graphene.String(required=False)
        label_set = graphene.String(required=False)
        preferred_embedder = graphene.String(required=False)
        slug = graphene.String(required=False)
        # NOTE: is_public removed - use SetCorpusVisibility mutation instead
        # This prevents bypassing permission checks via UpdateCorpusMutation
        corpus_agent_instructions = graphene.String(required=False)
        document_agent_instructions = graphene.String(required=False)
        categories = graphene.List(
            graphene.ID,
            required=False,
            description="Category IDs to assign (replaces existing)",
        )
        license = graphene.String(
            required=False, description="SPDX license identifier (e.g. CC-BY-4.0)"
        )
        license_link = graphene.String(
            required=False,
            description="URL to full license text (required for CUSTOM license)",
        )

    @classmethod
    def mutate(cls, root, info, *args, **kwargs) -> "UpdateCorpusMutation":
        # Issue #437: Prevent changing preferred_embedder after documents exist.
        # This avoids creating inconsistent embeddings within a corpus.
        # Use the ReEmbedCorpus mutation instead for controlled embedder
        # migration. We filter through ``visible_to_user`` so a caller who
        # can't see the corpus doesn't get a leaked "this corpus has docs"
        # signal from the early-exit — they fall through to the parent's
        # standard not-found / not-permitted response.
        if "preferred_embedder" in kwargs:
            corpus_global_id = kwargs.get("id")
            if corpus_global_id:
                # A malformed base64 id raises in ``from_global_id``; skip the
                # pre-check and let the parent ``super().mutate()`` return its
                # standard not-found / not-permitted response.
                try:
                    corpus_pk = from_global_id(corpus_global_id)[1]
                except Exception:
                    corpus_pk = None
                corpus = (
                    get_for_user_or_none(Corpus, corpus_pk, info.context.user)
                    if corpus_pk is not None
                    else None
                )
                if corpus is not None:
                    embedder_error = CorpusService.assert_embedder_change_allowed(
                        corpus, kwargs["preferred_embedder"]
                    )
                    if embedder_error:
                        return cls(ok=False, message=embedder_error)

        return super().mutate(root, info, *args, **kwargs)


class UpdateCorpusDescription(graphene.Mutation):
    """
    Mutation to update a corpus's markdown description, creating a new version in the process.
    Only the corpus creator can update the description.
    """

    class Arguments:
        corpus_id = graphene.ID(required=True, description="ID of the corpus to update")
        new_content = graphene.String(
            required=True, description="New markdown content for the corpus description"
        )

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(CorpusType)
    version = graphene.Int(description="The new version number after update")

    @login_required
    def mutate(root, info, corpus_id, new_content) -> "UpdateCorpusDescription":
        from opencontractserver.corpuses.models import Corpus

        try:
            user = info.context.user
            corpus_pk = from_global_id(corpus_id)[1]

            # Unified message prevents IDOR enumeration of corpora the caller cannot edit
            not_found_msg = (
                "Corpus not found or you do not have permission to update it."
            )

            # ``get_for_user_or_none`` enforces the READ gate;
            # ``CorpusService.update_description`` enforces the creator-only
            # rule (collaborators with a guardian UPDATE grant still cannot
            # edit the description, so its history stays attributable to a
            # single author) and returns the same unified IDOR-safe message.
            corpus = get_for_user_or_none(Corpus, corpus_pk, user)
            if corpus is None:
                return UpdateCorpusDescription(
                    ok=False, message=not_found_msg, obj=None, version=None
                )

            result = CorpusService.update_description(user, corpus, new_content)
            if not result.ok:
                return UpdateCorpusDescription(
                    ok=False, message=result.error, obj=None, version=None
                )
            revision = result.value

            if revision is None:
                # No changes were made
                return UpdateCorpusDescription(
                    ok=True,
                    message="No changes detected. Description remains at current version.",
                    obj=corpus,
                    version=corpus.revisions.count(),
                )

            # Refresh the corpus to get the updated state
            corpus.refresh_from_db()

            return UpdateCorpusDescription(
                ok=True,
                message=f"Corpus description updated successfully. Now at version {revision.version}.",
                obj=corpus,
                version=revision.version,
            )

        except Exception as e:
            logger.error(f"Error updating corpus description: {e}")
            return UpdateCorpusDescription(
                ok=False,
                message=f"Failed to update corpus description: {str(e)}",
                obj=None,
                version=None,
            )


class DeleteCorpusMutation(graphene.Mutation):
    ok = graphene.Boolean()
    message = graphene.String()

    class Arguments:
        id = graphene.String(required=True)

    @classmethod
    @login_required
    @graphql_ratelimit(rate=RateLimits.WRITE_LIGHT)
    def mutate(cls, root, info, id) -> "DeleteCorpusMutation":
        # Unified IDOR-safe envelope: same response whether the corpus
        # doesn't exist, the caller can't see it, or they can see it but
        # lack DELETE permission.  ``get_for_user_or_none`` enforces the READ
        # gate; ``CorpusService.delete_corpus`` runs the personal-corpus,
        # user-lock, and DELETE-permission checks. Returning ``ok=False``
        # (rather than raising ``Corpus.DoesNotExist``) keeps the response
        # shape consistent so the frontend can always pattern-match on
        # ``data.deleteCorpus.ok``.
        not_found_msg = "Corpus not found or you don't have permission to delete it."

        try:
            corpus_pk = from_global_id(id)[1]
        except Exception:
            return cls(ok=False, message=not_found_msg)

        obj = get_for_user_or_none(Corpus, corpus_pk, info.context.user)
        if obj is None:
            return cls(ok=False, message=not_found_msg)

        result = CorpusService.delete_corpus(
            info.context.user, obj, request=info.context
        )
        return cls(
            ok=result.ok,
            message="Success!" if result.ok else result.error,
        )


class AddDocumentsToCorpus(graphene.Mutation):
    """Add existing documents to a corpus.

    Delegates to CorpusDocumentService.add_documents_to_corpus() for:
    - Permission checking (corpus UPDATE permission)
    - Document validation (user owns or public)
    - Dual-system update (DocumentPath + corpus.add_document)
    """

    class Arguments:
        corpus_id = graphene.String(
            required=True, description="ID of corpus to add documents to."
        )
        document_ids = graphene.List(
            graphene.String,
            required=True,
            description="List of ids of the docs to add to corpus.",
        )

    ok = graphene.Boolean()
    message = graphene.String()

    @login_required
    def mutate(root, info, corpus_id, document_ids) -> "AddDocumentsToCorpus":
        from opencontractserver.corpuses.services import CorpusDocumentService

        # Unified message prevents enumeration of corpora the caller cannot see/edit
        not_found_msg = (
            "Corpus not found or you do not have permission to add documents to it"
        )
        # Decode global ids up-front so a malformed id surfaces as a clean
        # envelope rather than echoing raw exception text through the outer
        # ``except Exception`` (IDOR review on PR #1693). The corpus and the
        # document ids are decoded separately so a malformed *document* id
        # does not return a misleading corpus-scoped message.
        try:
            corpus_pk = from_global_id(corpus_id)[1]
        except Exception:
            return AddDocumentsToCorpus(message=not_found_msg, ok=False)
        try:
            doc_pks = [int(from_global_id(doc_id)[1]) for doc_id in document_ids]
        except Exception:
            return AddDocumentsToCorpus(
                message="One or more document ids are invalid", ok=False
            )
        try:
            user = info.context.user
            corpus = get_for_user_or_none(Corpus, corpus_pk, user)
            if corpus is None:
                return AddDocumentsToCorpus(message=not_found_msg, ok=False)

            # Delegate to service - handles permission checks, validation, dual-system update
            added_count, added_ids, error = (
                CorpusDocumentService.add_documents_to_corpus(
                    user=user,
                    document_ids=doc_pks,
                    corpus=corpus,
                    folder=None,  # No folder specified - add to root
                    request=info.context,
                )
            )

            if error:
                return AddDocumentsToCorpus(message=error, ok=False)

            return AddDocumentsToCorpus(
                message=f"Successfully added {added_count} document(s)",
                ok=True,
            )

        except Exception as e:
            return AddDocumentsToCorpus(message=f"Error on upload: {e}", ok=False)


class RemoveDocumentsFromCorpus(graphene.Mutation):
    """Remove documents from a corpus (soft-delete).

    Delegates to CorpusDocumentService.remove_documents_from_corpus() for:
    - Permission checking (corpus UPDATE permission)
    - Soft-delete via DocumentPath (creates is_deleted=True record)
    - Audit trail
    """

    class Arguments:
        corpus_id = graphene.String(
            required=True, description="ID of corpus to remove documents from."
        )
        document_ids_to_remove = graphene.List(
            graphene.String,
            required=True,
            description="List of ids of the docs to remove from corpus.",
        )

    ok = graphene.Boolean()
    message = graphene.String()

    @login_required
    def mutate(
        root, info, corpus_id, document_ids_to_remove
    ) -> "RemoveDocumentsFromCorpus":
        from opencontractserver.corpuses.services import CorpusDocumentService

        # Unified message prevents enumeration of corpora the caller cannot see/edit
        not_found_msg = (
            "Corpus not found or you do not have permission to remove documents from it"
        )
        # Decode global ids up-front so a malformed id surfaces as a clean
        # envelope rather than echoing raw exception text through the outer
        # ``except Exception`` (IDOR review on PR #1693). The corpus and the
        # document ids are decoded separately so a malformed *document* id
        # does not return a misleading corpus-scoped message.
        try:
            corpus_pk = from_global_id(corpus_id)[1]
        except Exception:
            return RemoveDocumentsFromCorpus(message=not_found_msg, ok=False)
        try:
            doc_pks = [
                int(from_global_id(doc_id)[1]) for doc_id in document_ids_to_remove
            ]
        except Exception:
            return RemoveDocumentsFromCorpus(
                message="One or more document ids are invalid", ok=False
            )
        try:
            user = info.context.user
            corpus = get_for_user_or_none(Corpus, corpus_pk, user)
            if corpus is None:
                return RemoveDocumentsFromCorpus(message=not_found_msg, ok=False)

            # Delegate to service - handles permission checks, soft-delete, audit trail
            removed_count, error = CorpusDocumentService.remove_documents_from_corpus(
                user=user,
                document_ids=doc_pks,
                corpus=corpus,
                request=info.context,
            )

            if error:
                return RemoveDocumentsFromCorpus(message=error, ok=False)

            return RemoveDocumentsFromCorpus(
                message=f"Successfully removed {removed_count} document(s)",
                ok=True,
            )

        except Exception as e:
            return RemoveDocumentsFromCorpus(message=f"Error on removal: {e}", ok=False)


class StartCorpusFork(graphene.Mutation):
    class Arguments:
        corpus_id = graphene.String(
            required=True,
            description="Graphene id of the corpus you want to package for export",
        )
        preferred_embedder = graphene.String(
            required=False,
            description=(
                "Override the embedder for the forked corpus. If provided and "
                "different from the source corpus, the fork will generate new "
                "embeddings using this embedder. If not provided, inherits "
                "the source corpus's preferred_embedder."
            ),
        )

    ok = graphene.Boolean()
    message = graphene.String()
    new_corpus = graphene.Field(CorpusType)

    @login_required
    def mutate(root, info, corpus_id, preferred_embedder=None) -> "StartCorpusFork":

        ok = False
        message = ""
        new_corpus = None

        try:

            # Get annotation ids for the old corpus - these refer to a corpus, doc and label by id, so easaiest way to
            # copy these is to first filter by annotations for our corpus. Then, later, we'll use a dict to map old ids
            # for labels and docs to new obj ids
            # Pre-guard ``from_global_id``: a malformed base64 id raises before
            # the helper is reached, so catch it here and return the same
            # unified IDOR-safe message as a missing / hidden corpus.
            try:
                corpus_pk = from_global_id(corpus_id)[1]
            except Exception:
                return StartCorpusFork(
                    ok=False,
                    message="Corpus not found or you don't have permission to fork it.",
                    new_corpus=None,
                )

            # IDOR protection: ``get_for_user_or_none`` filters through
            # ``visible_to_user``, which already enforces READ — missing
            # pk and no-READ collapse to the same ``None`` return.
            corpus = get_for_user_or_none(Corpus, corpus_pk, info.context.user)
            if corpus is None:
                return StartCorpusFork(
                    ok=False,
                    message="Corpus not found or you don't have permission to fork it.",
                    new_corpus=None,
                )

            # Collect all object IDs using the shared collector
            collected = collect_corpus_objects(corpus, include_metadata=True)

            # Clone the corpus: https://docs.djangoproject.com/en/3.1/topics/db/queries/copying-model-instances
            corpus.pk = None
            corpus.slug = ""  # Clear slug so save() generates a new unique one

            # Adjust the title to indicate it's a fork
            corpus.title = f"[FORK] {corpus.title}"

            # Issue #437: Allow specifying a different embedder for the forked corpus.
            # If provided, the fork's ensure_embeddings_for_corpus will automatically
            # generate new embeddings using the target embedder when documents are added.
            if preferred_embedder:
                corpus.preferred_embedder = preferred_embedder

            # lock the corpus which will tell frontend to show this as loading and disable selection
            corpus.backend_lock = True
            corpus.creator = info.context.user  # switch the creator to the current user
            corpus.parent_id = corpus_pk
            corpus.save()

            set_permissions_for_obj_to_user(
                info.context.user,
                corpus,
                [PermissionTypes.CRUD],
                request=info.context,
            )

            # Now remove references to related objects on our new object, as these point to original docs and labels
            # Note: New forked corpus has no DocumentPath records yet, so no document cleanup needed
            corpus.label_set = None

            # Copy docs, annotations, folders, relationships, and metadata using async task
            # to avoid massive lag if we have large dataset or lots of users requesting copies.
            # Use on_commit to ensure corpus is persisted before task runs.
            # Capture args as defaults to avoid late-binding closure issues.
            def dispatch_fork_task(
                _corpus_id=corpus.id,
                _collected=collected,
                _user_id=info.context.user.id,
            ) -> Any:
                fork_corpus.si(
                    _corpus_id,
                    _collected.document_ids,
                    _collected.label_set_id,
                    _collected.annotation_ids,
                    _collected.folder_ids,
                    _collected.relationship_ids,
                    _user_id,
                    _collected.metadata_column_ids,
                    _collected.metadata_datacell_ids,
                ).apply_async()

            transaction.on_commit(dispatch_fork_task)

            ok = True
            new_corpus = corpus

        except Exception as e:
            message = f"Error trying to fork corpus with id {corpus_id}: {e}"
            logger.error(message)

        record_event(
            "corpus_forked",
            {
                "env": settings.MODE,
                "user_id": info.context.user.id,
            },
        )

        return StartCorpusFork(ok=ok, message=message, new_corpus=new_corpus)


class ReEmbedCorpus(graphene.Mutation):
    """
    Re-embed all annotations in a corpus with a different embedder (Issue #437).

    This is the controlled migration path for changing a corpus's embedder
    after documents have been added. It:
    1. Validates the new embedder exists in the registry
    2. Locks the corpus (backend_lock=True)
    3. Queues a background task that updates preferred_embedder and
       generates new embeddings for all annotations
    4. The corpus unlocks automatically when re-embedding completes

    Only the corpus creator can trigger re-embedding.
    """

    class Arguments:
        corpus_id = graphene.String(
            required=True,
            description="Global ID of the corpus to re-embed",
        )
        new_embedder = graphene.String(
            required=True,
            description=(
                "Fully qualified Python path to the new embedder class "
                "(e.g., 'opencontractserver.pipeline.embedders."
                "sent_transformer_microservice.MicroserviceEmbedder')"
            ),
        )

    ok = graphene.Boolean()
    message = graphene.String()

    @login_required
    def mutate(root, info, corpus_id, new_embedder) -> "ReEmbedCorpus":
        from opencontractserver.pipeline.base.embedder import BaseEmbedder
        from opencontractserver.pipeline.utils import get_component_by_name
        from opencontractserver.tasks.corpus_tasks import reembed_corpus

        user = info.context.user

        try:
            corpus_pk = from_global_id(corpus_id)[1]
        except Exception:
            return ReEmbedCorpus(ok=False, message="Corpus not found")

        # IDOR protection: same response for missing pk, hidden pk, and
        # caller-is-not-creator.
        corpus = get_for_user_or_none(Corpus, corpus_pk, user)
        if corpus is None or corpus.creator != user:
            return ReEmbedCorpus(ok=False, message="Corpus not found")

        # Validate the new embedder exists in the registry and is an embedder
        try:
            embedder_class = get_component_by_name(new_embedder)
            if embedder_class is None:
                return ReEmbedCorpus(
                    ok=False,
                    message=f"Embedder '{new_embedder}' not found in the registry.",
                )
            if not issubclass(embedder_class, BaseEmbedder):
                return ReEmbedCorpus(
                    ok=False,
                    message=f"'{new_embedder}' is not an embedder component.",
                )
        except Exception as e:
            return ReEmbedCorpus(
                ok=False,
                message=f"Invalid embedder path: {e}",
            )

        # No-op if the embedder is already the same
        if corpus.preferred_embedder == new_embedder:
            return ReEmbedCorpus(
                ok=True,
                message="Corpus already uses this embedder. No re-embedding needed.",
            )

        # Atomically lock the corpus to prevent concurrent re-embed operations.
        # Uses UPDATE ... WHERE to avoid TOCTOU race conditions.
        locked = Corpus.objects.filter(pk=corpus.pk, backend_lock=False).update(
            backend_lock=True, modified=timezone.now()
        )

        if locked == 0:
            return ReEmbedCorpus(
                ok=False,
                message="Corpus is currently locked by another operation. "
                "Please wait for it to complete.",
            )

        transaction.on_commit(
            lambda: reembed_corpus.delay(
                corpus_id=corpus.pk,
                new_embedder_path=new_embedder,
            )
        )

        return ReEmbedCorpus(
            ok=True,
            message=f"Re-embedding started. The corpus will use "
            f"'{new_embedder}' once complete.",
        )


class CreateCorpusAction(graphene.Mutation):
    """
    Create a new CorpusAction that will be triggered when events occur in a corpus.

    Action types:
    - **Fieldset**: Run data extraction (fieldset_id)
    - **Analyzer**: Run classification/annotation (analyzer_id)
    - **Agent**: Execute an AI agent task. Provide task_instructions describing what the
      agent should do. Optionally link an agent_config_id for custom persona/tool defaults,
      or use create_agent_inline=True for thread/message moderation.
    - **Lightweight agent**: Just provide task_instructions (no agent_config needed).
      The system auto-selects tools based on the trigger type.

    Requires UPDATE permission on the corpus.
    """

    class Arguments:
        corpus_id = graphene.ID(
            required=True, description="ID of the corpus this action is for"
        )
        name = graphene.String(required=False, description="Name of the action")
        trigger = graphene.String(
            required=True,
            description="When to trigger: add_document, edit_document, new_thread, new_message",
        )
        fieldset_id = graphene.ID(
            required=False, description="ID of the fieldset to run"
        )
        analyzer_id = graphene.ID(
            required=False, description="ID of the analyzer to run"
        )
        # Agent-based action arguments
        task_instructions = graphene.String(
            required=False,
            description="What the agent should do. This is the single required "
            "field for agent actions (e.g., 'Read this document and update its "
            "description with a one-paragraph summary').",
        )
        agent_config_id = graphene.ID(
            required=False,
            description="Optional agent configuration for persona/tool defaults. "
            "Not required — task_instructions alone is sufficient for agent actions.",
        )
        pre_authorized_tools = graphene.List(
            graphene.String,
            required=False,
            description="Tools pre-authorized to run without approval. "
            "If empty, uses agent_config tools or trigger-appropriate defaults.",
        )
        # Inline agent creation arguments (for thread/message triggers)
        create_agent_inline = graphene.Boolean(
            required=False,
            description="Create a new agent inline instead of using existing agent_config_id",
        )
        inline_agent_name = graphene.String(
            required=False,
            description="Name for the new inline agent (required if create_agent_inline=True)",
        )
        inline_agent_description = graphene.String(
            required=False,
            description="Description for the new inline agent",
        )
        inline_agent_instructions = graphene.String(
            required=False,
            description="System instructions for the new inline agent (required if create_agent_inline=True)",
        )
        inline_agent_tools = graphene.List(
            graphene.String,
            required=False,
            description="Tools available to the new inline agent",
        )
        disabled = graphene.Boolean(
            required=False, description="Whether the action is disabled"
        )
        run_on_all_corpuses = graphene.Boolean(
            required=False, description="Whether to run this action on all corpuses"
        )

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(CorpusActionType)

    @login_required
    def mutate(
        root,
        info,
        corpus_id: str,
        trigger: str,
        name: str | None = None,
        fieldset_id: str | None = None,
        analyzer_id: str | None = None,
        task_instructions: str | None = None,
        agent_config_id: str | None = None,
        pre_authorized_tools: list | None = None,
        create_agent_inline: bool = False,
        inline_agent_name: str | None = None,
        inline_agent_description: str | None = None,
        inline_agent_instructions: str | None = None,
        inline_agent_tools: list | None = None,
        disabled: bool = False,
        run_on_all_corpuses: bool = False,
    ) -> "CreateCorpusAction":
        from opencontractserver.agents.models import AgentConfiguration

        try:
            user = info.context.user
            no_permission_msg = (
                "You don't have permission to create actions on this corpus"
            )
            # Pre-guard ``from_global_id``: a malformed base64 id raises before
            # the helper is reached — return the same unified message as a
            # missing / hidden / no-permission corpus.
            try:
                corpus_pk = from_global_id(corpus_id)[1]
            except Exception:
                return CreateCorpusAction(ok=False, message=no_permission_msg, obj=None)

            # Get corpus with visibility filter to prevent IDOR. ``None``
            # short-circuits to the same unified message as a no-CRUD result
            # so missing / hidden / no-permission look identical to the caller.
            corpus = get_for_user_or_none(Corpus, corpus_pk, user)
            if corpus is None or not corpus.user_can(
                user, PermissionTypes.CRUD, request=info.context
            ):
                return CreateCorpusAction(
                    ok=False,
                    message=no_permission_msg,
                    obj=None,
                )

            # Validate inline agent creation parameters
            if create_agent_inline:
                if not inline_agent_name:
                    return CreateCorpusAction(
                        ok=False,
                        message="inline_agent_name is required when create_agent_inline=True",
                        obj=None,
                    )
                if not inline_agent_instructions:
                    return CreateCorpusAction(
                        ok=False,
                        message="inline_agent_instructions is required when create_agent_inline=True",
                        obj=None,
                    )
                if not task_instructions:
                    return CreateCorpusAction(
                        ok=False,
                        message="task_instructions is required when creating an agent action",
                        obj=None,
                    )
                # Cannot provide both inline creation and existing agent
                if agent_config_id:
                    return CreateCorpusAction(
                        ok=False,
                        message="Cannot provide both agent_config_id and create_agent_inline=True",
                        obj=None,
                    )

            # For thread/message triggers with inline agent, validate tools are moderation category.
            if create_agent_inline and trigger in ["new_thread", "new_message"]:
                from opencontractserver.llms.tools.tool_registry import (
                    TOOL_REGISTRY,
                    ToolCategory,
                )

                valid_moderation_tools = {
                    tool.name
                    for tool in TOOL_REGISTRY
                    if tool.category == ToolCategory.MODERATION
                }

                if not inline_agent_tools:
                    return CreateCorpusAction(
                        ok=False,
                        message="At least one tool is required for moderation agents. "
                        f"Available moderation tools: {', '.join(sorted(valid_moderation_tools))}",
                        obj=None,
                    )

                invalid_tools = set(inline_agent_tools) - valid_moderation_tools
                if invalid_tools:
                    return CreateCorpusAction(
                        ok=False,
                        message=f"Invalid tools for moderation agent: {', '.join(sorted(invalid_tools))}. "
                        f"Valid moderation tools: {', '.join(sorted(valid_moderation_tools))}",
                        obj=None,
                    )

            # Determine action type: fieldset, analyzer, agent (with config),
            # agent (inline), or lightweight agent (task_instructions only)
            has_fieldset = bool(fieldset_id)
            has_analyzer = bool(analyzer_id)
            has_agent_config = bool(agent_config_id)
            has_inline_agent = bool(create_agent_inline)
            has_task_instructions = bool(task_instructions)

            # Fieldset/analyzer/agent_config/inline are mutually exclusive
            fk_count = sum(
                [has_fieldset, has_analyzer, has_agent_config, has_inline_agent]
            )
            if fk_count > 1:
                return CreateCorpusAction(
                    ok=False,
                    message=(
                        "Only one of fieldset_id, analyzer_id, "
                        "agent_config_id, or create_agent_inline can be provided"
                    ),
                    obj=None,
                )

            # Must have at least one action type
            if fk_count == 0 and not has_task_instructions:
                return CreateCorpusAction(
                    ok=False,
                    message=(
                        "Provide one of: fieldset_id, analyzer_id, agent_config_id, "
                        "create_agent_inline, or task_instructions"
                    ),
                    obj=None,
                )

            # task_instructions is required for all agent-type actions
            if (has_agent_config or has_inline_agent) and not has_task_instructions:
                return CreateCorpusAction(
                    ok=False,
                    message="task_instructions is required for agent actions",
                    obj=None,
                )

            # task_instructions must not be set on fieldset/analyzer actions
            if (has_fieldset or has_analyzer) and has_task_instructions:
                return CreateCorpusAction(
                    ok=False,
                    message="task_instructions cannot be set on fieldset or analyzer actions",
                    obj=None,
                )

            # Get fieldset, analyzer, or agent_config if provided
            fieldset = None
            analyzer = None
            agent_config = None

            if fieldset_id:
                fieldset_pk = from_global_id(fieldset_id)[1]
                fieldset = Fieldset.objects.visible_to_user(user).get(pk=fieldset_pk)

            if analyzer_id:
                analyzer_pk = from_global_id(analyzer_id)[1]
                analyzer = Analyzer.objects.visible_to_user(user).get(pk=analyzer_pk)

            if agent_config_id:
                agent_config_pk = from_global_id(agent_config_id)[1]
                agent_config = AgentConfiguration.objects.visible_to_user(user).get(
                    pk=agent_config_pk
                )
                if not agent_config.is_active:
                    return CreateCorpusAction(
                        ok=False,
                        message="The selected agent configuration is not active",
                        obj=None,
                    )

            # Create inline agent if requested (wrapped in transaction with action creation)
            if create_agent_inline:
                # Validation above guarantees both are populated when reaching here,
                # but use an explicit guard (not assert) so -O optimised builds are safe.
                if inline_agent_name is None or inline_agent_instructions is None:
                    raise ValueError(
                        "inline_agent_name and inline_agent_instructions are required "
                        "when create_agent_inline=True"
                    )
                with transaction.atomic():
                    agent_config = AgentConfiguration.objects.create(
                        name=inline_agent_name,
                        description=inline_agent_description
                        or f"Moderator agent for {corpus.title}",
                        system_instructions=inline_agent_instructions,
                        available_tools=inline_agent_tools or [],
                        permission_required_tools=[],
                        badge_config={
                            "icon": "shield",
                            "color": "#6366f1",
                            "label": "Moderator",
                        },
                        scope="CORPUS",
                        corpus=corpus,
                        creator=user,
                        is_active=True,
                        is_public=False,
                    )

                    set_permissions_for_obj_to_user(
                        user,
                        agent_config,
                        [PermissionTypes.CRUD],
                        request=info.context,
                    )

                    corpus_action = CorpusAction.objects.create(
                        name=name or "Corpus Action",
                        corpus=corpus,
                        fieldset=fieldset,
                        analyzer=analyzer,
                        agent_config=agent_config,
                        task_instructions=task_instructions or "",
                        pre_authorized_tools=pre_authorized_tools or [],
                        trigger=trigger,
                        disabled=disabled,
                        run_on_all_corpuses=run_on_all_corpuses,
                        creator=user,
                    )

                    set_permissions_for_obj_to_user(
                        user,
                        corpus_action,
                        [PermissionTypes.CRUD],
                        request=info.context,
                    )

                    return CreateCorpusAction(
                        ok=True,
                        message="Successfully created corpus action with inline agent",
                        obj=corpus_action,
                    )

            # Standard path: Create the corpus action
            corpus_action = CorpusAction.objects.create(
                name=name or "Corpus Action",
                corpus=corpus,
                fieldset=fieldset,
                analyzer=analyzer,
                agent_config=agent_config,
                task_instructions=task_instructions or "",
                pre_authorized_tools=pre_authorized_tools or [],
                trigger=trigger,
                disabled=disabled,
                run_on_all_corpuses=run_on_all_corpuses,
                creator=user,
            )

            set_permissions_for_obj_to_user(
                user,
                corpus_action,
                [PermissionTypes.CRUD],
                request=info.context,
            )

            return CreateCorpusAction(
                ok=True, message="Successfully created corpus action", obj=corpus_action
            )

        except AgentConfiguration.DoesNotExist:
            return CreateCorpusAction(
                ok=False,
                message="Agent configuration not found",
                obj=None,
            )

        except Exception as e:
            return CreateCorpusAction(
                ok=False, message=f"Failed to create corpus action: {str(e)}", obj=None
            )


class UpdateCorpusAction(graphene.Mutation):
    """
    Update an existing CorpusAction.
    Allows updating name, trigger, action type (fieldset/analyzer/agent), disabled state,
    and agent-specific settings.
    Requires the user to be the creator of the action.
    """

    class Arguments:
        id = graphene.ID(required=True, description="ID of the corpus action to update")
        name = graphene.String(required=False, description="Updated name of the action")
        trigger = graphene.String(
            required=False,
            description="Updated trigger (add_document, edit_document, new_thread, new_message)",
        )
        fieldset_id = graphene.ID(
            required=False,
            description="ID of the fieldset to run (clears other action types)",
        )
        analyzer_id = graphene.ID(
            required=False,
            description="ID of the analyzer to run (clears other action types)",
        )
        agent_config_id = graphene.ID(
            required=False,
            description="ID of the agent configuration (clears other action types)",
        )
        task_instructions = graphene.String(
            required=False,
            description="What the agent should do",
        )
        pre_authorized_tools = graphene.List(
            graphene.String,
            required=False,
            description="Tools pre-authorized to run without approval",
        )
        disabled = graphene.Boolean(
            required=False, description="Whether the action is disabled"
        )
        run_on_all_corpuses = graphene.Boolean(
            required=False, description="Whether to run this action on all corpuses"
        )

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(CorpusActionType)

    @login_required
    def mutate(
        root,
        info,
        id: str,
        name: str | None = None,
        trigger: str | None = None,
        fieldset_id: str | None = None,
        analyzer_id: str | None = None,
        agent_config_id: str | None = None,
        task_instructions: str | None = None,
        pre_authorized_tools: list | None = None,
        disabled: bool | None = None,
        run_on_all_corpuses: bool | None = None,
    ) -> "UpdateCorpusAction":
        from opencontractserver.agents.models import AgentConfiguration

        try:
            user = info.context.user
            action_pk = from_global_id(id)[1]

            # Get the corpus action with visibility filter
            corpus_action = CorpusAction.objects.visible_to_user(user).get(pk=action_pk)

            # Check if user is the creator
            if corpus_action.creator.id != user.id:
                return UpdateCorpusAction(
                    ok=False,
                    message="You can only update your own corpus actions",
                    obj=None,
                )

            # Update simple fields if provided
            if name is not None:
                corpus_action.name = name

            if trigger is not None:
                corpus_action.trigger = trigger

            if disabled is not None:
                corpus_action.disabled = disabled

            if run_on_all_corpuses is not None:
                corpus_action.run_on_all_corpuses = run_on_all_corpuses

            # Handle action type changes (fieldset, analyzer, or agent)
            # If any of these are provided, clear the others and set the new one
            if fieldset_id is not None:
                fieldset_pk = from_global_id(fieldset_id)[1]
                fieldset = Fieldset.objects.visible_to_user(user).get(pk=fieldset_pk)
                corpus_action.fieldset = fieldset
                corpus_action.analyzer = None
                corpus_action.agent_config = None
                corpus_action.task_instructions = ""
                corpus_action.pre_authorized_tools = []

            elif analyzer_id is not None:
                analyzer_pk = from_global_id(analyzer_id)[1]
                analyzer = Analyzer.objects.visible_to_user(user).get(pk=analyzer_pk)
                corpus_action.analyzer = analyzer
                corpus_action.fieldset = None
                corpus_action.agent_config = None
                corpus_action.task_instructions = ""
                corpus_action.pre_authorized_tools = []

            elif agent_config_id is not None:
                agent_config_pk = from_global_id(agent_config_id)[1]
                agent_config = AgentConfiguration.objects.visible_to_user(user).get(
                    pk=agent_config_pk
                )
                if not agent_config.is_active:
                    return UpdateCorpusAction(
                        ok=False,
                        message="The selected agent configuration is not active",
                        obj=None,
                    )
                corpus_action.agent_config = agent_config
                corpus_action.fieldset = None
                corpus_action.analyzer = None

            # Reject task_instructions on non-agent actions early,
            # before setting fields that model validation would later reject.
            will_be_agent = corpus_action.is_agent_action or agent_config_id is not None
            if not will_be_agent and task_instructions:
                return UpdateCorpusAction(
                    ok=False,
                    message="task_instructions can only be set on agent-based actions",
                    obj=None,
                )

            # Update agent-specific fields if this is (or is becoming) an agent action
            if will_be_agent or task_instructions is not None:
                if task_instructions is not None:
                    corpus_action.task_instructions = task_instructions
                if pre_authorized_tools is not None:
                    corpus_action.pre_authorized_tools = pre_authorized_tools

            corpus_action.save()

            return UpdateCorpusAction(
                ok=True, message="Successfully updated corpus action", obj=corpus_action
            )

        except CorpusAction.DoesNotExist:
            return UpdateCorpusAction(
                ok=False,
                message="Corpus action not found",
                obj=None,
            )

        except AgentConfiguration.DoesNotExist:
            return UpdateCorpusAction(
                ok=False,
                message="Agent configuration not found",
                obj=None,
            )

        except Fieldset.DoesNotExist:
            return UpdateCorpusAction(
                ok=False,
                message="Fieldset not found",
                obj=None,
            )

        except Analyzer.DoesNotExist:
            return UpdateCorpusAction(
                ok=False,
                message="Analyzer not found",
                obj=None,
            )

        except Exception as e:
            return UpdateCorpusAction(
                ok=False, message=f"Failed to update corpus action: {str(e)}", obj=None
            )


class DeleteCorpusAction(DRFDeletion):
    """
    Mutation to delete a CorpusAction.
    Requires the user to be the creator of the action or have appropriate permissions.
    """

    class IOSettings:
        model = CorpusAction
        lookup_field = "id"

    class Arguments:
        id = graphene.String(
            required=True, description="ID of the corpus action to delete"
        )


class RunCorpusAction(graphene.Mutation):
    """
    Manually trigger a specific agent-based corpus action on a document.

    Superuser-only. Creates a CorpusActionExecution record and dispatches
    the run_agent_corpus_action Celery task.
    """

    class Arguments:
        corpus_action_id = graphene.ID(
            required=True,
            description="ID of the CorpusAction to run",
        )
        document_id = graphene.ID(
            required=True,
            description="ID of the Document to run the action against",
        )

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(CorpusActionExecutionType)

    @user_passes_test(lambda user: user.is_superuser)
    @graphql_ratelimit(rate=RateLimits.ADMIN_OPERATION)
    def mutate(
        root, info, corpus_action_id: str, document_id: str
    ) -> "RunCorpusAction":
        from graphql_relay import from_global_id

        from opencontractserver.corpuses.models import CorpusActionExecution
        from opencontractserver.documents.models import DocumentPath
        from opencontractserver.tasks.agent_tasks import run_agent_corpus_action

        user = info.context.user

        # Decode Relay global IDs to database PKs
        _, action_pk = from_global_id(corpus_action_id)
        _, doc_pk = from_global_id(document_id)

        # Superuser-only: the @user_passes_test decorator above guarantees only
        # superusers reach this point, so raw .objects.get() is intentional and
        # bypasses visible_to_user() filtering by design. Defence-in-depth check
        # uses an explicit raise (not ``assert``) so it survives ``python -O``
        # which strips assertions.
        if not user.is_superuser:
            raise PermissionDenied("RunCorpusAction requires superuser privileges.")

        # Validate action exists
        try:
            action = CorpusAction.objects.get(pk=action_pk)
        except CorpusAction.DoesNotExist:
            return RunCorpusAction(ok=False, message="Corpus action not found.")

        # Must be an agent action
        if not action.is_agent_action:
            return RunCorpusAction(
                ok=False,
                message="Only agent-based actions can be manually triggered.",
            )

        # Validate document exists and belongs to the action's corpus
        try:
            document = Document.objects.get(pk=doc_pk)
        except Document.DoesNotExist:
            return RunCorpusAction(ok=False, message="Document not found.")

        if not DocumentPath.objects.filter(
            document=document, corpus=action.corpus
        ).exists():
            return RunCorpusAction(
                ok=False,
                message="Document is not in this action's corpus.",
            )

        # Create execution record
        execution = CorpusActionExecution.objects.create(
            corpus_action=action,
            document=document,
            corpus=action.corpus,
            action_type=CorpusActionExecution.ActionType.AGENT,
            status=CorpusActionExecution.Status.QUEUED,
            trigger=action.trigger,
            queued_at=timezone.now(),
            creator=user,
        )

        # Dispatch Celery task after transaction commits (ATOMIC_REQUESTS
        # wraps the entire request — dispatching inside the transaction
        # causes Celery to look up the execution before it's visible).
        transaction.on_commit(
            lambda: run_agent_corpus_action.delay(
                corpus_action_id=action.id,
                document_id=document.id,
                user_id=user.id,
                execution_id=execution.id,
                force=True,
            )
        )

        # Refresh so Django TextChoices enums are properly stored as
        # plain strings, which Graphene's enum serialization expects.
        execution.refresh_from_db()

        return RunCorpusAction(
            ok=True,
            message="Action queued successfully.",
            obj=execution,
        )


class AddTemplateToCorpus(graphene.Mutation):
    """
    Add an action template to a corpus by cloning it into a CorpusAction.

    This is the core of the Action Library feature: users browse available
    templates and opt-in per corpus. Once cloned, the action is a regular
    CorpusAction that can be edited/toggled/deleted like any other.

    Prevents duplicates: the same template cannot be added twice to the same
    corpus (checked via source_template FK).

    Requires the user to be the corpus creator or have CRUD permission.
    """

    class Arguments:
        template_id = graphene.ID(
            required=True, description="ID of the CorpusActionTemplate to clone"
        )
        corpus_id = graphene.ID(
            required=True, description="ID of the corpus to add the template to"
        )

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(CorpusActionType)

    @login_required
    def mutate(root, info, template_id: str, corpus_id: str) -> "AddTemplateToCorpus":
        try:
            user = info.context.user
            no_permission_msg = (
                "You don't have permission to add templates to this corpus"
            )
            # Pre-guard both ``from_global_id`` decodes: a malformed base64
            # corpus or template id raises before the helper is reached —
            # return the same unified message rather than a leaked decode error.
            try:
                corpus_pk = from_global_id(corpus_id)[1]
                template_pk = from_global_id(template_id)[1]
            except Exception:
                return AddTemplateToCorpus(
                    ok=False, message=no_permission_msg, obj=None
                )

            # Get corpus with visibility filter to prevent IDOR. ``None``
            # collapses missing / hidden / no-CRUD into the same response.
            corpus = get_for_user_or_none(Corpus, corpus_pk, user)
            if corpus is None or not corpus.user_can(
                user, PermissionTypes.CRUD, request=info.context
            ):
                return AddTemplateToCorpus(
                    ok=False,
                    message=no_permission_msg,
                    obj=None,
                )

            # Get the template (templates are global, no user filter needed)
            template = CorpusActionTemplate.objects.get(pk=template_pk, is_active=True)

            # Fast-path duplicate check (avoids wasted clone + rollback).
            # The unique constraint + IntegrityError catch below handles the
            # race-condition window between this check and the insert.
            if CorpusAction.objects.filter(
                corpus=corpus, source_template=template
            ).exists():
                return AddTemplateToCorpus(
                    ok=False,
                    message="This template has already been added to the corpus",
                    obj=None,
                )

            # Clone the template into a CorpusAction.
            # Wrap in a savepoint so that a race-condition IntegrityError
            # does not abort the outer transaction (PostgreSQL requirement).
            try:
                with transaction.atomic():
                    action = template.clone_to_corpus(corpus, creator=user)
            except IntegrityError:
                return AddTemplateToCorpus(
                    ok=False,
                    message="This template has already been added to the corpus",
                    obj=None,
                )

            set_permissions_for_obj_to_user(
                user,
                action,
                [PermissionTypes.CRUD],
                request=info.context,
            )

            return AddTemplateToCorpus(
                ok=True,
                message="Template added to corpus successfully",
                obj=action,
            )

        except CorpusActionTemplate.DoesNotExist:
            return AddTemplateToCorpus(
                ok=False, message="Template not found or inactive", obj=None
            )

        except DatabaseError:
            logger.exception("Database error adding template to corpus")
            return AddTemplateToCorpus(
                ok=False,
                message="Failed to add template. Please try again.",
                obj=None,
            )


class ToggleCorpusMemory(graphene.Mutation):
    """
    Toggle the agent memory system on/off for a corpus.

    When enabled, agents accumulate reusable insights from conversations
    into a memory document. The memory document is a first-class Document
    in the corpus, visible and editable by users.

    IMPORTANT: When memory is enabled, conversation patterns (NOT specific
    content) may be distilled into the memory document. Users should be
    aware of this when discussing sensitive topics.

    Requires CRUD permission on the corpus.
    """

    class Arguments:
        corpus_id = graphene.ID(
            required=True,
            description="The global ID of the corpus to toggle memory for",
        )
        enabled = graphene.Boolean(
            required=True,
            description="Whether to enable (true) or disable (false) memory",
        )

    ok = graphene.Boolean()
    message = graphene.String()
    corpus = graphene.Field(CorpusType)

    @login_required
    @graphql_ratelimit(rate=RateLimits.WRITE_LIGHT)
    def mutate(self, info, corpus_id, enabled) -> "ToggleCorpusMemory":
        user = info.context.user
        # IDOR protection: same response whether the pk is malformed,
        # corpus doesn't exist, is hidden from the caller, or the caller has
        # READ but no CRUD on it.
        not_found_msg = "Corpus not found or you don't have permission to modify it."
        # ``from_global_id`` can raise a bare ``Exception`` (via
        # ``binascii.Error``) on malformed base64 input — narrower
        # ``(ValueError, IndexError)`` would let those slip through as
        # raw GraphQL ``errors``.  Mirrors the broader catch used at
        # the other migrated ``from_global_id`` sites in this file.
        try:
            corpus_pk = from_global_id(corpus_id)[1]
        except Exception:
            return ToggleCorpusMemory(ok=False, message=not_found_msg, corpus=None)

        corpus = get_for_user_or_none(Corpus, corpus_pk, user)
        if corpus is None or not corpus.user_can(
            user, PermissionTypes.CRUD, request=info.context
        ):
            return ToggleCorpusMemory(ok=False, message=not_found_msg, corpus=None)

        corpus.memory_enabled = enabled
        corpus.save(update_fields=["memory_enabled", "modified"])

        status = "enabled" if enabled else "disabled"
        return ToggleCorpusMemory(
            ok=True,
            message=f"Agent memory {status} for corpus '{corpus.title}'",
            corpus=corpus,
        )
