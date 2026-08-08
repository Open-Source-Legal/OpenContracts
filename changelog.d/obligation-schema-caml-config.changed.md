- Obligation finding cards are no longer pinned to one project's thresholds.
  `RAMP_STEPS_MW = (25, 50, 75, 100)` was a constant in
  `enrichment/finding_cards.py` and was *enforced* — a card naming any other
  value was refused — which made the card useful for exactly one Texas
  interconnection study and silently wrong for anything else. The thresholds an
  obligation attaches at belong to the subject, not the software: an
  employment-law review turns on 50 and 250 employees, a fund review on AUM
  tiers.
  A corpus now declares its own scale in its `Readme.CAML`:
  `[component:obligation-schema unit=MW steps=25,50,75,100 label=ramp]`, read
  via the new `caml_intelligence.parse_component_props` and modelled by
  `ObligationSchema`. Configured where the corpus already describes itself
  rather than in a settings column nobody discovers, and tolerant of a typo —
  a malformed marker degrades to the default instead of failing the run.
  With no configuration the card still works and is still guarded: a
  PHASE_TRIGGERED obligation must say where it bites, but nothing constrains
  the values, because there is no list to constrain them against.
  Field renames follow: `applies_at_mw` → `applies_at` (plus a system-stamped
  `threshold_unit`, so a bare `75` in a stored card is readable a year later),
  and `energization_date` → `commencement_date`. The `recipient` description no
  longer names ERCOT/TSP/DSP.
