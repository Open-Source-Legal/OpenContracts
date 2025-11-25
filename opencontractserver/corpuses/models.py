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
            - status: 'added' (new copy created) or 'already_exists' (content already in corpus)
            - document_path: The DocumentPath record created or existing

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
            # Check if this content already exists in THIS corpus (by hash)
            # This implements corpus isolation - we check within corpus, not globally
            # IMPORTANT: Only deduplicate if hash is not None (avoid treating all NULL hashes as same)
            corpus_doc_with_hash = None
            if document.pdf_file_hash is not None:
                corpus_doc_with_hash = (
                    DocumentPath.objects.filter(
                        corpus=self,
                        document__pdf_file_hash=document.pdf_file_hash,
                        is_current=True,
                        is_deleted=False,
                    )
                    .select_related("document")
                    .first()
                )

            if corpus_doc_with_hash:
                # Content already exists in THIS corpus
                existing_doc = corpus_doc_with_hash.document
                logger.info(
                    f"Content from doc {document.pk} already exists in corpus {self.pk} "
                    f"as doc {existing_doc.pk}"
                )
                # Return the existing corpus-isolated document
                return existing_doc, "already_exists", corpus_doc_with_hash

            # Create corpus-isolated copy with new version tree
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
                structural_annotation_set=document.structural_annotation_set,  # Share structural annotations
                creator=user,
                **{
                    k: v
                    for k, v in doc_kwargs.items()
                    if k not in ["title", "description", "file_type"]
                },
            )

            logger.info(
                f"Created corpus-isolated copy {corpus_copy.pk} from doc {document.pk} "
                f"in corpus {self.pk} (structural_set={document.structural_annotation_set_id})"
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

            logger.info(
                f"Added corpus-isolated doc {corpus_copy.pk} to corpus {self.pk} at {path}"
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
        """Get count of documents directly in this folder (not including subfolders)."""
        return self.document_assignments.count()

    def get_descendant_document_count(self) -> int:
        """Get count of documents in this folder and all subfolders."""
        descendant_folders = self.get_descendant_folders()
        return CorpusDocumentFolder.objects.filter(
            folder__in=descendant_folders
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


class CorpusDocumentFolder(django.db.models.Model):
    """
    Junction table linking documents to folders within a corpus.
    Enforces one-folder-per-document-per-corpus constraint.
    Null folder means document is in corpus "root".
    """

    document = django.db.models.ForeignKey(
        "documents.Document",
        on_delete=django.db.models.CASCADE,
        related_name="corpus_folder_assignments",
    )

    corpus = django.db.models.ForeignKey(
        "corpuses.Corpus",
        on_delete=django.db.models.CASCADE,
        related_name="document_folder_assignments",
    )

    folder = django.db.models.ForeignKey(
        "CorpusFolder",
        on_delete=django.db.models.CASCADE,
        null=True,
        blank=True,
        related_name="document_assignments",
        help_text="Folder containing this document. Null = root of corpus.",
    )

    # Timestamps
    added_to_folder = django.db.models.DateTimeField(
        default=timezone.now,
        help_text="When document was added to this folder",
    )

    class Meta:
        indexes = [
            django.db.models.Index(fields=["corpus", "folder"]),
            django.db.models.Index(fields=["document", "corpus"]),
            django.db.models.Index(fields=["folder"]),
        ]
        constraints = [
            # One folder per document per corpus (null folder = root)
            django.db.models.UniqueConstraint(
                fields=["document", "corpus"],
                name="unique_document_folder_per_corpus",
            ),
        ]

    def clean(self):
        """Validate folder belongs to same corpus."""
        super().clean()
        if self.folder and self.folder.corpus_id != self.corpus_id:
            raise ValidationError("Folder must belong to the same corpus")

    def save(self, *args, **kwargs):
        """Validate before saving."""
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        folder_path = self.folder.get_path() if self.folder else "root"
        return f"{self.document.title} in {self.corpus.title}/{folder_path}"
