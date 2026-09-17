"""Human-annotation review state across document versions.

Annotations are never versioned or migrated: a human annotation stays pinned to
the ``Document`` row (version) it was drawn on. When that document is
superseded, each annotation on the previous version is **stale** relative to
the new version until a reviewer records a decision against it — re-approve it
(a successor with the same text and label is created on the new version),
correct it (a successor that differs), or drop it. ``STALE`` is derived: it is
the absence of a row for ``(annotation, target_document)``.

Only the parent hop is reviewed (v1→v2, then v2→v3 reviews v2's rows, successors
included), so there is no transitive lineage to maintain. See
``docs/architecture/reference-web-versioning.md`` (change 5) and
``opencontractserver/annotations/services/annotation_version_review_service.py``.
"""

from django.contrib.auth import get_user_model
from django.db import models

from opencontractserver.constants.annotations import (
    ANNOTATION_VERSION_DECISION_CORRECTED,
    ANNOTATION_VERSION_DECISION_DROPPED,
    ANNOTATION_VERSION_DECISION_REAPPROVED,
    ANNOTATION_VERSION_DECISIONS,
)


class AnnotationVersionDecision(models.Model):
    DECISION_CHOICES = [
        (ANNOTATION_VERSION_DECISION_REAPPROVED, "Re-approved on the new version"),
        (ANNOTATION_VERSION_DECISION_CORRECTED, "Corrected on the new version"),
        (ANNOTATION_VERSION_DECISION_DROPPED, "No longer applies"),
    ]

    annotation = models.ForeignKey(
        "annotations.Annotation",
        on_delete=models.CASCADE,
        related_name="version_decisions",
        help_text="The human annotation on the superseded (previous) version.",
    )
    target_document = models.ForeignKey(
        "documents.Document",
        on_delete=models.CASCADE,
        related_name="annotation_version_decisions",
        help_text="The newer version the annotation was reviewed against.",
    )
    decision = models.CharField(max_length=16, choices=DECISION_CHOICES)
    successor = models.ForeignKey(
        "annotations.Annotation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="carried_from_decisions",
        help_text="The ordinary annotation created on the new version, if any.",
    )
    creator = models.ForeignKey(get_user_model(), on_delete=models.CASCADE)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["annotation", "target_document"],
                name="uniq_annotation_version_decision",
            ),
            models.CheckConstraint(
                condition=models.Q(decision__in=ANNOTATION_VERSION_DECISIONS),
                name="annotation_version_decision_valid",
            ),
        ]
        indexes = [
            models.Index(
                fields=["target_document", "decision"],
                name="ann_ver_decision_target_idx",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"AnnotationVersionDecision({self.annotation_id} -> "
            f"{self.target_document_id}: {self.decision})"
        )
