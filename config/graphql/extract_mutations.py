"""
GraphQL mutations for extract, fieldset, column, datacell, and metadata operations.
"""

import logging
import uuid

import graphene
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from graphene.types.generic import GenericScalar
from graphql_jwt.decorators import login_required
from graphql_relay import from_global_id

from config.graphql.base import DRFDeletion, DRFMutation
from config.graphql.graphene_types import (
    ColumnType,
    DatacellType,
    DocumentType,
    ExtractType,
    FieldsetType,
)
from config.telemetry import record_event
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.extracts.models import Column, Datacell, Extract, Fieldset
from opencontractserver.tasks.extract_orchestrator_tasks import run_extract
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import (
    set_permissions_for_obj_to_user,
    user_has_permission_for_obj,
)

logger = logging.getLogger(__name__)


class ApproveDatacell(graphene.Mutation):
    # NOTE(deferred): Datacell-level permissions would add significant overhead.
    # Current approach relies on parent corpus/extract permissions.

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
    # NOTE(deferred): Datacell-level permissions would add significant overhead.
    # Current approach relies on parent corpus/extract permissions.

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
    # NOTE(deferred): Datacell-level permissions would add significant overhead.
    # Current approach relies on parent corpus/extract permissions.

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
    """Set a metadata value for a document.

    Permission model:
    - Requires Corpus UPDATE permission + Document READ permission
    - Metadata is a corpus-level feature, so corpus permission controls editing
    - Uses MetadataQueryOptimizer for consistent permission checking
    """

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

        from opencontractserver.extracts.query_optimizer import MetadataQueryOptimizer
        from opencontractserver.types.enums import PermissionTypes
        from opencontractserver.utils.permissioning import (
            set_permissions_for_obj_to_user,
        )

        try:
            user = info.context.user
            local_doc_id = int(from_global_id(document_id)[1])
            local_corpus_id = int(from_global_id(corpus_id)[1])
            local_column_id = int(from_global_id(column_id)[1])

            # Check permissions: Corpus UPDATE + Document READ
            has_perm, error_msg = (
                MetadataQueryOptimizer.check_metadata_mutation_permission(
                    user, local_doc_id, local_corpus_id, "UPDATE"
                )
            )
            if not has_perm:
                return SetMetadataValue(ok=False, message=error_msg)

            # Validate column belongs to corpus metadata schema
            is_valid, error_msg, column = (
                MetadataQueryOptimizer.validate_metadata_column(
                    local_column_id, local_corpus_id
                )
            )
            if not is_valid:
                return SetMetadataValue(ok=False, message=error_msg)

            # Get document for foreign key
            document = Document.objects.get(pk=local_doc_id)

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

        except Document.DoesNotExist:
            return SetMetadataValue(ok=False, message="Document not found")
        except Exception as e:
            return SetMetadataValue(
                ok=False, message=f"Error setting metadata value: {str(e)}"
            )


class DeleteMetadataValue(graphene.Mutation):
    """Delete a metadata value for a document.

    Permission model:
    - Requires Corpus DELETE permission + Document READ permission
    - Metadata is a corpus-level feature, so corpus permission controls deletion
    - Uses MetadataQueryOptimizer for consistent permission checking
    """

    class Arguments:
        document_id = graphene.ID(required=True)
        corpus_id = graphene.ID(required=True)
        column_id = graphene.ID(required=True)

    ok = graphene.Boolean()
    message = graphene.String()

    @login_required
    def mutate(root, info, document_id, corpus_id, column_id):
        from opencontractserver.extracts.query_optimizer import MetadataQueryOptimizer

        try:
            user = info.context.user
            local_doc_id = int(from_global_id(document_id)[1])
            local_corpus_id = int(from_global_id(corpus_id)[1])
            local_column_id = int(from_global_id(column_id)[1])

            # Check document + corpus permissions using optimizer (MIN logic)
            has_perm, error_msg = (
                MetadataQueryOptimizer.check_metadata_mutation_permission(
                    user, local_doc_id, local_corpus_id, "DELETE"
                )
            )
            if not has_perm:
                return DeleteMetadataValue(ok=False, message=error_msg)

            # Validate column belongs to corpus metadata schema
            is_valid, error_msg, column = (
                MetadataQueryOptimizer.validate_metadata_column(
                    local_column_id, local_corpus_id
                )
            )
            if not is_valid:
                return DeleteMetadataValue(ok=False, message=error_msg)

            # Get document for lookup
            document = Document.objects.get(pk=local_doc_id)

            # Find and delete the datacell
            datacell = Datacell.objects.get(document=document, column=column)
            datacell.delete()

            return DeleteMetadataValue(
                ok=True, message="Metadata value deleted successfully"
            )

        except Document.DoesNotExist:
            return DeleteMetadataValue(ok=False, message="Document not found")
        except Datacell.DoesNotExist:
            return DeleteMetadataValue(ok=False, message="Metadata value not found")
        except Exception as e:
            return DeleteMetadataValue(
                ok=False, message=f"Error deleting metadata value: {str(e)}"
            )


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

        fieldset = Fieldset.objects.visible_to_user(info.context.user).get(
            pk=from_global_id(fieldset_id)[1]
        )
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
            try:
                corpus = Corpus.objects.visible_to_user(info.context.user).get(
                    pk=corpus_pk
                )
            except Corpus.DoesNotExist:
                return CreateExtract(
                    ok=False,
                    msg="You don't have permission to create an extract for this corpus.",
                    obj=None,
                )

        if fieldset_id is not None:
            fieldset = Fieldset.objects.visible_to_user(info.context.user).get(
                pk=from_global_id(fieldset_id)[1]
            )
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
            try:
                corpus = Corpus.objects.visible_to_user(info.context.user).get(
                    pk=corpus_pk
                )
            except Corpus.DoesNotExist:
                return StartDocumentExtract(
                    ok=False, message="Resource not found", obj=None
                )

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
