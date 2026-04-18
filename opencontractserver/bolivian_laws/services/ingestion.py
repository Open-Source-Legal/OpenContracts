"""Ingestion service: PDFs → per-area Corpus.

Three responsibilities:

1. ``ensure_area_corpus(area, user)`` — idempotent corpus creation per area.
2. ``ingest_pdf(...)`` — SHA-256 dedupe + ``Corpus.import_content()`` call.
3. ``classify_pdf_area(...)`` — optional LLM-based area classifier.

These are deliberately framework-agnostic Python functions (not Celery
tasks) so the management command can call them inline or wrap them in a
task as needed.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Optional, Union

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from opencontractserver.bolivian_laws.constants import (
    AREA_PROFILES,
    LegalArea,
    LegalSource,
    corpus_slug_for_area,
    get_profile,
)
from opencontractserver.bolivian_laws.models import (
    BolivianLegalDocument,
    LegalAreaCorpus,
)
from opencontractserver.corpuses.models import Corpus

logger = logging.getLogger(__name__)
User = get_user_model()

PDF_MIMETYPE = "application/pdf"


def _resolve_user(user) -> User:
    """Resolve the ingestion user; fall back to the first superuser."""
    if user is not None:
        return user
    su = User.objects.filter(is_superuser=True).order_by("pk").first()
    if su is None:
        raise RuntimeError(
            "No user provided and no superuser exists; cannot create corpus."
        )
    return su


def ensure_area_corpus(area: str, user=None) -> Corpus:
    """Get or create the dedicated corpus for ``area``.

    Idempotent: subsequent calls return the same corpus. The
    ``preferred_embedder`` and ``corpus_agent_instructions`` are seeded
    from ``AREA_PROFILES`` and from the platform's default embedder.

    Args:
        area: A ``LegalArea`` value (string).
        user: User to record as creator. Defaults to the first superuser.

    Returns:
        The ``Corpus`` instance bound to that area.
    """
    if area not in AREA_PROFILES:
        raise ValueError(f"Unknown legal area: {area!r}")

    existing = (
        LegalAreaCorpus.objects.filter(area=area).select_related("corpus").first()
    )
    if existing is not None:
        return existing.corpus

    profile = get_profile(area)
    creator = _resolve_user(user)

    with transaction.atomic():
        # Re-check inside the transaction to avoid races.
        existing = (
            LegalAreaCorpus.objects.select_for_update()
            .filter(area=area)
            .select_related("corpus")
            .first()
        )
        if existing is not None:
            return existing.corpus

        corpus = Corpus.objects.create(
            title=profile.title,
            description=profile.description,
            slug=corpus_slug_for_area(area),
            corpus_agent_instructions=profile.agent_instructions,
            creator=creator,
            is_public=False,
        )
        LegalAreaCorpus.objects.create(area=area, corpus=corpus)
        logger.info(
            "Created Bolivian-laws corpus for area=%s id=%s slug=%s",
            area,
            corpus.pk,
            corpus.slug,
        )
        return corpus


def _read_bytes(pdf: Union[str, Path, bytes]) -> bytes:
    if isinstance(pdf, (str, Path)):
        return Path(pdf).read_bytes()
    if isinstance(pdf, (bytes, bytearray)):
        return bytes(pdf)
    raise TypeError(f"Unsupported pdf input type: {type(pdf)!r}")


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def ingest_pdf(
    pdf: Union[str, Path, bytes],
    *,
    area: str,
    title: str,
    source: str = LegalSource.MANUAL,
    external_id: str = "",
    published_at=None,
    metadata: Optional[dict] = None,
    filename: Optional[str] = None,
    user=None,
) -> BolivianLegalDocument:
    """Ingest a single PDF into the area's corpus, with SHA-256 dedupe.

    If a record with the same SHA-256 already exists (regardless of area
    or source), this is a no-op and the existing record is returned.

    Returns:
        The ``BolivianLegalDocument`` tracking record. ``status`` is
        ``INGESTED`` on success, or ``FAILED`` if the underlying import
        raised — in which case the exception is re-raised after the
        record is persisted with ``last_error``.
    """
    if area not in AREA_PROFILES:
        raise ValueError(f"Unknown legal area: {area!r}")

    content = _read_bytes(pdf)
    sha = _sha256(content)

    existing = BolivianLegalDocument.objects.filter(pdf_sha256=sha).first()
    if existing is not None:
        logger.info(
            "Dedupe hit: PDF sha=%s already ingested as record #%s",
            sha,
            existing.pk,
        )
        return existing

    corpus = ensure_area_corpus(area, user=user)
    creator = _resolve_user(user)

    record = BolivianLegalDocument.objects.create(
        area=area,
        source=source,
        external_id=external_id or "",
        title=title,
        published_at=published_at,
        pdf_sha256=sha,
        metadata=metadata or {},
        corpus=corpus,
        status=BolivianLegalDocument.Status.PENDING,
    )

    try:
        doc, _status, _doc_path = corpus.import_content(
            content=content,
            user=creator,
            filename=filename or f"{title}.pdf",
            file_type=PDF_MIMETYPE,
            title=title,
            description=f"[{LegalSource(source).label}] {title}",
        )
    except Exception as exc:
        record.status = BolivianLegalDocument.Status.FAILED
        record.last_error = str(exc)[:2000]
        record.save(update_fields=["status", "last_error"])
        logger.exception("Failed to ingest PDF sha=%s into area=%s", sha, area)
        raise

    record.document = doc
    record.status = BolivianLegalDocument.Status.INGESTED
    record.ingested_at = timezone.now()
    record.save(update_fields=["document", "status", "ingested_at"])
    return record


def infer_metadata_from_filename(name: str) -> dict:
    """Best-effort metadata extraction from a filename.

    Convention (orientative, not enforced):
    ``[area]_[year]_[number]_[title].pdf``

    Returns a dict with whatever fields could be inferred. Always safe
    to call; missing fields are simply absent from the result.
    """
    stem = Path(name).stem
    parts = stem.split("_")
    out: dict = {}

    if not parts:
        return out

    candidate_area = parts[0].lower()
    if candidate_area in AREA_PROFILES:
        out["area"] = candidate_area
        parts = parts[1:]

    if parts and parts[0].isdigit() and len(parts[0]) == 4:
        out["year"] = int(parts[0])
        parts = parts[1:]

    if parts and parts[0].isdigit():
        out["number"] = parts[0]
        parts = parts[1:]

    if parts:
        out["title_hint"] = " ".join(parts).replace("-", " ").strip()

    return out


# --- Optional LLM-based classifier ----------------------------------------


def _extract_pdf_text_preview(
    pdf: Union[str, Path, bytes], max_chars: int = 2000
) -> str:
    """Cheap text preview for classification.

    Uses pypdf if available; returns an empty string on any failure so
    the classifier can fall back to ``LegalArea.OTROS`` gracefully.
    """
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception:
        try:
            from PyPDF2 import PdfReader  # type: ignore
        except Exception:
            return ""

    try:
        if isinstance(pdf, (str, Path)):
            reader = PdfReader(str(pdf))
        else:
            from io import BytesIO

            reader = PdfReader(BytesIO(_read_bytes(pdf)))
        chunks: list[str] = []
        total = 0
        for page in reader.pages[:5]:
            try:
                txt = page.extract_text() or ""
            except Exception:
                txt = ""
            if not txt:
                continue
            chunks.append(txt)
            total += len(txt)
            if total >= max_chars:
                break
        return ("\n".join(chunks))[:max_chars]
    except Exception:
        return ""


async def classify_pdf_area(
    pdf: Union[str, Path, bytes],
    *,
    title: Optional[str] = None,
    model: Optional[str] = None,
) -> str:
    """Classify a PDF into a ``LegalArea`` using a cheap LLM call.

    Falls back to ``LegalArea.OTROS`` on any error (missing model, no
    API key, parse failure, etc.) so callers don't need to handle
    partial failures during bulk ingestion.
    """
    from django.conf import settings

    preview = _extract_pdf_text_preview(pdf)
    title_hint = title or "(sin título)"
    if not preview:
        logger.warning(
            "Classifier got empty preview for title=%r; defaulting to OTROS", title_hint
        )
        return LegalArea.OTROS

    classifier_model = (
        model
        or getattr(settings, "BOLIVIAN_LAWS_CLASSIFIER_MODEL", None)
        or "gpt-4o-mini"
    )

    valid_areas = ", ".join(a.value for a in LegalArea)
    prompt = (
        "Clasifica el siguiente documento jurídico boliviano en UNA de "
        f"estas áreas: {valid_areas}. Responde solo el código (en "
        "minúsculas, sin comillas).\n\n"
        f"Título: {title_hint}\n\n"
        f"Inicio del documento:\n{preview}"
    )

    try:
        # Use a minimal corpus-less structured response: we don't have a
        # corpus context here, so we fall back to a simple LLM call via
        # the agents API by attaching to any existing corpus is not
        # appropriate. Instead, use the structured response API on a
        # placeholder document — but we have none. So we use a direct
        # pydantic_ai call here, kept tiny and isolated.
        from pydantic_ai import Agent

        agent = Agent(classifier_model, output_type=str)  # type: ignore[arg-type]
        result = await agent.run(prompt)
        raw = (result.output or "").strip().lower()
        for area in LegalArea:
            if raw == area.value or raw.startswith(area.value):
                return area.value
        logger.warning(
            "Classifier returned unrecognized area %r; defaulting to OTROS", raw
        )
        return LegalArea.OTROS
    except Exception:
        logger.exception("LLM classification failed; defaulting to OTROS")
        return LegalArea.OTROS
