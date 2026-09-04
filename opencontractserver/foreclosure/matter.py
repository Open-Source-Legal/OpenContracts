"""Building a foreclosure matter from a corpus of recorded instruments.

Each document in the corpus is one recorded instrument. This module reads the
instrument type and the dates off each document's extracted text and assembles
the matter payload the compliance ruleset expects.

# What is read from documents, and what is not

Dates that appear on the face of a recorded instrument — the recording date,
the date mailed to the trustor, the publication and posting dates — are read
from the text.

Facts that do *not* appear on any recorded instrument are not invented. The
loan's purpose, the property's occupancy, whether a reinstatement was tendered
and refused: none of these are printed on a Notice of Default. They come from
``Corpus.custom_meta`` or from the analyzer's input, and where they are absent
the ruleset reports ``INSUFFICIENT RECORD`` rather than guessing. That is the
intended behaviour — a compliance finding built on an assumed fact is worse
than no finding.
"""

from __future__ import annotations

import datetime
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Instrument kinds as the ruleset's serde representation expects them.
NOTICE_OF_DEFAULT = "notice_of_default"
NOTICE_OF_SALE = "notice_of_sale"
TRUSTEES_DEED = "trustees_deed_upon_sale"
SUBSTITUTION_OF_TRUSTEE = "substitution_of_trustee"
ASSIGNMENT = "assignment_of_deed_of_trust"
RECONVEYANCE = "reconveyance"
RESCISSION = "rescission_of_notice_of_default"
DEED_OF_TRUST = "deed_of_trust"

# Ordered most-specific first. A Notice of Default recites the deed of trust it
# secures, so a naive substring scan would classify it as a deed of trust; the
# match that starts earliest in the text wins, and headings are searched before
# body text by the caller.
_INSTRUMENT_PATTERNS: list[tuple[str, str]] = [
    ("rescission of notice of default", RESCISSION),
    ("notice of default", NOTICE_OF_DEFAULT),
    ("notice of trustee's sale", NOTICE_OF_SALE),
    ("notice of trustees sale", NOTICE_OF_SALE),
    ("notice of sale", NOTICE_OF_SALE),
    ("trustee's deed upon sale", TRUSTEES_DEED),
    ("trustees deed upon sale", TRUSTEES_DEED),
    ("substitution of trustee", SUBSTITUTION_OF_TRUSTEE),
    ("assignment of deed of trust", ASSIGNMENT),
    ("full reconveyance", RECONVEYANCE),
    ("deed of trust", DEED_OF_TRUST),
]

_DATE_FORMATS = ("%B %d, %Y", "%B %d %Y", "%m/%d/%Y", "%Y-%m-%d", "%b %d, %Y")

_RECORDING_LABELS = ("Recording Date", "Date Recorded", "Recorded on")
_MAILING_LABELS = ("Date Mailed to Trustor", "Date Mailed", "Mailed on")
_PUBLICATION_LABELS = ("First Publication Date", "Date of First Publication")
_POSTING_LABELS = ("Date Posted", "Posted on")

_INSTRUMENT_NUMBER_RE = re.compile(
    r"instrument\s+no\.?\s*:?\s*([0-9][0-9\-]*)", re.IGNORECASE
)


def classify_instrument(text: str) -> str | None:
    """Identify the instrument kind, or ``None`` if the text does not say.

    The earliest match wins so that a specific heading outranks a passing
    mention later in the body.
    """
    if not text:
        return None
    lowered = text.lower()

    best: tuple[int, str] | None = None
    for needle, kind in _INSTRUMENT_PATTERNS:
        position = lowered.find(needle)
        if position == -1:
            continue
        if best is None or position < best[0]:
            best = (position, kind)
    return best[1] if best else None


def parse_date(value: str) -> datetime.date | None:
    """Parse a date in any of the forms these instruments use."""
    cleaned = value.strip().rstrip(".,;")
    for fmt in _DATE_FORMATS:
        try:
            return datetime.datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    return None


def find_labelled_date(text: str, labels: tuple[str, ...]) -> datetime.date | None:
    """Find a date following any of ``labels``."""
    if not text:
        return None

    lowered = text.lower()
    for label in labels:
        position = lowered.find(label.lower())
        if position == -1:
            continue
        tail = text[position + len(label) :].lstrip(": \t ")
        # These dates run at most three tokens ("January 15, 2024").
        candidate = " ".join(tail.split()[:3])
        parsed = parse_date(candidate)
        if parsed is not None:
            return parsed
    return None


def find_instrument_number(text: str) -> str | None:
    match = _INSTRUMENT_NUMBER_RE.search(text or "")
    return match.group(1) if match else None


def instrument_from_text(
    text: str,
    *,
    title: str = "",
    document_id: Any = None,
) -> dict[str, Any] | None:
    """Build one recorded-instrument payload from a document's text.

    The title is searched for the instrument kind before the body, for the same
    reason headings beat body text: the title names what the document *is*.

    Returns ``None`` when the kind or the recording date cannot be established
    — an instrument the ruleset cannot place in the timeline is better omitted
    than guessed at, and its absence surfaces as ``INSUFFICIENT RECORD``.
    """
    kind = classify_instrument(title) or classify_instrument(text)
    if kind is None:
        logger.info("Document %s: instrument type not recognised", document_id)
        return None

    recorded = find_labelled_date(text, _RECORDING_LABELS)
    if recorded is None:
        logger.info(
            "Document %s: classified as %s but no recording date found",
            document_id,
            kind,
        )
        return None

    payload: dict[str, Any] = {
        "kind": kind,
        "recorded_date": recorded.isoformat(),
        "instrument_number": find_instrument_number(text),
        "mailed_date": None,
        "first_publication_date": None,
        "posted_date": None,
        "provenance": None,
    }

    mailed = find_labelled_date(text, _MAILING_LABELS)
    if mailed:
        payload["mailed_date"] = mailed.isoformat()

    published = find_labelled_date(text, _PUBLICATION_LABELS)
    if published:
        payload["first_publication_date"] = published.isoformat()

    posted = find_labelled_date(text, _POSTING_LABELS)
    if posted:
        payload["posted_date"] = posted.isoformat()

    if document_id is not None:
        payload["provenance"] = {
            "document_id": str(document_id),
            "page": None,
            "bbox": None,
            "snippet": None,
        }

    return payload


def _read_text(document: Any) -> str:
    """Read a document's extracted text, tolerating an absent extract."""
    extract = getattr(document, "txt_extract_file", None)
    if not extract:
        return ""
    try:
        return extract.read().decode("utf-8")
    except Exception as exc:  # pragma: no cover - storage-dependent
        logger.warning("Could not read text for document %s: %s", document.id, exc)
        return ""


# Facts that never appear on a recorded instrument and must be supplied.
_MATTER_FACT_KEYS = (
    "sale_date",
    "payoff_date",
    "loan_purpose",
    "occupancy",
    "dwelling_units",
    "default_rate_percent",
    "county",
)

_MATTER_LIST_KEYS = (
    "postponements",
    "reinstatement_tenders",
    "payoff_requests",
)


def build_matter(
    *,
    matter_id: str,
    documents: list[Any],
    facts: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[Any]]:
    """Assemble the matter payload for the compliance ruleset.

    ``facts`` supplies what the instruments cannot: the sale date, the loan's
    purpose, occupancy, and any tenders, postponements or payoff requests.

    Returns the payload and the list of documents that could not be read as
    recorded instruments, so the caller can report them rather than silently
    dropping them.
    """
    facts = facts or {}

    instruments: list[dict[str, Any]] = []
    unrecognised: list[Any] = []

    for document in documents:
        payload = instrument_from_text(
            _read_text(document),
            title=getattr(document, "title", "") or "",
            document_id=getattr(document, "id", None),
        )
        if payload is None:
            unrecognised.append(document)
        else:
            instruments.append(payload)

    matter: dict[str, Any] = {
        "matter_id": matter_id,
        "county": None,
        "instruments": instruments,
        "sale_date": None,
        "postponements": [],
        "reinstatement_tenders": [],
        "payoff_requests": [],
        "payoff_date": None,
        "loan_purpose": None,
        "occupancy": None,
        "dwelling_units": None,
        "default_rate_percent": None,
    }

    for key in _MATTER_FACT_KEYS:
        if facts.get(key) is not None:
            matter[key] = facts[key]

    for key in _MATTER_LIST_KEYS:
        if facts.get(key):
            matter[key] = facts[key]

    return matter, unrecognised
