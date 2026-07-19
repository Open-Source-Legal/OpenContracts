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
from typing import Annotated, Any, Literal

import strawberry
from django.core.exceptions import ValidationError
from django.db import transaction
from graphql_relay import from_global_id

from config.graphql import enums
from config.graphql._util import strip_unset
from config.graphql.core.auth import PermissionDenied
from config.graphql.core.mutations import drf_deletion, drf_mutation
from config.graphql.core.relay import (
    register_type,
)
from config.graphql.core.scalars import GenericScalar
from config.graphql.ratelimits import get_user_tier_rate, graphql_ratelimit_dynamic
from config.graphql.serializers import AnnotationSerializer
from opencontractserver.annotations.models import (
    Annotation,
    AnnotationLabel,
    Note,
    Relationship,
    validate_link_url,
)
from opencontractserver.constants.annotations import (
    OC_CITY_LABEL_COLOR,
    OC_CITY_LABEL_DESCRIPTION,
    OC_CITY_LABEL_ICON,
    OC_COUNTRY_LABEL_COLOR,
    OC_COUNTRY_LABEL_DESCRIPTION,
    OC_COUNTRY_LABEL_ICON,
    OC_STATE_LABEL_COLOR,
    OC_STATE_LABEL_DESCRIPTION,
    OC_STATE_LABEL_ICON,
    OC_URL_LABEL,
    OC_URL_LABEL_COLOR,
    OC_URL_LABEL_DESCRIPTION,
    OC_URL_LABEL_ICON,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.shared.services.base import BaseService
from opencontractserver.types.enums import LabelType, PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

logger = logging.getLogger(__name__)


@graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("WRITE_LIGHT"), group="mutate")
def _write_light_rate_gate(root, info, **kwargs):
    """Rate-limit gate with the ``(root, info)`` shape core decorators expect.

    graphene applied ``@graphql_ratelimit_dynamic`` directly to each
    ``mutate(root, info, ...)`` classmethod; the strawberry mutate stubs take
    ``payload_cls`` as their first positional argument, which does not match
    that calling convention, so the decorator is hoisted onto this no-op and
    invoked at the top of each rate-limited stub. ``group="mutate"`` preserves
    the shared graphene bucket (every graphene mutation's func was literally
    named ``mutate``, so they all shared one rate group).
    """
    return None


_ANNOTATION_PARENT_NOT_FOUND_MSG = (
    "Document or corpus not found, or you do not have " "permission to annotate it."
)


def _format_link_url_error(exc: ValidationError) -> str:
    """Surface a stable, human-readable link_url validation error.

    ``str(ValidationError({"link_url": "..."}))`` returns a Python
    ``[" {'link_url': ['...']} "]`` string that leaks internal structure.
    Pull the first message off the dict so the user sees a clean sentence.
    """
    detail = getattr(exc, "message_dict", None)
    if detail:
        messages = detail.get("link_url", []) or []
        if messages:
            return str(messages[0])
    return "link_url failed validation."


def _resolve_annotation_parents(
    user,
    corpus_pk: int | str,
    document_pk: int | str,
    *,
    request=None,
) -> tuple[Document, Corpus] | None:
    """Resolve and validate the (document, corpus) parents for a new annotation.

    Returns the (document, corpus) tuple when:
        - both rows are visible to the user,
        - the user has CREATE permission on the corpus,
        - the document is a current member of the corpus (via DocumentPath).

    Returns None on any failure so callers can surface a single uniform
    "not found" error and avoid leaking existence/permission state. The
    DocumentPath check closes a cross-corpus IDOR (user has visibility to
    doc D in corpus A and CREATE on corpus B → would otherwise be allowed
    to write `Annotation(document=D, corpus=B)`).
    """
    document = BaseService.get_or_none(Document, document_pk, user, request=request)
    corpus = BaseService.get_or_none(Corpus, corpus_pk, user, request=request)
    if document is None or corpus is None:
        return None

    if BaseService.require_permission(
        corpus, user, PermissionTypes.CREATE, request=request
    ):
        return None

    if not DocumentPath.objects.filter(
        document=document, corpus=corpus, is_current=True, is_deleted=False
    ).exists():
        return None

    return document, corpus


# --------------------------------------------------------------------------- #
# Geographic auto-creating annotation mutations — issue #1819
# --------------------------------------------------------------------------- #
# Each of the three geographic mutations mirrors ``AddUrlAnnotation``
# (auto-creates the corresponding OC_* label on first use, ensures the corpus
# has a label set) but with one extra step: the supplied span text is fed to
# the offline geocoding service (``opencontractserver/utils/geocoding``) and
# the resolver result is stamped into ``Annotation.data`` so the map
# aggregation service (#1820 / #1821) can group pins without ever re-running
# the geocoder.
#
# When the resolver returns ``None`` (no row in the bundled dataset matches
# the text) the annotation is still created — the user's labelling work
# survives — but ``data['geocoded']`` is False so the aggregation service
# skips it. The mutation response surfaces the warning so a future agent /
# UI can prompt the user to clean up the text or pass a hint.
#
# These mutations are deliberately ``structural=True``: like other OC_*
# auto-annotations (OC_SECTION, OC_URL), the geographic conventions encode
# document structure rather than user opinion, and structural rows are
# always read-only for non-superusers per the platform's permission model.

# Only the visual / descriptive columns live here — the label-text column
# is sourced from ``GEOCODE_LABEL_TYPE_TO_LABEL_TEXT`` in the geographic
# service module so a fourth geographic label type stays a single-edit
# change.
_GEOCODE_LABEL_TYPE_TO_OC_LABEL_METADATA: dict[str, tuple[str, str, str]] = {
    "country": (
        OC_COUNTRY_LABEL_COLOR,
        OC_COUNTRY_LABEL_ICON,
        OC_COUNTRY_LABEL_DESCRIPTION,
    ),
    "state": (
        OC_STATE_LABEL_COLOR,
        OC_STATE_LABEL_ICON,
        OC_STATE_LABEL_DESCRIPTION,
    ),
    "city": (
        OC_CITY_LABEL_COLOR,
        OC_CITY_LABEL_ICON,
        OC_CITY_LABEL_DESCRIPTION,
    ),
}


def _create_geographic_annotation(
    *,
    user,
    info,
    corpus_pk: int | str,
    document_pk: int | str,
    page: int,
    raw_text: str,
    json: Any,
    annotation_type,
    geocode_label_type: Literal["country", "state", "city"],
    country_hint: str | None,
    state_hint: str | None,
) -> tuple[bool, str, Annotation | None]:
    """Shared body for the three Add*Annotation mutations.

    Returns ``(ok, message, annotation)`` so each mutation class is a thin
    wrapper that just unpacks the tuple — the actual ``resolve_place`` →
    ``ensure_label_and_labelset`` → ``Annotation.save`` flow lives in one
    place so all three label types follow the exact same contract.

    Per #1819, the annotation is created even when the geocoder fails — we
    don't want to silently lose the user's labelling work — but the
    ``data['geocoded']`` flag distinguishes resolved from un-resolved rows
    so the aggregation service excludes the latter.
    """
    # Guard empty / whitespace-only ``raw_text`` up front — an empty span
    # produces a no-op annotation (``geocoded=False``, no canonical_name)
    # that pollutes the user's annotation set without contributing to the
    # map. Surface a clear error instead of silently creating it.
    if not raw_text or not raw_text.strip():
        return False, "raw_text must not be empty", None

    parents = _resolve_annotation_parents(
        user, corpus_pk, document_pk, request=info.context
    )
    if parents is None:
        return False, _ANNOTATION_PARENT_NOT_FOUND_MSG, None
    document, corpus = parents

    from opencontractserver.annotations.services.geographic_service import (
        GEOCODE_LABEL_TYPE_TO_LABEL_TEXT,
        build_geocoded_annotation_data,
    )

    label_text = GEOCODE_LABEL_TYPE_TO_LABEL_TEXT[geocode_label_type]
    color, icon, description = _GEOCODE_LABEL_TYPE_TO_OC_LABEL_METADATA[
        geocode_label_type
    ]

    annotation_data = build_geocoded_annotation_data(
        geocode_label_type,
        raw_text,
        country_hint=country_hint,
        state_hint=state_hint,
    )
    if annotation_data["geocoded"]:
        message = f"Resolved '{raw_text}' to '{annotation_data['canonical_name']}'"
    else:
        message = (
            f"Annotation created but '{raw_text}' did not resolve to a "
            f"known {geocode_label_type}; pin omitted from map "
            "aggregation. Pass country_hint / state_hint to disambiguate."
        )

    with transaction.atomic():
        label = corpus.ensure_label_and_labelset(
            label_text=label_text,
            creator_id=user.pk,
            label_type=annotation_type.value,
            color=color,
            icon=icon,
            description=description,
        )
        # Structural items are platform-managed; the corpus-level
        # convention forbids users from editing them later (only
        # superusers can — see ``AnnotationManager.user_can`` Phase B).
        if not label.read_only:
            label.read_only = True
            label.save(update_fields=["read_only"])

        annotation = Annotation(
            page=page,
            raw_text=raw_text,
            corpus_id=corpus.pk,
            document_id=document.pk,
            annotation_label_id=label.pk,
            creator=user,
            json=json,
            annotation_type=annotation_type.value,
            structural=True,
            data=annotation_data,
        )
        annotation.save()
        set_permissions_for_obj_to_user(
            user,
            annotation,
            [PermissionTypes.CRUD],
            is_new=True,
            request=info.context,
        )

    return True, message, annotation


@strawberry.type(name="AddAnnotation")
class AddAnnotation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    annotation: None | (
        Annotated[AnnotationType, strawberry.lazy("config.graphql.annotation_types")]
    ) = strawberry.field(name="annotation", default=None)


register_type("AddAnnotation", AddAnnotation, model=None)


@strawberry.type(
    name="AddUrlAnnotation",
    description="Create an annotation labelled ``OC_URL`` with a click-through URL.\n\nConvenience wrapper over ``AddAnnotation``: ensures the corpus has an\n``OC_URL`` label (creating it if absent) and stamps ``link_url`` on the\nresulting annotation so the frontend renders the highlighted text as a\nclickable hyperlink.",
)
class AddUrlAnnotation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    annotation: None | (
        Annotated[AnnotationType, strawberry.lazy("config.graphql.annotation_types")]
    ) = strawberry.field(name="annotation", default=None)


register_type("AddUrlAnnotation", AddUrlAnnotation, model=None)


@strawberry.type(
    name="AddCountryAnnotation",
    description="Create an annotation labelled ``OC_COUNTRY`` with offline-geocoded data.\n\nMirrors :class:`AddUrlAnnotation` but routes through the bundled\ngeocoding service (see :mod:`opencontractserver.utils.geocoding`).\n``country_hint`` is intentionally absent — the country lookup is\nself-disambiguating.",
)
class AddCountryAnnotation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    annotation: None | (
        Annotated[AnnotationType, strawberry.lazy("config.graphql.annotation_types")]
    ) = strawberry.field(name="annotation", default=None)
    geocoded: bool | None = strawberry.field(
        name="geocoded",
        description="True if the offline geocoder resolved the span; False when the annotation was created but no map pin was generated.",
        default=None,
    )


register_type("AddCountryAnnotation", AddCountryAnnotation, model=None)


@strawberry.type(
    name="AddStateAnnotation",
    description="Create an annotation labelled ``OC_STATE`` with offline-geocoded data.\n\n``country_hint`` narrows the candidate pool to a single country; today\nthe bundled state dataset is US-only, so the hint mostly exists as a\nforward-compatibility hook for when non-US first-level admin\ndivisions are added.",
)
class AddStateAnnotation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    annotation: None | (
        Annotated[AnnotationType, strawberry.lazy("config.graphql.annotation_types")]
    ) = strawberry.field(name="annotation", default=None)
    geocoded: bool | None = strawberry.field(
        name="geocoded",
        description="True if the offline geocoder resolved the span; False when the annotation was created but no map pin was generated.",
        default=None,
    )


register_type("AddStateAnnotation", AddStateAnnotation, model=None)


@strawberry.type(
    name="AddCityAnnotation",
    description='Create an annotation labelled ``OC_CITY`` with offline-geocoded data.\n\n``country_hint`` / ``state_hint`` resolve via the same indexes the\nmain lookup uses, so any recognised form ("France" / "FR" / "Texas"\n/ "TX") works. Hints narrow the candidate pool BEFORE the\nexact / alias / fuzzy chain runs, so a hinted ambiguous string\n(e.g. "Paris" + state_hint="TX") prefers the right row even when\nmultiple rows are exact name matches.',
)
class AddCityAnnotation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    annotation: None | (
        Annotated[AnnotationType, strawberry.lazy("config.graphql.annotation_types")]
    ) = strawberry.field(name="annotation", default=None)
    geocoded: bool | None = strawberry.field(
        name="geocoded",
        description="True if the offline geocoder resolved the span; False when the annotation was created but no map pin was generated.",
        default=None,
    )


register_type("AddCityAnnotation", AddCityAnnotation, model=None)


@strawberry.type(name="RemoveAnnotation")
class RemoveAnnotation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)


register_type("RemoveAnnotation", RemoveAnnotation, model=None)


@strawberry.type(name="UpdateAnnotation")
class UpdateAnnotation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    obj_id: strawberry.ID | None = strawberry.field(name="objId", default=None)


register_type("UpdateAnnotation", UpdateAnnotation, model=None)


@strawberry.type(name="AddDocTypeAnnotation")
class AddDocTypeAnnotation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    annotation: None | (
        Annotated[AnnotationType, strawberry.lazy("config.graphql.annotation_types")]
    ) = strawberry.field(name="annotation", default=None)


register_type("AddDocTypeAnnotation", AddDocTypeAnnotation, model=None)


@strawberry.type(name="ApproveAnnotation")
class ApproveAnnotation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    user_feedback: None | (
        Annotated[UserFeedbackType, strawberry.lazy("config.graphql.user_types")]
    ) = strawberry.field(name="userFeedback", default=None)
    message: str | None = strawberry.field(name="message", default=None)


register_type("ApproveAnnotation", ApproveAnnotation, model=None)


@strawberry.type(name="RejectAnnotation")
class RejectAnnotation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    user_feedback: None | (
        Annotated[UserFeedbackType, strawberry.lazy("config.graphql.user_types")]
    ) = strawberry.field(name="userFeedback", default=None)
    message: str | None = strawberry.field(name="message", default=None)


register_type("RejectAnnotation", RejectAnnotation, model=None)


@strawberry.type(name="AddRelationship")
class AddRelationship:
    ok: bool | None = strawberry.field(name="ok", default=None)
    relationship: None | (
        Annotated[RelationshipType, strawberry.lazy("config.graphql.annotation_types")]
    ) = strawberry.field(name="relationship", default=None)
    message: str | None = strawberry.field(name="message", default=None)


register_type("AddRelationship", AddRelationship, model=None)


@strawberry.type(name="RemoveRelationship")
class RemoveRelationship:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)


register_type("RemoveRelationship", RemoveRelationship, model=None)


@strawberry.type(name="RemoveRelationships")
class RemoveRelationships:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)


register_type("RemoveRelationships", RemoveRelationships, model=None)


@strawberry.type(
    name="UpdateRelationship",
    description="Update an existing relationship by adding or removing annotations\nfrom source or target sets.",
)
class UpdateRelationship:
    ok: bool | None = strawberry.field(name="ok", default=None)
    relationship: None | (
        Annotated[RelationshipType, strawberry.lazy("config.graphql.annotation_types")]
    ) = strawberry.field(name="relationship", default=None)
    message: str | None = strawberry.field(name="message", default=None)


register_type("UpdateRelationship", UpdateRelationship, model=None)


@strawberry.type(name="UpdateRelations")
class UpdateRelations:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)


register_type("UpdateRelations", UpdateRelations, model=None)


@strawberry.type(
    name="UpdateNote",
    description="Mutation to update a note's content, creating a new version in the process.\nOnly the note creator can update their notes.",
)
class UpdateNote:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    obj: None | (
        Annotated[NoteType, strawberry.lazy("config.graphql.annotation_types")]
    ) = strawberry.field(name="obj", default=None)
    version: int | None = strawberry.field(
        name="version", description="The new version number after update", default=None
    )


register_type("UpdateNote", UpdateNote, model=None)


@strawberry.type(
    name="DeleteNote",
    description="Mutation to delete a note. Only the creator can delete their notes.",
)
class DeleteNote:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)


register_type("DeleteNote", DeleteNote, model=None)


@strawberry.type(
    name="CreateNote", description="Mutation to create a new note for a document."
)
class CreateNote:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    obj: None | (
        Annotated[NoteType, strawberry.lazy("config.graphql.annotation_types")]
    ) = strawberry.field(name="obj", default=None)


register_type("CreateNote", CreateNote, model=None)


def _mutate_AddAnnotation(
    payload_cls,
    root,
    info,
    json,
    page,
    raw_text,
    corpus_id,
    document_id,
    annotation_label_id,
    annotation_type,
    long_description=None,
    link_url=None,
):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_mutations.py:259

    Port of AddAnnotation.mutate
    """
    # @login_required (graphql_jwt) — inlined because mutate stubs take
    # ``payload_cls`` as their first positional argument, which does not
    # match core.auth's ``(root, info, ...)`` calling convention.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()
    # @graphql_ratelimit_dynamic(get_rate=get_user_tier_rate("WRITE_LIGHT")) —
    # inlined for the same reason; raises RateLimitExceeded when over.
    _write_light_rate_gate(root, info)
    # graphene passed the LabelType enum member; the strawberry wrapper
    # unwraps it to its raw string value — re-wrap so the verbatim body's
    # ``annotation_type.value`` keeps working.
    annotation_type = LabelType(annotation_type)

    corpus_pk = from_global_id(corpus_id)[1]
    document_pk = from_global_id(document_id)[1]
    label_pk = from_global_id(annotation_label_id)[1]

    user = info.context.user

    if link_url:
        try:
            validate_link_url(link_url)
        except ValidationError as exc:
            return payload_cls(
                ok=False, annotation=None, message=_format_link_url_error(exc)
            )

    parents = _resolve_annotation_parents(
        user, corpus_pk, document_pk, request=info.context
    )
    if parents is None:
        return payload_cls(
            ok=False,
            annotation=None,
            message=_ANNOTATION_PARENT_NOT_FOUND_MSG,
        )
    document, corpus = parents

    annotation = Annotation(
        page=page,
        raw_text=raw_text,
        long_description=long_description,
        corpus_id=corpus.pk,
        document_id=document.pk,
        annotation_label_id=label_pk,
        creator=user,
        json=json,
        annotation_type=annotation_type.value,
        # Normalise empty string to None so the column ends up NULL
        # (the ``if link_url:`` guard above only protects the validator
        # call, not the persisted value).
        link_url=link_url or None,
    )
    annotation.save()
    set_permissions_for_obj_to_user(
        user,
        annotation,
        [PermissionTypes.CRUD],
        is_new=True,
        request=info.context,
    )

    return payload_cls(ok=True, message="Annotation created", annotation=annotation)


def m_add_annotation(
    info: strawberry.Info,
    annotation_label_id: Annotated[
        str,
        strawberry.argument(
            name="annotationLabelId",
            description="Id of the label that is applied via this annotation.",
        ),
    ] = strawberry.UNSET,
    annotation_type: Annotated[
        enums.LabelType, strawberry.argument(name="annotationType")
    ] = strawberry.UNSET,
    corpus_id: Annotated[
        str,
        strawberry.argument(
            name="corpusId", description="ID of the corpus this annotation is for."
        ),
    ] = strawberry.UNSET,
    document_id: Annotated[
        str,
        strawberry.argument(
            name="documentId", description="Id of the document this annotation is on."
        ),
    ] = strawberry.UNSET,
    json: Annotated[
        GenericScalar,
        strawberry.argument(
            name="json", description="New-style JSON for multipage annotations"
        ),
    ] = strawberry.UNSET,
    link_url: Annotated[
        str | None,
        strawberry.argument(
            name="linkUrl",
            description="Optional URL opened on click. Restricted to http(s):// or site-relative paths; intended for OC_URL annotations.",
        ),
    ] = strawberry.UNSET,
    long_description: Annotated[
        str | None,
        strawberry.argument(
            name="longDescription",
            description="Optional markdown description for this annotation.",
        ),
    ] = strawberry.UNSET,
    page: Annotated[
        int,
        strawberry.argument(
            name="page", description="What page is this annotation on (0-indexed)"
        ),
    ] = strawberry.UNSET,
    raw_text: Annotated[
        str,
        strawberry.argument(
            name="rawText", description="What is the raw text of the annotation?"
        ),
    ] = strawberry.UNSET,
) -> AddAnnotation | None:
    kwargs = strip_unset(
        {
            "annotation_label_id": annotation_label_id,
            "annotation_type": annotation_type,
            "corpus_id": corpus_id,
            "document_id": document_id,
            "json": json,
            "link_url": link_url,
            "long_description": long_description,
            "page": page,
            "raw_text": raw_text,
        }
    )
    return _mutate_AddAnnotation(AddAnnotation, None, info, **kwargs)


def _mutate_AddUrlAnnotation(
    payload_cls,
    root,
    info,
    json,
    page,
    raw_text,
    corpus_id,
    document_id,
    annotation_type,
    link_url,
):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_mutations.py:367

    Port of AddUrlAnnotation.mutate
    """
    # @login_required (graphql_jwt) — inlined; see _mutate_AddAnnotation.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()
    # @graphql_ratelimit_dynamic (WRITE_LIGHT) — inlined; see _mutate_AddAnnotation.
    _write_light_rate_gate(root, info)
    # Re-wrap the raw enum value; see _mutate_AddAnnotation.
    annotation_type = LabelType(annotation_type)

    corpus_pk = from_global_id(corpus_id)[1]
    document_pk = from_global_id(document_id)[1]

    user = info.context.user

    try:
        validate_link_url(link_url)
    except ValidationError as exc:
        return payload_cls(
            ok=False, annotation=None, message=_format_link_url_error(exc)
        )

    parents = _resolve_annotation_parents(
        user, corpus_pk, document_pk, request=info.context
    )
    if parents is None:
        return payload_cls(
            ok=False,
            annotation=None,
            message=_ANNOTATION_PARENT_NOT_FOUND_MSG,
        )
    document, corpus = parents

    with transaction.atomic():
        # ``ensure_label_and_labelset`` is idempotent per (text, label_type).
        # PDF (TOKEN_LABEL) and text (SPAN_LABEL) documents each get their
        # own OC_URL row — the lookup filters on both fields, so flipping
        # types between calls cannot return a label of the wrong shape to
        # the renderer.
        label = corpus.ensure_label_and_labelset(
            label_text=OC_URL_LABEL,
            creator_id=user.pk,
            label_type=annotation_type.value,
            color=OC_URL_LABEL_COLOR,
            icon=OC_URL_LABEL_ICON,
            description=OC_URL_LABEL_DESCRIPTION,
        )

        annotation = Annotation(
            page=page,
            raw_text=raw_text,
            corpus_id=corpus.pk,
            document_id=document.pk,
            annotation_label_id=label.pk,
            creator=user,
            json=json,
            annotation_type=annotation_type.value,
            link_url=link_url,
        )
        annotation.save()
        set_permissions_for_obj_to_user(
            user,
            annotation,
            [PermissionTypes.CRUD],
            is_new=True,
            request=info.context,
        )

    return payload_cls(ok=True, message="URL annotation created", annotation=annotation)


def m_add_url_annotation(
    info: strawberry.Info,
    annotation_type: Annotated[
        enums.LabelType,
        strawberry.argument(
            name="annotationType",
            description="Annotation type: TOKEN_LABEL for PDFs, SPAN_LABEL for text.",
        ),
    ] = strawberry.UNSET,
    corpus_id: Annotated[
        str,
        strawberry.argument(
            name="corpusId", description="ID of the corpus this annotation is for."
        ),
    ] = strawberry.UNSET,
    document_id: Annotated[
        str,
        strawberry.argument(
            name="documentId", description="ID of the document this annotation is on."
        ),
    ] = strawberry.UNSET,
    json: Annotated[
        GenericScalar,
        strawberry.argument(
            name="json", description="New-style JSON for multipage annotations."
        ),
    ] = strawberry.UNSET,
    link_url: Annotated[
        str,
        strawberry.argument(
            name="linkUrl", description="The target URL to open on click."
        ),
    ] = strawberry.UNSET,
    page: Annotated[
        int,
        strawberry.argument(
            name="page", description="What page is this annotation on (0-indexed)."
        ),
    ] = strawberry.UNSET,
    raw_text: Annotated[
        str,
        strawberry.argument(name="rawText", description="The raw text being linked."),
    ] = strawberry.UNSET,
) -> AddUrlAnnotation | None:
    kwargs = strip_unset(
        {
            "annotation_type": annotation_type,
            "corpus_id": corpus_id,
            "document_id": document_id,
            "json": json,
            "link_url": link_url,
            "page": page,
            "raw_text": raw_text,
        }
    )
    return _mutate_AddUrlAnnotation(AddUrlAnnotation, None, info, **kwargs)


def _mutate_AddCountryAnnotation(
    payload_cls,
    root,
    info,
    json,
    page,
    raw_text,
    corpus_id,
    document_id,
    annotation_type,
):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_mutations.py:634

    Port of AddCountryAnnotation.mutate
    """
    # @login_required (graphql_jwt) — inlined; see _mutate_AddAnnotation.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()
    # @graphql_ratelimit_dynamic (WRITE_LIGHT) — inlined; see _mutate_AddAnnotation.
    _write_light_rate_gate(root, info)
    # Re-wrap the raw enum value; see _mutate_AddAnnotation.
    annotation_type = LabelType(annotation_type)

    corpus_pk = from_global_id(corpus_id)[1]
    document_pk = from_global_id(document_id)[1]
    user = info.context.user

    ok, message, annotation = _create_geographic_annotation(
        user=user,
        info=info,
        corpus_pk=corpus_pk,
        document_pk=document_pk,
        page=page,
        raw_text=raw_text,
        json=json,
        annotation_type=annotation_type,
        geocode_label_type="country",
        country_hint=None,
        state_hint=None,
    )
    return payload_cls(
        ok=ok,
        message=message,
        annotation=annotation,
        geocoded=bool(
            annotation and annotation.data and annotation.data.get("geocoded")
        ),
    )


def m_add_country_annotation(
    info: strawberry.Info,
    annotation_type: Annotated[
        enums.LabelType,
        strawberry.argument(
            name="annotationType",
            description="Annotation type: TOKEN_LABEL for PDFs, SPAN_LABEL for text.",
        ),
    ] = strawberry.UNSET,
    corpus_id: Annotated[
        str,
        strawberry.argument(
            name="corpusId", description="ID of the corpus this annotation is for."
        ),
    ] = strawberry.UNSET,
    document_id: Annotated[
        str,
        strawberry.argument(
            name="documentId", description="ID of the document this annotation is on."
        ),
    ] = strawberry.UNSET,
    json: Annotated[
        GenericScalar,
        strawberry.argument(
            name="json", description="New-style JSON for multipage annotations."
        ),
    ] = strawberry.UNSET,
    page: Annotated[
        int,
        strawberry.argument(
            name="page", description="What page is this annotation on (0-indexed)."
        ),
    ] = strawberry.UNSET,
    raw_text: Annotated[
        str,
        strawberry.argument(
            name="rawText",
            description="The raw text identifying the country (e.g. 'France', 'FR').",
        ),
    ] = strawberry.UNSET,
) -> AddCountryAnnotation | None:
    kwargs = strip_unset(
        {
            "annotation_type": annotation_type,
            "corpus_id": corpus_id,
            "document_id": document_id,
            "json": json,
            "page": page,
            "raw_text": raw_text,
        }
    )
    return _mutate_AddCountryAnnotation(AddCountryAnnotation, None, info, **kwargs)


def _mutate_AddStateAnnotation(
    payload_cls,
    root,
    info,
    json,
    page,
    raw_text,
    corpus_id,
    document_id,
    annotation_type,
    country_hint=None,
):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_mutations.py:712

    Port of AddStateAnnotation.mutate
    """
    # @login_required (graphql_jwt) — inlined; see _mutate_AddAnnotation.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()
    # @graphql_ratelimit_dynamic (WRITE_LIGHT) — inlined; see _mutate_AddAnnotation.
    _write_light_rate_gate(root, info)
    # Re-wrap the raw enum value; see _mutate_AddAnnotation.
    annotation_type = LabelType(annotation_type)

    corpus_pk = from_global_id(corpus_id)[1]
    document_pk = from_global_id(document_id)[1]
    user = info.context.user

    ok, message, annotation = _create_geographic_annotation(
        user=user,
        info=info,
        corpus_pk=corpus_pk,
        document_pk=document_pk,
        page=page,
        raw_text=raw_text,
        json=json,
        annotation_type=annotation_type,
        geocode_label_type="state",
        country_hint=country_hint,
        state_hint=None,
    )
    return payload_cls(
        ok=ok,
        message=message,
        annotation=annotation,
        geocoded=bool(
            annotation and annotation.data and annotation.data.get("geocoded")
        ),
    )


def m_add_state_annotation(
    info: strawberry.Info,
    annotation_type: Annotated[
        enums.LabelType, strawberry.argument(name="annotationType")
    ] = strawberry.UNSET,
    corpus_id: Annotated[str, strawberry.argument(name="corpusId")] = strawberry.UNSET,
    country_hint: Annotated[
        str | None,
        strawberry.argument(
            name="countryHint",
            description="Optional country to disambiguate the state (default: United States, the only first-level admin set bundled today).",
        ),
    ] = strawberry.UNSET,
    document_id: Annotated[
        str, strawberry.argument(name="documentId")
    ] = strawberry.UNSET,
    json: Annotated[GenericScalar, strawberry.argument(name="json")] = strawberry.UNSET,
    page: Annotated[int, strawberry.argument(name="page")] = strawberry.UNSET,
    raw_text: Annotated[
        str,
        strawberry.argument(
            name="rawText",
            description="The raw text identifying the state (e.g. 'Texas', 'TX').",
        ),
    ] = strawberry.UNSET,
) -> AddStateAnnotation | None:
    kwargs = strip_unset(
        {
            "annotation_type": annotation_type,
            "corpus_id": corpus_id,
            "country_hint": country_hint,
            "document_id": document_id,
            "json": json,
            "page": page,
            "raw_text": raw_text,
        }
    )
    return _mutate_AddStateAnnotation(AddStateAnnotation, None, info, **kwargs)


def _mutate_AddCityAnnotation(
    payload_cls,
    root,
    info,
    json,
    page,
    raw_text,
    corpus_id,
    document_id,
    annotation_type,
    country_hint=None,
    state_hint=None,
):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_mutations.py:800

    Port of AddCityAnnotation.mutate
    """
    # @login_required (graphql_jwt) — inlined; see _mutate_AddAnnotation.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()
    # @graphql_ratelimit_dynamic (WRITE_LIGHT) — inlined; see _mutate_AddAnnotation.
    _write_light_rate_gate(root, info)
    # Re-wrap the raw enum value; see _mutate_AddAnnotation.
    annotation_type = LabelType(annotation_type)

    corpus_pk = from_global_id(corpus_id)[1]
    document_pk = from_global_id(document_id)[1]
    user = info.context.user

    ok, message, annotation = _create_geographic_annotation(
        user=user,
        info=info,
        corpus_pk=corpus_pk,
        document_pk=document_pk,
        page=page,
        raw_text=raw_text,
        json=json,
        annotation_type=annotation_type,
        geocode_label_type="city",
        country_hint=country_hint,
        state_hint=state_hint,
    )
    return payload_cls(
        ok=ok,
        message=message,
        annotation=annotation,
        geocoded=bool(
            annotation and annotation.data and annotation.data.get("geocoded")
        ),
    )


def m_add_city_annotation(
    info: strawberry.Info,
    annotation_type: Annotated[
        enums.LabelType, strawberry.argument(name="annotationType")
    ] = strawberry.UNSET,
    corpus_id: Annotated[str, strawberry.argument(name="corpusId")] = strawberry.UNSET,
    country_hint: Annotated[
        str | None,
        strawberry.argument(
            name="countryHint",
            description="Optional country to narrow candidate cities.",
        ),
    ] = strawberry.UNSET,
    document_id: Annotated[
        str, strawberry.argument(name="documentId")
    ] = strawberry.UNSET,
    json: Annotated[GenericScalar, strawberry.argument(name="json")] = strawberry.UNSET,
    page: Annotated[int, strawberry.argument(name="page")] = strawberry.UNSET,
    raw_text: Annotated[
        str,
        strawberry.argument(
            name="rawText",
            description="The raw text identifying the city. Disambiguation hints are recommended for ambiguous names (e.g. 'Paris', 'Springfield').",
        ),
    ] = strawberry.UNSET,
    state_hint: Annotated[
        str | None,
        strawberry.argument(
            name="stateHint",
            description="Optional state / first-level admin division (only applied when the country is the US in the bundled dataset).",
        ),
    ] = strawberry.UNSET,
) -> AddCityAnnotation | None:
    kwargs = strip_unset(
        {
            "annotation_type": annotation_type,
            "corpus_id": corpus_id,
            "country_hint": country_hint,
            "document_id": document_id,
            "json": json,
            "page": page,
            "raw_text": raw_text,
            "state_hint": state_hint,
        }
    )
    return _mutate_AddCityAnnotation(AddCityAnnotation, None, info, **kwargs)


def _mutate_RemoveAnnotation(payload_cls, root, info, annotation_id):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_mutations.py:66

    Port of RemoveAnnotation.mutate

    Serves both ``removeAnnotation`` and ``removeDocTypeAnnotation`` (the
    graphene schema mounted the same ``RemoveAnnotation`` mutation class on
    both fields).
    """
    # @login_required (graphql_jwt) — inlined; see _mutate_AddAnnotation.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    try:
        user = info.context.user
        annotation_pk = from_global_id(annotation_id)[1]

        # IDOR-safe fetch via the service layer — unified error message
        # for not found and not permitted prevents enumeration.
        annotation_obj = BaseService.get_or_none(
            Annotation, annotation_pk, user, request=info.context
        )
        if annotation_obj is None:
            return payload_cls(
                ok=False,
                message="Annotation not found or you do not have permission to access it",
            )

        # Check if user has permission to delete this annotation; the
        # service helper delegates to the manager which understands
        # privacy-aware permissions for annotations created by analyses
        # or extracts.
        if BaseService.require_permission(
            annotation_obj, user, PermissionTypes.DELETE, request=info.context
        ):
            return payload_cls(
                ok=False,
                message="Annotation not found or you do not have permission to access it",
            )

        annotation_obj.delete()
        return payload_cls(ok=True, message="Annotation deleted successfully")
    except Exception as e:
        logger.error(f"Error deleting annotation {annotation_id}: {e}")
        return payload_cls(ok=False, message="An unexpected error occurred")


def m_remove_annotation(
    info: strawberry.Info,
    annotation_id: Annotated[
        str,
        strawberry.argument(
            name="annotationId",
            description="Id of the annotation that is to be deleted.",
        ),
    ] = strawberry.UNSET,
) -> RemoveAnnotation | None:
    kwargs = strip_unset({"annotation_id": annotation_id})
    return _mutate_RemoveAnnotation(RemoveAnnotation, None, info, **kwargs)


def m_update_annotation(
    info: strawberry.Info,
    annotation_label: Annotated[
        str | None, strawberry.argument(name="annotationLabel")
    ] = strawberry.UNSET,
    id: Annotated[str, strawberry.argument(name="id")] = strawberry.UNSET,
    json: Annotated[
        GenericScalar | None, strawberry.argument(name="json")
    ] = strawberry.UNSET,
    link_url: Annotated[
        str | None,
        strawberry.argument(
            name="linkUrl",
            description="Optional click-through URL for OC_URL annotations. Pass an empty string to clear an existing URL. Restricted to http(s):// or site-relative paths.",
        ),
    ] = strawberry.UNSET,
    long_description: Annotated[
        str | None, strawberry.argument(name="longDescription")
    ] = strawberry.UNSET,
    page: Annotated[int | None, strawberry.argument(name="page")] = strawberry.UNSET,
    raw_text: Annotated[
        str | None, strawberry.argument(name="rawText")
    ] = strawberry.UNSET,
) -> UpdateAnnotation | None:
    kwargs = strip_unset(
        {
            "annotation_label": annotation_label,
            "id": id,
            "json": json,
            "link_url": link_url,
            "long_description": long_description,
            "page": page,
            "raw_text": raw_text,
        }
    )
    return drf_mutation(
        payload_cls=UpdateAnnotation,
        model=Annotation,
        serializer=AnnotationSerializer,
        type_name="AnnotationType",
        pk_fields=("annotation_label",),
        lookup_field="id",
        root=None,
        info=info,
        kwargs=kwargs,
    )


def _mutate_AddDocTypeAnnotation(
    payload_cls, root, info, corpus_id, document_id, annotation_label_id
):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_mutations.py:857

    Port of AddDocTypeAnnotation.mutate
    """
    # @login_required (graphql_jwt) — inlined; see _mutate_AddAnnotation.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    corpus_pk = from_global_id(corpus_id)[1]
    document_pk = from_global_id(document_id)[1]
    annotation_label_pk = from_global_id(annotation_label_id)[1]

    user = info.context.user

    parents = _resolve_annotation_parents(
        user, corpus_pk, document_pk, request=info.context
    )
    if parents is None:
        return payload_cls(
            ok=False,
            annotation=None,
            message=_ANNOTATION_PARENT_NOT_FOUND_MSG,
        )
    document, corpus = parents

    annotation = Annotation.objects.create(
        corpus_id=corpus.pk,
        document_id=document.pk,
        annotation_label_id=annotation_label_pk,
        creator=user,
    )
    set_permissions_for_obj_to_user(
        user,
        annotation,
        [PermissionTypes.CRUD],
        is_new=True,
        request=info.context,
    )

    return payload_cls(ok=True, message="Annotation created", annotation=annotation)


def m_add_doc_type_annotation(
    info: strawberry.Info,
    annotation_label_id: Annotated[
        str,
        strawberry.argument(
            name="annotationLabelId",
            description="Id of the label that is applied via this annotation.",
        ),
    ] = strawberry.UNSET,
    corpus_id: Annotated[
        str,
        strawberry.argument(
            name="corpusId", description="ID of the corpus this annotation is for."
        ),
    ] = strawberry.UNSET,
    document_id: Annotated[
        str,
        strawberry.argument(
            name="documentId", description="Id of the document this annotation is on."
        ),
    ] = strawberry.UNSET,
) -> AddDocTypeAnnotation | None:
    kwargs = strip_unset(
        {
            "annotation_label_id": annotation_label_id,
            "corpus_id": corpus_id,
            "document_id": document_id,
        }
    )
    return _mutate_AddDocTypeAnnotation(AddDocTypeAnnotation, None, info, **kwargs)


def m_remove_doc_type_annotation(
    info: strawberry.Info,
    annotation_id: Annotated[
        str,
        strawberry.argument(
            name="annotationId",
            description="Id of the annotation that is to be deleted.",
        ),
    ] = strawberry.UNSET,
) -> RemoveAnnotation | None:
    kwargs = strip_unset({"annotation_id": annotation_id})
    return _mutate_RemoveAnnotation(RemoveAnnotation, None, info, **kwargs)


def _mutate_ApproveAnnotation(payload_cls, root, info, annotation_id, comment=None):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_mutations.py:142

    Port of ApproveAnnotation.mutate
    """
    # @login_required (graphql_jwt) — inlined; see _mutate_AddAnnotation.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    from opencontractserver.feedback.services import UserFeedbackService

    annotation_pk = from_global_id(annotation_id)[1]
    result = UserFeedbackService.approve_annotation(
        info.context.user,
        annotation_pk,
        comment=comment,
        request=info.context,
    )
    if not result.ok:
        return payload_cls(ok=False, user_feedback=None, message=result.error)
    return payload_cls(
        ok=True, user_feedback=result.value, message="Annotation approved"
    )


def m_approve_annotation(
    info: strawberry.Info,
    annotation_id: Annotated[
        strawberry.ID,
        strawberry.argument(
            name="annotationId", description="ID of the annotation to approve"
        ),
    ] = strawberry.UNSET,
    comment: Annotated[
        str | None,
        strawberry.argument(
            name="comment", description="Optional comment for the approval"
        ),
    ] = strawberry.UNSET,
) -> ApproveAnnotation | None:
    kwargs = strip_unset({"annotation_id": annotation_id, "comment": comment})
    return _mutate_ApproveAnnotation(ApproveAnnotation, None, info, **kwargs)


def _mutate_RejectAnnotation(payload_cls, root, info, annotation_id, comment=None):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_mutations.py:113

    Port of RejectAnnotation.mutate
    """
    # @login_required (graphql_jwt) — inlined; see _mutate_AddAnnotation.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    from opencontractserver.feedback.services import UserFeedbackService

    annotation_pk = from_global_id(annotation_id)[1]
    result = UserFeedbackService.reject_annotation(
        info.context.user,
        annotation_pk,
        comment=comment,
        request=info.context,
    )
    if not result.ok:
        return payload_cls(ok=False, user_feedback=None, message=result.error)
    return payload_cls(
        ok=True, user_feedback=result.value, message="Annotation rejected"
    )


def m_reject_annotation(
    info: strawberry.Info,
    annotation_id: Annotated[
        strawberry.ID,
        strawberry.argument(
            name="annotationId", description="ID of the annotation to reject"
        ),
    ] = strawberry.UNSET,
    comment: Annotated[
        str | None,
        strawberry.argument(
            name="comment", description="Optional comment for the rejection"
        ),
    ] = strawberry.UNSET,
) -> RejectAnnotation | None:
    kwargs = strip_unset({"annotation_id": annotation_id, "comment": comment})
    return _mutate_RejectAnnotation(RejectAnnotation, None, info, **kwargs)


def _mutate_AddRelationship(
    payload_cls,
    root,
    info,
    source_ids,
    target_ids,
    relationship_label_id,
    corpus_id,
    document_id,
):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_mutations.py:969

    Port of AddRelationship.mutate
    """
    # @login_required (graphql_jwt) — inlined; see _mutate_AddAnnotation.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    user = info.context.user
    # Unified message blocks IDOR enumeration of corpora, documents, and
    # annotations the caller cannot see. Both "does not exist" and "no
    # permission" branches must collapse to this string.
    not_found_msg = (
        "Relationship target(s) not found or you do not have permission "
        "to create a relationship here."
    )

    try:
        # Cast each parsed pk to int so non-numeric payloads (a global ID
        # of "BogusType:not-an-int" decodes successfully but yields a
        # string pk) fail closed inside this try/except instead of later
        # at the queryset boundary. This keeps the IDOR surface flat:
        # every bad-input path collapses to ``not_found_msg``.
        source_pks = [int(from_global_id(graphene_id)[1]) for graphene_id in source_ids]
        target_pks = [int(from_global_id(graphene_id)[1]) for graphene_id in target_ids]
        relationship_label_pk = int(from_global_id(relationship_label_id)[1])
        corpus_pk = int(from_global_id(corpus_id)[1])
        document_pk = int(from_global_id(document_id)[1])
    except Exception:
        # Bad / unparseable / non-integer global IDs are indistinguishable
        # from not-found to keep the IDOR surface flat. ``Exception``
        # catches ``binascii.Error`` from ``from_global_id`` on
        # undecodable input AND ``ValueError`` from the ``int()`` cast.
        return payload_cls(ok=False, relationship=None, message=not_found_msg)

    # Filter annotations through the service-layer visibility filter so
    # unauthorized or non-existent IDs collapse into the same "missing"
    # branch. Comparing counts catches both cases without echoing IDs
    # back to the caller.
    source_annotations = BaseService.filter_visible(
        Annotation, user, request=info.context
    ).filter(id__in=source_pks)
    target_annotations = BaseService.filter_visible(
        Annotation, user, request=info.context
    ).filter(id__in=target_pks)
    if source_annotations.count() != len(
        set(source_pks)
    ) or target_annotations.count() != len(set(target_pks)):
        return payload_cls(ok=False, relationship=None, message=not_found_msg)

    # IDOR-safe corpus fetch + CREATE gate via the service layer.
    corpus = BaseService.get_or_none(Corpus, corpus_pk, user, request=info.context)
    if corpus is None or BaseService.require_permission(
        corpus, user, PermissionTypes.CREATE, request=info.context
    ):
        return payload_cls(ok=False, relationship=None, message=not_found_msg)

    # Document visibility check: without this, a caller with CREATE on
    # `corpus` could create a Relationship pointing at any document_id
    # they happen to guess — including documents in a corpus they cannot
    # see. Collapse the failure into the same not-found message to keep
    # the IDOR surface flat with the source/target/corpus checks above.
    if (
        not BaseService.filter_visible(Document, user, request=info.context)
        .filter(pk=document_pk)
        .exists()
    ):
        return payload_cls(ok=False, relationship=None, message=not_found_msg)

    # Relationship label visibility check: closes the residual oracle
    # where a caller could probe private ``AnnotationLabel`` IDs by
    # supplying them and observing whether the create succeeds vs.
    # raises an FK constraint. Same not-found message.
    if (
        not BaseService.filter_visible(AnnotationLabel, user, request=info.context)
        .filter(pk=relationship_label_pk)
        .exists()
    ):
        return payload_cls(ok=False, relationship=None, message=not_found_msg)

    try:
        relationship = Relationship.objects.create(
            creator=user,
            relationship_label_id=relationship_label_pk,
            corpus_id=corpus_pk,
            document_id=document_pk,
        )
        set_permissions_for_obj_to_user(
            user,
            relationship,
            [PermissionTypes.CRUD],
            is_new=True,
            request=info.context,
        )
        relationship.target_annotations.set(target_annotations)
        relationship.source_annotations.set(source_annotations)
    except Exception:
        # Don't surface ORM or constraint messages to the caller — they
        # leak schema/existence information. Log server-side instead.
        # ``logger.exception`` already appends the traceback + message,
        # so we omit the redundant exception variable.
        logger.exception("Error creating relationship")
        return payload_cls(
            ok=False,
            relationship=None,
            message="Error creating relationship.",
        )

    return payload_cls(
        ok=True,
        relationship=relationship,
        message="Relationship created successfully",
    )


def m_add_relationship(
    info: strawberry.Info,
    corpus_id: Annotated[
        str,
        strawberry.argument(
            name="corpusId", description="ID of the corpus for this relationship."
        ),
    ] = strawberry.UNSET,
    document_id: Annotated[
        str,
        strawberry.argument(
            name="documentId", description="ID of the document for this relationship."
        ),
    ] = strawberry.UNSET,
    relationship_label_id: Annotated[
        str,
        strawberry.argument(
            name="relationshipLabelId",
            description="ID of the label for this relationship.",
        ),
    ] = strawberry.UNSET,
    source_ids: Annotated[
        list[str | None],
        strawberry.argument(
            name="sourceIds",
            description="List of ids of the tokens in the source annotation",
        ),
    ] = strawberry.UNSET,
    target_ids: Annotated[
        list[str | None],
        strawberry.argument(
            name="targetIds",
            description="List of ids of the target tokens in the label",
        ),
    ] = strawberry.UNSET,
) -> AddRelationship | None:
    kwargs = strip_unset(
        {
            "corpus_id": corpus_id,
            "document_id": document_id,
            "relationship_label_id": relationship_label_id,
            "source_ids": source_ids,
            "target_ids": target_ids,
        }
    )
    return _mutate_AddRelationship(AddRelationship, None, info, **kwargs)


def _mutate_RemoveRelationship(payload_cls, root, info, relationship_id):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_mutations.py:906

    Port of RemoveRelationship.mutate
    """
    # @login_required (graphql_jwt) — inlined; see _mutate_AddAnnotation.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    try:
        user = info.context.user
        relationship_pk = from_global_id(relationship_id)[1]

        # IDOR-safe fetch via the service layer.
        relationship_obj = BaseService.get_or_none(
            Relationship, relationship_pk, user, request=info.context
        )
        if relationship_obj is None:
            return payload_cls(
                ok=False,
                message="Relationship not found or you do not have permission to access it",
            )

        # Check if user has permission to delete this relationship.
        if BaseService.require_permission(
            relationship_obj,
            user,
            PermissionTypes.DELETE,
            request=info.context,
        ):
            return payload_cls(
                ok=False,
                message="Relationship not found or you do not have permission to access it",
            )

        relationship_obj.delete()
        return payload_cls(ok=True, message="Relationship deleted successfully")
    except Exception as e:
        logger.error(f"Error deleting relationship {relationship_id}: {e}")
        return payload_cls(ok=False, message="An unexpected error occurred")


def m_remove_relationship(
    info: strawberry.Info,
    relationship_id: Annotated[
        str,
        strawberry.argument(
            name="relationshipId",
            description="Id of the relationship that is to be deleted.",
        ),
    ] = strawberry.UNSET,
) -> RemoveRelationship | None:
    kwargs = strip_unset({"relationship_id": relationship_id})
    return _mutate_RemoveRelationship(RemoveRelationship, None, info, **kwargs)


def _mutate_RemoveRelationships(payload_cls, root, info, relationship_ids):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_mutations.py:1097

    Port of RemoveRelationships.mutate
    """
    # @login_required (graphql_jwt) — inlined; see _mutate_AddAnnotation.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    user = info.context.user
    # Unified error message prevents IDOR enumeration of relationship IDs
    not_found_msg = "Relationship not found or you do not have permission to access it"
    for graphene_id in relationship_ids:
        pk = from_global_id(graphene_id)[1]
        relationship = BaseService.get_or_none(
            Relationship, pk, user, request=info.context
        )
        if relationship is None or BaseService.require_permission(
            relationship, user, PermissionTypes.DELETE, request=info.context
        ):
            return payload_cls(ok=False, message=not_found_msg)
        relationship.delete()
    return payload_cls(ok=True, message="Success")


def m_remove_relationships(
    info: strawberry.Info,
    relationship_ids: Annotated[
        list[str | None] | None, strawberry.argument(name="relationshipIds")
    ] = strawberry.UNSET,
) -> RemoveRelationships | None:
    kwargs = strip_unset({"relationship_ids": relationship_ids})
    return _mutate_RemoveRelationships(RemoveRelationships, None, info, **kwargs)


def _mutate_UpdateRelationship(
    payload_cls,
    root,
    info,
    relationship_id,
    add_source_ids=None,
    add_target_ids=None,
    remove_source_ids=None,
    remove_target_ids=None,
):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_mutations.py:1152

    Port of UpdateRelationship.mutate
    """
    # @login_required (graphql_jwt) — inlined; see _mutate_AddAnnotation.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    user = info.context.user
    # Unified error message prevents IDOR enumeration of relationship/annotation IDs
    not_found_msg = "Relationship not found or you do not have permission to access it"
    try:
        relationship_pk = from_global_id(relationship_id)[1]
        relationship = BaseService.get_or_none(
            Relationship, relationship_pk, user, request=info.context
        )
        if relationship is None or BaseService.require_permission(
            relationship, user, PermissionTypes.UPDATE, request=info.context
        ):
            return payload_cls(
                ok=False,
                relationship=None,
                message=not_found_msg,
            )

        # Filter annotations through the service-layer visibility filter
        # so unauthorized IDs are dropped at the DB layer instead of
        # after a per-row permission check.
        def _load_visible_annotations(global_ids):
            pks = {from_global_id(g)[1] for g in global_ids}
            return (
                list(
                    BaseService.filter_visible(
                        Annotation, user, request=info.context
                    ).filter(id__in=pks)
                ),
                pks,
            )

        # Add source annotations. The visibility filter already enforces
        # READ — every returned annotation is by definition readable, so
        # no per-row permission re-check is needed. Compare resolved PKs
        # against requested PKs as sets so the equivalence is unambiguous
        # under duplicate input IDs.
        if add_source_ids:
            source_annotations, source_pks = _load_visible_annotations(add_source_ids)
            if {str(a.pk) for a in source_annotations} != source_pks:
                return payload_cls(
                    ok=False,
                    relationship=None,
                    message=not_found_msg,
                )
            relationship.source_annotations.add(*source_annotations)

        # Add target annotations (same READ-via-visibility guarantee).
        if add_target_ids:
            target_annotations, target_pks = _load_visible_annotations(add_target_ids)
            if {str(a.pk) for a in target_annotations} != target_pks:
                return payload_cls(
                    ok=False,
                    relationship=None,
                    message=not_found_msg,
                )
            relationship.target_annotations.add(*target_annotations)

        # Removal is gated by UPDATE on the relationship itself (already
        # checked above). Restrict removal to annotations actually attached
        # to this relationship to avoid leaking the existence of unrelated
        # annotation IDs the caller may not be able to see.
        if remove_source_ids:
            source_pks = [from_global_id(sid)[1] for sid in remove_source_ids]
            relationship.source_annotations.remove(
                *relationship.source_annotations.filter(id__in=source_pks)
            )

        if remove_target_ids:
            target_pks = [from_global_id(tid)[1] for tid in remove_target_ids]
            relationship.target_annotations.remove(
                *relationship.target_annotations.filter(id__in=target_pks)
            )

        relationship.save()

        return payload_cls(
            ok=True,
            relationship=relationship,
            message="Relationship updated successfully",
        )

    except Exception as e:
        logger.error(f"Error updating relationship: {e}")
        return payload_cls(
            ok=False,
            relationship=None,
            message=f"Error updating relationship: {str(e)}",
        )


def m_update_relationship(
    info: strawberry.Info,
    add_source_ids: Annotated[
        list[str | None] | None,
        strawberry.argument(
            name="addSourceIds", description="List of annotation IDs to add as sources"
        ),
    ] = strawberry.UNSET,
    add_target_ids: Annotated[
        list[str | None] | None,
        strawberry.argument(
            name="addTargetIds", description="List of annotation IDs to add as targets"
        ),
    ] = strawberry.UNSET,
    relationship_id: Annotated[
        str,
        strawberry.argument(
            name="relationshipId", description="ID of the relationship to update"
        ),
    ] = strawberry.UNSET,
    remove_source_ids: Annotated[
        list[str | None] | None,
        strawberry.argument(
            name="removeSourceIds",
            description="List of annotation IDs to remove from sources",
        ),
    ] = strawberry.UNSET,
    remove_target_ids: Annotated[
        list[str | None] | None,
        strawberry.argument(
            name="removeTargetIds",
            description="List of annotation IDs to remove from targets",
        ),
    ] = strawberry.UNSET,
) -> UpdateRelationship | None:
    kwargs = strip_unset(
        {
            "add_source_ids": add_source_ids,
            "add_target_ids": add_target_ids,
            "relationship_id": relationship_id,
            "remove_source_ids": remove_source_ids,
            "remove_target_ids": remove_target_ids,
        }
    )
    return _mutate_UpdateRelationship(UpdateRelationship, None, info, **kwargs)


def _mutate_UpdateRelations(payload_cls, root, info, relationships):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_mutations.py:1290

    Port of UpdateRelations.mutate

    graphene passed ``RelationInputType`` items as dict-like objects
    (``relationship["id"]``); strawberry passes dataclass instances, so
    the fields are read via attribute access.
    """
    # @login_required (graphql_jwt) — inlined; see _mutate_AddAnnotation.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    user = info.context.user
    # Unified error message prevents IDOR enumeration of relationship IDs
    not_found_msg = "Relationship not found or you do not have permission to access it"
    for relationship in relationships:
        pk = from_global_id(relationship.id)[1]
        source_pks = list(
            map(
                lambda graphene_id: from_global_id(graphene_id)[1],
                relationship.source_ids,
            )
        )
        target_pks = list(
            map(
                lambda graphene_id: from_global_id(graphene_id)[1],
                relationship.target_ids,
            )
        )
        relationship_label_pk = from_global_id(relationship.relationship_label_id)[1]
        corpus_pk = from_global_id(relationship.corpus_id)[1]
        document_pk = from_global_id(relationship.document_id)[1]

        relationship = BaseService.get_or_none(
            Relationship, pk, user, request=info.context
        )
        if relationship is None or BaseService.require_permission(
            relationship, user, PermissionTypes.UPDATE, request=info.context
        ):
            return payload_cls(ok=False, message=not_found_msg)

        relationship.relationship_label_id = relationship_label_pk
        relationship.document_id = document_pk
        relationship.corpus_id = corpus_pk
        relationship.save()

        relationship.target_annotations.set(target_pks)
        relationship.source_annotations.set(source_pks)

    return payload_cls(ok=True, message="Success")


def m_update_relationships(
    info: strawberry.Info,
    relationships: Annotated[
        None
        | (
            list[
                None
                | (
                    Annotated[
                        RelationInputType,
                        strawberry.lazy("config.graphql.annotation_types"),
                    ]
                )
            ]
        ),
        strawberry.argument(name="relationships"),
    ] = strawberry.UNSET,
) -> UpdateRelations | None:
    kwargs = strip_unset({"relationships": relationships})
    return _mutate_UpdateRelations(UpdateRelations, None, info, **kwargs)


def _mutate_UpdateNote(payload_cls, root, info, note_id, new_content, title=None):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_mutations.py:1356

    Port of UpdateNote.mutate
    """
    # @login_required (graphql_jwt) — inlined; see _mutate_AddAnnotation.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    from opencontractserver.annotations.models import Note

    try:
        user = info.context.user
        note_pk = from_global_id(note_id)[1]

        # Unified "not found" message avoids leaking note existence to non-creators
        not_found_msg = "Note not found or you do not have permission to update it."

        # Service-layer IDOR-safe fetch so unauthorized IDs hit the same
        # branch as truly-missing IDs.
        note = BaseService.get_or_none(Note, note_pk, user, request=info.context)
        if note is None:
            return payload_cls(ok=False, message=not_found_msg, obj=None, version=None)

        # Only the creator may edit a note (visibility != edit rights)
        if note.creator != user:
            return payload_cls(
                ok=False,
                message=not_found_msg,
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
            return payload_cls(
                ok=True,
                message="No changes detected. Note remains at current version.",
                obj=note,
                version=note.revisions.count(),
            )

        # Refresh the note to get the updated state
        note.refresh_from_db()

        return payload_cls(
            ok=True,
            message=f"Note updated successfully. Now at version {revision.version}.",
            obj=note,
            version=revision.version,
        )

    except Exception as e:
        logger.error(f"Error updating note: {e}")
        return payload_cls(
            ok=False,
            message=f"Failed to update note: {str(e)}",
            obj=None,
            version=None,
        )


def m_update_note(
    info: strawberry.Info,
    new_content: Annotated[
        str,
        strawberry.argument(
            name="newContent", description="New markdown content for the note"
        ),
    ] = strawberry.UNSET,
    note_id: Annotated[
        strawberry.ID,
        strawberry.argument(name="noteId", description="ID of the note to update"),
    ] = strawberry.UNSET,
    title: Annotated[
        str | None,
        strawberry.argument(
            name="title", description="Optional new title for the note"
        ),
    ] = strawberry.UNSET,
) -> UpdateNote | None:
    kwargs = strip_unset(
        {"new_content": new_content, "note_id": note_id, "title": title}
    )
    return _mutate_UpdateNote(UpdateNote, None, info, **kwargs)


def m_delete_note(
    info: strawberry.Info,
    id: Annotated[str, strawberry.argument(name="id")] = strawberry.UNSET,
) -> DeleteNote | None:
    kwargs = strip_unset({"id": id})
    return drf_deletion(
        payload_cls=DeleteNote,
        model=Note,
        lookup_field="id",
        root=None,
        info=info,
        kwargs=kwargs,
    )


def _mutate_CreateNote(
    payload_cls, root, info, document_id, title, content, corpus_id=None, parent_id=None
):
    """PORT: /home/user/oc-graphene-ref/config/graphql/annotation_mutations.py:1459

    Port of CreateNote.mutate
    """
    # @login_required (graphql_jwt) — inlined; see _mutate_AddAnnotation.
    if not info.context.user.is_authenticated:
        raise PermissionDenied()

    from opencontractserver.annotations.models import Note
    from opencontractserver.corpuses.models import Corpus
    from opencontractserver.documents.models import Document

    try:
        user = info.context.user
        document_pk = from_global_id(document_id)[1]

        # IDOR-safe document fetch via the service layer.
        document = BaseService.get_or_none(
            Document, document_pk, user, request=info.context
        )
        if document is None:
            raise Document.DoesNotExist

        # Prepare note data
        note_data = {
            "document": document,
            "title": title,
            "content": content,
            "creator": user,
        }

        # Handle optional corpus with IDOR-safe service-layer fetch.
        if corpus_id:
            corpus_pk = from_global_id(corpus_id)[1]
            corpus = BaseService.get_or_none(
                Corpus, corpus_pk, user, request=info.context
            )
            if corpus is None:
                raise Corpus.DoesNotExist
            note_data["corpus"] = corpus

        # Handle optional parent note with IDOR-safe service-layer fetch.
        if parent_id:
            parent_pk = from_global_id(parent_id)[1]
            parent_note = BaseService.get_or_none(
                Note, parent_pk, user, request=info.context
            )
            if parent_note is None:
                raise Note.DoesNotExist
            note_data["parent"] = parent_note

        # Create the note
        note = Note.objects.create(**note_data)

        # Set permissions
        set_permissions_for_obj_to_user(
            user,
            note,
            [PermissionTypes.CRUD],
            is_new=True,
            request=info.context,
        )

        return payload_cls(ok=True, message="Note created successfully!", obj=note)

    except Document.DoesNotExist:
        return payload_cls(ok=False, message="Document not found.", obj=None)
    except Corpus.DoesNotExist:
        return payload_cls(ok=False, message="Corpus not found.", obj=None)
    except Note.DoesNotExist:
        return payload_cls(ok=False, message="Parent note not found.", obj=None)
    except Exception as e:
        logger.error(f"Error creating note: {e}")
        return payload_cls(
            ok=False, message=f"Failed to create note: {str(e)}", obj=None
        )


def m_create_note(
    info: strawberry.Info,
    content: Annotated[
        str,
        strawberry.argument(name="content", description="Markdown content of the note"),
    ] = strawberry.UNSET,
    corpus_id: Annotated[
        strawberry.ID | None,
        strawberry.argument(
            name="corpusId",
            description="Optional ID of the corpus this note is associated with",
        ),
    ] = strawberry.UNSET,
    document_id: Annotated[
        strawberry.ID,
        strawberry.argument(
            name="documentId", description="ID of the document this note is for"
        ),
    ] = strawberry.UNSET,
    parent_id: Annotated[
        strawberry.ID | None,
        strawberry.argument(
            name="parentId",
            description="Optional ID of parent note for hierarchical notes",
        ),
    ] = strawberry.UNSET,
    title: Annotated[
        str, strawberry.argument(name="title", description="Title of the note")
    ] = strawberry.UNSET,
) -> CreateNote | None:
    kwargs = strip_unset(
        {
            "content": content,
            "corpus_id": corpus_id,
            "document_id": document_id,
            "parent_id": parent_id,
            "title": title,
        }
    )
    return _mutate_CreateNote(CreateNote, None, info, **kwargs)


MUTATION_FIELDS = {
    "add_annotation": strawberry.field(resolver=m_add_annotation, name="addAnnotation"),
    "add_url_annotation": strawberry.field(
        resolver=m_add_url_annotation,
        name="addUrlAnnotation",
        description="Create an annotation labelled ``OC_URL`` with a click-through URL.\n\nConvenience wrapper over ``AddAnnotation``: ensures the corpus has an\n``OC_URL`` label (creating it if absent) and stamps ``link_url`` on the\nresulting annotation so the frontend renders the highlighted text as a\nclickable hyperlink.",
    ),
    "add_country_annotation": strawberry.field(
        resolver=m_add_country_annotation,
        name="addCountryAnnotation",
        description="Create an annotation labelled ``OC_COUNTRY`` with offline-geocoded data.\n\nMirrors :class:`AddUrlAnnotation` but routes through the bundled\ngeocoding service (see :mod:`opencontractserver.utils.geocoding`).\n``country_hint`` is intentionally absent — the country lookup is\nself-disambiguating.",
    ),
    "add_state_annotation": strawberry.field(
        resolver=m_add_state_annotation,
        name="addStateAnnotation",
        description="Create an annotation labelled ``OC_STATE`` with offline-geocoded data.\n\n``country_hint`` narrows the candidate pool to a single country; today\nthe bundled state dataset is US-only, so the hint mostly exists as a\nforward-compatibility hook for when non-US first-level admin\ndivisions are added.",
    ),
    "add_city_annotation": strawberry.field(
        resolver=m_add_city_annotation,
        name="addCityAnnotation",
        description='Create an annotation labelled ``OC_CITY`` with offline-geocoded data.\n\n``country_hint`` / ``state_hint`` resolve via the same indexes the\nmain lookup uses, so any recognised form ("France" / "FR" / "Texas"\n/ "TX") works. Hints narrow the candidate pool BEFORE the\nexact / alias / fuzzy chain runs, so a hinted ambiguous string\n(e.g. "Paris" + state_hint="TX") prefers the right row even when\nmultiple rows are exact name matches.',
    ),
    "remove_annotation": strawberry.field(
        resolver=m_remove_annotation, name="removeAnnotation"
    ),
    "update_annotation": strawberry.field(
        resolver=m_update_annotation, name="updateAnnotation"
    ),
    "add_doc_type_annotation": strawberry.field(
        resolver=m_add_doc_type_annotation, name="addDocTypeAnnotation"
    ),
    "remove_doc_type_annotation": strawberry.field(
        resolver=m_remove_doc_type_annotation, name="removeDocTypeAnnotation"
    ),
    "approve_annotation": strawberry.field(
        resolver=m_approve_annotation, name="approveAnnotation"
    ),
    "reject_annotation": strawberry.field(
        resolver=m_reject_annotation, name="rejectAnnotation"
    ),
    "add_relationship": strawberry.field(
        resolver=m_add_relationship, name="addRelationship"
    ),
    "remove_relationship": strawberry.field(
        resolver=m_remove_relationship, name="removeRelationship"
    ),
    "remove_relationships": strawberry.field(
        resolver=m_remove_relationships, name="removeRelationships"
    ),
    "update_relationship": strawberry.field(
        resolver=m_update_relationship,
        name="updateRelationship",
        description="Update an existing relationship by adding or removing annotations\nfrom source or target sets.",
    ),
    "update_relationships": strawberry.field(
        resolver=m_update_relationships, name="updateRelationships"
    ),
    "update_note": strawberry.field(
        resolver=m_update_note,
        name="updateNote",
        description="Mutation to update a note's content, creating a new version in the process.\nOnly the note creator can update their notes.",
    ),
    "delete_note": strawberry.field(
        resolver=m_delete_note,
        name="deleteNote",
        description="Mutation to delete a note. Only the creator can delete their notes.",
    ),
    "create_note": strawberry.field(
        resolver=m_create_note,
        name="createNote",
        description="Mutation to create a new note for a document.",
    ),
}
