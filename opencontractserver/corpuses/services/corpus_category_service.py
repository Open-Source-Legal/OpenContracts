"""Corpus-category CRUD for the corpus service layer.

``CorpusCategoryService`` owns create / update / delete of
:class:`CorpusCategory` rows — the runtime-configurable tag set ("Case Law",
"Contracts", ...) used to organise corpuses on the Discover page. It
centralises the field validation, unique-name enforcement, and ORM access so
``config/graphql/corpus_category_mutations.py`` stays a thin GraphQL wrapper
(per CLAUDE.md rule 7: user-context code reaches models through the service
layer rather than composing ORM calls inline).

Categories are global, admin-provisioned structural data with no per-object
guardian permissions, so there is no ``visible_to_user`` gate here — the
*authorization* decision (superuser-only) stays at the GraphQL boundary,
consistent with the pipeline-settings mutations. This service owns the
*business rules* (validation, uniqueness, persistence).
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from opencontractserver.constants.corpus_categories import (
    DEFAULT_CATEGORY_COLOR,
    DEFAULT_CATEGORY_ICON,
    MAX_CATEGORY_DESCRIPTION_LENGTH,
    MAX_CATEGORY_ICON_LENGTH,
    MAX_CATEGORY_NAME_LENGTH,
)
from opencontractserver.corpuses.models import CorpusCategory
from opencontractserver.shared.services.base import BaseService
from opencontractserver.shared.services.conventions import ServiceResult

if TYPE_CHECKING:
    from opencontractserver.users.models import User

logger = logging.getLogger(__name__)

# Hex color in the form ``#RRGGBB`` — matches the ``color`` field width (7).
HEX_COLOR_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")


class CorpusCategoryService(BaseService):
    """Create / update / delete corpus categories (global structural data)."""

    @staticmethod
    def _validate_fields(
        *,
        name: str | None = None,
        description: str | None = None,
        icon: str | None = None,
        color: str | None = None,
    ) -> str | None:
        """Validate user-supplied category fields.

        Returns an error message string if any provided field is invalid,
        else ``None``. Only validates fields that are actually provided
        (non-``None``) so it works for both create (all fields) and partial
        update.
        """
        if name is not None:
            cleaned = name.strip()
            if not cleaned:
                return "Category name cannot be empty."
            if len(cleaned) > MAX_CATEGORY_NAME_LENGTH:
                return (
                    f"Category name exceeds maximum length of "
                    f"{MAX_CATEGORY_NAME_LENGTH} characters."
                )
        if (
            description is not None
            and len(description) > MAX_CATEGORY_DESCRIPTION_LENGTH
        ):
            return (
                f"Description exceeds maximum length of "
                f"{MAX_CATEGORY_DESCRIPTION_LENGTH} characters."
            )
        if icon is not None and len(icon) > MAX_CATEGORY_ICON_LENGTH:
            return (
                f"Icon name exceeds maximum length of "
                f"{MAX_CATEGORY_ICON_LENGTH} characters."
            )
        if color is not None and not HEX_COLOR_PATTERN.match(color):
            return f"Invalid color '{color}'. Expected a hex value like '#3B82F6'."
        return None

    @classmethod
    def get_category_or_none(cls, category_pk: str | int) -> CorpusCategory | None:
        """Fetch a category by primary key, or ``None`` if it does not exist.

        Plain (non-permission-scoped) lookup: categories are global structural
        data and the caller is already superuser-gated, so there is no
        per-object visibility filter to apply. Lives here so the GraphQL layer
        never touches ``CorpusCategory.objects`` directly.
        """
        return CorpusCategory.objects.filter(pk=category_pk).first()

    @classmethod
    def create_category(
        cls,
        user: User,
        *,
        name: str,
        description: str | None = None,
        icon: str | None = None,
        color: str | None = None,
        sort_order: int | None = None,
    ) -> ServiceResult[CorpusCategory]:
        """Create a new category after validation + unique-name enforcement."""
        error = cls._validate_fields(
            name=name, description=description, icon=icon, color=color
        )
        if error:
            return ServiceResult.failure(error)

        cleaned_name = name.strip()
        if CorpusCategory.objects.filter(name=cleaned_name).exists():
            return ServiceResult.failure(
                f"A category named '{cleaned_name}' already exists."
            )

        category = CorpusCategory.objects.create(
            name=cleaned_name,
            description=(description or "").strip(),
            icon=icon or DEFAULT_CATEGORY_ICON,
            color=color or DEFAULT_CATEGORY_COLOR,
            sort_order=sort_order if sort_order is not None else 0,
            creator=user,
            # Categories are globally visible structural data.
            is_public=True,
        )
        cls.log_action("Created", category, user, name=category.name)
        return ServiceResult.success(category)

    @classmethod
    def update_category(
        cls,
        user: User,
        category: CorpusCategory,
        *,
        name: str | None = None,
        description: str | None = None,
        icon: str | None = None,
        color: str | None = None,
        sort_order: int | None = None,
    ) -> ServiceResult[CorpusCategory]:
        """Apply a partial update to ``category``.

        Only the provided (non-``None``) fields are written, via
        ``update_fields`` to avoid full-row writes. The unique-name constraint
        is enforced with a friendly message rather than letting the
        ``IntegrityError`` bubble up. A call that supplies no fields is a no-op:
        it returns successfully without issuing a DB write (which would
        otherwise pointlessly bump ``modified``).
        """
        error = cls._validate_fields(
            name=name, description=description, icon=icon, color=color
        )
        if error:
            return ServiceResult.failure(error)

        update_fields = ["modified"]

        if name is not None:
            cleaned_name = name.strip()
            if (
                CorpusCategory.objects.filter(name=cleaned_name)
                .exclude(pk=category.pk)
                .exists()
            ):
                return ServiceResult.failure(
                    f"A category named '{cleaned_name}' already exists."
                )
            category.name = cleaned_name
            update_fields.append("name")
        if description is not None:
            category.description = description.strip()
            update_fields.append("description")
        if icon is not None:
            category.icon = icon
            update_fields.append("icon")
        if color is not None:
            category.color = color
            update_fields.append("color")
        if sort_order is not None:
            category.sort_order = sort_order
            update_fields.append("sort_order")

        # Nothing but the seeded "modified" sentinel means no real field was
        # supplied — skip the write so an empty update doesn't bump the
        # timestamp (and log) for no reason. Compare the exact list (not just
        # the length) so the guard stays correct if another sentinel is ever
        # seeded into ``update_fields``.
        if update_fields == ["modified"]:
            return ServiceResult.success(category)

        category.save(update_fields=update_fields)
        cls.log_action("Updated", category, user, name=category.name)
        return ServiceResult.success(category)

    @classmethod
    def delete_category(
        cls,
        user: User,
        category: CorpusCategory,
    ) -> ServiceResult[None]:
        """Delete a category.

        The ``Corpus.categories`` M2M through-rows are cleaned up automatically
        by Django; the corpuses themselves are untouched.
        """
        cls.log_action("Deleted", category, user, name=category.name)
        category.delete()
        return ServiceResult.success(None)
