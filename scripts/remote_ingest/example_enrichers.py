#!/usr/bin/env python3
"""
Example enrichers for the remote-ingest worker's pre-processing stage.

Each function is a complete, runnable enricher: ``(EnricherContext) -> Enrichment``.
Use them directly or copy them as a starting point. Wire one in with:

    docker compose -f remote_worker.yml run --rm worker run \
        --enricher example_enrichers:filename_metadata \
        --enricher example_enrichers:effective_date_annotations \
        --enricher example_enrichers:contract_type_label

(The module is importable because ``/app/scripts/remote_ingest`` is on the path
inside the worker container.)

These examples emit BOTH kinds of document metadata so you can see the
difference:

* ``custom_meta`` — a freeform JSON blob stored on ``Document.custom_meta``.
* ``metadata`` (via ``metadata_field``) — typed values in the corpus
  Column/Datacell metadata schema (what the UI shows as document metadata, the
  successor to the old "metadata annotations"). These are corpus-scoped, typed,
  and queryable.
"""

from __future__ import annotations

import re
from datetime import datetime

from enrichers import (
    DOC_TYPE_LABEL,
    TOKEN_LABEL,
    EnricherContext,
    Enrichment,
    label_def,
    metadata_field,
)

# --- 1. Structured metadata from the file path -----------------------------
# Fort Worth contracts are named like "058000-R3 - General - Contract - Acme.pdf".
_FW_NAME = re.compile(
    r"(?P<number>\d{6})-(?P<rev>[A-Z0-9]+)\s*-\s*(?P<category>[^-]+)-"
)


def filename_metadata(ctx: EnricherContext) -> Enrichment:
    """Parse the contract number / revision / category out of the file path and
    attach them as TYPED corpus metadata (datacells), plus the raw path as a
    freeform custom_meta value."""
    name = ctx.rel_path.rsplit("/", 1)[-1]
    enr = Enrichment(custom_meta={"source_path": ctx.rel_path})
    m = _FW_NAME.search(name)
    if m:
        enr.metadata.extend(
            [
                metadata_field("Contract Number", m.group("number")),
                metadata_field("Revision", m.group("rev")),
                metadata_field("Category", m.group("category").strip()),
            ]
        )
    return enr


# --- 2. Token annotations + a typed DATE datacell for detected dates -------
_DATE = re.compile(
    r"\b(?P<month>January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+(?P<day>\d{1,2}),?\s+(?P<year>\d{4})\b"
)
_DATE_LABEL = "DETECTED_DATE"


def effective_date_annotations(ctx: EnricherContext) -> Enrichment:
    """Tag every long-form date with a DETECTED_DATE token annotation, and record
    the FIRST date as a typed DATE metadata datacell ("Effective Date")."""
    enr = Enrichment(
        annotation_labels={_DATE_LABEL: label_def(_DATE_LABEL, TOKEN_LABEL)}
    )
    first_iso: str | None = None
    for match in ctx.find_token_matches(_DATE):
        enr.annotations.append(ctx.token_annotation(_DATE_LABEL, match))
        if first_iso is None:
            try:
                first_iso = datetime.strptime(
                    match.text.replace(",", ""), "%B %d %Y"
                ).strftime("%Y-%m-%d")
            except ValueError:
                first_iso = None
    if first_iso:
        enr.metadata.append(
            metadata_field("Effective Date", first_iso, data_type="DATE")
        )
    return enr


# --- 3. Document-type label + a CHOICE metadata datacell -------------------
def contract_type_label(ctx: EnricherContext) -> Enrichment:
    """Classify the document, applying both a DOC_TYPE_LABEL and a typed CHOICE
    metadata datacell ("Contract Type")."""
    text = ctx.content.lower()
    if "construction" in text:
        value = "Construction-Related"
    elif "amendment" in text or "renewal" in text:
        value = "Amendment"
    else:
        value = "General"

    label = f"contract:{value}"
    return Enrichment(
        doc_labels=[label],
        doc_label_defs={label: label_def(label, DOC_TYPE_LABEL, icon="file-text")},
        metadata=[
            metadata_field(
                "Contract Type",
                value,
                data_type="CHOICE",
                validation_config={
                    "choices": ["Construction-Related", "Amendment", "General"]
                },
            )
        ],
    )
