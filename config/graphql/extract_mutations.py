"""
GraphQL mutations for extract, fieldset, column, datacell, and metadata operations.
"""

import logging
import uuid
from typing import Optional

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
from opencontractserver.corpuses.services import CorpusDocumentService
from opencontractserver.documents.models import Document
from opencontractserver.extracts.models import Column, Datacell, Extract, Fieldset
from opencontractserver.tasks.extract_orchestrator_tasks import run_extract
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import (
    get_for_user_or_none,
    set_permissions_for_obj_to_user,
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
    def mutate(root, info, datacell_id) -> "ApproveDatacell":

        ok = True
        obj = None
        message = "SUCCESS!"

        try:
            pk = from_global_id(datacell_id)[1]
            obj = Datacell.objects.get(pk=pk, creator=info.context.user)
            obj.approved_by = info.context.user
            obj.rejected_by = None
            obj.save()

        except Datacell.DoesNotExist:
            ok = False
            message = "Datacell not found."
        except Exception:
            # Don't leak ORM/constraint text to the caller; log server-side.
            # logger.exception() captures the traceback automatically.
            logger.exception("Error approving datacell")
            ok = False
            message = "Failed to approve datacell."

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
    def mutate(root, info, datacell_id) -> "RejectDatacell":

        ok = True
        obj = None
        message = "SUCCESS!"

        try:
            pk = from_global_id(datacell_id)[1]
            obj = Datacell.objects.get(pk=pk, creator=info.context.user)
            obj.rejected_by = info.context.user
            obj.approved_by = None
            obj.save()

        except Datacell.DoesNotExist:
            ok = False
            message = "Datacell not found."
        except Exception:
            logger.exception("Error rejecting datacell")
            ok = False
            message = "Failed to reject datacell."

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
    def mutate(root, info, datacell_id, edited_data) -> "EditDatacell":

        ok = True
        obj = None
        message = "SUCCESS!"

        try:
            pk = from_global_id(datacell_id)[1]
            obj = Datacell.objects.get(pk=pk, creator=info.context.user)
            obj.corrected_data = edited_data
            obj.save()

        except Datacell.DoesNotExist:
            ok = False
            message = "Datacell not found."
        except Exception:
            logger.exception("Error editing datacell")
            ok = False
            message = "Failed to edit datacell."

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
    ) -> "CreateMetadataColumn":
        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.types.enums import PermissionTypes
        from opencontractserver.utils.permissioning import (
            set_permissions_for_obj_to_user,
        )

        # Unified message blocks IDOR enumeration: same response whether the
        # corpus does not exist or the caller lacks UPDATE permission.
        not_found_msg = "Corpus not found or you do not have permission to update it."

        try:
            user = info.context.user
            try:
                corpus = Corpus.objects.visible_to_user(user).get(
                    pk=from_global_id(corpus_id)[1]
                )
            except Corpus.DoesNotExist:
                return CreateMetadataColumn(ok=False, message=not_found_msg)

            # Check permissions
            if not corpus.user_can(user, PermissionTypes.UPDATE, request=info.context):
                return CreateMetadataColumn(ok=False, message=not_found_msg)

            # Get or create metadata fieldset for corpus
            if not hasattr(corpus, "metadata_schema") or corpus.metadata_schema is None:
                fieldset = Fieldset.objects.create(
                    name=f"{corpus.title} Metadata",
                    description=f"Metadata schema for {corpus.title}",
                    corpus=corpus,
                    creator=user,
                )
                set_permissions_for_obj_to_user(
                    user,
                    fieldset,
                    [PermissionTypes.CRUD],
                    is_new=True,
                    request=info.context,
                )
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

            set_permissions_for_obj_to_user(
                user,
                column,
                [PermissionTypes.CRUD],
                is_new=True,
                request=info.context,
            )

            return CreateMetadataColumn(
                ok=True, message="Metadata field created successfully", obj=column
            )

        except Exception:
            # Don't surface ORM/constraint text — log and return a generic
            # message. Corpus.DoesNotExist is handled in the inner try above
            # to keep the IDOR-safe response path unified.
            logger.exception("Error creating metadata field")
            return CreateMetadataColumn(
                ok=False, message="Error creating metadata field."
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
    def mutate(root, info, column_id, **kwargs) -> "UpdateMetadataColumn":
        from opencontractserver.types.enums import PermissionTypes

        # Unified message blocks IDOR enumeration: same response whether the
        # column does not exist or the caller lacks UPDATE permission.
        not_found_msg = "Column not found or you do not have permission to update it."

        try:
            user = info.context.user
            try:
                column = Column.objects.visible_to_user(user).get(
                    pk=from_global_id(column_id)[1]
                )
            except Column.DoesNotExist:
                return UpdateMetadataColumn(ok=False, message=not_found_msg)

            # Check permissions
            if not column.user_can(user, PermissionTypes.UPDATE, request=info.context):
                return UpdateMetadataColumn(ok=False, message=not_found_msg)

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

        except Exception:
            logger.exception("Error updating metadata field")
            return UpdateMetadataColumn(
                ok=False, message="Error updating metadata field."
            )


class SetMetadataValue(graphene.Mutation):
    """Set a metadata value for a document.

    Permission model:
    - Requires Corpus UPDATE permission + Document READ permission
    - Metadata is a corpus-level feature, so corpus permission controls editing
    - Uses MetadataService for consistent permission checking
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
    def mutate(
        root, info, document_id, corpus_id, column_id, value
    ) -> "SetMetadataValue":
        from django.utils import timezone

        from opencontractserver.extracts.services import MetadataService
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
            has_perm, error_msg = MetadataService.check_metadata_mutation_permission(
                user, local_doc_id, local_corpus_id, "UPDATE"
            )
            if not has_perm:
                return SetMetadataValue(ok=False, message=error_msg)

            # Validate column belongs to corpus metadata schema
            is_valid, error_msg, column = MetadataService.validate_metadata_column(
                local_column_id, local_corpus_id
            )
            if not is_valid or column is None:
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
                set_permissions_for_obj_to_user(
                    user,
                    datacell,
                    [PermissionTypes.CRUD],
                    is_new=True,
                    request=info.context,
                )

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
    - Uses MetadataService for consistent permission checking
    """

    class Arguments:
        document_id = graphene.ID(required=True)
        corpus_id = graphene.ID(required=True)
        column_id = graphene.ID(required=True)

    ok = graphene.Boolean()
    message = graphene.String()

    @login_required
    def mutate(root, info, document_id, corpus_id, column_id) -> "DeleteMetadataValue":
        from opencontractserver.extracts.services import MetadataService

        try:
            user = info.context.user
            local_doc_id = int(from_global_id(document_id)[1])
            local_corpus_id = int(from_global_id(corpus_id)[1])
            local_column_id = int(from_global_id(column_id)[1])

            # Check document + corpus permissions using optimizer (MIN logic)
            has_perm, error_msg = MetadataService.check_metadata_mutation_permission(
                user, local_doc_id, local_corpus_id, "DELETE"
            )
            if not has_perm:
                return DeleteMetadataValue(ok=False, message=error_msg)

            # Validate column belongs to corpus metadata schema
            is_valid, error_msg, column = MetadataService.validate_metadata_column(
                local_column_id, local_corpus_id
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
    def mutate(root, info, name, description) -> "CreateFieldset":
        fieldset = Fieldset(
            name=name,
            description=description,
            creator=info.context.user,
        )
        fieldset.save()
        set_permissions_for_obj_to_user(
            info.context.user,
            fieldset,
            [PermissionTypes.CRUD],
            is_new=True,
            request=info.context,
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
        must_contain_text=None,
    ) -> "UpdateColumnMutation":

        ok = False
        message = ""
        obj = None

        try:
            pk = from_global_id(id)[1]
            obj = Column.objects.get(pk=pk, creator=info.context.user)

            if task_name is not None:
                obj.task_name = task_name

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
    ) -> "CreateColumn":
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
            info.context.user,
            column,
            [PermissionTypes.CRUD],
            is_new=True,
            request=info.context,
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
    def mutate(root, info, id) -> "DeleteColumn":
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
    def mutate(root, info, extract_id) -> "StartExtract":
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
    ) -> "CreateExtract":

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
                info.context.user,
                fieldset,
                [PermissionTypes.CRUD],
                is_new=True,
                request=info.context,
            )

        extract = Extract(
            corpus=corpus,
            name=name,
            fieldset=fieldset,
            creator=info.context.user,
        )
        extract.save()

        if corpus is not None:
            # Route through the canonical service so corpus READ is enforced
            # against the requesting user before the mass-add (the create
            # mutation already gated on corpus access upstream; this just
            # keeps the data path through one entry point).
            extract.documents.add(
                *CorpusDocumentService.get_corpus_documents(
                    user=info.context.user, corpus=corpus
                )
            )
        else:
            logger.info("Corpus IS still None... no docs to add.")

        set_permissions_for_obj_to_user(
            info.context.user,
            extract,
            [PermissionTypes.CRUD],
            is_new=True,
            request=info.context,
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
    ) -> "UpdateExtractMutation":
        user = info.context.user

        # Unified message blocks IDOR enumeration: same response whether the
        # extract doesn't exist or the caller lacks UPDATE permission.
        extract_not_found_msg = (
            "Extract not found or you don't have permission to update it."
        )

        try:
            extract_pk = from_global_id(id)[1]
        except Exception:
            return UpdateExtractMutation(
                ok=False, message=extract_not_found_msg, obj=None
            )

        extract = get_for_user_or_none(Extract, extract_pk, user)
        if extract is None or not extract.user_can(
            user, PermissionTypes.UPDATE, request=info.context
        ):
            return UpdateExtractMutation(
                ok=False, message=extract_not_found_msg, obj=None
            )

        # Update fields
        if title is not None:
            extract.name = title

        if error is not None:
            extract.error = error

        if corpus_id is not None:
            try:
                corpus_pk = from_global_id(corpus_id)[1]
            except Exception:
                return UpdateExtractMutation(
                    ok=False,
                    message="Corpus not found or you don't have permission to use it.",
                    obj=None,
                )
            corpus = get_for_user_or_none(Corpus, corpus_pk, user)
            if corpus is None:
                return UpdateExtractMutation(
                    ok=False,
                    message="Corpus not found or you don't have permission to use it.",
                    obj=None,
                )
            extract.corpus = corpus

        if fieldset_id is not None:
            try:
                fieldset_pk = from_global_id(fieldset_id)[1]
            except Exception:
                return UpdateExtractMutation(
                    ok=False,
                    message=(
                        "Fieldset not found or you don't have permission to use it."
                    ),
                    obj=None,
                )
            fieldset = get_for_user_or_none(Fieldset, fieldset_pk, user)
            if fieldset is None:
                return UpdateExtractMutation(
                    ok=False,
                    message=(
                        "Fieldset not found or you don't have permission to use it."
                    ),
                    obj=None,
                )
            extract.fieldset = fieldset

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
    def mutate(root, info, extract_id, document_ids) -> "AddDocumentsToExtract":

        ok = False
        doc_objs: list[Document] = []

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
            doc_objs = list(
                Document.objects.filter(
                    Q(pk__in=doc_pks) & (Q(creator=user) | Q(is_public=True))
                )
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
    def mutate(
        root, info, extract_id, document_ids_to_remove
    ) -> "RemoveDocumentsFromExtract":

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
    def mutate(
        root, info, document_id, fieldset_id, corpus_id=None
    ) -> "StartDocumentExtract":
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


# ---------------------------------------------------------------------------
# Iteration support — CreateExtractIteration
# ---------------------------------------------------------------------------

# Iteration axes. Kept as a small Enum so the frontend can render dedicated
# affordances per axis without leaking field-level details into UI logic.
EXTRACT_ITERATION_AXES = ("MODEL", "DOCUMENT_VERSIONS", "FIELDSET")


def _clone_fieldset_for_iteration(
    source_fieldset: Fieldset,
    user,
    column_overrides: Optional[dict] = None,
    *,
    request=None,
) -> Fieldset:
    """Deep-clone a fieldset and its columns for a FIELDSET-axis iteration.

    ``column_overrides`` maps source-column global ids to a dict of fields
    to override on the cloned column (e.g. updated query/instructions/output_type).
    """
    new_fieldset = Fieldset.objects.create(
        name=f"{source_fieldset.name} (iteration)",
        description=source_fieldset.description,
        creator=user,
    )
    set_permissions_for_obj_to_user(
        user, new_fieldset, [PermissionTypes.CRUD], is_new=True, request=request
    )

    overrides_by_pk: dict = {}
    if column_overrides:
        for gid, payload in column_overrides.items():
            try:
                overrides_by_pk[int(from_global_id(gid)[1])] = payload or {}
            except Exception:
                # Silently skip bad ids; the iteration should still proceed
                # with un-overridden clones rather than 500.
                continue

    for column in source_fieldset.columns.all():
        overrides = overrides_by_pk.get(column.pk, {})
        clone = Column.objects.create(
            fieldset=new_fieldset,
            name=overrides.get("name", column.name),
            query=overrides.get("query", column.query),
            match_text=overrides.get("match_text", column.match_text),
            must_contain_text=overrides.get(
                "must_contain_text", column.must_contain_text
            ),
            output_type=overrides.get("output_type", column.output_type),
            limit_to_label=overrides.get("limit_to_label", column.limit_to_label),
            instructions=overrides.get("instructions", column.instructions),
            extract_is_list=overrides.get("extract_is_list", column.extract_is_list),
            task_name=overrides.get("task_name", column.task_name),
            data_type=column.data_type,
            validation_config=column.validation_config,
            is_manual_entry=column.is_manual_entry,
            default_value=column.default_value,
            help_text=column.help_text,
            display_order=column.display_order,
            creator=user,
        )
        set_permissions_for_obj_to_user(
            user, clone, [PermissionTypes.CRUD], is_new=True, request=request
        )
    return new_fieldset


def _resolve_iteration_documents(source_extract: Extract, axis: str):
    """Pick the document set for a new iteration.

    - DOCUMENT_VERSIONS: re-resolve every doc in the parent to the *current*
      Document in its ``version_tree_id`` so the iteration runs against the
      latest content.
    - All other axes: keep the parent's exact pinned Document PKs so the
      diff is apples-to-apples.
    """
    parent_docs = list(source_extract.documents.all())
    if axis != "DOCUMENT_VERSIONS":
        return parent_docs

    tree_ids = [d.version_tree_id for d in parent_docs if d.version_tree_id]
    if not tree_ids:
        return parent_docs
    current_by_tree = {
        d.version_tree_id: d
        for d in Document.objects.filter(version_tree_id__in=tree_ids, is_current=True)
    }
    # Fall back to the original Document if no current row exists for a tree
    # (e.g. soft-deleted) so the iteration set always matches the parent shape.
    return [current_by_tree.get(d.version_tree_id, d) for d in parent_docs]


class CreateExtractIteration(graphene.Mutation):
    """Fork an existing Extract into a new iteration along a single axis.

    Three axes are supported, mirroring the three eval workflows:
      * ``MODEL`` — same fieldset + same documents, new model_config.
      * ``DOCUMENT_VERSIONS`` — same fieldset + same model_config, but each
        document is replaced by the current row in its version tree.
      * ``FIELDSET`` — clone the fieldset (with optional per-column
        overrides), keep documents + model_config.

    The new extract has ``parent_extract`` set to the source so the UI can
    walk the iteration series. If ``auto_start`` is true the standard
    ``run_extract`` task is queued exactly as ``StartExtract`` would.
    """

    class Arguments:
        source_extract_id = graphene.ID(required=True)
        axis = graphene.String(
            required=True, description="One of MODEL | DOCUMENT_VERSIONS | FIELDSET"
        )
        name = graphene.String(
            required=False,
            description="Optional name for the new iteration; defaults to "
            "'<source name> (iteration N)'.",
        )
        model_config = GenericScalar(
            required=False,
            description="Run-time model config to capture on the new "
            "iteration. If omitted, parent's config is reused.",
        )
        column_overrides = GenericScalar(
            required=False,
            description="FIELDSET-axis only: { '<column global id>': { "
            "'query': '...', 'instructions': '...', ... } }.",
        )
        auto_start = graphene.Boolean(
            required=False,
            description="If true, queue run_extract for the new iteration.",
        )

    ok = graphene.Boolean()
    message = graphene.String()
    obj = graphene.Field(ExtractType)

    @staticmethod
    @login_required
    def mutate(
        root,
        info,
        source_extract_id,
        axis,
        name=None,
        model_config=None,
        column_overrides=None,
        auto_start=False,
    ) -> "CreateExtractIteration":
        user = info.context.user

        if axis not in EXTRACT_ITERATION_AXES:
            return CreateExtractIteration(
                ok=False,
                message=(f"axis must be one of {', '.join(EXTRACT_ITERATION_AXES)}"),
            )

        # Unified message blocks IDOR enumeration: same response whether the
        # source extract doesn't exist or the caller lacks READ permission.
        source_not_found_msg = (
            "Source extract not found or you don't have permission to read it."
        )

        try:
            source_pk = int(from_global_id(source_extract_id)[1])
        except (TypeError, ValueError):
            return CreateExtractIteration(ok=False, message=source_not_found_msg)

        source = get_for_user_or_none(Extract, source_pk, user)
        if source is None:
            return CreateExtractIteration(ok=False, message=source_not_found_msg)

        # Pick a fieldset based on axis: clone for FIELDSET, share otherwise.
        # Shared fieldsets are the right call for MODEL/DOC drift testing
        # because we want the column definitions to stay byte-identical.
        if axis == "FIELDSET":
            new_fieldset = _clone_fieldset_for_iteration(
                source.fieldset,
                user,
                column_overrides=column_overrides,
                request=info.context,
            )
        else:
            new_fieldset = source.fieldset

        # Compute a default name as "<source> (iteration N)" where N counts
        # existing siblings + the source itself, so users can't easily
        # collide names by repeated forking.
        if not name:
            sibling_count = Extract.objects.filter(parent_extract=source).count()
            name = f"{source.name} (iteration {sibling_count + 1})"

        # Inherit parent model_config when caller didn't supply one. We deep-
        # copy via dict() so subsequent edits to the parent don't leak in.
        effective_model_config = (
            dict(model_config)
            if model_config is not None
            else dict(source.model_config or {})
        )

        with transaction.atomic():
            new_extract = Extract.objects.create(
                corpus=source.corpus,
                name=name,
                fieldset=new_fieldset,
                creator=user,
                parent_extract=source,
                model_config=effective_model_config,
            )
            new_extract.documents.set(_resolve_iteration_documents(source, axis))
            set_permissions_for_obj_to_user(
                user,
                new_extract,
                [PermissionTypes.CRUD],
                is_new=True,
                request=info.context,
            )

        if auto_start:
            new_extract.started = timezone.now()
            new_extract.save(update_fields=["started"])
            transaction.on_commit(
                lambda: run_extract.s(new_extract.id, user.id).apply_async()
            )

        record_event(
            "extract_iteration_created",
            {
                "env": settings.MODE,
                "user_id": user.id,
                "axis": axis,
                "auto_start": bool(auto_start),
            },
        )

        return CreateExtractIteration(
            ok=True, message="Iteration created.", obj=new_extract
        )
