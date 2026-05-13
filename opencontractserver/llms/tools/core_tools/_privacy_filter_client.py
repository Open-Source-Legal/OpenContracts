"""Async HTTP client for the privacy-filter PII-detection microservice.

The client takes a single text string, splits it into overlapping chunks,
calls ``POST /v1/detect`` for each chunk, then re-maps detection offsets
back into the input string and de-duplicates across chunk overlap regions.

All offsets in the returned ``Detection`` records are relative to the
``text`` argument passed in. Callers that scan a slice of a larger document
are responsible for shifting offsets into the outer coordinate space.
"""

from __future__ import annotations

import logging
from typing import TypedDict

import httpx
from django.conf import settings

from opencontractserver.constants.document_processing import (
    PRIVACY_FILTER_CHUNK_OVERLAP as CHUNK_OVERLAP,
)
from opencontractserver.constants.document_processing import (
    PRIVACY_FILTER_CHUNK_SIZE as CHUNK_SIZE,
)

logger = logging.getLogger(__name__)

# Track whether the empty-API-key warning has already been emitted in this
# process so logs don't grow proportional to PII-scan call volume.
_warned_about_missing_api_key = False


class Detection(TypedDict):
    entity_group: str
    score: float
    start: int
    end: int
    text: str


async def adetect_pii(text: str) -> list[Detection]:
    """Detect PII in ``text``. Returns a list of detections with offsets
    relative to ``text``.
    """
    if not text:
        return []

    base_url = (getattr(settings, "PRIVACY_FILTER_URL", "") or "").rstrip("/")
    api_key = getattr(settings, "PRIVACY_FILTER_API_KEY", "") or ""
    timeout = float(getattr(settings, "PRIVACY_FILTER_TIMEOUT_SECONDS", 30))
    if not base_url:
        raise RuntimeError(
            "Privacy-filter service is not configured (PRIVACY_FILTER_URL is empty)."
        )

    if not api_key:
        # Compose's `${VAR:-}` substitution leaves the service running with
        # an empty key when the operator forgot to export it — there's no
        # external port mapping today, but any caller on the docker bridge
        # could POST unauthenticated. Surface this once per process so it
        # shows up in logs instead of silently shipping with no auth.
        global _warned_about_missing_api_key
        if not _warned_about_missing_api_key:
            logger.warning(
                "PRIVACY_FILTER_URL is set but PRIVACY_FILTER_API_KEY is empty; "
                "requests will be sent unauthenticated. Set PRIVACY_FILTER_API_KEY "
                "to gate access to the privacy-filter service."
            )
            _warned_about_missing_api_key = True

    detect_url = f"{base_url}/v1/detect"
    headers = {"X-API-Key": api_key, "Content-Type": "application/json"}

    # Track the index of each unique (start, end, group) detection in
    # ``results`` so that when chunk overlap yields the same span twice, we
    # keep the higher-confidence score rather than the first-seen score.
    seen: dict[tuple[int, int, str], int] = {}
    results: list[Detection] = []

    async with httpx.AsyncClient(timeout=timeout) as client:
        for chunk_start in _iter_chunk_starts(len(text)):
            chunk = text[chunk_start : chunk_start + CHUNK_SIZE]
            # Surface transport-level failures (timeouts, DNS, connection
            # refused, TLS errors, …) as plain RuntimeError. The agent tool
            # fault-tolerance layer turns RuntimeError into an error string
            # the LLM can react to; letting raw httpx exceptions propagate
            # would bypass that contract.
            try:
                resp = await client.post(
                    detect_url, json={"text": chunk}, headers=headers
                )
            except httpx.HTTPError as exc:
                raise RuntimeError(
                    f"privacy-filter request failed: {exc.__class__.__name__}: {exc}"
                ) from exc
            if resp.status_code >= 400:
                raise RuntimeError(
                    f"privacy-filter returned {resp.status_code}: {resp.text[:200]}"
                )
            data = resp.json()
            for det in data.get("detections", []):
                start = chunk_start + int(det["start"])
                end = chunk_start + int(det["end"])
                group = str(det["entity_group"])
                if start < 0 or end > len(text) or start >= end:
                    logger.warning(
                        "privacy-filter: skipping out-of-bounds detection "
                        "start=%s end=%s group=%s",
                        start,
                        end,
                        group,
                    )
                    continue
                key = (start, end, group)
                score = float(det["score"])
                existing_index = seen.get(key)
                if existing_index is not None:
                    # Same span detected in an overlapping chunk — keep the
                    # higher-confidence score so the eventual annotation
                    # reflects the model's most confident reading.
                    if score > results[existing_index]["score"]:
                        results[existing_index]["score"] = score
                    continue
                seen[key] = len(results)
                results.append(
                    Detection(
                        entity_group=group,
                        score=score,
                        start=start,
                        end=end,
                        text=text[start:end],
                    )
                )
    return results


def _iter_chunk_starts(total_len: int) -> list[int]:
    """Return chunk start offsets covering ``[0, total_len)``.

    Each chunk is up to ``CHUNK_SIZE`` chars; consecutive chunks overlap by
    ``CHUNK_OVERLAP`` so that detections spanning a boundary are still seen
    in at least one chunk's window.

    Note: when ``total_len`` falls just past a chunk boundary (e.g.
    ``CHUNK_SIZE + 1``), the final emitted ``pos`` can produce a chunk that
    overlaps the *previous* chunk by significantly more than
    ``CHUNK_OVERLAP``. That's intentional — it keeps the loop branch-free
    and the over-coverage is harmless because de-duplication on
    ``(start, end, group)`` collapses any duplicate detections in the
    overlapped region back down to a single result.
    """
    if total_len <= CHUNK_SIZE:
        return [0]
    step = CHUNK_SIZE - CHUNK_OVERLAP
    starts: list[int] = []
    pos = 0
    # Emit every chunk that doesn't yet reach total_len.
    while pos + CHUNK_SIZE < total_len:
        starts.append(pos)
        pos += step
    # The final chunk reaches (or extends past) total_len; Python slicing
    # clamps gracefully so we don't need to truncate. See note above re:
    # the over-overlap case when total_len lands just past a chunk
    # boundary.
    starts.append(pos)
    return starts
