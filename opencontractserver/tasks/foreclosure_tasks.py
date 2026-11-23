"""California foreclosure compliance analyzer.

Runs the ``legalis-ca-foreclosure`` ruleset over a corpus of recorded
instruments and stores the resulting compliance report on the Analysis.

Corpus-scoped rather than document-scoped: no single instrument answers whether
the three-month period under Civ. Code § 2924(a)(2) elapsed. That question
needs the Notice of Default and the Notice of Sale together, which is what a
corpus holds.
"""

from __future__ import annotations

import logging
from typing import Any

from opencontractserver.foreclosure.client import (
    ForeclosureComplianceClient,
    ForeclosureServiceError,
)
from opencontractserver.foreclosure.matter import build_matter
from opencontractserver.shared.decorators import corpus_analyzer_task

logger = logging.getLogger(__name__)


FORECLOSURE_INPUT_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "CaliforniaForeclosureComplianceInput",
    "type": "object",
    "description": (
        "Facts that do not appear on any recorded instrument and must be "
        "supplied. Anything omitted is reported as INSUFFICIENT RECORD rather "
        "than assumed."
    ),
    "properties": {
        "sale_date": {
            "type": "string",
            "format": "date",
            "description": "Date the trustee's sale was held (YYYY-MM-DD).",
        },
        "loan_purpose": {
            "type": "string",
            "enum": ["consumer", "business_purpose"],
            "description": (
                "Gates the Homeowner Bill of Rights. Consumer-mortgage "
                "protections do not reach a business-purpose loan."
            ),
        },
        "occupancy": {
            "type": "string",
            "enum": ["owner_occupied", "non_owner_occupied", "unknown"],
        },
        "dwelling_units": {
            "type": "integer",
            "minimum": 1,
            "description": "HBOR reaches residential property of 1-4 units.",
        },
        "county": {"type": "string"},
        "payoff_date": {"type": "string", "format": "date"},
        "default_rate_percent": {
            "type": "number",
            "description": (
                "Contractual default rate. Raises a § 1671 penalty question, "
                "which the ruleset refers to a human and never decides."
            ),
        },
        "reinstatement_tenders": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "tendered_date": {"type": "string", "format": "date"},
                    "amount_sufficient": {"type": ["boolean", "null"]},
                    "accepted": {"type": "boolean"},
                },
                "required": ["tendered_date", "accepted"],
            },
        },
        "postponements": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "from_date": {"type": "string", "format": "date"},
                    "to_date": {"type": "string", "format": "date"},
                    "announced_at_sale": {"type": "boolean"},
                },
                "required": ["from_date", "to_date", "announced_at_sale"],
            },
        },
        "payoff_requests": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "requested_date": {"type": "string", "format": "date"},
                    "delivered_date": {"type": ["string", "null"], "format": "date"},
                },
                "required": ["requested_date"],
            },
        },
    },
    "additionalProperties": False,
}


@corpus_analyzer_task(input_schema=FORECLOSURE_INPUT_SCHEMA)
def california_foreclosure_compliance(
    *args,
    corpus_id: int,
    analysis_id: int,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    # California Foreclosure Compliance

    Checks a corpus of recorded instruments against Civ. Code § 2924 et seq.
    and returns a dated compliance chronology.

    ## What it checks

    - **§ 2924(a)(2)** — three months between Notice of Default and Notice of Sale
    - **§ 2924b(b)(1), (b)(2)** — service of notices on the trustor
    - **§ 2924f(b)(1)** — publication, posting and recording of the Notice of Sale
    - **§ 2924c(e)** — reinstatement right, in *business* days
    - **§ 2924g(d)** — postponement announced at the time and place of sale
    - **§ 2943(c)** — payoff demand statement within 21 days
    - **§ 2941(b), (d)** — reconveyance after payoff

    ## What it will not decide

    Whether service was reasonably calculated to reach the trustor, and whether
    a default rate is an unenforceable penalty under § 1671, come back as
    questions for a human. There is no arithmetic that settles them, and the
    ruleset does not pretend otherwise.

    ## Outcomes

    A finding is COMPLIANT, VIOLATION, REQUIRES JUDGMENT, INSUFFICIENT RECORD,
    NOT APPLICABLE, RECORD INCONSISTENT, or NOT YET IN FORCE. **Insufficient
    record is not compliance** — a missing Notice of Default reports as a gap,
    never as a pass.

    ## Status

    No rule encoding has been reviewed by a licensed attorney. The result
    records this. Output is not legal advice.
    """
    from opencontractserver.corpuses.models import Corpus
    from opencontractserver.documents.models import Document

    corpus = Corpus.objects.get(id=corpus_id)
    documents = list(Document.objects.filter(corpus=corpus).order_by("id"))

    if not documents:
        return {
            "status": "no_documents",
            "message": f"Corpus {corpus_id} contains no documents to analyse.",
            "violations": 0,
        }

    # Facts the instruments cannot supply come from the analyzer input, then
    # from the corpus metadata as a fallback.
    facts: dict[str, Any] = {}
    corpus_meta = getattr(corpus, "custom_meta", None) or {}
    if isinstance(corpus_meta, dict):
        facts.update(corpus_meta.get("foreclosure", {}) or {})
    facts.update({k: v for k, v in kwargs.items() if v is not None})

    matter, unrecognised = build_matter(
        matter_id=f"corpus-{corpus_id}",
        documents=documents,
        facts=facts,
    )

    if not matter["instruments"]:
        return {
            "status": "no_instruments_recognised",
            "message": (
                f"None of the {len(documents)} document(s) in corpus {corpus_id} "
                "could be read as a recorded instrument with a recording date. "
                "Check that the documents have been parsed and that their text "
                "carries a labelled recording date."
            ),
            "documents_examined": len(documents),
            "violations": 0,
        }

    client = ForeclosureComplianceClient()

    try:
        health = client.health()
        result = client.evaluate(matter)
    except ForeclosureServiceError as exc:
        # Surface the failure rather than reporting a clean bill of health.
        logger.error("Foreclosure compliance service failed: %s", exc)
        raise

    violations = result.violations
    judgment = result.requires_judgment
    gaps = result.insufficient_record

    logger.info(
        "Corpus %s: %d violation(s), %d requiring judgment, %d gap(s)",
        corpus_id,
        len(violations),
        len(judgment),
        len(gaps),
    )

    return {
        "status": "completed",
        "ruleset": health.get("ruleset"),
        "jurisdiction": health.get("jurisdiction"),
        "attorney_verified_rules": health.get("attorney_verified_count", 0),
        "operative_date": result.report.get("operative_date"),
        "documents_examined": len(documents),
        "instruments_recognised": len(matter["instruments"]),
        "documents_unrecognised": [str(d.id) for d in unrecognised],
        "summary": result.summary,
        "violations": len(violations),
        "findings": [
            {
                "rule_id": f.get("rule_id"),
                "rule_name": f.get("rule_name"),
                "status": f.get("status"),
                "citation": f.get("citation"),
                "version_effective_from": f.get("version_effective_from"),
                "detail": f.get("detail"),
                "workings": f.get("workings", []),
                "missing": f.get("missing", []),
            }
            for f in result.report.get("findings", [])
        ],
        "report_text": result.text,
        "disclaimer": (
            "Generated from encoded statutory rules and the dates in the "
            "record. No rule encoding has been reviewed by a licensed "
            "attorney. Not legal advice."
        ),
    }
