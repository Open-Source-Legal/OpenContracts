#  Copyright (C) 2022  John Scrudato

import logging

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db.models import Q
from graphql_relay import from_global_id

from opencontractserver.shared.Models import BaseOCModel

User = get_user_model()

logger = logging.getLogger(__name__)


def resolve_single_oc_model_from_id(
    model_type: type[BaseOCModel] = None, graphql_id: str = "", user: User = None
) -> BaseOCModel:

    """
    Helper method for resolvers for single objs... gets object with id and makes sure the
    user has sufficient permissions to request it too.
    """
    model_name = model_type._meta.model_name
    app_label = model_type._meta.app_label

    django_pk = from_global_id(graphql_id)[1]

    if user.is_superuser:
        # print("User is a superuser... return value")
        obj = model_type.objects.get(id=django_pk)
    elif user.is_anonymous:
        obj = model_type.objects.get(id=django_pk, is_public=True)
    else:
        permission_model_type = apps.get_model(
            app_label, f"{model_name}userobjectpermission"
        )

        must_have_permissions = permission_model_type.objects.filter(
            permission__codename=f"read_{model_name}", user_id=user.id
        )

        # Start with basic permission filter (direct permissions, creator, public)
        base_filter = (
            Q(creator=user)
            | Q(is_public=True)
            | Q(**{f"{model_name}userobjectpermission__in": must_have_permissions})
        )

        # Check if this model inherits corpus permissions
        inherits_corpus_perms = getattr(
            model_type, "INHERITS_CORPUS_PERMISSIONS", False
        )
        logger.debug(f"model_type ({type(model_type)}): {model_type}")

        # If model has a corpus field and inherits permissions, add corpus permissions
        if inherits_corpus_perms:
            # Check if model has corpus field
            has_corpus_field = False
            for field in model_type._meta.get_fields():
                if field.name == "corpus":
                    has_corpus_field = True
                    break

            if has_corpus_field:

                # Get corpus permission model
                corpus_perm_model = apps.get_model(
                    "corpuses", "corpususerobjectpermission"
                )

                # Get corpuses with read permission
                corpus_permissions = corpus_perm_model.objects.filter(
                    permission__codename="read_corpus", user_id=user.id
                )

                # Get corpus IDs
                corpus_ids = corpus_permissions.values_list(
                    "content_object_id", flat=True
                )

                # Try different field patterns to capture all possible corpus reference patterns
                corpus_conditions = Q(corpus_id__in=corpus_ids)
                # Also check for other corpus-related fields
                corpus_field_names = []
                for field in model_type._meta.get_fields():
                    if field.name.endswith("corpus") and field.name != "corpus":
                        corpus_field_names.append(field.name)

                # Add conditions for each corpus-related field
                for field_name in corpus_field_names:
                    try:
                        # Using double-underscore is important here to properly handle foreign keys
                        filter_kwargs = {f"{field_name}__id__in": corpus_ids}
                        corpus_conditions |= Q(**filter_kwargs)
                    except Exception as e:
                        logger.warning(
                            f"RESOLVER: Error adding corpus condition for {field_name}: {str(e)}"
                        )

                if corpus_ids:
                    # Add corpus inheritance to base filter
                    base_filter |= corpus_conditions

        # Apply permission filter along with ID filter
        obj_queryset = model_type.objects.filter(
            base_filter & Q(id=django_pk)
        ).distinct()

        if len(obj_queryset) == 1:
            obj = obj_queryset[0]
        else:
            obj = None

    return obj
