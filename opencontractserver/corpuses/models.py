import uuid

import django
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone
from guardian.models import GroupObjectPermissionBase, UserObjectPermissionBase
from tree_queries.models import TreeNode

from opencontractserver.annotations.models import Annotation
from opencontractserver.shared.mixins import PermissionedOperationsMixin
from opencontractserver.shared.Models import BaseOCModel
from opencontractserver.shared.QuerySets import PermissionedTreeQuerySet
from opencontractserver.shared.utils import calc_oc_file_path


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
class Corpus(PermissionedOperationsMixin, TreeNode):

    """
    Corpus, which stores a collection of documents that are grouped for machine learning / study / export purposes.
    """

    # Model variables
    title = django.db.models.CharField(max_length=1024, db_index=True)
    description = django.db.models.TextField(default="", blank=True)
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

    objects = PermissionedTreeQuerySet.as_manager(with_tree_fields=True)

    class Meta:
        permissions = (
            ("permission_corpus", "permission corpus"),
            ("publish_corpus", "publish corpus"),
            ("create_corpus", "create corpus"),
            ("read_corpus", "read corpus"),
            ("update_corpus", "update corpus"),
            ("remove_corpus", "delete corpus"),
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

    # Override save to update modified on save
    def save(self, *args, **kwargs):

        """On save, update timestamps"""
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


# Documents inherit permissions from their parent corpus
INHERITS_CORPUS_PERMISSIONS = True
