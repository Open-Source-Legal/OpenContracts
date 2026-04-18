"""Models for the Bolivian Laws RAG service.

Two models:

- ``LegalAreaCorpus``: 1-to-1 idempotent mapping ``area → Corpus``. Avoids
  hardcoding corpus IDs anywhere else in the system.
- ``BolivianLegalDocument``: tracking record per ingested PDF, providing
  global SHA-256 dedupe, source attribution, area classification, and a
  back-pointer to the resulting OC ``Document``.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import models

from opencontractserver.bolivian_laws.constants import LegalArea, LegalSource

User = get_user_model()


class LegalAreaCorpus(models.Model):
    """Maps a legal area to its dedicated Corpus.

    Created on-demand by ``services.ingestion.ensure_area_corpus`` the
    first time documents for the area are ingested.
    """

    area = models.CharField(
        max_length=32,
        choices=LegalArea.choices,
        unique=True,
    )
    corpus = models.OneToOneField(
        "corpuses.Corpus",
        on_delete=models.CASCADE,
        related_name="bolivian_law_area",
    )
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Bolivian Legal Area Corpus"
        verbose_name_plural = "Bolivian Legal Area Corpora"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.get_area_display()} → corpus #{self.corpus_id}"


class BolivianLegalDocument(models.Model):
    """Tracking record for a Bolivian legal PDF that has been (or is being)
    ingested into the area corpus.

    ``pdf_sha256`` is globally unique to provide cheap dedupe across all
    sources/areas: the same PDF will not be ingested twice.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        INGESTED = "ingested", "Ingestado"
        FAILED = "failed", "Fallido"

    area = models.CharField(max_length=32, choices=LegalArea.choices)
    source = models.CharField(
        max_length=16,
        choices=LegalSource.choices,
        default=LegalSource.MANUAL,
    )
    external_id = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text=(
            "Identificador externo (número de gaceta, sentencia, etc.). "
            "Opcional; depende de la fuente."
        ),
    )
    title = models.CharField(max_length=1024)
    published_at = models.DateField(null=True, blank=True)
    pdf_sha256 = models.CharField(max_length=64, unique=True)
    metadata = models.JSONField(default=dict, blank=True)

    document = models.ForeignKey(
        "documents.Document",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bolivian_legal_records",
    )
    corpus = models.ForeignKey(
        "corpuses.Corpus",
        on_delete=models.CASCADE,
        related_name="bolivian_legal_records",
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
    )
    last_error = models.TextField(blank=True, default="")
    created = models.DateTimeField(auto_now_add=True)
    ingested_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Bolivian Legal Document"
        verbose_name_plural = "Bolivian Legal Documents"
        indexes = [
            models.Index(fields=["area", "status"]),
            models.Index(fields=["source", "status"]),
        ]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"[{self.get_area_display()}] {self.title[:60]}"
