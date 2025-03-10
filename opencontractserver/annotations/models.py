import uuid
from typing import Optional

import django
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

# Switching from Django-tree-queries to django-cte as it
# appears that django-tree-query has performance issues for large tables.
# See https://github.com/feincms/django-tree-queries/issues/77
# This will become an issue for annotations in particular. Since annotations will
# have a simple structure and query anyway, using django-cte here. Can migrate models
# using django-tree-queries down the road but shouldn't affect each other on
# separate models.
from django_cte import CTEManager, CTEQuerySet
from guardian.models import GroupObjectPermissionBase, UserObjectPermissionBase
from pgvector.django import VectorField

from opencontractserver.shared.defaults import (
    empty_bounding_box,
    jsonfield_default_value,
    jsonfield_empty_array,
)
from opencontractserver.shared.fields import NullableJSONField
from opencontractserver.shared.Models import BaseOCModel
from opencontractserver.shared.QuerySets import PermissionQuerySet
from opencontractserver.shared.utils import calc_oc_file_path

User = get_user_model()

# TODO - can we use the Python enum in data_types.py to drive choices
RELATIONSHIP_LABEL = "RELATIONSHIP_LABEL"
DOC_TYPE_LABEL = "DOC_TYPE_LABEL"
TOKEN_LABEL = "TOKEN_LABEL"
METADATA_LABEL = "METADATA_LABEL"
SPAN_LABEL = "SPAN_LABEL"

LABEL_TYPES = [
    (RELATIONSHIP_LABEL, _("Relationship label.")),
    (DOC_TYPE_LABEL, _("Document-level type label.")),
    (TOKEN_LABEL, _("Token-level labels for token-based labeling")),
    (SPAN_LABEL, _("Span labels for span-based labeling")),
    (METADATA_LABEL, _("Metadata label for manual entry field")),
]


class AnnotationLabel(BaseOCModel):

    label_type = django.db.models.CharField(
        max_length=128,
        blank=False,
        null=False,
        choices=LABEL_TYPES,
        default=TOKEN_LABEL,
    )

    # If an analyzer requires a specific label, we want to track this so we can ensure we don't install copies of it
    # over and over again.
    analyzer = django.db.models.ForeignKey(
        "analyzer.Analyzer",
        null=True,
        blank=True,
        related_name="annotation_labels",
        on_delete=django.db.models.SET_NULL,
    )

    # If this is meant to be a 'built-in' label and be used across corpuses without being explicitly added to a
    # labelset, set this value to True
    read_only = django.db.models.BooleanField(default=False)

    color = django.db.models.CharField(
        max_length=12, blank=False, null=False, default="#05313d"
    )
    description = django.db.models.TextField(null=False, default="")
    icon = django.db.models.CharField(
        max_length=128, blank=False, null=False, default="tags"
    )
    text = django.db.models.CharField(
        max_length=128, blank=False, null=False, default="Text Label"
    )

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
            ("permission_annotationlabel", "permission Annotationlabel"),
            ("publish_annotationlabel", "publish Annotationlabel"),
            ("create_annotationlabel", "create Annotationlabel"),
            ("read_annotationlabel", "read Annotationlabel"),
            ("update_annotationlabel", "update Annotationlabel"),
            ("remove_annotationlabel", "delete Annotationlabel"),
        )

        indexes = [
            django.db.models.Index(fields=["label_type"]),
            django.db.models.Index(fields=["analyzer"]),
            django.db.models.Index(fields=["text"]),
            django.db.models.Index(fields=["creator"]),
            django.db.models.Index(fields=["created"]),
            django.db.models.Index(fields=["modified"]),
        ]

        constraints = [
            django.db.models.UniqueConstraint(
                fields=["analyzer", "text", "creator", "label_type"],
                name="Only install one label of given name for each analyzer_id PER user (no duplicates)",
            )
        ]

    # Override save to update modified on save
    def save(self, *args, **kwargs):
        """On save, update timestamps"""
        if not self.pk:
            self.created = timezone.now()
        self.modified = timezone.now()

        return super().save(*args, **kwargs)


# Model for Django Guardian permissions... trying to improve performance...
class AnnotationLabelUserObjectPermission(UserObjectPermissionBase):
    content_object = django.db.models.ForeignKey(
        "AnnotationLabel", on_delete=django.db.models.CASCADE
    )
    # enabled = False


# Model for Django Guardian permissions... trying to improve performance...
class AnnotationLabelGroupObjectPermission(GroupObjectPermissionBase):
    content_object = django.db.models.ForeignKey(
        "AnnotationLabel", on_delete=django.db.models.CASCADE
    )
    # enabled = False


class Relationship(BaseOCModel):
    relationship_label = django.db.models.ForeignKey(
        "AnnotationLabel",
        null=True,
        on_delete=django.db.models.CASCADE,
        related_name="relationships",
    )
    corpus = django.db.models.ForeignKey(
        "corpuses.Corpus",
        null=True,
        on_delete=django.db.models.CASCADE,
        related_name="relationships",
    )
    document = django.db.models.ForeignKey(
        "documents.Document",
        related_name="relationships",
        null=False,
        on_delete=django.db.models.CASCADE,
    )
    source_annotations = django.db.models.ManyToManyField(
        "annotations.Annotation",
        related_name="source_node_in_relationships",
        related_query_name="source_node_in_relationship",
        blank=True,
    )
    target_annotations = django.db.models.ManyToManyField(
        "annotations.Annotation",
        related_name="target_node_in_relationships",
        related_query_name="target_node_in_relationship",
        blank=True,
    )

    # If relationshi was created by an analyzer as part of an analysis, we want to track
    # this.
    analyzer = django.db.models.ForeignKey(
        "analyzer.Analyzer", on_delete=django.db.models.SET_NULL, null=True, blank=True
    )

    # If this annotation was created as part of an analysis... track that.
    # TODO - ensure we actually import relationships (and this attribute) from analyzers
    analysis = django.db.models.ForeignKey(
        "analyzer.Analysis",
        null=True,
        blank=True,
        on_delete=django.db.models.CASCADE,
        related_name="relationships",
    )

    # Some relationships are structural and not corpus-specific
    structural = django.db.models.BooleanField(default=False)

    # Sharing
    is_public = django.db.models.BooleanField(default=False)
    creator = django.db.models.ForeignKey(
        get_user_model(),
        on_delete=django.db.models.CASCADE,
        null=False,
        default=1,
    )

    # Timing variables
    created = django.db.models.DateTimeField(
        "Creation Date and Time", default=timezone.now
    )
    modified = django.db.models.DateTimeField(default=timezone.now, blank=True)

    class Meta:
        permissions = (
            ("permission_relationship", "permission relationship"),
            ("create_relationship", "create relationship"),
            ("read_relationship", "read relationship"),
            ("update_relationship", "update relationship"),
            ("remove_relationship", "delete relationship"),
            ("publish_relationship", "publish relationship"),
        )

        indexes = [
            django.db.models.Index(fields=["relationship_label"]),
            django.db.models.Index(fields=["corpus"]),
            django.db.models.Index(fields=["document"]),
            django.db.models.Index(fields=["analyzer"]),
            django.db.models.Index(fields=["creator"]),
            django.db.models.Index(fields=["created"]),
            django.db.models.Index(fields=["modified"]),
        ]

    # Override save to update modified on save
    def save(self, *args, **kwargs):
        """On save, update timestamps"""
        if not self.pk:
            self.created = timezone.now()
        self.modified = timezone.now()

        return super().save(*args, **kwargs)


# Model for Django Guardian permissions... trying to improve performance...
class RelationshipUserObjectPermission(UserObjectPermissionBase):
    content_object = django.db.models.ForeignKey(
        "Relationship", on_delete=django.db.models.CASCADE
    )
    # enabled = False


# Model for Django Guardian permissions... trying to improve performance...
class RelationshipGroupObjectPermission(GroupObjectPermissionBase):
    content_object = django.db.models.ForeignKey(
        "Relationship", on_delete=django.db.models.CASCADE
    )
    # enabled = False


class AnnotationQuerySet(CTEQuerySet, PermissionQuerySet):
    """
    Custom QuerySet for the Annotation model combining CTEQuerySet and PermissionQuerySet functionalities.
    """

    pass


class AnnotationManager(CTEManager.from_queryset(AnnotationQuerySet)):
    """
    Custom Manager for the Annotation model that uses the combined AnnotationQuerySet
    and includes permissioning methods.
    """

    def get_queryset(self) -> AnnotationQuerySet:
        """
        Returns the custom AnnotationQuerySet.
        """
        return AnnotationQuerySet(self.model, using=self._db)

    def for_user(
        self, user: User, perm: str, extra_conditions: Optional[Q] = None
    ) -> AnnotationQuerySet:
        """
        Filters the queryset based on user permissions.

        Args:
            user: The user for whom permissions are checked.
            perm: The permission string.
            extra_conditions: Additional conditions for filtering.

        Returns:
            A filtered AnnotationQuerySet.
        """
        # This method should now use filter_queryset_by_permission to ensure
        # consistent permission handling that respects INHERITS_CORPUS_PERMISSIONS
        from opencontractserver.utils.permissioning import filter_queryset_by_permission

        queryset = self.get_queryset()

        # Apply extra conditions if provided
        if extra_conditions:
            queryset = queryset.filter(extra_conditions)

        # Use the centralized permission filtering
        return filter_queryset_by_permission(queryset, user, perm)


class Annotation(BaseOCModel):
    """
    The Annotation model represents annotations within documents.

    Annotations inherit permissions from their parent corpus.
    """

    # Use the custom manager that combines permissioning and CTE capabilities
    objects = AnnotationManager()

    page = django.db.models.IntegerField(default=1, blank=False)
    raw_text = django.db.models.TextField(null=True, blank=True)
    tokens_jsons = NullableJSONField(
        default=jsonfield_empty_array, null=True, blank=True
    )
    bounding_box = NullableJSONField(default=empty_bounding_box, null=True)
    json = NullableJSONField(default=jsonfield_default_value, null=False)

    # New parent field for hierarchical relationships
    parent = django.db.models.ForeignKey(
        "self",
        null=True,
        blank=True,
        related_name="children",
        on_delete=django.db.models.CASCADE,
    )

    # This is kind of duplicative of the AnnotationLabel label_type, BUT,
    # it makes more sense here. Slowly going to transition to this
    annotation_type = django.db.models.CharField(
        max_length=128,
        blank=False,
        null=False,
        choices=LABEL_TYPES,
        default=TOKEN_LABEL,
    )

    annotation_label = django.db.models.ForeignKey(
        "annotations.AnnotationLabel", null=True, on_delete=django.db.models.CASCADE
    )
    document = django.db.models.ForeignKey(
        "documents.Document",
        null=False,
        on_delete=django.db.models.CASCADE,
        related_name="doc_annotations",
        related_query_name="doc_annotation",
    )
    corpus = django.db.models.ForeignKey(
        "corpuses.Corpus",
        null=True,
        blank=True,
        on_delete=django.db.models.SET_NULL,
        related_name="annotations",
    )

    # Vector for vector search
    embedding = VectorField(dimensions=384, null=True)

    # If this annotation was created as part of an analysis... track that.
    analysis = django.db.models.ForeignKey(
        "analyzer.Analysis",
        null=True,
        blank=True,
        on_delete=django.db.models.CASCADE,
        related_name="annotations",
    )

    # Mark structural / layout annotations explicitly.
    structural = django.db.models.BooleanField(default=False)

    # Sharing
    is_public = django.db.models.BooleanField(default=False)
    creator = django.db.models.ForeignKey(
        get_user_model(),
        on_delete=django.db.models.CASCADE,
        null=False,
        default=1,
    )

    # Timing variables
    created = django.db.models.DateTimeField(
        "Creation Date and Time", default=timezone.now
    )
    modified = django.db.models.DateTimeField(default=timezone.now, blank=True)

    # Flag to indicate that Annotations inherit permissions from their parent corpus
    INHERITS_CORPUS_PERMISSIONS = True

    class Meta:
        permissions = (
            ("permission_annotation", "permission annotation"),
            ("create_annotation", "create annotation"),
            ("read_annotation", "read annotation"),
            ("update_annotation", "update annotation"),
            ("remove_annotation", "delete annotation"),
            ("publish_annotation", "publish relationship"),
        )

        indexes = [
            django.db.models.Index(fields=["page"]),
            django.db.models.Index(fields=["annotation_label"]),
            django.db.models.Index(fields=["document"]),
            django.db.models.Index(fields=["document", "creator"]),
            django.db.models.Index(fields=["corpus"]),
            django.db.models.Index(fields=["corpus", "creator"]),
            django.db.models.Index(fields=["document", "corpus"]),
            django.db.models.Index(fields=["document", "corpus", "creator"]),
            django.db.models.Index(fields=["analysis"]),
            django.db.models.Index(fields=["creator"]),
            django.db.models.Index(fields=["created"]),
            django.db.models.Index(fields=["modified"]),
        ]


# Model for Django Guardian permissions.
class AnnotationUserObjectPermission(UserObjectPermissionBase):
    content_object = django.db.models.ForeignKey(
        "Annotation", on_delete=django.db.models.CASCADE
    )
    # enabled = False


# Model for Django Guardian permissions.
class AnnotationGroupObjectPermission(GroupObjectPermissionBase):
    content_object = django.db.models.ForeignKey(
        "Annotation", on_delete=django.db.models.CASCADE
    )
    # enabled = False


def calculate_labelset_icon_path(instance, filename):
    return calc_oc_file_path(
        instance, filename, f"user_{instance.creator.id}/labelsets/icons/{uuid.uuid4()}"
    )


class LabelSet(BaseOCModel):
    """
    Label set object which stores a collection of:
     1) text labels,
     2) text label relationship labels,
     3) document labels and
     4) document relationship labels
    """

    # Basic metadata:
    title = django.db.models.CharField(max_length=1024, db_index=True)
    description = django.db.models.TextField(default="", blank=False)
    icon = django.db.models.FileField(
        blank=True, upload_to=calculate_labelset_icon_path
    )

    # For relational test...
    annotation_labels = django.db.models.ManyToManyField(
        AnnotationLabel,
        blank=True,
        related_name="included_in_labelsets",
        related_query_name="included_in_labelset",
    )

    # If this is created by an analyzer, let's link to it
    analyzer = django.db.models.ForeignKey(
        "analyzer.Analyzer", on_delete=django.db.models.SET_NULL, null=True, blank=True
    )

    INHERITS_CORPUS_PERMISSIONS = True

    class Meta:
        permissions = (
            ("permission_labelset", "Can permission labelset"),
            ("publish_labelset", "Can publish labelset"),
            ("create_labelset", "Can create labelset"),
            ("read_labelset", "Can read labelset"),
            ("update_labelset", "Can update labelset"),
            ("remove_labelset", "Can delete labelset"),
        )

        indexes = [
            django.db.models.Index(fields=["title"]),
            django.db.models.Index(fields=["analyzer"]),
            django.db.models.Index(fields=["creator"]),
            django.db.models.Index(fields=["created"]),
            django.db.models.Index(fields=["modified"]),
        ]

        constraints = [
            django.db.models.UniqueConstraint(
                fields=["analyzer", "title"],
                name="Only install one labelset of given title for each analyzer (no duplicates)",
            )
        ]


# Model for Django Guardian permissions...
class LabelSetUserObjectPermission(UserObjectPermissionBase):
    content_object = django.db.models.ForeignKey(
        "LabelSet", on_delete=django.db.models.CASCADE
    )
    # enabled = False


# Model for Django Guardian permissions...
class LabelSetGroupObjectPermission(GroupObjectPermissionBase):
    content_object = django.db.models.ForeignKey(
        "LabelSet", on_delete=django.db.models.CASCADE
    )
    # enabled = False


class NoteQuerySet(CTEQuerySet, PermissionQuerySet):
    """
    Custom QuerySet for the Note model combining CTEQuerySet and PermissionQuerySet functionalities.
    """

    pass


class NoteManager(CTEManager.from_queryset(NoteQuerySet)):
    """
    Custom Manager for the Note model that uses the combined NoteQuerySet
    and includes permissioning methods.
    """

    def get_queryset(self) -> NoteQuerySet:
        """
        Returns the custom NoteQuerySet.
        """
        return NoteQuerySet(self.model, using=self._db)

    def for_user(
        self, user: User, perm: str, extra_conditions: Optional[Q] = None
    ) -> NoteQuerySet:
        """
        Filters the queryset based on user permissions.

        Args:
            user: The user for whom permissions are checked.
            perm: The permission string.
            extra_conditions: Additional conditions for filtering.

        Returns:
            A filtered NoteQuerySet.
        """
        # This method should now use filter_queryset_by_permission to ensure
        # consistent permission handling that respects INHERITS_CORPUS_PERMISSIONS
        from opencontractserver.utils.permissioning import filter_queryset_by_permission

        queryset = self.get_queryset()

        # Apply extra conditions if provided
        if extra_conditions:
            queryset = queryset.filter(extra_conditions)

        # Use the centralized permission filtering
        return filter_queryset_by_permission(queryset, user, perm)


class Note(BaseOCModel):
    """
    Notes model for attaching hierarchical comments/notes to documents.
    Uses django_cte for hierarchical relationships.
    """

    objects = NoteManager()

    # Content
    title = django.db.models.CharField(max_length=1024, db_index=True)
    content = django.db.models.TextField(default="", blank=True)

    # Vector for vector search
    embedding = VectorField(dimensions=384, null=True)

    # Hierarchical relationship
    parent = django.db.models.ForeignKey(
        "self",
        null=True,
        blank=True,
        related_name="children",
        on_delete=django.db.models.CASCADE,
    )

    corpus = django.db.models.ForeignKey(
        "corpuses.Corpus",
        null=True,
        blank=True,
        on_delete=django.db.models.SET_NULL,
        related_name="notes",
    )

    # Document reference
    document = django.db.models.ForeignKey(
        "documents.Document",
        null=False,
        on_delete=django.db.models.CASCADE,
        related_name="notes",
    )

    # Optional reference to specific annotation
    annotation = django.db.models.ForeignKey(
        "annotations.Annotation",
        null=True,
        blank=True,
        on_delete=django.db.models.SET_NULL,
        related_name="notes",
    )

    # Sharing
    is_public = django.db.models.BooleanField(default=False)
    creator = django.db.models.ForeignKey(
        get_user_model(),
        on_delete=django.db.models.CASCADE,
        null=False,
    )

    # Timing variables
    created = django.db.models.DateTimeField(default=timezone.now)
    modified = django.db.models.DateTimeField(default=timezone.now, blank=True)

    # Flag to indicate that Notes inherit permissions from their parent corpus
    INHERITS_CORPUS_PERMISSIONS = True

    class Meta:
        permissions = (
            ("permission_note", "permission note"),
            ("publish_note", "publish note"),
            ("create_note", "create note"),
            ("read_note", "read note"),
            ("update_note", "update note"),
            ("remove_note", "delete note"),
        )
        indexes = [
            django.db.models.Index(fields=["title"]),
            django.db.models.Index(fields=["document"]),
            django.db.models.Index(fields=["annotation"]),
            django.db.models.Index(fields=["creator"]),
            django.db.models.Index(fields=["created"]),
            django.db.models.Index(fields=["modified"]),
            django.db.models.Index(fields=["parent"]),
            django.db.models.Index(fields=["corpus"]),
        ]
        ordering = ("created",)

    def save(self, *args, **kwargs):
        """On save, update timestamps"""
        if not self.pk:
            self.created = timezone.now()
        self.modified = timezone.now()
        return super().save(*args, **kwargs)


# Model for Django Guardian permissions
class NoteUserObjectPermission(UserObjectPermissionBase):
    content_object = django.db.models.ForeignKey(
        "Note", on_delete=django.db.models.CASCADE
    )


# Model for Django Guardian permissions
class NoteGroupObjectPermission(GroupObjectPermissionBase):
    content_object = django.db.models.ForeignKey(
        "Note", on_delete=django.db.models.CASCADE
    )
