from __future__ import annotations

import difflib
import hashlib
import logging
import re
import uuid
from typing import TYPE_CHECKING, Any

import django
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.validators import URLValidator
from django.db import transaction
from django.utils import timezone
from guardian.models import GroupObjectPermissionBase, UserObjectPermissionBase
from tree_queries.models import TreeNode

from opencontractserver.constants.document_processing import (
    DEFAULT_DOCUMENT_PATH_PREFIX,
    MARKDOWN_MIME_TYPE,
    MAX_FILENAME_LENGTH,
    MAX_PROCESSING_ERROR_LENGTH,
    MAX_PROCESSING_TRACEBACK_LENGTH,
    PERSONAL_CORPUS_DESCRIPTION,
    PERSONAL_CORPUS_TITLE,
)
from opencontractserver.constants.licenses import (
    CUSTOM,
    LICENSE_CHOICES,
    LICENSE_LINK_MAX_LENGTH,
    LICENSE_SPDX_MAX_LENGTH,
)
from opencontractserver.constants.notifications import (
    NOTIFICATION_BULK_CREATE_BATCH_SIZE,
)
from opencontractserver.corpuses.managers import CorpusActionExecutionManager
from opencontractserver.shared.Models import BaseOCModel
from opencontractserver.shared.QuerySets import PermissionedTreeQuerySet
from opencontractserver.shared.slug_utils import generate_unique_slug, sanitize_slug
from opencontractserver.shared.user_can_mixin import InstanceUserCanMixin
from opencontractserver.shared.utils import calc_oc_file_path
from opencontractserver.utils.embeddings import generate_embeddings_from_text
from opencontractserver.utils.text import truncate

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser, AnonymousUser
    from django.db.models import QuerySet

    from opencontractserver.annotations.models import AnnotationLabel
    from opencontractserver.documents.models import Document, DocumentPath
    from opencontractserver.users.models import User as UserModel

logger = logging.getLogger(__name__)


def calculate_icon_filepath(instance: Any, filename: str) -> str:
    return calc_oc_file_path(
        instance,
        filename,
        f"user_{instance.creator.id}/{instance.__class__.__name__}/icons/{uuid.uuid4()}",
    )


def calculate_temporary_filepath(instance: Any, filename: str) -> str:
    return calc_oc_file_path(
        instance,
        filename,
        "temporary_files/",
    )


def calculate_description_filepath(instance: Any, filename: str) -> str:
    """Generate a unique path for corpus markdown descriptions."""
    return calc_oc_file_path(
        instance,
        filename,
        f"user_{instance.creator.id}/{instance.__class__.__name__}/md_descriptions/{uuid.uuid4()}",
    )


# -------------------- CorpusCategory -------------------- #


class CorpusCategory(BaseOCModel):
    """Admin-defined categories for organizing corpuses (e.g., Legislation, Contracts)."""

    name = django.db.models.CharField(max_length=255, unique=True)
    description = django.db.models.TextField(blank=True, default="")
    icon = django.db.models.CharField(
        max_length=100,
        default="folder",
        help_text="Lucide icon name (e.g., 'scroll', 'file-text', 'building-2')",
    )
    color = django.db.models.CharField(
        max_length=7,
        default="#3B82F6",
        help_text="Hex color code for the category badge",
    )
    sort_order = django.db.models.IntegerField(
        default=0, help_text="Order in which categories appear in UI"
    )

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "Corpus Category"
        verbose_name_plural = "Corpus Categories"

    def __str__(self) -> str:
        return self.name


class TemporaryFileHandle(django.db.models.Model):
    """
    This may seem useless, but lets us leverage django's infrastructure to support multiple
    file storage backends to hand-off large files to workers using either S3 (for large deploys)
    or the django containers storage. There's no way to pass files directly to celery worker
    containers.
    """

    file = django.db.models.FileField(
        blank=True, null=True, upload_to=calculate_temporary_filepath
    )


# Create your models here.
class Corpus(InstanceUserCanMixin, TreeNode):
    """
    Corpus, which stores a collection of documents that are grouped for machine learning / study / export purposes.

    Inherits ``InstanceUserCanMixin`` so ``corpus.user_can(user, perm)``
    delegates to ``Corpus.objects.user_can(...)`` (which extends
    ``PermissionedTreeQuerySet``'s ``UserCanMixin``), matching the
    ``BaseOCModel`` surface for non-TreeNode models.
    """

    # Model variables
    title = django.db.models.CharField(max_length=1024, db_index=True)
    description = django.db.models.TextField(default="", blank=True)
    slug = django.db.models.CharField(
        max_length=128,
        db_index=True,
        null=True,
        blank=True,
        help_text=(
            "Case-sensitive slug unique per creator. Allowed: A-Z, a-z, 0-9, hyphen (-)."
        ),
    )
    md_description = django.db.models.FileField(
        blank=True,
        null=True,
        upload_to=calculate_description_filepath,
        help_text="Markdown description file for this corpus.",
    )
    icon = django.db.models.FileField(
        blank=True, null=True, upload_to=calculate_icon_filepath
    )

    # Categories and Labels in the Corpus
    categories = django.db.models.ManyToManyField(
        "CorpusCategory",
        blank=True,
        related_name="corpuses",
        help_text="Categories assigned to this corpus for discovery filtering",
    )
    label_set = django.db.models.ForeignKey(
        "annotations.LabelSet",
        null=True,
        blank=True,
        on_delete=django.db.models.SET_NULL,
        related_name="used_by_corpuses",
        related_query_name="used_by_corpus",
    )

    # Post-processors to run during export
    post_processors = django.db.models.JSONField(
        default=list,
        blank=True,
        help_text="List of fully qualified Python paths to post-processor functions",
    )

    # Embedder configuration
    preferred_embedder = django.db.models.CharField(
        max_length=1024,
        null=True,
        blank=True,
        help_text="Fully qualified Python path to the embedder class to use for this corpus. "
        "Auto-populated from DEFAULT_EMBEDDER at creation if not set. "
        "Immutable after documents are added (use re-embed to change).",
    )
    created_with_embedder = django.db.models.CharField(
        max_length=1024,
        null=True,
        blank=True,
        editable=False,
        help_text="The embedder that was active when this corpus was created. "
        "Set automatically and never changes (audit trail).",
    )

    # Agent instructions
    corpus_agent_instructions = django.db.models.TextField(
        null=True,
        blank=True,
        help_text=(
            "Custom system instructions for the corpus-level agent. "
            "If not set, uses DEFAULT_CORPUS_AGENT_INSTRUCTIONS from settings."
        ),
    )
    document_agent_instructions = django.db.models.TextField(
        null=True,
        blank=True,
        help_text=(
            "Custom system instructions for document-level agents in this corpus. "
            "If not set, uses DEFAULT_DOCUMENT_AGENT_INSTRUCTIONS from settings."
        ),
    )

    # Agent memory
    memory_enabled = django.db.models.BooleanField(
        default=False,
        help_text=(
            "Enable agent memory system for this corpus. When enabled, agents "
            "accumulate reusable insights from conversations into a memory document."
        ),
    )
    # NOTE: on_delete=SET_NULL means deleting the memory Document leaves
    # memory_enabled=True.  This is intentional — get_or_create_memory_document
    # will transparently recreate the document on the next agent interaction,
    # preserving the "memory stays enabled across disable/enable cycles" design.
    memory_document = django.db.models.OneToOneField(
        "documents.Document",
        on_delete=django.db.models.SET_NULL,
        null=True,
        blank=True,
        related_name="memory_for_corpus",
        help_text="The Document storing accumulated agent memory for this corpus.",
    )

    # Licensing
    license = django.db.models.CharField(
        max_length=LICENSE_SPDX_MAX_LENGTH,
        choices=LICENSE_CHOICES,
        default="",
        blank=True,
        help_text="SPDX identifier of the license applied to this corpus.",
    )
    license_link = django.db.models.URLField(
        max_length=LICENSE_LINK_MAX_LENGTH,
        default="",
        blank=True,
        validators=[URLValidator(schemes=["http", "https"])],
        help_text=(
            "URL to the full license text. Required when license is 'CUSTOM', "
            "optional for standard CC licenses."
        ),
    )

    # Sharing
    allow_comments = django.db.models.BooleanField(default=False)
    is_public = django.db.models.BooleanField(default=False)
    creator = django.db.models.ForeignKey(
        get_user_model(),
        on_delete=django.db.models.CASCADE,
        null=False,
        default=1,
    )

    # Object lock
    backend_lock = django.db.models.BooleanField(default=False)
    user_lock = django.db.models.ForeignKey(  # If another user is editing the document, it should be locked.
        get_user_model(),
        on_delete=django.db.models.CASCADE,
        related_name="editing_corpuses",
        related_query_name="editing_corpus",
        null=True,
        blank=True,
    )

    # Error status
    error = django.db.models.BooleanField(default=False)

    # Personal corpus flag
    is_personal = django.db.models.BooleanField(
        default=False,
        help_text="True if this is the user's personal 'My Documents' corpus",
    )

    # Timing variables
    created = django.db.models.DateTimeField(default=timezone.now)
    modified = django.db.models.DateTimeField(default=timezone.now, blank=True)

    # ------ Revision mechanics ------ #
    REVISION_SNAPSHOT_INTERVAL = 10

    def _read_md_description_content(self) -> str:
        """Return the current markdown description as text.

        Handles both text-mode and binary-mode reads so it works regardless of
        how the file was saved.
        """
        if not (self.md_description and self.md_description.name):
            return ""

        # First try text-mode which yields `str` directly.
        try:
            self.md_description.open("r")
            try:
                return self.md_description.read()
            finally:
                self.md_description.close()
        except Exception:
            # Fall back to binary mode and decode manually.
            try:
                self.md_description.open("rb")
                return self.md_description.read().decode("utf-8", errors="ignore")
            finally:
                self.md_description.close()

    @staticmethod
    def _markdown_to_plain_text(md: str) -> str:
        """Convert markdown to plain text by stripping formatting syntax.

        Handles the most common markdown constructs. Table cell separators
        and exotic extensions are not covered — the output is best-effort
        plain text suitable for card display and search indexing.
        """
        text = md
        # Remove fenced code blocks (keep content)
        text = re.sub(
            r"^```[^\n]*\n(.*?)^```", r"\1", text, flags=re.MULTILINE | re.DOTALL
        )
        # Remove HTML tags
        text = re.sub(r"<[^>]+>", "", text)
        # Remove headings markers
        text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
        # Remove bold/italic markers (DOTALL for multiline spans)
        text = re.sub(r"\*{1,3}(.+?)\*{1,3}", r"\1", text, flags=re.DOTALL)
        text = re.sub(r"_{1,3}(.+?)_{1,3}", r"\1", text, flags=re.DOTALL)
        # Remove strikethrough
        text = re.sub(r"~~(.+?)~~", r"\1", text, flags=re.DOTALL)
        # Remove images ![alt](url) — must run before links
        text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
        # Convert links [text](url) → text
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
        # Remove inline code backticks
        text = re.sub(r"`(.+?)`", r"\1", text)
        # Remove blockquote markers
        text = re.sub(r"^>\s+", "", text, flags=re.MULTILINE)
        # Remove horizontal rules
        text = re.sub(r"^[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)
        # Remove list markers
        text = re.sub(r"^[\s]*[-*+]\s+", "", text, flags=re.MULTILINE)
        text = re.sub(r"^[\s]*\d+\.\s+", "", text, flags=re.MULTILINE)
        # Collapse multiple blank lines
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def update_description(
        self, *, new_content: str, author: AbstractBaseUser | int
    ) -> CorpusDescriptionRevision | None:
        """Create a new revision and update md_description.

        Also keeps the plain-text ``description`` field in sync so that
        list views and card components always reflect the latest content.

        Args:
            new_content (str): Markdown content.
            author (User | int): Responsible user.
        Returns:
            CorpusDescriptionRevision | None: the stored revision or None if no content change.
        """

        author_obj: AbstractBaseUser
        if isinstance(author, int):
            author_obj = get_user_model().objects.get(pk=author)
        else:
            author_obj = author

        original_content = self._read_md_description_content()

        if original_content == (new_content or ""):
            return None  # No change

        with transaction.atomic():
            # Save new markdown file
            filename = f"{uuid.uuid4()}.md"
            self.md_description.save(
                filename, ContentFile(new_content.encode("utf-8")), save=False
            )
            # Keep the plain-text description field in sync
            self.description = self._markdown_to_plain_text(new_content)
            self.modified = timezone.now()
            self.save()

            # Compute next version
            from opencontractserver.corpuses.models import (  # avoid circular
                CorpusDescriptionRevision,
            )

            latest_rev = (
                CorpusDescriptionRevision.objects.filter(corpus_id=self.pk)
                .order_by("-version")
                .first()
            )
            next_version = 1 if latest_rev is None else latest_rev.version + 1

            diff_text = "\n".join(
                difflib.unified_diff(
                    original_content.splitlines(),
                    new_content.splitlines(),
                    lineterm="",
                )
            )

            should_snapshot = next_version % self.REVISION_SNAPSHOT_INTERVAL == 0
            snapshot_text = (
                new_content if should_snapshot or next_version == 1 else None
            )

            revision = CorpusDescriptionRevision.objects.create(
                corpus=self,
                author=author_obj,  # type: ignore[misc]
                version=next_version,
                diff=diff_text,
                snapshot=snapshot_text,
                checksum_base=hashlib.sha256(original_content.encode()).hexdigest(),
                checksum_full=hashlib.sha256(new_content.encode()).hexdigest(),
            )

        return revision

    objects = PermissionedTreeQuerySet.as_manager(with_tree_fields=True)

    class Meta:
        permissions = (
            ("permission_corpus", "permission corpus"),
            ("publish_corpus", "publish corpus"),
            ("create_corpus", "create corpus"),
            ("read_corpus", "read corpus"),
            ("update_corpus", "update corpus"),
            ("remove_corpus", "delete corpus"),
            ("comment_corpus", "comment corpus"),
        )
        indexes = [
            django.db.models.Index(fields=["title"]),
            django.db.models.Index(fields=["label_set"]),
            django.db.models.Index(fields=["creator"]),
            django.db.models.Index(fields=["user_lock"]),
            django.db.models.Index(fields=["created"]),
            django.db.models.Index(fields=["modified"]),
            django.db.models.Index(fields=["creator", "is_personal"]),
        ]
        ordering = ("created",)
        base_manager_name = "objects"
        constraints = [
            django.db.models.UniqueConstraint(
                fields=["creator", "slug"], name="uniq_corpus_slug_per_creator_cs"
            ),
            django.db.models.UniqueConstraint(
                fields=["creator"],
                condition=django.db.models.Q(is_personal=True),
                name="one_personal_corpus_per_user",
            ),
        ]

    # Override save to update modified on save
    def save(self, *args: Any, **kwargs: Any) -> None:
        """On save, update timestamps and freeze embedder on creation."""
        from opencontractserver.pipeline.utils import get_default_embedder_path

        # Ensure slug exists and is unique within creator scope
        if not self.slug or not isinstance(self.slug, str) or not self.slug.strip():
            base_value = self.title or "corpus"
            scope = Corpus.objects.filter(creator_id=self.creator_id)
            if self.pk:
                scope = scope.exclude(pk=self.pk)
            self.slug = generate_unique_slug(
                base_value=base_value,
                scope_qs=scope,
                slug_field="slug",
                max_length=128,
                fallback_prefix="corpus",
            )
        else:
            self.slug = sanitize_slug(self.slug, max_length=128)

        if not self.pk:
            self.created = timezone.now()

            # Freeze embedder at creation time (Issue #437):
            # If no preferred_embedder was explicitly provided, default to the
            # current default embedder from PipelineSettings so the corpus has
            # a stable, immutable binding.
            default_embedder = get_default_embedder_path()
            if self.preferred_embedder is None:
                self.preferred_embedder = default_embedder

            # Record which embedder was active at creation (audit trail).
            # This never changes, even if preferred_embedder is later updated
            # through a re-embed operation.
            self.created_with_embedder = self.preferred_embedder or default_embedder

        self.modified = timezone.now()

        # Detect is_public changes so we can propagate to documents.
        # Only check when updating an existing corpus and is_public might change.
        #
        # Race condition note: there is a TOCTOU window between the SELECT
        # (old_is_public lookup) and the UPDATE (super().save()).  A concurrent
        # save() could change is_public between these two calls, potentially
        # causing a missed propagation.  This is acceptable because corpus
        # visibility changes are low-frequency admin operations, and the
        # propagation is idempotent so a retry or subsequent save corrects it.
        _propagate_public = False
        if self.pk:
            update_fields = kwargs.get("update_fields")
            if update_fields is None or "is_public" in update_fields:
                old_is_public = (
                    Corpus.objects.filter(pk=self.pk)
                    .values_list("is_public", flat=True)
                    .first()
                )
                if old_is_public is not None and old_is_public != self.is_public:
                    _propagate_public = True

        super().save(*args, **kwargs)

        if _propagate_public:
            self._propagate_public_status_to_documents()

    def _propagate_public_status_to_documents(self) -> None:
        """Propagate this corpus's is_public flag to its documents.

        When a corpus becomes public, all its documents become public —
        EXCEPT documents that also live in another *private* corpus owned
        by a different user. Publicizing those would leak material the
        actor never had authority to share. Such docs are skipped and a
        warning is logged. (I-1 fix.)

        When a corpus becomes private, documents are set private ONLY if
        they are not in any other public corpus (preserving visibility
        for documents shared across multiple corpora).

        Document creators (other than the actor) are notified for every
        publicized document so they can audit the change.

        This maintains the permissioning guide's rule: both document AND
        corpus must have is_public=True for anonymous access.
        """
        from opencontractserver.documents.models import Document, DocumentPath
        from opencontractserver.notifications.models import (
            Notification,
            NotificationTypeChoices,
        )

        doc_ids = list(
            DocumentPath.objects.filter(
                corpus=self, is_current=True, is_deleted=False
            ).values_list("document_id", flat=True)
        )

        if not doc_ids:
            return

        if self.is_public:
            # Wrap the cross-owner snapshot + update + notification fan-out
            # in a single transaction so a concurrent publicize cannot slip
            # in between the snapshot and the update and cause a stale
            # notification for a document that didn't actually transition
            # in this call. Computing cross_owner_blocked_ids INSIDE the
            # atomic block also closes the narrow race where a document is
            # added to a new cross-owner private corpus between the
            # membership check and the update.
            with transaction.atomic():
                # Identify documents that also live in a private corpus
                # owned by someone OTHER than this corpus's creator.
                # Publicizing those would expose material the actor never
                # had authority to share, so they are excluded.
                #
                # NOTE: this SELECT is not protected by ``SELECT FOR
                # UPDATE`` — a concurrent ``DocumentPath`` insert that
                # links a document to a different cross-owner private
                # corpus between this snapshot and the
                # ``Document.objects.select_for_update()`` update below
                # could in theory escape the block. Closing that window
                # would require an explicit lock on the ``DocumentPath``
                # rows as well; the residual window is negligible in
                # practice (the publicize and the cross-owner-add must
                # interleave on millisecond boundaries) and the read-
                # committed snapshot still catches every membership
                # established before the atomic block opens.
                cross_owner_blocked_ids = set(
                    DocumentPath.objects.filter(
                        document_id__in=doc_ids,
                        corpus__is_public=False,
                        is_current=True,
                        is_deleted=False,
                    )
                    .exclude(corpus=self)
                    .exclude(corpus__creator=self.creator)
                    .values_list("document_id", flat=True)
                )
                if cross_owner_blocked_ids:
                    logger.warning(
                        "Corpus %s public flip skipped %d documents that "
                        "are also members of a private corpus owned by a "
                        "different user.",
                        self.pk,
                        len(cross_owner_blocked_ids),
                    )

                publicize_ids = [d for d in doc_ids if d not in cross_owner_blocked_ids]
                if not publicize_ids:
                    return

                transitioning = list(
                    Document.objects.select_for_update()
                    .filter(id__in=publicize_ids, is_public=False)
                    .values("id", "creator_id", "title")
                )
                Document.objects.filter(id__in=publicize_ids, is_public=False).update(
                    is_public=True
                )

                notifications = [
                    Notification(
                        recipient_id=row["creator_id"],
                        notification_type=(NotificationTypeChoices.DOCUMENT_PUBLICIZED),
                        actor=self.creator,
                        data={
                            "document_id": row["id"],
                            "document_title": row["title"],
                            "corpus_id": self.pk,
                            "corpus_title": self.title,
                        },
                    )
                    for row in transitioning
                    if row["creator_id"] and row["creator_id"] != self.creator_id
                ]
                if notifications:
                    # Cap each INSERT batch so a corpus with thousands of
                    # cross-owner documents does not blow up a single SQL
                    # statement.
                    Notification.objects.bulk_create(
                        notifications,
                        batch_size=NOTIFICATION_BULK_CREATE_BATCH_SIZE,
                    )
        else:
            # Corpus became private → revoke public only for documents
            # NOT in any other public corpus
            in_other_public = set(
                DocumentPath.objects.filter(
                    document_id__in=doc_ids,
                    corpus__is_public=True,
                    is_current=True,
                    is_deleted=False,
                )
                .exclude(corpus=self)
                .values_list("document_id", flat=True)
            )
            revoke_ids = [d for d in doc_ids if d not in in_other_public]
            if revoke_ids:
                Document.objects.filter(id__in=revoke_ids, is_public=True).update(
                    is_public=False
                )

    def has_documents(self) -> bool:
        """Check whether this corpus has any active documents (via DocumentPath)."""
        from opencontractserver.documents.models import DocumentPath

        return DocumentPath.objects.filter(
            corpus=self, is_current=True, is_deleted=False
        ).exists()

    def user_can_moderate(self, user: UserModel | AnonymousUser | None) -> bool:
        """
        Check whether ``user`` may view/act on moderation surfaces for this corpus.

        Canonical replacement for the inline
        ``user.is_superuser or corpus.creator == user or
        corpus.moderators.filter(user=user).exists()`` pattern in moderation
        resolvers (see ``config/graphql/conversation_queries.py``).

        Returns ``True`` iff:
            * ``user`` is a superuser, OR
            * ``user`` is the corpus creator, OR
            * ``user`` is a designated moderator (any row in
              :class:`~opencontractserver.conversations.models.CorpusModerator`,
              regardless of the ``permissions`` list).

        Anonymous / unauthenticated / ``None`` users always get ``False``.

        NOTE: This is intentionally more permissive than
        :meth:`Conversation.can_moderate`, which additionally requires the
        ``CorpusModerator.permissions`` list to be non-empty. Reconciling
        the two is a behavior change tracked separately from the
        consolidation work in #1450.
        """
        if user is None:
            return False
        if not getattr(user, "is_authenticated", False):
            return False
        if user.is_superuser:
            return True
        if self.creator_id == user.pk:
            return True
        return self.moderators.filter(user=user).exists()

    def clean(self) -> None:
        """Validate the model before saving.

        NOTE: Django's save() does NOT call clean()/full_clean(). This method
        runs in the admin, management commands, and explicit full_clean() calls
        but NOT during API mutations. The serializer (CorpusSerializer.validate)
        is the primary enforcement layer for the GraphQL API path.
        """
        super().clean()

        # Validate license against the allowlist.
        valid_license_values = {choice[0] for choice in LICENSE_CHOICES}
        if self.license and self.license not in valid_license_values:
            raise ValidationError({"license": "Invalid license value."})

        # CUSTOM license requires a license_link URL.
        if self.license == CUSTOM and not self.license_link:
            raise ValidationError(
                {"license_link": "A URL is required when using a custom license."}
            )
        # Clear stale license_link when license is not CUSTOM.
        if self.license != CUSTOM and self.license_link:
            self.license_link = ""

        # Validate post_processors is a list
        if not isinstance(self.post_processors, list):
            raise ValidationError({"post_processors": "Must be a list of Python paths"})

        # Validate each post-processor path
        for processor in self.post_processors:
            if not isinstance(processor, str):
                raise ValidationError(
                    {"post_processors": "Each processor must be a string"}
                )
            if not processor.count(".") >= 1:
                raise ValidationError(
                    {"post_processors": f"Invalid Python path: {processor}"}
                )

    def embed_text(self, text: str) -> tuple[str | None, list[float] | None]:
        """
        Use a unified embeddings function from utils to create embeddings for the text.

        Args:
            text (str): The text to embed

        Returns:
            A tuple of (embedder path, embeddings list), or (None, None) on failure.
        """
        return generate_embeddings_from_text(text, corpus_id=self.pk)

    # --------------------------------------------------------------------- #
    # Personal Corpus Management                                            #
    # --------------------------------------------------------------------- #

    @staticmethod
    def _ensure_corpus_permissions_exist() -> None:
        """
        Ensure that Permission rows for the Corpus model exist in the DB.

        During fresh migrations the User ``post_save`` signal fires before
        Django's ``post_migrate`` signal creates Permission objects. Calling
        ``django.contrib.auth.management.create_permissions`` for the
        ``corpuses`` app config is idempotent and cheap (a few SELECT
        queries when permissions already exist).
        """
        from django.apps import apps
        from django.contrib.auth.management import create_permissions

        app_config = apps.get_app_config("corpuses")
        create_permissions(app_config, verbosity=0)

    @classmethod
    def get_or_create_personal_corpus(cls, user: AbstractBaseUser) -> Corpus:
        """
        Get or create the user's personal "My Documents" corpus.

        Each user has exactly one personal corpus (enforced by UniqueConstraint).
        This method is idempotent - calling it multiple times returns the same corpus.

        Args:
            user: The User instance to get/create personal corpus for

        Returns:
            Corpus: The user's personal corpus

        Raises:
            IntegrityError: If concurrent creation attempts occur (handled by get_or_create)
        """
        from opencontractserver.types.enums import PermissionTypes
        from opencontractserver.utils.permissioning import (
            set_permissions_for_obj_to_user,
        )

        with transaction.atomic():
            corpus, created = cls.objects.get_or_create(
                creator=user,
                is_personal=True,
                defaults={
                    "title": PERSONAL_CORPUS_TITLE,
                    "description": PERSONAL_CORPUS_DESCRIPTION,
                    "is_public": False,
                },
            )

            if created:
                logger.info(f"Created personal corpus {corpus.pk} for user {user.pk}")
                # Ensure permission objects exist in the database before
                # assigning them.  During fresh migrations the User post_save
                # signal fires before Django's post_migrate signal has had a
                # chance to create Permission rows, causing
                # "Permission matching query does not exist" errors.
                cls._ensure_corpus_permissions_exist()
                # Grant full permissions to the user
                set_permissions_for_obj_to_user(user, corpus, [PermissionTypes.ALL])  # type: ignore[arg-type]
            elif not corpus.slug:
                # Backfill slug for corpuses created before slug auto-generation
                # (e.g. by migration 0038 which used historical models).
                # Use QuerySet.update() to avoid firing Django signals.
                scope = cls.objects.filter(creator_id=user.pk).exclude(pk=corpus.pk)
                new_slug = generate_unique_slug(
                    base_value=corpus.title or "corpus",
                    scope_qs=scope,
                    slug_field="slug",
                    max_length=128,
                    fallback_prefix="corpus",
                )
                now = timezone.now()
                cls.objects.filter(pk=corpus.pk).update(slug=new_slug, modified=now)
                # Update in-memory object so callers see the new slug
                corpus.slug = new_slug
                corpus.modified = now

        return corpus

    # --------------------------------------------------------------------- #
    # Document Management - Issue #654                                     #
    # --------------------------------------------------------------------- #

    def add_document(
        self,
        document: Document | None = None,
        path: str | None = None,
        user: AbstractBaseUser | None = None,
        folder: CorpusFolder | None = None,
        **doc_kwargs: Any,
    ) -> tuple[Document, str, DocumentPath]:
        """
        Add a document to this corpus, creating a corpus-isolated copy.

        This implements Phase 2 corpus isolation. When adding a document to a corpus,
        a NEW corpus-isolated document is created with:
        - Its own version_tree_id (independent version tree)
        - source_document pointing to original (provenance tracking)
        - DocumentPath linking to this corpus

        This ensures no cross-corpus version tree conflicts.

        Args:
            document: The source Document to copy into corpus (required)
            path: The filesystem path within the corpus (auto-generated if not provided)
            user: The user performing the operation (required)
            folder: Optional CorpusFolder to place the document in
            **doc_kwargs: Override properties for the corpus copy

        Returns:
            Tuple of (document, status, document_path) where:
            - document: The NEW corpus-isolated document (NOT the original)
            - status: 'added' (always - no content-based deduplication)
            - document_path: The DocumentPath record created

        Note: No content-based deduplication is performed. Each call creates
        a new corpus-isolated document regardless of content hash.

        Raises:
            ValueError: If user or document is not provided
        """
        if not user:
            raise ValueError("User is required for document operations (audit trail)")

        if not document:
            raise ValueError(
                "Document is required. For content-based imports, use import_content()"
            )

        from opencontractserver.documents.models import Document, DocumentPath

        # Generate path if not provided
        if not path:
            if document.title:
                safe_title = "".join(
                    c if c.isalnum() or c in "-_." else "_"
                    for c in document.title[:MAX_FILENAME_LENGTH]
                )
                path = f"{DEFAULT_DOCUMENT_PATH_PREFIX}/{safe_title or f'doc_{document.pk}'}"
            else:
                path = f"{DEFAULT_DOCUMENT_PATH_PREFIX}/doc_{document.pk}"

        # Extract path-level lineage kwargs before they hit Document.objects.create()
        path_kwargs = {}
        for key in ("ingestion_source", "external_id", "ingestion_metadata"):
            if key in doc_kwargs:
                path_kwargs[key] = doc_kwargs.pop(key)

        with transaction.atomic():
            # Always create corpus-isolated copy (no content-based deduplication)
            # Each add_document() call creates a new document regardless of content hash
            tree_id = uuid.uuid4()
            corpus_copy = Document.objects.create(
                title=doc_kwargs.get("title", document.title),
                description=doc_kwargs.get("description", document.description),
                file_type=doc_kwargs.get("file_type", document.file_type),
                pdf_file=document.pdf_file,  # Share file blob (Rule I3)
                pdf_file_hash=document.pdf_file_hash,
                # Share parsing artifacts (file blobs, not duplicated)
                pawls_parse_file=document.pawls_parse_file,
                txt_extract_file=document.txt_extract_file,
                icon=document.icon,
                md_summary_file=document.md_summary_file,
                page_count=document.page_count,
                custom_meta=document.custom_meta,  # Inherit custom metadata
                is_public=self.is_public
                or document.is_public,  # Public corpus → public doc
                version_tree_id=tree_id,  # NEW isolated version tree
                is_current=True,
                parent=None,  # Root of NEW content tree
                source_document=document,  # Provenance tracking (Rule I2)
                # Reuse structural_annotation_set instead of duplicating
                # This avoids duplicating annotations/embeddings - embeddings are
                # added incrementally based on the corpus's preferred_embedder
                structural_annotation_set=(
                    doc_kwargs.get("structural_annotation_set")
                    or document.structural_annotation_set
                ),
                creator=user,  # type: ignore[misc]
                # CRITICAL: Set processing_started to prevent ingest signal from firing
                # Corpus copies share parsing artifacts - they don't need re-parsing
                processing_started=timezone.now(),
                backend_lock=False,  # Already processed, not locked
                **{
                    k: v
                    for k, v in doc_kwargs.items()
                    if k
                    not in [
                        "title",
                        "description",
                        "file_type",
                        "is_public",
                        "structural_annotation_set",
                    ]
                },
            )

            logger.info(
                f"Created corpus-isolated copy {corpus_copy.pk} from doc {document.pk} "
                f"in corpus {self.pk} (structural_set={corpus_copy.structural_annotation_set_id})"
            )

            # Queue task to ensure embeddings exist for this corpus's embedder
            # This handles the case where the structural set was created with a different
            # embedder than this corpus uses
            if corpus_copy.structural_annotation_set:
                from opencontractserver.tasks.corpus_tasks import (
                    ensure_embeddings_for_corpus,
                )

                ss_id = corpus_copy.structural_annotation_set_id
                c_id = self.pk
                # Use default args to capture values at lambda creation (not by reference)
                transaction.on_commit(
                    lambda ss=ss_id, c=c_id: ensure_embeddings_for_corpus.delay(  # type: ignore[misc]
                        ss, c
                    )
                )

            # Check if path is occupied — use select_for_update to prevent
            # TOCTOU race conditions under concurrent requests.
            occupied_path = (
                DocumentPath.objects.select_for_update()
                .filter(corpus=self, path=path, is_current=True, is_deleted=False)
                .first()
            )

            if occupied_path:
                # Path exists with different document - mark as not current
                occupied_path.is_current = False
                occupied_path.save(update_fields=["is_current"])
                parent = occupied_path
                version_number = occupied_path.version_number + 1
                logger.info(
                    f"Replacing doc {occupied_path.document_id} with {corpus_copy.pk} "
                    f"at {path} in corpus {self.pk}"
                )
            else:
                parent = None
                version_number = 1

            # Create DocumentPath linking corpus-isolated document
            new_path = DocumentPath.objects.create(
                document=corpus_copy,
                corpus=self,
                folder=folder,
                path=path,
                version_number=version_number,
                parent=parent,
                is_current=True,
                is_deleted=False,
                creator=user,  # type: ignore[misc]
                **path_kwargs,
            )

            logger.info(
                f"Added corpus-isolated doc {corpus_copy.pk} to corpus {self.pk} at {path}"
            )

            # Trigger corpus actions if document is ready (not still processing)
            # This handles the case where an already-processed document is added.
            # If backend_lock=True, the document is still processing and actions
            # will be triggered by set_doc_lock_state in doc_tasks.py when complete.
            if not corpus_copy.backend_lock:
                from opencontractserver.tasks.corpus_tasks import process_corpus_action

                logger.info(
                    f"[add_document] Doc {corpus_copy.pk} is ready, "
                    f"triggering corpus actions for corpus {self.pk}"
                )
                transaction.on_commit(
                    lambda: process_corpus_action.delay(
                        corpus_id=self.pk,
                        document_ids=[corpus_copy.pk],
                        user_id=user.pk,
                        trigger=CorpusActionTrigger.ADD_DOCUMENT,
                    )
                )

            return corpus_copy, "added", new_path

    # File types that go through the parsing pipeline
    PARSEABLE_MIMETYPES = {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }

    def import_content(
        self,
        content: bytes,
        user: AbstractBaseUser,
        path: str | None = None,
        folder: CorpusFolder | None = None,
        filename: str | None = None,
        file_type: str | None = None,
        **doc_kwargs: Any,
    ) -> tuple[Document, str, DocumentPath]:
        """
        Import content into this corpus with automatic file type handling.

        All file types now use the unified import_document() pipeline which provides:
        - Full versioning support (uploading to same path creates new version)
        - Consistent storage (text files → txt_extract_file, binary → pdf_file)
        - Path-based version tracking for all document types

        Args:
            content: File content bytes (required)
            user: The user performing the operation (required)
            path: The filesystem path within the corpus (auto-generated if not provided)
            folder: Optional CorpusFolder to place the document in
            filename: Original filename (used for path generation if path not provided)
            file_type: MIME type of the content (determines storage field)
            **doc_kwargs: Additional arguments for document creation (title, description, etc.)

        Returns:
            Tuple of (document, status, document_path) where status is one of:
            - 'created': New document at new path
            - 'updated': New version at existing path

        Raises:
            ValueError: If user or content is not provided
        """
        if not user:
            raise ValueError("User is required for document operations (audit trail)")

        if content is None:
            raise ValueError("Content is required for import_content()")

        from opencontractserver.documents.versioning import import_document

        # Determine file type - check doc_kwargs for backwards compatibility
        effective_file_type = file_type or doc_kwargs.get("file_type")

        # Generate path if not provided
        if not path:
            if filename:
                # Use filename to generate path
                safe_filename = "".join(
                    c if c.isalnum() or c in "-_." else "_"
                    for c in filename[:MAX_FILENAME_LENGTH]
                )
                path = f"{DEFAULT_DOCUMENT_PATH_PREFIX}/{safe_filename}"
            else:
                path = f"{DEFAULT_DOCUMENT_PATH_PREFIX}/doc_{uuid.uuid4().hex[:8]}"

        # All file types now go through the unified versioning pipeline
        # Text files are stored in txt_extract_file, binary files in pdf_file
        doc, status, doc_path = import_document(
            corpus=self,
            path=path,
            content=content,
            user=user,  # type: ignore[arg-type]
            folder=folder,
            file_type=effective_file_type,
            **doc_kwargs,
        )

        return doc, status, doc_path

    def remove_document(
        self,
        document: Document | None = None,
        path: str | None = None,
        user: AbstractBaseUser | None = None,
    ) -> list[DocumentPath]:
        """
        Remove a document from this corpus (soft delete).

        This is the recommended way to remove documents, replacing corpus.documents.remove().
        It creates a soft-delete DocumentPath record maintaining history.

        Args:
            document: The Document to remove (optional if path provided)
            path: The filesystem path to remove (optional if document provided)
            user: The user performing the operation (required)

        Returns:
            List of DocumentPath records that were soft-deleted

        Raises:
            ValueError: If neither document nor path provided, or if user not provided
            RuntimeError: If operation fails
        """
        if not user:
            raise ValueError("User is required for document operations (audit trail)")

        if not document and not path:
            raise ValueError("Either document or path must be provided")

        from opencontractserver.documents.models import DocumentPath

        deleted_paths = []

        with transaction.atomic():
            if path:
                # Delete specific path
                active_path = DocumentPath.objects.filter(
                    corpus=self, path=path, is_current=True, is_deleted=False
                ).first()

                if active_path:
                    # Mark current as not current
                    active_path.is_current = False
                    active_path.save(update_fields=["is_current"])

                    # Create soft-deleted record
                    deleted_path = DocumentPath.objects.create(
                        document=active_path.document,
                        corpus=self,
                        folder=active_path.folder,
                        path=active_path.path,
                        version_number=active_path.version_number,
                        parent=active_path,
                        is_deleted=True,
                        is_current=True,
                        creator=user,  # type: ignore[misc]
                    )
                    deleted_paths.append(deleted_path)
                    logger.info(
                        f"Removed document at path {path} from corpus {self.pk}"
                    )
                else:
                    logger.warning(
                        f"Path {path} not found in corpus {self.pk} for deletion"
                    )
            else:
                # Delete all paths for this document. The early
                # ``if not document and not path`` guard above ensures
                # ``document`` is set whenever ``path`` is falsy.
                assert document is not None
                active_paths = DocumentPath.objects.filter(
                    corpus=self, document=document, is_current=True, is_deleted=False
                )

                for path_record in active_paths:
                    # Mark current as not current
                    path_record.is_current = False
                    path_record.save(update_fields=["is_current"])

                    # Create soft-deleted record
                    deleted_path = DocumentPath.objects.create(
                        document=path_record.document,
                        corpus=self,
                        folder=path_record.folder,
                        path=path_record.path,
                        version_number=path_record.version_number,
                        parent=path_record,
                        is_deleted=True,
                        is_current=True,
                        creator=user,  # type: ignore[misc]
                    )
                    deleted_paths.append(deleted_path)
                    logger.info(
                        f"Removed document {document.pk} at path "
                        f"{path_record.path} from corpus {self.pk}"
                    )

        # After removal, revoke is_public for documents no longer in any
        # public corpus.  This mirrors the revocation logic in
        # _propagate_public_status_to_documents and ensures documents
        # don't remain publicly visible after removal.
        if deleted_paths and self.is_public:
            removed_doc_ids = list({dp.document_id for dp in deleted_paths})
            still_in_public = set(
                DocumentPath.objects.filter(
                    document_id__in=removed_doc_ids,
                    corpus__is_public=True,
                    is_current=True,
                    is_deleted=False,
                ).values_list("document_id", flat=True)
            )
            revoke_ids = [d for d in removed_doc_ids if d not in still_in_public]
            if revoke_ids:
                from opencontractserver.documents.models import Document

                Document.objects.filter(id__in=revoke_ids, is_public=True).update(
                    is_public=False
                )

        return deleted_paths

    def _get_active_documents(self, include_caml: bool = False) -> QuerySet[Document]:
        """
        INTERNAL: corpus documents with no permission check.

        **API note on the underscore prefix.** Despite the leading
        underscore, this method *is* the blessed cross-module API for
        non-user-context callers — Celery tasks, signal handlers, badge
        / corpus / analyzer task batches, and the LLM-tool helpers that
        run without a request. The underscore is load-bearing on the
        Manager/QuerySet contract: it signals "do not call from a
        user-context resolver / view / mutation"; ``get_documents()``
        is the deprecated public alias that emits a warning. Renaming
        away from the underscore would require simultaneously renaming
        the public alias and updating ~10 call sites; the current shape
        is the trade-off between Python convention and reviewer
        clarity. Cross-module callers (`badge_tasks`, `corpus_tasks`,
        `sharing`, `analyzer`, the LLM-tool helpers, etc.) are
        intentional and approved — see the deprecation notice on
        ``get_documents()`` below.

        Returns all documents with an active, non-deleted ``DocumentPath`` in
        this corpus.  Reserved for Celery tasks, signal handlers, and the
        corpus-objs service itself, where the caller has already verified
        permission (or no user is involved).

        User-context code MUST go through
        ``CorpusObjsService.get_corpus_documents(user, corpus)`` so that
        corpus READ is enforced uniformly.

        Args:
            include_caml: If True, include CAML/markdown documents in
                results.  Defaults to False so extractors, analyzers, and
                other internal processes skip CAML articles automatically.

        Returns:
            QuerySet of Document objects with active paths in this corpus.
        """
        from opencontractserver.documents.models import Document, DocumentPath

        active_doc_ids = DocumentPath.objects.filter(
            corpus=self, is_current=True, is_deleted=False
        ).values_list("document_id", flat=True)

        qs = Document.objects.filter(id__in=active_doc_ids).distinct()
        if not include_caml:
            qs = qs.exclude(file_type=MARKDOWN_MIME_TYPE)
        return qs

    def get_documents(self, include_caml: bool = False) -> QuerySet[Document]:
        """
        DEPRECATED user-facing wrapper around ``_get_active_documents``.

        Use ``CorpusObjsService.get_corpus_documents(user, corpus)`` in any
        user-context code (request handlers, MCP tools, LLM tools, GraphQL
        resolvers).  For internal/task code without a user, call
        ``corpus._get_active_documents()`` directly to opt out of the
        deprecation warning.

        Args:
            include_caml: If True, include CAML/markdown documents in
                results.

        Returns:
            QuerySet of Document objects with active paths in this corpus.
        """
        import warnings

        warnings.warn(
            "Corpus.get_documents() is deprecated. Use "
            "CorpusObjsService.get_corpus_documents(user, corpus) in any "
            "user-context code (request handlers, MCP tools, LLM tools, "
            "GraphQL resolvers). For internal use (Celery tasks, signal "
            "handlers), call corpus._get_active_documents() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self._get_active_documents(include_caml=include_caml)

    def document_count(self) -> int:
        """
        Get count of documents with active paths in this corpus.
        Excludes CAML articles (text/markdown) so the count reflects
        only user-uploaded documents.

        Returns:
            Integer count of active documents
        """
        from opencontractserver.documents.models import DocumentPath

        return (
            DocumentPath.objects.filter(corpus=self, is_current=True, is_deleted=False)
            .exclude(document__file_type=MARKDOWN_MIME_TYPE)
            .values("document_id")
            .distinct()
            .count()
        )

    # --------------------------------------------------------------------- #
    # Label helper                                                         #
    # --------------------------------------------------------------------- #

    def ensure_label_and_labelset(
        self,
        *,
        label_text: str,
        creator_id: int,
        label_type: str | None = None,
        color: str = "#05313d",
        description: str = "",
        icon: str = "tags",
    ) -> AnnotationLabel:
        """Return an AnnotationLabel for *label_text*, creating prerequisites.

        Ensures the corpus has a label-set and that a label with the given text
        & type exists within it. Returns that label instance.
        """

        from django.db import transaction

        from opencontractserver.annotations.models import (
            TOKEN_LABEL,
            AnnotationLabel,
            LabelSet,
        )

        if label_type is None:
            label_type = TOKEN_LABEL

        with transaction.atomic():
            # Create label-set lazily.
            if self.label_set is None:
                self.label_set = LabelSet.objects.create(
                    title=f"Corpus {self.pk} Set",
                    description="Auto-created label set",
                    creator_id=creator_id,
                )
                self.save(update_fields=["label_set", "modified"])

            # Fetch/create label inside that set.
            label = self.label_set.annotation_labels.filter(
                text=label_text, label_type=label_type
            ).first()
            if label is None:
                label = AnnotationLabel.objects.create(
                    text=label_text,
                    label_type=label_type,
                    color=color,
                    description=description,
                    icon=icon,
                    creator_id=creator_id,
                )
                self.label_set.annotation_labels.add(label)

        return label


# Model for Django Guardian permissions... trying to improve performance...
class CorpusUserObjectPermission(UserObjectPermissionBase):
    content_object = django.db.models.ForeignKey(
        "Corpus", on_delete=django.db.models.CASCADE
    )
    # enabled = False


# Model for Django Guardian permissions... trying to improve performance...
class CorpusGroupObjectPermission(GroupObjectPermissionBase):
    content_object = django.db.models.ForeignKey(
        "Corpus", on_delete=django.db.models.CASCADE
    )
    # enabled = False


class CorpusActionTrigger(django.db.models.TextChoices):
    ADD_DOCUMENT = "add_document", "Add Document"
    EDIT_DOCUMENT = "edit_document", "Edit Document"
    NEW_THREAD = "new_thread", "New Thread Created"
    NEW_MESSAGE = "new_message", "New Message Posted"


class CorpusAction(BaseOCModel):
    name = django.db.models.CharField(
        max_length=256, blank=False, null=False, default="Corpus Action"
    )
    corpus = django.db.models.ForeignKey(
        "Corpus", on_delete=django.db.models.CASCADE, related_name="actions"
    )
    fieldset = django.db.models.ForeignKey(
        "extracts.Fieldset", on_delete=django.db.models.SET_NULL, null=True, blank=True
    )
    analyzer = django.db.models.ForeignKey(
        "analyzer.Analyzer", on_delete=django.db.models.SET_NULL, null=True, blank=True
    )
    # Agent-based action fields
    agent_config = django.db.models.ForeignKey(
        "agents.AgentConfiguration",
        on_delete=django.db.models.SET_NULL,
        null=True,
        blank=True,
        related_name="corpus_actions",
        help_text="Optional agent configuration for persona/tool defaults. "
        "Not required for agent actions — task_instructions alone is sufficient.",
    )
    task_instructions = django.db.models.TextField(
        blank=True,
        default="",
        help_text="What the agent should do (e.g., 'Read this document and update "
        "its description with a one-paragraph summary'). This is the single "
        "required field for agent-based actions.",
    )
    pre_authorized_tools = django.db.models.JSONField(
        default=list,
        blank=True,
        help_text="Tools pre-authorized to run without approval. If empty, uses "
        "agent_config.available_tools or trigger-appropriate defaults.",
    )
    trigger = django.db.models.CharField(
        max_length=256, choices=CorpusActionTrigger.choices
    )
    disabled = django.db.models.BooleanField(null=False, default=False, blank=True)
    run_on_all_corpuses = django.db.models.BooleanField(
        null=False, default=False, blank=True
    )
    source_template = django.db.models.ForeignKey(
        "CorpusActionTemplate",
        on_delete=django.db.models.SET_NULL,
        null=True,
        blank=True,
        related_name="cloned_actions",
        help_text="The template this action was cloned from, if any.",
    )

    class Meta:
        constraints = [
            django.db.models.CheckConstraint(
                condition=(
                    # Fieldset only (no analyzer, no agent)
                    django.db.models.Q(
                        fieldset__isnull=False,
                        analyzer__isnull=True,
                        agent_config__isnull=True,
                    )
                    # Analyzer only (no fieldset, no agent)
                    | django.db.models.Q(
                        fieldset__isnull=True,
                        analyzer__isnull=False,
                        agent_config__isnull=True,
                    )
                    # Agent with config (no fieldset, no analyzer).
                    # Requires non-empty task_instructions to match clean().
                    | (
                        django.db.models.Q(
                            fieldset__isnull=True,
                            analyzer__isnull=True,
                            agent_config__isnull=False,
                        )
                        & ~django.db.models.Q(task_instructions="")
                    )
                    # Lightweight agent: task_instructions only
                    | (
                        django.db.models.Q(
                            fieldset__isnull=True,
                            analyzer__isnull=True,
                            agent_config__isnull=True,
                        )
                        & ~django.db.models.Q(task_instructions="")
                    )
                ),
                name="valid_action_type_configuration",
            ),
            django.db.models.UniqueConstraint(
                fields=["corpus", "source_template"],
                condition=django.db.models.Q(source_template__isnull=False),
                name="unique_template_per_corpus",
            ),
        ]
        permissions = (
            ("permission_corpusaction", "permission corpusaction"),
            ("publish_corpusaction", "publish corpusaction"),
            ("create_corpusaction", "create corpusaction"),
            ("read_corpusaction", "read corpusaction"),
            ("update_corpusaction", "update corpusaction"),
            ("remove_corpusaction", "delete corpusaction"),
            ("comment_corpusaction", "comment corpusaction"),
        )

    @property
    def is_agent_action(self) -> bool:
        """Whether this action is an agent-based action (with or without config).

        An action is agent-based if it has an agent_config, or if it has
        task_instructions without a fieldset or analyzer (lightweight agent).

        Keep in sync with: clean() validation and Meta.constraints
        (valid_action_type_configuration).
        """
        if self.agent_config_id:
            return True
        if self.task_instructions and not self.fieldset_id and not self.analyzer_id:
            return True
        return False

    def clean(self) -> None:
        has_fieldset = self.fieldset is not None
        has_analyzer = self.analyzer is not None
        has_agent_config = self.agent_config is not None
        has_task_instructions = bool(self.task_instructions)

        fk_count = sum([has_fieldset, has_analyzer, has_agent_config])

        # Fieldset/analyzer/agent_config are mutually exclusive
        if fk_count > 1:
            raise ValidationError(
                "Only one of fieldset, analyzer, or agent_config can be set."
            )

        # Must have at least one action type
        if fk_count == 0 and not has_task_instructions:
            raise ValidationError(
                "One of fieldset, analyzer, agent_config, or "
                "task_instructions must be set."
            )

        # task_instructions must not be set on fieldset/analyzer actions
        if (has_fieldset or has_analyzer) and has_task_instructions:
            raise ValidationError(
                "task_instructions cannot be set on fieldset or analyzer actions."
            )

        # Agent actions (with config) require task_instructions.
        # Keep in sync with: is_agent_action property and Meta.constraints
        # (valid_action_type_configuration).
        if has_agent_config and not has_task_instructions:
            raise ValidationError(
                "task_instructions is required for agent-based actions."
            )

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        if self.fieldset:
            action_type = "Fieldset"
        elif self.analyzer:
            action_type = "Analyzer"
        elif self.is_agent_action:
            action_type = "Agent"
        else:
            action_type = "Unknown"
        return f"CorpusAction for {self.corpus} - {action_type} - {self.get_trigger_display()}"


class CorpusActionUserObjectPermission(UserObjectPermissionBase):
    content_object = django.db.models.ForeignKey(
        "CorpusAction", on_delete=django.db.models.CASCADE
    )
    # enabled = False


# Model for Django Guardian permissions... trying to improve performance...
class CorpusActionGroupObjectPermission(GroupObjectPermissionBase):
    content_object = django.db.models.ForeignKey(
        "CorpusAction", on_delete=django.db.models.CASCADE
    )
    # enabled = False


class CorpusActionTemplate(BaseOCModel):
    """Reusable template for agent-based corpus actions.

    Templates define the agent configuration, task instructions, and trigger
    type that a cloned ``CorpusAction`` will use.  Users browse available
    templates via the Action Library UI and add them to individual corpuses
    on demand (no auto-cloning).

    Templates are agent-only — no fieldset or analyzer support.

    Exposed via GraphQL (``CorpusActionTemplateType`` query and
    ``AddTemplateToCorpus`` mutation).  Template records themselves are
    managed through Django admin; users interact with the cloned
    ``CorpusAction`` instances on their corpuses.
    """

    # Override BaseOCModel.creator to use SET_NULL — system-level templates
    # are owned by an arbitrary superuser at migration time and must survive
    # that user being deleted.
    creator = django.db.models.ForeignKey(  # type: ignore[assignment]
        get_user_model(),
        on_delete=django.db.models.SET_NULL,
        null=True,
        blank=True,
        db_index=True,
    )

    name = django.db.models.CharField(max_length=256, unique=True)
    description = django.db.models.TextField(blank=True, default="")

    agent_config = django.db.models.ForeignKey(
        "agents.AgentConfiguration",
        on_delete=django.db.models.SET_NULL,
        null=True,
        blank=True,
        related_name="action_templates",
        help_text="Optional agent configuration for persona/tool defaults.",
    )
    task_instructions = django.db.models.TextField(
        help_text="What the agent should do when this action fires.",
    )
    pre_authorized_tools = django.db.models.JSONField(
        default=list,
        blank=True,
        help_text="Tools pre-authorized to run without user approval.",
    )

    trigger = django.db.models.CharField(
        max_length=256, choices=CorpusActionTrigger.choices
    )

    is_active = django.db.models.BooleanField(
        default=True,
        help_text="Whether this template appears in the Action Library for users to add.",
    )
    disabled_on_clone = django.db.models.BooleanField(
        default=False,
        help_text="If True, cloned actions start disabled (user must opt-in).",
    )
    sort_order = django.db.models.IntegerField(
        default=0,
        help_text="Display ordering in template lists.",
    )

    class Meta:
        ordering = ["sort_order", "name"]
        indexes = [
            django.db.models.Index(
                fields=["sort_order", "name"],
                name="corpuses_actio_sort_or_idx",
            ),
        ]
        constraints = [
            django.db.models.CheckConstraint(
                condition=~django.db.models.Q(task_instructions=""),
                name="nonempty_task_instructions",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if not self.task_instructions:
            raise ValidationError(
                {"task_instructions": "Task instructions cannot be empty."}
            )

    def __str__(self) -> str:
        return f"CorpusActionTemplate: {self.name} ({self.get_trigger_display()})"

    def to_action_kwargs(
        self, corpus: Corpus, creator: AbstractBaseUser | None = None
    ) -> dict[str, Any]:
        """Return kwargs dict for constructing a CorpusAction from this template.

        Note:
            ``task_instructions`` is **copied** into the new ``CorpusAction``.
            Later edits to the template's instructions do *not* propagate to
            existing clones.

            By contrast, ``agent_config`` is a FK reference to the *same*
            ``AgentConfiguration`` that the template uses.  All corpus actions
            cloned from a template therefore share one configuration object.
            If an admin later edits that ``AgentConfiguration``, every cloned
            action is affected.  This is intentional — templates act as a
            single source of truth for agent behaviour.

        Raises:
            ValueError: If neither ``creator`` nor ``corpus.creator`` is set.
        """
        resolved_creator = creator or corpus.creator
        if resolved_creator is None:
            raise ValueError(
                f"Cannot clone template {self.name!r}: no creator provided "
                f"and corpus {corpus.pk} has no creator."
            )
        return dict(
            name=self.name,
            corpus=corpus,
            agent_config=self.agent_config,
            task_instructions=self.task_instructions,
            pre_authorized_tools=list(self.pre_authorized_tools),
            trigger=self.trigger,
            disabled=self.disabled_on_clone,
            creator=resolved_creator,
            source_template=self,
        )

    def clone_to_corpus(
        self, corpus: Corpus, creator: AbstractBaseUser | None = None
    ) -> CorpusAction:
        """Create a CorpusAction from this template for the given corpus.

        Returns the created CorpusAction instance.
        """
        kwargs = self.to_action_kwargs(corpus, creator)
        action = CorpusAction(**kwargs)
        action.save()
        return action


# -------------------- CorpusDescriptionRevision -------------------- #


class CorpusDescriptionRevision(django.db.models.Model):
    """Append-only history for Corpus markdown description."""

    corpus = django.db.models.ForeignKey(
        "corpuses.Corpus",
        on_delete=django.db.models.CASCADE,
        related_name="revisions",
    )

    author = django.db.models.ForeignKey(
        get_user_model(),
        on_delete=django.db.models.SET_NULL,
        null=True,
        related_name="corpus_revisions",
    )

    version = django.db.models.PositiveIntegerField()
    diff = django.db.models.TextField(blank=True)
    snapshot = django.db.models.TextField(null=True, blank=True)
    checksum_base = django.db.models.CharField(max_length=64, blank=True)
    checksum_full = django.db.models.CharField(max_length=64, blank=True)
    created = django.db.models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        unique_together = ("corpus", "version")
        ordering = ("corpus_id", "version")
        indexes = [
            django.db.models.Index(fields=["corpus"]),
            django.db.models.Index(fields=["author"]),
            django.db.models.Index(fields=["created"]),
        ]

    def __str__(self) -> str:
        return (
            f"CorpusDescriptionRevision(corpus_id={self.corpus_id}, v={self.version})"
        )


# --------------------------------------------------------------------------- #
# Corpus Engagement Metrics
# --------------------------------------------------------------------------- #


class CorpusEngagementMetrics(django.db.models.Model):
    """
    Denormalized engagement metrics per corpus for fast dashboard queries.

    This model stores aggregated statistics about corpus participation,
    updated asynchronously via Celery tasks to avoid performance impact
    on user operations.

    Epic: #565 - Corpus Engagement Metrics & Analytics
    """

    corpus = django.db.models.OneToOneField(
        "corpuses.Corpus",
        on_delete=django.db.models.CASCADE,
        related_name="engagement_metrics",
        help_text="The corpus these metrics belong to",
    )

    # Thread counts
    total_threads = django.db.models.IntegerField(
        default=0,
        help_text="Total number of discussion threads in this corpus",
    )
    active_threads = django.db.models.IntegerField(
        default=0,
        help_text="Number of active (not locked/deleted) threads",
    )

    # Message counts
    total_messages = django.db.models.IntegerField(
        default=0,
        help_text="Total number of messages across all threads",
    )
    messages_last_7_days = django.db.models.IntegerField(
        default=0,
        help_text="Number of messages posted in the last 7 days",
    )
    messages_last_30_days = django.db.models.IntegerField(
        default=0,
        help_text="Number of messages posted in the last 30 days",
    )

    # Contributor counts
    unique_contributors = django.db.models.IntegerField(
        default=0,
        help_text="Total number of unique users who have posted messages",
    )
    active_contributors_30_days = django.db.models.IntegerField(
        default=0,
        help_text="Number of users who posted in the last 30 days",
    )

    # Engagement metrics
    total_upvotes = django.db.models.IntegerField(
        default=0,
        help_text="Total upvotes across all messages in this corpus",
    )
    avg_messages_per_thread = django.db.models.FloatField(
        default=0.0,
        help_text="Average number of messages per thread",
    )

    # Metadata
    last_updated = django.db.models.DateTimeField(
        auto_now=True,
        help_text="Timestamp when metrics were last calculated",
    )

    class Meta:
        verbose_name = "Corpus Engagement Metrics"
        verbose_name_plural = "Corpus Engagement Metrics"
        indexes = [
            django.db.models.Index(fields=["corpus", "last_updated"]),
        ]

    def __str__(self) -> str:
        return f"Engagement Metrics for {self.corpus.title}"


# --------------------------------------------------------------------------- #
# Corpus Folder Structure
# --------------------------------------------------------------------------- #


class CorpusFolder(InstanceUserCanMixin, TreeNode):
    """
    Hierarchical folder structure within a corpus for organizing documents.
    Uses TreeNode for efficient tree operations via CTEs.

    Inherits ``InstanceUserCanMixin`` solely to keep the surface signature
    consistent with peer models — the real authorization always delegates
    to the parent corpus (see overridden ``user_can`` below).

    Per-folder guardian rows are not allocated for ``CorpusFolder``;
    permissions are inherited from the parent ``Corpus``. The override on
    ``user_can`` enforces that delegation structurally so callers that
    type ``folder.user_can(user, perm)`` with plausible intent cannot
    silently get a wrong answer from the default folder-row check (which
    would return ``False`` for a shared reader because the folder has no
    guardian rows).
    """

    # Basic fields
    name = django.db.models.CharField(
        max_length=255, help_text="Folder name (not full path)"
    )

    corpus = django.db.models.ForeignKey(
        "Corpus",
        on_delete=django.db.models.CASCADE,
        related_name="folders",
        help_text="Parent corpus this folder belongs to",
    )

    # Metadata
    description = django.db.models.TextField(blank=True, default="")
    color = django.db.models.CharField(
        max_length=7,
        blank=True,
        default="#05313d",
        help_text="Hex color for UI display",
    )
    icon = django.db.models.CharField(
        max_length=50,
        blank=True,
        default="folder",
        help_text="Icon identifier for UI",
    )
    tags = django.db.models.JSONField(
        default=list,
        blank=True,
        help_text="List of tags for categorization",
    )

    # Sharing (inherits from corpus but can be set independently)
    is_public = django.db.models.BooleanField(default=False)

    # Timestamps and ownership
    created = django.db.models.DateTimeField(default=timezone.now)
    modified = django.db.models.DateTimeField(default=timezone.now)
    creator = django.db.models.ForeignKey(
        get_user_model(),
        on_delete=django.db.models.CASCADE,
    )

    # Use permissioned tree queryset
    objects = PermissionedTreeQuerySet.as_manager(with_tree_fields=True)

    class Meta:
        ordering = ("name",)
        indexes = [
            django.db.models.Index(fields=["corpus", "name"]),
            django.db.models.Index(fields=["creator"]),
            django.db.models.Index(fields=["corpus", "parent"]),
        ]
        constraints = [
            # Unique folder names per parent within a corpus
            django.db.models.UniqueConstraint(
                fields=["corpus", "parent", "name"],
                name="unique_folder_name_per_parent",
            ),
        ]
        permissions = (
            ("permission_corpusfolder", "permission corpusfolder"),
            ("publish_corpusfolder", "publish corpusfolder"),
            ("create_corpusfolder", "create corpusfolder"),
            ("read_corpusfolder", "read corpusfolder"),
            ("update_corpusfolder", "update corpusfolder"),
            ("remove_corpusfolder", "delete corpusfolder"),
        )

    def save(self, *args: Any, **kwargs: Any) -> None:
        """On save, update timestamps and validate parent corpus"""
        if not self.pk:
            self.created = timezone.now()
        self.modified = timezone.now()

        # Validate parent belongs to same corpus
        if self.parent and self.parent.corpus_id != self.corpus_id:
            raise ValidationError("Folder parent must belong to the same corpus")

        super().save(*args, **kwargs)

    def clean(self) -> None:
        """Validate the model before saving."""
        super().clean()

        # Validate tags is a list
        if not isinstance(self.tags, list):
            raise ValidationError({"tags": "Must be a list of strings"})

        # Validate each tag is a string
        for tag in self.tags:
            if not isinstance(tag, str):
                raise ValidationError({"tags": "Each tag must be a string"})

    def user_can(
        self,
        user: Any,
        permission: Any,
        *,
        include_group_permissions: bool = True,
        request: Any = None,
    ) -> bool:
        """Authorize against the parent corpus rather than the folder row.

        ``CorpusFolder`` does not maintain its own guardian object-permission
        rows — sharing is inherited from the parent ``Corpus``. Calling the
        default ``InstanceUserCanMixin.user_can`` against a folder would
        check guardian grants on the folder row, which never exist, so a
        shared reader would receive a silent ``False``. Delegate to
        ``self.corpus.user_can(user, perm)`` to keep the answer consistent
        with the rest of the permissioning surface (``DocumentFolderService``
        and every legacy call site already go through the corpus).

        ``request`` is threaded through unchanged so the request-scoped
        ``PermissionQueryOptimizer`` (issue #1640) can cache across
        repeated folder visibility checks in a single request.
        """
        return self.corpus.user_can(
            user,
            permission,
            include_group_permissions=include_group_permissions,
            request=request,
        )

    def get_path(self) -> str:
        """Get full path from root to this folder."""
        ancestors = self.ancestors(include_self=True)
        return "/".join(f.name for f in ancestors)

    def get_descendant_folders(self) -> QuerySet[CorpusFolder]:
        """Get all descendant folders efficiently using CTE."""
        return self.descendants(include_self=True)

    def get_document_count(self) -> int:
        """
        Get count of documents directly in this folder (not including subfolders).

        Uses DocumentPath with proper filtering for is_current=True, is_deleted=False.
        """
        from opencontractserver.documents.models import DocumentPath

        return DocumentPath.objects.filter(
            folder=self, is_current=True, is_deleted=False
        ).count()

    def get_descendant_document_count(self) -> int:
        """
        Get count of documents in this folder and all subfolders.

        Uses DocumentPath with proper filtering for is_current=True, is_deleted=False.
        """
        from opencontractserver.documents.models import DocumentPath

        descendant_folders = self.get_descendant_folders()

        return DocumentPath.objects.filter(
            folder__in=descendant_folders, is_current=True, is_deleted=False
        ).count()

    def __str__(self) -> str:
        return f"{self.corpus.title}/{self.get_path()}"


class CorpusFolderUserObjectPermission(UserObjectPermissionBase):
    """Guardian permission model for per-user folder permissions."""

    content_object = django.db.models.ForeignKey(
        "CorpusFolder", on_delete=django.db.models.CASCADE
    )


class CorpusFolderGroupObjectPermission(GroupObjectPermissionBase):
    """Guardian permission model for per-group folder permissions."""

    content_object = django.db.models.ForeignKey(
        "CorpusFolder", on_delete=django.db.models.CASCADE
    )


# --------------------------------------------------------------------------- #
# Corpus Action Execution Trail
# --------------------------------------------------------------------------- #


class CorpusActionExecution(BaseOCModel):
    """
    Tracks individual executions of corpus actions.

    One record per (corpus_action, document, run) combination.
    Provides unified querying across all action types (fieldset, analyzer, agent).

    Design Notes:
    - Uses JSONField for affected_objects instead of GenericForeignKey for query performance
    - Append-mostly pattern: only status transitions after creation
    - Denormalized corpus_id for fast corpus-level queries without joins
    """

    class Status(django.db.models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        SKIPPED = "skipped", "Skipped"  # Idempotent skip (already processed)

    class ActionType(django.db.models.TextChoices):
        FIELDSET = "fieldset", "Fieldset Extract"
        ANALYZER = "analyzer", "Analyzer"
        AGENT = "agent", "Agent"

    # Core relationships
    corpus_action = django.db.models.ForeignKey(
        "CorpusAction",
        on_delete=django.db.models.CASCADE,
        related_name="executions",
        help_text="The corpus action configuration that was executed",
    )
    document = django.db.models.ForeignKey(
        "documents.Document",
        on_delete=django.db.models.CASCADE,
        null=True,
        blank=True,
        related_name="corpus_action_executions",
        help_text="The document this action was executed on (null for thread-based actions)",
    )

    # Thread/message context (for NEW_THREAD and NEW_MESSAGE triggers)
    conversation = django.db.models.ForeignKey(
        "conversations.Conversation",
        on_delete=django.db.models.CASCADE,
        null=True,
        blank=True,
        related_name="corpus_action_executions",
        help_text="The thread that triggered this execution (for thread-based actions)",
    )
    message = django.db.models.ForeignKey(
        "conversations.ChatMessage",
        on_delete=django.db.models.CASCADE,
        null=True,
        blank=True,
        related_name="corpus_action_executions",
        help_text="The message that triggered this execution (for NEW_MESSAGE trigger)",
    )

    # Denormalized for query performance (avoids join through corpus_action)
    corpus = django.db.models.ForeignKey(
        "Corpus",
        on_delete=django.db.models.CASCADE,
        related_name="action_executions",
        help_text="Denormalized corpus reference for fast queries",
        db_index=True,
    )

    # Denormalized action type for filtering without join
    action_type = django.db.models.CharField(
        max_length=20,
        choices=ActionType.choices,
        db_index=True,
        help_text="Type of action (fieldset/analyzer/agent)",
    )

    # Execution lifecycle
    status = django.db.models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.QUEUED,
        db_index=True,
    )
    queued_at = django.db.models.DateTimeField(
        db_index=True,
        help_text="When the execution was queued (set explicitly for bulk_create)",
    )
    started_at = django.db.models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="When execution actually started",
    )
    completed_at = django.db.models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="When execution completed (success or failure)",
    )

    # Trigger context
    trigger = django.db.models.CharField(
        max_length=128,
        choices=CorpusActionTrigger.choices,
        help_text="What triggered this execution",
    )

    # Result tracking - uses JSON for flexibility and query performance
    affected_objects = django.db.models.JSONField(
        default=list,
        blank=True,
        help_text="""
        List of objects created or modified by this execution.
        Format: [
            {"type": "extract", "id": 123},
            {"type": "datacell", "id": 456, "column_name": "parties"},
            {"type": "analysis", "id": 789},
            {"type": "annotation", "id": 101, "label": "indemnification"},
            {"type": "document_summary", "revision_id": 202},
            {"type": "document_meta", "field": "description", "old": "...", "new": "..."},
        ]
        """,
    )

    # For agent actions, link to detailed result
    agent_result = django.db.models.ForeignKey(
        "agents.AgentActionResult",
        on_delete=django.db.models.SET_NULL,
        null=True,
        blank=True,
        related_name="execution_record",
        help_text="Detailed agent result (for agent actions only)",
    )

    # For fieldset actions, link to extract
    extract = django.db.models.ForeignKey(
        "extracts.Extract",
        on_delete=django.db.models.SET_NULL,
        null=True,
        blank=True,
        related_name="execution_records",
        help_text="Extract created (for fieldset actions only)",
    )

    # For analyzer actions, link to analysis
    analysis = django.db.models.ForeignKey(
        "analyzer.Analysis",
        on_delete=django.db.models.SET_NULL,
        null=True,
        blank=True,
        related_name="execution_records",
        help_text="Analysis created (for analyzer actions only)",
    )

    # Error tracking
    error_message = django.db.models.TextField(
        blank=True,
        default="",
        help_text="Error message if status is FAILED",
    )
    error_traceback = django.db.models.TextField(
        blank=True,
        default="",
        help_text="Full traceback for debugging (truncated to 10KB)",
    )

    # Execution metadata (model, tokens, retries, etc.)
    execution_metadata = django.db.models.JSONField(
        default=dict,
        blank=True,
        help_text="""
        Additional execution context:
        {
            "model": "gpt-4",
            "tokens_used": 1500,
            "retry_count": 0,
            "celery_task_id": "abc-123",
            "worker_id": "worker-1",
        }
        """,
    )

    # Custom manager for optimized queries (django-stubs flags re-declaring
    # ``objects`` as overriding a class variable; intentional manager override).
    objects = CorpusActionExecutionManager()  # type: ignore[misc]

    class Meta:
        ordering = ["-queued_at"]
        permissions = (
            ("permission_corpusactionexecution", "permission corpusactionexecution"),
            ("publish_corpusactionexecution", "publish corpusactionexecution"),
            ("create_corpusactionexecution", "create corpusactionexecution"),
            ("read_corpusactionexecution", "read corpusactionexecution"),
            ("update_corpusactionexecution", "update corpusactionexecution"),
            ("remove_corpusactionexecution", "delete corpusactionexecution"),
        )
        indexes = [
            # Primary query: "Get all executions for a corpus, newest first"
            # Used by: corpus action trail UI, corpus dashboard
            django.db.models.Index(
                fields=["corpus", "-queued_at"],
                name="corpusactionexec_corpus_queue",
            ),
            # Query: "Get executions for a specific action, newest first"
            # Used by: action detail view, monitoring
            django.db.models.Index(
                fields=["corpus_action", "-queued_at"],
                name="corpusactionexec_action_queue",
            ),
            # Query: "Get executions for a document across all actions"
            # Used by: document history view
            django.db.models.Index(
                fields=["document", "-queued_at"],
                name="corpusactionexec_doc_queue",
            ),
            # Query: "Get executions by status" (pending work, failures)
            # Used by: monitoring, retry logic
            django.db.models.Index(
                fields=["status", "-queued_at"],
                name="corpusactionexec_status_queue",
            ),
            # Query: "Get executions by type for a corpus"
            # Used by: filtered trail views
            django.db.models.Index(
                fields=["corpus", "action_type", "-queued_at"],
                name="corpusactionexec_type_queue",
            ),
            # Composite: Detect duplicate/concurrent executions
            django.db.models.Index(
                fields=["corpus_action", "document", "status"],
                name="corpusactionexec_dedup",
            ),
            # Query: "Get executions for a conversation (thread) across all actions"
            # Used by: thread moderation history
            django.db.models.Index(
                fields=["conversation", "-queued_at"],
                name="corpusactionexec_conv_queue",
            ),
        ]

    def __str__(self) -> str:
        if self.document_id:
            target = f"doc:{self.document_id}"
        elif self.conversation_id:
            target = f"thread:{self.conversation_id}"
        else:
            target = "unknown"
        return f"{self.action_type}:{self.corpus_action.name}@{target} ({self.status})"

    @property
    def duration_seconds(self) -> float | None:
        """Calculate execution duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    @property
    def wait_time_seconds(self) -> float | None:
        """Calculate time spent in queue before execution."""
        if self.queued_at and self.started_at:
            return (self.started_at - self.queued_at).total_seconds()
        return None

    def add_affected_object(self, obj_type: str, obj_id: int, **extra: Any) -> None:
        """
        Add an affected object to the trail.

        Usage:
            execution.add_affected_object("datacell", datacell.id, column_name="parties")
            execution.add_affected_object("annotation", ann.id, label="indemnification")
        """
        entry = {"type": obj_type, "id": obj_id, **extra}
        if self.affected_objects is None:
            self.affected_objects = []
        self.affected_objects.append(entry)

    def mark_started(self, save: bool = True) -> None:
        """Mark execution as started. Use atomic update in concurrent scenarios."""
        self.status = self.Status.RUNNING
        self.started_at = timezone.now()
        if save:
            self.save(update_fields=["status", "started_at", "modified"])

    def mark_completed(
        self,
        affected_objects: list[dict] | None = None,
        metadata: dict | None = None,
        save: bool = True,
    ) -> None:
        """Mark execution as successfully completed."""
        self.status = self.Status.COMPLETED
        self.completed_at = timezone.now()
        if affected_objects:
            self.affected_objects = affected_objects
        if metadata:
            self.execution_metadata.update(metadata)
        if save:
            self.save(
                update_fields=[
                    "status",
                    "completed_at",
                    "affected_objects",
                    "execution_metadata",
                    "modified",
                ]
            )

    def mark_failed(
        self,
        error_message: str,
        error_traceback: str = "",
        save: bool = True,
    ) -> None:
        """Mark execution as failed with error details."""
        self.status = self.Status.FAILED
        self.completed_at = timezone.now()
        self.error_message = truncate(error_message, MAX_PROCESSING_ERROR_LENGTH)
        self.error_traceback = truncate(
            error_traceback, MAX_PROCESSING_TRACEBACK_LENGTH
        )
        if save:
            self.save(
                update_fields=[
                    "status",
                    "completed_at",
                    "error_message",
                    "error_traceback",
                    "modified",
                ]
            )

    def mark_skipped(self, reason: str = "", save: bool = True) -> None:
        """Mark execution as skipped (idempotent - already processed)."""
        self.status = self.Status.SKIPPED
        self.completed_at = timezone.now()
        if reason:
            self.execution_metadata["skip_reason"] = reason
        if save:
            self.save(
                update_fields=[
                    "status",
                    "completed_at",
                    "execution_metadata",
                    "modified",
                ]
            )

    @classmethod
    def bulk_queue(
        cls,
        corpus_action: CorpusAction,
        document_ids: list[int],
        trigger: str,
        user_id: int,
    ) -> list[CorpusActionExecution]:
        """
        Efficiently queue multiple executions in a single INSERT.

        Returns list of created execution records.
        """
        # Determine action type
        # Note: Use 'is not None' instead of truthiness because some models
        # (e.g., Analyzer) use CharField primary keys which may be empty strings
        if corpus_action.fieldset_id is not None:
            action_type = cls.ActionType.FIELDSET
        elif corpus_action.analyzer_id is not None:
            action_type = cls.ActionType.ANALYZER
        else:
            action_type = cls.ActionType.AGENT

        now = timezone.now()
        executions = [
            cls(
                corpus_action=corpus_action,
                document_id=doc_id,
                corpus_id=corpus_action.corpus_id,
                action_type=action_type,
                status=cls.Status.QUEUED,
                trigger=trigger,
                queued_at=now,
                creator_id=user_id,
            )
            for doc_id in document_ids
        ]

        return cls.objects.bulk_create(executions)  # type: ignore[return-value,arg-type]


class CorpusActionExecutionUserObjectPermission(UserObjectPermissionBase):
    """Guardian permission model for per-user execution permissions."""

    content_object = django.db.models.ForeignKey(
        "CorpusActionExecution", on_delete=django.db.models.CASCADE
    )


class CorpusActionExecutionGroupObjectPermission(GroupObjectPermissionBase):
    """Guardian permission model for per-group execution permissions."""

    content_object = django.db.models.ForeignKey(
        "CorpusActionExecution", on_delete=django.db.models.CASCADE
    )
