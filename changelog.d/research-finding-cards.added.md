- **Finding cards are an outcome of deep research, not a separate feature.**
  `record_finding` (`opencontractserver/tasks/research_tasks.py`) now takes
  optional structured fields — `as_of_date`, `applicable_process`,
  `authority_status`, a half-open `effective_interval`, the cited authority's
  effective date, `confidence` and `unresolved_qualifications` — validated
  all-or-nothing so a half-filled card can never be stored. They ride in the
  existing `ResearchReport.findings` JSON; no new model, mutation or endpoint.
  The schema lives in `opencontractserver/enrichment/finding_cards.py`.
- **Anachronistic citations are refused.** A card whose cited authority takes
  effect after the date it is cited for is rejected with an error telling the
  agent to find the version in force instead. A run had cited the revised
  Planning Guide (effective 2026-07-11) as the authority for 2026-07-10.
- **Reports open with the takeaway.** `ResearchReportService.finalize` emits a
  `[component:research-findings]` CAML marker above the prose when a run
  recorded any card, rendered by a new embed in the existing CAML component
  registry. Executive summary and report body were already produced by
  `finalize_report`.
- **Deep research can target a Corpus Group** (`ResearchReport.corpus_group`,
  migration `research.0005`). `start_deep_research` takes an optional
  `corpus_group_slug`; a group the caller cannot see is refused rather than
  silently narrowed. A new `search_across_group` closure fans retrieval over
  the group's visible corpora and registers each hit's annotation id into the
  citation whitelist, preserving the closed-citation-graph invariant that a
  plain `search_across_corpora` tool would have broken.
- **Group-scoped runs are told the cross-corpus tool exists.** The mission
  section read "explore the corpus" and never mentioned `search_across_group`,
  so the first group-scoped run answered from the anchor corpus alone — the tool
  was wired up and never called. `build_deep_research_system_prompt` now takes
  `corpus_group_title` and states that `similarity_search` sees only the anchor
  while `search_across_group` reaches the group.
- **`unresolved_qualifications` cannot be empty on a card.** A blank list is
  indistinguishable from a field nobody filled in, so "we looked and found none"
  and "we never looked" rendered identically. An explicit statement is now
  required either way.
- **Cross-corpus hits are truncated** to `RESEARCH_CITABLE_PASSAGE_PREVIEW_CHARS`
  like `find_citable_passages`. Full text per hit multiplies by the group's
  member count; the first cross-corpus run exhausted its token budget and
  finalised as a salvage composition.
