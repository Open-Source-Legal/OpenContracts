import difflib
import functools
import hashlib
import uuid

import django
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
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
            # TODO: Implement diff reconstruction if needed
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
            # Reconstruct from diffs if no snapshot
            original_content = ""
            # TODO: Implement diff reconstruction if needed
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

    class Meta:
        permissions = (
            ("permission_documentrelationship", "permission document relationship"),
            ("publish_documentrelationship", "publish document relationship"),
            ("create_documentrelationship", "create document relationship"),
            ("read_documentrelationship", "read document relationship"),
            ("update_documentrelationship", "update document relationship"),
            ("remove_documentrelationship", "delete document relationship"),
            ("comment_documentrelationship", "comment document relationship"),
        )
        indexes = [
            django.db.models.Index(fields=["source_document"]),
            django.db.models.Index(fields=["target_document"]),
            django.db.models.Index(fields=["relationship_type"]),
            django.db.models.Index(fields=["annotation_label"]),
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
        """Validate that annotation_label is present for RELATIONSHIP type."""
        super().clean()
        if self.relationship_type == "RELATIONSHIP" and not self.annotation_label:
            raise ValidationError(
                {
                    "annotation_label": "Annotation label is required for relationship type RELATIONSHIP."
                }
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


# Model for Django Guardian permissions
class DocumentRelationshipUserObjectPermission(UserObjectPermissionBase):
    content_object = django.db.models.ForeignKey(
        "DocumentRelationship", on_delete=django.db.models.CASCADE
    )


# Model for Django Guardian permissions
class DocumentRelationshipGroupObjectPermission(GroupObjectPermissionBase):
    content_object = django.db.models.ForeignKey(
        "DocumentRelationship", on_delete=django.db.models.CASCADE
    )


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
