- Fixed agents dating their own analysis from training data. Nothing in the
  stack told an agent what "now" is, so a persona asking it to "state the
  analysis date" got one invented: a July-2026 question answered over 2026
  authorities was reported "as of June 2024" — substantively right and
  immediately untrustworthy. `agent_factory._inject_temporal_grounding` now
  appends a computed block to every agent's system prompt (research timestamp,
  and corpus currency read from stamped `retrieved_at` source metadata when the
  corpus has it), forbids inferring an "as of" date, and forces apart the two
  date pairs temporal legal questions turn on: the date asked about vs the date
  researched, and when an authority was **approved** vs when it became
  **effective**.
- Fixed cross-corpus search hits carrying no citable identity. Authority
  corpora annotate structurally — every annotation has `document_id=None` and
  reaches its document through a shared `StructuralAnnotationSet` — so
  `search_across_corpora` returned hits with no document at all, and answers
  cited "paragraph p.0" rather than a rule section. Hits now resolve their
  document and carry `canonical_key`, `section`, `authority_weight`,
  `instrument_type`, `publisher`, `status`, `effective_from` / `effective_until`,
  `version_label` and `source_url`.
- **Version-correctness (load-bearing):** a structural set is shared by every
  sibling in a version tree, so resolution goes through the *current*
  `DocumentPath` in the searched corpus. Taking the set's first document would
  cite a superseded rule as current — precisely the error separate current and
  historical corpora exist to prevent.
- The DFW orchestrator persona now cites from those fields, ranks sources by
  `authority_weight` (controlling rule vs implementing notice vs evidentiary
  lineage) instead of listing them flat, and quotes the computed research
  timestamp rather than stating an "as of" date.
