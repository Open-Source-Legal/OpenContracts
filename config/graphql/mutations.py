import base64
import json
import logging
import uuid

import graphene
import graphql_jwt
from celery import chain, chord, group
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Max, Q
from django.utils import timezone
from filetype import filetype
from graphene.types.generic import GenericScalar
from graphql import GraphQLError
from graphql_jwt.decorators import login_required, user_passes_test
from graphql_relay import from_global_id, to_global_id

# Import agent mutations
from config.graphql.agent_mutations import (
    CreateAgentConfigurationMutation,
    DeleteAgentConfigurationMutation,
    UpdateAgentConfigurationMutation,
)
from config.graphql.annotation_serializers import AnnotationLabelSerializer

# Import badge mutations
from config.graphql.badge_mutations import (
    AwardBadgeMutation,
    CreateBadgeMutation,
    DeleteBadgeMutation,
    RevokeBadgeMutation,
    UpdateBadgeMutation,
)
from config.graphql.base import DRFDeletion, DRFMutation

# Import conversation mutations
from config.graphql.conversation_mutations import (
    CreateThreadMessageMutation,
    CreateThreadMutation,
    DeleteConversationMutation,
    DeleteMessageMutation,
    ReplyToMessageMutation,
    UpdateMessageMutation,
)

# Import corpus folder mutations
from config.graphql.corpus_folder_mutations import (
    CreateCorpusFolderMutation,
    DeleteCorpusFolderMutation,
    MoveCorpusFolderMutation,
    MoveDocumentsToFolderMutation,
    MoveDocumentToFolderMutation,
    UpdateCorpusFolderMutation,
)
from config.graphql.graphene_types import (
    AnalysisType,
    AnnotationLabelType,
    AnnotationType,
    ColumnType,
    CorpusActionType,
    CorpusType,
    DatacellType,
    DocumentRelationshipType,
    DocumentType,
    ExtractType,
    FieldsetType,
    LabelSetType,
    NoteType,
    RelationInputType,
    RelationshipType,
    UserExportType,
    UserFeedbackType,
    UserType,
)

# Import moderation mutations
from config.graphql.moderation_mutations import (
    AddModeratorMutation,
    DeleteThreadMutation,
    LockThreadMutation,
    PinThreadMutation,
    RemoveModeratorMutation,
    RestoreThreadMutation,
    RollbackModerationActionMutation,
    UnlockThreadMutation,
    UnpinThreadMutation,
    UpdateModeratorPermissionsMutation,
)
from config.graphql.notification_mutations import (
    DeleteNotificationMutation,
    MarkAllNotificationsReadMutation,
    MarkNotificationReadMutation,
    MarkNotificationUnreadMutation,
)
from config.graphql.ratelimits import (
    RateLimits,
    get_user_tier_rate,
    graphql_ratelimit,
    graphql_ratelimit_dynamic,
)
from config.graphql.serializers import (
    AnnotationSerializer,
    CorpusSerializer,
    DocumentSerializer,
    LabelsetSerializer,
)

# Import smart label mutations
from config.graphql.smart_label_mutations import (
    SmartLabelListMutation,
    SmartLabelSearchOrCreateMutation,
)

# Import voting mutations
from config.graphql.voting_mutations import (
    RemoveConversationVoteMutation,
    RemoveVoteMutation,
    VoteConversationMutation,
    VoteMessageMutation,
)
from config.telemetry import record_event
from opencontractserver.analyzer.models import Analysis, Analyzer
from opencontractserver.annotations.models import (
    Annotation,
    AnnotationLabel,
    LabelSet,
    Note,
    Relationship,
)
from opencontractserver.constants.zip_import import ZIP_MAX_TOTAL_SIZE_BYTES
from opencontractserver.corpuses.models import (
    Corpus,
    CorpusAction,
    CorpusFolder,
    TemporaryFileHandle,
)
from opencontractserver.documents.models import (
    Document,
    DocumentPath,
    DocumentRelationship,
)
from opencontractserver.documents.query_optimizer import (
    DocumentRelationshipQueryOptimizer,
)
from opencontractserver.extracts.models import Column, Datacell, Extract, Fieldset
from opencontractserver.feedback.models import UserFeedback
from opencontractserver.tasks import (
    build_label_lookups_task,
    burn_doc_annotations,
    delete_analysis_and_annotations_task,
    fork_corpus,
    fork_corpus_v2,
    import_corpus,
    import_document_to_corpus,
    package_annotated_docs,
    process_documents_zip,
)
from opencontractserver.tasks.corpus_tasks import process_analyzer
from opencontractserver.tasks.doc_tasks import convert_doc_to_funsd
from opencontractserver.tasks.export_tasks import (
    on_demand_post_processors,
    package_funsd_exports,
)
from opencontractserver.tasks.extract_orchestrator_tasks import run_extract
from opencontractserver.tasks.permissioning_tasks import (
    make_analysis_public_task,
    make_corpus_public_task,
)
from opencontractserver.types.dicts import OpenContractsAnnotatedDocumentImportType
from opencontractserver.types.enums import (
    AnnotationFilterMode,
    ExportType,
    LabelType,
    PermissionTypes,
)
from opencontractserver.users.models import UserExport
from opencontractserver.utils.etl import is_dict_instance_of_typed_dict
from opencontractserver.utils.files import is_plaintext_content
from opencontractserver.utils.permissioning import (
    set_permissions_for_obj_to_user,
    user_has_permission_for_obj,
)

logger = logging.getLogger(__name__)

# Import validate_color from validation_utils to avoid circular imports
from config.graphql.validation_utils import validate_color  # noqa: E402


class MakeAnalysisPublic(graphene.Mutation):
    class Arguments:
        analysis_id = graphene.String(
            required=True, description="Analysis id to make public (superuser only)"
        )

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(AnalysisType)

    @user_passes_test(lambda user: user.is_superuser)
    @graphql_ratelimit(rate=RateLimits.ADMIN_OPERATION)
    def mutate(root, info, analysis_id):

        try:
            analysis_pk = from_global_id(analysis_id)[1]
            make_analysis_public_task.si(analysis_id=analysis_pk).apply_async()

            message = (
                "Starting an OpenContracts worker to make your analysis public! Underlying corpus must be made "
                "public too!"
            )
            ok = True

        except Exception as e:
            ok = False
            message = (
                f"ERROR - Could not make analysis public due to unexpected error: {e}"
            )

        return MakeAnalysisPublic(ok=ok, message=message)


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
    def mutate(root, info, corpus_id, is_public):
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


class UpdateLabelset(DRFMutation):
    class IOSettings:
        lookup_field = "id"
        serializer = LabelsetSerializer
        model = LabelSet
        graphene_model = LabelSetType

    class Arguments:
        id = graphene.String(required=True)
        icon = graphene.String(
            required=False,
            description="Base64-encoded file string for the Labelset icon (optional).",
        )
        title = graphene.String(required=True, description="Title of the Labelset.")
        description = graphene.String(
            required=False, description="Description of the Labelset."
        )


class ApproveDatacell(graphene.Mutation):
    # TODO - I think permissioning cells makes sense but adds a lot of overhead and probably requires
    #  some changes like granting permission based on parent corpus / extract.

    class Arguments:
        datacell_id = graphene.String(required=True)

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(DatacellType)

    @login_required
    def mutate(root, info, datacell_id):

        ok = True
        obj = None

        try:
            pk = from_global_id(datacell_id)[1]
            obj = Datacell.objects.get(pk=pk, creator=info.context.user)
            obj.approved_by = info.context.user
            obj.rejected_by = None
            obj.save()
            message = "SUCCESS!"

        except Exception as e:
            ok = False
            message = f"Failed to approve datacell due to error: {e}"

        return ApproveDatacell(ok=ok, obj=obj, message=message)


class RejectDatacell(graphene.Mutation):
    # TODO - I think permissioning cells makes sense but adds a lot of overhead and probably requires
    #  some changes like granting permission based on parent corpus / extract.

    class Arguments:
        datacell_id = graphene.String(required=True)

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(DatacellType)

    @login_required
    def mutate(root, info, datacell_id):

        ok = True
        obj = None

        try:
            pk = from_global_id(datacell_id)[1]
            obj = Datacell.objects.get(pk=pk, creator=info.context.user)
            obj.rejected_by = info.context.user
            obj.approved_by = None
            obj.save()
            message = "SUCCESS!"

        except Exception as e:
            ok = False
            message = f"Failed to approve datacell due to error: {e}"

        return RejectDatacell(ok=ok, obj=obj, message=message)


class EditDatacell(graphene.Mutation):
    # TODO - I think permissioning cells makes sense but adds a lot of overhead and probably requires
    #  some changes like granting permission based on parent corpus / extract.

    class Arguments:
        datacell_id = graphene.String(required=True)
        edited_data = GenericScalar(required=True)

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(DatacellType)

    @login_required
    def mutate(root, info, datacell_id, edited_data):

        ok = True
        obj = None

        try:
            pk = from_global_id(datacell_id)[1]
            obj = Datacell.objects.get(pk=pk, creator=info.context.user)
            obj.corrected_data = edited_data
            obj.save()
            message = "SUCCESS!"

        except Exception as e:
            ok = False
            message = f"Failed to approve datacell due to error: {e}"

        return EditDatacell(ok=ok, obj=obj, message=message)


class CreateMetadataColumn(graphene.Mutation):
    """Create a metadata column for a corpus."""

    class Arguments:
        corpus_id = graphene.ID(required=True, description="ID of the corpus")
        name = graphene.String(required=True, description="Name of the metadata field")
        data_type = graphene.String(required=True, description="Data type of the field")
        validation_config = GenericScalar(
            required=False, description="Validation configuration"
        )
        default_value = GenericScalar(required=False, description="Default value")
        help_text = graphene.String(
            required=False, description="Help text for the field"
        )
        display_order = graphene.Int(required=False, description="Display order")

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(ColumnType)

    @login_required
    def mutate(
        root,
        info,
        corpus_id,
        name,
        data_type,
        validation_config=None,
        default_value=None,
        help_text=None,
        display_order=0,
    ):
        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.types.enums import PermissionTypes
        from opencontractserver.utils.permissioning import (
            set_permissions_for_obj_to_user,
        )

        try:
            user = info.context.user
            corpus = Corpus.objects.get(pk=from_global_id(corpus_id)[1])

            # Check permissions
            if not user_has_permission_for_obj(
                user, corpus, PermissionTypes.UPDATE, include_group_permissions=True
            ):
                return CreateMetadataColumn(
                    ok=False, message="You don't have permission to update this corpus"
                )

            # Get or create metadata fieldset for corpus
            if not hasattr(corpus, "metadata_schema") or corpus.metadata_schema is None:
                fieldset = Fieldset.objects.create(
                    name=f"{corpus.title} Metadata",
                    description=f"Metadata schema for {corpus.title}",
                    corpus=corpus,
                    creator=user,
                )
                set_permissions_for_obj_to_user(user, fieldset, [PermissionTypes.CRUD])
            else:
                fieldset = corpus.metadata_schema

            # Validate data type
            valid_types = [
                "STRING",
                "TEXT",
                "BOOLEAN",
                "INTEGER",
                "FLOAT",
                "DATE",
                "DATETIME",
                "URL",
                "EMAIL",
                "CHOICE",
                "MULTI_CHOICE",
                "JSON",
            ]
            if data_type not in valid_types:
                return CreateMetadataColumn(
                    ok=False,
                    message=f"Invalid data type. Must be one of: {', '.join(valid_types)}",
                )

            # Validate choice fields
            if data_type in ["CHOICE", "MULTI_CHOICE"]:
                if not validation_config or "choices" not in validation_config:
                    return CreateMetadataColumn(
                        ok=False,
                        message="Choice fields require 'choices' in validation_config",
                    )

            # Create column
            column = Column.objects.create(
                fieldset=fieldset,
                name=name,
                data_type=data_type,
                validation_config=validation_config or {},
                default_value=default_value,
                help_text=help_text or "",
                display_order=display_order,
                is_manual_entry=True,
                output_type=data_type.lower(),  # For compatibility
                creator=user,
            )

            set_permissions_for_obj_to_user(user, column, [PermissionTypes.CRUD])

            return CreateMetadataColumn(
                ok=True, message="Metadata field created successfully", obj=column
            )

        except Corpus.DoesNotExist:
            return CreateMetadataColumn(ok=False, message="Corpus not found")
        except Exception as e:
            return CreateMetadataColumn(
                ok=False, message=f"Error creating metadata field: {str(e)}"
            )


class UpdateMetadataColumn(graphene.Mutation):
    """Update a metadata column."""

    class Arguments:
        column_id = graphene.ID(required=True)
        name = graphene.String(required=False)
        validation_config = GenericScalar(required=False)
        default_value = GenericScalar(required=False)
        help_text = graphene.String(required=False)
        display_order = graphene.Int(required=False)

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(ColumnType)

    @login_required
    def mutate(root, info, column_id, **kwargs):
        from opencontractserver.types.enums import PermissionTypes

        try:
            user = info.context.user
            column = Column.objects.get(pk=from_global_id(column_id)[1])

            # Check permissions
            if not user_has_permission_for_obj(
                user, column, PermissionTypes.UPDATE, include_group_permissions=True
            ):
                return UpdateMetadataColumn(
                    ok=False, message="You don't have permission to update this column"
                )

            # Ensure it's a manual entry column
            if not column.is_manual_entry:
                return UpdateMetadataColumn(
                    ok=False, message="Only manual entry columns can be updated"
                )

            # Update fields
            if "name" in kwargs:
                column.name = kwargs["name"]
            if "validation_config" in kwargs:
                # Validate choice fields
                if column.data_type in ["CHOICE", "MULTI_CHOICE"]:
                    if "choices" not in kwargs["validation_config"]:
                        return UpdateMetadataColumn(
                            ok=False,
                            message="Choice fields require 'choices' in validation_config",
                        )
                column.validation_config = kwargs["validation_config"]
            if "default_value" in kwargs:
                column.default_value = kwargs["default_value"]
            if "help_text" in kwargs:
                column.help_text = kwargs["help_text"]
            if "display_order" in kwargs:
                column.display_order = kwargs["display_order"]

            column.save()

            return UpdateMetadataColumn(
                ok=True, message="Metadata field updated successfully", obj=column
            )

        except Column.DoesNotExist:
            return UpdateMetadataColumn(ok=False, message="Column not found")
        except Exception as e:
            return UpdateMetadataColumn(
                ok=False, message=f"Error updating metadata field: {str(e)}"
            )


class SetMetadataValue(graphene.Mutation):
    """Set a metadata value for a document."""

    class Arguments:
        document_id = graphene.ID(required=True)
        corpus_id = graphene.ID(required=True)
        column_id = graphene.ID(required=True)
        value = GenericScalar(required=True)

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(DatacellType)

    @login_required
    def mutate(root, info, document_id, corpus_id, column_id, value):
        from django.utils import timezone

        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.types.enums import PermissionTypes
        from opencontractserver.utils.permissioning import (
            set_permissions_for_obj_to_user,
        )

        try:
            user = info.context.user
            document = Document.objects.get(pk=from_global_id(document_id)[1])
            corpus = Corpus.objects.get(pk=from_global_id(corpus_id)[1])
            column = Column.objects.get(pk=from_global_id(column_id)[1])

            # Check permissions on document
            if not user_has_permission_for_obj(
                user, document, PermissionTypes.UPDATE, include_group_permissions=True
            ):
                return SetMetadataValue(
                    ok=False,
                    message="You don't have permission to update this document",
                )

            # Ensure column belongs to corpus metadata schema
            if not (
                column.fieldset
                and hasattr(column.fieldset, "corpus")
                and column.fieldset.corpus_id == corpus.id
            ):
                return SetMetadataValue(
                    ok=False, message="Column does not belong to corpus metadata schema"
                )

            # Ensure it's a manual entry column
            if not column.is_manual_entry:
                return SetMetadataValue(
                    ok=False, message="Only manual entry columns can be set"
                )

            # Find or create datacell
            datacell, created = Datacell.objects.update_or_create(
                document=document,
                column=column,
                defaults={
                    "data": {"value": value},
                    "data_definition": column.output_type,
                    "creator": user,
                    "completed": timezone.now(),
                },
            )

            if created:
                set_permissions_for_obj_to_user(user, datacell, [PermissionTypes.CRUD])

            return SetMetadataValue(
                ok=True, message="Metadata value set successfully", obj=datacell
            )

        except (Document.DoesNotExist, Corpus.DoesNotExist, Column.DoesNotExist):
            return SetMetadataValue(
                ok=False, message="Document, corpus, or column not found"
            )
        except Exception as e:
            return SetMetadataValue(
                ok=False, message=f"Error setting metadata value: {str(e)}"
            )


class DeleteMetadataValue(graphene.Mutation):
    """Delete a metadata value for a document."""

    class Arguments:
        document_id = graphene.ID(required=True)
        corpus_id = graphene.ID(required=True)
        column_id = graphene.ID(required=True)

    ok = graphene.Boolean()
    message = graphene.String()

    @login_required
    def mutate(root, info, document_id, corpus_id, column_id):
        from opencontractserver.types.enums import PermissionTypes

        try:
            user = info.context.user
            document = Document.objects.get(pk=from_global_id(document_id)[1])
            # corpus = Corpus.objects.get(pk=from_global_id(corpus_id)[1])
            column = Column.objects.get(pk=from_global_id(column_id)[1])

            # Find the datacell
            datacell = Datacell.objects.get(document=document, column=column)

            # Check permissions
            if not user_has_permission_for_obj(
                user, datacell, PermissionTypes.DELETE, include_group_permissions=True
            ):
                return DeleteMetadataValue(
                    ok=False,
                    message="You don't have permission to delete this metadata value",
                )

            datacell.delete()

            return DeleteMetadataValue(
                ok=True, message="Metadata value deleted successfully"
            )

        except Datacell.DoesNotExist:
            return DeleteMetadataValue(ok=False, message="Metadata value not found")
        except Exception as e:
            return DeleteMetadataValue(
                ok=False, message=f"Error deleting metadata value: {str(e)}"
            )


class CreateLabelset(graphene.Mutation):
    class Arguments:
        base64_icon_string = graphene.String(
            required=False,
            description="Base64-encoded file string for the Labelset icon (optional).",
        )
        filename = graphene.String(
            required=False, description="Filename of the document."
        )
        title = graphene.String(required=True, description="Title of the Labelset.")
        description = graphene.String(
            required=False, description="Description of the Labelset."
        )

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(LabelSetType)

    @login_required
    @graphql_ratelimit(rate=RateLimits.WRITE_MEDIUM)
    def mutate(root, info, title, description, filename=None, base64_icon_string=None):

        if base64_icon_string is None:
            base64_icon_string = settings.DEFAULT_IMAGE

        ok = False
        obj = None

        try:
            user = info.context.user
            icon = ContentFile(
                base64.b64decode(
                    base64_icon_string.split(",")[1]
                    if "," in base64_icon_string[:32]
                    else base64_icon_string
                ),
                name=filename if filename is not None else "icon.png",
            )
            obj = LabelSet(
                creator=user, title=title, description=description, icon=icon
            )
            obj.save()

            # Assign permissions for user to obj so it can be retrieved
            set_permissions_for_obj_to_user(user, obj, [PermissionTypes.CRUD])

            ok = True
            message = "Success"

        except Exception as e:
            message = f"Error creating labelset: {e}"

        return CreateLabelset(message=message, ok=ok, obj=obj)


class DeleteLabelset(DRFDeletion):
    class IOSettings:
        model = LabelSet
        lookup_field = "id"

    class Arguments:
        id = graphene.String(required=True)


class DeleteExport(DRFDeletion):
    class IOSettings:
        model = UserExport
        lookup_field = "id"

    class Arguments:
        id = graphene.String(required=True)


class AcceptCookieConsent(graphene.Mutation):
    """
    Mutation to record when an authenticated user accepts cookie consent.
    For anonymous users, this is handled via localStorage in the frontend.
    """

    class Arguments:
        pass

    ok = graphene.Boolean()
    message = graphene.String()

    @login_required
    def mutate(root, info):
        try:
            user = info.context.user
            user.cookie_consent_accepted = True
            user.cookie_consent_date = timezone.now()
            user.save(update_fields=["cookie_consent_accepted", "cookie_consent_date"])

            return AcceptCookieConsent(
                ok=True, message="Cookie consent recorded successfully"
            )
        except Exception as e:
            logger.error(f"Error recording cookie consent: {e}")
            return AcceptCookieConsent(
                ok=False, message=f"Failed to record cookie consent: {str(e)}"
            )


class DismissGettingStarted(graphene.Mutation):
    """
    Mutation to record when a user dismisses the Getting Started guide.
    This preference is stored on the user model and persists across sessions.
    """

    class Arguments:
        pass

    ok = graphene.Boolean()
    message = graphene.String()

    @login_required
    def mutate(root, info):
        try:
            user = info.context.user
            user.dismissed_getting_started = True
            user.save(update_fields=["dismissed_getting_started"])

            return DismissGettingStarted(
                ok=True, message="Getting Started guide dismissed successfully"
            )
        except Exception as e:
            logger.error(f"Error dismissing Getting Started guide: {e}")
            return DismissGettingStarted(
                ok=False, message=f"Failed to dismiss Getting Started guide: {str(e)}"
            )


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
    def mutate(root, info, corpus_id, document_ids):
        from opencontractserver.corpuses.folder_service import DocumentFolderService

        try:
            user = info.context.user
            doc_pks = [int(from_global_id(doc_id)[1]) for doc_id in document_ids]
            corpus = Corpus.objects.get(pk=from_global_id(corpus_id)[1])

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
            return AddDocumentsToCorpus(message="Corpus not found", ok=False)
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
    def mutate(root, info, corpus_id, document_ids_to_remove):
        from opencontractserver.corpuses.folder_service import DocumentFolderService

        try:
            user = info.context.user
            doc_pks = [
                int(from_global_id(doc_id)[1]) for doc_id in document_ids_to_remove
            ]
            corpus = Corpus.objects.get(pk=from_global_id(corpus_id)[1])

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
            return RemoveDocumentsFromCorpus(message="Corpus not found", ok=False)
        except Exception as e:
            return RemoveDocumentsFromCorpus(message=f"Error on removal: {e}", ok=False)


class UpdateDocument(DRFMutation):
    class IOSettings:
        lookup_field = "id"
        serializer = DocumentSerializer
        model = Document
        graphene_model = DocumentType

    class Arguments:
        id = graphene.String(required=True)
        title = graphene.String(required=False)
        description = graphene.String(required=False)
        pdf_file = graphene.String(required=False)
        custom_meta = GenericScalar(required=False)
        slug = graphene.String(required=False)


class UpdateDocumentSummary(graphene.Mutation):
    """
    Mutation to update a document's markdown summary for a specific corpus, creating a new version in the process.
    Users can create/update summaries if:
    - No summary exists yet and they have permission on the corpus (public or their corpus)
    - A summary exists and they are the original author
    """

    class Arguments:
        document_id = graphene.ID(
            required=True, description="ID of the document to update"
        )
        corpus_id = graphene.ID(
            required=True, description="ID of the corpus this summary is for"
        )
        new_content = graphene.String(
            required=True, description="New markdown content for the document summary"
        )

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(DocumentType)
    version = graphene.Int(description="The new version number after update")

    @login_required
    def mutate(root, info, document_id, corpus_id, new_content):
        try:
            from opencontractserver.corpuses.models import Corpus
            from opencontractserver.documents.models import DocumentSummaryRevision

            # Extract pks from graphene ids
            _, doc_pk = from_global_id(document_id)
            _, corpus_pk = from_global_id(corpus_id)

            document = Document.objects.get(pk=doc_pk)
            corpus = Corpus.objects.get(pk=corpus_pk)

            # Check if user has any existing summary for this document-corpus combination
            existing_summary = (
                DocumentSummaryRevision.objects.filter(
                    document_id=doc_pk, corpus_id=corpus_pk
                )
                .order_by("version")
                .first()
            )

            # Permission logic
            if existing_summary:
                # If summary exists, only the original author can update
                if existing_summary.author != info.context.user:
                    return UpdateDocumentSummary(
                        ok=False,
                        message="You can only edit summaries you created.",
                        obj=None,
                        version=None,
                    )
            else:
                # If no summary exists, check corpus permissions
                # User can create if: corpus is public OR user has update permission on corpus
                is_public_corpus = corpus.is_public
                user_has_corpus_perm = info.context.user.has_perm(
                    "update_corpus", corpus
                )
                user_is_creator = corpus.creator == info.context.user

                if not (is_public_corpus or user_has_corpus_perm or user_is_creator):
                    return UpdateDocumentSummary(
                        ok=False,
                        message="You don't have permission to create summaries for this corpus.",
                        obj=None,
                        version=None,
                    )

            # Update the summary using the new method
            revision = document.update_summary(
                new_content=new_content, author=info.context.user, corpus=corpus
            )

            # If no change, revision will be None
            if revision is None:
                latest_version = (
                    DocumentSummaryRevision.objects.filter(
                        document_id=doc_pk, corpus_id=corpus_pk
                    ).aggregate(max_version=Max("version"))["max_version"]
                    or 0
                )

                return UpdateDocumentSummary(
                    ok=True,
                    message="No changes detected in summary content.",
                    obj=document,
                    version=latest_version,
                )

            return UpdateDocumentSummary(
                ok=True,
                message=f"Summary updated successfully. New version: {revision.version}",
                obj=document,
                version=revision.version,
            )

        except Document.DoesNotExist:
            return UpdateDocumentSummary(
                ok=False,
                message="Document not found.",
                obj=None,
                version=None,
            )
        except Corpus.DoesNotExist:
            return UpdateDocumentSummary(
                ok=False,
                message="Corpus not found.",
                obj=None,
                version=None,
            )
        except Exception as e:
            return UpdateDocumentSummary(
                ok=False,
                message=f"Error updating document summary: {str(e)}",
                obj=None,
                version=None,
            )


class StartCorpusFork(graphene.Mutation):
    """
    Fork a corpus with all its content.

    This mutation creates a copy of a corpus including:
    - Documents (with file copies)
    - LabelSet and AnnotationLabels
    - Annotations (non-analysis)
    - Relationships between annotations
    - Extracts, Fieldsets, Columns, Datacells
    - Conversations (chat type only)
    - Notes and NoteRevisions
    - Folder structure

    What is NOT forked:
    - Analyses and analyzer-created annotations
    - Discussion threads (conversation_type='thread')
    - Moderation actions and audit trails
    - User reputation and moderator assignments
    - CorpusActions (automation configs)
    """

    class Arguments:
        corpus_id = graphene.String(
            required=True,
            description="Graphene id of the corpus you want to fork",
        )
        fork_extracts = graphene.Boolean(
            default_value=True,
            description="Whether to fork extracts and datacells",
        )
        fork_conversations = graphene.Boolean(
            default_value=True,
            description="Whether to fork chat conversations",
        )
        fork_notes = graphene.Boolean(
            default_value=True,
            description="Whether to fork notes",
        )

    ok = graphene.Boolean()
    message = graphene.String()
    new_corpus = graphene.Field(CorpusType)

    @login_required
    def mutate(
        root,
        info,
        corpus_id,
        fork_extracts=True,
        fork_conversations=True,
        fork_notes=True,
    ):
        ok = False
        message = ""
        new_corpus = None

        try:
            # Parse corpus ID
            corpus_pk = from_global_id(corpus_id)[1]

            # Get corpus obj with visibility check
            try:
                source_corpus = Corpus.objects.visible_to_user(info.context.user).get(
                    pk=corpus_pk
                )
            except Corpus.DoesNotExist:
                return StartCorpusFork(
                    ok=False, message="Corpus not found", new_corpus=None
                )

            # Verify READ permission (IDOR protection - same error message)
            if not user_has_permission_for_obj(
                info.context.user,
                source_corpus,
                PermissionTypes.READ,
                include_group_permissions=True,
            ):
                return StartCorpusFork(
                    ok=False, message="Corpus not found", new_corpus=None
                )

            # Create new corpus (locked until async task completes)
            # Using Django ORM copy trick - set pk to None and save
            new_corpus_obj = Corpus(
                title=f"[FORK] {source_corpus.title}",
                description=source_corpus.description,
                icon=source_corpus.icon,
                allow_comments=source_corpus.allow_comments,
                is_public=False,  # Forks start private
                creator=info.context.user,
                backend_lock=True,  # Lock until fork completes
                parent_id=corpus_pk,  # Track lineage
                # Copy agent instructions
                corpus_agent_instructions=source_corpus.corpus_agent_instructions,
                document_agent_instructions=source_corpus.document_agent_instructions,
                preferred_embedder=source_corpus.preferred_embedder,
            )
            new_corpus_obj.save()

            # Set full permissions for the user
            set_permissions_for_obj_to_user(
                info.context.user, new_corpus_obj, [PermissionTypes.CRUD]
            )

            # Queue async fork task with new modular implementation
            fork_corpus_v2.delay(
                new_corpus_id=new_corpus_obj.id,
                source_corpus_id=int(corpus_pk),
                user_id=info.context.user.id,
                fork_extracts_flag=fork_extracts,
                fork_conversations_flag=fork_conversations,
                fork_notes_flag=fork_notes,
            )

            ok = True
            new_corpus = new_corpus_obj
            message = "Fork started successfully"

        except Exception as e:
            message = f"Error trying to fork corpus with id {corpus_id}: {e}"
            logger.error(message)

        record_event(
            "corpus_forked",
            {
                "env": settings.MODE,
                "user_id": info.context.user.id,
                "source_corpus_id": corpus_pk if "corpus_pk" in dir() else None,
                "fork_extracts": fork_extracts,
                "fork_conversations": fork_conversations,
                "fork_notes": fork_notes,
            },
        )

        return StartCorpusFork(ok=ok, message=message, new_corpus=new_corpus)


class StartCorpusExport(graphene.Mutation):
    """
    Mutation entrypoint for starting a corpus export.
    Now refactored to optionally accept a list of Analysis IDs (analyses_ids)
    that should be included in the export. If analyses_ids are provided, then
    only annotations/labels from those analyses are included. Otherwise, all
    annotations/labels for the corpus are included.
    """

    class Arguments:
        corpus_id = graphene.String(
            required=True,
            description="Graphene id of the corpus you want to package for export",
        )
        export_format = graphene.Argument(graphene.Enum.from_enum(ExportType))
        post_processors = graphene.List(
            graphene.String,
            required=False,
            description="List of fully qualified Python paths to post-processor functions to run",
        )
        input_kwargs = GenericScalar(
            required=False,
            description="Additional keyword arguments to pass to post-processors",
        )
        analyses_ids = graphene.List(
            graphene.String,
            required=False,
            description="Optional list of Graphene IDs for analyses that should be included in the export",
        )
        annotation_filter_mode = graphene.Argument(
            graphene.Enum.from_enum(AnnotationFilterMode),
            required=False,
            default_value=AnnotationFilterMode.CORPUS_LABELSET_ONLY.value,
            description="How to filter annotations - from corpus label set only, plus analyses, or analyses only",
        )

    ok = graphene.Boolean()
    message = graphene.String()
    export = graphene.Field(UserExportType)

    @login_required
    @graphql_ratelimit(rate=RateLimits.EXPORT)
    def mutate(
        root,
        info,
        corpus_id: str,
        export_format: str,
        post_processors: list[str] = None,
        input_kwargs: dict = None,
        analyses_ids: list[str] = None,
        annotation_filter_mode: str = AnnotationFilterMode.CORPUS_LABELSET_ONLY.value,
    ) -> "StartCorpusExport":
        """
        Initiates async Celery export tasks. If analyses_ids are supplied,
        the export is filtered to annotations/labels from only those analyses.
        Otherwise, all annotations/labels on corpus are included.

        :param root: GraphQL's root object
        :param info: GraphQL's info, containing context
        :param corpus_id: Graphene string id for the corpus
        :param export_format: The type of export to create (OPEN_CONTRACTS, FUNSD, etc.)
        :param post_processors: Optional list of python paths for post-processing
        :param input_kwargs: Optional dictionary of extra info for post-processors
        :param analyses_ids: Optional list of GraphQL IDs for analyses to filter by
        :return: The StartCorpusExport GraphQL object
        """
        post_processors = post_processors or []
        input_kwargs = input_kwargs or {}

        # Usage checks, permission checks, etc
        if (
            info.context.user.is_usage_capped
            and not settings.USAGE_CAPPED_USER_CAN_EXPORT_CORPUS
        ):
            raise PermissionError(
                "By default, new users cannot create exports. Please contact the admin to "
                "authorize your account."
            )

        try:
            # Prepare a new UserExport row
            started = timezone.now()
            date_str = started.strftime("%m/%d/%Y, %H:%M:%S")
            corpus_pk = from_global_id(corpus_id)[1]

            # Verify corpus visibility and READ permission before creating export
            try:
                corpus = Corpus.objects.visible_to_user(info.context.user).get(
                    pk=corpus_pk
                )
            except Corpus.DoesNotExist:
                return StartCorpusExport(
                    ok=False, message="Corpus not found", export=None
                )

            if not user_has_permission_for_obj(
                info.context.user,
                corpus,
                PermissionTypes.READ,
                include_group_permissions=True,
            ):
                return StartCorpusExport(
                    ok=False, message="Corpus not found", export=None
                )

            export = UserExport.objects.create(
                creator=info.context.user,
                name=f"Export Corpus PK {corpus_pk} on {date_str}",
                started=started,
                format=export_format,
                backend_lock=True,
                post_processors=post_processors,
                input_kwargs=input_kwargs,
            )
            logger.info(f"Export created: {export}")

            set_permissions_for_obj_to_user(
                info.context.user, export, [PermissionTypes.CRUD]
            )

            # For chaining, we convert analyses_ids from GraphQL global IDs → PKs (if any).
            analysis_pk_list: list[int] = []
            if analyses_ids is not None:
                for g_id in analyses_ids:
                    try:
                        _, pk_str = from_global_id(g_id)
                        analysis_pk_list.append(int(pk_str))
                    except Exception:  # If invalid, just skip for safety
                        pass

            # Collect doc_ids in the corpus for the tasks
            doc_ids = Document.objects.filter(corpus=corpus_pk).values_list(
                "id", flat=True
            )
            logger.info(f"Doc ids: {list(doc_ids)}")

            # Build the Celery chain: label lookups → burn doc annotations → package → optional post-proc
            if export_format == ExportType.OPEN_CONTRACTS.value:
                chain(
                    build_label_lookups_task.si(
                        corpus_pk,
                        analysis_pk_list if analysis_pk_list else None,
                        annotation_filter_mode,
                    ),
                    chain(
                        chord(
                            group(
                                burn_doc_annotations.s(
                                    doc_id,
                                    corpus_pk,
                                    analysis_pk_list if analysis_pk_list else None,
                                    annotation_filter_mode,
                                )
                                for doc_id in doc_ids
                            ),
                            package_annotated_docs.s(
                                export.id,
                                corpus_pk,
                                analysis_pk_list if analysis_pk_list else None,
                                annotation_filter_mode,
                            ),
                        ),
                        on_demand_post_processors.si(
                            export.id,
                            corpus_pk,
                        ),
                    ),
                ).apply_async()

                ok = True
                message = "SUCCESS"

            elif export_format == ExportType.FUNSD:
                chain(
                    chord(
                        group(
                            convert_doc_to_funsd.s(
                                info.context.user.id,
                                doc_id,
                                corpus_pk,
                                analysis_pk_list if analysis_pk_list else None,
                            )
                            for doc_id in doc_ids
                        ),
                        package_funsd_exports.s(
                            export.id,
                            corpus_pk,
                            analysis_pk_list if analysis_pk_list else None,
                        ),
                    ),
                    on_demand_post_processors.si(export.id, corpus_pk),
                ).apply_async()

                ok = True
                message = "SUCCESS"
            else:
                ok = False
                message = "Unknown Format"

            record_event(
                "export_started",
                {
                    "env": settings.MODE,
                    "user_id": info.context.user.id,
                    "export_format": export_format,
                },
            )

        except Exception as e:
            message = f"StartCorpusExport() - Unable to create export due to error: {e}"
            logger.error(message)
            ok = False
            export = None

        return StartCorpusExport(ok=ok, message=message, export=export)


class UploadAnnotatedDocument(graphene.Mutation):
    class Arguments:
        target_corpus_id = graphene.String(required=True)
        document_import_data = graphene.String(required=True)

    ok = graphene.Boolean()
    message = graphene.String()

    @login_required
    def mutate(root, info, target_corpus_id, document_import_data):

        try:
            ok = True
            message = "SUCCESS"

            received_json = json.loads(document_import_data)
            if not is_dict_instance_of_typed_dict(
                received_json, OpenContractsAnnotatedDocumentImportType
            ):
                raise GraphQLError("document_import_data is invalid...")

            import_document_to_corpus.s(
                target_corpus_id=target_corpus_id,
                user_id=info.context.user.id,
                document_import_data=received_json,
            ).apply_async()

        except Exception as e:
            ok = False
            message = f"UploadAnnotatedDocument() - could not start load job due to error: {e}"
            logger.error(message)

        return UploadAnnotatedDocument(message=message, ok=ok)


class UploadCorpusImportZip(graphene.Mutation):
    class Arguments:
        base_64_file_string = graphene.String(
            required=True,
            description="Base-64 encoded string for zip of corpus file you want to import",
        )

    ok = graphene.Boolean()
    message = graphene.String()
    corpus = graphene.Field(CorpusType)

    @login_required
    @graphql_ratelimit(rate=RateLimits.IMPORT)
    def mutate(root, info, base_64_file_string):

        if (
            info.context.user.is_usage_capped
            and not settings.USAGE_CAPPED_USER_CAN_IMPORT_CORPUS
        ):
            raise PermissionError(
                "By default, new users import corpuses. Please contact the admin to "
                "authorize your account."
            )

        try:
            logger.info(
                "UploadCorpusImportZip.mutate() - Received corpus import base64 encoded..."
            )
            corpus_obj = Corpus.objects.create(
                title="New Import", creator=info.context.user, backend_lock=False
            )
            logger.info("UploadCorpusImportZip.mutate() - placeholder created...")

            set_permissions_for_obj_to_user(
                info.context.user, corpus_obj, [PermissionTypes.CRUD]
            )
            logger.info("UploadCorpusImportZip.mutate() - permissions assigned...")

            # Store our corpus in a temporary file handler which lets us rely on
            # django-wide selection of S3 or local storage in django container
            base64_img_bytes = base_64_file_string.encode("utf-8")
            decoded_file_data = base64.decodebytes(base64_img_bytes)

            with transaction.atomic():
                temporary_file = TemporaryFileHandle.objects.create()
                temporary_file.file = ContentFile(
                    decoded_file_data,
                    name=f"corpus_import_{uuid.uuid4()}.pdf",
                )
                temporary_file.save()
                logger.info("UploadCorpusImportZip.mutate() - temporary file created.")

            transaction.on_commit(
                lambda: chain(
                    import_corpus.s(
                        temporary_file.id, info.context.user.id, corpus_obj.id
                    )
                ).apply_async()
            )
            logger.info("UploadCorpusImportZip.mutate() - Async task launched...")

            ok = True
            message = "Started"
            logger.info("UploadCorpusImportZip() - Imported started")

        except Exception as e:
            ok = False
            message = (
                f"UploadCorpusImportZip() - could not start load job due to error: {e}"
            )
            corpus_obj = None
            logger.error(message)

        return UploadCorpusImportZip(message=message, ok=ok, corpus=corpus_obj)


class UploadDocument(graphene.Mutation):
    class Arguments:
        base64_file_string = graphene.String(
            required=True, description="Base64-encoded file string for the file."
        )
        # base64_file_string = graphene.Base64(required=True, description="Base64-encoded file string for the file.")
        filename = graphene.String(
            required=True, description="Filename of the document."
        )
        title = graphene.String(required=True, description="Title of the document.")
        description = graphene.String(
            required=True, description="Description of the document."
        )
        custom_meta = GenericScalar(required=False, description="")
        add_to_corpus_id = graphene.ID(
            required=False,
            description="If provided, successfully uploaded document will "
            "be uploaded to corpus with specified id",
        )
        add_to_extract_id = graphene.ID(
            required=False,
            description="If provided, successfully uploaded document will be added to extract with specified id",
        )
        add_to_folder_id = graphene.ID(
            required=False,
            description="If provided along with add_to_corpus_id, the document "
            "will be assigned to this folder within the corpus",
        )
        make_public = graphene.Boolean(
            required=True,
            description="If True, document is immediately public. "
            "Defaults to False.",
        )
        slug = graphene.String(required=False)

    ok = graphene.Boolean()
    message = graphene.String()
    document = graphene.Field(DocumentType)

    @login_required
    @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("WRITE_HEAVY"))
    def mutate(
        root,
        info,
        base64_file_string,
        filename,
        title,
        description,
        custom_meta,
        make_public,
        add_to_corpus_id=None,
        add_to_extract_id=None,
        add_to_folder_id=None,
        slug=None,
    ):
        if add_to_corpus_id is not None and add_to_extract_id is not None:
            return UploadDocument(
                message="Cannot simultaneously add document to both corpus and extract",
                ok=False,
                document=None,
            )

        ok = False
        document = None

        # Was going to user a user_passes_test decorator, but I wanted a custom error message
        # that could be easily reflected to user in the GUI.
        if (
            info.context.user.is_usage_capped
            and info.context.user.document_set.count()
            > settings.USAGE_CAPPED_USER_DOC_CAP_COUNT - 1
        ):
            raise PermissionError(
                f"Your usage is capped at {settings.USAGE_CAPPED_USER_DOC_CAP_COUNT} documents. "
                f"Try deleting an existing document first or contact the admin for a higher limit."
            )

        try:
            message = "Success"

            file_bytes = base64.b64decode(base64_file_string)

            # Check file type
            kind = filetype.guess(file_bytes)
            if kind is None:

                if is_plaintext_content(file_bytes):
                    kind = "text/plain"
                else:
                    return UploadDocument(
                        message="Unable to determine file type", ok=False, document=None
                    )
            else:
                kind = kind.mime

            if kind not in settings.ALLOWED_DOCUMENT_MIMETYPES:
                return UploadDocument(
                    message=f"Unallowed filetype: {kind}", ok=False, document=None
                )

            user = info.context.user

            # If uploading directly to a corpus, use import_content() for deduplication
            if add_to_corpus_id is not None and kind in [
                "application/pdf",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ]:
                try:
                    corpus = Corpus.objects.get(id=from_global_id(add_to_corpus_id)[1])

                    # Resolve folder if provided
                    folder = None
                    if add_to_folder_id is not None:
                        folder_pk = from_global_id(add_to_folder_id)[1]
                        folder = CorpusFolder.objects.get(pk=folder_pk, corpus=corpus)

                    # Generate path from filename
                    safe_filename = "".join(
                        c if c.isalnum() or c in "-_." else "_" for c in filename[:100]
                    )
                    doc_path = f"/documents/{safe_filename}"

                    # Use import_content for content-based deduplication
                    document, status, path_record = corpus.import_content(
                        content=file_bytes,
                        path=doc_path,
                        user=user,
                        folder=folder,
                        title=title,
                        description=description,
                        file_type=kind,
                        custom_meta=custom_meta,
                        backend_lock=True,
                        is_public=make_public,
                        slug=slug,
                    )

                    # Set permissions on the document (may be new or reused)
                    set_permissions_for_obj_to_user(
                        user, document, [PermissionTypes.CRUD]
                    )

                    if status == "created":
                        logger.info(
                            f"[UPLOAD] Created new document {document.id} in corpus {corpus.id}"
                        )
                    elif status == "created_from_existing":
                        logger.info(
                            f"[UPLOAD] Created corpus-isolated document {document.id} "
                            f"with provenance from {document.source_document_id} in corpus {corpus.id}"
                        )
                    elif status == "linked":
                        logger.info(
                            f"[UPLOAD] Linked to existing document {document.id} "
                            f"(same content already in corpus) in corpus {corpus.id}"
                        )
                    elif status == "updated":
                        logger.info(
                            f"[UPLOAD] Updated document at path {doc_path} in corpus {corpus.id}"
                        )
                    else:
                        logger.info(
                            f"[UPLOAD] Document {document.id} status: {status} in corpus {corpus.id}"
                        )

                    # Note: folder assignment is already handled by corpus.import_content()
                    # which passes folder to import_document() -> DocumentPath creation

                except Exception as e:
                    logger.error(f"[UPLOAD] Error importing to corpus: {e}")
                    message = f"Importing to corpus failed due to error: {e}"
                    return UploadDocument(message=message, ok=False, document=None)
            else:
                # Standalone document upload (no corpus) - create directly
                if kind in [
                    "application/pdf",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ]:
                    pdf_file = ContentFile(file_bytes, name=filename)
                    document = Document(
                        creator=user,
                        title=title,
                        description=description,
                        custom_meta=custom_meta,
                        pdf_file=pdf_file,
                        backend_lock=True,
                        is_public=make_public,
                        file_type=kind,
                        slug=slug,
                    )
                    document.save()
                elif kind in ["text/plain", "application/txt"]:
                    txt_extract_file = ContentFile(file_bytes, name=filename)
                    document = Document(
                        creator=user,
                        title=title,
                        description=description,
                        custom_meta=custom_meta,
                        txt_extract_file=txt_extract_file,
                        backend_lock=True,
                        is_public=make_public,
                        file_type=kind,
                        slug=slug,
                    )
                    document.save()

                set_permissions_for_obj_to_user(user, document, [PermissionTypes.CRUD])

                # Handle linking to extract (corpus case already handled above)
                if add_to_extract_id is not None:
                    try:
                        extract = Extract.objects.get(
                            Q(pk=from_global_id(add_to_extract_id)[1])
                            & (Q(creator=user) | Q(is_public=True))
                        )
                        if extract.finished is not None:
                            raise ValueError(
                                "Cannot add document to a finished extract"
                            )
                        transaction.on_commit(lambda: extract.documents.add(document))
                    except Exception as e:
                        message = f"Adding to extract failed due to error: {e}"

            ok = True

        except Exception as e:
            message = f"Error on upload: {e}"

        return UploadDocument(message=message, ok=ok, document=document)


class UploadDocumentsZip(graphene.Mutation):
    """
    Mutation for uploading multiple documents via a zip file.
    The zip is stored as a temporary file and processed asynchronously.
    Only files with allowed MIME types will be created as documents.
    """

    class Arguments:
        base64_file_string = graphene.String(
            required=True,
            description="Base64-encoded zip file containing documents to upload",
        )
        title_prefix = graphene.String(
            required=False,
            description="Optional prefix for document titles (will be combined with filename)",
        )
        description = graphene.String(
            required=False,
            description="Optional description to apply to all documents",
        )
        custom_meta = GenericScalar(
            required=False, description="Optional metadata to apply to all documents"
        )
        add_to_corpus_id = graphene.ID(
            required=False,
            description="If provided, successfully uploaded documents will be added to corpus with specified id",
        )
        make_public = graphene.Boolean(
            required=True,
            description="If True, documents are immediately public. Defaults to False.",
        )

    ok = graphene.Boolean()
    message = graphene.String()
    job_id = graphene.String(description="ID to track the processing job")

    @login_required
    @graphql_ratelimit(rate=RateLimits.IMPORT)
    def mutate(
        root,
        info,
        base64_file_string,
        make_public,
        title_prefix=None,
        description=None,
        custom_meta=None,
        add_to_corpus_id=None,
    ):
        # Was going to user a user_passes_test decorator, but I wanted a custom error message
        # that could be easily reflected to user in the GUI.
        if (
            info.context.user.is_usage_capped
            and not settings.USAGE_CAPPED_USER_CAN_IMPORT_CORPUS
        ):
            raise PermissionError(
                "By default, usage-capped users cannot bulk upload documents. "
                "Please contact the admin to authorize your account."
            )

        try:
            logger.info("UploadDocumentsZip.mutate() - Received zip upload request...")

            # Store zip in a temporary file
            base64_img_bytes = base64_file_string.encode("utf-8")
            decoded_file_data = base64.decodebytes(base64_img_bytes)

            job_id = str(uuid.uuid4())

            with transaction.atomic():
                temporary_file = TemporaryFileHandle.objects.create()
                temporary_file.file = ContentFile(
                    decoded_file_data,
                    name=f"documents_zip_import_{job_id}.zip",
                )
                temporary_file.save()
                logger.info("UploadDocumentsZip.mutate() - temporary file created.")

                # Check if we need to link to a corpus
                corpus_id = None
                if add_to_corpus_id is not None:
                    try:
                        corpus = Corpus.objects.get(
                            id=from_global_id(add_to_corpus_id)[1]
                        )
                        # Check if user has permission on this corpus
                        if not user_has_permission_for_obj(
                            info.context.user, corpus, PermissionTypes.EDIT
                        ):
                            raise PermissionError(
                                "You don't have permission to add documents to this corpus"
                            )
                        corpus_id = corpus.id
                    except Exception as e:
                        logger.error(f"Error validating corpus: {e}")
                        return UploadDocumentsZip(
                            message=f"Error validating corpus: {e}",
                            ok=False,
                            job_id=job_id,
                        )

            # Launch async task to process the zip file
            if getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
                chain(
                    process_documents_zip.s(
                        temporary_file.id,
                        info.context.user.id,
                        job_id,
                        title_prefix,
                        description,
                        custom_meta,
                        make_public,
                        corpus_id,
                    )
                ).apply_async()
            else:
                transaction.on_commit(
                    lambda: chain(
                        process_documents_zip.s(
                            temporary_file.id,
                            info.context.user.id,
                            job_id,
                            title_prefix,
                            description,
                            custom_meta,
                            make_public,
                            corpus_id,
                        )
                    ).apply_async()
                )
            logger.info("UploadDocumentsZip.mutate() - Async task launched...")

            ok = True
            message = f"Upload started. Job ID: {job_id}"

        except Exception as e:
            ok = False
            message = f"Could not start document upload job due to error: {e}"
            job_id = None
            logger.error(message)

        return UploadDocumentsZip(message=message, ok=ok, job_id=job_id)


class ImportZipToCorpus(graphene.Mutation):
    """
    Mutation for importing a zip file to a corpus with folder structure preserved.

    Unlike UploadDocumentsZip which discards folder structure, this mutation:
    - Creates corpus folders matching the zip's directory structure
    - Places documents in their corresponding folders
    - Validates zip security (path traversal, zip bombs, etc.)
    - Requires corpus EDIT permission

    The import is processed asynchronously. Use the returned job_id to track progress.
    """

    class Arguments:
        base64_file_string = graphene.String(
            required=True,
            description="Base64-encoded zip file containing documents to import",
        )
        corpus_id = graphene.ID(
            required=True,
            description="ID of the corpus to import documents into",
        )
        target_folder_id = graphene.ID(
            required=False,
            description=(
                "Optional folder ID within the corpus to place zip contents under. "
                "If not provided, zip contents are placed at corpus root."
            ),
        )
        title_prefix = graphene.String(
            required=False,
            description="Optional prefix for document titles (combined with filename)",
        )
        description = graphene.String(
            required=False,
            description="Optional description to apply to all documents",
        )
        custom_meta = GenericScalar(
            required=False,
            description="Optional metadata to apply to all documents",
        )
        make_public = graphene.Boolean(
            required=True,
            description="If True, documents are immediately public",
        )

    ok = graphene.Boolean()
    message = graphene.String()
    job_id = graphene.String(description="ID to track the import job")

    @login_required
    @graphql_ratelimit(rate=RateLimits.IMPORT)
    def mutate(
        root,
        info,
        base64_file_string,
        corpus_id,
        make_public,
        target_folder_id=None,
        title_prefix=None,
        description=None,
        custom_meta=None,
    ):
        from celery import chain

        from opencontractserver.tasks.import_tasks import (
            import_zip_with_folder_structure,
        )

        # Check if usage-capped users can import
        if (
            info.context.user.is_usage_capped
            and not settings.USAGE_CAPPED_USER_CAN_IMPORT_CORPUS
        ):
            raise PermissionError(
                "By default, usage-capped users cannot bulk import documents. "
                "Please contact the admin to authorize your account."
            )

        try:
            logger.info("ImportZipToCorpus.mutate() - Received zip import request...")

            # Validate and get corpus
            try:
                corpus = Corpus.objects.get(id=from_global_id(corpus_id)[1])
            except Corpus.DoesNotExist:
                return ImportZipToCorpus(
                    ok=False,
                    message="Corpus not found",
                    job_id=None,
                )

            # Check permission on corpus
            if not user_has_permission_for_obj(
                info.context.user, corpus, PermissionTypes.EDIT
            ):
                return ImportZipToCorpus(
                    ok=False,
                    message="You don't have permission to add documents to this corpus",
                    job_id=None,
                )

            # Validate target folder if provided
            target_folder_pk = None
            if target_folder_id:
                try:
                    target_folder = CorpusFolder.objects.get(
                        id=from_global_id(target_folder_id)[1],
                        corpus=corpus,
                    )
                    target_folder_pk = target_folder.id
                except CorpusFolder.DoesNotExist:
                    return ImportZipToCorpus(
                        ok=False,
                        message="Target folder not found or does not belong to this corpus",
                        job_id=None,
                    )

            # Validate base64 string size before decoding to prevent memory exhaustion
            # Base64 encoding adds ~33% overhead, so max encoded size is ~1.4x decoded size
            max_encoded_size = int(ZIP_MAX_TOTAL_SIZE_BYTES * 1.4)
            if len(base64_file_string) > max_encoded_size:
                return ImportZipToCorpus(
                    ok=False,
                    message=f"File exceeds maximum allowed size of {ZIP_MAX_TOTAL_SIZE_BYTES // (1024 * 1024)}MB",
                    job_id=None,
                )

            # Decode and store the zip file
            base64_zip_bytes = base64_file_string.encode("utf-8")
            decoded_file_data = base64.decodebytes(base64_zip_bytes)

            job_id = str(uuid.uuid4())

            with transaction.atomic():
                temporary_file = TemporaryFileHandle.objects.create()
                temporary_file.file = ContentFile(
                    decoded_file_data,
                    name=f"zip_import_{job_id}.zip",
                )
                temporary_file.save()
                logger.info("ImportZipToCorpus.mutate() - Temporary file created")

            # Launch async task
            if getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
                chain(
                    import_zip_with_folder_structure.s(
                        temporary_file.id,
                        info.context.user.id,
                        job_id,
                        corpus.id,
                        target_folder_pk,
                        title_prefix,
                        description,
                        custom_meta,
                        make_public,
                    )
                ).apply_async()
            else:
                transaction.on_commit(
                    lambda: chain(
                        import_zip_with_folder_structure.s(
                            temporary_file.id,
                            info.context.user.id,
                            job_id,
                            corpus.id,
                            target_folder_pk,
                            title_prefix,
                            description,
                            custom_meta,
                            make_public,
                        )
                    ).apply_async()
                )
            logger.info("ImportZipToCorpus.mutate() - Async task launched")

            return ImportZipToCorpus(
                ok=True,
                message=f"Import started. Job ID: {job_id}",
                job_id=job_id,
            )

        except Exception as e:
            logger.error(f"ImportZipToCorpus.mutate() - Error: {e}")
            return ImportZipToCorpus(
                ok=False,
                message=f"Could not start import job: {e}",
                job_id=None,
            )


class DeleteDocument(DRFDeletion):
    class IOSettings:
        model = Document
        lookup_field = "id"

    class Arguments:
        id = graphene.String(required=True)


class DeleteMultipleDocuments(graphene.Mutation):
    class Arguments:
        document_ids_to_delete = graphene.List(
            graphene.String,
            required=True,
            description="List of ids of the documents to delete",
        )

    ok = graphene.Boolean()
    message = graphene.String()

    @login_required
    def mutate(root, info, document_ids_to_delete):
        try:
            document_pks = list(
                map(
                    lambda label_id: from_global_id(label_id)[1], document_ids_to_delete
                )
            )
            documents = Document.objects.filter(
                pk__in=document_pks, creator=info.context.user
            )
            documents.delete()
            ok = True
            message = "Success"

        except Exception as e:
            ok = False
            message = f"Delete failed due to error: {e}"

        return DeleteMultipleDocuments(ok=ok, message=message)


class RemoveAnnotation(graphene.Mutation):
    class Arguments:
        annotation_id = graphene.String(
            required=True, description="Id of the annotation that is to be deleted."
        )

    ok = graphene.Boolean()
    message = graphene.String()

    @login_required
    def mutate(root, info, annotation_id):
        try:
            annotation_pk = from_global_id(annotation_id)[1]
            annotation_obj = Annotation.objects.get(pk=annotation_pk)

            # Check if user has permission to delete this annotation
            # This now handles privacy-aware permissions for annotations with created_by_* fields
            if not user_has_permission_for_obj(
                info.context.user,
                annotation_obj,
                PermissionTypes.DELETE,
                include_group_permissions=True,
            ):
                return RemoveAnnotation(
                    ok=False,
                    message="You don't have permission to delete this annotation",
                )

            annotation_obj.delete()
            return RemoveAnnotation(ok=True, message="Annotation deleted successfully")

        except Annotation.DoesNotExist:
            return RemoveAnnotation(ok=False, message="Annotation not found")
        except Exception as e:
            logger.error(f"Error deleting annotation {annotation_id}: {e}")
            return RemoveAnnotation(
                ok=False, message=f"Error deleting annotation: {str(e)}"
            )


class RejectAnnotation(graphene.Mutation):
    class Arguments:
        annotation_id = graphene.ID(
            required=True, description="ID of the annotation to reject"
        )
        comment = graphene.String(description="Optional comment for the rejection")

    ok = graphene.Boolean()
    user_feedback = graphene.Field(UserFeedbackType)
    message = graphene.String()

    @login_required
    @transaction.atomic
    def mutate(root, info, annotation_id, comment=None):
        user = info.context.user
        annotation_pk = from_global_id(annotation_id)[1]

        try:
            annotation = Annotation.objects.get(pk=annotation_pk)
        except ObjectDoesNotExist:
            return RejectAnnotation(
                ok=False, user_feedback=None, message="Annotation not found"
            )

        # Check if user has COMMENT permission on this annotation
        # COMMENT permission respects document+corpus inheritance and corpus.allow_comments
        can_comment = user_has_permission_for_obj(
            user, annotation, PermissionTypes.COMMENT, include_group_permissions=True
        )

        if not can_comment:
            return RejectAnnotation(
                ok=False,
                user_feedback=None,
                message="You don't have permission to comment on this annotation",
            )

        user_feedback, created = UserFeedback.objects.get_or_create(
            commented_annotation=annotation,
            defaults={
                "creator": user,
                "approved": False,
                "rejected": True,
                "comment": comment or "",
            },
        )

        if not created:
            user_feedback.approved = False
            user_feedback.rejected = True
            user_feedback.comment = comment or user_feedback.comment
            user_feedback.save()

        set_permissions_for_obj_to_user(user, user_feedback, [PermissionTypes.CRUD])

        return RejectAnnotation(
            ok=True, user_feedback=user_feedback, message="Annotation rejected"
        )


class ApproveAnnotation(graphene.Mutation):
    class Arguments:
        annotation_id = graphene.ID(
            required=True, description="ID of the annotation to approve"
        )
        comment = graphene.String(description="Optional comment for the approval")

    ok = graphene.Boolean()
    user_feedback = graphene.Field(UserFeedbackType)
    message = graphene.String()

    @login_required
    @transaction.atomic
    def mutate(root, info, annotation_id, comment=None):
        user = info.context.user
        annotation_pk = from_global_id(annotation_id)[1]

        try:
            annotation = Annotation.objects.get(pk=annotation_pk)
        except ObjectDoesNotExist:
            return ApproveAnnotation(
                ok=False, user_feedback=None, message="Annotation not found"
            )

        # Check if user has COMMENT permission on this annotation
        # COMMENT permission respects document+corpus inheritance and corpus.allow_comments
        can_comment = user_has_permission_for_obj(
            user, annotation, PermissionTypes.COMMENT, include_group_permissions=True
        )

        if not can_comment:
            return ApproveAnnotation(
                ok=False,
                user_feedback=None,
                message="You don't have permission to comment on this annotation",
            )

        user_feedback, created = UserFeedback.objects.get_or_create(
            commented_annotation=annotation,
            defaults={
                "creator": user,
                "approved": True,
                "rejected": False,
                "comment": comment or "",
            },
        )

        if not created:
            user_feedback.approved = True
            user_feedback.rejected = False
            user_feedback.comment = comment or user_feedback.comment
            user_feedback.save()

        set_permissions_for_obj_to_user(user, user_feedback, [PermissionTypes.CRUD])

        return ApproveAnnotation(
            ok=True, user_feedback=user_feedback, message="Annotation approved"
        )


class AddAnnotation(graphene.Mutation):
    class Arguments:
        json = GenericScalar(
            required=True, description="New-style JSON for multipage annotations"
        )
        page = graphene.Int(
            required=True, description="What page is this annotation on (0-indexed)"
        )
        raw_text = graphene.String(
            required=True, description="What is the raw text of the annotation?"
        )
        corpus_id = graphene.String(
            required=True, description="ID of the corpus this annotation is for."
        )
        document_id = graphene.String(
            required=True, description="Id of the document this annotation is on."
        )
        annotation_label_id = graphene.String(
            required=True,
            description="Id of the label that is applied via this annotation.",
        )
        annotation_type = graphene.Argument(
            graphene.Enum.from_enum(LabelType), required=True
        )

    ok = graphene.Boolean()
    annotation = graphene.Field(AnnotationType)

    @login_required
    @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("WRITE_LIGHT"))
    def mutate(
        root,
        info,
        json,
        page,
        raw_text,
        corpus_id,
        document_id,
        annotation_label_id,
        annotation_type,
    ):
        corpus_pk = from_global_id(corpus_id)[1]
        document_pk = from_global_id(document_id)[1]
        label_pk = from_global_id(annotation_label_id)[1]

        user = info.context.user

        annotation = Annotation(
            page=page,
            raw_text=raw_text,
            corpus_id=corpus_pk,
            document_id=document_pk,
            annotation_label_id=label_pk,
            creator=user,
            json=json,
            annotation_type=annotation_type.value,
        )
        annotation.save()
        set_permissions_for_obj_to_user(user, annotation, [PermissionTypes.CRUD])
        ok = True

        return AddAnnotation(ok=ok, annotation=annotation)


class AddDocTypeAnnotation(graphene.Mutation):
    class Arguments:
        corpus_id = graphene.String(
            required=True, description="ID of the corpus this annotation is for."
        )
        document_id = graphene.String(
            required=True, description="Id of the document this annotation is on."
        )
        annotation_label_id = graphene.String(
            required=True,
            description="Id of the label that is applied via this annotation.",
        )

    ok = graphene.Boolean()
    annotation = graphene.Field(AnnotationType)

    @login_required
    def mutate(root, info, corpus_id, document_id, annotation_label_id):
        annotation = None
        ok = False

        corpus_pk = from_global_id(corpus_id)[1]
        document_pk = from_global_id(document_id)[1]
        annotation_label_pk = from_global_id(annotation_label_id)[1]

        user = info.context.user

        annotation = Annotation.objects.create(
            corpus_id=corpus_pk,
            document_id=document_pk,
            annotation_label_id=annotation_label_pk,
            creator=user,
        )
        set_permissions_for_obj_to_user(user, annotation, [PermissionTypes.CRUD])
        ok = True

        return AddDocTypeAnnotation(ok=ok, annotation=annotation)


class RemoveRelationship(graphene.Mutation):
    class Arguments:
        relationship_id = graphene.String(
            required=True, description="Id of the relationship that is to be deleted."
        )

    ok = graphene.Boolean()
    message = graphene.String()

    @login_required
    def mutate(root, info, relationship_id):
        try:
            relationship_pk = from_global_id(relationship_id)[1]
            relationship_obj = Relationship.objects.get(pk=relationship_pk)

            # Check if user has permission to delete this relationship
            if not user_has_permission_for_obj(
                info.context.user,
                relationship_obj,
                PermissionTypes.DELETE,
                include_group_permissions=True,
            ):
                return RemoveRelationship(
                    ok=False,
                    message="You don't have permission to delete this relationship",
                )

            relationship_obj.delete()
            return RemoveRelationship(
                ok=True, message="Relationship deleted successfully"
            )

        except Relationship.DoesNotExist:
            return RemoveRelationship(ok=False, message="Relationship not found")
        except Exception as e:
            logger.error(f"Error deleting relationship {relationship_id}: {e}")
            return RemoveRelationship(
                ok=False, message=f"Error deleting relationship: {str(e)}"
            )


class AddRelationship(graphene.Mutation):
    class Arguments:
        source_ids = graphene.List(
            graphene.String,
            required=True,
            description="List of ids of the tokens in the source annotation",
        )
        target_ids = graphene.List(
            graphene.String,
            required=True,
            description="List of ids of the target tokens in the label",
        )
        relationship_label_id = graphene.String(
            required=True, description="ID of the label for this relationship."
        )
        corpus_id = graphene.String(
            required=True, description="ID of the corpus for this relationship."
        )
        document_id = graphene.String(
            required=True, description="ID of the document for this relationship."
        )

    ok = graphene.Boolean()
    relationship = graphene.Field(RelationshipType)
    message = graphene.String()

    @login_required
    def mutate(
        root,
        info,
        source_ids,
        target_ids,
        relationship_label_id,
        corpus_id,
        document_id,
    ):
        try:
            source_pks = list(
                map(lambda graphene_id: from_global_id(graphene_id)[1], source_ids)
            )
            target_pks = list(
                map(lambda graphene_id: from_global_id(graphene_id)[1], target_ids)
            )
            relationship_label_pk = from_global_id(relationship_label_id)[1]
            corpus_pk = from_global_id(corpus_id)[1]
            document_pk = from_global_id(document_id)[1]

            source_annotations = Annotation.objects.filter(id__in=source_pks)
            target_annotations = Annotation.objects.filter(id__in=target_pks)

            # Check that user can see all source and target annotations
            all_annotations = list(source_annotations) + list(target_annotations)
            for annotation in all_annotations:
                if not user_has_permission_for_obj(
                    info.context.user,
                    annotation,
                    PermissionTypes.READ,
                    include_group_permissions=True,
                ):
                    return AddRelationship(
                        ok=False,
                        relationship=None,
                        message=f"You don't have permission to see annotation {annotation.id}",
                    )

            # Check that user has permission to create in the corpus
            corpus = Corpus.objects.get(pk=corpus_pk)
            if not user_has_permission_for_obj(
                info.context.user,
                corpus,
                PermissionTypes.CREATE,
                include_group_permissions=True,
            ):
                return AddRelationship(
                    ok=False,
                    relationship=None,
                    message="You don't have permission to create relationships in this corpus",
                )

            relationship = Relationship.objects.create(
                creator=info.context.user,
                relationship_label_id=relationship_label_pk,
                corpus_id=corpus_pk,
                document_id=document_pk,
            )
            set_permissions_for_obj_to_user(
                info.context.user, relationship, [PermissionTypes.CRUD]
            )
            relationship.target_annotations.set(target_annotations)
            relationship.source_annotations.set(source_annotations)

            return AddRelationship(
                ok=True,
                relationship=relationship,
                message="Relationship created successfully",
            )

        except Exception as e:
            logger.error(f"Error creating relationship: {e}")
            return AddRelationship(
                ok=False,
                relationship=None,
                message=f"Error creating relationship: {str(e)}",
            )


class RemoveRelationships(graphene.Mutation):
    class Arguments:
        relationship_ids = graphene.List(graphene.String)

    ok = graphene.Boolean()
    message = graphene.String()

    @login_required
    def mutate(root, info, relationship_ids):
        user = info.context.user
        for graphene_id in relationship_ids:
            pk = from_global_id(graphene_id)[1]
            try:
                relationship = Relationship.objects.get(pk=pk)
                if not user_has_permission_for_obj(
                    user,
                    relationship,
                    PermissionTypes.DELETE,
                    include_group_permissions=True,
                ):
                    return RemoveRelationships(ok=False, message="Permission denied")
                relationship.delete()
            except Relationship.DoesNotExist:
                return RemoveRelationships(ok=False, message="Relationship not found")
        return RemoveRelationships(ok=True, message="Success")


class UpdateRelationship(graphene.Mutation):
    """
    Update an existing relationship by adding or removing annotations
    from source or target sets.
    """

    class Arguments:
        relationship_id = graphene.String(
            required=True, description="ID of the relationship to update"
        )
        add_source_ids = graphene.List(
            graphene.String,
            required=False,
            description="List of annotation IDs to add as sources",
        )
        add_target_ids = graphene.List(
            graphene.String,
            required=False,
            description="List of annotation IDs to add as targets",
        )
        remove_source_ids = graphene.List(
            graphene.String,
            required=False,
            description="List of annotation IDs to remove from sources",
        )
        remove_target_ids = graphene.List(
            graphene.String,
            required=False,
            description="List of annotation IDs to remove from targets",
        )

    ok = graphene.Boolean()
    relationship = graphene.Field(RelationshipType)
    message = graphene.String()

    @login_required
    def mutate(
        root,
        info,
        relationship_id,
        add_source_ids=None,
        add_target_ids=None,
        remove_source_ids=None,
        remove_target_ids=None,
    ):
        try:
            relationship_pk = from_global_id(relationship_id)[1]
            relationship = Relationship.objects.get(pk=relationship_pk)

            # Check UPDATE permission on the relationship
            if not user_has_permission_for_obj(
                info.context.user,
                relationship,
                PermissionTypes.UPDATE,
                include_group_permissions=True,
            ):
                return UpdateRelationship(
                    ok=False,
                    relationship=None,
                    message="You don't have permission to update this relationship",
                )

            # Add source annotations
            if add_source_ids:
                source_pks = [from_global_id(sid)[1] for sid in add_source_ids]
                source_annotations = Annotation.objects.filter(id__in=source_pks)

                # Verify user can read all annotations
                for annotation in source_annotations:
                    if not user_has_permission_for_obj(
                        info.context.user,
                        annotation,
                        PermissionTypes.READ,
                        include_group_permissions=True,
                    ):
                        return UpdateRelationship(
                            ok=False,
                            relationship=None,
                            message=f"You don't have permission to see annotation {annotation.id}",
                        )

                relationship.source_annotations.add(*source_annotations)

            # Add target annotations
            if add_target_ids:
                target_pks = [from_global_id(tid)[1] for tid in add_target_ids]
                target_annotations = Annotation.objects.filter(id__in=target_pks)

                # Verify user can read all annotations
                for annotation in target_annotations:
                    if not user_has_permission_for_obj(
                        info.context.user,
                        annotation,
                        PermissionTypes.READ,
                        include_group_permissions=True,
                    ):
                        return UpdateRelationship(
                            ok=False,
                            relationship=None,
                            message=f"You don't have permission to see annotation {annotation.id}",
                        )

                relationship.target_annotations.add(*target_annotations)

            # Remove source annotations
            if remove_source_ids:
                source_pks = [from_global_id(sid)[1] for sid in remove_source_ids]
                source_annotations = Annotation.objects.filter(id__in=source_pks)
                relationship.source_annotations.remove(*source_annotations)

            # Remove target annotations
            if remove_target_ids:
                target_pks = [from_global_id(tid)[1] for tid in remove_target_ids]
                target_annotations = Annotation.objects.filter(id__in=target_pks)
                relationship.target_annotations.remove(*target_annotations)

            relationship.save()

            return UpdateRelationship(
                ok=True,
                relationship=relationship,
                message="Relationship updated successfully",
            )

        except Relationship.DoesNotExist:
            return UpdateRelationship(
                ok=False,
                relationship=None,
                message="Relationship not found",
            )
        except Exception as e:
            logger.error(f"Error updating relationship: {e}")
            return UpdateRelationship(
                ok=False,
                relationship=None,
                message=f"Error updating relationship: {str(e)}",
            )


class UpdateAnnotation(DRFMutation):
    class IOSettings:
        pk_fields = ["annotation_label"]
        lookup_field = "id"
        serializer = AnnotationSerializer
        model = Annotation
        graphene_model = AnnotationType

    class Arguments:
        id = graphene.String(required=True)
        page = graphene.Int()
        raw_text = graphene.String()
        json = GenericScalar()
        annotation_label = graphene.String()


class UpdateRelations(graphene.Mutation):
    class Arguments:
        relationships = graphene.List(RelationInputType)

    ok = graphene.Boolean()
    message = graphene.String()

    @login_required
    def mutate(root, info, relationships):
        user = info.context.user
        for relationship in relationships:
            pk = from_global_id(relationship["id"])[1]
            source_pks = list(
                map(
                    lambda graphene_id: from_global_id(graphene_id)[1],
                    relationship["source_ids"],
                )
            )
            target_pks = list(
                map(
                    lambda graphene_id: from_global_id(graphene_id)[1],
                    relationship["target_ids"],
                )
            )
            relationship_label_pk = from_global_id(
                relationship["relationship_label_id"]
            )[1]
            corpus_pk = from_global_id(relationship["corpus_id"])[1]
            document_pk = from_global_id(relationship["document_id"])[1]

            try:
                relationship = Relationship.objects.get(id=pk)
                if not user_has_permission_for_obj(
                    user,
                    relationship,
                    PermissionTypes.UPDATE,
                    include_group_permissions=True,
                ):
                    return UpdateRelations(ok=False, message="Permission denied")
            except Relationship.DoesNotExist:
                return UpdateRelations(ok=False, message="Relationship not found")

            relationship.relationship_label_id = relationship_label_pk
            relationship.document_id = document_pk
            relationship.corpus_id = corpus_pk
            relationship.save()

            relationship.target_annotations.set(target_pks)
            relationship.source_annotations.set(source_pks)

        return UpdateRelations(ok=True, message="Success")


# ============================================================================
# DOCUMENT RELATIONSHIP MUTATIONS
# ============================================================================


class CreateDocumentRelationship(graphene.Mutation):
    """
    Create a new relationship between two documents in the same corpus.

    Permission requirements:
    - User must have CREATE permission on BOTH source and target documents
    - User must have CREATE permission on the corpus

    Validation:
    - Both documents must be in the specified corpus
    - For RELATIONSHIP type: annotation_label_id is required
    - For NOTES type: annotation_label_id is optional
    """

    class Arguments:
        source_document_id = graphene.String(
            required=True, description="ID of the source document"
        )
        target_document_id = graphene.String(
            required=True, description="ID of the target document"
        )
        relationship_type = graphene.String(
            required=True,
            description="Type of relationship: 'RELATIONSHIP' or 'NOTES'",
        )
        annotation_label_id = graphene.String(
            required=False,
            description="ID of the annotation label (required for RELATIONSHIP type)",
        )
        corpus_id = graphene.String(
            required=True,
            description="ID of the corpus (both documents must be in this corpus)",
        )
        data = GenericScalar(
            required=False, description="JSON data payload (e.g., for notes content)"
        )

    ok = graphene.Boolean()
    document_relationship = graphene.Field(DocumentRelationshipType)
    message = graphene.String()

    @login_required
    def mutate(
        root,
        info,
        source_document_id,
        target_document_id,
        relationship_type,
        corpus_id,
        annotation_label_id=None,
        data=None,
    ):
        try:
            # Decode global IDs
            source_doc_pk = from_global_id(source_document_id)[1]
            target_doc_pk = from_global_id(target_document_id)[1]
            corpus_pk = from_global_id(corpus_id)[1]

            # Validate relationship_type (use model constant)
            valid_types = [
                choice[0] for choice in DocumentRelationship.RELATIONSHIP_TYPE_CHOICES
            ]
            if relationship_type not in valid_types:
                return CreateDocumentRelationship(
                    ok=False,
                    document_relationship=None,
                    message=f"Invalid relationship_type. Must be one of: {valid_types}",
                )

            # Validate that RELATIONSHIP type has annotation_label
            if relationship_type == "RELATIONSHIP" and not annotation_label_id:
                return CreateDocumentRelationship(
                    ok=False,
                    document_relationship=None,
                    message="annotation_label_id is required for RELATIONSHIP type",
                )

            # Fetch corpus first and check permission
            try:
                corpus = Corpus.objects.get(pk=corpus_pk)
            except Corpus.DoesNotExist:
                return CreateDocumentRelationship(
                    ok=False,
                    document_relationship=None,
                    message="Corpus not found",
                )

            # IDOR-safe: same message for not found or no permission
            if not user_has_permission_for_obj(
                info.context.user,
                corpus,
                PermissionTypes.CREATE,
                include_group_permissions=True,
            ):
                return CreateDocumentRelationship(
                    ok=False,
                    document_relationship=None,
                    message="Corpus not found",
                )

            # Fetch source document and check permission (before same-corpus check
            # for better error messages)
            try:
                source_doc = Document.objects.get(pk=source_doc_pk)
            except Document.DoesNotExist:
                return CreateDocumentRelationship(
                    ok=False,
                    document_relationship=None,
                    message="Source document not found",
                )

            if not user_has_permission_for_obj(
                info.context.user,
                source_doc,
                PermissionTypes.CREATE,
                include_group_permissions=True,
            ):
                return CreateDocumentRelationship(
                    ok=False,
                    document_relationship=None,
                    message="You don't have permission to create relationships for the source document",
                )

            # Fetch target document and check permission
            try:
                target_doc = Document.objects.get(pk=target_doc_pk)
            except Document.DoesNotExist:
                return CreateDocumentRelationship(
                    ok=False,
                    document_relationship=None,
                    message="Target document not found",
                )

            if not user_has_permission_for_obj(
                info.context.user,
                target_doc,
                PermissionTypes.CREATE,
                include_group_permissions=True,
            ):
                return CreateDocumentRelationship(
                    ok=False,
                    document_relationship=None,
                    message="You don't have permission to create relationships for the target document",
                )

            # Validate both docs are in the corpus via DocumentPath
            # Use distinct document IDs to handle cases where a document
            # has multiple paths in the corpus (e.g., different folders)
            from opencontractserver.documents.models import DocumentPath

            docs_in_corpus = set(
                DocumentPath.objects.filter(
                    corpus_id=corpus_pk,
                    document_id__in=[source_doc_pk, target_doc_pk],
                    is_current=True,
                    is_deleted=False,
                ).values_list("document_id", flat=True)
            )

            if len(docs_in_corpus) != 2:
                return CreateDocumentRelationship(
                    ok=False,
                    document_relationship=None,
                    message="Both documents must be in the same corpus",
                )

            # Handle optional annotation_label
            annotation_label_pk = None
            if annotation_label_id:
                annotation_label_pk = from_global_id(annotation_label_id)[1]
                try:
                    AnnotationLabel.objects.get(pk=annotation_label_pk)
                except AnnotationLabel.DoesNotExist:
                    return CreateDocumentRelationship(
                        ok=False,
                        document_relationship=None,
                        message="Annotation label not found",
                    )

            # Create the document relationship
            #
            # PERMISSION MODEL: DocumentRelationship uses inherited permissions
            # (not guardian object permissions). Access is determined by:
            #   Effective Permission = MIN(source_doc_perm, target_doc_perm, corpus_perm)
            # See: docs/permissioning/consolidated_permissioning_guide.md
            #
            doc_relationship = DocumentRelationship.objects.create(
                creator=info.context.user,
                source_document_id=source_doc_pk,
                target_document_id=target_doc_pk,
                relationship_type=relationship_type,
                annotation_label_id=annotation_label_pk,
                corpus_id=corpus_pk,
                data=data or {},
            )

            return CreateDocumentRelationship(
                ok=True,
                document_relationship=doc_relationship,
                message="Document relationship created successfully",
            )

        except Exception as e:
            logger.error(f"Error creating document relationship: {e}")
            return CreateDocumentRelationship(
                ok=False,
                document_relationship=None,
                message=f"Error creating document relationship: {str(e)}",
            )


class UpdateDocumentRelationship(graphene.Mutation):
    """
    Update an existing document relationship.

    Permission requirements:
    - User must have UPDATE permission on the document relationship
    - OR UPDATE permission on BOTH source and target documents

    Updatable fields:
    - relationship_type (with validation for annotation_label requirement)
    - annotation_label_id
    - data (JSON payload)
    - corpus_id
    """

    class Arguments:
        document_relationship_id = graphene.String(
            required=True, description="ID of the document relationship to update"
        )
        relationship_type = graphene.String(
            required=False,
            description="New relationship type: 'RELATIONSHIP' or 'NOTES'",
        )
        annotation_label_id = graphene.String(
            required=False, description="New annotation label ID"
        )
        corpus_id = graphene.String(required=False, description="New corpus ID")
        data = GenericScalar(required=False, description="Updated JSON data payload")

    ok = graphene.Boolean()
    document_relationship = graphene.Field(DocumentRelationshipType)
    message = graphene.String()

    @login_required
    def mutate(
        root,
        info,
        document_relationship_id,
        relationship_type=None,
        annotation_label_id=None,
        corpus_id=None,
        data=None,
    ):
        try:
            # Decode global ID
            doc_rel_pk = from_global_id(document_relationship_id)[1]

            # Use optimizer for IDOR-safe fetch with visibility check
            doc_relationship = (
                DocumentRelationshipQueryOptimizer.get_relationship_by_id(
                    user=info.context.user,
                    relationship_id=int(doc_rel_pk),
                )
            )

            # IDOR protection: same message for not found or not accessible
            if doc_relationship is None:
                return UpdateDocumentRelationship(
                    ok=False,
                    document_relationship=None,
                    message="Document relationship not found",
                )

            # Check UPDATE permission (inherited from source_doc + target_doc + corpus)
            if not DocumentRelationshipQueryOptimizer.user_has_permission(
                info.context.user,
                doc_relationship,
                "UPDATE",
            ):
                return UpdateDocumentRelationship(
                    ok=False,
                    document_relationship=None,
                    message="You don't have permission to update this document relationship",
                )

            # Validate relationship_type if provided (use model constant)
            valid_types = [
                choice[0] for choice in DocumentRelationship.RELATIONSHIP_TYPE_CHOICES
            ]
            if relationship_type is not None:
                if relationship_type not in valid_types:
                    return UpdateDocumentRelationship(
                        ok=False,
                        document_relationship=None,
                        message=f"Invalid relationship_type. Must be one of: {valid_types}",
                    )
                doc_relationship.relationship_type = relationship_type

            # Handle annotation_label update
            if annotation_label_id is not None:
                if annotation_label_id == "":
                    # Explicitly clearing the annotation label
                    doc_relationship.annotation_label_id = None
                else:
                    annotation_label_pk = from_global_id(annotation_label_id)[1]
                    try:
                        AnnotationLabel.objects.get(pk=annotation_label_pk)
                    except AnnotationLabel.DoesNotExist:
                        return UpdateDocumentRelationship(
                            ok=False,
                            document_relationship=None,
                            message="Annotation label not found",
                        )
                    doc_relationship.annotation_label_id = annotation_label_pk

            # Explicit validation: RELATIONSHIP type requires annotation_label
            # (Check before full_clean for clearer error message)
            final_type = relationship_type or doc_relationship.relationship_type
            final_label = (
                doc_relationship.annotation_label_id
                if annotation_label_id != ""
                else None
            )
            if final_type == "RELATIONSHIP" and not final_label:
                return UpdateDocumentRelationship(
                    ok=False,
                    document_relationship=None,
                    message="annotation_label_id is required for RELATIONSHIP type",
                )

            # Handle corpus update
            if corpus_id is not None:
                if corpus_id == "":
                    return UpdateDocumentRelationship(
                        ok=False,
                        document_relationship=None,
                        message="Corpus is required for document relationships",
                    )
                else:
                    corpus_pk = from_global_id(corpus_id)[1]
                    try:
                        corpus = Corpus.objects.get(pk=corpus_pk)
                    except Corpus.DoesNotExist:
                        # IDOR-safe: same message for not found or no permission
                        return UpdateDocumentRelationship(
                            ok=False,
                            document_relationship=None,
                            message="Corpus not found",
                        )

                    # Check permission on the new corpus (IDOR-safe message)
                    if not user_has_permission_for_obj(
                        info.context.user,
                        corpus,
                        PermissionTypes.UPDATE,
                        include_group_permissions=True,
                    ):
                        return UpdateDocumentRelationship(
                            ok=False,
                            document_relationship=None,
                            message="Corpus not found",
                        )

                    # Validate both documents are in the new corpus
                    docs_in_corpus = corpus.documents.filter(
                        id__in=[
                            doc_relationship.source_document_id,
                            doc_relationship.target_document_id,
                        ]
                    ).count()
                    if docs_in_corpus != 2:
                        return UpdateDocumentRelationship(
                            ok=False,
                            document_relationship=None,
                            message="Both documents must be in the specified corpus",
                        )
                    doc_relationship.corpus_id = corpus_pk

            # Handle data update
            if data is not None:
                doc_relationship.data = data

            # Validate before saving
            doc_relationship.full_clean()
            doc_relationship.save()

            return UpdateDocumentRelationship(
                ok=True,
                document_relationship=doc_relationship,
                message="Document relationship updated successfully",
            )

        except Exception as e:
            logger.error(f"Error updating document relationship: {e}")
            return UpdateDocumentRelationship(
                ok=False,
                document_relationship=None,
                message=f"Error updating document relationship: {str(e)}",
            )


class DeleteDocumentRelationship(graphene.Mutation):
    """
    Delete a document relationship.

    Permission requirements:
    - User must have DELETE permission on the document relationship
    - OR DELETE permission on BOTH source and target documents
    """

    class Arguments:
        document_relationship_id = graphene.String(
            required=True, description="ID of the document relationship to delete"
        )

    ok = graphene.Boolean()
    message = graphene.String()

    @login_required
    def mutate(root, info, document_relationship_id):
        try:
            # Decode global ID
            doc_rel_pk = from_global_id(document_relationship_id)[1]

            # Use optimizer for IDOR-safe fetch with visibility check
            doc_relationship = (
                DocumentRelationshipQueryOptimizer.get_relationship_by_id(
                    user=info.context.user,
                    relationship_id=int(doc_rel_pk),
                )
            )

            # IDOR protection: same message for not found or not accessible
            if doc_relationship is None:
                return DeleteDocumentRelationship(
                    ok=False, message="Document relationship not found"
                )

            # Check DELETE permission (inherited from source_doc + target_doc + corpus)
            if not DocumentRelationshipQueryOptimizer.user_has_permission(
                info.context.user,
                doc_relationship,
                "DELETE",
            ):
                return DeleteDocumentRelationship(
                    ok=False,
                    message="You don't have permission to delete this document relationship",
                )

            doc_relationship.delete()

            return DeleteDocumentRelationship(
                ok=True, message="Document relationship deleted successfully"
            )

        except Exception as e:
            logger.error(f"Error deleting document relationship: {e}")
            return DeleteDocumentRelationship(
                ok=False, message=f"Error deleting document relationship: {str(e)}"
            )


class DeleteDocumentRelationships(graphene.Mutation):
    """
    Delete multiple document relationships at once.

    Permission requirements:
    - User must have DELETE permission on each document relationship
    """

    class Arguments:
        document_relationship_ids = graphene.List(
            graphene.String,
            required=True,
            description="List of document relationship IDs to delete",
        )

    ok = graphene.Boolean()
    message = graphene.String()
    deleted_count = graphene.Int()

    @login_required
    def mutate(root, info, document_relationship_ids):
        user = info.context.user

        try:
            # Decode all IDs first
            relationship_pks = [
                int(from_global_id(gid)[1]) for gid in document_relationship_ids
            ]

            # Fetch all relationships in a single query (fixes N+1)
            visible_relationships = (
                DocumentRelationshipQueryOptimizer.get_visible_relationships(
                    user=user
                ).filter(id__in=relationship_pks)
            )

            # Build a dict for O(1) lookup
            relationship_map = {rel.id: rel for rel in visible_relationships}

            # Check all relationships are visible (IDOR protection)
            for pk in relationship_pks:
                if pk not in relationship_map:
                    return DeleteDocumentRelationships(
                        ok=False,
                        message="Document relationship not found",
                        deleted_count=0,
                    )

            # Check DELETE permission for each relationship
            # (inherited from source_doc + target_doc + corpus)
            for pk, doc_relationship in relationship_map.items():
                if not DocumentRelationshipQueryOptimizer.user_has_permission(
                    user,
                    doc_relationship,
                    "DELETE",
                ):
                    return DeleteDocumentRelationships(
                        ok=False,
                        message="Document relationship not found",
                        deleted_count=0,
                    )

            # Delete all at once
            deleted_count = len(relationship_pks)
            DocumentRelationship.objects.filter(id__in=relationship_pks).delete()

            return DeleteDocumentRelationships(
                ok=True,
                message=f"Successfully deleted {deleted_count} document relationship(s)",
                deleted_count=deleted_count,
            )

        except Exception as e:
            logger.error(f"Error deleting document relationships: {e}")
            return DeleteDocumentRelationships(
                ok=False,
                message=f"Error deleting document relationships: {str(e)}",
                deleted_count=0,
            )


class DeleteLabelMutation(DRFDeletion):
    class IOSettings:
        model = AnnotationLabel
        lookup_field = "id"

    class Arguments:
        id = graphene.String(required=True)


class DeleteMultipleLabelMutation(graphene.Mutation):
    class Arguments:
        annotation_label_ids_to_delete = graphene.List(
            graphene.String,
            required=True,
            description="List of ids of the labels to delete",
        )

    ok = graphene.Boolean()
    message = graphene.String()

    @login_required
    def mutate(root, info, annotation_label_ids_to_delete):
        user = info.context.user
        try:
            label_pks = list(
                map(
                    lambda label_id: from_global_id(label_id)[1],
                    annotation_label_ids_to_delete,
                )
            )
            for label_pk in label_pks:
                try:
                    label = AnnotationLabel.objects.get(pk=label_pk)
                    # AnnotationLabel uses creator-based permissions (no guardian tables)
                    # Only the creator or superuser can delete labels
                    # read_only labels cannot be deleted (built-in system labels)
                    if label.read_only:
                        return DeleteMultipleLabelMutation(
                            ok=False, message="Cannot delete read-only labels"
                        )
                    if not user.is_superuser and label.creator_id != user.id:
                        # Use consistent error message for IDOR protection
                        return DeleteMultipleLabelMutation(
                            ok=False, message="Label not found"
                        )
                    label.delete()
                except AnnotationLabel.DoesNotExist:
                    return DeleteMultipleLabelMutation(
                        ok=False, message="Label not found"
                    )
            ok = True
            message = "Success"

        except Exception as e:
            ok = False
            message = f"Delete failed due to error: {e}"

        return DeleteMultipleLabelMutation(ok=ok, message=message)


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

    @classmethod
    def mutate(cls, root, info, *args, **kwargs):
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


class UpdateMe(graphene.Mutation):
    """Update basic profile fields for the current user, including slug."""

    class Arguments:
        name = graphene.String(required=False)
        first_name = graphene.String(required=False)
        last_name = graphene.String(required=False)
        phone = graphene.String(required=False)
        slug = graphene.String(required=False)
        is_profile_public = graphene.Boolean(required=False)  # Issue #611

    ok = graphene.Boolean()
    message = graphene.String()
    user = graphene.Field(UserType)

    @login_required
    def mutate(self, info, **kwargs):
        from config.graphql.serializers import UserUpdateSerializer

        user = info.context.user
        try:
            serializer = UserUpdateSerializer(user, data=kwargs, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return UpdateMe(ok=True, message="Success", user=user)
        except Exception as e:
            return UpdateMe(
                ok=False, message=f"Failed to update profile: {e}", user=None
            )


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
    def mutate(root, info, corpus_id, new_content):
        from opencontractserver.corpuses.models import Corpus

        try:
            user = info.context.user
            corpus_pk = from_global_id(corpus_id)[1]

            # Get the corpus and check ownership
            corpus = Corpus.objects.get(pk=corpus_pk)

            if corpus.creator != user:
                return UpdateCorpusDescription(
                    ok=False,
                    message="You can only update descriptions for corpuses that you created.",
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

        except Corpus.DoesNotExist:
            return UpdateCorpusDescription(
                ok=False, message="Corpus not found.", obj=None, version=None
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


class CreateLabelMutation(DRFMutation):
    class IOSettings:
        pk_fields = []
        serializer = AnnotationLabelSerializer
        model = AnnotationLabel
        graphene_model = AnnotationLabelType

    class Arguments:
        text = graphene.String(required=False)
        description = graphene.String(required=False)
        color = graphene.String(required=False)
        icon = graphene.String(required=False)
        type = graphene.String(required=False)


class UpdateLabelMutation(DRFMutation):
    class IOSettings:
        pk_fields = []
        serializer = AnnotationLabelSerializer
        lookup_field = "id"
        model = AnnotationLabel
        graphene_model = AnnotationLabelType

    class Arguments:
        id = graphene.String(required=True)
        text = graphene.String(required=False)
        description = graphene.String(required=False)
        color = graphene.String(required=False)
        icon = graphene.String(required=False)
        label_type = graphene.String(required=False)


class RemoveLabelsFromLabelsetMutation(graphene.Mutation):
    class Arguments:
        label_ids = graphene.List(
            graphene.String,
            required=True,
            description="List of Ids of the labels to be deleted.",
        )
        labelset_id = graphene.String(
            "Id of the labelset to delete the labels from", required=True
        )

    ok = graphene.Boolean()
    message = graphene.String()

    @login_required
    def mutate(root, info, label_ids, labelset_id):

        ok = False

        try:
            user = info.context.user
            label_pks = list(
                map(lambda graphene_id: from_global_id(graphene_id)[1], label_ids)
            )
            labelset = LabelSet.objects.get(
                Q(pk=from_global_id(labelset_id)[1])
                & (Q(creator=user) | Q(is_public=True))
            )
            labelset_labels = labelset.documents.filter(pk__in=label_pks)
            labelset.annotation_labels.remove(*labelset_labels)
            ok = True
            message = "Success"

        except Exception as e:
            message = f"Error removing label(s) from labelset: {e}"

        return RemoveLabelsFromLabelsetMutation(message=message, ok=ok)


class CreateLabelForLabelsetMutation(graphene.Mutation):
    class Arguments:
        labelset_id = graphene.String(
            required=True, description="Id of the label that is to be updated."
        )
        text = graphene.String(required=False)
        description = graphene.String(required=False)
        color = graphene.String(required=False)
        icon = graphene.String(required=False)
        label_type = graphene.String(required=False)

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(AnnotationLabelType)
    obj_id = graphene.ID()

    @login_required
    def mutate(root, info, labelset_id, text, description, color, icon, label_type):

        ok = False
        obj = None
        obj_id = None

        # Validate color format (defense in depth)
        is_valid_color, color_error = validate_color(color)
        if not is_valid_color:
            return CreateLabelForLabelsetMutation(
                obj=None, obj_id=None, message=color_error, ok=False
            )

        try:
            labelset = LabelSet.objects.get(
                pk=from_global_id(labelset_id)[1], creator=info.context.user
            )
            logger.debug("CreateLabelForLabelsetMutation - mutate / Labelset", labelset)
            obj = AnnotationLabel.objects.create(
                text=text,
                description=description,
                color=color,
                icon=icon,
                label_type=label_type,
                creator=info.context.user,
            )
            obj_id = to_global_id("AnnotationLabelType", obj.id)
            logger.debug("CreateLabelForLabelsetMutation - mutate / Created label", obj)

            set_permissions_for_obj_to_user(
                info.context.user, obj, [PermissionTypes.CRUD]
            )
            logger.debug(
                "CreateLabelForLabelsetMutation - permissioned for creating user"
            )

            labelset.annotation_labels.add(obj)
            ok = True
            message = "SUCCESS"
            logger.debug("Done")

        except Exception as e:
            message = f"Failed to create label for labelset due to error: {e}"

        return CreateLabelForLabelsetMutation(
            obj=obj, obj_id=obj_id, message=message, ok=ok
        )


class StartDocumentAnalysisMutation(graphene.Mutation):
    class Arguments:
        document_id = graphene.ID(
            required=False, description="Id of the document to be analyzed."
        )
        analyzer_id = graphene.ID(
            required=True, description="Id of the analyzer to use."
        )
        corpus_id = graphene.ID(
            required=False,
            description="Optional Id of the corpus to associate with the analysis.",
        )
        analysis_input_data = GenericScalar(
            required=False,
            description="Optional arguments to be passed to the analyzer.",
        )

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(AnalysisType)

    @login_required
    def mutate(
        root,
        info,
        analyzer_id,
        document_id=None,
        corpus_id=None,
        analysis_input_data=None,
    ):
        """
        Starts a document or corpus analysis using the specified analyzer.
        Accepts optional analysis_input_data for analyzers that need
        user-provided parameters.
        """

        user = info.context.user
        logger.info(f"StartDocumentAnalysisMutation called by user {user.id}")

        document_pk = from_global_id(document_id)[1] if document_id else None
        analyzer_pk = from_global_id(analyzer_id)[1]
        corpus_pk = from_global_id(corpus_id)[1] if corpus_id else None

        logger.info(
            f"Parsed IDs - document_pk: {document_pk}, analyzer_pk: {analyzer_pk}, corpus_pk: {corpus_pk}"
        )
        logger.info(f"Analysis input data: {analysis_input_data}")

        if document_pk is None and corpus_pk is None:
            raise ValueError("One of document_pk and corpus_pk must be provided")

        try:
            # Check permissions for document
            if document_pk:
                document = Document.objects.get(pk=document_pk)
                if not (document.creator == user or document.is_public):
                    raise PermissionError(
                        "You don't have permission to analyze this document."
                    )

            # Check permissions for corpus
            if corpus_pk:
                corpus = Corpus.objects.get(pk=corpus_pk)
                if not (corpus.creator == user or corpus.is_public):
                    raise PermissionError(
                        "You don't have permission to analyze this corpus."
                    )

            analyzer = Analyzer.objects.get(pk=analyzer_pk)
            logger.info(
                f"Found analyzer: {analyzer.id} with task_name: {analyzer.task_name}"
            )

            analysis = process_analyzer(
                user_id=user.id,
                analyzer=analyzer,
                corpus_id=corpus_pk,
                document_ids=[document_pk] if document_pk else None,
                corpus_action=None,
                analysis_input_data=analysis_input_data,
            )

            logger.info(
                f"Analysis created with ID: {analysis.id if analysis else 'None'}"
            )

            record_event(
                "analysis_started",
                {
                    "env": settings.MODE,
                    "user_id": info.context.user.id,
                },
            )

            return StartDocumentAnalysisMutation(
                ok=True, message="SUCCESS", obj=analysis
            )
        except Exception as e:
            logger.error(f"StartDocumentAnalysisMutation error: {e}", exc_info=True)
            return StartDocumentAnalysisMutation(ok=False, message=f"Error: {str(e)}")


class StartDocumentExtract(graphene.Mutation):
    class Arguments:
        document_id = graphene.ID(required=True)
        fieldset_id = graphene.ID(required=True)
        corpus_id = graphene.ID(required=False)

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(ExtractType)

    @staticmethod
    @login_required
    def mutate(root, info, document_id, fieldset_id, corpus_id=None):
        from opencontractserver.corpuses.models import Corpus

        doc_pk = from_global_id(document_id)[1]
        fieldset_pk = from_global_id(fieldset_id)[1]

        # Verify visibility for both document and fieldset
        try:
            document = Document.objects.visible_to_user(info.context.user).get(
                pk=doc_pk
            )
            fieldset = Fieldset.objects.visible_to_user(info.context.user).get(
                pk=fieldset_pk
            )
        except (Document.DoesNotExist, Fieldset.DoesNotExist):
            return StartDocumentExtract(
                ok=False, message="Resource not found", obj=None
            )

        corpus = None
        if corpus_id:
            corpus_pk = from_global_id(corpus_id)[1]
            corpus = Corpus.objects.get(pk=corpus_pk)

        extract = Extract.objects.create(
            name=f"Extract {uuid.uuid4()} for {document.title}",
            fieldset=fieldset,
            creator=info.context.user,
            corpus=corpus,
        )
        extract.documents.add(document)
        extract.save()

        # Start celery task to process extract
        extract.started = timezone.now()
        extract.save()
        transaction.on_commit(
            lambda: run_extract.s(extract.id, info.context.user.id).apply_async()
        )

        return StartDocumentExtract(ok=True, message="STARTED!", obj=extract)


class DeleteAnalysisMutation(graphene.Mutation):
    ok = graphene.Boolean()
    message = graphene.String()

    class Arguments:
        id = graphene.String(required=True)

    @login_required
    def mutate(root, info, id):

        # ok = False
        # message = "Could not complete"

        analysis_pk = from_global_id(id)[1]
        analysis = Analysis.objects.get(id=analysis_pk)

        # Check the object isn't locked by another user
        if analysis.user_lock is not None:
            if info.context.user.id == analysis.user_lock_id:
                raise PermissionError(
                    f"Specified object is locked by {info.context.user.username}. Cannot be "
                    f"updated / edited by another user."
                )

        # We ARE OK with deleting something that's been locked by the backend, however, as sh@t happens, and we want
        # frontend users to be able to delete things that are hanging or taking too long and start over / abandon them.

        if not user_has_permission_for_obj(
            user_val=info.context.user,
            instance=analysis,
            permission=PermissionTypes.DELETE,
            include_group_permissions=True,
        ):
            PermissionError("You don't have permission to delete this analysis.")

        # Kick off an async task to delete the analysis (as it can be very large)
        delete_analysis_and_annotations_task.si(analysis_pk=analysis_pk).apply_async()


class ObtainJSONWebTokenWithUser(graphql_jwt.ObtainJSONWebToken):
    user = graphene.Field(UserType)

    @classmethod
    def resolve(cls, root, info, **kwargs):
        return cls(user=info.context.user)


class CreateFieldset(graphene.Mutation):
    class Arguments:
        name = graphene.String(required=True)
        description = graphene.String(required=True)

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(FieldsetType)

    @staticmethod
    @login_required
    def mutate(root, info, name, description):
        fieldset = Fieldset(
            name=name,
            description=description,
            creator=info.context.user,
        )
        fieldset.save()
        set_permissions_for_obj_to_user(
            info.context.user, fieldset, [PermissionTypes.CRUD]
        )

        record_event(
            "fieldset_created",
            {
                "env": settings.MODE,
                "user_id": info.context.user.id,
            },
        )

        return CreateFieldset(ok=True, message="SUCCESS!", obj=fieldset)


class UpdateColumnMutation(DRFMutation):
    class Arguments:
        name = graphene.String(required=False)
        id = graphene.ID(required=True)
        fieldset_id = graphene.ID(required=False)
        query = graphene.String(required=False)
        match_text = graphene.String(required=False)
        output_type = graphene.String(required=False)
        limit_to_label = graphene.String(required=False)
        instructions = graphene.String(required=False)
        extract_is_list = graphene.Boolean(required=False)
        must_contain_text = graphene.String(required=False)
        task_name = graphene.String(required=False)

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(ColumnType)

    @staticmethod
    @login_required
    def mutate(
        root,
        info,
        id,
        name=None,
        query=None,
        match_text=None,
        output_type=None,
        limit_to_label=None,
        instructions=None,
        task_name=None,
        extract_is_list=None,
        language_model_id=None,
        must_contain_text=None,
    ):

        ok = False
        message = ""
        obj = None

        try:
            pk = from_global_id(id)[1]
            obj = Column.objects.get(pk=pk, creator=info.context.user)

            if task_name is not None:
                obj.task_name = task_name

            if language_model_id is not None:
                obj.language_model_id = from_global_id(language_model_id)[1]

            if name is not None:
                obj.name = name

            if query is not None:
                obj.query = query

            if match_text is not None:
                obj.match_text = match_text

            if output_type is not None:
                obj.output_type = output_type

            if limit_to_label is not None:
                obj.limit_to_label = limit_to_label

            if instructions is not None:
                obj.instructions = instructions

            if extract_is_list is not None:
                obj.extract_is_list = extract_is_list

            if must_contain_text is not None:
                obj.must_contain_text = must_contain_text

            obj.save()
            message = "SUCCESS!"
            ok = True

        except Exception as e:
            message = f"Failed to update: {e}"

        return UpdateColumnMutation(ok=ok, message=message, obj=obj)


class CreateColumn(graphene.Mutation):
    class Arguments:
        fieldset_id = graphene.ID(required=True)
        query = graphene.String(required=False)
        match_text = graphene.String(required=False)
        output_type = graphene.String(required=True)
        limit_to_label = graphene.String(required=False)
        instructions = graphene.String(required=False)
        extract_is_list = graphene.Boolean(required=False)
        must_contain_text = graphene.String(required=False)
        name = graphene.String(required=True)
        task_name = graphene.String(required=False)

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(ColumnType)

    @staticmethod
    @login_required
    def mutate(
        root,
        info,
        name,
        fieldset_id,
        output_type,
        task_name=None,
        extract_is_list=None,
        must_contain_text=None,
        query=None,
        match_text=None,
        limit_to_label=None,
        instructions=None,
    ):
        if {query, match_text} == {None}:
            raise ValueError("One of `query` or `match_text` must be provided.")

        fieldset = Fieldset.objects.get(pk=from_global_id(fieldset_id)[1])
        column = Column(
            name=name,
            fieldset=fieldset,
            query=query,
            match_text=match_text,
            output_type=output_type,
            limit_to_label=limit_to_label,
            instructions=instructions,
            must_contain_text=must_contain_text,
            **({"task_name": task_name} if task_name is not None else {}),
            extract_is_list=extract_is_list if extract_is_list is not None else False,
            creator=info.context.user,
        )
        column.save()
        set_permissions_for_obj_to_user(
            info.context.user, column, [PermissionTypes.CRUD]
        )
        return CreateColumn(ok=True, message="SUCCESS!", obj=column)


class DeleteColumn(graphene.Mutation):
    class Arguments:
        id = graphene.ID(required=True)

    ok = graphene.Boolean()
    message = graphene.String()
    deleted_id = graphene.String()

    @staticmethod
    @login_required
    def mutate(root, info, id):
        Column.objects.get(pk=from_global_id(id)[1], creator=info.context.user).delete()
        return DeleteColumn(ok=True, message="STARTED!", deleted_id=id)


class StartExtract(graphene.Mutation):
    class Arguments:
        extract_id = graphene.ID(required=True)

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(ExtractType)

    @staticmethod
    @login_required
    def mutate(root, info, extract_id):
        # Start celery task to process extract
        pk = from_global_id(extract_id)[1]
        extract = Extract.objects.get(pk=pk, creator=info.context.user)
        extract.started = timezone.now()
        extract.save()
        transaction.on_commit(
            lambda: run_extract.s(pk, info.context.user.id).apply_async()
        )

        record_event(
            "extract_started",
            {
                "env": settings.MODE,
                "user_id": info.context.user.id,
            },
        )

        return StartExtract(ok=True, message="STARTED!", obj=extract)


class CreateExtract(graphene.Mutation):
    """
    Create a new extract. If fieldset_id is provided, attach existing fieldset.
    Otherwise, a new fieldset is created. If no name is provided, fieldset name has
    form "[Extract name] Fieldset"
    """

    class Arguments:
        corpus_id = graphene.ID(required=False)
        name = graphene.String(required=True)
        fieldset_id = graphene.ID(required=False)
        fieldset_name = graphene.String(required=False)
        fieldset_description = graphene.String(required=False)

    ok = graphene.Boolean()
    msg = graphene.String()
    obj = graphene.Field(ExtractType)

    @staticmethod
    @login_required
    def mutate(
        root,
        info,
        name,
        corpus_id=None,
        fieldset_id=None,
        fieldset_name=None,
        fieldset_description=None,
    ):

        corpus = None
        if corpus_id is not None:
            corpus_pk = from_global_id(corpus_id)[1]
            corpus = Corpus.objects.get(pk=corpus_pk)
            if not (corpus.creator == info.context.user or corpus.is_public):
                return CreateExtract(
                    ok=False,
                    msg="You don't have permission to create an extract for this corpus.",
                    obj=None,
                )

        if fieldset_id is not None:
            fieldset = Fieldset.objects.get(pk=from_global_id(fieldset_id)[1])
        else:
            if fieldset_name is None:
                fieldset_name = f"{name} Fieldset"

            fieldset = Fieldset.objects.create(
                name=fieldset_name,
                description=(
                    fieldset_description
                    if fieldset_description is not None
                    else f"Autogenerated {fieldset_name}"
                ),
                creator=info.context.user,
            )
            set_permissions_for_obj_to_user(
                info.context.user, fieldset, [PermissionTypes.CRUD]
            )

        extract = Extract(
            corpus=corpus,
            name=name,
            fieldset=fieldset,
            creator=info.context.user,
        )
        extract.save()

        if corpus is not None:
            # Use new DocumentPath-based method to get active documents in corpus
            extract.documents.add(*corpus.get_documents())
        else:
            logger.info("Corpus IS still None... no docs to add.")

        set_permissions_for_obj_to_user(
            info.context.user, extract, [PermissionTypes.CRUD]
        )

        return CreateExtract(ok=True, msg="SUCCESS!", obj=extract)


class UpdateExtractMutation(graphene.Mutation):
    """
    Mutation to update an existing Extract object.

    Supports updating the name (title), corpus, fieldset, and error fields.
    Ensures proper permission checks are applied.
    """

    class Arguments:
        id = graphene.ID(required=True, description="ID of the Extract to update.")
        title = graphene.String(
            required=False, description="New title for the Extract."
        )
        corpus_id = graphene.ID(
            required=False,
            description="ID of the Corpus to associate with the Extract.",
        )
        fieldset_id = graphene.ID(
            required=False,
            description="ID of the Fieldset to associate with the Extract.",
        )
        error = graphene.String(
            required=False, description="Error message to update on the Extract."
        )
        # The Extract model does not have 'description', 'icon', or 'label_set' fields.
        # If these fields are added to the model, they can be included here.

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(ExtractType)

    @staticmethod
    @login_required
    def mutate(
        root, info, id, title=None, corpus_id=None, fieldset_id=None, error=None
    ):
        user = info.context.user

        try:
            extract_pk = from_global_id(id)[1]
            extract = Extract.objects.get(pk=extract_pk)
        except Extract.DoesNotExist:
            return UpdateExtractMutation(
                ok=False, message="Extract not found.", obj=None
            )

        # Check if the user has permission to update the Extract object
        if not user_has_permission_for_obj(
            user_val=user,
            instance=extract,
            permission=PermissionTypes.UPDATE,
            include_group_permissions=True,
        ):
            return UpdateExtractMutation(
                ok=False,
                message="You don't have permission to update this extract.",
                obj=None,
            )

        # Update fields
        if title is not None:
            extract.name = title

        if error is not None:
            extract.error = error

        if corpus_id is not None:
            corpus_pk = from_global_id(corpus_id)[1]
            try:
                corpus = Corpus.objects.get(pk=corpus_pk)
                # Check permission
                if not user_has_permission_for_obj(
                    user_val=user,
                    instance=corpus,
                    permission=PermissionTypes.READ,
                    include_group_permissions=True,
                ):
                    return UpdateExtractMutation(
                        ok=False,
                        message="You don't have permission to use this corpus.",
                        obj=None,
                    )
                extract.corpus = corpus
            except Corpus.DoesNotExist:
                return UpdateExtractMutation(
                    ok=False, message="Corpus not found.", obj=None
                )

        if fieldset_id is not None:
            fieldset_pk = from_global_id(fieldset_id)[1]
            print(
                f"Attempting to update extract {extract.id} with fieldset_id {fieldset_id} (pk: {fieldset_pk})"
            )
            try:
                fieldset = Fieldset.objects.get(pk=fieldset_pk)
                print(f"Found fieldset {fieldset.id} for update")
                # Check permission
                if not user_has_permission_for_obj(
                    user_val=user,
                    instance=fieldset,
                    permission=PermissionTypes.READ,
                    include_group_permissions=True,
                ):
                    print(
                        f"User {user.id} denied permission to use fieldset {fieldset.id}"
                    )
                    return UpdateExtractMutation(
                        ok=False,
                        message="You don't have permission to use this fieldset.",
                        obj=None,
                    )
                print(f"Updating extract {extract.id} fieldset to {fieldset.id}")
                extract.fieldset = fieldset
            except Fieldset.DoesNotExist:
                print(f"Fieldset with pk {fieldset_pk} not found")
                return UpdateExtractMutation(
                    ok=False, message="Fieldset not found.", obj=None
                )

        extract.save()
        extract.refresh_from_db()

        return UpdateExtractMutation(
            ok=True, message="Extract updated successfully.", obj=extract
        )


class AddDocumentsToExtract(DRFMutation):
    class Arguments:
        document_ids = graphene.List(
            graphene.ID,
            required=True,
            description="List of ids of the documents to add to extract.",
        )
        extract_id = graphene.ID(
            required=True, description="Id of corpus to add docs to."
        )

    ok = graphene.Boolean()
    message = graphene.String()
    objs = graphene.List(DocumentType)

    @login_required
    def mutate(root, info, extract_id, document_ids):

        ok = False
        doc_objs = []

        try:
            user = info.context.user

            extract = Extract.objects.get(
                Q(pk=from_global_id(extract_id)[1])
                & (Q(creator=user) | Q(is_public=True))
            )

            if extract.finished is not None:
                raise ValueError(
                    f"Extract {extract_id} already finished... it cannot be edited."
                )

            doc_pks = list(
                map(lambda graphene_id: from_global_id(graphene_id)[1], document_ids)
            )
            doc_objs = Document.objects.filter(
                Q(pk__in=doc_pks) & (Q(creator=user) | Q(is_public=True))
            )
            # print(f"Add documents to extract {extract}: {doc_objs}")
            extract.documents.add(*doc_objs)

            ok = True
            message = "Success"

        except Exception as e:
            message = f"Error assigning docs to corpus: {e}"

        return AddDocumentsToExtract(message=message, ok=ok, objs=doc_objs)


class RemoveDocumentsFromExtract(graphene.Mutation):
    class Arguments:
        extract_id = graphene.ID(
            required=True, description="ID of extract to remove documents from."
        )
        document_ids_to_remove = graphene.List(
            graphene.ID,
            required=True,
            description="List of ids of the docs to remove from extract.",
        )

    ok = graphene.Boolean()
    message = graphene.String()
    ids_removed = graphene.List(graphene.String)

    @login_required
    def mutate(root, info, extract_id, document_ids_to_remove):

        ok = False

        try:
            user = info.context.user
            extract = Extract.objects.get(
                Q(pk=from_global_id(extract_id)[1])
                & (Q(creator=user) | Q(is_public=True))
            )

            if extract.finished is not None:
                raise ValueError(
                    f"Extract {extract_id} already finished... it cannot be edited."
                )

            doc_pks = list(
                map(
                    lambda graphene_id: from_global_id(graphene_id)[1],
                    document_ids_to_remove,
                )
            )

            extract_docs = extract.documents.filter(pk__in=doc_pks)
            extract.documents.remove(*extract_docs)
            ok = True
            message = "Success"

        except Exception as e:
            message = f"Error on removing docs: {e}"

        return RemoveDocumentsFromExtract(
            message=message, ok=ok, ids_removed=document_ids_to_remove
        )


class DeleteExtract(DRFDeletion):
    class IOSettings:
        model = Extract
        lookup_field = "id"

    class Arguments:
        id = graphene.String(required=True)


class CreateCorpusAction(graphene.Mutation):
    """
    Create a new CorpusAction that will be triggered when documents are added or edited in a corpus.
    The action can run a fieldset extraction, an analyzer, or an agent - but exactly one must be specified.
    Requires UPDATE permission on the corpus to create actions.

    For thread/message-based triggers (new_thread, new_message), supports inline agent creation
    via create_agent_inline=True with agent creation parameters. This creates a corpus-scoped
    moderator agent and links it to the action in one transaction.
    """

    class Arguments:
        corpus_id = graphene.ID(
            required=True, description="ID of the corpus this action is for"
        )
        name = graphene.String(required=False, description="Name of the action")
        trigger = graphene.String(
            required=True,
            description="When to trigger the action (add_document or edit_document)",
        )
        fieldset_id = graphene.ID(
            required=False, description="ID of the fieldset to run"
        )
        analyzer_id = graphene.ID(
            required=False, description="ID of the analyzer to run"
        )
        # Agent-based action arguments (existing agent)
        agent_config_id = graphene.ID(
            required=False, description="ID of the agent configuration to use"
        )
        agent_prompt = graphene.String(
            required=False,
            description="Task prompt for the agent (required if agent_config_id is provided)",
        )
        pre_authorized_tools = graphene.List(
            graphene.String,
            required=False,
            description="Tools pre-authorized to run without approval",
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
        name: str = None,
        fieldset_id: str = None,
        analyzer_id: str = None,
        agent_config_id: str = None,
        agent_prompt: str = None,
        pre_authorized_tools: list = None,
        create_agent_inline: bool = False,
        inline_agent_name: str = None,
        inline_agent_description: str = None,
        inline_agent_instructions: str = None,
        inline_agent_tools: list = None,
        disabled: bool = False,
        run_on_all_corpuses: bool = False,
    ):
        from opencontractserver.agents.models import AgentConfiguration

        try:
            user = info.context.user
            corpus_pk = from_global_id(corpus_id)[1]

            # Get corpus and check permissions
            corpus = Corpus.objects.get(pk=corpus_pk)

            # Check if user has update permission on the corpus
            if corpus.creator.id != user.id:
                return CreateCorpusAction(
                    ok=False,
                    message="You can only create actions for your own corpuses",
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
                if not agent_prompt:
                    return CreateCorpusAction(
                        ok=False,
                        message="agent_prompt is required when creating an agent action",
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
            # Rationale: Thread/message triggered actions are specifically designed for automated
            # moderation workflows (spam detection, content filtering, etc.). Restricting tools
            # to the MODERATION category ensures these agents can only perform moderation-related
            # operations and cannot access broader corpus/document manipulation tools which could
            # pose security risks when triggered automatically by user content.
            if create_agent_inline and trigger in ["new_thread", "new_message"]:
                from opencontractserver.llms.tools.tool_registry import (
                    TOOL_REGISTRY,
                    ToolCategory,
                )

                # Get valid moderation tool names
                valid_moderation_tools = {
                    tool.name
                    for tool in TOOL_REGISTRY
                    if tool.category == ToolCategory.MODERATION
                }

                # Require at least one tool for moderation agents
                if not inline_agent_tools:
                    return CreateCorpusAction(
                        ok=False,
                        message="At least one tool is required for moderation agents. "
                        f"Available moderation tools: {', '.join(sorted(valid_moderation_tools))}",
                        obj=None,
                    )

                # Validate provided tools are valid moderation tools
                invalid_tools = set(inline_agent_tools) - valid_moderation_tools
                if invalid_tools:
                    return CreateCorpusAction(
                        ok=False,
                        message=f"Invalid tools for moderation agent: {', '.join(sorted(invalid_tools))}. "
                        f"Valid moderation tools: {', '.join(sorted(valid_moderation_tools))}",
                        obj=None,
                    )

            # Validate that exactly one of fieldset_id, analyzer_id, agent_config_id, or create_agent_inline is provided
            action_types_provided = sum(
                [
                    bool(fieldset_id),
                    bool(analyzer_id),
                    bool(agent_config_id),
                    bool(create_agent_inline),
                ]
            )
            if action_types_provided != 1:
                return CreateCorpusAction(
                    ok=False,
                    message=(
                        "Exactly one of fieldset_id, analyzer_id, "
                        "agent_config_id, or create_agent_inline must be provided"
                    ),
                    obj=None,
                )

            # Validate agent_prompt is provided when agent_config_id is set
            if agent_config_id and not agent_prompt:
                return CreateCorpusAction(
                    ok=False,
                    message="agent_prompt is required when agent_config_id is provided",
                    obj=None,
                )

            # Get fieldset, analyzer, or agent_config if provided
            fieldset = None
            analyzer = None
            agent_config = None

            if fieldset_id:
                fieldset_pk = from_global_id(fieldset_id)[1]
                fieldset = Fieldset.objects.get(pk=fieldset_pk)

            if analyzer_id:
                analyzer_pk = from_global_id(analyzer_id)[1]
                analyzer = Analyzer.objects.get(pk=analyzer_pk)

            if agent_config_id:
                agent_config_pk = from_global_id(agent_config_id)[1]
                agent_config = AgentConfiguration.objects.get(pk=agent_config_pk)
                # Verify agent config is active
                if not agent_config.is_active:
                    return CreateCorpusAction(
                        ok=False,
                        message="The selected agent configuration is not active",
                        obj=None,
                    )

            # Create inline agent if requested (wrapped in transaction with action creation)
            if create_agent_inline:
                with transaction.atomic():
                    # Create corpus-scoped agent configuration
                    agent_config = AgentConfiguration.objects.create(
                        name=inline_agent_name,
                        description=inline_agent_description
                        or f"Moderator agent for {corpus.title}",
                        system_instructions=inline_agent_instructions,
                        available_tools=inline_agent_tools or [],
                        permission_required_tools=[],  # All tools are pre-authorized for corpus actions
                        badge_config={
                            "icon": "shield",
                            "color": "#6366f1",
                            "label": "Moderator",
                        },
                        scope="CORPUS",
                        corpus=corpus,
                        creator=user,
                        is_active=True,
                        is_public=False,  # Corpus-scoped agents are private to corpus
                    )

                    # Set permissions for the inline agent
                    set_permissions_for_obj_to_user(
                        user, agent_config, [PermissionTypes.CRUD]
                    )

                    # Create the corpus action
                    corpus_action = CorpusAction.objects.create(
                        name=name or "Corpus Action",
                        corpus=corpus,
                        fieldset=fieldset,
                        analyzer=analyzer,
                        agent_config=agent_config,
                        agent_prompt=agent_prompt or "",
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

            # Standard path: Create the corpus action (no inline agent)
            corpus_action = CorpusAction.objects.create(
                name=name or "Corpus Action",
                corpus=corpus,
                fieldset=fieldset,
                analyzer=analyzer,
                agent_config=agent_config,
                agent_prompt=agent_prompt or "",
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
        agent_prompt = graphene.String(
            required=False,
            description="Task prompt for the agent",
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
        name: str = None,
        trigger: str = None,
        fieldset_id: str = None,
        analyzer_id: str = None,
        agent_config_id: str = None,
        agent_prompt: str = None,
        pre_authorized_tools: list = None,
        disabled: bool = None,
        run_on_all_corpuses: bool = None,
    ):
        from opencontractserver.agents.models import AgentConfiguration

        try:
            user = info.context.user
            action_pk = from_global_id(id)[1]

            # Get the corpus action
            corpus_action = CorpusAction.objects.get(pk=action_pk)

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
                fieldset = Fieldset.objects.get(pk=fieldset_pk)
                corpus_action.fieldset = fieldset
                corpus_action.analyzer = None
                corpus_action.agent_config = None
                corpus_action.agent_prompt = ""
                corpus_action.pre_authorized_tools = []

            elif analyzer_id is not None:
                analyzer_pk = from_global_id(analyzer_id)[1]
                analyzer = Analyzer.objects.get(pk=analyzer_pk)
                corpus_action.analyzer = analyzer
                corpus_action.fieldset = None
                corpus_action.agent_config = None
                corpus_action.agent_prompt = ""
                corpus_action.pre_authorized_tools = []

            elif agent_config_id is not None:
                agent_config_pk = from_global_id(agent_config_id)[1]
                agent_config = AgentConfiguration.objects.get(pk=agent_config_pk)
                if not agent_config.is_active:
                    return UpdateCorpusAction(
                        ok=False,
                        message="The selected agent configuration is not active",
                        obj=None,
                    )
                corpus_action.agent_config = agent_config
                corpus_action.fieldset = None
                corpus_action.analyzer = None
                # Agent prompt and pre_authorized_tools are updated below

            # Update agent-specific fields if agent is being used
            if corpus_action.agent_config:
                if agent_prompt is not None:
                    corpus_action.agent_prompt = agent_prompt
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


class UpdateNote(graphene.Mutation):
    """
    Mutation to update a note's content, creating a new version in the process.
    Only the note creator can update their notes.
    """

    class Arguments:
        note_id = graphene.ID(required=True, description="ID of the note to update")
        new_content = graphene.String(
            required=True, description="New markdown content for the note"
        )
        title = graphene.String(
            required=False, description="Optional new title for the note"
        )

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(NoteType)
    version = graphene.Int(description="The new version number after update")

    @login_required
    def mutate(root, info, note_id, new_content, title=None):
        from opencontractserver.annotations.models import Note

        try:
            user = info.context.user
            note_pk = from_global_id(note_id)[1]

            # Get the note and check ownership
            note = Note.objects.get(pk=note_pk)

            if note.creator != user:
                return UpdateNote(
                    ok=False,
                    message="You can only update notes that you created.",
                    obj=None,
                    version=None,
                )

            # Update title if provided
            if title is not None:
                note.title = title

            # Use the version_up method to create a new version
            revision = note.version_up(new_content=new_content, author=user)

            if revision is None:
                # No changes were made
                return UpdateNote(
                    ok=True,
                    message="No changes detected. Note remains at current version.",
                    obj=note,
                    version=note.revisions.count(),
                )

            # Refresh the note to get the updated state
            note.refresh_from_db()

            return UpdateNote(
                ok=True,
                message=f"Note updated successfully. Now at version {revision.version}.",
                obj=note,
                version=revision.version,
            )

        except Note.DoesNotExist:
            return UpdateNote(
                ok=False, message="Note not found.", obj=None, version=None
            )
        except Exception as e:
            logger.error(f"Error updating note: {e}")
            return UpdateNote(
                ok=False,
                message=f"Failed to update note: {str(e)}",
                obj=None,
                version=None,
            )


class DeleteNote(DRFDeletion):
    """
    Mutation to delete a note. Only the creator can delete their notes.
    """

    class IOSettings:
        model = Note
        lookup_field = "id"

    class Arguments:
        id = graphene.String(required=True)


class CreateNote(graphene.Mutation):
    """
    Mutation to create a new note for a document.
    """

    class Arguments:
        document_id = graphene.ID(
            required=True, description="ID of the document this note is for"
        )
        corpus_id = graphene.ID(
            required=False,
            description="Optional ID of the corpus this note is associated with",
        )
        title = graphene.String(required=True, description="Title of the note")
        content = graphene.String(
            required=True, description="Markdown content of the note"
        )
        parent_id = graphene.ID(
            required=False,
            description="Optional ID of parent note for hierarchical notes",
        )

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(NoteType)

    @login_required
    def mutate(root, info, document_id, title, content, corpus_id=None, parent_id=None):
        from opencontractserver.annotations.models import Note
        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.documents.models import Document

        try:
            user = info.context.user
            document_pk = from_global_id(document_id)[1]

            # Get the document
            document = Document.objects.get(pk=document_pk)

            # Check if user has permission to add notes to this document
            if not (document.is_public or document.creator == user):
                return CreateNote(
                    ok=False,
                    message="You don't have permission to add notes to this document.",
                    obj=None,
                )

            # Prepare note data
            note_data = {
                "document": document,
                "title": title,
                "content": content,
                "creator": user,
            }

            # Handle optional corpus
            if corpus_id:
                corpus_pk = from_global_id(corpus_id)[1]
                corpus = Corpus.objects.get(pk=corpus_pk)
                note_data["corpus"] = corpus

            # Handle optional parent note
            if parent_id:
                parent_pk = from_global_id(parent_id)[1]
                parent_note = Note.objects.get(pk=parent_pk)
                note_data["parent"] = parent_note

            # Create the note
            note = Note.objects.create(**note_data)

            # Set permissions
            set_permissions_for_obj_to_user(user, note, [PermissionTypes.CRUD])

            return CreateNote(ok=True, message="Note created successfully!", obj=note)

        except Document.DoesNotExist:
            return CreateNote(ok=False, message="Document not found.", obj=None)
        except Corpus.DoesNotExist:
            return CreateNote(ok=False, message="Corpus not found.", obj=None)
        except Note.DoesNotExist:
            return CreateNote(ok=False, message="Parent note not found.", obj=None)
        except Exception as e:
            logger.error(f"Error creating note: {e}")
            return CreateNote(
                ok=False, message=f"Failed to create note: {str(e)}", obj=None
            )


# DOCUMENT VERSIONING MUTATIONS ################################################


class RestoreDeletedDocument(graphene.Mutation):
    """
    Restore a soft-deleted document path within a corpus.

    Delegates to DocumentFolderService.restore_document() for:
    - Permission checking (corpus UPDATE permission)
    - Creating new DocumentPath with is_deleted=False
    """

    class Arguments:
        document_id = graphene.String(
            required=True, description="Global ID of the document to restore"
        )
        corpus_id = graphene.String(
            required=True, description="Global ID of the corpus"
        )

    ok = graphene.Boolean()
    message = graphene.String()
    document = graphene.Field(DocumentType)

    @login_required
    @graphql_ratelimit(rate=RateLimits.WRITE_MEDIUM)
    def mutate(root, info, document_id, corpus_id):
        from opencontractserver.corpuses.folder_service import DocumentFolderService

        user = info.context.user

        try:
            doc_pk = from_global_id(document_id)[1]
            corpus_pk = from_global_id(corpus_id)[1]

            document = Document.objects.get(pk=doc_pk)
            corpus = Corpus.objects.get(pk=corpus_pk)

            # Find the deleted path entry
            deleted_path = (
                DocumentPath.objects.filter(
                    document=document, corpus=corpus, is_deleted=True, is_current=True
                )
                .order_by("-created")
                .first()
            )

            if not deleted_path:
                return RestoreDeletedDocument(
                    ok=False,
                    message="Cannot restore document - it may not be deleted or may not exist in this corpus",
                    document=None,
                )

            # Delegate to service - handles permission checks and restoration
            success, error = DocumentFolderService.restore_document(
                user=user,
                document_path=deleted_path,
            )

            if not success:
                return RestoreDeletedDocument(
                    ok=False,
                    message=error,
                    document=None,
                )

            return RestoreDeletedDocument(
                ok=True,
                message="Document restored successfully",
                document=document,
            )

        except Document.DoesNotExist:
            return RestoreDeletedDocument(
                ok=False, message="Document not found", document=None
            )
        except Corpus.DoesNotExist:
            return RestoreDeletedDocument(
                ok=False, message="Corpus not found", document=None
            )
        except Exception as e:
            logger.error(f"Failed to restore document: {str(e)}")
            return RestoreDeletedDocument(
                ok=False,
                message=f"Failed to restore document: {str(e)}",
                document=None,
            )


class PermanentlyDeleteDocument(graphene.Mutation):
    """
    Permanently delete a soft-deleted document from a corpus.

    This is IRREVERSIBLE and removes:
    - All DocumentPath history for the document in this corpus
    - User annotations (non-structural) on the document
    - Relationships involving those annotations
    - DocumentSummaryRevision records
    - The Document itself if no other corpus references it

    Requires DELETE permission on the corpus.
    """

    class Arguments:
        document_id = graphene.String(
            required=True, description="Global ID of the document to permanently delete"
        )
        corpus_id = graphene.String(
            required=True, description="Global ID of the corpus"
        )

    ok = graphene.Boolean()
    message = graphene.String()

    @login_required
    @graphql_ratelimit(rate=RateLimits.WRITE_MEDIUM)
    def mutate(root, info, document_id, corpus_id):
        from opencontractserver.corpuses.folder_service import DocumentFolderService

        user = info.context.user

        try:
            doc_pk = from_global_id(document_id)[1]
            corpus_pk = from_global_id(corpus_id)[1]

            document = Document.objects.get(pk=doc_pk)
            corpus = Corpus.objects.get(pk=corpus_pk)

            success, error = DocumentFolderService.permanently_delete_document(
                user=user,
                document=document,
                corpus=corpus,
            )

            if not success:
                return PermanentlyDeleteDocument(ok=False, message=error)

            return PermanentlyDeleteDocument(
                ok=True, message="Document permanently deleted"
            )

        except Document.DoesNotExist:
            return PermanentlyDeleteDocument(ok=False, message="Document not found")
        except Corpus.DoesNotExist:
            return PermanentlyDeleteDocument(ok=False, message="Corpus not found")
        except Exception as e:
            logger.error(f"Failed to permanently delete document: {str(e)}")
            return PermanentlyDeleteDocument(
                ok=False, message=f"Failed to permanently delete document: {str(e)}"
            )


class EmptyTrash(graphene.Mutation):
    """
    Permanently delete ALL soft-deleted documents in a corpus (empty trash).

    This is IRREVERSIBLE and removes all documents currently in the corpus trash.

    Requires DELETE permission on the corpus.
    """

    class Arguments:
        corpus_id = graphene.String(
            required=True, description="Global ID of the corpus to empty trash for"
        )

    ok = graphene.Boolean()
    message = graphene.String()
    deleted_count = graphene.Int()

    @login_required
    @graphql_ratelimit(rate=RateLimits.WRITE_MEDIUM)
    def mutate(root, info, corpus_id):
        from opencontractserver.corpuses.folder_service import DocumentFolderService

        user = info.context.user

        try:
            corpus_pk = from_global_id(corpus_id)[1]
            corpus = Corpus.objects.get(pk=corpus_pk)

            deleted_count, error = DocumentFolderService.empty_trash(
                user=user,
                corpus=corpus,
            )

            if error:
                # Partial success case - some deleted but with errors
                return EmptyTrash(
                    ok=deleted_count > 0,
                    message=error,
                    deleted_count=deleted_count,
                )

            return EmptyTrash(
                ok=True,
                message=f"Successfully deleted {deleted_count} document(s) from trash",
                deleted_count=deleted_count,
            )

        except Corpus.DoesNotExist:
            return EmptyTrash(ok=False, message="Corpus not found", deleted_count=0)
        except Exception as e:
            logger.error(f"Failed to empty trash: {str(e)}")
            return EmptyTrash(
                ok=False, message=f"Failed to empty trash: {str(e)}", deleted_count=0
            )


class RestoreDocumentToVersion(graphene.Mutation):
    """
    Restore a document to a previous content version.
    Creates a new version that is a copy of the specified version.
    """

    class Arguments:
        document_id = graphene.String(
            required=True,
            description="Global ID of the document version to restore to",
        )
        corpus_id = graphene.String(
            required=True, description="Global ID of the corpus"
        )

    ok = graphene.Boolean()
    message = graphene.String()
    document = graphene.Field(DocumentType)
    new_version_number = graphene.Int()

    @login_required
    @graphql_ratelimit(rate=RateLimits.WRITE_MEDIUM)
    def mutate(root, info, document_id, corpus_id):
        user = info.context.user

        try:
            doc_pk = from_global_id(document_id)[1]
            corpus_pk = from_global_id(corpus_id)[1]

            old_version = Document.objects.get(pk=doc_pk)
            corpus = Corpus.objects.get(pk=corpus_pk)

            # Check UPDATE permission on both document and corpus
            if not user_has_permission_for_obj(
                user,
                old_version,
                PermissionTypes.UPDATE,
                include_group_permissions=True,
            ):
                return RestoreDocumentToVersion(
                    ok=False,
                    message="You don't have permission to restore this document",
                    document=None,
                    new_version_number=None,
                )

            if not user_has_permission_for_obj(
                user, corpus, PermissionTypes.UPDATE, include_group_permissions=True
            ):
                return RestoreDocumentToVersion(
                    ok=False,
                    message="You don't have permission to modify this corpus",
                    document=None,
                    new_version_number=None,
                )

            # Find the current version in the same version tree
            current_version = Document.objects.filter(
                version_tree_id=old_version.version_tree_id, is_current=True
            ).first()

            if not current_version:
                return RestoreDocumentToVersion(
                    ok=False,
                    message="Cannot find current version of this document",
                    document=None,
                    new_version_number=None,
                )

            if old_version.id == current_version.id:
                return RestoreDocumentToVersion(
                    ok=False,
                    message="Cannot restore to current version",
                    document=None,
                    new_version_number=None,
                )

            # Find the current path in the corpus
            current_path = DocumentPath.objects.filter(
                document__version_tree_id=old_version.version_tree_id,
                corpus=corpus,
                is_current=True,
                is_deleted=False,
            ).first()

            if not current_path:
                return RestoreDocumentToVersion(
                    ok=False,
                    message="Document not found in this corpus",
                    document=None,
                    new_version_number=None,
                )

            # Create a new document version as a copy of the old version
            with transaction.atomic():
                # Mark old current as not current
                current_version.is_current = False
                current_version.save()

                # Create new document version
                new_document = Document.objects.create(
                    title=old_version.title,
                    description=old_version.description,
                    custom_meta=old_version.custom_meta,
                    pdf_file=old_version.pdf_file,
                    txt_extract_file=old_version.txt_extract_file,
                    pawls_parse_file=old_version.pawls_parse_file,
                    icon=old_version.icon,
                    page_count=old_version.page_count,
                    file_type=old_version.file_type,
                    pdf_file_hash=old_version.pdf_file_hash,
                    creator=user,
                    # Versioning fields
                    version_tree_id=old_version.version_tree_id,
                    is_current=True,
                    parent=current_version,  # Parent is the old current, not the restored version
                )

                # Copy permissions from old version
                set_permissions_for_obj_to_user(
                    user, new_document, [PermissionTypes.CRUD]
                )

                # Mark old path as not current FIRST to avoid unique constraint violation
                current_path.is_current = False
                current_path.save()

                # Create new path entry with incremented version number
                new_path = DocumentPath.objects.create(
                    document=new_document,
                    corpus=corpus,
                    folder=current_path.folder,
                    path=current_path.path,
                    version_number=current_path.version_number + 1,
                    is_current=True,
                    is_deleted=False,
                    parent=current_path,
                    creator=user,
                )

            logger.info(
                f"User {user.id} restored document to version {old_version.id} "
                f"in corpus {corpus_pk}, new version number: {new_path.version_number}"
            )

            return RestoreDocumentToVersion(
                ok=True,
                message="Document restored to version successfully",
                document=new_document,
                new_version_number=new_path.version_number,
            )

        except Document.DoesNotExist:
            return RestoreDocumentToVersion(
                ok=False,
                message="Document version not found",
                document=None,
                new_version_number=None,
            )
        except Corpus.DoesNotExist:
            return RestoreDocumentToVersion(
                ok=False,
                message="Corpus not found",
                document=None,
                new_version_number=None,
            )
        except Exception as e:
            logger.error(f"Failed to restore document to version: {str(e)}")
            return RestoreDocumentToVersion(
                ok=False,
                message=f"Failed to restore document: {str(e)}",
                document=None,
                new_version_number=None,
            )


class Mutation(graphene.ObjectType):
    # TOKEN MUTATIONS (IF WE'RE NOT OUTSOURCING JWT CREATION TO AUTH0) #######
    if not settings.USE_AUTH0:
        token_auth = ObtainJSONWebTokenWithUser.Field()
    else:
        token_auth = graphql_jwt.ObtainJSONWebToken.Field()

    verify_token = graphql_jwt.Verify.Field()
    refresh_token = graphql_jwt.Refresh.Field()

    # ANNOTATION MUTATIONS ######################################################
    add_annotation = AddAnnotation.Field()
    remove_annotation = RemoveAnnotation.Field()
    update_annotation = UpdateAnnotation.Field()
    add_doc_type_annotation = AddDocTypeAnnotation.Field()
    remove_doc_type_annotation = RemoveAnnotation.Field()
    approve_annotation = ApproveAnnotation.Field()
    reject_annotation = RejectAnnotation.Field()

    # RELATIONSHIP MUTATIONS #####################################################
    add_relationship = AddRelationship.Field()
    remove_relationship = RemoveRelationship.Field()
    remove_relationships = RemoveRelationships.Field()
    update_relationship = UpdateRelationship.Field()
    update_relationships = UpdateRelations.Field()

    # DOCUMENT RELATIONSHIP MUTATIONS ############################################
    create_document_relationship = CreateDocumentRelationship.Field()
    update_document_relationship = UpdateDocumentRelationship.Field()
    delete_document_relationship = DeleteDocumentRelationship.Field()
    delete_document_relationships = DeleteDocumentRelationships.Field()

    # LABELSET MUTATIONS #######################################################
    create_labelset = CreateLabelset.Field()
    update_labelset = UpdateLabelset.Field()
    delete_labelset = DeleteLabelset.Field()

    # LABEL MUTATIONS ##########################################################
    create_annotation_label = CreateLabelMutation.Field()
    update_annotation_label = UpdateLabelMutation.Field()
    delete_annotation_label = DeleteLabelMutation.Field()
    delete_multiple_annotation_labels = DeleteMultipleLabelMutation.Field()
    create_annotation_label_for_labelset = CreateLabelForLabelsetMutation.Field()
    remove_annotation_labels_from_labelset = RemoveLabelsFromLabelsetMutation.Field()

    # SMART LABEL MUTATIONS (search/create with auto labelset management)
    smart_label_search_or_create = SmartLabelSearchOrCreateMutation.Field()
    smart_label_list = SmartLabelListMutation.Field()

    # DOCUMENT MUTATIONS #######################################################
    upload_document = UploadDocument.Field()  # Limited by user.is_usage_capped
    update_document = UpdateDocument.Field()
    update_document_summary = UpdateDocumentSummary.Field()
    delete_document = DeleteDocument.Field()
    delete_multiple_documents = DeleteMultipleDocuments.Field()
    upload_documents_zip = UploadDocumentsZip.Field()  # Bulk document upload via zip

    # DOCUMENT VERSIONING MUTATIONS ############################################
    restore_deleted_document = RestoreDeletedDocument.Field()
    restore_document_to_version = RestoreDocumentToVersion.Field()
    permanently_delete_document = PermanentlyDeleteDocument.Field()
    empty_trash = EmptyTrash.Field()

    # CORPUS MUTATIONS #########################################################
    fork_corpus = StartCorpusFork.Field()
    set_corpus_visibility = SetCorpusVisibility.Field()
    create_corpus = CreateCorpusMutation.Field()
    update_corpus = UpdateCorpusMutation.Field()
    update_me = UpdateMe.Field()
    update_corpus_description = UpdateCorpusDescription.Field()
    delete_corpus = DeleteCorpusMutation.Field()
    link_documents_to_corpus = AddDocumentsToCorpus.Field()
    remove_documents_from_corpus = RemoveDocumentsFromCorpus.Field()
    create_corpus_action = CreateCorpusAction.Field()
    update_corpus_action = UpdateCorpusAction.Field()
    delete_corpus_action = DeleteCorpusAction.Field()

    # CORPUS FOLDER MUTATIONS ##################################################
    create_corpus_folder = CreateCorpusFolderMutation.Field()
    update_corpus_folder = UpdateCorpusFolderMutation.Field()
    move_corpus_folder = MoveCorpusFolderMutation.Field()
    delete_corpus_folder = DeleteCorpusFolderMutation.Field()
    move_document_to_folder = MoveDocumentToFolderMutation.Field()
    move_documents_to_folder = MoveDocumentsToFolderMutation.Field()

    # IMPORT MUTATIONS #########################################################
    import_open_contracts_zip = UploadCorpusImportZip.Field()
    import_annotated_doc_to_corpus = UploadAnnotatedDocument.Field()
    import_zip_to_corpus = (
        ImportZipToCorpus.Field()
    )  # Bulk import with folder structure

    # EXPORT MUTATIONS #########################################################
    export_corpus = StartCorpusExport.Field()  # Limited by user.is_usage_capped
    delete_export = DeleteExport.Field()

    # USER PREFERENCE MUTATIONS #################################################
    accept_cookie_consent = AcceptCookieConsent.Field()
    dismiss_getting_started = DismissGettingStarted.Field()

    # ANALYSIS MUTATIONS #########################################################
    start_analysis_on_doc = StartDocumentAnalysisMutation.Field()
    delete_analysis = DeleteAnalysisMutation.Field()
    make_analysis_public = MakeAnalysisPublic.Field()

    # EXTRACT MUTATIONS ##########################################################
    create_fieldset = CreateFieldset.Field()

    create_column = CreateColumn.Field()
    update_column = UpdateColumnMutation.Field()
    delete_column = DeleteColumn.Field()

    create_extract = CreateExtract.Field()
    start_extract = StartExtract.Field()
    delete_extract = DeleteExtract.Field()
    update_extract = UpdateExtractMutation.Field()
    add_docs_to_extract = AddDocumentsToExtract.Field()
    remove_docs_from_extract = RemoveDocumentsFromExtract.Field()
    approve_datacell = ApproveDatacell.Field()
    reject_datacell = RejectDatacell.Field()
    edit_datacell = EditDatacell.Field()
    start_extract_for_doc = StartDocumentExtract.Field()
    update_note = UpdateNote.Field()
    delete_note = DeleteNote.Field()
    create_note = CreateNote.Field()

    # NEW METADATA MUTATIONS (Column/Datacell based) ################################
    create_metadata_column = CreateMetadataColumn.Field()
    update_metadata_column = UpdateMetadataColumn.Field()
    set_metadata_value = SetMetadataValue.Field()
    delete_metadata_value = DeleteMetadataValue.Field()

    # BADGE MUTATIONS #############################################################
    create_badge = CreateBadgeMutation.Field()
    update_badge = UpdateBadgeMutation.Field()
    delete_badge = DeleteBadgeMutation.Field()
    award_badge = AwardBadgeMutation.Field()
    revoke_badge = RevokeBadgeMutation.Field()

    # CONVERSATION/THREAD MUTATIONS ##############################################
    create_thread = CreateThreadMutation.Field()
    create_thread_message = CreateThreadMessageMutation.Field()
    reply_to_message = ReplyToMessageMutation.Field()
    update_message = UpdateMessageMutation.Field()
    delete_conversation = DeleteConversationMutation.Field()
    delete_message = DeleteMessageMutation.Field()

    # MODERATION MUTATIONS #######################################################
    lock_thread = LockThreadMutation.Field()
    unlock_thread = UnlockThreadMutation.Field()
    pin_thread = PinThreadMutation.Field()
    unpin_thread = UnpinThreadMutation.Field()
    delete_thread = DeleteThreadMutation.Field()
    restore_thread = RestoreThreadMutation.Field()
    add_moderator = AddModeratorMutation.Field()
    remove_moderator = RemoveModeratorMutation.Field()
    update_moderator_permissions = UpdateModeratorPermissionsMutation.Field()
    rollback_moderation_action = RollbackModerationActionMutation.Field()

    # VOTING MUTATIONS ###########################################################
    vote_message = VoteMessageMutation.Field()
    remove_vote = RemoveVoteMutation.Field()
    vote_conversation = VoteConversationMutation.Field()
    remove_conversation_vote = RemoveConversationVoteMutation.Field()

    # NOTIFICATION MUTATIONS #####################################################
    mark_notification_read = MarkNotificationReadMutation.Field()
    mark_notification_unread = MarkNotificationUnreadMutation.Field()
    mark_all_notifications_read = MarkAllNotificationsReadMutation.Field()
    delete_notification = DeleteNotificationMutation.Field()

    # AGENT CONFIGURATION MUTATIONS ##############################################
    create_agent_configuration = CreateAgentConfigurationMutation.Field()
    update_agent_configuration = UpdateAgentConfigurationMutation.Field()
    delete_agent_configuration = DeleteAgentConfigurationMutation.Field()
