"""``UserFeedback`` service — approve / reject annotation feedback flows.

The annotation-level feedback flows have always lived inline in
``config/graphql/annotation_mutations.py``. They share a fixed structure:
fetch + permission-gate an :class:`Annotation`, then ``get_or_create`` a
:class:`UserFeedback` row and grant the creator CRUD on the new (or
re-issued) row. ``UserFeedbackService`` centralises that structure.

Permission model:
- Annotation lookup uses ``visible_to_user`` (READ filter) for IDOR safety.
- The COMMENT permission on the annotation is required to attach feedback,
  honouring the document + corpus inheritance and ``corpus.allow_comments``
  rules encoded by :meth:`Annotation.user_can`.
- The creator's CRUD grant flows through ``set_permissions_for_obj_to_user``
  with ``is_new=created`` so stale guardian rows from a prior CRUD → READ
  downgrade are still swept on a re-issue.

Phase 5 of the service-layer centralization roadmap — see
``docs/refactor_plans/2026-05-19-service-layer-centralization-design.md``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.db import transaction

from opencontractserver.shared.services.base import BaseService
from opencontractserver.shared.services.conventions import ServiceResult
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

if TYPE_CHECKING:
    from opencontractserver.feedback.models import UserFeedback


# Unified IDOR-safe message — surfaced for "not found", "not visible", and
# "lacks COMMENT permission". Identical text in both flows.
_ANNOTATION_NOT_FOUND_MSG = (
    "Annotation not found or you do not have permission to access it"
)


class UserFeedbackService(BaseService):
    """Annotation-level feedback CRUD."""

    @classmethod
    def approve_annotation(
        cls,
        user: Any,
        annotation_pk: Any,
        *,
        comment: str | None = None,
        request: Any = None,
    ) -> ServiceResult[UserFeedback]:
        """Mark an annotation as approved (creating/updating its feedback row)."""
        return cls._set_feedback(
            user,
            annotation_pk,
            approved=True,
            rejected=False,
            comment=comment,
            request=request,
        )

    @classmethod
    def reject_annotation(
        cls,
        user: Any,
        annotation_pk: Any,
        *,
        comment: str | None = None,
        request: Any = None,
    ) -> ServiceResult[UserFeedback]:
        """Mark an annotation as rejected (creating/updating its feedback row)."""
        return cls._set_feedback(
            user,
            annotation_pk,
            approved=False,
            rejected=True,
            comment=comment,
            request=request,
        )

    # ----------------------------------------------------------------- internal

    @classmethod
    @transaction.atomic
    def _set_feedback(
        cls,
        user: Any,
        annotation_pk: Any,
        *,
        approved: bool,
        rejected: bool,
        comment: str | None,
        request: Any,
    ) -> ServiceResult[UserFeedback]:
        """Shared approve/reject body.

        Wrapping the get-or-create + permission grant in
        ``transaction.atomic()`` matches the per-mutation ``@transaction.atomic``
        decorator that previously wrapped each flow.

        ``comment`` semantics (preserved verbatim from the pre-relocation
        mutation pair): ``None`` and ``""`` are both treated as "no new
        comment supplied" — the existing comment is retained when updating
        an existing row. Passing an empty string therefore does **not**
        clear a previously-set comment; callers wanting to clear must
        delete the ``UserFeedback`` row (or extend this API). New rows
        store ``comment=""`` when ``comment`` is falsy.
        """
        from opencontractserver.annotations.models import Annotation
        from opencontractserver.feedback.models import UserFeedback

        try:
            annotation = Annotation.objects.visible_to_user(user).get(pk=annotation_pk)
        except Annotation.DoesNotExist:
            return ServiceResult.failure(_ANNOTATION_NOT_FOUND_MSG)

        if not annotation.user_can(user, PermissionTypes.COMMENT, request=request):
            return ServiceResult.failure(_ANNOTATION_NOT_FOUND_MSG)

        user_feedback, created = UserFeedback.objects.get_or_create(
            commented_annotation=annotation,
            defaults={
                "creator": user,
                "approved": approved,
                "rejected": rejected,
                "comment": comment or "",
            },
        )

        if not created:
            user_feedback.approved = approved
            user_feedback.rejected = rejected
            user_feedback.comment = comment or user_feedback.comment
            user_feedback.save()

        # ``is_new=created`` so an existing UserFeedback row still flows
        # through the ``remove_perm`` sweep that clears stale guardian rows
        # from any prior CRUD → READ-only downgrade. Only fresh-creation
        # paths get the 7-DB-op skip.
        set_permissions_for_obj_to_user(
            user,
            user_feedback,
            [PermissionTypes.CRUD],
            is_new=created,
            request=request,
        )
        cls.log_action("Approved" if approved else "Rejected", annotation, user)
        return ServiceResult.success(user_feedback)
