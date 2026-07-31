- **A second finding-card shape for project readiness.** The existing card is
  built around a half-open effective interval and answers "which process
  governed on date X". A readiness question — which requirements apply, which
  forms are needed, what is still unknown — has no interval, and forcing it
  through the regime shape pushed the substance back into prose. `record_finding`
  now also accepts `obligation`, `owed_by`, `form_reference` and `deadline`; the
  two shapes are validated separately, cannot be mixed in one call, and carry a
  `kind` discriminator. Rendered by the existing CAML embed
  (`ResearchFindingsEmbed`).
- **The card schema is now the one the tool validates through.**
  `opencontractserver/enrichment/finding_cards.py` had become an orphan — it
  defined `FindingCard`/`FindingSet` that nothing but its own tests imported,
  while `record_finding` built a parallel dict by hand. It now defines
  `RegimeCard` and `ObligationCard`, and `record_finding` constructs through
  them, so the field list has exactly one definition. The tool keeps its own
  guard clauses for their *messages*: an agent told "unresolved_qualifications
  cannot be empty; if nothing is unresolved, say so explicitly" recovers, where
  a pydantic type error usually just gets retried.
