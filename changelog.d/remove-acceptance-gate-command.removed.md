- Removed `manage.py evaluate_griddossier_acceptance_gate`. It reached inside
  the application — calling `astart_deep_research`, building corpus agents, and
  re-deriving report quality from model rows — which made it a second
  implementation of the product's own checks, drifting from them and measuring
  itself. Most of what it scored is now enforced where it belongs: at
  `record_finding` (unclassified card, phase-triggered card with no ramp steps,
  material card with no citation, obligation with no obligor, obligor the cited
  passages never name), and its approval-vs-effectiveness check moved to a
  finalize warning (below). Its one remaining check — that a run distinguishes
  preparer / submitter / recipient / certifier from the responsible party
  somewhere — is cross-card judgement and is now a step in the procedure, not
  code. That procedure runs over the GUI and the GraphQL API:
  `docs/test_scripts/griddossier_acceptance_gate.md`.
