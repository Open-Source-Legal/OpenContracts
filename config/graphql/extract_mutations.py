"""Generated strawberry GraphQL module (graphene migration).

Shape-generated from the graphene schema; stub functions marked PORT(...)
carry the ported business logic. See config/graphql_new/manifest.json.
"""

# mypy: disable-error-code="name-defined, valid-type, arg-type"
#   Code-generation artifacts of the strawberry schema bindings that
#   mypy's static pass cannot resolve, NOT real typing defects:
#     name-defined / valid-type — ``Annotated["XType", strawberry.lazy(...)]``
#       forward-reference strings + the runtime-generated ``*Connection``
#       types (``make_connection_types``).
#     arg-type — resolvers construct result types with ``to_global_id()``
#       (``str``) for ``strawberry.ID`` fields and return Django MODEL
#       instances where the field annotation names the strawberry type
#       (the graphene-django resolver contract). Both are correct at
#       runtime. Hand-written config/graphql/core/* stays fully checked.
# flake8: noqa: E501, F821 — generated strawberry schema module.
# E501: long GraphQL field/argument ``description=`` strings and the
# single-line generated resolver signatures (black cannot split string
# literals). F821: ``Annotated["XType", strawberry.lazy(...)]`` /
# ``cast("QuerySet", ...)`` forward-reference STRINGS that pyflakes
# resolves as names — the whole point of strawberry.lazy is to avoid the
# import (which would then be F401). Both are code-generation artifacts,
# not defects; hand-written modules (config/graphql/core/*, security.py,
# testing.py, filters.py, …) stay fully linted.

from __future__ import annotations

import logging
import uuid
from typing import Annotated

import strawberry
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from graphql_relay import from_global_id

from config.graphql._util import strip_unset
from config.graphql.core.auth import PermissionDenied
from config.graphql.core.mutations import drf_deletion
from config.graphql.core.relay import (
    register_type,
)
from config.graphql.core.scalars import GenericScalar
from config.telemetry import record_event
from opencontractserver.corpuses.models import Corpus
from opencontractserver.corpuses.services import CorpusDocumentService
from opencontractserver.documents.models import Document
from opencontractserver.extracts.models import Column, Datacell, Extract, Fieldset
from opencontractserver.shared.services.base import BaseService
from opencontractserver.tasks.extract_orchestrator_tasks import run_extract
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import (
    get_for_user_or_none,
    set_permissions_for_obj_to_user,
)

logger = logging.getLogger(__name__)


def _get_metadata_column_with_corpus(
    column_id: str, user, request
) -> tuple[Column | None, Corpus | None]:
    """READ-gated lookup of a metadata ``Column`` plus its parent ``Corpus``.

    Metadata columns are corpus-scoped objects (reached via
    ``Fieldset.corpus``), so mutations that write to them must authorize
    against the parent corpus, not the child ``Column`` — see
    ``UpdateMetadataColumn``/``DeleteMetadataColumn``, both of which use this
    helper so the corpus-scoped gate can't drift back to a column-scoped one
    in only one of them.

    ``select_related("fieldset__corpus")`` fetches the column, its fieldset,
    and the corpus in a single query instead of two extra lazy round-trips.

    Returns ``(None, None)`` when the column is not visible to ``user`` or
    its fieldset has no linked corpus (a fieldset's ``corpus`` FK is
    nullable). Both cases collapse to the caller's unified "not found or no
    permission" response — an orphaned fieldset has no corpus to authorize
    a write against, so it is treated the same as "not found" rather than
    surfacing a distinct error that would aid enumeration.
    """
    pk = from_global_id(column_id)[1]
    column = (
        BaseService.filter_visible(Column, user, request=request)
        .select_related("fieldset__corpus")
        .filter(pk=pk)
        .first()
    )
    if column is None or column.fieldset.corpus is None:
        return None, None
    return column, column.fieldset.corpus


# ---------------------------------------------------------------------------
# Iteration support — CreateExtractIteration
# ---------------------------------------------------------------------------

# Iteration axes. Kept as a small Enum so the frontend can render dedicated
# affordances per axis without leaking field-level details into UI logic.
EXTRACT_ITERATION_AXES = ("MODEL", "DOCUMENT_VERSIONS", "FIELDSET")


def _clone_fieldset_for_iteration(
    source_fieldset: Fieldset,
    user,
    column_overrides: dict | None = None,
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


@strawberry.type(name="CreateFieldset")
class CreateFieldset:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    obj: None | (
        Annotated[FieldsetType, strawberry.lazy("config.graphql.extract_types")]
    ) = strawberry.field(name="obj", default=None)


register_type("CreateFieldset", CreateFieldset, model=None)


@strawberry.type(
    name="UpdateFieldset",
    description="Rename / re-describe a fieldset the caller may UPDATE.",
)
class UpdateFieldset:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    obj: None | (
        Annotated[FieldsetType, strawberry.lazy("config.graphql.extract_types")]
    ) = strawberry.field(name="obj", default=None)


register_type("UpdateFieldset", UpdateFieldset, model=None)


@strawberry.type(name="CreateColumn")
class CreateColumn:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    obj: None | (
        Annotated[ColumnType, strawberry.lazy("config.graphql.extract_types")]
    ) = strawberry.field(name="obj", default=None)


register_type("CreateColumn", CreateColumn, model=None)


@strawberry.type(name="UpdateColumnMutation")
class UpdateColumnMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    obj_id: strawberry.ID | None = strawberry.field(name="objId", default=None)
    obj: None | (
        Annotated[ColumnType, strawberry.lazy("config.graphql.extract_types")]
    ) = strawberry.field(name="obj", default=None)


register_type("UpdateColumnMutation", UpdateColumnMutation, model=None)


@strawberry.type(name="DeleteColumn")
class DeleteColumn:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    deleted_id: str | None = strawberry.field(name="deletedId", default=None)


register_type("DeleteColumn", DeleteColumn, model=None)


@strawberry.type(
    name="CreateExtract",
    description='Create a new extract. If fieldset_id is provided, attach existing fieldset.\nOtherwise, a new fieldset is created. If no name is provided, fieldset name has\nform "[Extract name] Fieldset"',
)
class CreateExtract:
    ok: bool | None = strawberry.field(name="ok", default=None)
    msg: str | None = strawberry.field(name="msg", default=None)
    obj: None | (
        Annotated[ExtractType, strawberry.lazy("config.graphql.extract_types")]
    ) = strawberry.field(name="obj", default=None)


register_type("CreateExtract", CreateExtract, model=None)


@strawberry.type(
    name="CreateExtractIteration",
    description="Fork an existing Extract into a new iteration along a single axis.\n\nThree axes are supported, mirroring the three eval workflows:\n  * ``MODEL`` — same fieldset + same documents, new model_config.\n  * ``DOCUMENT_VERSIONS`` — same fieldset + same model_config, but each\n    document is replaced by the current row in its version tree.\n  * ``FIELDSET`` — clone the fieldset (with optional per-column\n    overrides), keep documents + model_config.\n\nThe new extract has ``parent_extract`` set to the source so the UI can\nwalk the iteration series. If ``auto_start`` is true the standard\n``run_extract`` task is queued exactly as ``StartExtract`` would.",
)
class CreateExtractIteration:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    obj: None | (
        Annotated[ExtractType, strawberry.lazy("config.graphql.extract_types")]
    ) = strawberry.field(name="obj", default=None)


register_type("CreateExtractIteration", CreateExtractIteration, model=None)


@strawberry.type(name="StartExtract")
class StartExtract:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    obj: None | (
        Annotated[ExtractType, strawberry.lazy("config.graphql.extract_types")]
    ) = strawberry.field(name="obj", default=None)


register_type("StartExtract", StartExtract, model=None)


@strawberry.type(name="DeleteExtract")
class DeleteExtract:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)


register_type("DeleteExtract", DeleteExtract, model=None)


@strawberry.type(
    name="UpdateExtractMutation",
    description="Mutation to update an existing Extract object.\n\nSupports updating the name (title), corpus, fieldset, and error fields.\nEnsures proper permission checks are applied.",
)
class UpdateExtractMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    obj: None | (
        Annotated[ExtractType, strawberry.lazy("config.graphql.extract_types")]
    ) = strawberry.field(name="obj", default=None)


register_type("UpdateExtractMutation", UpdateExtractMutation, model=None)


@strawberry.type(name="AddDocumentsToExtract")
class AddDocumentsToExtract:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    obj_id: strawberry.ID | None = strawberry.field(name="objId", default=None)
    objs: None | (
        list[
            None
            | (
                Annotated[
                    DocumentType, strawberry.lazy("config.graphql.document_types")
                ]
            )
        ]
    ) = strawberry.field(name="objs", default=None)


register_type("AddDocumentsToExtract", AddDocumentsToExtract, model=None)


@strawberry.type(name="RemoveDocumentsFromExtract")
class RemoveDocumentsFromExtract:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    ids_removed: list[str | None] | None = strawberry.field(
        name="idsRemoved", default=None
    )


register_type("RemoveDocumentsFromExtract", RemoveDocumentsFromExtract, model=None)


@strawberry.type(name="ApproveDatacell")
class ApproveDatacell:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    obj: None | (
        Annotated[DatacellType, strawberry.lazy("config.graphql.extract_types")]
    ) = strawberry.field(name="obj", default=None)


register_type("ApproveDatacell", ApproveDatacell, model=None)


@strawberry.type(name="RejectDatacell")
class RejectDatacell:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    obj: None | (
        Annotated[DatacellType, strawberry.lazy("config.graphql.extract_types")]
    ) = strawberry.field(name="obj", default=None)


register_type("RejectDatacell", RejectDatacell, model=None)


@strawberry.type(name="EditDatacell")
class EditDatacell:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    obj: None | (
        Annotated[DatacellType, strawberry.lazy("config.graphql.extract_types")]
    ) = strawberry.field(name="obj", default=None)


register_type("EditDatacell", EditDatacell, model=None)


@strawberry.type(name="StartDocumentExtract")
class StartDocumentExtract:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    obj: None | (
        Annotated[ExtractType, strawberry.lazy("config.graphql.extract_types")]
    ) = strawberry.field(name="obj", default=None)


register_type("StartDocumentExtract", StartDocumentExtract, model=None)


@strawberry.type(
    name="CreateMetadataColumn", description="Create a metadata column for a corpus."
)
class CreateMetadataColumn:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    obj: None | (
        Annotated[ColumnType, strawberry.lazy("config.graphql.extract_types")]
    ) = strawberry.field(name="obj", default=None)


register_type("CreateMetadataColumn", CreateMetadataColumn, model=None)


@strawberry.type(name="UpdateMetadataColumn", description="Update a metadata column.")
class UpdateMetadataColumn:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    obj: None | (
        Annotated[ColumnType, strawberry.lazy("config.graphql.extract_types")]
    ) = strawberry.field(name="obj", default=None)


register_type("UpdateMetadataColumn", UpdateMetadataColumn, model=None)


@strawberry.type(
    name="DeleteMetadataColumn",
    description="Delete a manual-entry metadata column definition (values cascade).",
)
class DeleteMetadataColumn:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)


register_type("DeleteMetadataColumn", DeleteMetadataColumn, model=None)


@strawberry.type(
    name="SetMetadataValue",
    description="Set a metadata value for a document.\n\nPermission model:\n- Requires Corpus UPDATE permission + Document READ permission\n- Metadata is a corpus-level feature, so corpus permission controls editing\n- Uses MetadataService for consistent permission checking",
)
class SetMetadataValue:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    obj: None | (
        Annotated[DatacellType, strawberry.lazy("config.graphql.extract_types")]
    ) = strawberry.field(name="obj", default=None)


register_type("SetMetadataValue", SetMetadataValue, model=None)


@strawberry.type(
    name="DeleteMetadataValue",
    description="Delete a metadata value for a document.\n\nPermission model:\n- Requires Corpus DELETE permission + Document READ permission\n- Metadata is a corpus-level feature, so corpus permission controls deletion\n- Uses MetadataService for consistent permission checking",
)
class DeleteMetadataValue:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)


register_type("DeleteMetadataValue", DeleteMetadataValue, model=None)


def _mutate_CreateFieldset(payload_cls, root, info, name, description):
    """PORT: config.graphql.extract_mutations.CreateFieldset.mutate

    Port of CreateFieldset.mutate
    """
    # @login_required (graphql_jwt) — inlined because mutate stubs take
    # ``payload_cls`` as their first positional argument, which does not
    # match core.auth's ``(root, info, ...)`` calling convention.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

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

    return payload_cls(ok=True, message="SUCCESS!", obj=fieldset)


def m_create_fieldset(
    info: strawberry.Info,
    description: Annotated[
        str, strawberry.argument(name="description")
    ] = strawberry.UNSET,
    name: Annotated[str, strawberry.argument(name="name")] = strawberry.UNSET,
) -> CreateFieldset | None:
    kwargs = strip_unset({"description": description, "name": name})
    return _mutate_CreateFieldset(CreateFieldset, None, info, **kwargs)


def _mutate_UpdateFieldset(payload_cls, root, info, id, name=None, description=None):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:656

    Port of UpdateFieldset.mutate
    """
    # @login_required (graphql_jwt) — inlined; see _mutate_CreateFieldset.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    # Unified message blocks IDOR enumeration: same response whether the
    # fieldset does not exist or the caller lacks UPDATE permission.
    not_found_msg = "Fieldset not found or you do not have permission to update it."

    try:
        user = info.context.user
        fieldset = BaseService.get_or_none(
            Fieldset, from_global_id(id)[1], user, request=info.context
        )
        # require_permission returns "" on grant and a non-empty error
        # string on denial, so a truthy result means "denied". Guard the
        # None case first to avoid calling require_permission on a missing
        # object.
        if fieldset is None:
            return payload_cls(ok=False, message=not_found_msg)
        if BaseService.require_permission(
            fieldset, user, PermissionTypes.UPDATE, request=info.context
        ):
            return payload_cls(ok=False, message=not_found_msg)

        if name is not None:
            fieldset.name = name
        if description is not None:
            fieldset.description = description
        fieldset.save()

        return payload_cls(ok=True, message="SUCCESS!", obj=fieldset)

    except Exception:
        logger.exception("Error updating fieldset")
        return payload_cls(ok=False, message="Error updating fieldset.")


def m_update_fieldset(
    info: strawberry.Info,
    description: Annotated[
        str | None, strawberry.argument(name="description")
    ] = strawberry.UNSET,
    id: Annotated[strawberry.ID, strawberry.argument(name="id")] = strawberry.UNSET,
    name: Annotated[str | None, strawberry.argument(name="name")] = strawberry.UNSET,
) -> UpdateFieldset | None:
    kwargs = strip_unset({"description": description, "id": id, "name": name})
    return _mutate_UpdateFieldset(UpdateFieldset, None, info, **kwargs)


def _mutate_CreateColumn(
    payload_cls,
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
    """PORT: config.graphql.extract_mutations.CreateColumn.mutate

    Port of CreateColumn.mutate
    """
    # @login_required (graphql_jwt) — inlined; see _mutate_CreateFieldset.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    if {query, match_text} == {None}:
        raise ValueError("One of `query` or `match_text` must be provided.")

    fieldset = BaseService.get_or_none(
        Fieldset,
        from_global_id(fieldset_id)[1],
        info.context.user,
        request=info.context,
    )
    if fieldset is None:
        raise Fieldset.DoesNotExist
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
    return payload_cls(ok=True, message="SUCCESS!", obj=column)


def m_create_column(
    info: strawberry.Info,
    extract_is_list: Annotated[
        bool | None, strawberry.argument(name="extractIsList")
    ] = strawberry.UNSET,
    fieldset_id: Annotated[
        strawberry.ID, strawberry.argument(name="fieldsetId")
    ] = strawberry.UNSET,
    instructions: Annotated[
        str | None, strawberry.argument(name="instructions")
    ] = strawberry.UNSET,
    limit_to_label: Annotated[
        str | None, strawberry.argument(name="limitToLabel")
    ] = strawberry.UNSET,
    match_text: Annotated[
        str | None, strawberry.argument(name="matchText")
    ] = strawberry.UNSET,
    must_contain_text: Annotated[
        str | None, strawberry.argument(name="mustContainText")
    ] = strawberry.UNSET,
    name: Annotated[str, strawberry.argument(name="name")] = strawberry.UNSET,
    output_type: Annotated[
        str, strawberry.argument(name="outputType")
    ] = strawberry.UNSET,
    query: Annotated[str | None, strawberry.argument(name="query")] = strawberry.UNSET,
    task_name: Annotated[
        str | None, strawberry.argument(name="taskName")
    ] = strawberry.UNSET,
) -> CreateColumn | None:
    kwargs = strip_unset(
        {
            "extract_is_list": extract_is_list,
            "fieldset_id": fieldset_id,
            "instructions": instructions,
            "limit_to_label": limit_to_label,
            "match_text": match_text,
            "must_contain_text": must_contain_text,
            "name": name,
            "output_type": output_type,
            "query": query,
            "task_name": task_name,
        }
    )
    return _mutate_CreateColumn(CreateColumn, None, info, **kwargs)


def _mutate_UpdateColumnMutation(
    payload_cls,
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
    fieldset_id=None,
):
    """PORT: config.graphql.extract_mutations.UpdateColumnMutation.mutate

    Port of UpdateColumnMutation.mutate
    """
    # @login_required (graphql_jwt) — inlined; see _mutate_CreateFieldset.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

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

    return payload_cls(ok=ok, message=message, obj=obj)


def m_update_column(
    info: strawberry.Info,
    extract_is_list: Annotated[
        bool | None, strawberry.argument(name="extractIsList")
    ] = strawberry.UNSET,
    fieldset_id: Annotated[
        strawberry.ID | None, strawberry.argument(name="fieldsetId")
    ] = strawberry.UNSET,
    id: Annotated[strawberry.ID, strawberry.argument(name="id")] = strawberry.UNSET,
    instructions: Annotated[
        str | None, strawberry.argument(name="instructions")
    ] = strawberry.UNSET,
    limit_to_label: Annotated[
        str | None, strawberry.argument(name="limitToLabel")
    ] = strawberry.UNSET,
    match_text: Annotated[
        str | None, strawberry.argument(name="matchText")
    ] = strawberry.UNSET,
    must_contain_text: Annotated[
        str | None, strawberry.argument(name="mustContainText")
    ] = strawberry.UNSET,
    name: Annotated[str | None, strawberry.argument(name="name")] = strawberry.UNSET,
    output_type: Annotated[
        str | None, strawberry.argument(name="outputType")
    ] = strawberry.UNSET,
    query: Annotated[str | None, strawberry.argument(name="query")] = strawberry.UNSET,
    task_name: Annotated[
        str | None, strawberry.argument(name="taskName")
    ] = strawberry.UNSET,
) -> UpdateColumnMutation | None:
    kwargs = strip_unset(
        {
            "extract_is_list": extract_is_list,
            "fieldset_id": fieldset_id,
            "id": id,
            "instructions": instructions,
            "limit_to_label": limit_to_label,
            "match_text": match_text,
            "must_contain_text": must_contain_text,
            "name": name,
            "output_type": output_type,
            "query": query,
            "task_name": task_name,
        }
    )
    return _mutate_UpdateColumnMutation(UpdateColumnMutation, None, info, **kwargs)


def _mutate_DeleteColumn(payload_cls, root, info, id):
    """PORT: config.graphql.extract_mutations.DeleteColumn.mutate

    Port of DeleteColumn.mutate
    """
    # @login_required (graphql_jwt) — inlined; see _mutate_CreateFieldset.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    Column.objects.get(pk=from_global_id(id)[1], creator=info.context.user).delete()
    return payload_cls(ok=True, message="STARTED!", deleted_id=id)


def m_delete_column(
    info: strawberry.Info,
    id: Annotated[strawberry.ID, strawberry.argument(name="id")] = strawberry.UNSET,
) -> DeleteColumn | None:
    kwargs = strip_unset({"id": id})
    return _mutate_DeleteColumn(DeleteColumn, None, info, **kwargs)


def _mutate_CreateExtract(
    payload_cls,
    root,
    info,
    name,
    corpus_id=None,
    fieldset_id=None,
    fieldset_name=None,
    fieldset_description=None,
):
    """PORT: config.graphql.extract_mutations.CreateExtract.mutate

    Port of CreateExtract.mutate
    """
    # @login_required (graphql_jwt) — inlined; see _mutate_CreateFieldset.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    corpus = None
    if corpus_id is not None:
        corpus_pk = from_global_id(corpus_id)[1]
        corpus = BaseService.get_or_none(
            Corpus, corpus_pk, info.context.user, request=info.context
        )
        if corpus is None:
            return payload_cls(
                ok=False,
                msg="You don't have permission to create an extract for this corpus.",
                obj=None,
            )

    if fieldset_id is not None:
        fieldset = BaseService.get_or_none(
            Fieldset,
            from_global_id(fieldset_id)[1],
            info.context.user,
            request=info.context,
        )
        if fieldset is None:
            raise Fieldset.DoesNotExist
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

    return payload_cls(ok=True, msg="SUCCESS!", obj=extract)


def m_create_extract(
    info: strawberry.Info,
    corpus_id: Annotated[
        strawberry.ID | None, strawberry.argument(name="corpusId")
    ] = strawberry.UNSET,
    fieldset_description: Annotated[
        str | None, strawberry.argument(name="fieldsetDescription")
    ] = strawberry.UNSET,
    fieldset_id: Annotated[
        strawberry.ID | None, strawberry.argument(name="fieldsetId")
    ] = strawberry.UNSET,
    fieldset_name: Annotated[
        str | None, strawberry.argument(name="fieldsetName")
    ] = strawberry.UNSET,
    name: Annotated[str, strawberry.argument(name="name")] = strawberry.UNSET,
) -> CreateExtract | None:
    kwargs = strip_unset(
        {
            "corpus_id": corpus_id,
            "fieldset_description": fieldset_description,
            "fieldset_id": fieldset_id,
            "fieldset_name": fieldset_name,
            "name": name,
        }
    )
    return _mutate_CreateExtract(CreateExtract, None, info, **kwargs)


def _mutate_CreateExtractIteration(
    payload_cls,
    root,
    info,
    source_extract_id,
    axis,
    name=None,
    model_config=None,
    column_overrides=None,
    auto_start=False,
):
    """PORT: config.graphql.extract_mutations.CreateExtractIteration.mutate

    Port of CreateExtractIteration.mutate
    """
    # @login_required (graphql_jwt) — inlined; see _mutate_CreateFieldset.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    user = info.context.user

    if axis not in EXTRACT_ITERATION_AXES:
        return payload_cls(
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
        return payload_cls(ok=False, message=source_not_found_msg)

    source = get_for_user_or_none(Extract, source_pk, user)
    if source is None:
        return payload_cls(ok=False, message=source_not_found_msg)

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

    return payload_cls(ok=True, message="Iteration created.", obj=new_extract)


def m_create_extract_iteration(
    info: strawberry.Info,
    auto_start: Annotated[
        bool | None,
        strawberry.argument(
            name="autoStart",
            description="If true, queue run_extract for the new iteration.",
        ),
    ] = strawberry.UNSET,
    axis: Annotated[
        str,
        strawberry.argument(
            name="axis", description="One of MODEL | DOCUMENT_VERSIONS | FIELDSET"
        ),
    ] = strawberry.UNSET,
    column_overrides: Annotated[
        GenericScalar | None,
        strawberry.argument(
            name="columnOverrides",
            description="FIELDSET-axis only: { '<column global id>': { 'query': '...', 'instructions': '...', ... } }.",
        ),
    ] = strawberry.UNSET,
    model_config: Annotated[
        GenericScalar | None,
        strawberry.argument(
            name="modelConfig",
            description="Run-time model config to capture on the new iteration. If omitted, parent's config is reused.",
        ),
    ] = strawberry.UNSET,
    name: Annotated[
        str | None,
        strawberry.argument(
            name="name",
            description="Optional name for the new iteration; defaults to '<source name> (iteration N)'.",
        ),
    ] = strawberry.UNSET,
    source_extract_id: Annotated[
        strawberry.ID, strawberry.argument(name="sourceExtractId")
    ] = strawberry.UNSET,
) -> CreateExtractIteration | None:
    kwargs = strip_unset(
        {
            "auto_start": auto_start,
            "axis": axis,
            "column_overrides": column_overrides,
            "model_config": model_config,
            "name": name,
            "source_extract_id": source_extract_id,
        }
    )
    return _mutate_CreateExtractIteration(CreateExtractIteration, None, info, **kwargs)


def _mutate_StartExtract(payload_cls, root, info, extract_id):
    """PORT: config.graphql.extract_mutations.StartExtract.mutate

    Port of StartExtract.mutate
    """
    # @login_required (graphql_jwt) — inlined; see _mutate_CreateFieldset.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    # Start celery task to process extract
    pk = from_global_id(extract_id)[1]
    extract = Extract.objects.get(pk=pk, creator=info.context.user)
    extract.started = timezone.now()
    extract.save()
    transaction.on_commit(lambda: run_extract.s(pk, info.context.user.id).apply_async())

    record_event(
        "extract_started",
        {
            "env": settings.MODE,
            "user_id": info.context.user.id,
        },
    )

    return payload_cls(ok=True, message="STARTED!", obj=extract)


def m_start_extract(
    info: strawberry.Info,
    extract_id: Annotated[
        strawberry.ID, strawberry.argument(name="extractId")
    ] = strawberry.UNSET,
) -> StartExtract | None:
    kwargs = strip_unset({"extract_id": extract_id})
    return _mutate_StartExtract(StartExtract, None, info, **kwargs)


def m_delete_extract(
    info: strawberry.Info,
    id: Annotated[str, strawberry.argument(name="id")] = strawberry.UNSET,
) -> DeleteExtract | None:
    kwargs = strip_unset({"id": id})
    return drf_deletion(
        payload_cls=DeleteExtract,
        model=Extract,
        lookup_field="id",
        root=None,
        info=info,
        kwargs=kwargs,
    )


def _mutate_UpdateExtractMutation(
    payload_cls,
    root,
    info,
    id,
    title=None,
    corpus_id=None,
    fieldset_id=None,
    error=None,
):
    """PORT: config.graphql.extract_mutations.UpdateExtractMutation.mutate

    Port of UpdateExtractMutation.mutate
    """
    # @login_required (graphql_jwt) — inlined; see _mutate_CreateFieldset.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    user = info.context.user

    # Unified message blocks IDOR enumeration: same response whether the
    # extract doesn't exist or the caller lacks UPDATE permission.
    extract_not_found_msg = (
        "Extract not found or you don't have permission to update it."
    )

    try:
        extract_pk = from_global_id(id)[1]
    except Exception:
        return payload_cls(ok=False, message=extract_not_found_msg, obj=None)

    extract = get_for_user_or_none(Extract, extract_pk, user)
    if extract is None or BaseService.require_permission(
        extract, user, PermissionTypes.UPDATE, request=info.context
    ):
        return payload_cls(ok=False, message=extract_not_found_msg, obj=None)

    # Update fields
    if title is not None:
        extract.name = title

    if error is not None:
        extract.error = error

    if corpus_id is not None:
        try:
            corpus_pk = from_global_id(corpus_id)[1]
        except Exception:
            return payload_cls(
                ok=False,
                message="Corpus not found or you don't have permission to use it.",
                obj=None,
            )
        corpus = get_for_user_or_none(Corpus, corpus_pk, user)
        if corpus is None:
            return payload_cls(
                ok=False,
                message="Corpus not found or you don't have permission to use it.",
                obj=None,
            )
        extract.corpus = corpus

    if fieldset_id is not None:
        try:
            fieldset_pk = from_global_id(fieldset_id)[1]
        except Exception:
            return payload_cls(
                ok=False,
                message=("Fieldset not found or you don't have permission to use it."),
                obj=None,
            )
        fieldset = get_for_user_or_none(Fieldset, fieldset_pk, user)
        if fieldset is None:
            return payload_cls(
                ok=False,
                message=("Fieldset not found or you don't have permission to use it."),
                obj=None,
            )
        extract.fieldset = fieldset

    extract.save()
    extract.refresh_from_db()

    return payload_cls(ok=True, message="Extract updated successfully.", obj=extract)


def m_update_extract(
    info: strawberry.Info,
    corpus_id: Annotated[
        strawberry.ID | None,
        strawberry.argument(
            name="corpusId",
            description="ID of the Corpus to associate with the Extract.",
        ),
    ] = strawberry.UNSET,
    error: Annotated[
        str | None,
        strawberry.argument(
            name="error", description="Error message to update on the Extract."
        ),
    ] = strawberry.UNSET,
    fieldset_id: Annotated[
        strawberry.ID | None,
        strawberry.argument(
            name="fieldsetId",
            description="ID of the Fieldset to associate with the Extract.",
        ),
    ] = strawberry.UNSET,
    id: Annotated[
        strawberry.ID,
        strawberry.argument(name="id", description="ID of the Extract to update."),
    ] = strawberry.UNSET,
    title: Annotated[
        str | None,
        strawberry.argument(name="title", description="New title for the Extract."),
    ] = strawberry.UNSET,
) -> UpdateExtractMutation | None:
    kwargs = strip_unset(
        {
            "corpus_id": corpus_id,
            "error": error,
            "fieldset_id": fieldset_id,
            "id": id,
            "title": title,
        }
    )
    return _mutate_UpdateExtractMutation(UpdateExtractMutation, None, info, **kwargs)


def _mutate_AddDocumentsToExtract(payload_cls, root, info, extract_id, document_ids):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:1121

    Port of AddDocumentsToExtract.mutate
    """
    # @login_required (graphql_jwt) — inlined; see _mutate_CreateFieldset.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    ok = False
    doc_objs: list[Document] = []

    try:
        user = info.context.user

        extract = Extract.objects.get(
            Q(pk=from_global_id(extract_id)[1]) & (Q(creator=user) | Q(is_public=True))
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

    return payload_cls(message=message, ok=ok, objs=doc_objs)


def m_add_docs_to_extract(
    info: strawberry.Info,
    document_ids: Annotated[
        list[strawberry.ID | None],
        strawberry.argument(
            name="documentIds",
            description="List of ids of the documents to add to extract.",
        ),
    ] = strawberry.UNSET,
    extract_id: Annotated[
        strawberry.ID,
        strawberry.argument(
            name="extractId", description="Id of corpus to add docs to."
        ),
    ] = strawberry.UNSET,
) -> AddDocumentsToExtract | None:
    kwargs = strip_unset({"document_ids": document_ids, "extract_id": extract_id})
    return _mutate_AddDocumentsToExtract(AddDocumentsToExtract, None, info, **kwargs)


def _mutate_RemoveDocumentsFromExtract(
    payload_cls, root, info, extract_id, document_ids_to_remove
):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:1175

    Port of RemoveDocumentsFromExtract.mutate
    """
    # @login_required (graphql_jwt) — inlined; see _mutate_CreateFieldset.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    ok = False

    try:
        user = info.context.user
        extract = Extract.objects.get(
            Q(pk=from_global_id(extract_id)[1]) & (Q(creator=user) | Q(is_public=True))
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

    return payload_cls(message=message, ok=ok, ids_removed=document_ids_to_remove)


def m_remove_docs_from_extract(
    info: strawberry.Info,
    document_ids_to_remove: Annotated[
        list[strawberry.ID | None],
        strawberry.argument(
            name="documentIdsToRemove",
            description="List of ids of the docs to remove from extract.",
        ),
    ] = strawberry.UNSET,
    extract_id: Annotated[
        strawberry.ID,
        strawberry.argument(
            name="extractId", description="ID of extract to remove documents from."
        ),
    ] = strawberry.UNSET,
) -> RemoveDocumentsFromExtract | None:
    kwargs = strip_unset(
        {"document_ids_to_remove": document_ids_to_remove, "extract_id": extract_id}
    )
    return _mutate_RemoveDocumentsFromExtract(
        RemoveDocumentsFromExtract, None, info, **kwargs
    )


def _mutate_ApproveDatacell(payload_cls, root, info, datacell_id):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:87

    Port of ApproveDatacell.mutate
    """
    # NOTE(deferred): Datacell-level permissions would add significant overhead.
    # Current approach relies on parent corpus/extract permissions.
    # @login_required (graphql_jwt) — inlined; see _mutate_CreateFieldset.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

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

    return payload_cls(ok=ok, obj=obj, message=message)


def m_approve_datacell(
    info: strawberry.Info,
    datacell_id: Annotated[
        str, strawberry.argument(name="datacellId")
    ] = strawberry.UNSET,
) -> ApproveDatacell | None:
    kwargs = strip_unset({"datacell_id": datacell_id})
    return _mutate_ApproveDatacell(ApproveDatacell, None, info, **kwargs)


def _mutate_RejectDatacell(payload_cls, root, info, datacell_id):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:125

    Port of RejectDatacell.mutate
    """
    # NOTE(deferred): Datacell-level permissions would add significant overhead.
    # Current approach relies on parent corpus/extract permissions.
    # @login_required (graphql_jwt) — inlined; see _mutate_CreateFieldset.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

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

    return payload_cls(ok=ok, obj=obj, message=message)


def m_reject_datacell(
    info: strawberry.Info,
    datacell_id: Annotated[
        str, strawberry.argument(name="datacellId")
    ] = strawberry.UNSET,
) -> RejectDatacell | None:
    kwargs = strip_unset({"datacell_id": datacell_id})
    return _mutate_RejectDatacell(RejectDatacell, None, info, **kwargs)


def _mutate_EditDatacell(payload_cls, root, info, datacell_id, edited_data):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:162

    Port of EditDatacell.mutate
    """
    # NOTE(deferred): Datacell-level permissions would add significant overhead.
    # Current approach relies on parent corpus/extract permissions.
    # @login_required (graphql_jwt) — inlined; see _mutate_CreateFieldset.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

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

    return payload_cls(ok=ok, obj=obj, message=message)


def m_edit_datacell(
    info: strawberry.Info,
    datacell_id: Annotated[
        str, strawberry.argument(name="datacellId")
    ] = strawberry.UNSET,
    edited_data: Annotated[
        GenericScalar, strawberry.argument(name="editedData")
    ] = strawberry.UNSET,
) -> EditDatacell | None:
    kwargs = strip_unset({"datacell_id": datacell_id, "edited_data": edited_data})
    return _mutate_EditDatacell(EditDatacell, None, info, **kwargs)


def _mutate_StartDocumentExtract(
    payload_cls, root, info, document_id, fieldset_id, corpus_id=None
):
    """PORT: config.graphql.extract_mutations.StartDocumentExtract.mutate

    Port of StartDocumentExtract.mutate
    """
    # @login_required (graphql_jwt) — inlined; see _mutate_CreateFieldset.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    doc_pk = from_global_id(document_id)[1]
    fieldset_pk = from_global_id(fieldset_id)[1]

    # Verify visibility for both document and fieldset via service layer.
    document = BaseService.get_or_none(
        Document, doc_pk, info.context.user, request=info.context
    )
    fieldset = BaseService.get_or_none(
        Fieldset, fieldset_pk, info.context.user, request=info.context
    )
    if document is None or fieldset is None:
        return payload_cls(ok=False, message="Resource not found", obj=None)

    corpus = None
    if corpus_id:
        corpus_pk = from_global_id(corpus_id)[1]
        corpus = BaseService.get_or_none(
            Corpus, corpus_pk, info.context.user, request=info.context
        )
        if corpus is None:
            return payload_cls(ok=False, message="Resource not found", obj=None)

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

    return payload_cls(ok=True, message="STARTED!", obj=extract)


def m_start_extract_for_doc(
    info: strawberry.Info,
    corpus_id: Annotated[
        strawberry.ID | None, strawberry.argument(name="corpusId")
    ] = strawberry.UNSET,
    document_id: Annotated[
        strawberry.ID, strawberry.argument(name="documentId")
    ] = strawberry.UNSET,
    fieldset_id: Annotated[
        strawberry.ID, strawberry.argument(name="fieldsetId")
    ] = strawberry.UNSET,
) -> StartDocumentExtract | None:
    kwargs = strip_unset(
        {"corpus_id": corpus_id, "document_id": document_id, "fieldset_id": fieldset_id}
    )
    return _mutate_StartDocumentExtract(StartDocumentExtract, None, info, **kwargs)


def _mutate_CreateMetadataColumn(
    payload_cls,
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
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:206

    Port of CreateMetadataColumn.mutate
    """
    # @login_required (graphql_jwt) — inlined; see _mutate_CreateFieldset.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    # Unified message blocks IDOR enumeration: same response whether the
    # corpus does not exist or the caller lacks UPDATE permission.
    not_found_msg = "Corpus not found or you do not have permission to update it."

    try:
        user = info.context.user
        corpus = BaseService.get_or_none(
            Corpus, from_global_id(corpus_id)[1], user, request=info.context
        )
        if corpus is None or BaseService.require_permission(
            corpus, user, PermissionTypes.UPDATE, request=info.context
        ):
            return payload_cls(ok=False, message=not_found_msg)

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
            return payload_cls(
                ok=False,
                message=f"Invalid data type. Must be one of: {', '.join(valid_types)}",
            )

        # Validate choice fields
        if data_type in ["CHOICE", "MULTI_CHOICE"]:
            if not validation_config or "choices" not in validation_config:
                return payload_cls(
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

        return payload_cls(
            ok=True, message="Metadata field created successfully", obj=column
        )

    except Exception:
        # Don't surface ORM/constraint text — log and return a generic
        # message. Corpus.DoesNotExist is handled in the inner try above
        # to keep the IDOR-safe response path unified.
        logger.exception("Error creating metadata field")
        return payload_cls(ok=False, message="Error creating metadata field.")


def m_create_metadata_column(
    info: strawberry.Info,
    corpus_id: Annotated[
        strawberry.ID,
        strawberry.argument(name="corpusId", description="ID of the corpus"),
    ] = strawberry.UNSET,
    data_type: Annotated[
        str, strawberry.argument(name="dataType", description="Data type of the field")
    ] = strawberry.UNSET,
    default_value: Annotated[
        GenericScalar | None,
        strawberry.argument(name="defaultValue", description="Default value"),
    ] = strawberry.UNSET,
    display_order: Annotated[
        int | None,
        strawberry.argument(name="displayOrder", description="Display order"),
    ] = strawberry.UNSET,
    help_text: Annotated[
        str | None,
        strawberry.argument(name="helpText", description="Help text for the field"),
    ] = strawberry.UNSET,
    name: Annotated[
        str, strawberry.argument(name="name", description="Name of the metadata field")
    ] = strawberry.UNSET,
    validation_config: Annotated[
        GenericScalar | None,
        strawberry.argument(
            name="validationConfig", description="Validation configuration"
        ),
    ] = strawberry.UNSET,
) -> CreateMetadataColumn | None:
    kwargs = strip_unset(
        {
            "corpus_id": corpus_id,
            "data_type": data_type,
            "default_value": default_value,
            "display_order": display_order,
            "help_text": help_text,
            "name": name,
            "validation_config": validation_config,
        }
    )
    return _mutate_CreateMetadataColumn(CreateMetadataColumn, None, info, **kwargs)


def _mutate_UpdateMetadataColumn(payload_cls, root, info, column_id, **kwargs):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:336

    Port of UpdateMetadataColumn.mutate
    """
    # @login_required (graphql_jwt) — inlined; see _mutate_CreateFieldset.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    # Unified message blocks IDOR enumeration: same response whether the
    # column does not exist or the caller lacks UPDATE permission.
    not_found_msg = "Column not found or you do not have permission to update it."

    try:
        user = info.context.user
        # READ-gate the column lookup through the service layer, then
        # authorize the write against the parent corpus (not the child
        # Column) so a creator/direct Column grant can't outlive corpus
        # permissions. Mirrors DeleteMetadataColumn — metadata schemas
        # are corpus-scoped objects.
        column, corpus = _get_metadata_column_with_corpus(column_id, user, info.context)
        if column is None or corpus is None:
            return payload_cls(ok=False, message=not_found_msg)

        if BaseService.require_permission(
            corpus, user, PermissionTypes.UPDATE, request=info.context
        ):
            return payload_cls(ok=False, message=not_found_msg)

        # Ensure it's a manual entry column
        if not column.is_manual_entry:
            return payload_cls(
                ok=False, message="Only manual entry columns can be updated"
            )

        # Update fields
        if "name" in kwargs:
            column.name = kwargs["name"]
        if "validation_config" in kwargs:
            # Validate choice fields
            if column.data_type in ["CHOICE", "MULTI_CHOICE"]:
                if "choices" not in kwargs["validation_config"]:
                    return payload_cls(
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

        return payload_cls(
            ok=True, message="Metadata field updated successfully", obj=column
        )

    except Exception:
        logger.exception("Error updating metadata field")
        return payload_cls(ok=False, message="Error updating metadata field.")


def m_update_metadata_column(
    info: strawberry.Info,
    column_id: Annotated[
        strawberry.ID, strawberry.argument(name="columnId")
    ] = strawberry.UNSET,
    default_value: Annotated[
        GenericScalar | None, strawberry.argument(name="defaultValue")
    ] = strawberry.UNSET,
    display_order: Annotated[
        int | None, strawberry.argument(name="displayOrder")
    ] = strawberry.UNSET,
    help_text: Annotated[
        str | None, strawberry.argument(name="helpText")
    ] = strawberry.UNSET,
    name: Annotated[str | None, strawberry.argument(name="name")] = strawberry.UNSET,
    validation_config: Annotated[
        GenericScalar | None, strawberry.argument(name="validationConfig")
    ] = strawberry.UNSET,
) -> UpdateMetadataColumn | None:
    kwargs = strip_unset(
        {
            "column_id": column_id,
            "default_value": default_value,
            "display_order": display_order,
            "help_text": help_text,
            "name": name,
            "validation_config": validation_config,
        }
    )
    return _mutate_UpdateMetadataColumn(UpdateMetadataColumn, None, info, **kwargs)


def _mutate_DeleteMetadataColumn(payload_cls, root, info, column_id):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:409

    Port of DeleteMetadataColumn.mutate
    """
    # @login_required (graphql_jwt) — inlined; see _mutate_CreateFieldset.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    # Unified message blocks IDOR enumeration: same response whether the
    # column does not exist or the caller lacks DELETE permission.
    not_found_msg = "Column not found or you do not have permission to delete it."

    try:
        user = info.context.user
        # READ-gate the column lookup through the service layer so an
        # invisible column returns the unified not-found message before
        # any fieldset/corpus traversal (IDOR-safe). Mirrors how
        # CreateMetadataColumn/UpdateMetadataColumn fetch the column.
        column, corpus = _get_metadata_column_with_corpus(column_id, user, info.context)
        if column is None or corpus is None:
            return payload_cls(ok=False, message=not_found_msg)

        # Metadata schemas are corpus-scoped objects. Authorize destructive
        # schema changes against the parent corpus instead of the child
        # Column so creator/direct Column grants cannot outlive corpus
        # permissions and cascade-delete metadata values.
        if BaseService.require_permission(
            corpus, user, PermissionTypes.DELETE, request=info.context
        ):
            return payload_cls(ok=False, message=not_found_msg)

        # Mirrors UpdateMetadataColumn: only manual-entry (metadata)
        # columns are managed through this surface — extract columns
        # have their own lifecycle (DeleteColumn).
        if not column.is_manual_entry:
            return payload_cls(
                ok=False, message="Only manual entry columns can be deleted"
            )

        column.delete()
        return payload_cls(ok=True, message="Metadata field deleted successfully")

    except Exception:
        logger.exception("Error deleting metadata field")
        return payload_cls(ok=False, message="Error deleting metadata field.")


def m_delete_metadata_column(
    info: strawberry.Info,
    column_id: Annotated[
        strawberry.ID, strawberry.argument(name="columnId")
    ] = strawberry.UNSET,
) -> DeleteMetadataColumn | None:
    kwargs = strip_unset({"column_id": column_id})
    return _mutate_DeleteMetadataColumn(DeleteMetadataColumn, None, info, **kwargs)


def _mutate_SetMetadataValue(
    payload_cls, root, info, document_id, corpus_id, column_id, value
):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:477

    Port of SetMetadataValue.mutate
    """
    from opencontractserver.extracts.services import MetadataService

    # @login_required (graphql_jwt) — inlined; see _mutate_CreateFieldset.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

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
            return payload_cls(ok=False, message=error_msg)

        # Validate column belongs to corpus metadata schema
        is_valid, error_msg, column = MetadataService.validate_metadata_column(
            local_column_id, local_corpus_id
        )
        if not is_valid or column is None:
            return payload_cls(ok=False, message=error_msg)

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

        return payload_cls(
            ok=True, message="Metadata value set successfully", obj=datacell
        )

    except Document.DoesNotExist:
        return payload_cls(ok=False, message="Document not found")
    except Exception as e:
        return payload_cls(ok=False, message=f"Error setting metadata value: {str(e)}")


def m_set_metadata_value(
    info: strawberry.Info,
    column_id: Annotated[
        strawberry.ID, strawberry.argument(name="columnId")
    ] = strawberry.UNSET,
    corpus_id: Annotated[
        strawberry.ID, strawberry.argument(name="corpusId")
    ] = strawberry.UNSET,
    document_id: Annotated[
        strawberry.ID, strawberry.argument(name="documentId")
    ] = strawberry.UNSET,
    value: Annotated[
        GenericScalar, strawberry.argument(name="value")
    ] = strawberry.UNSET,
) -> SetMetadataValue | None:
    kwargs = strip_unset(
        {
            "column_id": column_id,
            "corpus_id": corpus_id,
            "document_id": document_id,
            "value": value,
        }
    )
    return _mutate_SetMetadataValue(SetMetadataValue, None, info, **kwargs)


def _mutate_DeleteMetadataValue(
    payload_cls, root, info, document_id, corpus_id, column_id
):
    """PORT: /home/user/venv-oc/lib/python3.11/site-packages/graphql_jwt/decorators.py:562

    Port of DeleteMetadataValue.mutate
    """
    from opencontractserver.extracts.services import MetadataService

    # @login_required (graphql_jwt) — inlined; see _mutate_CreateFieldset.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

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
            return payload_cls(ok=False, message=error_msg)

        # Validate column belongs to corpus metadata schema
        is_valid, error_msg, column = MetadataService.validate_metadata_column(
            local_column_id, local_corpus_id
        )
        if not is_valid:
            return payload_cls(ok=False, message=error_msg)

        # Get document for lookup
        document = Document.objects.get(pk=local_doc_id)

        # Find and delete the datacell
        datacell = Datacell.objects.get(document=document, column=column)
        datacell.delete()

        return payload_cls(ok=True, message="Metadata value deleted successfully")

    except Document.DoesNotExist:
        return payload_cls(ok=False, message="Document not found")
    except Datacell.DoesNotExist:
        return payload_cls(ok=False, message="Metadata value not found")
    except Exception as e:
        return payload_cls(ok=False, message=f"Error deleting metadata value: {str(e)}")


def m_delete_metadata_value(
    info: strawberry.Info,
    column_id: Annotated[
        strawberry.ID, strawberry.argument(name="columnId")
    ] = strawberry.UNSET,
    corpus_id: Annotated[
        strawberry.ID, strawberry.argument(name="corpusId")
    ] = strawberry.UNSET,
    document_id: Annotated[
        strawberry.ID, strawberry.argument(name="documentId")
    ] = strawberry.UNSET,
) -> DeleteMetadataValue | None:
    kwargs = strip_unset(
        {"column_id": column_id, "corpus_id": corpus_id, "document_id": document_id}
    )
    return _mutate_DeleteMetadataValue(DeleteMetadataValue, None, info, **kwargs)


MUTATION_FIELDS = {
    "create_fieldset": strawberry.field(
        resolver=m_create_fieldset, name="createFieldset"
    ),
    "update_fieldset": strawberry.field(
        resolver=m_update_fieldset,
        name="updateFieldset",
        description="Rename / re-describe a fieldset the caller may UPDATE.",
    ),
    "create_column": strawberry.field(resolver=m_create_column, name="createColumn"),
    "update_column": strawberry.field(resolver=m_update_column, name="updateColumn"),
    "delete_column": strawberry.field(resolver=m_delete_column, name="deleteColumn"),
    "create_extract": strawberry.field(
        resolver=m_create_extract,
        name="createExtract",
        description='Create a new extract. If fieldset_id is provided, attach existing fieldset.\nOtherwise, a new fieldset is created. If no name is provided, fieldset name has\nform "[Extract name] Fieldset"',
    ),
    "create_extract_iteration": strawberry.field(
        resolver=m_create_extract_iteration,
        name="createExtractIteration",
        description="Fork an existing Extract into a new iteration along a single axis.\n\nThree axes are supported, mirroring the three eval workflows:\n  * ``MODEL`` — same fieldset + same documents, new model_config.\n  * ``DOCUMENT_VERSIONS`` — same fieldset + same model_config, but each\n    document is replaced by the current row in its version tree.\n  * ``FIELDSET`` — clone the fieldset (with optional per-column\n    overrides), keep documents + model_config.\n\nThe new extract has ``parent_extract`` set to the source so the UI can\nwalk the iteration series. If ``auto_start`` is true the standard\n``run_extract`` task is queued exactly as ``StartExtract`` would.",
    ),
    "start_extract": strawberry.field(resolver=m_start_extract, name="startExtract"),
    "delete_extract": strawberry.field(resolver=m_delete_extract, name="deleteExtract"),
    "update_extract": strawberry.field(
        resolver=m_update_extract,
        name="updateExtract",
        description="Mutation to update an existing Extract object.\n\nSupports updating the name (title), corpus, fieldset, and error fields.\nEnsures proper permission checks are applied.",
    ),
    "add_docs_to_extract": strawberry.field(
        resolver=m_add_docs_to_extract, name="addDocsToExtract"
    ),
    "remove_docs_from_extract": strawberry.field(
        resolver=m_remove_docs_from_extract, name="removeDocsFromExtract"
    ),
    "approve_datacell": strawberry.field(
        resolver=m_approve_datacell, name="approveDatacell"
    ),
    "reject_datacell": strawberry.field(
        resolver=m_reject_datacell, name="rejectDatacell"
    ),
    "edit_datacell": strawberry.field(resolver=m_edit_datacell, name="editDatacell"),
    "start_extract_for_doc": strawberry.field(
        resolver=m_start_extract_for_doc, name="startExtractForDoc"
    ),
    "create_metadata_column": strawberry.field(
        resolver=m_create_metadata_column,
        name="createMetadataColumn",
        description="Create a metadata column for a corpus.",
    ),
    "update_metadata_column": strawberry.field(
        resolver=m_update_metadata_column,
        name="updateMetadataColumn",
        description="Update a metadata column.",
    ),
    "delete_metadata_column": strawberry.field(
        resolver=m_delete_metadata_column,
        name="deleteMetadataColumn",
        description="Delete a manual-entry metadata column definition (values cascade).",
    ),
    "set_metadata_value": strawberry.field(
        resolver=m_set_metadata_value,
        name="setMetadataValue",
        description="Set a metadata value for a document.\n\nPermission model:\n- Requires Corpus UPDATE permission + Document READ permission\n- Metadata is a corpus-level feature, so corpus permission controls editing\n- Uses MetadataService for consistent permission checking",
    ),
    "delete_metadata_value": strawberry.field(
        resolver=m_delete_metadata_value,
        name="deleteMetadataValue",
        description="Delete a metadata value for a document.\n\nPermission model:\n- Requires Corpus DELETE permission + Document READ permission\n- Metadata is a corpus-level feature, so corpus permission controls deletion\n- Uses MetadataService for consistent permission checking",
    ),
}
