import base64
import json
import logging
import uuid

import graphene
import graphql_jwt
from celery import chain, chord, group
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Max, Q
from django.utils import timezone
from filetype import filetype
from graphene.types.generic import GenericScalar
from graphql import GraphQLError
from graphql_jwt.decorators import login_required, user_passes_test
from graphql_relay import from_global_id, to_global_id

from config.graphql.annotation_serializers import AnnotationLabelSerializer
from config.graphql.base import DRFDeletion, DRFMutation
from config.graphql.graphene_types import (
    AnalysisType,
    AnnotationLabelType,
    AnnotationType,
    ColumnType,
    CorpusActionType,
    CorpusQueryType,
    CorpusType,
    DatacellType,
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
from config.graphql.serializers import (
    AnnotationSerializer,
    CorpusSerializer,
    DocumentSerializer,
    LabelsetSerializer,
)
from opencontractserver.analyzer.models import Analysis, Analyzer
from opencontractserver.annotations.models import (
    Annotation,
    AnnotationLabel,
    LabelSet,
    Note,
    Relationship,
)
from opencontractserver.corpuses.models import (
    Corpus,
    CorpusAction,
    CorpusQuery,
    TemporaryFileHandle,
)
from opencontractserver.documents.models import Document
from opencontractserver.extracts.models import Column, Datacell, Extract, Fieldset
from opencontractserver.feedback.models import UserFeedback
from opencontractserver.tasks import (
    build_label_lookups_task,
    burn_doc_annotations,
    delete_analysis_and_annotations_task,
    fork_corpus,
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


class MakeAnalysisPublic(graphene.Mutation):
    class Arguments:
        analysis_id = graphene.String(
            required=True, description="Analysis id to make public (superuser only)"
        )

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(AnalysisType)

    @user_passes_test(lambda user: user.is_superuser)
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


class MakeCorpusPublic(graphene.Mutation):
    class Arguments:
        corpus_id = graphene.String(
            required=True, description="Corpus id to make public (superuser only)"
        )

    ok = graphene.Boolean()
    message = graphene.String()

    @user_passes_test(lambda user: user.is_superuser)
    def mutate(root, info, corpus_id):

        try:
            corpus_pk = from_global_id(corpus_id)[1]

            make_corpus_public_task.si(corpus_id=corpus_pk).apply_async()
            message = "Starting an OpenContracts worker to make your corpus public!"
            ok = True

        except Exception as e:
            message = f"Failed to start task to make your corpus public due to unexpected error: {e}"
            ok = False

        return MakeCorpusPublic(
            ok=ok,
            message=message,
        )


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
        validation_config = GenericScalar(required=False, description="Validation configuration")
        default_value = GenericScalar(required=False, description="Default value")
        help_text = graphene.String(required=False, description="Help text for the field")
        display_order = graphene.Int(required=False, description="Display order")

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(ColumnType)

    @login_required
    def mutate(root, info, corpus_id, name, data_type, validation_config=None, 
               default_value=None, help_text=None, display_order=0):
        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.types.enums import PermissionTypes
        from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user
        
        try:
            user = info.context.user
            corpus = Corpus.objects.get(pk=from_global_id(corpus_id)[1])
            
            # Check permissions
            if not user_has_permission_for_obj(user, corpus, PermissionTypes.UPDATE):
                return CreateMetadataColumn(
                    ok=False,
                    message="You don't have permission to update this corpus"
                )
            
            # Get or create metadata fieldset for corpus
            if not hasattr(corpus, 'metadata_schema') or corpus.metadata_schema is None:
                fieldset = Fieldset.objects.create(
                    name=f"{corpus.title} Metadata",
                    description=f"Metadata schema for {corpus.title}",
                    corpus=corpus,
                    creator=user
                )
                set_permissions_for_obj_to_user(user, fieldset, [PermissionTypes.CRUD])
            else:
                fieldset = corpus.metadata_schema
            
            # Validate data type
            valid_types = ['STRING', 'TEXT', 'BOOLEAN', 'INTEGER', 'FLOAT', 
                          'DATE', 'DATETIME', 'URL', 'EMAIL', 'CHOICE', 
                          'MULTI_CHOICE', 'JSON']
            if data_type not in valid_types:
                return CreateMetadataColumn(
                    ok=False,
                    message=f"Invalid data type. Must be one of: {', '.join(valid_types)}"
                )
            
            # Validate choice fields
            if data_type in ['CHOICE', 'MULTI_CHOICE']:
                if not validation_config or 'choices' not in validation_config:
                    return CreateMetadataColumn(
                        ok=False,
                        message="Choice fields require 'choices' in validation_config"
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
                creator=user
            )
            
            set_permissions_for_obj_to_user(user, column, [PermissionTypes.CRUD])
            
            return CreateMetadataColumn(
                ok=True,
                message="Metadata field created successfully",
                obj=column
            )
            
        except Corpus.DoesNotExist:
            return CreateMetadataColumn(
                ok=False,
                message="Corpus not found"
            )
        except Exception as e:
            return CreateMetadataColumn(
                ok=False,
                message=f"Error creating metadata field: {str(e)}"
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
            if not user_has_permission_for_obj(user, column, PermissionTypes.UPDATE):
                return UpdateMetadataColumn(
                    ok=False,
                    message="You don't have permission to update this column"
                )
            
            # Ensure it's a manual entry column
            if not column.is_manual_entry:
                return UpdateMetadataColumn(
                    ok=False,
                    message="Only manual entry columns can be updated"
                )
            
            # Update fields
            if 'name' in kwargs:
                column.name = kwargs['name']
            if 'validation_config' in kwargs:
                # Validate choice fields
                if column.data_type in ['CHOICE', 'MULTI_CHOICE']:
                    if 'choices' not in kwargs['validation_config']:
                        return UpdateMetadataColumn(
                            ok=False,
                            message="Choice fields require 'choices' in validation_config"
                        )
                column.validation_config = kwargs['validation_config']
            if 'default_value' in kwargs:
                column.default_value = kwargs['default_value']
            if 'help_text' in kwargs:
                column.help_text = kwargs['help_text']
            if 'display_order' in kwargs:
                column.display_order = kwargs['display_order']
            
            column.save()
            
            return UpdateMetadataColumn(
                ok=True,
                message="Metadata field updated successfully",
                obj=column
            )
            
        except Column.DoesNotExist:
            return UpdateMetadataColumn(
                ok=False,
                message="Column not found"
            )
        except Exception as e:
            return UpdateMetadataColumn(
                ok=False,
                message=f"Error updating metadata field: {str(e)}"
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
        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.types.enums import PermissionTypes
        from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user
        from django.utils import timezone
        
        try:
            user = info.context.user
            document = Document.objects.get(pk=from_global_id(document_id)[1])
            corpus = Corpus.objects.get(pk=from_global_id(corpus_id)[1])
            column = Column.objects.get(pk=from_global_id(column_id)[1])
            
            # Check permissions on document
            if not user_has_permission_for_obj(user, document, PermissionTypes.UPDATE):
                return SetMetadataValue(
                    ok=False,
                    message="You don't have permission to update this document"
                )
            
            # Ensure column belongs to corpus metadata schema
            if not (column.fieldset and hasattr(column.fieldset, 'corpus') and 
                    column.fieldset.corpus_id == corpus.id):
                return SetMetadataValue(
                    ok=False,
                    message="Column does not belong to corpus metadata schema"
                )
            
            # Ensure it's a manual entry column
            if not column.is_manual_entry:
                return SetMetadataValue(
                    ok=False,
                    message="Only manual entry columns can be set"
                )
            
            # Find or create datacell
            datacell, created = Datacell.objects.update_or_create(
                document=document,
                column=column,
                defaults={
                    'data': {'value': value},
                    'data_definition': column.output_type,
                    'creator': user,
                    'completed': timezone.now(),
                }
            )
            
            if created:
                set_permissions_for_obj_to_user(user, datacell, [PermissionTypes.CRUD])
            
            return SetMetadataValue(
                ok=True,
                message="Metadata value set successfully",
                obj=datacell
            )
            
        except (Document.DoesNotExist, Corpus.DoesNotExist, Column.DoesNotExist):
            return SetMetadataValue(
                ok=False,
                message="Document, corpus, or column not found"
            )
        except Exception as e:
            return SetMetadataValue(
                ok=False,
                message=f"Error setting metadata value: {str(e)}"
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
        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.types.enums import PermissionTypes
        
        try:
            user = info.context.user
            document = Document.objects.get(pk=from_global_id(document_id)[1])
            corpus = Corpus.objects.get(pk=from_global_id(corpus_id)[1])
            column = Column.objects.get(pk=from_global_id(column_id)[1])
            
            # Find the datacell
            datacell = Datacell.objects.get(
                document=document,
                column=column
            )
            
            # Check permissions
            if not user_has_permission_for_obj(user, datacell, PermissionTypes.DELETE):
                return DeleteMetadataValue(
                    ok=False,
                    message="You don't have permission to delete this metadata value"
                )
            
            datacell.delete()
            
            return DeleteMetadataValue(
                ok=True,
                message="Metadata value deleted successfully"
            )
            
        except Datacell.DoesNotExist:
            return DeleteMetadataValue(
                ok=False,
                message="Metadata value not found"
            )
        except Exception as e:
            return DeleteMetadataValue(
                ok=False,
                message=f"Error deleting metadata value: {str(e)}"
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


class AddDocumentsToCorpus(graphene.Mutation):
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
        ok = False
        message = "Success"

        try:
            user = info.context.user
            doc_pks = list(
                map(lambda graphene_id: from_global_id(graphene_id)[1], document_ids)
            )
            doc_objs = Document.objects.filter(
                Q(pk__in=doc_pks) & (Q(creator=user) | Q(is_public=True))
            )
            corpus = Corpus.objects.get(
                Q(pk=from_global_id(corpus_id)[1])
                & (Q(creator=user) | Q(is_public=True))
            )
            corpus.documents.add(*doc_objs)
            ok = True

        except Exception as e:
            message = f"Error on upload: {e}"
            ok = False

        return AddDocumentsToCorpus(message=message, ok=ok)


class RemoveDocumentsFromCorpus(graphene.Mutation):
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
        ok = False
        message = "Success"

        try:
            user = info.context.user
            doc_pks = list(
                map(
                    lambda graphene_id: from_global_id(graphene_id)[1],
                    document_ids_to_remove,
                )
            )
            corpus = Corpus.objects.get(
                Q(pk=from_global_id(corpus_id)[1])
                & (Q(creator=user) | Q(is_public=True))
            )
            corpus_docs = corpus.documents.filter(pk__in=doc_pks)
            corpus.documents.remove(*corpus_docs)
            ok = True

        except Exception as e:
            message = f"Error on upload: {e}"
            ok = False

        return RemoveDocumentsFromCorpus(message=message, ok=ok)


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
    class Arguments:
        corpus_id = graphene.String(
            required=True,
            description="Graphene id of the corpus you want to package for export",
        )

    ok = graphene.Boolean()
    message = graphene.String()
    new_corpus = graphene.Field(CorpusType)

    @login_required
    def mutate(root, info, corpus_id):

        ok = False
        message = ""
        new_corpus = None

        try:

            # Get annotation ids for the old corpus - these refer to a corpus, doc and label by id, so easaiest way to
            # copy these is to first filter by annotations for our corpus. Then, later, we'll use a dict to map old ids
            # for labels and docs to new obj ids
            corpus_pk = from_global_id(corpus_id)[1]
            annotation_ids = list(
                Annotation.objects.filter(
                    corpus_id=corpus_pk,
                    analysis__isnull=True,
                ).values_list("id", flat=True)
            )

            # Get corpus obj
            corpus = Corpus.objects.get(pk=corpus_pk)

            # Get ids to related objects that need copyin'
            doc_ids = list(corpus.documents.all().values_list("id", flat=True))
            label_set_id = corpus.label_set.pk if corpus.label_set else None

            # Clone the corpus: https://docs.djangoproject.com/en/3.1/topics/db/queries/copying-model-instances
            corpus.pk = None

            # Adjust the title to indicate it's a fork
            corpus.title = f"{corpus.title}"

            # lock the corpus which will tell frontend to show this as loading and disable selection
            corpus.backend_lock = True
            corpus.creator = info.context.user  # switch the creator to the current user
            corpus.parent_id = corpus_pk
            corpus.save()

            set_permissions_for_obj_to_user(
                info.context.user, corpus, [PermissionTypes.CRUD]
            )

            # Now remove references to related objects on our new object, as these point to original docs and labels
            corpus.documents.clear()
            corpus.label_set = None

            # Copy docs and annotations using async task to avoid massive lag if we have large dataset or lots of
            # users requesting copies.
            fork_corpus.si(
                corpus.id, doc_ids, label_set_id, annotation_ids, info.context.user.id
            ).apply_async()

        except Exception as e:
            message = f"Error trying to fork corpus with id {corpus_id}: {e}"
            logger.error(message)

        return StartCorpusFork(ok=ok, message=message, new_corpus=new_corpus)


class StartQueryForCorpus(graphene.Mutation):
    class Arguments:
        corpus_id = graphene.String(
            required=True,
            description="Graphene id of the corpus you want to package for export",
        )
        query = graphene.String(
            required=True,
            description="What is the question the user wants an answer to?",
        )

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(CorpusQueryType)

    @login_required
    def mutate(root, info, corpus_id, query):

        obj = None
        ok = False
        message = "SUCCESS!"
        # Enforce sane limits on free / rando users. Can be overriden.
        try:
            if (
                info.context.user.is_usage_capped
                and CorpusQuery.objects.filter(creator=info.context.user).count() > 10
            ):
                raise PermissionError(
                    "By default, new users are limited to 10 queries. Please contact the admin to "
                    "upgrade your account."
                )

            obj = CorpusQuery.objects.create(
                query=query,
                creator=info.context.user,
                corpus_id=from_global_id(corpus_id)[1],
            )
            # print(f"Obj created: {obj}")
            set_permissions_for_obj_to_user(
                info.context.user, obj, [PermissionTypes.CRUD]
            )
            ok = True
        except Exception as e:
            message = f"Error asking query: {e}"

        return StartQueryForCorpus(ok=ok, obj=obj, message=message)


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
        make_public = graphene.Boolean(
            required=True,
            description="If True, document is immediately public. "
            "Defaults to False.",
        )

    ok = graphene.Boolean()
    message = graphene.String()
    document = graphene.Field(DocumentType)

    @login_required
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
                    file_type=kind,  # Store filetype
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
                )
                document.save()

            set_permissions_for_obj_to_user(user, document, [PermissionTypes.CRUD])

            # Handle linking to corpus or extract
            if add_to_corpus_id is not None:
                try:
                    corpus = Corpus.objects.get(id=from_global_id(add_to_corpus_id)[1])
                    transaction.on_commit(lambda: corpus.documents.add(document))
                except Exception as e:
                    message = f"Adding to corpus failed due to error: {e}"
            elif add_to_extract_id is not None:
                try:
                    extract = Extract.objects.get(
                        Q(pk=from_global_id(add_to_extract_id)[1])
                        & (Q(creator=user) | Q(is_public=True))
                    )
                    if extract.finished is not None:
                        raise ValueError("Cannot add document to a finished extract")
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

    @login_required
    def mutate(root, info, annotation_id):
        annotation_pk = from_global_id(annotation_id)[1]
        annotation_obj = Annotation.objects.get(pk=annotation_pk)
        annotation_obj.delete()

        return RemoveAnnotation(ok=True)


class RejectAnnotation(graphene.Mutation):
    class Arguments:
        annotation_id = graphene.ID(
            required=True, description="ID of the annotation to reject"
        )
        comment = graphene.String(description="Optional comment for the rejection")

    ok = graphene.Boolean()
    user_feedback = graphene.Field(UserFeedbackType)

    @login_required
    @transaction.atomic
    def mutate(root, info, annotation_id, comment=None):
        user = info.context.user
        annotation_pk = from_global_id(annotation_id)[1]

        try:
            annotation = Annotation.objects.get(pk=annotation_pk)
        except ObjectDoesNotExist:
            return RejectAnnotation(ok=False, user_feedback=None)

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

        return RejectAnnotation(ok=True, user_feedback=user_feedback)


class ApproveAnnotation(graphene.Mutation):
    class Arguments:
        annotation_id = graphene.ID(
            required=True, description="ID of the annotation to approve"
        )
        comment = graphene.String(description="Optional comment for the approval")

    ok = graphene.Boolean()
    user_feedback = graphene.Field(UserFeedbackType)

    @login_required
    @transaction.atomic
    def mutate(root, info, annotation_id, comment=None):
        user = info.context.user
        annotation_pk = from_global_id(annotation_id)[1]

        try:
            annotation = Annotation.objects.get(pk=annotation_pk)
        except ObjectDoesNotExist:
            return ApproveAnnotation(ok=False, user_feedback=None)

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

        return ApproveAnnotation(ok=True, user_feedback=user_feedback)


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

    @login_required
    def mutate(root, info, relationship_id):
        relationship_pk = from_global_id(relationship_id)[1]
        relationship_obj = Relationship.objects.get(pk=relationship_pk)
        relationship_obj.delete()

        return RemoveRelationship(ok=True)


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

        return AddRelationship(ok=True, relationship=relationship)


class RemoveRelationships(graphene.Mutation):
    class Arguments:
        relationship_ids = graphene.List(graphene.String)

    ok = graphene.Boolean()

    @login_required
    def mutate(root, info, relationship_ids):
        relation_pks = list(
            map(lambda graphene_id: from_global_id(graphene_id)[1], relationship_ids)
        )
        Relationship.objects.filter(id__in=relation_pks).delete()
        return RemoveRelationships(ok=True)


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

    @login_required
    def mutate(root, info, relationships):
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

            relationship = Relationship.objects.get(id=pk)
            relationship.relationship_label_id = relationship_label_pk
            relationship.document_id = document_pk
            relationship.corpus_id = corpus_pk
            relationship.save()

            relationship.target_annotations.set(target_pks)
            relationship.source_annotations.set(source_pks)

        return UpdateRelations(ok=True)


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
        try:
            label_pks = list(
                map(
                    lambda label_id: from_global_id(label_id)[1],
                    annotation_label_ids_to_delete,
                )
            )
            labels = AnnotationLabel.objects.filter(pk__in=label_pks)
            labels.delete()
            ok = True
            message = "Success"

        except Exception as e:
            ok = False
            message = f"Delete failed due to error: {e}"

        return DeleteMultipleLabelMutation(ok=ok, message=message)


class CreateCorpusMutation(DRFMutation):
    class IOSettings:
        pk_fields = ["label_set"]
        serializer = CorpusSerializer
        model = Corpus
        graphene_model = CorpusType

    class Arguments:
        title = graphene.String(required=False)
        description = graphene.String(required=False)
        icon = graphene.String(required=False)
        label_set = graphene.String(required=False)
        preferred_embedder = graphene.String(required=False)


class UpdateCorpusMutation(DRFMutation):
    class IOSettings:
        lookup_field = "id"
        pk_fields = ["label_set"]
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

        document_pk = from_global_id(document_id)[1] if document_id else None
        analyzer_pk = from_global_id(analyzer_id)[1]
        corpus_pk = from_global_id(corpus_id)[1] if corpus_id else None

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

            analysis = process_analyzer(
                user_id=user.id,
                analyzer=analyzer,
                corpus_id=corpus_pk,
                document_ids=[document_pk] if document_pk else None,
                corpus_action=None,
                analysis_input_data=analysis_input_data,
            )

            return StartDocumentAnalysisMutation(
                ok=True, message="SUCCESS", obj=analysis
            )
        except Exception as e:
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

        document = Document.objects.get(pk=doc_pk)
        fieldset = Fieldset.objects.get(pk=fieldset_pk)

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
        run_extract.s(extract.id, info.context.user.id).apply_async()

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
        run_extract.s(pk, info.context.user.id).apply_async()

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
            # print(f"Try to add corpus docs: {corpus.documents.all()}")
            extract.documents.add(*corpus.documents.all())
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
    The action can either run a fieldset extraction or an analyzer, but not both.
    Requires UPDATE permission on the corpus to create actions.
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
        disabled: bool = False,
        run_on_all_corpuses: bool = False,
    ):
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

            # Validate that exactly one of fieldset_id or analyzer_id is provided
            if bool(fieldset_id) == bool(analyzer_id):
                return CreateCorpusAction(
                    ok=False,
                    message="Exactly one of fieldset_id or analyzer_id must be provided",
                    obj=None,
                )

            # Get fieldset or analyzer if provided
            fieldset = None
            analyzer = None

            if fieldset_id:
                fieldset_pk = from_global_id(fieldset_id)[1]
                fieldset = Fieldset.objects.get(pk=fieldset_pk)

            if analyzer_id:
                analyzer_pk = from_global_id(analyzer_id)[1]
                analyzer = Analyzer.objects.get(pk=analyzer_pk)
                # Analyzers don't have permissions currently, but we could add them here if needed

            # Create the corpus action
            corpus_action = CorpusAction.objects.create(
                name=name or "Corpus Action",
                corpus=corpus,
                fieldset=fieldset,
                analyzer=analyzer,
                trigger=trigger,
                disabled=disabled,
                run_on_all_corpuses=run_on_all_corpuses,
                creator=user,
            )

            set_permissions_for_obj_to_user(user, corpus_action, [PermissionTypes.CRUD])

            return CreateCorpusAction(
                ok=True, message="Successfully created corpus action", obj=corpus_action
            )

        except Exception as e:
            return CreateCorpusAction(
                ok=False, message=f"Failed to create corpus action: {str(e)}", obj=None
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
    update_relationships = UpdateRelations.Field()

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

    # DOCUMENT MUTATIONS #######################################################
    upload_document = UploadDocument.Field()  # Limited by user.is_usage_capped
    update_document = UpdateDocument.Field()
    update_document_summary = UpdateDocumentSummary.Field()
    delete_document = DeleteDocument.Field()
    delete_multiple_documents = DeleteMultipleDocuments.Field()
    upload_documents_zip = UploadDocumentsZip.Field()  # Bulk document upload via zip

    # CORPUS MUTATIONS #########################################################
    fork_corpus = StartCorpusFork.Field()
    make_corpus_public = MakeCorpusPublic.Field()
    create_corpus = CreateCorpusMutation.Field()
    update_corpus = UpdateCorpusMutation.Field()
    update_corpus_description = UpdateCorpusDescription.Field()
    delete_corpus = DeleteCorpusMutation.Field()
    link_documents_to_corpus = AddDocumentsToCorpus.Field()
    remove_documents_from_corpus = RemoveDocumentsFromCorpus.Field()
    create_corpus_action = CreateCorpusAction.Field()
    delete_corpus_action = DeleteCorpusAction.Field()

    # IMPORT MUTATIONS #########################################################
    import_open_contracts_zip = UploadCorpusImportZip.Field()
    import_annotated_doc_to_corpus = UploadAnnotatedDocument.Field()

    # EXPORT MUTATIONS #########################################################
    export_corpus = StartCorpusExport.Field()  # Limited by user.is_usage_capped
    delete_export = DeleteExport.Field()

    # ANALYSIS MUTATIONS #########################################################
    start_analysis_on_doc = StartDocumentAnalysisMutation.Field()
    delete_analysis = DeleteAnalysisMutation.Field()
    make_analysis_public = MakeAnalysisPublic.Field()

    # QUERY MUTATIONS #########################################################
    ask_query = StartQueryForCorpus.Field()

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
