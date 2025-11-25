from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models

from opencontractserver.corpuses.models import Corpus
from opencontractserver.shared.defaults import jsonfield_default_value
from opencontractserver.shared.fields import NullableJSONField
from opencontractserver.shared.Models import BaseOCModel

User = get_user_model()


class BadgeTypeChoices(models.TextChoices):
    GLOBAL = "GLOBAL", "Global"
    CORPUS = "CORPUS", "Corpus-Specific"


class Badge(BaseOCModel):
    """
    Represents a badge that can be awarded to users for achievements.
    Badges can be global or corpus-specific.
    """

    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Unique name for the badge",
    )

    description = models.TextField(
        help_text="Description of what this badge represents or how to earn it"
    )

    icon = models.CharField(
        max_length=100,
        help_text="Icon identifier from lucide-react (e.g., 'Trophy', 'Star', 'Award')",
    )

    badge_type = models.CharField(
        max_length=10,
        choices=BadgeTypeChoices.choices,
        default=BadgeTypeChoices.GLOBAL,
        help_text="Whether this badge is global or corpus-specific",
    )

    color = models.CharField(
        max_length=7,
        default="#05313d",
        help_text="Hex color code for badge display",
    )

    corpus = models.ForeignKey(
        Corpus,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="badges",
        help_text="If badge_type is CORPUS, the corpus this badge belongs to",
    )

    is_auto_awarded = models.BooleanField(
        default=False,
        help_text="Whether this badge is automatically awarded based on criteria",
    )

    criteria_config = NullableJSONField(
        default=jsonfield_default_value,
        blank=True,
        null=True,
        help_text="JSON configuration for auto-award criteria. "
        "Example: {'type': 'reputation_threshold', 'value': 100, 'scope': 'global'}",
    )

    class Meta:
        ordering = ["-created"]
        indexes = [
            models.Index(fields=["badge_type", "corpus"]),
            models.Index(fields=["is_auto_awarded"]),
        ]
        permissions = (
            ("permission_badge", "permission badge"),
            ("publish_badge", "publish badge"),
            ("create_badge", "create badge"),
            ("read_badge", "read badge"),
            ("update_badge", "update badge"),
            ("remove_badge", "remove badge"),
        )

    def clean(self):
        """
        Validate that corpus-specific badges have a corpus and global badges don't.
        Also validate criteria_config structure for auto-awarded badges using the registry.
        """
        from opencontractserver.badges.criteria_registry import BadgeCriteriaRegistry

        # Validate badge_type and corpus relationship
        if self.badge_type == BadgeTypeChoices.CORPUS and not self.corpus:
            raise ValidationError(
                {"corpus": "Corpus-specific badges must have a corpus assigned."}
            )
        if self.badge_type == BadgeTypeChoices.GLOBAL and self.corpus:
            raise ValidationError(
                {"corpus": "Global badges cannot be associated with a corpus."}
            )

        # Enhanced validation for auto-awarded badges
        if self.is_auto_awarded:
            if not self.criteria_config:
                raise ValidationError(
                    {
                        "criteria_config": "Auto-awarded badges must have criteria configuration. "
                        "Either provide criteria_config or set is_auto_awarded to False."
                    }
                )

            # Validate criteria config against registry
            is_valid, error_message = BadgeCriteriaRegistry.validate_config(
                self.criteria_config
            )
            if not is_valid:
                raise ValidationError(
                    {
                        "criteria_config": f"Invalid criteria configuration: {error_message}"
                    }
                )

            # Validate scope compatibility between criteria type and badge type
            criteria_type = self.criteria_config.get("type")
            criteria_def = BadgeCriteriaRegistry.get(criteria_type)
            if criteria_def:
                # Check if criteria scope matches badge type
                if (
                    criteria_def.scope == "corpus"
                    and self.badge_type != BadgeTypeChoices.CORPUS
                ):
                    raise ValidationError(
                        {
                            "criteria_config": f"Criteria type '{criteria_type}' can only be used "
                            f"with corpus-specific badges (CORPUS), not {self.badge_type} badges"
                        }
                    )
                if (
                    criteria_def.scope == "global"
                    and self.badge_type != BadgeTypeChoices.GLOBAL
                ):
                    raise ValidationError(
                        {
                            "criteria_config": f"Criteria type '{criteria_type}' can only be used "
                            f"with global badges (GLOBAL), not {self.badge_type} badges"
                        }
                    )

        # Validate that non-auto-awarded badges don't have criteria_config
        elif self.criteria_config:
            raise ValidationError(
                {
                    "criteria_config": "Only auto-awarded badges can have criteria configuration. "
                    "Either set is_auto_awarded to True or remove criteria_config."
                }
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        scope = f" ({self.corpus.title})" if self.corpus else " (Global)"
        return f"{self.name}{scope}"


class UserBadge(models.Model):
    """
    Represents the awarding of a badge to a user.
    Tracks when and by whom the badge was awarded.
    """

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="badges",
        help_text="User who received the badge",
    )

    badge = models.ForeignKey(
        Badge,
        on_delete=models.CASCADE,
        related_name="awards",
        help_text="Badge that was awarded",
    )

    awarded_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the badge was awarded",
    )

    awarded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="badges_awarded",
        help_text="User who awarded the badge (null for auto-awards)",
    )

    corpus = models.ForeignKey(
        Corpus,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="user_badges",
        help_text="For corpus-specific badges, the context in which it was awarded",
    )

    class Meta:
        ordering = ["-awarded_at"]
        constraints = [
            # Constraint for global badges (corpus is NULL)
            models.UniqueConstraint(
                fields=["user", "badge"],
                condition=models.Q(corpus__isnull=True),
                name="unique_user_badge_global",
            ),
            # Constraint for corpus-specific badges (corpus is NOT NULL)
            models.UniqueConstraint(
                fields=["user", "badge", "corpus"],
                condition=models.Q(corpus__isnull=False),
                name="unique_user_badge_corpus",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "awarded_at"]),
            models.Index(fields=["badge", "corpus"]),
        ]

    def clean(self):
        """
        Validate that corpus-specific badge awards have matching corpus references.
        """
        if self.badge.badge_type == BadgeTypeChoices.CORPUS:
            if not self.corpus:
                raise ValidationError(
                    {"corpus": "Corpus-specific badge awards must specify a corpus."}
                )
            if self.badge.corpus != self.corpus:
                raise ValidationError(
                    {
                        "corpus": f"Badge is for corpus '{self.badge.corpus}', "
                        f"but awarded in context of '{self.corpus}'."
                    }
                )
        else:  # Global badge
            if self.corpus:
                raise ValidationError(
                    {"corpus": "Global badges cannot have a corpus context."}
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.badge.name} → {self.user.username} ({self.awarded_at.date()})"
