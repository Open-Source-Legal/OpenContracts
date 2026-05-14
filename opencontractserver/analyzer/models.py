import functools
import hashlib
import hmac
import secrets
import uuid

import django
from django.contrib.auth import get_user_model
from guardian.models import GroupObjectPermissionBase, UserObjectPermissionBase

from opencontractserver.corpuses.models import Corpus
from opencontractserver.shared.defaults import jsonfield_default_value
from opencontractserver.shared.fields import NullableJSONField
from opencontractserver.shared.Models import BaseOCModel
from opencontractserver.shared.utils import calc_oc_file_path
from opencontractserver.types.enums import JobStatus


def calculate_analyzer_icon_path(instance, filename):
    return calc_oc_file_path(
        instance, filename, f"user_{instance.creator.id}/analyzers/icons/{uuid.uuid4()}"
    )


class GremlinEngine(BaseOCModel):
    """
    Model for a Gremlin API endpoint that can execute Gremlin queries against.
    """

    class Meta:
        permissions = (
            ("permission_gremlinengine", "permission gremlin engine"),
            ("publish_gremlinengine", "publish gremlin engine"),
            ("create_gremlinengine", "create gremlin engine"),
            ("read_gremlinengine", "read gremlin engine"),
            ("update_gremlinengine", "update gremlin engine"),
            ("remove_gremlinengine", "delete gremlin engine"),
            ("comment_gremlinengine", "comment gremlin engine"),
        )

    url = django.db.models.CharField(
        max_length=1024,
        blank=False,
        null=False,
    )

    # Anticipating that you may have totally unauthenticated Gremlin Engine
    api_key = django.db.models.CharField(
        max_length=1024,
        blank=True,
        null=True,
    )

    last_synced = django.db.models.DateTimeField(
        "Creation Date and Time", blank=True, null=True
    )
    install_started = django.db.models.DateTimeField(
        "Install Started", blank=True, null=True
    )
    install_completed = django.db.models.DateTimeField(
        "Install Completed", blank=True, null=True
    )
    is_public = django.db.models.BooleanField(default=False)


class GremlinEngineUserObjectPermission(UserObjectPermissionBase):
    content_object = django.db.models.ForeignKey(
        "GremlinEngine", on_delete=django.db.models.CASCADE
    )
    # enabled = False


# Model for Django Guardian permissions.
class GremlinEngineGroupObjectPermission(GroupObjectPermissionBase):
    content_object = django.db.models.ForeignKey(
        "GremlinEngine", on_delete=django.db.models.CASCADE
    )
    # enabled = False


class Analyzer(BaseOCModel):
    """
    Model representing an analyzer that can be run on a corpus. An analyzer is a
    Python package that is installed in a Gremlin Engine and can be run on a corpus
    to produce annotations.
    """

    class Meta:
        permissions = (
            ("permission_analyzer", "permission analyzer"),
            ("publish_analyzer", "publish analyzer"),
            ("create_analyzer", "create analyzer"),
            ("read_analyzer", "read analyzer"),
            ("update_analyzer", "update analyzer"),
            ("remove_analyzer", "delete analyzer"),
            ("comment_analyzer", "comment analyzer"),
        )
        constraints = [
            django.db.models.CheckConstraint(
                condition=(
                    django.db.models.Q(
                        host_gremlin__isnull=True, task_name__isnull=False
                    )
                    | django.db.models.Q(
                        host_gremlin__isnull=False, task_name__isnull=True
                    )
                ),
                name="one_field_null_constraint",
            ),
            django.db.models.UniqueConstraint(
                fields=["host_gremlin"],
                condition=django.db.models.Q(host_gremlin__isnull=False),
                name="unique_host_gremlin_if_not_null",
            ),
            django.db.models.UniqueConstraint(
                fields=["task_name"],
                condition=django.db.models.Q(task_name__isnull=False),
                name="unique_task_name_if_not_null",
            ),
        ]

    id = django.db.models.CharField(max_length=1024, primary_key=True)

    # Tracking information to tie this back to the OC Analyzer that was used to create it.
    manifest = NullableJSONField(default=jsonfield_default_value, null=True, blank=True)
    description = django.db.models.TextField(null=False, blank=True, default="")
    disabled = django.db.models.BooleanField(default=False)
    is_public = django.db.models.BooleanField(default=False)
    icon = django.db.models.FileField(
        blank=True, upload_to=calculate_analyzer_icon_path
    )

    host_gremlin = django.db.models.ForeignKey(
        GremlinEngine,
        on_delete=django.db.models.CASCADE,
        null=True,
        blank=True,
    )

    task_name = django.db.models.CharField(
        max_length=1024,
        null=True,
        blank=True,
        default=None,
    )

    input_schema = NullableJSONField(
        default=jsonfield_default_value,
        null=True,
        blank=True,
        help_text="Optional JSONSchema describing the analyzer input.",
    )


class AnalyzerUserObjectPermission(UserObjectPermissionBase):
    content_object = django.db.models.ForeignKey(
        "Analyzer", on_delete=django.db.models.CASCADE
    )
    # enabled = False


# Model for Django Guardian permissions.
class AnalyzerGroupObjectPermission(GroupObjectPermissionBase):
    content_object = django.db.models.ForeignKey(
        "Analyzer", on_delete=django.db.models.CASCADE
    )
    # enabled = False


# Create your models here.
class Analysis(BaseOCModel):
    """
    Okay, this is duplicative of new Extracts objects... I can probably make this pull double duty
    BUT I think the more expeditious approach here is to just start fresh and leave this for now but
    Eventually replace it or merge the two concepts.

    For now, the distinction is extracts are not annotating the documents directly but rather tracking where
    information is coming from - so we can still jump into the document - but storing extracted information for
    export as a csv.
    """

    class Meta:
        permissions = (
            ("create_analysis", "create Analysis"),
            ("read_analysis", "read Analysis"),
            ("update_analysis", "update Analysis"),
            ("remove_analysis", "delete Analysis"),
            ("publish_analysis", "publish Analysis"),
            ("permission_analysis", "permission Analysis"),
            ("comment_analysis", "comment Analysis"),
        )

    # Sharing
    is_public = django.db.models.BooleanField(default=False)
    creator = django.db.models.ForeignKey(
        get_user_model(),
        on_delete=django.db.models.CASCADE,
        null=False,
        default=1,
    )

    # Tracking information to tie this back to the OC Analyzer that was used to create it.
    analyzer = django.db.models.ForeignKey(
        Analyzer, null=False, blank=False, on_delete=django.db.models.CASCADE
    )

    # SHA-256 hex of the callback token. The plaintext is generated by
    # ``rotate_callback_token`` and sent to the analyzer worker at submit
    # time; the database never stores the plaintext, so a DB read alone
    # does not let an attacker forge a callback. Empty string means no
    # token has been generated yet.
    callback_token_hash = django.db.models.CharField(
        max_length=64, blank=True, default="", editable=False
    )

    received_callback_file = django.db.models.FileField(
        max_length=1024,
        blank=True,
        null=True,
        upload_to=functools.partial(calc_oc_file_path, sub_folder="pdf_files"),
    )

    # Which corpus was analyzed
    analyzed_corpus = django.db.models.ForeignKey(
        Corpus,
        on_delete=django.db.models.SET_NULL,
        related_name="analyses",
        blank=True,
        null=True,
    )

    # If applicable, what CorpusAction ran?
    corpus_action = django.db.models.ForeignKey(
        "corpuses.CorpusAction",
        related_name="analyses",
        blank=True,
        null=True,
        on_delete=django.db.models.SET_NULL,
    )

    import_log = django.db.models.TextField(blank=True, null=True)

    # More for future use - if we are not analyzing an entire corpus but a subset
    # or, potentially, just a random selection of documents, which documents were analyzed?
    # For starters, just analyze entire corpus.
    analyzed_documents = django.db.models.ManyToManyField(
        "documents.Document", related_name="included_in_analyses", blank=True
    )

    # Error handling
    error_message = django.db.models.TextField(blank=True, null=True)
    error_traceback = django.db.models.TextField(blank=True, null=True)

    # Result message
    result_message = django.db.models.TextField(blank=True, null=True)

    # Timing variables
    analysis_started = django.db.models.DateTimeField(blank=True, null=True)
    analysis_completed = django.db.models.DateTimeField(blank=True, null=True)
    status = django.db.models.CharField(
        max_length=24,
        choices=[(status.value, status.name) for status in JobStatus],
        default=JobStatus.CREATED.value,
    )

    @staticmethod
    def _hash_callback_token(plaintext: str) -> str:
        return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()

    def rotate_callback_token(self) -> str:
        """Generate a fresh plaintext callback token, store its hash, return the plaintext.

        .. warning::
           If the instance already has a ``pk`` (i.e. it has been saved at
           least once) the hash is persisted automatically as part of this
           call. If the instance is unsaved (``self.pk is None``) the
           caller MUST follow up with ``self.save(...)`` before
           transmitting the plaintext, otherwise the plaintext will be
           sent to the worker but the DB will lack the verifying hash and
           every callback for this analysis will fail.

        The plaintext is the only artifact that can be sent to the
        analyzer worker; the database never receives it. Each call
        rotates the token, so any in-flight callback bound to a previous
        plaintext will fail verification.
        """
        plaintext = secrets.token_urlsafe(32)
        self.callback_token_hash = self._hash_callback_token(plaintext)
        # Auto-persist for already-saved instances so callers can't silently
        # ship the plaintext to a worker while the DB still holds the old
        # hash. ``save(update_fields=...)`` keeps this narrow.
        if self.pk is not None:
            self.save(update_fields=["callback_token_hash"])
        return plaintext

    def verify_callback_token(self, candidate: str | None) -> bool:
        """Return True iff ``candidate`` hashes to the stored token hash.

        Uses constant-time comparison to avoid timing leaks. An empty
        stored hash (no token has been issued) always returns False.
        """
        if not candidate or not self.callback_token_hash:
            return False
        return hmac.compare_digest(
            self.callback_token_hash,
            self._hash_callback_token(candidate),
        )


# Model for Django Guardian permissions.
class AnalysisUserObjectPermission(UserObjectPermissionBase):
    content_object = django.db.models.ForeignKey(
        "Analysis", on_delete=django.db.models.CASCADE
    )
    # enabled = False


# Model for Django Guardian permissions.
class AnalysisGroupObjectPermission(GroupObjectPermissionBase):
    content_object = django.db.models.ForeignKey(
        "Analysis", on_delete=django.db.models.CASCADE
    )
    # enabled = False
