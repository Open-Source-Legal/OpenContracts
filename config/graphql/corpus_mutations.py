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
from graphql import GraphQLError
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
from opencontractserver.documents.models import Document
from opencontractserver.extracts.models import Fieldset
from opencontractserver.tasks import fork_corpus
from opencontractserver.tasks.permissioning_tasks import make_corpus_public_task
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.corpus_collector import collect_corpus_objects
from opencontractserver.utils.permissioning import (
    set_permissions_for_obj_to_user,
    user_has_permission_for_obj,
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

        try:
            corpus_pk = from_global_id(corpus_id)[1]
        except Exception:
            return SetCorpusVisibility(ok=False, message="Invalid corpus ID format")

        try:
            corpus = Corpus.objects.get(pk=corpus_pk)
        except Corpus.DoesNotExist:
            # IDOR protection: same message whether corpus doesn't exist or user can't access
            return SetCorpusVisibility(
                ok=False, message="Corpus not found or you don't have permission"
            )

        # Permission check: owner OR has PERMISSION OR superuser
        # This is the security gate - prevents unauthorized visibility changes
        can_change_visibility = (
            user.is_superuser
            or corpus.creator_id == user.id
            or user_has_permission_for_obj(
                user, corpus, PermissionTypes.PERMISSION, include_group_permissions=True
            )
        )

        if not can_change_visibility:
            # IDOR protection: same message as "not found"
            return SetCorpusVisibility(
                ok=False, message="Corpus not found or you don't have permission"
            )

        # Check if visibility is actually changing
        if corpus.is_public == is_public:
            status = "public" if is_public else "private"
            return SetCorpusVisibility(ok=True, message=f"Corpus is already {status}")

        if is_public:
            # Use existing async task to cascade public visibility to all child objects
            # This sets is_public=True on documents, annotations, analyses, etc.
            make_corpus_public_task.si(corpus_id=corpus_pk).apply_async()
            return SetCorpusVisibility(
                ok=True,
                message="Making corpus public. This may take a moment for large corpuses.",
            )
        else:
            # Make private - only update the corpus flag
            # Note: Child objects (docs, annotations) remain public if they were made public
            # This is intentional to avoid breaking existing public links
            corpus.is_public = False
            corpus.save(update_fields=["is_public"])
            return SetCorpusVisibility(ok=True, message="Corpus is now private")


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
            from graphql_relay import from_global_id

            from opencontractserver.types.enums import PermissionTypes

            obj_pk = from_global_id(result.obj_id)[1]
            corpus = cls.IOSettings.model.objects.get(pk=obj_pk)
            # Grant creator full permissions including PERMISSION to manage access
            set_permissions_for_obj_to_user(
                info.context.user,
                corpus,
                [
                    PermissionTypes.CRUD,
                    PermissionTypes.PUBLISH,
                    PermissionTypes.PERMISSION,
                ],
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
        # Use the ReEmbedCorpus mutation instead for controlled embedder migration.
        if "preferred_embedder" in kwargs:
            corpus_global_id = kwargs.get("id")
            if corpus_global_id:
                corpus_pk = from_global_id(corpus_global_id)[1]
                try:
                    corpus = Corpus.objects.get(pk=corpus_pk)
                    if corpus.has_documents():
                        new_embedder = kwargs["preferred_embedder"]
                        if new_embedder != corpus.preferred_embedder:
                            return cls(
                                ok=False,
                                message=(
                                    "Cannot change preferred_embedder after documents "
                                    "have been added to this corpus. Changing the "
                                    "embedder would create inconsistent embeddings. "
                                    "Use the reEmbedCorpus mutation to migrate to a "
                                    "different embedder."
                                ),
                            )
                except Corpus.DoesNotExist:
                    pass  # Let the parent class handle not-found

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

            # Filter through visible_to_user so unauthorized IDs collapse to the
            # same branch as truly-missing IDs
            try:
                corpus = Corpus.objects.visible_to_user(user).get(pk=corpus_pk)
            except Corpus.DoesNotExist:
                return UpdateCorpusDescription(
                    ok=False, message=not_found_msg, obj=None, version=None
                )

            if corpus.creator != user:
                return UpdateCorpusDescription(
                    ok=False,
                    message=not_found_msg,
                    obj=None,
                    version=None,
                )

            # Use the update_description method to create a new version
            revision = corpus.update_description(new_content=new_content, author=user)

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


class DeleteCorpusMutation(DRFDeletion):
    class IOSettings:
        model = Corpus
        lookup_field = "id"

    class Arguments:
        id = graphene.String(required=True)

    @classmethod
    @login_required
    @graphql_ratelimit(rate=RateLimits.WRITE_LIGHT)
    def mutate(cls, root, info, *args, **kwargs) -> "DeleteCorpusMutation":
        id = from_global_id(kwargs[cls.IOSettings.lookup_field])[1]
        obj = cls.IOSettings.model.objects.get(pk=id)

        if obj.is_personal:
            raise GraphQLError(
                "Cannot delete your personal 'My Documents' corpus. "
                "This corpus is automatically managed and stores your uploaded documents."
            )

        return super().mutate(root, info, *args, **kwargs)


class AddDocumentsToCorpus(graphene.Mutation):
    """Add existing documents to a corpus.

    Delegates to DocumentFolderService.add_documents_to_corpus() for:
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
        from opencontractserver.corpuses.folder_service import DocumentFolderService

        # Unified message prevents enumeration of corpora the caller cannot see/edit
        not_found_msg = (
            "Corpus not found or you do not have permission to add documents to it"
        )
        try:
            user = info.context.user
            doc_pks = [int(from_global_id(doc_id)[1]) for doc_id in document_ids]
            corpus = Corpus.objects.visible_to_user(user).get(
                pk=from_global_id(corpus_id)[1]
            )

            # Delegate to service - handles permission checks, validation, dual-system update
            added_count, added_ids, error = (
                DocumentFolderService.add_documents_to_corpus(
                    user=user,
                    document_ids=doc_pks,
                    corpus=corpus,
                    folder=None,  # No folder specified - add to root
                )
            )

            if error:
                return AddDocumentsToCorpus(message=error, ok=False)

            return AddDocumentsToCorpus(
                message=f"Successfully added {added_count} document(s)",
                ok=True,
            )

        except Corpus.DoesNotExist:
            return AddDocumentsToCorpus(message=not_found_msg, ok=False)
        except Exception as e:
            return AddDocumentsToCorpus(message=f"Error on upload: {e}", ok=False)


class RemoveDocumentsFromCorpus(graphene.Mutation):
    """Remove documents from a corpus (soft-delete).

    Delegates to DocumentFolderService.remove_documents_from_corpus() for:
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
        from opencontractserver.corpuses.folder_service import DocumentFolderService

        # Unified message prevents enumeration of corpora the caller cannot see/edit
        not_found_msg = (
            "Corpus not found or you do not have permission to remove documents from it"
        )
        try:
            user = info.context.user
            doc_pks = [
                int(from_global_id(doc_id)[1]) for doc_id in document_ids_to_remove
            ]
            corpus = Corpus.objects.visible_to_user(user).get(
                pk=from_global_id(corpus_id)[1]
            )

            # Delegate to service - handles permission checks, soft-delete, audit trail
            removed_count, error = DocumentFolderService.remove_documents_from_corpus(
                user=user,
                document_ids=doc_pks,
                corpus=corpus,
            )

            if error:
                return RemoveDocumentsFromCorpus(message=error, ok=False)

            return RemoveDocumentsFromCorpus(
                message=f"Successfully removed {removed_count} document(s)",
                ok=True,
            )

        except Corpus.DoesNotExist:
            return RemoveDocumentsFromCorpus(message=not_found_msg, ok=False)
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
            corpus_pk = from_global_id(corpus_id)[1]

            # Get corpus obj with visibility check
            try:
                corpus = Corpus.objects.visible_to_user(info.context.user).get(
                    pk=corpus_pk
                )
            except Corpus.DoesNotExist:
                return StartCorpusFork(
                    ok=False, message="Corpus not found", new_corpus=None
                )

            # Verify READ permission
            if not user_has_permission_for_obj(
                info.context.user,
                corpus,
                PermissionTypes.READ,
                include_group_permissions=True,
            ):
                return StartCorpusFork(
                    ok=False, message="Corpus not found", new_corpus=None
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
                info.context.user, corpus, [PermissionTypes.CRUD]
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
            return ReEmbedCorpus(ok=False, message="Invalid corpus ID")

        try:
            corpus = Corpus.objects.get(pk=corpus_pk)
        except Corpus.DoesNotExist:
            return ReEmbedCorpus(ok=False, message="Corpus not found")

        # Only creator can re-embed
        if corpus.creator != user:
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
            corpus_pk = from_global_id(corpus_id)[1]

            # Get corpus with visibility filter to prevent IDOR
            corpus = Corpus.objects.visible_to_user(user).get(pk=corpus_pk)

            # Check if user has update permission on the corpus
            if not (
                user.is_superuser
                or corpus.creator_id == user.id
                or user_has_permission_for_obj(
                    user, corpus, PermissionTypes.CRUD, include_group_permissions=True
                )
            ):
                return CreateCorpusAction(
                    ok=False,
                    message="You don't have permission to create actions on this corpus",
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
                        user, agent_config, [PermissionTypes.CRUD]
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
                        user, corpus_action, [PermissionTypes.CRUD]
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

            set_permissions_for_obj_to_user(user, corpus_action, [PermissionTypes.CRUD])

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
            corpus_pk = from_global_id(corpus_id)[1]
            template_pk = from_global_id(template_id)[1]

            # Get corpus with visibility filter to prevent IDOR
            corpus = Corpus.objects.visible_to_user(user).get(pk=corpus_pk)

            # Check if user has update permission on the corpus
            if not (
                user.is_superuser
                or corpus.creator_id == user.id
                or user_has_permission_for_obj(
                    user, corpus, PermissionTypes.CRUD, include_group_permissions=True
                )
            ):
                return AddTemplateToCorpus(
                    ok=False,
                    message="You don't have permission to add templates to this corpus",
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

            set_permissions_for_obj_to_user(user, action, [PermissionTypes.CRUD])

            return AddTemplateToCorpus(
                ok=True,
                message="Template added to corpus successfully",
                obj=action,
            )

        except Corpus.DoesNotExist:
            return AddTemplateToCorpus(ok=False, message="Corpus not found", obj=None)

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
        try:
            corpus_pk = from_global_id(corpus_id)[1]
            corpus = Corpus.objects.get(pk=corpus_pk)
        except (Corpus.DoesNotExist, ValueError, IndexError):
            return ToggleCorpusMemory(ok=False, message="Corpus not found", corpus=None)

        if not user_has_permission_for_obj(user, corpus, PermissionTypes.CRUD):
            return ToggleCorpusMemory(
                ok=False,
                message="You don't have permission to modify this corpus",
                corpus=None,
            )

        corpus.memory_enabled = enabled
        corpus.save(update_fields=["memory_enabled", "modified"])

        status = "enabled" if enabled else "disabled"
        return ToggleCorpusMemory(
            ok=True,
            message=f"Agent memory {status} for corpus '{corpus.title}'",
            corpus=corpus,
        )
