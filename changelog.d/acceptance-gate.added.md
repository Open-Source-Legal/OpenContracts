- **A hard acceptance gate for the 100 MW readiness question**
  (`manage.py evaluate_griddossier_acceptance_gate`). Seven criteria: every
  obligation classified for applicability; the ramp steps compared explicitly;
  the six date kinds kept apart; every material card entailed or blocked; party
  roles distinguished; two independent adversarial reviewers; and reliability
  across repeated runs. Five criteria are deterministic reads of the stored
  report — an LLM reviewer asked "is every card classified?" will say yes about
  a report where most are — and reviewers are reserved for judgements that
  genuinely need reading.
- **Obligation cards carry applicability, party roles and six date kinds.**
  `record_finding` now takes `applicability` (one of seven classes, with
  `applies_at_mw` required for PHASE_TRIGGERED), `responsible_party` plus
  distinct `preparer` / `submitter` / `recipient` / `certifier`, and
  `approval_date` / `effective_date` / `service_request_date` /
  `application_date` / `deadline` / `energization_date` as separate fields.
- **Material obligations must be entailed or are withheld.** An uncited
  material card is refused by `record_finding` at the door; one whose citations
  do not survive the closed-citation gate is withheld by
  `ResearchReportService.finalize`, with the count surfaced as a warning so the
  omission is visible rather than silent.
- **Deep research compacts against its own budget.** History is resent on every
  model call, so cumulative input grows with the square of the tool-call count:
  a 19-call run whose history settled near 110k burned 2.1M tokens and died
  before recording a single finding. The default ratio put the trigger at 785k
  of a 1M window — unreachable, because the run is killed at its token cap
  first, so compaction never fired once.
