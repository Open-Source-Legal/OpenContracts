"""django-filter FilterSet ↔ GraphQL argument-name mapping.

graphene derived connection argument names from django-filter filter names
via ``graphene.utils.str_converters.to_camel_case`` (which camel-cases
around *single* underscores while preserving a ``__`` boundary as ``_`` +
TitleCase — e.g. ``annotation_label__text__contains`` →
``annotationLabel_TextContains``). The strawberry schema keeps the same
wire names; this module reproduces the conversion so resolvers can map
GraphQL argument names back to filter names.
"""

from __future__ import annotations

import binascii
import itertools
from functools import lru_cache

from django import forms
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _
from django_filters import Filter, MultipleChoiceFilter
from django_filters.filterset import (
    FILTER_FOR_DBFIELD_DEFAULTS,
    BaseFilterSet,
    FilterSet,
)
from graphql_relay import from_global_id


def to_camel_case(snake_str: str) -> str:
    """graphene.utils.str_converters.to_camel_case — exact port."""
    components = snake_str.split("_")
    return components[0] + "".join(x.capitalize() if x else "_" for x in components[1:])


@lru_cache(maxsize=None)
def filterset_arg_names(filterset_class: type) -> tuple[tuple[str, str], ...]:
    """(filter_name, graphql_arg_name) pairs for a FilterSet class."""
    return tuple(
        (name, to_camel_case(name))
        for name in filterset_class.base_filters  # type: ignore[attr-defined]
    )


# --------------------------------------------------------------------------- #
# graphene-django FilterSet wrapping (ports of                                #
# graphene_django.filter.filterset + .filters.global_id_filter + forms)       #
# --------------------------------------------------------------------------- #


class GlobalIDFormField(forms.Field):
    default_error_messages = {"invalid": _("Invalid ID specified.")}

    def clean(self, value):
        if not value and not self.required:
            return None

        try:
            _type, _id = from_global_id(value)
        except (TypeError, ValueError, UnicodeDecodeError, binascii.Error):
            raise ValidationError(self.error_messages["invalid"])

        try:
            forms.CharField().clean(_id)
            forms.CharField().clean(_type)
        except ValidationError:
            raise ValidationError(self.error_messages["invalid"])

        return value


class GlobalIDMultipleChoiceField(forms.MultipleChoiceField):
    default_error_messages = {
        "invalid_choice": _("One of the specified IDs was invalid (%(value)s)."),
        "invalid_list": _("Enter a list of values."),
    }

    def valid_value(self, value):
        # Clean will raise a validation error if there is a problem
        GlobalIDFormField().clean(value)
        return True


class GlobalIDFilter(Filter):
    """Filter for a Relay global ID — decodes to the primary key."""

    field_class = GlobalIDFormField

    def filter(self, qs, value):
        _id = None
        if value is not None:
            _, _id = from_global_id(value)
        return super().filter(qs, _id)


class GlobalIDMultipleChoiceFilter(MultipleChoiceFilter):
    field_class = GlobalIDMultipleChoiceField

    def filter(self, qs, value):
        gids = [from_global_id(v)[1] for v in value]
        return super().filter(qs, gids)


GRAPHENE_FILTER_SET_OVERRIDES = {
    models.AutoField: {"filter_class": GlobalIDFilter},
    models.OneToOneField: {"filter_class": GlobalIDFilter},
    models.ForeignKey: {"filter_class": GlobalIDFilter},
    models.ManyToManyField: {"filter_class": GlobalIDMultipleChoiceFilter},
    models.ManyToOneRel: {"filter_class": GlobalIDMultipleChoiceFilter},
    models.ManyToManyRel: {"filter_class": GlobalIDMultipleChoiceFilter},
}


class GrapheneFilterSetMixin(BaseFilterSet):
    """BaseFilterSet with default overrides to handle relay global IDs."""

    FILTER_DEFAULTS = dict(
        itertools.chain(
            FILTER_FOR_DBFIELD_DEFAULTS.items(), GRAPHENE_FILTER_SET_OVERRIDES.items()
        )
    )


@lru_cache(maxsize=None)
def setup_filterset(filterset_class: type) -> type:
    """Wrap a provided FilterSet with the relay global-ID overrides."""
    return type(
        f"Graphene{filterset_class.__name__}",
        (filterset_class, GrapheneFilterSetMixin),
        {},
    )


def filterset_factory(model: type, fields: dict) -> type:
    """Create a FilterSet for ``model`` from a graphene-django
    ``filter_fields`` mapping (port of ``custom_filterset_factory``)."""
    meta_class = type("Meta", (object,), {"model": model, "fields": fields})
    return type(
        f"{model._meta.object_name}FilterSet",  # type: ignore[attr-defined]
        (FilterSet, GrapheneFilterSetMixin),
        {"Meta": meta_class},
    )
