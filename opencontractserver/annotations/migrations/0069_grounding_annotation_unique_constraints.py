"""
Add database-level unique constraints backing the application-level
``get_or_create`` calls in ``opencontractserver/utils/extraction_grounding.py``.

Context (issue #1407, follow-up to PR #1397):
The grounding pipeline already uses ``Annotation.objects.get_or_create()``
to make Celery retries idempotent.  Without a backing ``UniqueConstraint``,
two workers racing on the same datacell can both miss on the SELECT and
both succeed on the CREATE — duplicating the source annotation that the
``get_or_create`` was meant to prevent.  In practice this is rare for a
single datacell (Celery typically retries sequentially), but the
constraints below promote idempotency from a best-effort behaviour to a
correctness invariant.

The constraints are scoped to ``is_grounding_source=True`` so that
legitimate non-grounding flows producing the same key tuple — e.g.
``add_annotations_from_exact_strings`` finding multiple occurrences of
the same word on the same page, or hierarchical annotation trees with
duplicate ``raw_text`` at different parents — are not blocked.

Two partial unique constraints (one per annotation_type) match the
respective ``get_or_create`` lookup keys exactly:

* TOKEN_LABEL (PDF grounding) — keyed on
  ``(document, corpus, annotation_label, page, raw_text, creator)`` since
  the bounding-box ``json`` is deterministic for a fixed input and we
  want retries to reuse the existing row even if PlasmaPDF reformats the
  bounding-box layout.
* SPAN_LABEL (text/DOCX grounding) — keyed on
  ``(document, corpus, annotation_label, raw_text, json, creator)``
  because the character offsets in ``json={"start", "end"}`` ARE the
  identity for a span annotation.  ``page`` is omitted (always 1 in this
  path).

``creator`` is included so two users manually creating identical
grounding rows are not blocked — only a single user creating the literal
same row is, which matches the realistic race-condition target (the
grounding pipeline always uses the datacell owner's ID).

Migration steps (in order):
1. Add the ``is_grounding_source`` boolean field (default False).
2. Backfill: set ``is_grounding_source=True`` for any pre-existing
   annotation tied to the ``OC_EXTRACT_SOURCE`` label and not structural,
   so the constraints meaningfully cover historical grounding rows.
3. Dedupe surviving duplicates among the backfilled (now-flagged) rows,
   re-pointing ``datacell.sources`` M2M FKs to the lowest-pk keeper —
   same pattern as ``0068_enforce_embedder_path_not_null.py``.
4. Add the two partial UniqueConstraints.
"""

import logging

from django.db import migrations, models, transaction
from django.db.models import Count, Q

# Frozen at migration write time. Mirrors
# ``opencontractserver.constants.annotations.OC_EXTRACT_SOURCE_LABEL`` —
# importing the live constant would couple this historical migration to the
# current module layout and break replay if the constant is ever renamed.
OC_EXTRACT_SOURCE_LABEL = "OC_EXTRACT_SOURCE"

logger = logging.getLogger(__name__)


def backfill_is_grounding_source(apps, schema_editor):
    """Flag pre-existing grounding annotations.

    Without this backfill, historical OC_EXTRACT_SOURCE rows would have
    ``is_grounding_source=False`` and slip past the new constraints.
    """
    Annotation = apps.get_model("annotations", "Annotation")
    AnnotationLabel = apps.get_model("annotations", "AnnotationLabel")

    grounding_label_ids = list(
        AnnotationLabel.objects.filter(text=OC_EXTRACT_SOURCE_LABEL).values_list(
            "id", flat=True
        )
    )
    if not grounding_label_ids:
        return

    updated = Annotation.objects.filter(
        annotation_label_id__in=grounding_label_ids,
        structural=False,
    ).update(is_grounding_source=True)

    if updated:
        logger.info(
            "Backfilled is_grounding_source=True on %s pre-existing "
            "OC_EXTRACT_SOURCE annotation rows.",
            updated,
        )


def reverse_backfill(apps, schema_editor):
    """Reverse: clear is_grounding_source on the backfilled rows."""
    Annotation = apps.get_model("annotations", "Annotation")
    Annotation.objects.filter(is_grounding_source=True).update(
        is_grounding_source=False
    )


def _repoint_m2m_through(through_model, owner_field: str, redundant_ids, keeper_id):
    """Repoint redundant ``annotation_id`` rows to ``keeper_id`` on an M2M through table.

    The default Django M2M through table carries ``UNIQUE(<owner>_id,
    annotation_id)``.  In the realistic race the migration targets — two
    workers each grounding the same datacell — both ``keeper`` and the
    redundant duplicates already sit in the same ``<owner>``'s
    ``annotation`` set, so a blind ``UPDATE annotation_id = keeper_id``
    collides with the existing keeper row and raises ``IntegrityError``.

    The fix: for every owner that already references the keeper, first
    delete the redundant rows that would collide, then update the rest.
    """
    existing_owners = list(
        through_model.objects.filter(annotation_id=keeper_id).values_list(
            f"{owner_field}_id", flat=True
        )
    )
    if existing_owners:
        through_model.objects.filter(
            annotation_id__in=redundant_ids,
            **{f"{owner_field}_id__in": existing_owners},
        ).delete()
    through_model.objects.filter(annotation_id__in=redundant_ids).update(
        annotation_id=keeper_id
    )


def _repoint_cross_references(apps, redundant_ids: list[int], keeper_id: int) -> None:
    """Repoint every realistic cross-reference from ``redundant_ids`` to ``keeper_id``.

    Survey of FK / M2M references to ``Annotation`` outside the grounding
    pipeline (run ``grep -nE 'ForeignKey|ManyToManyField' ...`` to refresh):

    * ``extracts.Datacell.sources`` (M2M)            — primary, always
    * ``feedback.UserFeedback.commented_annotation`` (FK, SET_NULL)
    * ``conversations.ChatMessage.source_annotations`` (M2M)
    * ``conversations.ChatMessage.created_annotations`` (M2M)
    * ``users.Assignment.resulting_annotations`` (M2M)
    * ``annotations.Relationship.source_annotations`` (M2M)
    * ``annotations.Relationship.target_annotations`` (M2M)
    * ``annotations.Embedding.annotation`` (FK, CASCADE)
       — handled implicitly: deleting redundant annotations cascade-deletes
       their embeddings, the keeper retains its own.
    * ``annotations.Annotation.parent`` (FK, CASCADE)
       — grounding annotations are leaf rows; in the unlikely event a child
       FK exists, CASCADE preserves migration integrity at the cost of
       data on a duplicate row that should not have had children.

    Every reference except the cascading ones is repointed to the keeper so
    no cross-domain data is silently dropped when the redundant row is
    deleted.  M2M through tables go through ``_repoint_m2m_through`` so the
    UNIQUE(owner, annotation) constraint never blocks the update.
    """
    Datacell = apps.get_model("extracts", "Datacell")
    UserFeedback = apps.get_model("feedback", "UserFeedback")
    ChatMessage = apps.get_model("conversations", "ChatMessage")
    Assignment = apps.get_model("users", "Assignment")
    Relationship = apps.get_model("annotations", "Relationship")

    _repoint_m2m_through(
        Datacell.sources.through, "datacell", redundant_ids, keeper_id
    )
    UserFeedback.objects.filter(commented_annotation_id__in=redundant_ids).update(
        commented_annotation_id=keeper_id
    )
    _repoint_m2m_through(
        ChatMessage.source_annotations.through,
        "chatmessage",
        redundant_ids,
        keeper_id,
    )
    _repoint_m2m_through(
        ChatMessage.created_annotations.through,
        "chatmessage",
        redundant_ids,
        keeper_id,
    )
    _repoint_m2m_through(
        Assignment.resulting_annotations.through,
        "assignment",
        redundant_ids,
        keeper_id,
    )
    _repoint_m2m_through(
        Relationship.source_annotations.through,
        "relationship",
        redundant_ids,
        keeper_id,
    )
    _repoint_m2m_through(
        Relationship.target_annotations.through,
        "relationship",
        redundant_ids,
        keeper_id,
    )


def _dedupe_token_label(apps):
    """Collapse duplicate flagged TOKEN_LABEL grounding annotations.

    Groups by ``(document, corpus, annotation_label, page, raw_text,
    creator)`` and, for each group of >1, keeps the lowest-pk row and
    repoints all realistic cross-references (see
    ``_repoint_cross_references``) to it before deleting the rest.
    """
    Annotation = apps.get_model("annotations", "Annotation")

    duplicates = (
        Annotation.objects.filter(
            structural=False,
            annotation_type="TOKEN_LABEL",
            is_grounding_source=True,
        )
        .values(
            "document_id",
            "corpus_id",
            "annotation_label_id",
            "page",
            "raw_text",
            "creator_id",
        )
        .annotate(n=Count("id"))
        .filter(n__gt=1)
    )

    total_groups = 0
    total_collapsed = 0
    for group in duplicates:
        ids = list(
            Annotation.objects.filter(
                structural=False,
                annotation_type="TOKEN_LABEL",
                is_grounding_source=True,
                document_id=group["document_id"],
                corpus_id=group["corpus_id"],
                annotation_label_id=group["annotation_label_id"],
                page=group["page"],
                raw_text=group["raw_text"],
                creator_id=group["creator_id"],
            )
            .order_by("id")
            .values_list("id", flat=True)
        )
        if len(ids) <= 1:
            continue
        keeper, *redundant = ids
        with transaction.atomic():
            _repoint_cross_references(apps, redundant, keeper)
            Annotation.objects.filter(id__in=redundant).delete()
        total_groups += 1
        total_collapsed += len(redundant)

    if total_groups:
        logger.info(
            "Collapsed %s duplicate grounding TOKEN_LABEL annotation rows "
            "across %s groups before adding unique constraint.",
            total_collapsed,
            total_groups,
        )


def _dedupe_span_label(apps):
    """Collapse duplicate flagged SPAN_LABEL grounding annotations.

    Groups by ``(document, corpus, annotation_label, raw_text, json,
    creator)``.  ``json`` equality on PostgreSQL JSONB is structural
    (key-order independent), which matches the application-level
    ``get_or_create`` lookup behaviour.
    """
    Annotation = apps.get_model("annotations", "Annotation")

    duplicates = (
        Annotation.objects.filter(
            structural=False,
            annotation_type="SPAN_LABEL",
            is_grounding_source=True,
        )
        .values(
            "document_id",
            "corpus_id",
            "annotation_label_id",
            "raw_text",
            "json",
            "creator_id",
        )
        .annotate(n=Count("id"))
        .filter(n__gt=1)
    )

    total_groups = 0
    total_collapsed = 0
    for group in duplicates:
        ids = list(
            Annotation.objects.filter(
                structural=False,
                annotation_type="SPAN_LABEL",
                is_grounding_source=True,
                document_id=group["document_id"],
                corpus_id=group["corpus_id"],
                annotation_label_id=group["annotation_label_id"],
                raw_text=group["raw_text"],
                json=group["json"],
                creator_id=group["creator_id"],
            )
            .order_by("id")
            .values_list("id", flat=True)
        )
        if len(ids) <= 1:
            continue
        keeper, *redundant = ids
        with transaction.atomic():
            _repoint_cross_references(apps, redundant, keeper)
            Annotation.objects.filter(id__in=redundant).delete()
        total_groups += 1
        total_collapsed += len(redundant)

    if total_groups:
        logger.info(
            "Collapsed %s duplicate grounding SPAN_LABEL annotation rows "
            "across %s groups before adding unique constraint.",
            total_collapsed,
            total_groups,
        )


def dedupe_grounding_targets(apps, schema_editor):
    _dedupe_token_label(apps)
    _dedupe_span_label(apps)


def reverse_dedupe(apps, schema_editor):
    """No-op: dropping the constraint cannot resurrect deleted duplicates."""


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("annotations", "0068_enforce_embedder_path_not_null"),
        # Dedup helper repoints cross-references on these apps' models. Pin
        # to the latest migration of each so they exist when this runs.
        ("conversations", "0018_conversation_memory_curated"),
        ("extracts", "0028_rename_placeholder_indexes"),
        ("feedback", "0006_alter_userfeedback_backend_lock"),
        ("users", "0026_alter_user_username_validator"),
    ]

    operations = [
        migrations.AddField(
            model_name="annotation",
            name="is_grounding_source",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(backfill_is_grounding_source, reverse_backfill),
        migrations.RunPython(dedupe_grounding_targets, reverse_dedupe),
        migrations.AddConstraint(
            model_name="annotation",
            constraint=models.UniqueConstraint(
                fields=[
                    "document",
                    "corpus",
                    "annotation_label",
                    "page",
                    "raw_text",
                    "creator",
                ],
                condition=Q(
                    structural=False,
                    annotation_type="TOKEN_LABEL",
                    is_grounding_source=True,
                ),
                name="annotation_unique_token_label_grounding_key",
            ),
        ),
        migrations.AddConstraint(
            model_name="annotation",
            constraint=models.UniqueConstraint(
                fields=[
                    "document",
                    "corpus",
                    "annotation_label",
                    "raw_text",
                    "json",
                    "creator",
                ],
                condition=Q(
                    structural=False,
                    annotation_type="SPAN_LABEL",
                    is_grounding_source=True,
                ),
                name="annotation_unique_span_label_grounding_key",
            ),
        ),
    ]
