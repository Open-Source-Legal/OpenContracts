"""Celery tasks for the Bolivian Laws RAG service."""

from __future__ import annotations

import logging
from typing import Optional

from celery import shared_task

from opencontractserver.bolivian_laws.constants import LegalSource
from opencontractserver.bolivian_laws.services.ingestion import ingest_pdf

logger = logging.getLogger(__name__)


@shared_task(name="bolivian_laws.ingest_pdf_async")
def ingest_pdf_async(
    pdf_path: str,
    *,
    area: str,
    title: str,
    source: str = LegalSource.MANUAL,
    external_id: str = "",
    published_at: Optional[str] = None,
    metadata: Optional[dict] = None,
    user_id: Optional[int] = None,
) -> int:
    """Async wrapper around ``ingest_pdf`` for bulk ingestion via Celery.

    Returns the resulting ``BolivianLegalDocument`` primary key.
    """
    from datetime import date

    from django.contrib.auth import get_user_model

    user = None
    if user_id is not None:
        user = get_user_model().objects.filter(pk=user_id).first()

    parsed_date: Optional[date] = None
    if published_at:
        try:
            parsed_date = date.fromisoformat(published_at)
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
