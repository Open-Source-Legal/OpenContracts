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

from opencontractserver.corpuses.managers import CorpusActionExecutionManager
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

    def __str__(self):
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
    documents = django.db.models.ManyToManyField("documents.Document", blank=True)
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
    # Document Management - Issue #654                                     #
    # --------------------------------------------------------------------- #

    def add_document(
        self,
        document=None,
        path: str = None,
        user=None,
        folder=None,
        content: bytes = None,
        **doc_kwargs,
    ):
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
            content: DEPRECATED - use import_content() for content-based imports
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

        # Handle deprecated content parameter
        if content is not None:
            logger.warning(
                "content parameter is deprecated in add_document(). "
                "Use import_content() for content-based imports."
            )

        from opencontractserver.documents.models import Document, DocumentPath

        # Generate path if not provided
        if not path:
            if document.title:
                safe_title = "".join(
                    c if c.isalnum() or c in "-_." else "_"
                    for c in document.title[:100]
                )
                path = f"/documents/{safe_title or f'doc_{document.pk}'}"
            else:
                path = f"/documents/doc_{document.pk}"

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
                is_public=document.is_public,  # Inherit public status
                version_tree_id=tree_id,  # NEW isolated version tree
                is_current=True,
                parent=None,  # Root of NEW content tree
                source_document=document,  # Provenance tracking (Rule I2)
                creator=user,
                **{
                    k: v
                    for k, v in doc_kwargs.items()
                    if k not in ["title", "description", "file_type"]
                },
            )

            # Copy structural annotations for corpus isolation (per-corpus embeddings)
            # Annotations are copied without embeddings - they'll be regenerated per-corpus
            from opencontractserver.annotations.models import Annotation, Relationship

            structural_annots = Annotation.objects.filter(
                document=document, structural=True
            )
            annot_id_map = {}  # Map old annotation IDs to new ones for relationships

            for annot in structural_annots:
                old_id = annot.pk
                annot.pk = None
                annot.document = corpus_copy
                annot.corpus = self  # Associate with this corpus
                annot.embedding = None  # Clear legacy embedding field
                annot.embeddings = None  # Clear new embedding FK
                annot.save()
                annot_id_map[old_id] = annot.pk

            # Copy structural relationships, remapping annotation references
            structural_rels = Relationship.objects.filter(
                document=document, structural=True
            ).prefetch_related("source_annotations", "target_annotations")

            for rel in structural_rels:
                old_source_ids = list(
                    rel.source_annotations.values_list("id", flat=True)
                )
                old_target_ids = list(
                    rel.target_annotations.values_list("id", flat=True)
                )

                rel.pk = None
                rel.document = corpus_copy
                rel.corpus = self  # Associate with this corpus
                rel.save()

                # Remap source and target annotations to the copied annotations
                new_source_ids = [
                    annot_id_map.get(sid)
                    for sid in old_source_ids
                    if sid in annot_id_map
                ]
                new_target_ids = [
                    annot_id_map.get(tid)
                    for tid in old_target_ids
                    if tid in annot_id_map
                ]

                if new_source_ids:
                    rel.source_annotations.set(new_source_ids)
                if new_target_ids:
                    rel.target_annotations.set(new_target_ids)

            structural_count = len(annot_id_map)
            logger.info(
                f"Created corpus-isolated copy {corpus_copy.pk} from doc {document.pk} "
                f"in corpus {self.pk} (copied {structural_count} structural annotations)"
            )

            # Check if path is occupied
            occupied_path = DocumentPath.objects.filter(
                corpus=self, path=path, is_current=True, is_deleted=False
            ).first()

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
                creator=user,
            )

            # Maintain M2M relationship for backwards compatibility
            # This allows legacy queries like Document.objects.filter(corpus=...)
            self.documents.add(corpus_copy)

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

    def import_content(
        self,
        content: bytes,
        path: str = None,
        user=None,
        folder=None,
        **doc_kwargs,
    ):
        """
        Import content into this corpus with corpus-isolated deduplication.

        This uses SHA-256 hashing to detect duplicate content within THIS corpus.
        Documents are isolated within the corpus with independent version trees.
        Provenance is tracked via source_document field when content exists elsewhere.

        Args:
            content: PDF content bytes (required)
            path: The filesystem path within the corpus (auto-generated if not provided)
            user: The user performing the operation (required)
            folder: Optional CorpusFolder to place the document in
            **doc_kwargs: Additional arguments for document creation (title, description, etc.)

        Returns:
            Tuple of (document, status, document_path) where status is one of:
            - 'created': Brand new document (content hash first seen globally)
            - 'updated': Content changed at existing path (version increment)
            - 'unchanged': No change detected at path
            - 'linked': Same content already exists in THIS corpus at different path
            - 'created_from_existing': New corpus-isolated doc, content exists elsewhere

        Raises:
            ValueError: If user or content is not provided
        """
        if not user:
            raise ValueError("User is required for document operations (audit trail)")

        if content is None:
            raise ValueError("Content is required for import_content()")

        from opencontractserver.documents.versioning import import_document

        # Generate path if not provided
        if not path:
            path = f"/documents/doc_{uuid.uuid4().hex[:8]}"

        return import_document(
            corpus=self,
            path=path,
            content=content,
            user=user,
            folder=folder,
            **doc_kwargs,
        )

    def remove_document(self, document=None, path: str = None, user=None):
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
                        creator=user,
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
                # Delete all paths for this document
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
                        creator=user,
                    )
                    deleted_paths.append(deleted_path)
                    logger.info(
                        f"Removed document {document.pk} at path "
                        f"{path_record.path} from corpus {self.pk}"
                    )

        return deleted_paths

    def get_documents(self):
        """
        Get all documents with active paths in this corpus.

        This method uses DocumentPath as the source of truth.

        Returns:
            QuerySet of Document objects with active paths in this corpus
        """
        from opencontractserver.documents.models import Document, DocumentPath

        active_doc_ids = DocumentPath.objects.filter(
            corpus=self, is_current=True, is_deleted=False
        ).values_list("document_id", flat=True)

        return Document.objects.filter(id__in=active_doc_ids).distinct()

    def document_count(self):
        """
        Get count of documents with active paths in this corpus.

        Returns:
            Integer count of active documents
        """
        from opencontractserver.documents.models import DocumentPath

        return (
            DocumentPath.objects.filter(corpus=self, is_current=True, is_deleted=False)
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
        help_text="Agent configuration to use for this action",
    )
    agent_prompt = django.db.models.TextField(
        blank=True,
        default="",
        help_text="Task-specific prompt for the agent (e.g., 'Summarize this document')",
    )
    pre_authorized_tools = django.db.models.JSONField(
        default=list,
        blank=True,
        help_text="Tools pre-authorized to run without approval. If empty, uses agent_config.available_tools",
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
            # Exactly ONE of fieldset, analyzer, or agent_config must be set
            django.db.models.CheckConstraint(
                check=(
                    # Fieldset only
                    django.db.models.Q(
                        fieldset__isnull=False,
                        analyzer__isnull=True,
                        agent_config__isnull=True,
                    )
                    # Analyzer only
                    | django.db.models.Q(
                        fieldset__isnull=True,
                        analyzer__isnull=False,
                        agent_config__isnull=True,
                    )
                    # Agent config only
                    | django.db.models.Q(
                        fieldset__isnull=True,
                        analyzer__isnull=True,
                        agent_config__isnull=False,
                    )
                ),
                name="exactly_one_of_fieldset_analyzer_or_agent",
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
        # Count how many action types are set
        action_types_set = sum(
            [
                self.fieldset is not None,
                self.analyzer is not None,
                self.agent_config is not None,
            ]
        )
        if action_types_set > 1:
            raise ValidationError(
                "Only one of fieldset, analyzer, or agent_config can be set."
            )
        if action_types_set == 0:
            raise ValidationError(
                "One of fieldset, analyzer, or agent_config must be set."
            )
        # Validate agent_prompt is provided when agent_config is set
        if self.agent_config and not self.agent_prompt:
            raise ValidationError("agent_prompt is required when agent_config is set.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        if self.fieldset:
            action_type = "Fieldset"
        elif self.analyzer:
            action_type = "Analyzer"
        elif self.agent_config:
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

    def __str__(self):
        return f"Engagement Metrics for {self.corpus.title}"


# --------------------------------------------------------------------------- #
# Corpus Folder Structure
# --------------------------------------------------------------------------- #


class CorpusFolder(TreeNode):
    """
    Hierarchical folder structure within a corpus for organizing documents.
    Uses TreeNode for efficient tree operations via CTEs.
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

    def save(self, *args, **kwargs):
        """On save, update timestamps and validate parent corpus"""
        if not self.pk:
            self.created = timezone.now()
        self.modified = timezone.now()

        # Validate parent belongs to same corpus
        if self.parent and self.parent.corpus_id != self.corpus_id:
            raise ValidationError("Folder parent must belong to the same corpus")

        super().save(*args, **kwargs)

    def clean(self):
        """Validate the model before saving."""
        super().clean()

        # Validate tags is a list
        if not isinstance(self.tags, list):
            raise ValidationError({"tags": "Must be a list of strings"})

        # Validate each tag is a string
        for tag in self.tags:
            if not isinstance(tag, str):
                raise ValidationError({"tags": "Each tag must be a string"})

    def get_path(self) -> str:
        """Get full path from root to this folder."""
        ancestors = self.ancestors(include_self=True)
        return "/".join(f.name for f in ancestors)

    def get_descendant_folders(self):
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

    def __str__(self):
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

    # Custom manager for optimized queries
    objects = CorpusActionExecutionManager()

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

    def __str__(self):
        if self.document_id:
            target = f"doc:{self.document_id}"
        elif self.conversation_id:
            target = f"thread:{self.conversation_id}"
        else:
            target = "unknown"
        return f"{self.action_type}:{self.corpus_action.name}@{target} ({self.status})"

    @property
    def duration_seconds(self) -> Optional[float]:
        """Calculate execution duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    @property
    def wait_time_seconds(self) -> Optional[float]:
        """Calculate time spent in queue before execution."""
        if self.queued_at and self.started_at:
            return (self.started_at - self.queued_at).total_seconds()
        return None

    def add_affected_object(self, obj_type: str, obj_id: int, **extra) -> None:
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
        affected_objects: Optional[list[dict]] = None,
        metadata: Optional[dict] = None,
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
        self.error_message = error_message[:5000]  # Truncate
        self.error_traceback = error_traceback[:10000]  # Truncate
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
        corpus_action: "CorpusAction",
        document_ids: list[int],
        trigger: str,
        user_id: int,
    ) -> list["CorpusActionExecution"]:
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

        return cls.objects.bulk_create(executions)


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
