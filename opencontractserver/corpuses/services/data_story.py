"""Corpus "data story" — aggregate the default Collection Profile extract.

The corpus-home data story (composition / timeline / value) is built from the
per-document structured profile produced by the default ``Collection Profile``
fieldset action (document type, counterparty, effective date, total value). This
service reads those datacells **corpus-as-gate** — the source corpus must be
READ-visible, and then every cell for that corpus's profile extract is read
(mirroring ``GovernanceGraphService``, which gates on the corpus and then reads
its reference rows corpus-as-gate). That keeps a public corpus's data story
anonymous-visible without flipping ``is_public`` on each individual datacell.

LLM extraction is noisy — a "date" column routinely comes back as a sentence of
reasoning, labels arrive wrapped in markdown ``**bold**``, and a numeric column
may return a stray string. Normalisation lives here (one place, server-side) so
the GraphQL contract hands the frontend clean values: a Title-Cased type, a
plain party name, an ISO ``YYYY-MM-DD`` date (parsed out of prose when needed),
and a positive float value (or null). The frontend then only has to render.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from opencontractserver.corpuses.models import Corpus
from opencontractserver.extracts.models import Datacell, Extract
from opencontractserver.shared.services.base import BaseService

# The default profile fieldset + its columns. This is the single source of truth
# for the schema — both the reader below and the setup wiring
# (``CorpusIntelligenceSetupService._setup_structured_profile``) build from it,
# so the column names the reader looks up always match what was extracted.
DEFAULT_PROFILE_FIELDSET_NAME = "Collection Profile"
PROFILE_COLUMN_TYPE = "Document type"
PROFILE_COLUMN_PARTY = "Counterparty"
PROFILE_COLUMN_DATE = "Effective date"
PROFILE_COLUMN_VALUE = "Total value"

# The add_document CorpusAction name (the action that keeps the profile growing
# as documents arrive). Kept here so the action + its accumulating Extract are
# found by ``get_or_create`` on every setup, never duplicated.
PROFILE_ACTION_NAME = "Collection profile"

# Column extraction specs. Generalises beyond contracts: type / party / date /
# value describe most document collections. Output values are normalised by the
# reader (markdown stripped, dates parsed out of prose, value coerced), so the
# prompts can stay forgiving.
PROFILE_COLUMN_SPECS: list[dict[str, str]] = [
    {
        "name": PROFILE_COLUMN_TYPE,
        "output_type": "str",
        "query": (
            "What kind of document or agreement is this? Reply with a short 2-4 "
            'word category such as "Renewal Notice", "Grant Agreement", '
            '"Interlocal Agreement", "Cooperative Purchasing Agreement", '
            '"Amendment", or "Professional Services Agreement".'
        ),
        "instructions": "Return ONLY the short Title-Cased category phrase. No explanation.",
    },
    {
        "name": PROFILE_COLUMN_PARTY,
        "output_type": "str",
        "query": (
            "Who is the primary organization or party this document concerns (the "
            "vendor, agency, grantee, or counterparty)? Give the organization name only."
        ),
        "instructions": "Return only the organization/entity name, no extra words.",
    },
    {
        "name": PROFILE_COLUMN_DATE,
        "output_type": "str",
        "query": (
            "What is the effective date or start date of this agreement? Return it "
            "as an ISO date YYYY-MM-DD."
        ),
        "instructions": (
            "Return only an ISO date YYYY-MM-DD. If none is stated, return an empty string."
        ),
    },
    {
        "name": PROFILE_COLUMN_VALUE,
        "output_type": "float",
        "query": (
            "What is the total dollar value, maximum compensation, or grant amount "
            "of this agreement, as a plain number with no currency symbol or "
            "commas? If no amount is stated, return 0."
        ),
        "instructions": "Return only the numeric amount, e.g. 10537030.00, or 0 if none.",
    },
]


def get_or_create_default_profile_fieldset(creator: Any):
    """Idempotently return the shared ``Collection Profile`` fieldset + columns.

    Returns ``(fieldset, created)``. Safe to call on every setup — a missing
    column is added, an existing one is left untouched.
    """
    from opencontractserver.extracts.models import Column, Fieldset

    fieldset, created = Fieldset.objects.get_or_create(
        name=DEFAULT_PROFILE_FIELDSET_NAME,
        defaults={
            "description": (
                "Per-document profile (type, counterparty, effective date, value) "
                "powering the corpus-home data story."
            ),
            "creator": creator,
        },
    )
    for i, spec in enumerate(PROFILE_COLUMN_SPECS):
        Column.objects.get_or_create(
            fieldset=fieldset,
            name=spec["name"],
            defaults=dict(
                query=spec["query"],
                output_type=spec["output_type"],
                instructions=spec["instructions"],
                creator=creator,
                display_order=i,
                is_manual_entry=False,
            ),
        )
    return fieldset, created


_MONTHS = {
    name.lower(): i
    for i, name in enumerate(
        [
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ],
        start=1,
    )
}
_MONTH_DATE_RE = re.compile(
    r"\b(" + "|".join(_MONTHS) + r")\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b",
    re.IGNORECASE,
)
_ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


@dataclass
class ProfileRow:
    document_id: int
    title: str
    slug: str | None
    type: str | None
    party: str | None
    effective_date: str | None
    value: float | None


@dataclass
class DataStory:
    total_documents: int
    profiles: list[ProfileRow]


def _cell_value(dc: Datacell) -> Any:
    data = dc.data
    if isinstance(data, dict):
        return data.get("data", None)
    return data


def _clean_label(value: Any) -> str | None:
    """Strip markdown emphasis / trailing punctuation; collapse whitespace.

    A label that comes back as a whole sentence (the model explaining itself) is
    not a usable category — cap length and drop anything that is clearly prose.
    """
    if value is None:
        return None
    s = re.sub(r"\s+", " ", str(value).replace("*", "").strip()).strip(" .;:")
    if not s:
        return None
    # A genuine type/party is short; a multi-clause sentence is the model
    # reasoning, not a value — reject it rather than render a paragraph.
    if len(s) > 60 or s.count(" ") > 8:
        return None
    return s


def _parse_date(value: Any) -> str | None:
    """Return an ISO ``YYYY-MM-DD`` parsed from the cell, or None.

    Handles a clean ISO value, and recovers a ``Month DD, YYYY`` date out of the
    reasoning prose the model sometimes returns instead of just the date.
    """
    if value is None:
        return None
    s = str(value)
    m = _ISO_DATE_RE.search(s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = _MONTH_DATE_RE.search(s)
    if m:
        month = _MONTHS[m.group(1).lower()]
        day = int(m.group(2))
        year = int(m.group(3))
        if 1 <= day <= 31 and 1900 <= year <= 2100:
            return f"{year:04d}-{month:02d}-{day:02d}"
    return None


def _parse_value(value: Any) -> float | None:
    """Coerce a positive dollar amount; None for zero/absent/garbled."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) if value > 0 else None
    m = _NUMBER_RE.search(str(value))
    if not m:
        return None
    try:
        f = float(m.group(0).replace(",", ""))
    except ValueError:
        return None
    return f if f > 0 else None


class CorpusDataStoryService(BaseService):
    """Assemble the per-document profile rows for one corpus's data story."""

    @classmethod
    def build(
        cls, user: Any, corpus_pk: int, *, request: Any = None
    ) -> DataStory | None:
        # READ gate: the corpus must be visible to the caller (a public corpus is
        # visible to anonymous users). Returns None — the resolver maps that to a
        # null field and the embed self-hides.
        corpus = (
            BaseService.filter_visible(Corpus, user, request=request)
            .filter(id=corpus_pk)
            .first()
        )
        if corpus is None:
            return None

        # Corpus-as-gate: the corpus READ above is the gate, so cells are read
        # without per-row user filtering. NOTE: this is intentionally NOT
        # equivalent to per-document visibility — a private document inside a
        # readable corpus (e.g. a cross-owner doc that
        # ``_propagate_public_status_to_documents`` skipped) will still surface
        # its profile here, unlike ``CorpusType.documents``. Acceptable for this
        # aggregate surface; do not copy this pattern where per-doc privacy matters.
        #
        # Pin to a single canonical extract. Setup ``get_or_create``s exactly one
        # Collection-Profile extract per corpus, but guard against historical
        # duplicates by taking the most recent rather than silently mixing cells
        # across extracts (which would let a stale prior run win per document).
        profile_extract = (
            Extract.objects.filter(
                corpus_id=corpus_pk,
                fieldset__name=DEFAULT_PROFILE_FIELDSET_NAME,
            )
            .order_by("-created")
            .first()
        )
        if profile_extract is None:
            return DataStory(total_documents=0, profiles=[])

        cells = (
            Datacell.objects.filter(
                extract_id=profile_extract.id,
                completed__isnull=False,
            )
            .select_related("column", "document")
            .order_by("document_id")
        )

        by_doc: dict[int, dict[str, Any]] = {}
        for dc in cells:
            row = by_doc.setdefault(dc.document_id, {"_doc": dc.document})
            row[dc.column.name] = _cell_value(dc)

        profiles: list[ProfileRow] = []
        for doc_id, row in by_doc.items():
            doc = row["_doc"]
            profiles.append(
                ProfileRow(
                    document_id=doc_id,
                    title=doc.title or "Untitled document",
                    slug=getattr(doc, "slug", None),
                    type=_clean_label(row.get(PROFILE_COLUMN_TYPE)),
                    party=_clean_label(row.get(PROFILE_COLUMN_PARTY)),
                    effective_date=_parse_date(row.get(PROFILE_COLUMN_DATE)),
                    value=_parse_value(row.get(PROFILE_COLUMN_VALUE)),
                )
            )

        return DataStory(total_documents=len(profiles), profiles=profiles)
