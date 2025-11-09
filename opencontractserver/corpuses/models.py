import difflib
import hashlib
import logging
import uuid
from typing import Optional

import django
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from guardian.models import GroupObjectPermissionBase, UserObjectPermissionBase
from tree_queries.models import TreeNode

from opencontractserver.annotations.models import Annotation
from opencontractserver.shared.Models import BaseOCModel
from opencontractserver.shared.QuerySets import PermissionedTreeQuerySet
from opencontractserver.shared.slug_utils import generate_unique_slug, sanitize_slug
from opencontractserver.shared.utils import calc_oc_file_path
from opencontractserver.utils.embeddings import generate_embeddings_from_text

logger = logging.getLogger(__name__)


def calculate_icon_filepath(instance, filename):
    return calc_oc_file_path(
        instance,
        filename,
        f"user_{instance.creator.id}/{instance.__class__.__name__}/icons/{uuid.uuid4()}",
    )


def calculate_temporary_filepath(instance, filename):
    return calc_oc_file_path(
        instance,
        filename,
        "temporary_files/",
    )


def calculate_description_filepath(instance, filename):
    """Generate a unique path for corpus markdown descriptions."""
    return calc_oc_file_path(
        instance,
        filename,
        f"user_{instance.creator.id}/{instance.__class__.__name__}/md_descriptions/{uuid.uuid4()}",
    )


class CorpusDocumentAssociation(django.db.models.Model):
    """
    Through model for Corpus-Document many-to-many relationship.
    Adds virtual folder path information for organizing documents within a corpus.

    The path field represents a virtual folder structure (e.g., "/contracts/2024/" or "" for root).
    This allows documents to be organized differently across different corpuses without
    requiring explicit folder objects.
    """

    corpus = django.db.models.ForeignKey(
        "Corpus",
        on_delete=django.db.models.CASCADE,
        related_name="document_associations",
    )
    document = django.db.models.ForeignKey(
        "documents.Document",
        on_delete=django.db.models.CASCADE,
        related_name="corpus_associations",
    )
    path = django.db.models.CharField(
        max_length=1024,
        default="",
        blank=True,
        db_index=True,
        help_text=(
            "Virtual folder path for this document in the corpus. "
            "Use forward slashes with leading/trailing slashes (e.g., '/folder/subfolder/'). "
            "Empty string or '/' represents root level."
        ),
    )
    created = django.db.models.DateTimeField(default=timezone.now)
    modified = django.db.models.DateTimeField(default=timezone.now, blank=True)

    class Meta:
        unique_together = ("corpus", "document")
        indexes = [
            django.db.models.Index(fields=["corpus", "path"]),
            django.db.models.Index(fields=["document"]),
            django.db.models.Index(fields=["path"]),
            django.db.models.Index(fields=["created"]),
        ]
        ordering = ("path", "document__title")

    def save(self, *args, **kwargs):
        """Normalize path on save."""
        # Normalize empty paths to empty string
        if self.path in (None, "/"):
            self.path = ""
        # Ensure non-empty paths have proper format
        elif self.path:
            # Strip whitespace
            self.path = self.path.strip()
            # Ensure leading slash
            if not self.path.startswith("/"):
                self.path = "/" + self.path
            # Ensure trailing slash
            if not self.path.endswith("/"):
                self.path = self.path + "/"

        self.modified = timezone.now()
        if not self.pk:
            self.created = timezone.now()

        return super().save(*args, **kwargs)

    def __str__(self):
        path_display = self.path if self.path else "/"
        return f"{self.corpus.title}: {self.document.title} @ {path_display}"


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
class Corpus(TreeNode):
    """
    Corpus, which stores a collection of documents that are grouped for machine learning / study / export purposes.
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

    # Documents and Labels in the Corpus
    documents = django.db.models.ManyToManyField(
        "documents.Document",
        blank=True,
        through="CorpusDocumentAssociation",
        related_name="corpuses_via_associations",
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
        help_text="Fully qualified Python path to the embedder class to use for this corpus",
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
            self.md_description.open("r")  # type: ignore[arg-type]
            try:
                return self.md_description.read()
            finally:
                self.md_description.close()
        except Exception:
            # Fall back to binary mode and decode manually.
            try:
                self.md_description.open("rb")  # type: ignore[arg-type]
                return self.md_description.read().decode("utf-8", errors="ignore")
            finally:
                self.md_description.close()

    def update_description(self, *, new_content: str, author):
        """Create a new revision and update md_description.

        Args:
            new_content (str): Markdown content.
            author (User | int): Responsible user.
        Returns:
            CorpusDescriptionRevision | None: the stored revision or None if no content change.
        """

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
                author=author_obj,
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
        ]
        ordering = ("created",)
        base_manager_name = "objects"
        constraints = [
            django.db.models.UniqueConstraint(
                fields=["creator", "slug"], name="uniq_corpus_slug_per_creator_cs"
            )
        ]

    # Override save to update modified on save
    def save(self, *args, **kwargs):
        """On save, update timestamps"""
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
        self.modified = timezone.now()

        return super().save(*args, **kwargs)

    def clean(self):
        """Validate the model before saving."""
        super().clean()

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

    def embed_text(self, text: str) -> tuple[Optional[str], Optional[list[float]]]:
        """
        Use a unified embeddings function from utils to create embeddings for the text.

        Args:
            text (str): The text to embed

        Returns:
            A tuple of (embedder path, embeddings list), or (None, None) on failure.
        """
        return generate_embeddings_from_text(text, corpus_id=self.pk)

    # --------------------------------------------------------------------- #
    # Document association helpers                                         #
    # --------------------------------------------------------------------- #

    def add_document(self, document, path=""):
        """
        Add a document to this corpus with an optional path.

        Args:
            document: Document instance or ID to add
            path: Virtual folder path (e.g., "/contracts/2024/"). Defaults to root ("").

        Returns:
            CorpusDocumentAssociation instance
        """
        from opencontractserver.documents.models import Document

        if isinstance(document, int):
            document = Document.objects.get(pk=document)

        association, created = CorpusDocumentAssociation.objects.get_or_create(
            corpus=self, document=document, defaults={"path": path}
        )

        # Update path if association already exists but path differs
        if not created and association.path != path:
            association.path = path
            association.save()

        return association

    def add_documents(self, documents, path=""):
        """
        Add multiple documents to this corpus with the same path.

        Args:
            documents: Iterable of Document instances or IDs
            path: Virtual folder path for all documents. Defaults to root ("").

        Returns:
            List of CorpusDocumentAssociation instances
        """
        from opencontractserver.documents.models import Document

        # Convert IDs to documents if needed
        doc_objects = []
        for doc in documents:
            if isinstance(doc, int):
                doc_objects.append(Document.objects.get(pk=doc))
            else:
                doc_objects.append(doc)

        associations = []
        for doc in doc_objects:
            association = self.add_document(doc, path)
            associations.append(association)

        return associations

    def remove_document(self, document):
        """
        Remove a document from this corpus.

        Args:
            document: Document instance or ID to remove

        Returns:
            bool: True if removed, False if not found
        """
        from opencontractserver.documents.models import Document

        if isinstance(document, int):
            document = Document.objects.get(pk=document)

        deleted_count, _ = CorpusDocumentAssociation.objects.filter(
            corpus=self, document=document
        ).delete()

        return deleted_count > 0

    def remove_documents(self, documents):
        """
        Remove multiple documents from this corpus.

        Args:
            documents: Iterable of Document instances or IDs

        Returns:
            int: Number of associations deleted
        """
        from opencontractserver.documents.models import Document

        # Convert to IDs
        doc_ids = []
        for doc in documents:
            if isinstance(doc, int):
                doc_ids.append(doc)
            else:
                doc_ids.append(doc.id)

        deleted_count, _ = CorpusDocumentAssociation.objects.filter(
            corpus=self, document_id__in=doc_ids
        ).delete()

        return deleted_count

    def get_document_path(self, document):
        """
        Get the virtual folder path for a document in this corpus.

        Args:
            document: Document instance or ID

        Returns:
            str: Path string, or None if document not in corpus
        """
        from opencontractserver.documents.models import Document

        if isinstance(document, int):
            document_id = document
        else:
            document_id = document.id

        try:
            association = CorpusDocumentAssociation.objects.get(
                corpus=self, document_id=document_id
            )
            return association.path
        except CorpusDocumentAssociation.DoesNotExist:
            return None

    def set_document_path(self, document, path):
        """
        Update the virtual folder path for a document in this corpus.

        Args:
            document: Document instance or ID
            path: New path string

        Returns:
            CorpusDocumentAssociation: Updated association, or None if not found
        """
        from opencontractserver.documents.models import Document

        if isinstance(document, int):
            document_id = document
        else:
            document_id = document.id

        try:
            association = CorpusDocumentAssociation.objects.get(
                corpus=self, document_id=document_id
            )
            association.path = path
            association.save()
            return association
        except CorpusDocumentAssociation.DoesNotExist:
            return None

    def get_documents_in_path(self, path="", recursive=False):
        """
        Get documents at a specific path in this corpus.

        Args:
            path: Virtual folder path. Defaults to root ("").
            recursive: If True, include documents in subfolders

        Returns:
            QuerySet of Document instances
        """
        from opencontractserver.documents.models import Document

        # Normalize path
        if path in (None, "/"):
            path = ""
        elif path:
            path = path.strip()
            if not path.startswith("/"):
                path = "/" + path
            if not path.endswith("/"):
                path = path + "/"

        if recursive and path:
            # Get all documents in this path and subpaths
            associations = CorpusDocumentAssociation.objects.filter(
                corpus=self, path__startswith=path
            )
        elif recursive:
            # Get all documents in corpus
            associations = CorpusDocumentAssociation.objects.filter(corpus=self)
        else:
            # Get only documents exactly in this path
            associations = CorpusDocumentAssociation.objects.filter(
                corpus=self, path=path
            )

        doc_ids = associations.values_list("document_id", flat=True)
        return Document.objects.filter(id__in=doc_ids)

    def get_folder_structure(self):
        """
        Get the complete folder structure for this corpus.

        Returns:
            dict: Dictionary with paths as keys and document counts as values
        """
        associations = CorpusDocumentAssociation.objects.filter(corpus=self).values(
            "path"
        )

        # Count documents per path
        from collections import defaultdict

        path_counts = defaultdict(int)
        for assoc in associations:
            path = assoc["path"] or "/"
            path_counts[path] += 1

        return dict(path_counts)

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
    ):
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


class CorpusQuery(BaseOCModel):
    """
    Store the response to the query as a structured annotation which can then be
    displayed and sources rendered via the frontend.

    NOTE - not permissioned separately from the corpus
    """

    query = django.db.models.TextField(blank=False, null=False)
    corpus = django.db.models.ForeignKey(
        "Corpus", on_delete=django.db.models.CASCADE, related_name="queries"
    )
    sources = django.db.models.ManyToManyField(
        Annotation,
        blank=True,
        related_name="queries",
        related_query_name="created_by_query",
    )
    response = django.db.models.TextField(blank=True, null=True)
    started = django.db.models.DateTimeField(null=True, blank=True)
    completed = django.db.models.DateTimeField(null=True, blank=True)
    failed = django.db.models.DateTimeField(null=True, blank=True)
    stacktrace = django.db.models.TextField(null=True, blank=True)

    class Meta:
        permissions = (
            ("permission_corpusquery", "permission corpusquery"),
            ("publish_corpusquery", "publish corpusquery"),
            ("create_corpusquery", "create corpusquery"),
            ("read_corpusquery", "read corpusquery"),
            ("update_corpusquery", "update corpusquery"),
            ("remove_corpusquery", "delete corpusquery"),
            ("comment_corpusquery", "comment corpusquery"),
        )
        indexes = [
            django.db.models.Index(fields=["corpus"]),
            django.db.models.Index(fields=["started"]),
            django.db.models.Index(fields=["completed"]),
            django.db.models.Index(fields=["failed"]),
            django.db.models.Index(fields=["creator"]),
            django.db.models.Index(fields=["created"]),
        ]
        ordering = ("created",)
        base_manager_name = "objects"


# Model for Django Guardian permissions... trying to improve performance...
class CorpusQueryUserObjectPermission(UserObjectPermissionBase):
    content_object = django.db.models.ForeignKey(
        "CorpusQuery", on_delete=django.db.models.CASCADE
    )
    # enabled = False


# Model for Django Guardian permissions... trying to improve performance...
class CorpusQueryGroupObjectPermission(GroupObjectPermissionBase):
    content_object = django.db.models.ForeignKey(
        "CorpusQuery", on_delete=django.db.models.CASCADE
    )
    # enabled = False


class CorpusActionTrigger(django.db.models.TextChoices):
    ADD_DOCUMENT = "add_document", "Add Document"
    EDIT_DOCUMENT = "edit_document", "Edit Document"


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
    trigger = django.db.models.CharField(
        max_length=256, choices=CorpusActionTrigger.choices
    )
    disabled = django.db.models.BooleanField(null=False, default=False, blank=True)
    run_on_all_corpuses = django.db.models.BooleanField(
        null=False, default=False, blank=True
    )

    class Meta:
        constraints = [
            django.db.models.CheckConstraint(
                check=(
                    django.db.models.Q(fieldset__isnull=False, analyzer__isnull=True)
                    | django.db.models.Q(fieldset__isnull=True, analyzer__isnull=False)
                ),
                name="exactly_one_of_fieldset_or_analyzer",
            )
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

    def clean(self):
        if self.fieldset and self.analyzer:
            raise ValidationError("Only one of fieldset or analyzer can be set.")
        if not self.fieldset and not self.analyzer:
            raise ValidationError("Either fieldset or analyzer must be set.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        action_type = "Fieldset" if self.fieldset else "Analyzer"
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

    def __str__(self):
        return (
            f"CorpusDescriptionRevision(corpus_id={self.corpus_id}, v={self.version})"
        )
