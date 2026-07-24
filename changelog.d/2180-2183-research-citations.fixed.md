- **Tightened deep-research citation discipline (#2180, #2181, #2182, #2183).**
  Added a `## Citation discipline` section to the deep-research system prompt
  (`build_deep_research_system_prompt` in
  `opencontractserver/research/constants.py`) that instructs the agent to: anchor
  the passage whose own words support a claim and never a bare section header —
  reaching for `search_exact_text_as_sources` to pull a pinpoint anchor (#2180);
  cite the document that actually *contains* the language, following any
  incorporation-by-reference / cross-reference hop to its source before anchoring
  (#2181); leave task/prompt-derived background *uncited* rather than forcing a
  corpus anchor onto it (#2182); and state each claim exactly once inside a
  single `<cite>` tag, never as a plain sentence followed by a cited restatement
  (#2183).
- **Added a finalize-time weak-citation lint (#2180).** `_render_citations`
  (`opencontractserver/research/services/research_reports.py`) now tags each
  citation with `anchor_is_header`, and `ResearchReportService.finalize` records
  a concise warning (surfaced in the report's UI warning chips) when a footnote
  resolves to a section header instead of a supporting passage. Detection keys on
  the anchor's **annotation label** (`RESEARCH_HEADER_ANCHOR_LABELS`:
  `OC_SECTION` + the LlamaParse heading labels `Title` / `Section Header` /
  `Heading` / `Page Header`, matched case-/separator-insensitively) — *not* on
  `Annotation.structural`, which the parsing pipeline sets on the entire layout
  layer (body paragraphs, tables, sentence chunks) and which the bookmark-derived
  OC_SECTION headers are `structural=False` for; keying on it would both flood
  false positives and miss the real #2180 headers. The lint is observational — it
  never rewrites report prose.
- **Confirmed the report composer is not the source of the #2183 duplication.**
  The finalize path emits the agent's `markdown_body` verbatim (cite-rendered)
  and the salvage path renders each finding exactly once; the observed doubling
  was agent-authored prose (a plain sentence joined to a near-identical cited
  restatement), now addressed by the prompt rule above. New regression tests
  (`test_finalize_renders_each_claim_once`,
  `test_compose_salvage_body_renders_each_finding_once`) lock in single-render
  behavior so a future composer change can't reintroduce it.
