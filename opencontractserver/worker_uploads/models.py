import hashlib
import secrets
import uuid
from datetime import datetime
from typing import Any, Optional

from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone

from opencontractserver.shared.utils import calc_oc_file_path

User = get_user_model()

TOKEN_KEY_LENGTH = 64  # 256-bit random hex token
TOKEN_HASH_LENGTH = 64  # SHA-256 hex digest length


def _generate_token_key() -> str:
    """Generate a cryptographically random token key (plaintext).

    Referenced by migration 0001_initial as a field default. Not used at
    runtime — all token creation goes through CorpusAccessToken.create_token()
    which hashes before storage. Do not remove: the migration import will break.
    """
    return secrets.token_hex(TOKEN_KEY_LENGTH // 2)


def hash_token(plaintext: str) -> str:
    """One-way SHA-256 hash of a plaintext token for secure storage."""
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def _upload_staging_path(instance: Any, filename: str) -> str:
    return calc_oc_file_path(instance, filename, "worker_uploads/staging")


class WorkerAccount(models.Model):
    """
    Service account for external document processing workers.

    Each WorkerAccount has an auto-created Django User for permission
    compatibility with the existing guardian-based permission system.
    The linked User is created with an unusable password and is_staff=False.
    """

    name = models.CharField(
        max_length=255,
        unique=True,
        help_text="Human-readable name for this worker account.",
    )
    description = models.TextField(
        blank=True,
        default="",
        help_text="Description of what this worker does.",
    )
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="worker_account",
        help_text="Auto-created Django User for permission compatibility.",
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Inactive accounts cannot authenticate.",
    )
    creator = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_worker_accounts",
        help_text="Admin who created this worker account.",
    )
    created = models.DateTimeField(default=timezone.now, db_index=True)
    modified = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created"]
        indexes = [
            models.Index(fields=["name"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self) -> str:
        status = "active" if self.is_active else "inactive"
        return f"WorkerAccount({self.name}, {status})"

    @classmethod
    def create_with_user(
        cls,
        *,
        name: str,
        description: str = "",
        creator: Optional[Any] = None,
    ) -> "WorkerAccount":
        """
        Create a WorkerAccount with an auto-generated Django User.

        The User is created with:
        - username: worker_<uuid> (guaranteed unique)
        - unusable password (no login possible)
        - is_staff=False, is_superuser=False

        Runs inside transaction.atomic() so the User is rolled back if
        WorkerAccount creation fails (no orphaned users).

        Raises:
            ValueError: If a WorkerAccount with the given name already exists.
        """
        from django.db import IntegrityError, transaction

        with transaction.atomic():
            if cls.objects.filter(name=name).exists():
                raise ValueError(f"WorkerAccount with name '{name}' already exists.")

            username = f"worker_{uuid.uuid4().hex[:12]}"
            user = User.objects.create_user(
                username=username,
                email=f"{username}@workers.internal",
                password=None,  # create_user(password=None) sets unusable password
                is_staff=False,
                is_superuser=False,
            )

            try:
                return cls.objects.create(
                    name=name,
                    description=description,
                    user=user,
                    creator=creator,
                )
            except IntegrityError:
                raise ValueError(f"WorkerAccount with name '{name}' already exists.")


class CorpusAccessToken(models.Model):
    """
    Scoped access token granting a WorkerAccount upload access to a specific corpus.

    Tokens are long-lived (configurable expiry) and can be revoked individually.
    Each token is scoped to exactly one corpus. Create multiple tokens for
    multi-corpus access.

    Security: Only the SHA-256 hash of the token is stored. The plaintext is
    returned once at creation via ``create_token()`` and cannot be recovered.
    Authentication hashes the incoming key and performs a constant-time lookup.
    """

    key = models.CharField(
        max_length=TOKEN_HASH_LENGTH,
        unique=True,
        db_index=True,
        help_text="SHA-256 hash of the access token. Plaintext shown only once at creation.",
    )
    # Short prefix for admin identification (first 8 chars of plaintext)
    key_prefix = models.CharField(
        max_length=8,
        blank=True,
        default="",
        help_text="First 8 characters of the plaintext token for admin identification.",
    )
    worker_account = models.ForeignKey(
        WorkerAccount,
        on_delete=models.CASCADE,
        related_name="access_tokens",
        help_text="Worker account this token belongs to.",
    )
    corpus = models.ForeignKey(
        "corpuses.Corpus",
        on_delete=models.CASCADE,
        related_name="worker_access_tokens",
        help_text="Corpus this token grants upload access to.",
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Token expiry. Null means no expiry.",
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Revoked tokens have is_active=False.",
    )
    rate_limit_per_minute = models.PositiveIntegerField(
        default=0,
        help_text="Max uploads per minute. 0 means unlimited.",
    )
    created = models.DateTimeField(default=timezone.now, db_index=True)
    modified = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created"]
        indexes = [
            models.Index(fields=["worker_account", "corpus"]),
            models.Index(fields=["is_active", "expires_at"]),
        ]

    def __str__(self) -> str:
        status = "active" if self.is_active else "revoked"
        prefix = f"{self.key_prefix}..." if self.key_prefix else "???"
        return (
            f"CorpusAccessToken({prefix}, "
            f"worker={self.worker_account.name}, "
            f"corpus={self.corpus_id}, {status})"
        )

    @classmethod
    def create_token(
        cls,
        *,
        worker_account: WorkerAccount,
        corpus: Any,
        expires_at: Optional[datetime] = None,
        rate_limit_per_minute: int = 0,
        is_active: bool = True,
    ) -> tuple["CorpusAccessToken", str]:
        """
        Create a new token, storing only the SHA-256 hash.

        Returns:
            Tuple of (token_instance, plaintext_key). The plaintext is shown
            only once — it cannot be recovered from the stored hash.
        """
        plaintext = _generate_token_key()
        token = cls.objects.create(
            key=hash_token(plaintext),
            key_prefix=plaintext[:8],
            worker_account=worker_account,
            corpus=corpus,
            expires_at=expires_at,
            rate_limit_per_minute=rate_limit_per_minute,
            is_active=is_active,
        )
        return token, plaintext

    @property
    def is_valid(self) -> bool:
        """
        Check if token is currently valid (active, not expired, account active).

        Note: accesses self.worker_account.is_active. The auth backend
        (WorkerTokenAuthentication) uses select_related("worker_account") so
        this is already cached on the request path. If calling is_valid outside
        the auth flow, ensure worker_account is prefetched to avoid an extra query.
        """
        if not self.is_active:
            return False
        if not self.worker_account.is_active:
            return False
        if self.expires_at and timezone.now() >= self.expires_at:
            return False
        return True


class UploadStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    PROCESSING = "PROCESSING", "Processing"
    COMPLETED = "COMPLETED", "Completed"
    FAILED = "FAILED", "Failed"


class WorkerDocumentUpload(models.Model):
    """
    Staging table for worker document uploads.

    Uploads are written here by the REST endpoint and drained by a batch
    processor Celery task. This database-backed queue avoids Redis saturation
    when handling millions of uploads.

    The batch processor uses SELECT ... FOR UPDATE SKIP LOCKED to allow
    concurrent processing without conflicts.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    corpus_access_token = models.ForeignKey(
        CorpusAccessToken,
        on_delete=models.SET_NULL,
        null=True,
        related_name="uploads",
        help_text="Token used for this upload.",
    )
    corpus = models.ForeignKey(
        "corpuses.Corpus",
        on_delete=models.CASCADE,
        related_name="worker_uploads",
        help_text="Target corpus for this upload.",
    )
    status = models.CharField(
        max_length=20,
        choices=UploadStatus.choices,
        default=UploadStatus.PENDING,
        db_index=True,
    )
    file = models.FileField(
        upload_to=_upload_staging_path,
        help_text="The uploaded document file.",
    )
    metadata = models.JSONField(
        default=dict,
        help_text="JSON payload with annotations, embeddings, labels, and target path.",
    )
    error_message = models.TextField(
        blank=True,
        default="",
        help_text="Error details if processing failed.",
    )
    result_document = models.ForeignKey(
        "documents.Document",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="worker_upload_records",
        help_text="The Document created after successful processing.",
    )
    created = models.DateTimeField(default=timezone.now, db_index=True)
    processing_started = models.DateTimeField(null=True, blank=True)
    processing_finished = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created"]
        indexes = [
            models.Index(fields=["status", "created"]),
            models.Index(fields=["corpus", "status"]),
            models.Index(fields=["corpus_access_token"]),
        ]

    def __str__(self) -> str:
        return f"WorkerDocumentUpload({self.id}, {self.status})"
