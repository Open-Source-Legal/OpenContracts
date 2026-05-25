import logging
from typing import Optional

import graphene
from django.db import transaction
from graphql_jwt.decorators import login_required
from graphql_relay import from_global_id

from config.graphql.graphene_types import AnnotationLabelType, LabelSetType
from config.graphql.validation_utils import validate_color
from opencontractserver.annotations.models import AnnotationLabel, LabelSet
from opencontractserver.corpuses.models import Corpus
from opencontractserver.shared.services.base import BaseService
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

logger = logging.getLogger(__name__)


class SmartLabelSearchOrCreateMutation(graphene.Mutation):
    """
    Smart mutation that handles label search and creation with automatic labelset management.

    This mutation encapsulates the following logic:
    1. If no labelset exists for the corpus and createIfNotFound is true:
       - Creates a new labelset
       - Assigns it to the corpus
       - Creates the label in the new labelset

    2. If labelset exists:
       - Searches for existing labels matching the search term
       - If matches found: returns the matching labels
       - If no matches and createIfNotFound is true: creates the label
       - If no matches and createIfNotFound is false: returns empty list
    """

    class Arguments:
        corpus_id = graphene.String(
            required=True, description="ID of the corpus to work with"
        )
        search_term = graphene.String(
            required=True, description="The label text to search for or create"
        )
        label_type = graphene.String(
            required=True,
            description="The type of label (SPAN_LABEL, TOKEN_LABEL, etc.)",
        )
        color = graphene.String(
            required=False,
            default_value="#1a75bc",
            description="Color for new label (if created)",
        )
        description = graphene.String(
            required=False,
            default_value="",
            description="Description for new label (if created)",
        )
        icon = graphene.String(
            required=False,
            default_value="tag",
            description="Icon for new label (if created)",
        )
        create_if_not_found = graphene.Boolean(
            required=False,
            default_value=False,
            description="Whether to create label/labelset if not found",
        )
        labelset_title = graphene.String(
            required=False,
            description="Title for new labelset (if created). Defaults to corpus title + ' Labels'",
        )
        labelset_description = graphene.String(
            required=False,
            default_value="",
            description="Description for new labelset (if created)",
        )

    # Outputs
    ok = graphene.Boolean()
    message = graphene.String()
    labels = graphene.List(
        AnnotationLabelType, description="List of matching or created labels"
    )
    labelset = graphene.Field(
        LabelSetType, description="The labelset (existing or newly created)"
    )
    labelset_created = graphene.Boolean(
        description="Whether a new labelset was created"
    )
    label_created = graphene.Boolean(description="Whether a new label was created")

    @login_required
    @transaction.atomic
    def mutate(
        root,
        info,
        corpus_id: str,
        search_term: str,
        label_type: str,
        color: str = "#1a75bc",
        description: str = "",
        icon: str = "tag",
        create_if_not_found: bool = False,
        labelset_title: Optional[str] = None,
        labelset_description: str = "",
    ) -> "SmartLabelSearchOrCreateMutation":
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
            return SmartLabelSearchOrCreateMutation(
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
                return SmartLabelSearchOrCreateMutation(
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
                        message = f"Created labelset '{labelset.title}' and label '{search_term}'"
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

        return SmartLabelSearchOrCreateMutation(
            ok=ok,
            message=message,
            labels=labels,
            labelset=labelset,
            labelset_created=labelset_created,
            label_created=label_created,
        )


class SmartLabelListMutation(graphene.Mutation):
    """
    Simplified mutation to get all available labels for a corpus with helpful status info.
    """

    class Arguments:
        corpus_id = graphene.String(required=True, description="ID of the corpus")
        label_type = graphene.String(
            required=False, description="Optional filter by label type"
        )

    ok = graphene.Boolean()
    message = graphene.String()
    labels = graphene.List(AnnotationLabelType)
    has_labelset = graphene.Boolean()
    can_create_labels = graphene.Boolean()

    @login_required
    def mutate(
        root, info, corpus_id: str, label_type: Optional[str] = None
    ) -> "SmartLabelListMutation":
        user = info.context.user
        labels = []
        has_labelset = False
        can_create_labels = False

        try:
            # Get corpus
            corpus_pk = from_global_id(corpus_id)[1]
            corpus = Corpus.objects.get(pk=corpus_pk)

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

            return SmartLabelListMutation(
                ok=True,
                message=message,
                labels=labels,
                has_labelset=has_labelset,
                can_create_labels=can_create_labels,
            )

        except Corpus.DoesNotExist:
            return SmartLabelListMutation(
                ok=False,
                message="Corpus not found",
                labels=[],
                has_labelset=False,
                can_create_labels=False,
            )
        except Exception as e:
            logger.error(f"SmartLabelListMutation error: {e}", exc_info=True)
            return SmartLabelListMutation(
                ok=False,
                message=f"Error: {str(e)}",
                labels=[],
                has_labelset=False,
                can_create_labels=False,
            )
