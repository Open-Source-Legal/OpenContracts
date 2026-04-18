"""Celery tasks for the Bolivian Laws RAG service.

Two concerns live here:

- **Ingestion**: ``ingest_pdf_async`` takes an already-downloaded PDF on
  disk and pushes it through the ingestion pipeline.
- **Scraping**: ``scrape_and_ingest_source`` / ``scrape_and_ingest_all``
  drive the per-source scrapers, deduplicate by SHA-256, and hand each
  PDF off to ``ingest_pdf`` inline.

The scraping tasks are idempotent and safe to run on a Celery Beat
schedule: already-ingested PDFs are a no-op thanks to the SHA-256
dedupe in the ingestion service.
"""

from __future__ import annotations

import datetime as dt
import logging

from celery import shared_task
from django.conf import settings

from opencontractserver.bolivian_laws.constants import LegalArea, LegalSource
from opencontractserver.bolivian_laws.services.ingestion import (
    ingest_pdf,
)

logger = logging.getLogger(__name__)


@shared_task(name="bolivian_laws.ingest_pdf_async")
def ingest_pdf_async(
    pdf_path: str,
    *,
    area: str,
    title: str,
    source: str = LegalSource.MANUAL,
    external_id: str = "",
    published_at: str | None = None,
    metadata: dict | None = None,
    user_id: int | None = None,
) -> int:
    """Async wrapper around ``ingest_pdf`` for bulk ingestion via Celery.

    Returns the resulting ``BolivianLegalDocument`` primary key.
    """
    from django.contrib.auth import get_user_model

    user = None
    if user_id is not None:
        user = get_user_model().objects.filter(pk=user_id).first()

    parsed_date: dt.date | None = None
    if published_at:
        try:
            parsed_date = dt.date.fromisoformat(published_at)
        except ValueError:
            logger.warning("Invalid published_at=%r; ignoring.", published_at)

    record = ingest_pdf(
        pdf_path,
        area=area,
        title=title,
        source=source,
        external_id=external_id,
        published_at=parsed_date,
        metadata=metadata,
        user=user,
    )
    return record.pk


def _resolve_scrape_area(entry) -> str:
    """Pick a legal area for a scraped entry.

    Priority:
    1. The scraper's own suggestion (keyword/sala-based heuristics).
    2. ``LegalArea.OTROS`` as a safe fallback so ingestion never fails
       just because classification is uncertain.

    We intentionally avoid calling the LLM classifier from the scraping
    task itself — that would make the periodic job expensive and
    coupled to OpenAI availability. Users can re-classify records
    manually or re-run ingestion through the management command with
    ``--auto-classify`` when desired.
    """
    suggested = getattr(entry, "suggested_area", None)
    if suggested in {a.value for a in LegalArea}:
        return suggested
    return LegalArea.OTROS.value


@shared_task(
    name="bolivian_laws.scrape_and_ingest_source",
    acks_late=True,
)
def scrape_and_ingest_source(
    source_key: str,
    *,
    since_days: int | None = None,
    max_entries: int | None = None,
    user_id: int | None = None,
) -> dict:
    """Run a single scraper and ingest everything it yields.

    Returns a summary dict with per-status counts so the caller (or
    Flower) can see at a glance what happened.
    """
    # Imports live inside the task so Celery worker startup doesn't
    # need httpx/bs4 resolved before Django is ready.
    import hashlib

    from django.contrib.auth import get_user_model

    from opencontractserver.bolivian_laws.models import BolivianLegalDocument
    from opencontractserver.bolivian_laws.scrapers import get_scraper_class

    user = None
    if user_id is not None:
        user = get_user_model().objects.filter(pk=user_id).first()

    lookback_days = (
        since_days
        if since_days is not None
        else int(getattr(settings, "BOLIVIAN_LAWS_SCRAPE_LOOKBACK_DAYS", 30) or 30)
    )
    since: dt.date | None = None
    if lookback_days > 0:
        since = dt.date.today() - dt.timedelta(days=lookback_days)

    scraper_cls = get_scraper_class(source_key)
    summary = {
        "source": source_key,
        "since": since.isoformat() if since else None,
        "discovered": 0,
        "ingested": 0,
        "dedupe_hits": 0,
        "failed": 0,
    }

    with scraper_cls() as scraper:
        for entry in scraper.iter_entries(since=since, max_entries=max_entries):
            summary["discovered"] += 1
            try:
                pdf_bytes = scraper.download_pdf(entry)
            except Exception as exc:
                summary["failed"] += 1
                logger.warning(
                    "[%s] failed to download %s: %s",
                    source_key,
                    entry.pdf_url,
                    exc,
                )
                continue

            sha = hashlib.sha256(pdf_bytes).hexdigest()
            if BolivianLegalDocument.objects.filter(pdf_sha256=sha).exists():
                summary["dedupe_hits"] += 1
                continue

            area = _resolve_scrape_area(entry)
            try:
                ingest_pdf(
                    pdf_bytes,
                    area=area,
                    title=entry.title or entry.pdf_url.rsplit("/", 1)[-1],
                    source=source_key,
                    external_id=entry.external_id,
                    published_at=entry.published_at,
                    metadata={**entry.metadata, "pdf_url": entry.pdf_url},
                    user=user,
                    filename=entry.pdf_url.rsplit("/", 1)[-1] or None,
                )
            except Exception as exc:
                summary["failed"] += 1
                logger.exception(
                    "[%s] ingest failed for %s: %s",
                    source_key,
                    entry.pdf_url,
                    exc,
                )
                continue

            summary["ingested"] += 1

    logger.info(
        "Bolivian-laws scrape finished: %s",
        {k: v for k, v in summary.items() if v is not None},
    )
    return summary


@shared_task(name="bolivian_laws.scrape_and_ingest_all")
def scrape_and_ingest_all(
    *,
    since_days: int | None = None,
    max_entries_per_source: int | None = None,
) -> list[str]:
    """Fan out one :func:`scrape_and_ingest_source` task per known source.

    Returns the list of enqueued task IDs so callers can track them
    (e.g. via ``GroupResult``) if desired.
    """
    from opencontractserver.bolivian_laws.scrapers import SCRAPERS

    task_ids: list[str] = []
    for source_key in SCRAPERS:
        async_result = scrape_and_ingest_source.delay(
            source_key,
            since_days=since_days,
            max_entries=max_entries_per_source,
        )
        task_ids.append(async_result.id)
    return task_ids
