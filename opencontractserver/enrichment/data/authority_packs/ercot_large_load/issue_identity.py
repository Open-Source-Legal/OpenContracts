"""Shared identity classification for ERCOT issue attachments."""

from __future__ import annotations

from opencontractserver.enrichment.authority_sources import (
    AuthorityWeight,
    InstrumentType,
)


def classify_ercot_issue_attachment(
    descriptor: str,
    *,
    item_sequence: str | int | None = None,
) -> tuple[InstrumentType, AuthorityWeight]:
    """Classify only attachment families named explicitly by ERCOT.

    Issue pages contain a heterogeneous record: sponsor proposals, comments,
    testimony, transcripts, committee reports, ballots, and impact analyses.
    Falling back to one generic type would silently turn an unfamiliar filing
    into an official staff memorandum. Unknown labels therefore fail closed.
    """

    # ERCOT's issue-file convention reserves publisher item 1 for the
    # sponsor's original revision request. Some live PGRR/NPRR listings label
    # it only with a filename/date, so descriptor keywords are unavailable.
    # This publisher-owned sequence is positive classification evidence for
    # item 1 only; later unfamiliar items remain fail-closed below.
    if item_sequence is not None and str(item_sequence).strip().isdigit():
        if int(str(item_sequence).strip()) == 1:
            return InstrumentType.REVISION_REQUEST, AuthorityWeight.EVIDENTIARY

    lowered = descriptor.casefold()
    if "comment" in lowered:
        return InstrumentType.COMMENT, AuthorityWeight.ADVOCACY
    if "testimony" in lowered:
        return InstrumentType.TESTIMONY, AuthorityWeight.EVIDENTIARY
    if "transcript" in lowered:
        return InstrumentType.TRANSCRIPT, AuthorityWeight.EVIDENTIARY
    if any(
        marker in lowered
        for marker in (
            "report",
            "memorandum",
            "memo",
            "analysis",
            "ballot",
            "vote",
            "recommendation",
            "minutes",
        )
    ):
        return InstrumentType.STAFF_MEMO, AuthorityWeight.EVIDENTIARY
    if any(
        marker in lowered
        for marker in (
            "original",
            "proposal",
            "revision",
            "submission",
            "proposed language",
            "redline",
        )
    ):
        return InstrumentType.REVISION_REQUEST, AuthorityWeight.EVIDENTIARY
    raise ValueError(
        f"unknown ERCOT issue attachment type for descriptor {descriptor!r}"
    )
