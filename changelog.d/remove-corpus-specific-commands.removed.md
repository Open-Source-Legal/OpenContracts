- Removed four management commands and their data, all specific to one
  deployment rather than to the product:
  `evaluate_grid_dossier_gold_questions`, `evaluate_grid_dossier_gold_tests`
  and `seed_grid_dossier_poison_filing` are gone for the same reason
  `evaluate_griddossier_acceptance_gate` was — evaluation tooling that reaches
  inside the application is a second implementation of the product's own
  checks, free to drift from them and, in the end, measuring itself. None had a
  test importing it.
  `load_grid_dossier_groups` was **moved**, not deleted, to an external
  deployment repo (`ERCOT_LOAD_Grid_Dossier`) along with its manifests, its
  597-line test suite and the gold acceptance data. A deployment's corpus
  groups are a property of that deployment; shipping the manifest in the
  product meant every install carried one customer's ERCOT topology. The
  convergence logic is unchanged and its tests still pass against a live
  install from outside the tree — writes continue to route through
  `CorpusGroupService` / `AgentConfigurationService`, so the product's
  permission invariants remain the single source of truth.
  `load_authority_pack`, `discover_authority_candidates` and
  `reconcile_authority_effective_date_states` stay: they are generic
  provisioning and maintenance, which is what management commands are for.
