"""
GraphQL mutations for annotation, relationship, and note operations.
"""

import logging
from typing import Any, Literal

import graphene
from django.core.exceptions import ValidationError
from django.db import transaction
from graphene.types.generic import GenericScalar
from graphql_jwt.decorators import login_required
from graphql_relay import from_global_id

from config.graphql.base import DRFDeletion, DRFMutation
from config.graphql.graphene_types import (
    AnnotationType,
    NoteType,
    RelationInputType,
    RelationshipType,
    UserFeedbackType,
)
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


class RemoveAnnotation(graphene.Mutation):
    class Arguments:
        annotation_id = graphene.String(
            required=True, description="Id of the annotation that is to be deleted."
        )

    ok = graphene.Boolean()
    message = graphene.String()

    @login_required
    def mutate(root, info, annotation_id) -> "RemoveAnnotation":
        try:
            user = info.context.user
            annotation_pk = from_global_id(annotation_id)[1]

            # IDOR-safe fetch via the service layer — unified error message
            # for not found and not permitted prevents enumeration.
            annotation_obj = BaseService.get_or_none(
                Annotation, annotation_pk, user, request=info.context
            )
            if annotation_obj is None:
                return RemoveAnnotation(
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
                return RemoveAnnotation(
                    ok=False,
                    message="Annotation not found or you do not have permission to access it",
                )

            annotation_obj.delete()
            return RemoveAnnotation(ok=True, message="Annotation deleted successfully")
        except Exception as e:
            logger.error(f"Error deleting annotation {annotation_id}: {e}")
            return RemoveAnnotation(ok=False, message="An unexpected error occurred")


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
    def mutate(root, info, annotation_id, comment=None) -> "RejectAnnotation":
        from opencontractserver.feedback.services import UserFeedbackService

        annotation_pk = from_global_id(annotation_id)[1]
        result = UserFeedbackService.reject_annotation(
            info.context.user,
            annotation_pk,
            comment=comment,
            request=info.context,
        )
        if not result.ok:
            return RejectAnnotation(ok=False, user_feedback=None, message=result.error)
        return RejectAnnotation(
            ok=True, user_feedback=result.value, message="Annotation rejected"
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
    def mutate(root, info, annotation_id, comment=None) -> "ApproveAnnotation":
        from opencontractserver.feedback.services import UserFeedbackService

        annotation_pk = from_global_id(annotation_id)[1]
        result = UserFeedbackService.approve_annotation(
            info.context.user,
            annotation_pk,
            comment=comment,
            request=info.context,
        )
        if not result.ok:
            return ApproveAnnotation(ok=False, user_feedback=None, message=result.error)
        return ApproveAnnotation(
            ok=True, user_feedback=result.value, message="Annotation approved"
        )


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
) -> tuple["Document", "Corpus"] | None:
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
        long_description = graphene.String(
            required=False,
            description="Optional markdown description for this annotation.",
        )
        link_url = graphene.String(
            required=False,
            description=(
                "Optional URL opened on click. Restricted to http(s):// or "
                "site-relative paths; intended for OC_URL annotations."
            ),
        )

    ok = graphene.Boolean()
    message = graphene.String()
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
        long_description=None,
        link_url=None,
    ) -> "AddAnnotation":
        corpus_pk = from_global_id(corpus_id)[1]
        document_pk = from_global_id(document_id)[1]
        label_pk = from_global_id(annotation_label_id)[1]

        user = info.context.user

        if link_url:
            try:
                validate_link_url(link_url)
            except ValidationError as exc:
                return AddAnnotation(
                    ok=False, annotation=None, message=_format_link_url_error(exc)
                )

        parents = _resolve_annotation_parents(
            user, corpus_pk, document_pk, request=info.context
        )
        if parents is None:
            return AddAnnotation(
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

        return AddAnnotation(
            ok=True, message="Annotation created", annotation=annotation
        )


class AddUrlAnnotation(graphene.Mutation):
    """Create an annotation labelled ``OC_URL`` with a click-through URL.

    Convenience wrapper over ``AddAnnotation``: ensures the corpus has an
    ``OC_URL`` label (creating it if absent) and stamps ``link_url`` on the
    resulting annotation so the frontend renders the highlighted text as a
    clickable hyperlink.
    """

    class Arguments:
        json = GenericScalar(
            required=True, description="New-style JSON for multipage annotations."
        )
        page = graphene.Int(
            required=True, description="What page is this annotation on (0-indexed)."
        )
        raw_text = graphene.String(
            required=True, description="The raw text being linked."
        )
        corpus_id = graphene.String(
            required=True, description="ID of the corpus this annotation is for."
        )
        document_id = graphene.String(
            required=True, description="ID of the document this annotation is on."
        )
        annotation_type = graphene.Argument(
            graphene.Enum.from_enum(LabelType),
            required=True,
            description="Annotation type: TOKEN_LABEL for PDFs, SPAN_LABEL for text.",
        )
        link_url = graphene.String(
            required=True,
            description="The target URL to open on click.",
        )

    ok = graphene.Boolean()
    message = graphene.String()
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
        annotation_type,
        link_url,
    ) -> "AddUrlAnnotation":
        corpus_pk = from_global_id(corpus_id)[1]
        document_pk = from_global_id(document_id)[1]

        user = info.context.user

        try:
            validate_link_url(link_url)
        except ValidationError as exc:
            return AddUrlAnnotation(
                ok=False, annotation=None, message=_format_link_url_error(exc)
            )

        parents = _resolve_annotation_parents(
            user, corpus_pk, document_pk, request=info.context
        )
        if parents is None:
            return AddUrlAnnotation(
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

        return AddUrlAnnotation(
            ok=True, message="URL annotation created", annotation=annotation
        )


# --------------------------------------------------------------------------- #
# Geographic auto-creating annotation mutations — issue #1819
# --------------------------------------------------------------------------- #
# Each of the three mutations below mirrors ``AddUrlAnnotation`` (auto-creates
# the corresponding OC_* label on first use, ensures the corpus has a label
# set) but with one extra step: the supplied span text is fed to the offline
# geocoding service (``opencontractserver/utils/geocoding``) and the resolver
# result is stamped into ``Annotation.data`` so the map aggregation service
# (#1820 / #1821) can group pins without ever re-running the geocoder.
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
) -> tuple[bool, str, "Annotation | None"]:
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


class AddCountryAnnotation(graphene.Mutation):
    """Create an annotation labelled ``OC_COUNTRY`` with offline-geocoded data.

    Mirrors :class:`AddUrlAnnotation` but routes through the bundled
    geocoding service (see :mod:`opencontractserver.utils.geocoding`).
    ``country_hint`` is intentionally absent — the country lookup is
    self-disambiguating.
    """

    class Arguments:
        json = GenericScalar(
            required=True, description="New-style JSON for multipage annotations."
        )
        page = graphene.Int(
            required=True, description="What page is this annotation on (0-indexed)."
        )
        raw_text = graphene.String(
            required=True,
            description="The raw text identifying the country (e.g. 'France', 'FR').",
        )
        corpus_id = graphene.String(
            required=True, description="ID of the corpus this annotation is for."
        )
        document_id = graphene.String(
            required=True, description="ID of the document this annotation is on."
        )
        annotation_type = graphene.Argument(
            graphene.Enum.from_enum(LabelType),
            required=True,
            description="Annotation type: TOKEN_LABEL for PDFs, SPAN_LABEL for text.",
        )

    ok = graphene.Boolean()
    message = graphene.String()
    annotation = graphene.Field(AnnotationType)
    geocoded = graphene.Boolean(
        description=(
            "True if the offline geocoder resolved the span; False when "
            "the annotation was created but no map pin was generated."
        )
    )

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
        annotation_type,
    ) -> "AddCountryAnnotation":
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
        return AddCountryAnnotation(
            ok=ok,
            message=message,
            annotation=annotation,
            geocoded=bool(
                annotation and annotation.data and annotation.data.get("geocoded")
            ),
        )


class AddStateAnnotation(graphene.Mutation):
    """Create an annotation labelled ``OC_STATE`` with offline-geocoded data.

    ``country_hint`` narrows the candidate pool to a single country; today
    the bundled state dataset is US-only, so the hint mostly exists as a
    forward-compatibility hook for when non-US first-level admin
    divisions are added.
    """

    class Arguments:
        json = GenericScalar(required=True)
        page = graphene.Int(required=True)
        raw_text = graphene.String(
            required=True,
            description="The raw text identifying the state (e.g. 'Texas', 'TX').",
        )
        corpus_id = graphene.String(required=True)
        document_id = graphene.String(required=True)
        annotation_type = graphene.Argument(
            graphene.Enum.from_enum(LabelType), required=True
        )
        country_hint = graphene.String(
            required=False,
            description=(
                "Optional country to disambiguate the state (default: "
                "United States, the only first-level admin set bundled today)."
            ),
        )

    ok = graphene.Boolean()
    message = graphene.String()
    annotation = graphene.Field(AnnotationType)
    geocoded = graphene.Boolean(
        description=(
            "True if the offline geocoder resolved the span; False when "
            "the annotation was created but no map pin was generated."
        )
    )

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
        annotation_type,
        country_hint=None,
    ) -> "AddStateAnnotation":
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
        return AddStateAnnotation(
            ok=ok,
            message=message,
            annotation=annotation,
            geocoded=bool(
                annotation and annotation.data and annotation.data.get("geocoded")
            ),
        )


class AddCityAnnotation(graphene.Mutation):
    """Create an annotation labelled ``OC_CITY`` with offline-geocoded data.

    ``country_hint`` / ``state_hint`` resolve via the same indexes the
    main lookup uses, so any recognised form ("France" / "FR" / "Texas"
    / "TX") works. Hints narrow the candidate pool BEFORE the
    exact / alias / fuzzy chain runs, so a hinted ambiguous string
    (e.g. "Paris" + state_hint="TX") prefers the right row even when
    multiple rows are exact name matches.
    """

    class Arguments:
        json = GenericScalar(required=True)
        page = graphene.Int(required=True)
        raw_text = graphene.String(
            required=True,
            description=(
                "The raw text identifying the city. Disambiguation hints "
                "are recommended for ambiguous names (e.g. 'Paris', 'Springfield')."
            ),
        )
        corpus_id = graphene.String(required=True)
        document_id = graphene.String(required=True)
        annotation_type = graphene.Argument(
            graphene.Enum.from_enum(LabelType), required=True
        )
        country_hint = graphene.String(
            required=False,
            description="Optional country to narrow candidate cities.",
        )
        state_hint = graphene.String(
            required=False,
            description=(
                "Optional state / first-level admin division "
                "(only applied when the country is the US in the bundled dataset)."
            ),
        )

    ok = graphene.Boolean()
    message = graphene.String()
    annotation = graphene.Field(AnnotationType)
    geocoded = graphene.Boolean(
        description=(
            "True if the offline geocoder resolved the span; False when "
            "the annotation was created but no map pin was generated."
        )
    )

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
        annotation_type,
        country_hint=None,
        state_hint=None,
    ) -> "AddCityAnnotation":
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
        return AddCityAnnotation(
            ok=ok,
            message=message,
            annotation=annotation,
            geocoded=bool(
                annotation and annotation.data and annotation.data.get("geocoded")
            ),
        )


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
    message = graphene.String()
    annotation = graphene.Field(AnnotationType)

    @login_required
    def mutate(
        root, info, corpus_id, document_id, annotation_label_id
    ) -> "AddDocTypeAnnotation":
        corpus_pk = from_global_id(corpus_id)[1]
        document_pk = from_global_id(document_id)[1]
        annotation_label_pk = from_global_id(annotation_label_id)[1]

        user = info.context.user

        parents = _resolve_annotation_parents(
            user, corpus_pk, document_pk, request=info.context
        )
        if parents is None:
            return AddDocTypeAnnotation(
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

        return AddDocTypeAnnotation(
            ok=True, message="Annotation created", annotation=annotation
        )


class RemoveRelationship(graphene.Mutation):
    class Arguments:
        relationship_id = graphene.String(
            required=True, description="Id of the relationship that is to be deleted."
        )

    ok = graphene.Boolean()
    message = graphene.String()

    @login_required
    def mutate(root, info, relationship_id) -> "RemoveRelationship":
        try:
            user = info.context.user
            relationship_pk = from_global_id(relationship_id)[1]

            # IDOR-safe fetch via the service layer.
            relationship_obj = BaseService.get_or_none(
                Relationship, relationship_pk, user, request=info.context
            )
            if relationship_obj is None:
                return RemoveRelationship(
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
                return RemoveRelationship(
                    ok=False,
                    message="Relationship not found or you do not have permission to access it",
                )

            relationship_obj.delete()
            return RemoveRelationship(
                ok=True, message="Relationship deleted successfully"
            )
        except Exception as e:
            logger.error(f"Error deleting relationship {relationship_id}: {e}")
            return RemoveRelationship(ok=False, message="An unexpected error occurred")


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
    ) -> "AddRelationship":
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
            source_pks = [
                int(from_global_id(graphene_id)[1]) for graphene_id in source_ids
            ]
            target_pks = [
                int(from_global_id(graphene_id)[1]) for graphene_id in target_ids
            ]
            relationship_label_pk = int(from_global_id(relationship_label_id)[1])
            corpus_pk = int(from_global_id(corpus_id)[1])
            document_pk = int(from_global_id(document_id)[1])
        except Exception:
            # Bad / unparseable / non-integer global IDs are indistinguishable
            # from not-found to keep the IDOR surface flat. ``Exception``
            # catches ``binascii.Error`` from ``from_global_id`` on
            # undecodable input AND ``ValueError`` from the ``int()`` cast.
            return AddRelationship(ok=False, relationship=None, message=not_found_msg)

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
            return AddRelationship(ok=False, relationship=None, message=not_found_msg)

        # IDOR-safe corpus fetch + CREATE gate via the service layer.
        corpus = BaseService.get_or_none(Corpus, corpus_pk, user, request=info.context)
        if corpus is None or BaseService.require_permission(
            corpus, user, PermissionTypes.CREATE, request=info.context
        ):
            return AddRelationship(ok=False, relationship=None, message=not_found_msg)

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
            return AddRelationship(ok=False, relationship=None, message=not_found_msg)

        # Relationship label visibility check: closes the residual oracle
        # where a caller could probe private ``AnnotationLabel`` IDs by
        # supplying them and observing whether the create succeeds vs.
        # raises an FK constraint. Same not-found message.
        if (
            not BaseService.filter_visible(AnnotationLabel, user, request=info.context)
            .filter(pk=relationship_label_pk)
            .exists()
        ):
            return AddRelationship(ok=False, relationship=None, message=not_found_msg)

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
            return AddRelationship(
                ok=False,
                relationship=None,
                message="Error creating relationship.",
            )

        return AddRelationship(
            ok=True,
            relationship=relationship,
            message="Relationship created successfully",
        )


class RemoveRelationships(graphene.Mutation):
    class Arguments:
        relationship_ids = graphene.List(graphene.String)

    ok = graphene.Boolean()
    message = graphene.String()

    @login_required
    def mutate(root, info, relationship_ids) -> "RemoveRelationships":
        user = info.context.user
        # Unified error message prevents IDOR enumeration of relationship IDs
        not_found_msg = (
            "Relationship not found or you do not have permission to access it"
        )
        for graphene_id in relationship_ids:
            pk = from_global_id(graphene_id)[1]
            relationship = BaseService.get_or_none(
                Relationship, pk, user, request=info.context
            )
            if relationship is None or BaseService.require_permission(
                relationship, user, PermissionTypes.DELETE, request=info.context
            ):
                return RemoveRelationships(ok=False, message=not_found_msg)
            relationship.delete()
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
    ) -> "UpdateRelationship":
        user = info.context.user
        # Unified error message prevents IDOR enumeration of relationship/annotation IDs
        not_found_msg = (
            "Relationship not found or you do not have permission to access it"
        )
        try:
            relationship_pk = from_global_id(relationship_id)[1]
            relationship = BaseService.get_or_none(
                Relationship, relationship_pk, user, request=info.context
            )
            if relationship is None or BaseService.require_permission(
                relationship, user, PermissionTypes.UPDATE, request=info.context
            ):
                return UpdateRelationship(
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
                source_annotations, source_pks = _load_visible_annotations(
                    add_source_ids
                )
                if {str(a.pk) for a in source_annotations} != source_pks:
                    return UpdateRelationship(
                        ok=False,
                        relationship=None,
                        message=not_found_msg,
                    )
                relationship.source_annotations.add(*source_annotations)

            # Add target annotations (same READ-via-visibility guarantee).
            if add_target_ids:
                target_annotations, target_pks = _load_visible_annotations(
                    add_target_ids
                )
                if {str(a.pk) for a in target_annotations} != target_pks:
                    return UpdateRelationship(
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

            return UpdateRelationship(
                ok=True,
                relationship=relationship,
                message="Relationship updated successfully",
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
        long_description = graphene.String()
        json = GenericScalar()
        annotation_label = graphene.String()
        link_url = graphene.String(
            required=False,
            description=(
                "Optional click-through URL for OC_URL annotations. Pass an "
                "empty string to clear an existing URL. Restricted to "
                "http(s):// or site-relative paths."
            ),
        )


class UpdateRelations(graphene.Mutation):
    class Arguments:
        relationships = graphene.List(RelationInputType)

    ok = graphene.Boolean()
    message = graphene.String()

    @login_required
    def mutate(root, info, relationships) -> "UpdateRelations":
        user = info.context.user
        # Unified error message prevents IDOR enumeration of relationship IDs
        not_found_msg = (
            "Relationship not found or you do not have permission to access it"
        )
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

            relationship = BaseService.get_or_none(
                Relationship, pk, user, request=info.context
            )
            if relationship is None or BaseService.require_permission(
                relationship, user, PermissionTypes.UPDATE, request=info.context
            ):
                return UpdateRelations(ok=False, message=not_found_msg)

            relationship.relationship_label_id = relationship_label_pk
            relationship.document_id = document_pk
            relationship.corpus_id = corpus_pk
            relationship.save()

            relationship.target_annotations.set(target_pks)
            relationship.source_annotations.set(source_pks)

        return UpdateRelations(ok=True, message="Success")


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
    def mutate(root, info, note_id, new_content, title=None) -> "UpdateNote":
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
                return UpdateNote(
                    ok=False, message=not_found_msg, obj=None, version=None
                )

            # Only the creator may edit a note (visibility != edit rights)
            if note.creator != user:
                return UpdateNote(
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
    def mutate(
        root, info, document_id, title, content, corpus_id=None, parent_id=None
    ) -> "CreateNote":
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
