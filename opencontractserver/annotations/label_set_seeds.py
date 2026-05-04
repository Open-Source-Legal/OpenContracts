"""
Default LabelSet definition and seeding logic.

The data migration (``annotations/0069``) and the ``seed_default_labelset``
management command both call ``create_default_labelset`` from here so that the
behaviour stays in one place. The caller passes its own ``apps`` registry so
migrations use historical model state while the management command uses the
live registry.
"""

import logging

logger = logging.getLogger(__name__)

# Title used to identify the seeded default labelset. Treat this as a stable
# identifier — users may rename or reassign the default via is_default flips,
# but the seeder itself only looks for this title to stay idempotent.
DEFAULT_LABELSET_TITLE = "Default Labels"
DEFAULT_LABELSET_DESCRIPTION = (
    "Default annotation label set seeded at install. Pre-selected in the "
    "new-corpus modal so corpuses have a usable starter palette out of the "
    "box. Owned by the install's first superuser; safe to edit."
)

# A starter palette covering both generic research/review patterns
# (Important, Question, Reference) and the most common corporate-contract
# concepts (parties, dates, term, governing law, liability limits). Picked
# to be useful out of the box for legal/compliance teams without being
# overwhelming. Users can add, remove, or rename labels freely after
# creation — these are seeds, not lock-ins.
#
# label_type is "TOKEN_LABEL" everywhere because all of these apply to text
# spans rather than whole documents. Strings are used (instead of importing
# the LABEL_TYPES enum) so the migration runtime registry doesn't need to
# import the live module.
#
# Color palette: red for risk/exits, amber/orange for time pressure, blue
# for definitional/structural concepts, green for effective/positive dates,
# purple for actors, teal for cross-references, slate for jurisdictional
# scaffolding. Icon names map to lucide-react in the frontend; unknown
# names fall back to the default tag glyph, so non-existent icons just
# degrade gracefully.
DEFAULT_LABELS: list[dict[str, str]] = [
    # --- General research / review ---
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
    # --- Contract structure ---
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
    # --- Dates & lifecycle ---
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
    # --- Risk allocation ---
    {
        "text": "Limitation of Liability",
        "description": "Caps, carve-outs, or other liability-limiting language.",
        "color": "#ca8a04",
        "icon": "shield-alert",
        "label_type": "TOKEN_LABEL",
    },
]


def create_default_labelset(apps, schema_editor):
    """Create the install-wide default LabelSet and its starter labels.

    Idempotent: if a LabelSet titled ``DEFAULT_LABELSET_TITLE`` already
    exists, it is reused. Missing labels are added; existing labels are not
    duplicated. The labelset is marked ``is_default=True`` and ``is_public=
    True`` so all users see it by default.

    Args:
        apps: An app registry — either ``django.apps.apps`` (live) or the
            historical registry provided by a migration's ``apps`` parameter.
        schema_editor: The migration schema editor, or ``None`` when called
            from the management command.
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

    labelset = LabelSet.objects.filter(title=DEFAULT_LABELSET_TITLE).first()
    if labelset is None:
        labelset = LabelSet.objects.create(
            title=DEFAULT_LABELSET_TITLE,
            description=DEFAULT_LABELSET_DESCRIPTION,
            creator=system_user,
            is_public=True,
            is_default=True,
        )
    else:
        # Backfill flags on a pre-existing labelset that matched by title.
        updates = {}
        if not labelset.is_public:
            updates["is_public"] = True
        if not labelset.is_default:
            # Clear any other default first to satisfy the partial unique
            # constraint, then promote this one.
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
    """Remove the seeded default labelset and its starter labels.

    Only deletes labels owned by the seeded labelset and not used by any
    other labelset, to avoid pulling out labels users may have reused.
    """
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
