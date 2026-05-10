import logging
import uuid
from typing import Any, ClassVar, Optional

import django
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import (
    AbstractBaseUser,
    AbstractUser,
    AnonymousUser,
    Group,
)
from django.contrib.auth.models import UserManager as DjangoUserManager
from django.db import IntegrityError
from django.db.models import Q, QuerySet
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from guardian.models import GroupObjectPermissionBase, UserObjectPermissionBase

from opencontractserver.constants.users import (
    HANDLE_INSERT_RETRY_ATTEMPTS,
    USER_HANDLE_MAX_LENGTH,
)
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
from opencontractserver.users.handle_generator import generate_handle
from opencontractserver.users.validators import UserUnicodeUsernameValidator

logger = logging.getLogger(__name__)


class UserProfileManager(DjangoUserManager["User"]):
    """
    Custom manager for User model that implements visible_to_user pattern.

    Issue: #611 - Create User Profile Page with badge display and stats
    Epic: #572 - Social Features Epic
    """

    def visible_to_user(
        self, user: Optional["AbstractBaseUser"] = None
    ) -> QuerySet["User"]:
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
        # Handle None user as anonymous
        if user is None or isinstance(user, AnonymousUser):
            # Anonymous users can only see public profiles
            return self.filter(is_profile_public=True, is_active=True)

        # Authenticated users can see:
        # 1. Their own profile (even if private)
        # 2. All public profiles
        return self.filter(Q(id=user.pk) | Q(is_profile_public=True), is_active=True)


class User(AbstractUser):
    """Default user for OpenContractServer."""

    # Class attribute — referenced by Django admin forms (UserChangeForm,
    # UserCreationForm) directly, separate from the field validators list.
    username_validator = UserUnicodeUsernameValidator()

    # Declared at class body to avoid mutating the shared Field.validators list on every User() call.
    username = django.db.models.CharField(
        _("username"),
        max_length=150,
        unique=True,
        help_text=_(
            "Required. 150 characters or fewer. Letters, digits and "
            "@/./+/-/_/|/*/\\ only."
        ),
        validators=[UserUnicodeUsernameValidator()],
        error_messages={
            "unique": _("A user with that username already exists."),
        },
    )

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

    # Reddit-style display handle. Auto-assigned on save when missing;
    # surfaced via the ``UserType.displayName`` GraphQL resolver so users
    # without populated Auth0 ``name``/``given_name`` claims don't fall
    # through to the redacted ``user_<id>`` fallback.
    handle = django.db.models.CharField(
        "Display Handle",
        max_length=USER_HANDLE_MAX_LENGTH,
        unique=True,
        null=True,
        blank=True,
        help_text=(
            "Auto-assigned Reddit-style handle (e.g. 'cleverFox', 'cleverFox42'). "
            "Used by the displayName resolver when Auth0 name claims are absent. "
            "User-facing editing is out of scope for the initial rollout."
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

    # UI Preferences
    dismissed_getting_started = django.db.models.BooleanField(
        "Dismissed Getting Started",
        default=False,
        help_text="Whether the user has dismissed the Getting Started guide on the Discover page",
    )

    # Custom manager for profile visibility
    objects: ClassVar[UserProfileManager] = UserProfileManager()

    def __str__(self) -> str:
        return f"{self.username}: {self.email}"

    def get_absolute_url(self) -> str:
        """Get url for user's detail view.

        Returns:
            str: URL for user detail.

        """
        return reverse("users:detail", kwargs={"username": self.username})

    def save(self, *args: Any, **kwargs: Any) -> None:
        # Avoid referencing the slug column before it exists in initial migrations
        slug_column_exists = table_has_column(self._meta.db_table, "slug")

        # Skip slug processing when saving unrelated fields (e.g. last_login)
        update_fields = kwargs.get("update_fields")
        slug_being_saved = update_fields is None or "slug" in update_fields

        if slug_column_exists and slug_being_saved:
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

        # Auto-assign Reddit-style display handle. Mirrors the slug guard so
        # initial migrations that pre-date the column don't explode on save.
        # The django-guardian Anonymous user is a system account that never
        # surfaces to other users, so it never needs (or wants) a handle —
        # excluding it here also keeps the management command, migration,
        # and ``DisplayName`` query symmetric.
        handle_column_exists = table_has_column(self._meta.db_table, "handle")
        handle_being_saved = update_fields is None or "handle" in update_fields
        needs_handle = (
            handle_column_exists
            and handle_being_saved
            and (not self.handle or not str(self.handle).strip())
            and self.username != "Anonymous"
        )

        created = self.id is None

        if needs_handle:
            # Bounded retry loop: ``generate_handle`` checks uniqueness with a
            # non-locking ``.exists()`` query, so two concurrent inserts can
            # sample the same candidate before either commits. Catch the
            # resulting unique-constraint IntegrityError on the ``handle``
            # column and re-roll. With the ~56k-pair namespace the first
            # attempt almost always wins; the bound prevents pathological
            # loops if the namespace is misconfigured.
            #
            # ``scope_qs`` excludes ``self.pk`` only when re-saving an existing
            # row. For a brand-new INSERT, ``self.pk`` is ``None`` and stays
            # ``None`` even across failed attempts: Django captures the
            # RETURNING id only on a successful INSERT, so an IntegrityError
            # below leaves ``self.pk`` unset for the next iteration. That's
            # the correct behaviour — there's no committed row of ours to
            # exclude from the uniqueness check.
            user_cls = type(self)
            scope_qs = user_cls.objects.all()
            for attempt in range(HANDLE_INSERT_RETRY_ATTEMPTS):
                self.handle = generate_handle(
                    scope_qs=scope_qs.exclude(pk=self.pk) if self.pk else scope_qs,
                )
                try:
                    super().save(*args, **kwargs)
                    break
                except IntegrityError:
                    # Don't string-parse the DB error message — formats vary
                    # across drivers and constraint names. Instead query for
                    # an existing row holding our chosen handle: a hit means
                    # this WAS a handle collision and we should re-roll; a
                    # miss means the IntegrityError came from another column
                    # (username, slug, …) and must propagate.
                    chosen = self.handle
                    self.handle = None
                    if not chosen or not (
                        user_cls.objects.exclude(pk=self.pk)
                        .filter(handle=chosen)
                        .exists()
                    ):
                        raise
                    if attempt == HANDLE_INSERT_RETRY_ATTEMPTS - 1:
                        raise
                    continue
        else:
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
    def save(self, *args: Any, **kwargs: Any) -> None:
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
def calculate_export_filename(instance: "UserExport", filename: str) -> str:
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
    def save(self, *args: Any, **kwargs: Any) -> None:
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
def calculate_import_filename(instance: "UserImport", filename: str) -> str:
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
    def save(self, *args: Any, **kwargs: Any) -> None:
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

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Ensure only one instance exists"""
        if Installation.objects.exists() and not self.pk:
            raise ValueError("Cannot create multiple Installation instances")
        return super().save(*args, **kwargs)

    @classmethod
    def get(cls) -> "Installation":
        """Get or create the singleton installation instance"""
        instance, _ = cls.objects.get_or_create()
        return instance
