"""Default LabelSet definition and seeding logic shared by the
``annotations/0070`` data migration and the ``seed_default_labelset``
management command.

Callers pass an ``apps`` registry so the migration can use historical model
state while the management command uses the live registry.
"""

import logging

from django.db import transaction

logger = logging.getLogger(__name__)

DEFAULT_LABELSET_TITLE = "Default Labels"
DEFAULT_LABELSET_DESCRIPTION = (
    "Default annotation label set seeded at install. Pre-selected in the "
    "new-corpus modal so corpuses have a usable starter palette out of the "
    "box. Owned by the install's first superuser; safe to edit."
)

# Strings (not the LABEL_TYPES enum) so the migration's historical app
# registry doesn't need to import the live module.
DEFAULT_LABELS: list[dict[str, str]] = [
    {
        "text": "Important",
        "description": "A key passage worth highlighting.",
        "color": "#dc2626",
        "icon": "star",
        "label_type": "TOKEN_LABEL",
    },
    {
        "text": "Question",
        "description": "A passage that raises a question or needs follow-up.",
        "color": "#f59e0b",
        "icon": "help-circle",
        "label_type": "TOKEN_LABEL",
    },
    {
        "text": "Reference",
        "description": "A cross-reference to another document, section, or source.",
        "color": "#0f766e",
        "icon": "link",
        "label_type": "TOKEN_LABEL",
    },
    {
        "text": "Definition",
        "description": "A defined term or definitional clause.",
        "color": "#2563eb",
        "icon": "book",
        "label_type": "TOKEN_LABEL",
    },
    {
        "text": "Party",
        "description": "A named party, signatory, or counterparty to the agreement.",
        "color": "#7c3aed",
        "icon": "users",
        "label_type": "TOKEN_LABEL",
    },
    {
        "text": "Governing Law",
        "description": "The jurisdiction or body of law that governs the agreement.",
        "color": "#475569",
        "icon": "scale",
        "label_type": "TOKEN_LABEL",
    },
    {
        "text": "Effective Date",
        "description": "The date the agreement becomes effective.",
        "color": "#059669",
        "icon": "calendar-check",
        "label_type": "TOKEN_LABEL",
    },
    {
        "text": "Termination Date",
        "description": "A specific date on which the agreement terminates.",
        "color": "#b91c1c",
        "icon": "calendar-x",
        "label_type": "TOKEN_LABEL",
    },
    {
        "text": "Expiration",
        "description": "Language describing how or when the agreement expires.",
        "color": "#ea580c",
        "icon": "clock",
        "label_type": "TOKEN_LABEL",
    },
    {
        "text": "Termination",
        "description": "Termination rights, triggers, or termination-for-cause language.",
        "color": "#dc2626",
        "icon": "x-circle",
        "label_type": "TOKEN_LABEL",
    },
    {
        "text": "Renewal",
        "description": "Auto-renewal, optional renewal, or extension language.",
        "color": "#0284c7",
        "icon": "repeat",
        "label_type": "TOKEN_LABEL",
    },
    {
        "text": "Limitation of Liability",
        "description": "Caps, carve-outs, or other liability-limiting language.",
        "color": "#ca8a04",
        "icon": "shield-alert",
        "label_type": "TOKEN_LABEL",
    },
]


def create_default_labelset(apps, schema_editor):
    """Idempotently seed the install-wide default LabelSet and its starter
    labels.

    Wrapped in ``transaction.atomic()`` so concurrent migration workers and
    the management command can't both create a duplicate labelset between
    the title lookup and the create.
    """
    User = apps.get_model("users", "User")
    LabelSet = apps.get_model("annotations", "LabelSet")
    AnnotationLabel = apps.get_model("annotations", "AnnotationLabel")

    system_user = User.objects.filter(is_superuser=True).order_by("id").first()
    if not system_user:
        logger.warning(
            "No superuser found — skipping default LabelSet creation. "
            "After creating a superuser, run: "
            "python manage.py seed_default_labelset"
        )
        return

    with transaction.atomic():
        labelset, created = LabelSet.objects.get_or_create(
            title=DEFAULT_LABELSET_TITLE,
            defaults={
                "description": DEFAULT_LABELSET_DESCRIPTION,
                "creator": system_user,
                "is_public": True,
                "is_default": True,
            },
        )

        if not created:
            updates = {}
            if not labelset.is_public:
                updates["is_public"] = True
            if not labelset.is_default:
                # Demote any other default to keep the partial unique
                # constraint satisfied before promoting this one.
                LabelSet.objects.filter(is_default=True).exclude(pk=labelset.pk).update(
                    is_default=False
                )
                updates["is_default"] = True
            if updates:
                for field, value in updates.items():
                    setattr(labelset, field, value)
                labelset.save(update_fields=list(updates.keys()))

    existing_label_texts = set(
        labelset.annotation_labels.values_list("text", flat=True)
    )

    for spec in DEFAULT_LABELS:
        if spec["text"] in existing_label_texts:
            continue
        label, _ = AnnotationLabel.objects.get_or_create(
            text=spec["text"],
            label_type=spec["label_type"],
            creator=system_user,
            analyzer=None,
            defaults={
                "description": spec["description"],
                "color": spec["color"],
                "icon": spec["icon"],
                "is_public": True,
                "read_only": False,
            },
        )
        labelset.annotation_labels.add(label)


def reverse_migration(apps, schema_editor):
    """Remove the seeded default labelset and any starter labels that aren't
    referenced by another labelset (so user-edited reuses survive)."""
    LabelSet = apps.get_model("annotations", "LabelSet")
    AnnotationLabel = apps.get_model("annotations", "AnnotationLabel")

    labelset = LabelSet.objects.filter(title=DEFAULT_LABELSET_TITLE).first()
    if labelset is None:
        return

    label_texts = [spec["text"] for spec in DEFAULT_LABELS]
    candidate_labels = list(
        labelset.annotation_labels.filter(text__in=label_texts).values_list(
            "id", flat=True
        )
    )
    labelset.delete()

    AnnotationLabel.objects.filter(
        id__in=candidate_labels, included_in_labelset__isnull=True
    ).delete()
