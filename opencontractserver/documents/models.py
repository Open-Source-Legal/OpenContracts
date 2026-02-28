import difflib
import functools
import hashlib
import uuid

import django
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone
from guardian.models import GroupObjectPermissionBase, UserObjectPermissionBase
from pgvector.django import VectorField
from tree_queries.models import TreeNode

from opencontractserver.shared.defaults import jsonfield_default_value
from opencontractserver.shared.fields import NullableJSONField
from opencontractserver.shared.Managers import DocumentManager
from opencontractserver.shared.mixins import HasEmbeddingMixin
from opencontractserver.shared.Models import BaseOCModel
from opencontractserver.shared.slug_utils import generate_unique_slug, sanitize_slug
from opencontractserver.shared.utils import calc_oc_file_path


class DocumentProcessingStatus(models.TextChoices):
    """Processing status for documents in the parsing pipeline."""

    PENDING = "pending", "Pending"
    PROCESSING = "processing", "Processing"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"


class Document(TreeNode, BaseOCModel, HasEmbeddingMixin):
    """
    Document
    """

    objects = DocumentManager()

    # Key fields
    title = django.db.models.CharField(max_length=1024, null=True, blank=True)
    description = django.db.models.TextField(null=True, blank=True)
    slug = django.db.models.CharField(
        max_length=128,
        db_index=True,
        null=True,
        blank=True,
        help_text=(
            "Case-sensitive slug unique per creator. Allowed: A-Z, a-z, 0-9, hyphen (-)."
        ),
    )
    custom_meta = NullableJSONField(
        default=jsonfield_default_value, null=True, blank=True
    )

    # File fields (Some of these are text blobs or jsons that could be huge, so we're storing them in S3 and going
    # to have the frontend fetch them from there. Will be much faster and cheaper than having a huge relational database
    # full of these kinds of things).
    file_type = django.db.models.CharField(
        blank=False, null=False, max_length=255, default="application/pdf"
    )
    icon = django.db.models.FileField(
        max_length=1024,
        blank=True,
        upload_to=functools.partial(calc_oc_file_path, sub_folder="pdf_icons"),
    )
    pdf_file = django.db.models.FileField(
        max_length=1024,
        blank=True,
        null=True,
        upload_to=functools.partial(calc_oc_file_path, sub_folder="pdf_files"),
    )
    txt_extract_file = django.db.models.FileField(
        max_length=1024,
        blank=True,
        upload_to=functools.partial(calc_oc_file_path, sub_folder="txt_layers_files"),
        null=True,
    )
    md_summary_file = django.db.models.FileField(
        max_length=1024,
        blank=True,
        upload_to=functools.partial(calc_oc_file_path, sub_folder="md_summaries"),
        null=True,
    )
    page_count = django.db.models.IntegerField(
        default=0,
        null=False,
        blank=True,
    )
    pawls_parse_file = django.db.models.FileField(
        max_length=1024,
        blank=True,
        upload_to=functools.partial(calc_oc_file_path, sub_folder="pawls_layers_files"),
        null=True,
    )

    # Hash field for PDF file integrity and caching
    pdf_file_hash = django.db.models.CharField(
        max_length=64,  # SHA-256 produces 64 hex characters
        null=True,
        blank=True,
        db_index=True,
        help_text="SHA-256 hash of the PDF file content for caching and integrity checks",
    )

    # Versioning fields for dual-tree architecture
    version_tree_id = django.db.models.UUIDField(
        default=uuid.uuid4,
        db_index=True,
        help_text="Groups all content versions of same logical document. Implements Rule C1.",
    )
    is_current = django.db.models.BooleanField(
        default=True,
        db_index=True,
        help_text="True for newest content in this version tree. Implements Rule C3.",
    )

    # Provenance tracking for corpus-isolated documents (Phase 2)
    source_document = django.db.models.ForeignKey(
        "self",
        on_delete=django.db.models.SET_NULL,
        null=True,
        blank=True,
        related_name="corpus_copies",
        help_text="Original document this was copied from (cross-corpus provenance). Implements Rule I2.",
    )

    # Shared structural annotations (Phase 2.5)
    structural_annotation_set = django.db.models.ForeignKey(
        "annotations.StructuralAnnotationSet",
        on_delete=django.db.models.PROTECT,  # Never delete if documents reference it
        null=True,
        blank=True,
        related_name="documents",
        help_text="Shared structural annotations for this document's content",
    )

    processing_started = django.db.models.DateTimeField(null=True)
    processing_finished = django.db.models.DateTimeField(null=True)

    # Processing status fields for pipeline hardening (PR #824)
    processing_status = django.db.models.CharField(
        max_length=20,
        choices=DocumentProcessingStatus.choices,
        default=DocumentProcessingStatus.PENDING,
        db_index=True,
        help_text="Current processing status of the document in the parsing pipeline",
    )
    processing_error = django.db.models.TextField(
        blank=True,
        default="",
        help_text="Error message if processing failed",
    )
    processing_error_traceback = django.db.models.TextField(
        blank=True,
        default="",
        help_text="Full traceback if processing failed",
    )

    # Vector for vector search
    embedding = VectorField(dimensions=384, null=True, blank=True)

    class Meta:
        permissions = (
            ("permission_document", "permission document"),
            ("publish_document", "publish document"),
            ("create_document", "create document"),
            ("read_document", "read document"),
            ("update_document", "update document"),
            ("remove_document", "delete document"),
            ("comment_document", "comment document"),
        )
        indexes = [
            django.db.models.Index(fields=["title"]),
            django.db.models.Index(fields=["page_count"]),
            django.db.models.Index(fields=["creator"]),
            django.db.models.Index(fields=["created"]),
            django.db.models.Index(fields=["modified"]),
        ]
        constraints = [
            django.db.models.UniqueConstraint(
                fields=["creator", "slug"], name="uniq_document_slug_per_creator_cs"
            ),
            # Rule C3: Only one current Document per version tree
            django.db.models.UniqueConstraint(
                fields=["version_tree_id"],
                condition=django.db.models.Q(is_current=True),
                name="one_current_per_version_tree",
            ),
        ]

    # ------ Revision mechanics ------ #
    REVISION_SNAPSHOT_INTERVAL = 10

    def get_summary_for_corpus(self, corpus):
        """Get the latest summary content for this document in a specific corpus.

        Args:
            corpus: The corpus to get the summary for.
        Returns:
            str: The latest summary content, or empty string if none exists.
        """
        from opencontractserver.documents.models import DocumentSummaryRevision

        latest_rev = (
            DocumentSummaryRevision.objects.filter(
                document_id=self.pk, corpus_id=corpus.pk
            )
            .order_by("-version")
            .first()
        )

        if not latest_rev:
            return ""

        if latest_rev.snapshot:
            return latest_rev.snapshot
        else:
            # Diff reconstruction not yet needed — every revision currently
            # stores a full snapshot. Return empty string as a safe fallback.
            return ""

    def update_summary(self, *, new_content: str, author, corpus):
        """Create a new revision and update md_summary_file for a specific corpus.

        Args:
            new_content (str): Markdown content.
            author (User | int): Responsible user.
            corpus: The corpus this summary is for.
        Returns:
            DocumentSummaryRevision | None: the stored revision or None if no content change.
        """

        if isinstance(author, int):
            author_obj = get_user_model().objects.get(pk=author)
        else:
            author_obj = author

        # Get the original content for this document-corpus combination
        from opencontractserver.documents.models import (  # avoid circular
            DocumentSummaryRevision,
        )

        latest_rev = (
            DocumentSummaryRevision.objects.filter(
                document_id=self.pk, corpus_id=corpus.pk
            )
            .order_by("-version")
            .first()
        )

        if latest_rev and latest_rev.snapshot:
            original_content = latest_rev.snapshot
        elif latest_rev:
            # Diff reconstruction not yet needed — every revision currently
            # stores a full snapshot. Return empty string as a safe fallback.
            original_content = ""
        else:
            original_content = ""

        if original_content == (new_content or ""):
            return None  # No change

        with transaction.atomic():
            # Compute next version for this document-corpus combination
            next_version = 1 if latest_rev is None else latest_rev.version + 1

            diff_text = "\n".join(
                difflib.unified_diff(
                    original_content.splitlines(),
                    new_content.splitlines(),
                    lineterm="",
                )
            )

            # Store a full snapshot for every revision for simplicity; can revert back later
            snapshot_text = new_content  # always persist full content

            revision = DocumentSummaryRevision.objects.create(
                document=self,
                corpus=corpus,
                author=author_obj,
                version=next_version,
                diff=diff_text,
                snapshot=snapshot_text,
                checksum_base=hashlib.sha256(original_content.encode()).hexdigest(),
                checksum_full=hashlib.sha256(new_content.encode()).hexdigest(),
            )

        return revision

    def get_embedding_reference_kwargs(self) -> dict:
        return {"document_id": self.pk}

    def compute_pdf_hash(self):
        """
        Compute SHA-256 hash of the PDF file content.
        Returns None if no PDF file exists.
        """
        if not self.pdf_file:
            return None

        sha256_hash = hashlib.sha256()
        # Read file in chunks to handle large PDFs efficiently
        for chunk in self.pdf_file.chunks(chunk_size=8192):
            sha256_hash.update(chunk)

        return sha256_hash.hexdigest()

    def update_pdf_hash(self):
        """
        Update the pdf_file_hash field with the current PDF's hash.
        This method saves the model if the hash changes.
        """
        new_hash = self.compute_pdf_hash()
        if new_hash != self.pdf_file_hash:
            self.pdf_file_hash = new_hash
            self.save(update_fields=["pdf_file_hash"])
            return True
        return False

    def __str__(self):
        """
        String representation method
        :return:
        """
        return f"Doc ({self.id}) - {self.description}".encode("utf-8", "ignore").decode(
            "utf-8", "ignore"
        )

    def save(self, *args, **kwargs):
        # Ensure slug exists and is unique within creator scope
        if not self.slug or not isinstance(self.slug, str) or not self.slug.strip():
            base_value = self.title or self.description or f"document-{self.pk or ''}"
            scope = Document.objects.filter(creator_id=self.creator_id)
            if self.pk:
                scope = scope.exclude(pk=self.pk)
            self.slug = generate_unique_slug(
                base_value=base_value,
                scope_qs=scope,
                slug_field="slug",
                max_length=128,
                fallback_prefix="document",
            )
        else:
            self.slug = sanitize_slug(self.slug, max_length=128)

        super().save(*args, **kwargs)


# Model for Django Guardian permissions... trying to improve performance...
class DocumentUserObjectPermission(UserObjectPermissionBase):
    content_object = django.db.models.ForeignKey(
        "Document", on_delete=django.db.models.CASCADE
    )
    # enabled = False


# Model for Django Guardian permissions... trying to improve performance...
class DocumentGroupObjectPermission(GroupObjectPermissionBase):
    content_object = django.db.models.ForeignKey(
        "Document", on_delete=django.db.models.CASCADE
    )
    # enabled = False


# Basically going to hold row-level data for extracts, and, for analyses, the analyses
# results per analysis per document
class DocumentAnalysisRow(BaseOCModel):
    document = django.db.models.ForeignKey(
        "documents.Document",
        related_name="rows",
        on_delete=django.db.models.CASCADE,
        null=False,
        blank=False,
    )
    annotations = django.db.models.ManyToManyField(
        "annotations.Annotation", related_name="rows"
    )
    data = django.db.models.ManyToManyField(
        "extracts.Datacell",
        related_name="rows",
    )
    analysis = django.db.models.ForeignKey(
        "analyzer.Analysis",
        related_name="rows",
        on_delete=django.db.models.CASCADE,
        null=True,
        blank=True,
    )
    extract = django.db.models.ForeignKey(
        "extracts.Extract",
        related_name="rows",
        on_delete=django.db.models.CASCADE,
        null=True,
        blank=True,
    )

    class Meta:
        permissions = (
            ("create_documentanalysisrow", "create DocumentAnalysisRow"),
            ("read_documentanalysisrow", "read DocumentAnalysisRow"),
            ("update_documentanalysisrow", "update DocumentAnalysisRow"),
            ("remove_documentanalysisrow", "delete DocumentAnalysisRow"),
            ("publish_documentanalysisrow", "publish DocumentAnalysisRow"),
            ("permission_documentanalysisrow", "permission DocumentAnalysisRow"),
            ("comment_documentanalysisrow", "comment DocumentAnalysisRow"),
        )
        constraints = [
            django.db.models.UniqueConstraint(
                fields=["document", "analysis"],
                condition=django.db.models.Q(analysis__isnull=False),
                name="unique_document_analysis",
            ),
            django.db.models.UniqueConstraint(
                fields=["document", "extract"],
                condition=django.db.models.Q(extract__isnull=False),
                name="unique_document_extract",
            ),
        ]

    def clean(self):
        super().clean()
        if (self.analysis is None and self.extract is None) or (
            self.analysis is not None and self.extract is not None
        ):
            raise ValidationError(
                "Either 'analysis' or 'extract' must be set, but not both."
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class DocumentAnalysisRowUserObjectPermission(UserObjectPermissionBase):
    content_object = django.db.models.ForeignKey(
        "DocumentAnalysisRow", on_delete=django.db.models.CASCADE
    )
    # enabled = Falses


# Model for Django Guardian permissions... trying to improve performance...
class DocumentAnalysisRowGroupObjectPermission(GroupObjectPermissionBase):
    content_object = django.db.models.ForeignKey(
        "DocumentAnalysisRow", on_delete=django.db.models.CASCADE
    )
    # enabled = False


class DocumentRelationship(BaseOCModel):
    """
    Represents a relationship between two documents, such as notes or other relationships.
    For RELATIONSHIP types, the meaning is defined by the associated annotation_label.
    For NOTES types, the annotation_label is optional and multiple notes can exist between the same documents.
    """

    RELATIONSHIP_TYPE_CHOICES = [
        ("NOTES", "Notes"),
        ("RELATIONSHIP", "Relationship"),
    ]

    source_document = django.db.models.ForeignKey(
        "Document",
        related_name="source_relationships",
        on_delete=django.db.models.CASCADE,
        null=False,
    )

    target_document = django.db.models.ForeignKey(
        "Document",
        related_name="target_relationships",
        on_delete=django.db.models.CASCADE,
        null=False,
    )

    relationship_type = django.db.models.CharField(
        max_length=32,
        choices=RELATIONSHIP_TYPE_CHOICES,
        default="RELATIONSHIP",
        null=False,
    )

    annotation_label = django.db.models.ForeignKey(
        "annotations.AnnotationLabel",
        null=True,
        blank=True,  # Allow blank for NOTES type
        on_delete=django.db.models.CASCADE,
        related_name="document_relationships",
    )

    corpus = django.db.models.ForeignKey(
        "corpuses.Corpus",
        related_name="document_relationships",
        on_delete=django.db.models.CASCADE,
        null=True,
        blank=True,
    )

    data = NullableJSONField(
        default=jsonfield_default_value,
        null=True,
        blank=True,
    )

    # Note: DocumentRelationship inherits permissions from source_document,
    # target_document, and corpus - no individual guardian permissions needed.
    # Use DocumentRelationshipQueryOptimizer for permission-aware queries.

    class Meta:
        indexes = [
            django.db.models.Index(fields=["source_document"]),
            django.db.models.Index(fields=["target_document"]),
            django.db.models.Index(fields=["relationship_type"]),
            django.db.models.Index(fields=["annotation_label"]),
            django.db.models.Index(fields=["corpus"]),
            django.db.models.Index(fields=["creator"]),
            django.db.models.Index(fields=["created"]),
            django.db.models.Index(fields=["modified"]),
        ]
        constraints = [
            django.db.models.UniqueConstraint(
                fields=["source_document", "target_document", "annotation_label"],
                condition=django.db.models.Q(relationship_type="RELATIONSHIP"),
                name="unique_document_relationship",
            )
        ]

    def clean(self):
        """
        Validate DocumentRelationship constraints:
        1. annotation_label is required for RELATIONSHIP type
        2. corpus is required
        3. Both documents must be in the specified corpus
        """
        super().clean()

        if self.relationship_type == "RELATIONSHIP" and not self.annotation_label:
            raise ValidationError(
                {
                    "annotation_label": "Annotation label is required for relationship type RELATIONSHIP."
                }
            )

        # Corpus is required
        if not self.corpus_id:
            raise ValidationError(
                {"corpus": "Corpus is required for document relationships."}
            )

        # Both documents must be in the corpus via DocumentPath
        if self.source_document_id and self.target_document_id and self.corpus_id:
            docs_in_corpus = DocumentPath.objects.filter(
                corpus_id=self.corpus_id,
                document_id__in=[self.source_document_id, self.target_document_id],
                is_current=True,
                is_deleted=False,
            ).count()

            if docs_in_corpus != 2:
                raise ValidationError(
                    "Both source and target documents must be in the specified corpus."
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


# -------------------- DocumentPath -------------------- #


class DocumentPath(TreeNode, BaseOCModel):
    """
    Path Tree - tracks where documents lived and what happened to them.

    This model implements the Path Tree from the dual-tree versioning architecture.
    Each node represents a lifecycle event:
    - File first imported
    - File content updated to new version
    - File moved or renamed
    - File deleted (soft delete)
    - File restored

    Architecture Rules Implemented:
    - P1: New DocumentPath for every lifecycle event
    - P2: New nodes are children of previous state (via TreeNode parent)
    - P3: Only current filesystem state has is_current=True
    - P4: One active path per (corpus, path) tuple
    - P5: version_number increments only on content changes
    - P6: Folder deletion sets folder=NULL
    """

    document = django.db.models.ForeignKey(
        "Document",
        on_delete=django.db.models.PROTECT,  # Never delete Documents
        related_name="path_records",
        help_text="Specific content version this path points to",
    )

    corpus = django.db.models.ForeignKey(
        "corpuses.Corpus",
        on_delete=django.db.models.CASCADE,
        related_name="document_paths",
        help_text="Corpus owning this path",
    )

    folder = django.db.models.ForeignKey(
        "corpuses.CorpusFolder",
        null=True,
        blank=True,
        on_delete=django.db.models.SET_NULL,  # Rule P6: folder deletion sets NULL
        related_name="document_paths",
        help_text="Current folder (null if folder deleted or at root)",
    )

    path = django.db.models.CharField(
        max_length=1024,
        db_index=True,
        help_text="Full path in corpus filesystem",
    )

    version_number = django.db.models.IntegerField(
        help_text="Content version number (Rule P5: increments only on content changes)",
    )

    is_deleted = django.db.models.BooleanField(
        default=False,
        db_index=True,
        help_text="Soft delete flag",
    )

    is_current = django.db.models.BooleanField(
        default=True,
        db_index=True,
        help_text="True for current filesystem state (Rule P3)",
    )

    # TreeNode provides: parent (previous state), tree_depth, tree_path, tree_ordering

    class Meta:
        constraints = [
            # Rule P4: Only one active path per (corpus, path) tuple
            django.db.models.UniqueConstraint(
                fields=["corpus", "path"],
                condition=django.db.models.Q(is_current=True, is_deleted=False),
                name="unique_active_path_per_corpus",
            ),
        ]
        indexes = [
            django.db.models.Index(fields=["corpus", "is_current", "is_deleted"]),
            django.db.models.Index(fields=["document", "corpus"]),
            django.db.models.Index(fields=["path"]),
            django.db.models.Index(fields=["version_number"]),
            django.db.models.Index(fields=["creator"]),
            django.db.models.Index(fields=["created"]),
        ]
        permissions = (
            ("create_documentpath", "create DocumentPath"),
            ("read_documentpath", "read DocumentPath"),
            ("update_documentpath", "update DocumentPath"),
            ("remove_documentpath", "delete DocumentPath"),
        )

    def __str__(self):
        status = "deleted" if self.is_deleted else "active"
        current = "current" if self.is_current else "historical"
        return f"DocumentPath(doc={self.document_id}, path={self.path}, v{self.version_number}, {status}, {current})"


# Model for Django Guardian permissions
class DocumentPathUserObjectPermission(UserObjectPermissionBase):
    content_object = django.db.models.ForeignKey(
        "DocumentPath", on_delete=django.db.models.CASCADE
    )


# Model for Django Guardian permissions
class DocumentPathGroupObjectPermission(GroupObjectPermissionBase):
    content_object = django.db.models.ForeignKey(
        "DocumentPath", on_delete=django.db.models.CASCADE
    )


# -------------------- DocumentSummaryRevision -------------------- #


class DocumentSummaryRevision(django.db.models.Model):
    """Append-only history for Document markdown summaries, scoped to corpus."""

    document = django.db.models.ForeignKey(
        "documents.Document",
        on_delete=django.db.models.CASCADE,
        related_name="summary_revisions",
    )

    corpus = django.db.models.ForeignKey(
        "corpuses.Corpus",
        on_delete=django.db.models.CASCADE,
        related_name="document_summary_revisions",
    )

    author = django.db.models.ForeignKey(
        get_user_model(),
        on_delete=django.db.models.SET_NULL,
        null=True,
        related_name="document_summary_revisions",
    )

    version = django.db.models.PositiveIntegerField()
    diff = django.db.models.TextField(blank=True)
    snapshot = django.db.models.TextField(null=True, blank=True)
    checksum_base = django.db.models.CharField(max_length=64, blank=True)
    checksum_full = django.db.models.CharField(max_length=64, blank=True)
    created = django.db.models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        unique_together = ("document", "corpus", "version")
        ordering = ("document_id", "corpus_id", "version")
        indexes = [
            django.db.models.Index(fields=["document", "corpus"]),
            django.db.models.Index(fields=["author"]),
            django.db.models.Index(fields=["created"]),
        ]

    def __str__(self):
        return (
            f"DocumentSummaryRevision(document_id={self.document_id}, v={self.version})"
        )


# -------------------- PipelineSettings (Singleton) -------------------- #


class PipelineSettings(django.db.models.Model):
    """
    Singleton model for configurable document processing pipeline settings.

    This model stores runtime-configurable settings for the document ingestion
    pipeline, allowing superusers to change parsers, embedders, and thumbnailers
    without code deployment.

    The singleton instance is created via migration and cannot be deleted.
    Only superusers can modify these settings via the GraphQL API.

    ⚠️  CRITICAL: SECRET_KEY Dependency
    ----------------------------------
    Encrypted secrets (API keys, credentials) are tied to Django's SECRET_KEY.
    If you rotate SECRET_KEY, ALL encrypted secrets become PERMANENTLY UNRECOVERABLE.

    Before rotating SECRET_KEY:
    1. Export secrets via Django shell: PipelineSettings.get_instance().get_secrets()
    2. Store exported secrets securely
    3. After rotation, re-import via: instance.set_secrets(exported_secrets); instance.save()

    Settings Structure:
        preferred_parsers: Dict mapping MIME types to parser class paths
            Example: {"application/pdf": "opencontractserver.pipeline.parsers.docling_parser_rest.DoclingParser"}

        preferred_embedders: Dict mapping MIME types to embedder class paths
            Example: {"application/pdf":
                "opencontractserver.pipeline.embedders...MicroserviceEmbedder"}

        preferred_thumbnailers: Dict mapping MIME types to thumbnailer class paths
            Example: {"application/pdf":
                "opencontractserver.pipeline.thumbnailers...PdfThumbnailGenerator"}

        parser_kwargs: Dict mapping parser class paths to their configuration kwargs
            Example: {"opencontractserver.pipeline.parsers.docling_parser_rest.DoclingParser": {"force_ocr": false}}

        component_settings: Dict mapping component class paths to their settings overrides
            Example: {"opencontractserver.pipeline.embedders.MicroserviceEmbedder": {"timeout": 30}}

        default_embedder: Default embedder class path when no MIME-specific embedder is found

    Security - Encrypted Secrets Storage:
        Sensitive values (API keys, credentials) can be stored in the `encrypted_secrets`
        field, which is encrypted at rest using Fernet symmetric encryption. The encryption
        key is derived from Django's SECRET_KEY.

        Structure of encrypted_secrets (after decryption):
            {
                "component_class_path": {
                    "api_key": "...",
                    "secret_token": "...",
                }
            }

        Use set_secrets() and get_secrets() methods to access encrypted data.
        The GraphQL mutations handle encryption/decryption transparently.
    """

    # Preferred parsers per MIME type
    preferred_parsers = NullableJSONField(
        default=dict,
        blank=True,
        help_text="Mapping of MIME types to preferred parser class paths",
    )

    # Preferred embedders per MIME type
    preferred_embedders = NullableJSONField(
        default=dict,
        blank=True,
        help_text="Mapping of MIME types to preferred embedder class paths",
    )

    # Preferred thumbnailers per MIME type
    preferred_thumbnailers = NullableJSONField(
        default=dict,
        blank=True,
        help_text="Mapping of MIME types to preferred thumbnailer class paths",
    )

    # Parser-specific kwargs
    parser_kwargs = NullableJSONField(
        default=dict,
        blank=True,
        help_text="Mapping of parser class paths to configuration kwargs",
    )

    # Component-specific settings overrides
    component_settings = NullableJSONField(
        default=dict,
        blank=True,
        help_text="Mapping of component class paths to settings overrides",
    )

    # Default embedder when no MIME-specific one is found
    default_embedder = django.db.models.CharField(
        max_length=512,
        blank=True,
        default="",
        help_text="Default embedder class path",
    )

    # Encrypted secrets storage (API keys, tokens, credentials)
    # Stored as Fernet-encrypted JSON blob
    encrypted_secrets = django.db.models.BinaryField(
        blank=True,
        null=True,
        help_text="Encrypted storage for sensitive configuration (API keys, credentials)",
    )

    # Audit fields
    modified = django.db.models.DateTimeField(auto_now=True, db_index=True)
    modified_by = django.db.models.ForeignKey(
        get_user_model(),
        on_delete=django.db.models.SET_NULL,
        null=True,
        blank=True,
        related_name="pipeline_settings_modifications",
        help_text="User who last modified these settings",
    )

    class Meta:
        verbose_name = "Pipeline Settings"
        verbose_name_plural = "Pipeline Settings"
        constraints = [
            django.db.models.CheckConstraint(
                condition=django.db.models.Q(pk=1),
                name="pipeline_settings_singleton_pk",
            ),
        ]

    def __str__(self):
        return "PipelineSettings (Singleton)"

    # Cache settings
    CACHE_KEY = "pipeline_settings_singleton"

    @classmethod
    def _get_cache_ttl(cls) -> int:
        """Get cache TTL from Django settings."""
        from django.conf import settings as django_settings

        return getattr(django_settings, "PIPELINE_SETTINGS_CACHE_TTL_SECONDS", 300)

    @classmethod
    def _get_encryption_salt_length(cls) -> int:
        """Get encryption salt length from Django settings."""
        from django.conf import settings as django_settings

        return getattr(django_settings, "PIPELINE_SETTINGS_ENCRYPTION_SALT_LENGTH", 16)

    @classmethod
    def _get_encryption_iterations(cls) -> int:
        """Get PBKDF2 iteration count from Django settings."""
        from django.conf import settings as django_settings

        return getattr(
            django_settings, "PIPELINE_SETTINGS_ENCRYPTION_ITERATIONS", 480000
        )

    @classmethod
    def _get_max_secret_size(cls) -> int:
        """Get maximum secret payload size from Django settings."""
        from django.conf import settings as django_settings

        return getattr(
            django_settings, "PIPELINE_SETTINGS_MAX_SECRET_SIZE_BYTES", 10240
        )

    def save(self, *args, **kwargs):
        """Ensure singleton pattern and invalidate cache on save."""
        from django.db import transaction

        if not self.pk and PipelineSettings.objects.exists():
            raise ValidationError(
                "PipelineSettings is a singleton. Use PipelineSettings.get_instance() instead."
            )
        super().save(*args, **kwargs)
        # Eagerly invalidate cache after save for immediate consistency
        # (required in autocommit mode and Django TestCase which never commits).
        self._invalidate_cache()
        # Also invalidate on commit in case save() runs inside a larger
        # transaction that might roll back and be retried.
        transaction.on_commit(lambda: self._invalidate_cache())

    def delete(self, *args, **kwargs):
        """Prevent deletion of the singleton instance."""
        raise ValidationError("PipelineSettings singleton cannot be deleted.")

    @classmethod
    def _invalidate_cache(cls) -> None:
        """Invalidate the cached instance."""
        from django.core.cache import cache

        cache.delete(cls.CACHE_KEY)

    @classmethod
    def get_instance(cls, use_cache: bool = True) -> "PipelineSettings":
        """
        Get the singleton PipelineSettings instance.

        Uses Django's cache framework with a 5-minute TTL to reduce database
        queries during document processing.

        If no instance exists (shouldn't happen after migration), creates one
        with default values from Django settings.

        Args:
            use_cache: If True (default), use cached instance. Set to False
                to bypass cache and get fresh data from database.

        Returns:
            PipelineSettings: The singleton instance.
        """
        from django.conf import settings as django_settings
        from django.core.cache import cache
        from django.db import transaction

        # Try cache first (if enabled)
        if use_cache:
            cached = cache.get(cls.CACHE_KEY)
            if cached is not None:
                return cached

        # Get from database with atomic transaction to prevent race conditions
        # during concurrent startup or migration.
        with transaction.atomic():
            instance, created = cls.objects.select_related("modified_by").get_or_create(
                pk=1,
                defaults={
                    "preferred_parsers": getattr(
                        django_settings, "PREFERRED_PARSERS", {}
                    ),
                    "preferred_embedders": getattr(
                        django_settings, "PREFERRED_EMBEDDERS", {}
                    ),
                    "preferred_thumbnailers": {},  # No default in Django settings
                    "parser_kwargs": getattr(django_settings, "PARSER_KWARGS", {}),
                    "component_settings": getattr(
                        django_settings, "PIPELINE_SETTINGS", {}
                    ),
                    "default_embedder": getattr(
                        django_settings, "DEFAULT_EMBEDDER", ""
                    ),
                },
            )

        # Cache the instance
        if use_cache:
            cache.set(cls.CACHE_KEY, instance, cls._get_cache_ttl())

        return instance

    def get_preferred_parser(self, mimetype: str) -> str | None:
        """
        Get the preferred parser class path for a MIME type.

        Database is the single source of truth at runtime.
        Initial values are populated from Django settings via get_instance().

        Args:
            mimetype: The MIME type (e.g., "application/pdf")

        Returns:
            Parser class path or None if not found.
        """
        if self.preferred_parsers and mimetype in self.preferred_parsers:
            return self.preferred_parsers[mimetype]
        return None

    def get_preferred_embedder(self, mimetype: str) -> str | None:
        """
        Get the preferred embedder class path for a MIME type.

        Database is the single source of truth at runtime.
        Initial values are populated from Django settings via get_instance().

        Args:
            mimetype: The MIME type (e.g., "application/pdf")

        Returns:
            Embedder class path or None if not found.
        """
        if self.preferred_embedders and mimetype in self.preferred_embedders:
            return self.preferred_embedders[mimetype]
        return None

    def get_preferred_thumbnailer(self, mimetype: str) -> str | None:
        """
        Get the preferred thumbnailer class path for a MIME type.

        Database is the single source of truth at runtime.

        Args:
            mimetype: The MIME type (e.g., "application/pdf")

        Returns:
            Thumbnailer class path or None if not found.
        """
        if self.preferred_thumbnailers and mimetype in self.preferred_thumbnailers:
            return self.preferred_thumbnailers[mimetype]
        return None

    def get_parser_kwargs(self, parser_class_path: str) -> dict:
        """
        Get configuration kwargs for a specific parser.

        Database is the single source of truth at runtime.
        Initial values are populated from Django settings via get_instance().

        Args:
            parser_class_path: Full class path of the parser

        Returns:
            Dict of kwargs for the parser.
        """
        if self.parser_kwargs and parser_class_path in self.parser_kwargs:
            return self.parser_kwargs[parser_class_path]
        return {}

    def get_component_settings(self, component_class_path: str) -> dict:
        """
        Get settings overrides for a specific component from database.

        This method only returns database settings, not Django settings fallback.
        The Django settings fallback (with proper simple name vs full path
        precedence) is handled by PipelineComponentBase.get_component_settings().

        Args:
            component_class_path: Full class path of the component

        Returns:
            Dict of settings for the component from database, or empty dict.
        """
        # Only return database settings - no Django fallback here
        # The fallback chain is handled by PipelineComponentBase
        if self.component_settings and component_class_path in self.component_settings:
            return self.component_settings[component_class_path]

        return {}

    def get_default_embedder(self) -> str:
        """
        Get the default embedder class path.

        Database is the single source of truth at runtime.
        Initial values are populated from Django settings via get_instance().

        Returns:
            Default embedder class path.
        """
        return self.default_embedder or ""

    # =====================================================================
    # Encrypted Secrets Management
    # =====================================================================

    @classmethod
    def _derive_key(cls, salt: bytes) -> bytes:
        """
        Derive encryption key from Django SECRET_KEY using PBKDF2.

        Uses PBKDF2-HMAC-SHA256 with high iteration count as recommended
        by OWASP for secure key derivation.

        Args:
            salt: Random salt bytes (16 bytes recommended)

        Returns:
            32-byte derived key suitable for Fernet
        """
        import base64
        import hashlib

        from django.conf import settings as django_settings

        # Use PBKDF2 with SHA256 for secure key derivation
        key = hashlib.pbkdf2_hmac(
            "sha256",
            django_settings.SECRET_KEY.encode(),
            salt,
            cls._get_encryption_iterations(),
            dklen=32,
        )
        return base64.urlsafe_b64encode(key)

    def get_secrets(self) -> dict:
        """
        Get the decrypted secrets dictionary.

        Returns:
            Dict mapping component class paths to their secrets:
            {
                "opencontractserver.pipeline.parsers.llamaparse_parser.LlamaParseParser": {
                    "api_key": "...",
                },
                ...
            }
        """
        import json
        import logging

        from cryptography.fernet import Fernet, InvalidToken

        logger = logging.getLogger(__name__)

        if not self.encrypted_secrets:
            return {}

        try:
            raw_data = bytes(self.encrypted_secrets)

            # Extract salt and ciphertext
            salt_length = self._get_encryption_salt_length()
            if len(raw_data) < salt_length:
                logger.error(
                    "PipelineSettings: encrypted_secrets too short to contain salt"
                )
                return {}

            salt = raw_data[:salt_length]
            ciphertext = raw_data[salt_length:]

            # Derive key from salt and decrypt
            key = self._derive_key(salt)
            fernet = Fernet(key)
            decrypted = fernet.decrypt(ciphertext)
            return json.loads(decrypted.decode("utf-8"))

        except InvalidToken:
            logger.critical(
                "PipelineSettings: Failed to decrypt secrets - InvalidToken. "
                "This may indicate SECRET_KEY has changed. Secrets are unrecoverable "
                "without the original SECRET_KEY."
            )
            return {}
        except json.JSONDecodeError as e:
            logger.error(
                f"PipelineSettings: Decrypted secrets contain invalid JSON: {e}"
            )
            return {}
        except Exception as e:
            logger.critical(
                f"PipelineSettings: Unexpected error decrypting secrets: {e}. "
                "Secrets may be corrupted or SECRET_KEY may have changed."
            )
            return {}

    def set_secrets(self, secrets: dict) -> None:
        """
        Encrypt and store secrets.

        Args:
            secrets: Dict mapping component class paths to their secrets:
            {
                "opencontractserver.pipeline.parsers.llamaparse_parser.LlamaParseParser": {
                    "api_key": "...",
                },
            }

        Raises:
            ValueError: If secrets payload exceeds size limit
        """
        import json
        import os

        from cryptography.fernet import Fernet

        json_bytes = json.dumps(secrets).encode("utf-8")

        # Validate size
        max_size = self._get_max_secret_size()
        if len(json_bytes) > max_size:
            raise ValueError(
                f"Secrets payload exceeds maximum size of {max_size} bytes"
            )

        # Generate random salt for this encryption
        salt = os.urandom(self._get_encryption_salt_length())

        # Derive key and encrypt
        key = self._derive_key(salt)
        fernet = Fernet(key)
        ciphertext = fernet.encrypt(json_bytes)

        # Store salt + ciphertext
        self.encrypted_secrets = salt + ciphertext

    def update_secrets(self, component_path: str, secret_values: dict) -> None:
        """
        Update secrets for a specific component (merge with existing).

        Args:
            component_path: Full class path of the component
            secret_values: Dict of secret key-value pairs to set
        """
        secrets = self.get_secrets()
        if component_path not in secrets:
            secrets[component_path] = {}
        secrets[component_path].update(secret_values)
        self.set_secrets(secrets)

    def get_component_secrets(self, component_path: str) -> dict:
        """
        Get secrets for a specific component.

        Args:
            component_path: Full class path of the component

        Returns:
            Dict of secret key-value pairs for the component.
        """
        secrets = self.get_secrets()
        return secrets.get(component_path, {})

    def delete_component_secrets(self, component_path: str) -> None:
        """
        Delete all secrets for a specific component.

        Args:
            component_path: Full class path of the component
        """
        secrets = self.get_secrets()
        if component_path in secrets:
            del secrets[component_path]
            self.set_secrets(secrets)

    def get_full_component_settings(self, component_class_path: str) -> dict:
        """
        Get full settings for a component, merging non-sensitive settings
        with decrypted secrets.

        This is the method pipeline components should use to get their
        complete configuration.

        Args:
            component_class_path: Full class path of the component

        Returns:
            Dict of all settings (non-sensitive + secrets) for the component.
        """
        # Get non-sensitive settings
        settings = dict(self.get_component_settings(component_class_path))

        # Merge with secrets (secrets take precedence)
        secrets = self.get_component_secrets(component_class_path)
        settings.update(secrets)

        return settings

    # =====================================================================
    # Component Schema and Validation Methods
    # =====================================================================

    def get_component_schema(self, component_path: str) -> dict:
        """
        Get the settings schema for a specific component.

        This is useful for the admin UI to dynamically generate configuration
        forms based on what a component requires.

        Args:
            component_path: Full class path or simple name of the component

        Returns:
            Dict mapping setting names to their schema information:
            {
                "api_key": {
                    "type": "secret",
                    "required": True,
                    "default": "",
                    "description": "API key",
                    "python_type": "str",
                    "has_value": True,  # Whether a value is currently configured
                },
                ...
            }
        """
        import logging

        from opencontractserver.pipeline.base.settings_schema import (
            get_settings_schema,
        )
        from opencontractserver.pipeline.registry import get_registry

        logger = logging.getLogger(__name__)
        registry = get_registry()

        # Try to find component by full path or simple name
        component_def = registry.get_by_class_name(component_path)
        if not component_def:
            component_def = registry.get_by_name(component_path)

        if not component_def or not component_def.component_class:
            logger.warning(f"Component not found: {component_path}")
            return {}

        schema = get_settings_schema(component_def.component_class)

        # Augment schema with current value status
        current_settings = self.get_full_component_settings(component_def.class_name)
        for setting_name, info in schema.items():
            value = current_settings.get(setting_name)
            # For secrets, only indicate whether a value exists, never the value itself
            if info.get("type") == "secret":
                info["has_value"] = value is not None and value != ""
                info["current_value"] = None  # Never expose secret values
            else:
                info["has_value"] = value is not None
                info["current_value"] = value

        return schema

    def validate_all_components(self) -> dict[str, list[str]]:
        """
        Validate that all registered components have their required settings configured.

        Scans all parsers, embedders, thumbnailers, and post-processors,
        checks their Settings schemas, and reports any missing required settings.

        Returns:
            Dict mapping component class paths to lists of missing settings:
            {
                "opencontractserver.pipeline.parsers.llamaparse_parser.LlamaParseParser": [
                    "api_key"
                ],
                ...
            }
            Empty dict if all required settings are configured.
        """
        import logging

        from opencontractserver.pipeline.base.settings_schema import (
            get_required_settings,
            get_settings_schema,
        )
        from opencontractserver.pipeline.registry import get_registry

        logger = logging.getLogger(__name__)
        registry = get_registry()
        missing_by_component: dict[str, list[str]] = {}

        # Collect all components
        all_components = []
        all_components.extend(registry.parsers)
        all_components.extend(registry.embedders)
        all_components.extend(registry.thumbnailers)
        all_components.extend(registry.post_processors)

        for component_def in all_components:
            component_class = component_def.component_class
            if component_class is None:
                continue

            class_path = component_def.class_name
            schema = get_settings_schema(component_class)

            if not schema:
                # Component has no Settings schema, skip
                continue

            required_settings = get_required_settings(component_class)
            if not required_settings:
                # No required settings, skip
                continue

            # Get current settings from DB
            current_settings = self.get_full_component_settings(class_path)

            missing = []
            for setting_name in required_settings:
                value = current_settings.get(setting_name)
                if value is None or (isinstance(value, str) and not value.strip()):
                    missing.append(setting_name)

            if missing:
                missing_by_component[class_path] = missing
                logger.warning(
                    f"Component '{class_path}' is missing required settings: "
                    f"{', '.join(missing)}"
                )

        return missing_by_component

    def get_all_component_schemas(self) -> dict[str, dict]:
        """
        Get settings schemas for all registered components.

        Returns:
            Dict mapping component class paths to their schemas:
            {
                "opencontractserver.pipeline.parsers.llamaparse_parser.LlamaParseParser": {
                    "api_key": {...},
                    "num_workers": {...},
                },
                ...
            }
        """
        from opencontractserver.pipeline.base.settings_schema import (
            get_settings_schema,
        )
        from opencontractserver.pipeline.registry import get_registry

        registry = get_registry()
        schemas: dict[str, dict] = {}

        all_components = []
        all_components.extend(registry.parsers)
        all_components.extend(registry.embedders)
        all_components.extend(registry.thumbnailers)
        all_components.extend(registry.post_processors)

        for component_def in all_components:
            if component_def.component_class is None:
                continue

            schema = get_settings_schema(component_def.component_class)
            if schema:
                # Augment with current value status
                current_settings = self.get_full_component_settings(
                    component_def.class_name
                )
                for setting_name, info in schema.items():
                    value = current_settings.get(setting_name)
                    if info.get("type") == "secret":
                        info["has_value"] = value is not None and value != ""
                        info["current_value"] = None
                    else:
                        info["has_value"] = value is not None
                        info["current_value"] = value

                schemas[component_def.class_name] = schema

        return schemas
