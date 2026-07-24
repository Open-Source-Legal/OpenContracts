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
  resolves to a section header / structural anchor instead of a supporting
  passage. Detection keys solely off `Annotation.structural` — the flag the
  parsing pipeline sets on OC_SECTION layout annotations, which are exactly the
  headers that mis-anchored in #2180. It deliberately does *not* also text-match
  filing-style headings (`ITEM 1A`, `SECTION 8`, …), because legal prose commonly
  opens an operative clause with its section number (“Section 8.1 requires …”),
  which would false-positive on real citations in contract corpora. The lint is
  observational — it never rewrites report prose.
- **Confirmed the report composer is not the source of the #2183 duplication.**
  The finalize path emits the agent's `markdown_body` verbatim (cite-rendered)
  and the salvage path renders each finding exactly once; the observed doubling
  was agent-authored prose (a plain sentence joined to a near-identical cited
  restatement), now addressed by the prompt rule above. New regression tests
  (`test_finalize_renders_each_claim_once`,
  `test_compose_salvage_body_renders_each_finding_once`) lock in single-render
  behavior so a future composer change can't reintroduce it.
