"""The schema for a structured finding card, and the only definition of it.

A deep-research finding is ordinarily a claim plus the annotation ids that
support it. A *card* is a finding that also commits to a shape, so the report,
the interface and any downstream consumer read the same fields instead of
re-deriving them from prose.

Two shapes, because regulatory questions come in two kinds:

``RegimeCard``
    "Which process governed on date X." Built around a half-open effective
    interval, ``[start, end)``, whose **end is exclusive** — a rule superseded
    on 2026-07-11 governed all of 2026-07-10, and an inclusive end lets both
    regimes claim the boundary day.

``ObligationCard``
    "What must this project do." Built around an obligation, who owes it, the
    form that discharges it and the date it is due. A project-readiness answer
    is a list of these; forcing it through ``RegimeCard`` pushed the substance
    back into prose, which is what the card exists to prevent.

These models are what ``record_finding`` validates through
(``opencontractserver/tasks/research_tasks.py``) — the stored dict is produced
by ``model_dump()`` here, so the field list has exactly one definition. The
tool keeps its own guard clauses for the *messages*: an agent that is told
"unresolved_qualifications cannot be empty; if nothing is unresolved, say so
explicitly" recovers, where a pydantic type error usually just gets retried.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Confidence = Literal["HIGH", "MEDIUM", "LOW"]

#: Rendered for an interval with no known end. Chosen over an empty string so
#: an open interval reads as deliberate rather than as missing data.
OPEN_INTERVAL = "…"


class RegimeCard(BaseModel):
    """What governed, over what interval, on whose authority."""

    kind: Literal["REGIME"] = "REGIME"
    as_of_date: str = Field(description="The date this card answers for (YYYY-MM-DD).")
    applicable_process: str
    authority_status: str
    effective_interval_start: str | None = None
    effective_interval_end: str | None = Field(
        default=None,
        description="EXCLUSIVE. A process superseded on 2026-07-11 has end '2026-07-11'.",
    )
    primary_authority_effective_from: str | None = Field(
        default=None,
        description=(
            "Effective date of the cited authority. Must be on or before "
            "as_of_date: a document effective later cannot be what governed "
            "that day."
        ),
    )
    confidence: Confidence
    unresolved_qualifications: list[str]

    def render_interval(self) -> str:
        start = self.effective_interval_start or "unestablished"
        end = self.effective_interval_end or OPEN_INTERVAL
        return f"[{start}, {end})"

    def covers(self, iso_date: str) -> bool:
        """Whether ``iso_date`` falls inside the half-open interval.

        String comparison is safe for zero-padded ISO dates and avoids a parse
        that could raise on the model's occasional malformed value.
        """
        if self.effective_interval_start and iso_date < self.effective_interval_start:
            return False
        if self.effective_interval_end and iso_date >= self.effective_interval_end:
            return False
        return True


#: How an obligation attaches to a project. The distinction that matters:
#: "this applies to you", "this applies once you cross a threshold", and "this
#: applied only during the transition" are three different answers, and a
#: reader who cannot tell them apart cannot plan.
Applicability = Literal[
    "GENERALLY_APPLICABLE",
    "PHASE_TRIGGERED",
    "CONDITIONAL",
    "ALTERNATIVE_PATHWAY",
    "TRANSITION_ONLY",
    "NOT_APPLICABLE",
    "UNRESOLVED",
]

#: The CAML marker that configures obligation cards for a corpus, e.g.
#: ``[component:obligation-schema unit=MW steps=25,50,75,100 label=ramp]``.
#: Configuration lives in the corpus's ``Readme.CAML`` because the thresholds
#: an obligation attaches at are a property of the SUBJECT, not of the software
#: — a Texas interconnection study is evaluated at a 25/50/75/100 MW ramp, an
#: employment-law review at 50 and 250 employees, a fund review at AUM tiers.
#: Baking one set into the schema made the card useful for exactly one project.
OBLIGATION_SCHEMA_MARKER = "obligation-schema"


class ObligationSchema(BaseModel):
    """How obligation cards are scored for one corpus.

    Threshold-aware by configuration rather than by construction. With no
    configuration the card still works — it simply has no scale, so a
    PHASE_TRIGGERED obligation must say where it bites but nothing checks those
    values against a list. With a configured scale the values are also
    validated, which is what stops an agent inventing a step the project never
    planned for.
    """

    #: Unit the thresholds are measured in ("MW", "employees", "$m"). Shown to
    #: the agent and stamped onto each card so a stored card is self-describing
    #: — a bare ``75`` in a JSON column means nothing a year later.
    threshold_unit: str | None = None
    #: The steps under evaluation, ascending. Empty means "no fixed scale".
    threshold_steps: tuple[float, ...] = ()
    #: What the scale is called in prose ("ramp", "headcount"). Used in the
    #: agent-facing error messages so they read in the subject's own language.
    threshold_label: str = "threshold"

    @property
    def has_scale(self) -> bool:
        return bool(self.threshold_steps)

    def describe(self) -> str:
        """One clause naming the scale, for the agent-facing prompt."""
        if not self.has_scale:
            return ""
        steps = ", ".join(_format_step(s) for s in self.threshold_steps)
        unit = f" {self.threshold_unit}" if self.threshold_unit else ""
        return f"{self.threshold_label} steps {steps}{unit}"

    @classmethod
    def from_caml_props(cls, props: dict[str, str] | None) -> ObligationSchema:
        """Build from the props of an ``obligation-schema`` CAML marker.

        Tolerant by design: a corpus author writing prose should never break a
        research run with a typo. An unparseable ``steps`` value yields no
        scale rather than an exception, which degrades to the unconfigured
        behaviour instead of failing the run.
        """
        if not props:
            return cls()
        steps: list[float] = []
        for raw in (props.get("steps") or "").split(","):
            raw = raw.strip()
            if not raw:
                continue
            try:
                steps.append(float(raw))
            except ValueError:
                return cls(threshold_unit=props.get("unit") or None)
        return cls(
            threshold_unit=props.get("unit") or None,
            threshold_steps=tuple(sorted(set(steps))),
            threshold_label=(props.get("label") or "threshold").strip() or "threshold",
        )


def _format_step(value: float) -> str:
    """``25.0`` -> ``25``; ``1.5`` -> ``1.5``. Steps are usually whole."""
    return str(int(value)) if float(value).is_integer() else str(value)


class ObligationCard(BaseModel):
    """Something the project must do, and what is still unknown about it.

    The role and date fields exist because a single "owed_by" and a single
    "deadline" quietly conflate things a developer cannot afford to conflate.
    Whoever *prepares* a study is often not who *submits* it, and neither is
    who *certifies* it; an approval date is not an effective date is not the
    date your application is due. Where the record does not distinguish them
    the fields stay null — an absent role is not the same claim as a role that
    happens to coincide with the responsible party.
    """

    kind: Literal["OBLIGATION"] = "OBLIGATION"
    obligation: str = Field(description="What must be done.")

    # --- applicability ---------------------------------------------------
    applicability: Applicability = Field(
        description=(
            "GENERALLY_APPLICABLE (every project of this kind), PHASE_TRIGGERED "
            "(bites at a threshold — say which in applies_at), CONDITIONAL "
            "(depends on a fact about the project), ALTERNATIVE_PATHWAY (one of "
            "several routes), TRANSITION_ONLY (applied only across a rule "
            "change), NOT_APPLICABLE (checked and excluded — say why in "
            "unresolved_qualifications), UNRESOLVED (the record does not settle "
            "whether it applies)."
        )
    )
    applies_at: list[float] = Field(
        default_factory=list,
        description=(
            "Which threshold values on the corpus's configured scale this bites "
            "at. REQUIRED when applicability is PHASE_TRIGGERED — otherwise "
            "'phase-triggered' is a label, not a classification."
        ),
    )
    threshold_unit: str | None = Field(
        default=None,
        description=(
            "Unit for `applies_at`, stamped by the system from the corpus "
            "configuration. A bare number in a stored card means nothing "
            "without it."
        ),
    )

    # --- parties ---------------------------------------------------------
    responsible_party: str = Field(
        description="Who is on the hook. An obligation with no obligor cannot be acted on."
    )
    preparer: str | None = Field(
        default=None,
        description="Who prepares the material, if not the responsible party.",
    )
    submitter: str | None = Field(
        default=None, description="Who files it, if not the responsible party."
    )
    recipient: str | None = Field(
        default=None,
        description="Who receives it (the regulator, the counterparty, the filing body).",
    )
    certifier: str | None = Field(
        default=None,
        description="Who attests or certifies, where that is a distinct role.",
    )
    obligor_grounded: bool = Field(
        default=True,
        description=(
            "Whether the cited passages actually NAME responsible_party. Set by "
            "the system, not by the agent. False marks an attribution carried in "
            "from elsewhere — the obligation and the citation can both be right "
            "while the obligor is inferred."
        ),
    )

    # --- dates, each a different question ---------------------------------
    approval_date: str | None = Field(
        default=None, description="When a regulator approved the instrument."
    )
    effective_date: str | None = Field(
        default=None,
        description="When the instrument became operative. NOT the approval date.",
    )
    service_request_date: str | None = Field(
        default=None, description="When service must be / was requested."
    )
    application_date: str | None = Field(
        default=None, description="When the application must be / was filed."
    )
    deadline: str | None = Field(
        default=None, description="The date this obligation must be discharged by."
    )
    commencement_date: str | None = Field(
        default=None,
        description=(
            "Target or required date the thing being regulated begins operating "
            "(energization, occupancy, first sale)."
        ),
    )

    form_reference: str | None = Field(
        default=None,
        description="The form that discharges it, e.g. 'Protocol Section 23, Form W'.",
    )
    material: bool = Field(
        default=True,
        description=(
            "Whether this is a material obligation. A material card with no "
            "supporting citation is blocked from the final report."
        ),
    )
    confidence: Confidence
    unresolved_qualifications: list[str]

    def distinct_roles(self) -> dict[str, str]:
        """Roles the record actually distinguishes from the responsible party."""
        return {
            name: value
            for name, value in (
                ("preparer", self.preparer),
                ("submitter", self.submitter),
                ("recipient", self.recipient),
                ("certifier", self.certifier),
            )
            if value
            and value.strip()
            and value.strip() != self.responsible_party.strip()
        }

    def stated_dates(self) -> dict[str, str]:
        """Only the date kinds this card actually establishes."""
        return {
            name: value
            for name, value in (
                ("approval_date", self.approval_date),
                ("effective_date", self.effective_date),
                ("service_request_date", self.service_request_date),
                ("application_date", self.application_date),
                ("deadline", self.deadline),
                ("commencement_date", self.commencement_date),
            )
            if value and value.strip()
        }
