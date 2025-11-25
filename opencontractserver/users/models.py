import logging
import uuid

import django
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import (
    AbstractUser,
    Group,
)
from django.contrib.auth.models import UserManager as DjangoUserManager
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from guardian.models import GroupObjectPermissionBase, UserObjectPermissionBase

from opencontractserver.shared.db_utils import table_has_column
from opencontractserver.shared.defaults import jsonfield_default_value
from opencontractserver.shared.fields import NullableJSONField
from opencontractserver.shared.Models import BaseOCModel
from opencontractserver.shared.slug_utils import (
    generate_unique_slug,
    sanitize_slug,
    validate_user_slug_or_raise,
)
from opencontractserver.shared.utils import calc_oc_file_path
from opencontractserver.types.enums import ExportType
from opencontractserver.users.validators import UserUnicodeUsernameValidator

logger = logging.getLogger(__name__)


class UserProfileManager(DjangoUserManager):
    """
    Custom manager for User model that implements visible_to_user pattern.

    Issue: #611 - Create User Profile Page with badge display and stats
    Epic: #572 - Social Features Epic
    """

    def visible_to_user(self, user=None):
        """
        Returns queryset filtered to users whose profiles are visible to the requesting user.

        Privacy rules:
        - Own profile is always visible (even if private)
        - Public profiles are visible to everyone
        - Private profiles are only visible to the profile owner

        Args:
            user: The requesting user (or None for anonymous)

        Returns:
            QuerySet of User objects visible to the requesting user
        """
        from django.contrib.auth.models import AnonymousUser

        # Handle None user as anonymous
        if user is None or isinstance(user, AnonymousUser):
            # Anonymous users can only see public profiles
            return self.filter(is_profile_public=True, is_active=True)

        # Authenticated users can see:
        # 1. Their own profile (even if private)
        # 2. All public profiles
        return self.filter(Q(id=user.id) | Q(is_profile_public=True), is_active=True)


class User(AbstractUser):
    """Default user for OpenContractServer."""

    #: First and last name do not cover name patterns around the globe
    name = django.db.models.CharField(_("Name of User"), blank=True, max_length=255)
    first_name = django.db.models.CharField("First Name", blank=True, max_length=255)
    last_name = django.db.models.CharField("First Name", blank=True, max_length=255)

    given_name = django.db.models.CharField("First Name", blank=True, max_length=255)
    family_name = django.db.models.CharField("Last Name", blank=True, max_length=255)
    auth0_Id = django.db.models.CharField("Auth0 User ID", blank=True, max_length=255)
    phone = django.db.models.CharField("Phone Number", blank=True, max_length=255)
    email = django.db.models.CharField("Email Address", blank=True, max_length=255)

    synced = django.db.models.BooleanField("Synced Remote User Data", default=False)
    is_active = django.db.models.BooleanField(
        "Disabled Account", default=True
    )  # This is the django RemoveUserBackend default field to disable external accounts.
    email_verified = django.db.models.BooleanField("Is email verified?", default=False)
    is_social_user = django.db.models.BooleanField("Social Sign-up", default=False)

    # Open Contracts is going to be deployed publicly on a shoestring budget initially.
    # I'd like to make full functionality available, but I also can't afford to support
    # unlimited usage for others. This flag, if True, will limit total doc count to 10 docs
    # and total private corpus count to 1. All other functionality will remain the same.
    is_usage_capped = django.db.models.BooleanField("Usage Capped?", default=True)

    last_synced = django.db.models.DateTimeField(
        "Last Sync with Remote User Data", blank=True, null=True
    )
    first_signed_in = django.db.models.DateTimeField(
        "First login", default=timezone.now
    )
    last_ip = django.db.models.CharField("Last IP Address", blank=True, max_length=255)

    # Slug for public/profile URLs (case-sensitive)
    slug = django.db.models.CharField(
        "Slug",
        max_length=64,
        unique=True,
        null=True,
        blank=True,
        help_text=(
            "Case-sensitive URL slug. Allowed characters: A-Z, a-z, 0-9, and hyphen (-)."
        ),
    )

    # Cookie consent tracking
    cookie_consent_accepted = django.db.models.BooleanField(
        "Cookie Consent Accepted",
        default=False,
        help_text="Whether the user has accepted cookie consent",
    )
    cookie_consent_date = django.db.models.DateTimeField(
        "Cookie Consent Date",
        blank=True,
        null=True,
        help_text="When the user accepted cookie consent",
    )

    # Profile visibility (Issue #611 - User Profile Page)
    is_profile_public = django.db.models.BooleanField(
        "Public Profile",
        default=True,
        help_text="Whether this user's profile is visible to other users",
    )

    # Custom manager for profile visibility
    objects = UserProfileManager()

    def __str__(self):
        return f"{self.username}: {self.email}"

    def __init__(self, *args, **kwargs):
        self._meta.get_field("username").validators[0] = UserUnicodeUsernameValidator()

        super().__init__(*args, **kwargs)

    def get_absolute_url(self):
        """Get url for user's detail view.

        Returns:
            str: URL for user detail.

        """
        return reverse("users:detail", kwargs={"username": self.username})

    def save(self, *args, **kwargs):
        # Avoid referencing the slug column before it exists in initial migrations
        slug_column_exists = table_has_column(self._meta.db_table, "slug")

        if slug_column_exists:
            # Ensure slug exists and is valid
            if not self.slug or not isinstance(self.slug, str) or not self.slug.strip():
                # Generate a unique slug from username
                base_value = self.username or self.email or "user"
                # We cannot query without saving if no PK yet; use all users for uniqueness
                scope_qs = get_user_model().objects.all()
                self.slug = generate_unique_slug(
                    base_value=base_value,
                    scope_qs=scope_qs.exclude(pk=self.pk) if self.pk else scope_qs,
                    slug_field="slug",
                    max_length=64,
                    fallback_prefix="user",
                )
            else:
                # Sanitize and validate provided slug
                sanitized = sanitize_slug(self.slug, max_length=64)
                if not sanitized:
                    from django.core.exceptions import ValidationError

                    raise ValidationError({"slug": "Slug cannot be empty."})
                validate_user_slug_or_raise(sanitized)
                self.slug = sanitized

        created = self.id is None
        super().save(*args, **kwargs)

        # after save user has ID
        # add user to group only after creating
        if created and not self.username == "Anonymous":
            logger.info(
                f"Adding user {self.username} to group {settings.DEFAULT_PERMISSIONS_GROUP}"
            )
            # Ensure the default permissions group is present even if database was flushed during tests.
            # Using get_or_create avoids breaking user creation when the group is missing.
            my_group, _ = Group.objects.get_or_create(
                name=settings.DEFAULT_PERMISSIONS_GROUP
            )
            self.groups.add(my_group)


class Assignment(django.db.models.Model):
    """
    This was included very early in an aspirational attempt to build some workflow
    functionality to assign and track review to specific users. Still a good idea, still
    not started, and still a lot of work ;-). Leaving this, but it's not used anywhere ATM.
    """

    name = django.db.models.CharField(max_length=1024, null=True, blank=True)
    document = django.db.models.ForeignKey(
        "documents.Document", null=False, on_delete=django.db.models.CASCADE
    )
    corpus = django.db.models.ForeignKey(
        "corpuses.Corpus", null=True, on_delete=django.db.models.CASCADE
    )

    resulting_annotations = django.db.models.ManyToManyField(
        "annotations.Annotation", blank=True
    )
    resulting_relationships = django.db.models.ManyToManyField(
        "annotations.Relationship", blank=True
    )

    comments = django.db.models.TextField(default="", blank=False)

    # Sharing
    assignor = django.db.models.ForeignKey(
        get_user_model(),
        on_delete=django.db.models.CASCADE,
        related_name="created_assignments",
        related_query_name="created_assignment",
        null=False,
        default=1,
    )
    assignee = django.db.models.ForeignKey(
        get_user_model(),
        related_name="my_assignments",
        related_query_name="my_assignment",
        on_delete=django.db.models.SET_NULL,
        null=True,
        blank=True,
    )

    # Timing variables
    completed_at = django.db.models.DateTimeField(
        "Creation Date and Time", default=None, blank=True, null=True
    )
    created = django.db.models.DateTimeField(
        "Creation Date and Time", default=timezone.now
    )
    modified = django.db.models.DateTimeField(default=timezone.now, blank=True)

    class Meta:
        permissions = (
            ("permission_assignment", "permission assignment"),
            ("publish_assignment", "publish assignment"),
            ("create_assignment", "create assignment"),
            ("read_assignment", "read assignment"),
            ("update_assignment", "update assignment"),
            ("remove_assignment", "delete assignment"),
            ("comment_assignment", "comment assignment"),
        )

    # Override save to update modified on save
    def save(self, *args, **kwargs):
        """On save, update timestamps"""
        if not self.pk:
            self.created = timezone.now()
        self.modified = timezone.now()

        return super().save(*args, **kwargs)


# Model for Django Guardian permissions.
class AssignmentUserObjectPermission(UserObjectPermissionBase):
    content_object = django.db.models.ForeignKey(
        "Assignment", on_delete=django.db.models.CASCADE
    )
    # enabled = False


# Model for Django Guardian permissions.
class AssignmentGroupObjectPermission(GroupObjectPermissionBase):
    content_object = django.db.models.ForeignKey(
        "Assignment", on_delete=django.db.models.CASCADE
    )
    # enabled = False


# Can't use lambdas in migrations, sadly, so need to wrap underlying function
def calculate_export_filename(instance, filename):
    return calc_oc_file_path(
        instance, filename, f"user_{instance.creator.id}/exports/{filename}"
    )


class UserExport(BaseOCModel):

    file = django.db.models.FileField(blank=True, upload_to=calculate_export_filename)
    name = django.db.models.CharField(max_length=1024, null=True, blank=True)
    created = django.db.models.DateTimeField(default=timezone.now)
    started = django.db.models.DateTimeField(null=True)
    finished = django.db.models.DateTimeField(null=True)
    errors = django.db.models.TextField(blank=True)
    post_processors = django.db.models.JSONField(
        default=list,
        blank=True,
        help_text="List of fully qualified Python paths to post-processor functions",
    )
    input_kwargs = NullableJSONField(
        default=jsonfield_default_value,
        null=True,
        blank=True,
        help_text="Additional keyword arguments to pass to post-processors",
    )

    format = django.db.models.CharField(
        max_length=128,
        blank=False,
        null=False,
        choices=ExportType.choices(),
        default=ExportType.OPEN_CONTRACTS,
    )

    # Backend stuff
    backend_lock = django.db.models.BooleanField(
        default=False
    )  # If this is being processed by backend

    # Sharing
    is_public = django.db.models.BooleanField(default=False)
    creator = django.db.models.ForeignKey(
        get_user_model(),
        on_delete=django.db.models.CASCADE,
        null=False,
        default=1,
    )

    class Meta:
        permissions = (
            ("permission_userexport", "permission user export"),
            ("publish_userexport", "publish user export"),
            ("create_userexport", "create user export"),
            ("read_userexport", "read user export"),
            ("update_userexport", "update user export"),
            ("remove_userexport", "delete user export"),
            ("comment_userexport", "comment user export"),
        )

    # Override save to update modified on save
    def save(self, *args, **kwargs):
        """On save, update timestamps"""
        if not self.pk:
            self.created = timezone.now()

        return super().save(*args, **kwargs)


# Model for Django Guardian permissions.
class UserExportUserObjectPermission(UserObjectPermissionBase):
    content_object = django.db.models.ForeignKey(
        "UserExport", on_delete=django.db.models.CASCADE
    )
    # enabled = False


# Model for Django Guardian permissions.
class UserExportGroupObjectPermission(GroupObjectPermissionBase):
    content_object = django.db.models.ForeignKey(
        "UserExport", on_delete=django.db.models.CASCADE
    )
    # enabled = False


# Can't use lambda functions so need a wrapper
def calculate_import_filename(instance, filename):
    return calc_oc_file_path(
        instance, filename, f"user_{instance.creator.id}/imports/{filename}"
    )


class UserImport(BaseOCModel):
    zip = django.db.models.FileField(blank=True, upload_to=calculate_import_filename)
    name = django.db.models.CharField(max_length=1024, null=True, blank=True)
    created = django.db.models.DateTimeField(default=timezone.now)
    started = django.db.models.DateTimeField(null=True)
    finished = django.db.models.DateTimeField(null=True)
    errors = django.db.models.TextField(blank=True)

    # Sharing
    is_public = django.db.models.BooleanField(default=False)
    creator = django.db.models.ForeignKey(
        get_user_model(),
        on_delete=django.db.models.CASCADE,
        null=False,
        default=1,
    )

    class Meta:
        permissions = (
            ("permission_userimport", "permission user import"),
            ("publish_userimport", "publish user import"),
            ("create_userimport", "create user import"),
            ("read_userimport", "read user import"),
            ("update_userimport", "update user import"),
            ("remove_userimport", "delete user import"),
            ("comment_userimport", "comment user import"),
        )

    # Override save to update modified on save
    def save(self, *args, **kwargs):
        """On save, update timestamps"""
        if not self.pk:
            self.created = timezone.now()

        return super().save(*args, **kwargs)


class Auth0APIToken(django.db.models.Model):
    token = django.db.models.TextField("Auth0 Token")
    expiration_Date = django.db.models.DateTimeField("Token Expiration Date:")
    refreshing = django.db.models.BooleanField("Refreshing Token", default=False)
    auth0_Response = django.db.models.TextField("Last Response from Auth0")


class Installation(django.db.models.Model):
    """
    Singleton model to track installation-specific information for telemetry.
    Only one instance of this model should ever exist.
    """

    id = django.db.models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Unique identifier for this installation",
    )
    created = django.db.models.DateTimeField(
        "Installation Date", default=timezone.now, editable=False
    )

    class Meta:
        verbose_name = "Installation"
        verbose_name_plural = "Installation"

    def save(self, *args, **kwargs):
        """Ensure only one instance exists"""
        if Installation.objects.exists() and not self.pk:
            raise ValueError("Cannot create multiple Installation instances")
        return super().save(*args, **kwargs)

    @classmethod
    def get(cls) -> "Installation":
        """Get or create the singleton installation instance"""
        instance, _ = cls.objects.get_or_create()
        return instance
