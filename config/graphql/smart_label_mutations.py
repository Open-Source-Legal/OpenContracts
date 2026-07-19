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
from typing import Annotated

import strawberry
from django.db import transaction
from graphql_relay import from_global_id

from config.graphql._util import strip_unset
from config.graphql.core.auth import PermissionDenied
from config.graphql.core.relay import (
    register_type,
)
from config.graphql.validation_utils import validate_color
from opencontractserver.annotations.models import AnnotationLabel, LabelSet
from opencontractserver.corpuses.models import Corpus
from opencontractserver.shared.services.base import BaseService
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

logger = logging.getLogger(__name__)


@strawberry.type(
    name="SmartLabelSearchOrCreateMutation",
    description="Smart mutation that handles label search and creation with automatic labelset management.\n\nThis mutation encapsulates the following logic:\n1. If no labelset exists for the corpus and createIfNotFound is true:\n   - Creates a new labelset\n   - Assigns it to the corpus\n   - Creates the label in the new labelset\n\n2. If labelset exists:\n   - Searches for existing labels matching the search term\n   - If matches found: returns the matching labels\n   - If no matches and createIfNotFound is true: creates the label\n   - If no matches and createIfNotFound is false: returns empty list",
)
class SmartLabelSearchOrCreateMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    labels: None | (
        list[
            None
            | (
                Annotated[
                    AnnotationLabelType,
                    strawberry.lazy("config.graphql.annotation_types"),
                ]
            )
        ]
    ) = strawberry.field(
        name="labels", description="List of matching or created labels", default=None
    )
    labelset: None | (
        Annotated[LabelSetType, strawberry.lazy("config.graphql.annotation_types")]
    ) = strawberry.field(
        name="labelset",
        description="The labelset (existing or newly created)",
        default=None,
    )
    labelset_created: bool | None = strawberry.field(
        name="labelsetCreated",
        description="Whether a new labelset was created",
        default=None,
    )
    label_created: bool | None = strawberry.field(
        name="labelCreated", description="Whether a new label was created", default=None
    )


register_type(
    "SmartLabelSearchOrCreateMutation", SmartLabelSearchOrCreateMutation, model=None
)


@strawberry.type(
    name="SmartLabelListMutation",
    description="Simplified mutation to get all available labels for a corpus with helpful status info.",
)
class SmartLabelListMutation:
    ok: bool | None = strawberry.field(name="ok", default=None)
    message: str | None = strawberry.field(name="message", default=None)
    labels: None | (
        list[
            None
            | (
                Annotated[
                    AnnotationLabelType,
                    strawberry.lazy("config.graphql.annotation_types"),
                ]
            )
        ]
    ) = strawberry.field(name="labels", default=None)
    has_labelset: bool | None = strawberry.field(name="hasLabelset", default=None)
    can_create_labels: bool | None = strawberry.field(
        name="canCreateLabels", default=None
    )


register_type("SmartLabelListMutation", SmartLabelListMutation, model=None)


@transaction.atomic
def _mutate_SmartLabelSearchOrCreateMutation(
    payload_cls,
    root,
    info,
    corpus_id: str,
    search_term: str,
    label_type: str,
    color: str = "#1a75bc",
    description: str = "",
    icon: str = "tag",
    create_if_not_found: bool = False,
    labelset_title: str | None = None,
    labelset_description: str = "",
):
    """PORT: /home/user/oc-graphene-ref/config/graphql/smart_label_mutations.py:94

    Port of SmartLabelSearchOrCreateMutation.mutate
    """
    # @login_required — inlined (mutate stub takes ``payload_cls`` first,
    # breaking the ``(root, info)`` convention core.auth expects).
    if not info.context.user.is_authenticated:
        raise PermissionDenied()
    user = info.context.user
    labels = []
    labelset = None
    labelset_created = False
    label_created = False
    message = "Success"
    ok = True

    # Validate color format (defense in depth)
    is_valid_color, color_error = validate_color(color)
    if not is_valid_color:
        return payload_cls(
            ok=False,
            message=color_error,
            labels=[],
            labelset=None,
            labelset_created=False,
            label_created=False,
        )

    try:
        # Get corpus
        corpus_pk = from_global_id(corpus_id)[1]
        corpus = Corpus.objects.get(pk=corpus_pk)

        # Check user has permission to update corpus
        permission_error = BaseService.require_permission(
            corpus,
            user,
            PermissionTypes.UPDATE,
            request=info.context,
            error_message="You don't have permission to update this corpus",
        )
        if permission_error:
            return payload_cls(
                ok=False,
                message=permission_error,
                labels=[],
                labelset=None,
                labelset_created=False,
                label_created=False,
            )

        # Check if corpus has a labelset
        labelset = corpus.label_set

        # Step 1: Handle labelset creation if needed
        if not labelset and create_if_not_found:
            # Create new labelset
            labelset_title = labelset_title or f"{corpus.title} Labels"
            labelset = LabelSet.objects.create(
                title=labelset_title,
                description=labelset_description or f"Labels for {corpus.title}",
                creator=user,
            )
            set_permissions_for_obj_to_user(
                user,
                labelset,
                [PermissionTypes.CRUD],
                is_new=True,
                request=info.context,
            )

            # Assign labelset to corpus
            corpus.label_set = labelset
            corpus.save()
            labelset_created = True

            logger.info(
                f"Created new labelset '{labelset_title}' for corpus {corpus_id}"
            )

        # Step 2: Search for existing labels or create new one
        if labelset:
            # Search for existing labels with case-insensitive partial match
            existing_labels = labelset.annotation_labels.filter(
                text__icontains=search_term, label_type=label_type
            )

            if existing_labels.exists():
                # Return matching labels
                labels = list(existing_labels)
                message = f"Found {len(labels)} matching label(s)"

            elif create_if_not_found:
                # Create new label
                new_label = AnnotationLabel.objects.create(
                    text=search_term,
                    description=description,
                    color=color,
                    icon=icon,
                    label_type=label_type,
                    creator=user,
                )
                set_permissions_for_obj_to_user(
                    user,
                    new_label,
                    [PermissionTypes.CRUD],
                    is_new=True,
                    request=info.context,
                )

                # Add to labelset
                labelset.annotation_labels.add(new_label)
                labels = [new_label]
                label_created = True

                if labelset_created:
                    message = (
                        f"Created labelset '{labelset.title}' and label '{search_term}'"
                    )
                else:
                    message = f"Created label '{search_term}'"

                logger.info(
                    f"Created new label '{search_term}' in labelset {labelset.id}"
                )
            else:
                # No matches and not creating
                message = f"No labels found matching '{search_term}'"
        else:
            # No labelset and not creating
            if create_if_not_found:
                message = "Cannot create label: corpus has no labelset and labelset creation was not requested"
                ok = False
            else:
                message = "No labelset configured for this corpus"

    except Corpus.DoesNotExist:
        ok = False
        message = "Corpus not found"
    except Exception as e:
        ok = False
        message = f"Error: {str(e)}"
        logger.error(f"SmartLabelSearchOrCreateMutation error: {e}", exc_info=True)
        raise  # Re-raise to trigger transaction rollback

    return payload_cls(
        ok=ok,
        message=message,
        labels=labels,
        labelset=labelset,
        labelset_created=labelset_created,
        label_created=label_created,
    )


def m_smart_label_search_or_create(
    info: strawberry.Info,
    color: Annotated[
        str | None,
        strawberry.argument(
            name="color", description="Color for new label (if created)"
        ),
    ] = "#1a75bc",
    corpus_id: Annotated[
        str,
        strawberry.argument(
            name="corpusId", description="ID of the corpus to work with"
        ),
    ] = strawberry.UNSET,
    create_if_not_found: Annotated[
        bool | None,
        strawberry.argument(
            name="createIfNotFound",
            description="Whether to create label/labelset if not found",
        ),
    ] = False,
    description: Annotated[
        str | None,
        strawberry.argument(
            name="description", description="Description for new label (if created)"
        ),
    ] = "",
    icon: Annotated[
        str | None,
        strawberry.argument(name="icon", description="Icon for new label (if created)"),
    ] = "tag",
    label_type: Annotated[
        str,
        strawberry.argument(
            name="labelType",
            description="The type of label (SPAN_LABEL, TOKEN_LABEL, etc.)",
        ),
    ] = strawberry.UNSET,
    labelset_description: Annotated[
        str | None,
        strawberry.argument(
            name="labelsetDescription",
            description="Description for new labelset (if created)",
        ),
    ] = "",
    labelset_title: Annotated[
        str | None,
        strawberry.argument(
            name="labelsetTitle",
            description="Title for new labelset (if created). Defaults to corpus title + ' Labels'",
        ),
    ] = strawberry.UNSET,
    search_term: Annotated[
        str,
        strawberry.argument(
            name="searchTerm", description="The label text to search for or create"
        ),
    ] = strawberry.UNSET,
) -> SmartLabelSearchOrCreateMutation | None:
    kwargs = strip_unset(
        {
            "color": color,
            "corpus_id": corpus_id,
            "create_if_not_found": create_if_not_found,
            "description": description,
            "icon": icon,
            "label_type": label_type,
            "labelset_description": labelset_description,
            "labelset_title": labelset_title,
            "search_term": search_term,
        }
    )
    return _mutate_SmartLabelSearchOrCreateMutation(
        SmartLabelSearchOrCreateMutation, None, info, **kwargs
    )


def _mutate_SmartLabelListMutation(
    payload_cls, root, info, corpus_id: str, label_type: str | None = None
):
    """PORT: /home/user/oc-graphene-ref/config/graphql/smart_label_mutations.py:270

    Port of SmartLabelListMutation.mutate
    """
    # @login_required — inlined (mutate stub takes ``payload_cls`` first).
    if not info.context.user.is_authenticated:
        raise PermissionDenied()
    user = info.context.user
    labels = []
    has_labelset = False
    can_create_labels = False

    # IDOR-safe READ gate: only return label info for a corpus the user
    # can actually read. ``get_or_none`` returns ``None`` for both
    # not-found and not-permitted, so an unreadable (e.g. private) corpus
    # is indistinguishable from a missing one. Without this gate any
    # logged-in user could enumerate a private corpus's labelset taxonomy.
    corpus_pk = from_global_id(corpus_id)[1]
    corpus = BaseService.get_or_none(
        Corpus, corpus_pk, user, PermissionTypes.READ, request=info.context
    )
    if corpus is None:
        return payload_cls(
            ok=False,
            message="Corpus not found",
            labels=[],
            has_labelset=False,
            can_create_labels=False,
        )

    try:
        # Check permissions (boolean flag for UI/response shape — use the
        # BaseService bool helper instead of touching Tier-0 directly).
        can_create_labels = BaseService.user_has(
            corpus, user, PermissionTypes.UPDATE, request=info.context
        )

        # Check labelset
        if corpus.label_set:
            has_labelset = True

            # Get labels
            label_queryset = corpus.label_set.annotation_labels.all()
            if label_type:
                label_queryset = label_queryset.filter(label_type=label_type)
            labels = list(label_queryset)

            message = f"Found {len(labels)} label(s)"
        else:
            message = "No labelset configured for this corpus"

        return payload_cls(
            ok=True,
            message=message,
            labels=labels,
            has_labelset=has_labelset,
            can_create_labels=can_create_labels,
        )
    except Exception as e:
        logger.error(f"SmartLabelListMutation error: {e}", exc_info=True)
        return payload_cls(
            ok=False,
            message=f"Error: {str(e)}",
            labels=[],
            has_labelset=False,
            can_create_labels=False,
        )


def m_smart_label_list(
    info: strawberry.Info,
    corpus_id: Annotated[
        str, strawberry.argument(name="corpusId", description="ID of the corpus")
    ] = strawberry.UNSET,
    label_type: Annotated[
        str | None,
        strawberry.argument(
            name="labelType", description="Optional filter by label type"
        ),
    ] = strawberry.UNSET,
) -> SmartLabelListMutation | None:
    kwargs = strip_unset({"corpus_id": corpus_id, "label_type": label_type})
    return _mutate_SmartLabelListMutation(SmartLabelListMutation, None, info, **kwargs)


MUTATION_FIELDS = {
    "smart_label_search_or_create": strawberry.field(
        resolver=m_smart_label_search_or_create,
        name="smartLabelSearchOrCreate",
        description="Smart mutation that handles label search and creation with automatic labelset management.\n\nThis mutation encapsulates the following logic:\n1. If no labelset exists for the corpus and createIfNotFound is true:\n   - Creates a new labelset\n   - Assigns it to the corpus\n   - Creates the label in the new labelset\n\n2. If labelset exists:\n   - Searches for existing labels matching the search term\n   - If matches found: returns the matching labels\n   - If no matches and createIfNotFound is true: creates the label\n   - If no matches and createIfNotFound is false: returns empty list",
    ),
    "smart_label_list": strawberry.field(
        resolver=m_smart_label_list,
        name="smartLabelList",
        description="Simplified mutation to get all available labels for a corpus with helpful status info.",
    ),
}
