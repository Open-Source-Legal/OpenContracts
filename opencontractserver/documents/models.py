import functools

import django
from django.core.exceptions import ValidationError
from guardian.models import GroupObjectPermissionBase, UserObjectPermissionBase
from pgvector.django import VectorField

from opencontractserver.shared.defaults import jsonfield_default_value
from opencontractserver.shared.fields import NullableJSONField
from opencontractserver.shared.Models import BaseOCModel
from opencontractserver.shared.utils import calc_oc_file_path


class Document(BaseOCModel):
    """
    Document

    Documents inherit permissions from their parent corpus.
    """

    # Key fields
    title = django.db.models.CharField(max_length=1024, null=True, blank=True)
    description = django.db.models.TextField(null=True, blank=True)
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

    processing_started = django.db.models.DateTimeField(null=True)
    processing_finished = django.db.models.DateTimeField(null=True)

    # Vector for vector search
    embedding = VectorField(dimensions=384, null=True, blank=True)
    description_embedding = VectorField(dimensions=384, null=True, blank=True)

    # This flag enables permission inheritance from parent corpus
    INHERITS_CORPUS_PERMISSIONS = True

    class Meta:
        permissions = (
            ("permission_document", "permission document"),
            ("publish_document", "publish document"),
            ("create_document", "create document"),
            ("read_document", "read document"),
            ("update_document", "update document"),
            ("remove_document", "delete document"),
        )
        indexes = [
            django.db.models.Index(fields=["title"]),
            django.db.models.Index(fields=["page_count"]),
            django.db.models.Index(fields=["creator"]),
            django.db.models.Index(fields=["created"]),
            django.db.models.Index(fields=["modified"]),
        ]

    def __str__(self):
        """
        String representation method
        :return:
        """
        return f"Doc ({self.id}) - {self.description}".encode("utf-8", "ignore").decode(
            "utf-8", "ignore"
        )


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

    INHERITS_CORPUS_PERMISSIONS = True

    class Meta:
        permissions = (
            ("permission_documentrelationship", "permission document relationship"),
            ("publish_documentrelationship", "publish document relationship"),
            ("create_documentrelationship", "create document relationship"),
            ("read_documentrelationship", "read document relationship"),
            ("update_documentrelationship", "update document relationship"),
            ("remove_documentrelationship", "delete document relationship"),
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
