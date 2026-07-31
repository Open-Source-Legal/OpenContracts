- **`find_citable_passages(document_id=…)` could never match in an authority
  corpus.** `AnnotationService.search_corpus_annotation_text` filtered
  `document_id` directly, but structural annotations carry `document_id=None`
  and reach their document through `structural_set` — so every document-scoped
  lookup reported "no passage contains X". The failure is silent: a research
  agent retries with shorter and shorter phrases until its token budget is
  gone. Observed: twelve consecutive misses, including for "Form" and
  "application", ending in a salvage report with zero findings. Same root cause
  as the document-less cross-corpus hits fixed earlier in
  `llms/tools/core_tools/multi_corpus.py`.
- **`gpt-4.1` was sized as an 8K-context model.** `MODEL_CONTEXT_WINDOWS` falls
  back to longest-prefix matching, so every unlisted `gpt-4*` name inherited the
  bare `gpt-4` entry (8,192) — a ~128x under-estimate for a model holding ~1M.
  Compaction sized itself against the fiction and
  `get_remaining_context_budget` reported a nearly-exhausted budget to an agent
  that had barely started. The gpt-4.1 family is now listed explicitly, with a
  note on the ordering hazard.
- **`search_across_group` fan-out is bounded.** `k` is per corpus, so `k=10`
  over a ten-member group returned 100 passages in one tool result — and the
  whole history is resent on every later model call. One run burned 2.03M
  cumulative input tokens across 11 tool calls. `k` is now capped per corpus
  and the total row count ceilinged, with an explicit note when hits are
  dropped.
- **Deep-research tool calls are recorded.** `append_tool_call` existed, was
  tested, and was never called, so every report carried an empty audit log and
  the Run details tab had nothing to show. Research closures are now wrapped so
  each call logs its tool, summarised arguments and result shape.
- **Citable anchors were confined to the anchor corpus.** `find_citable_passages`
  searched only the run's own corpus, so on a group-scoped run the agent could
  see a sibling corpus through `search_across_group` and still never obtain a
  quotable anchor from it — every kept citation resolved to the anchor by
  construction, which reads as "the group was not used". It now fans across the
  group's visible corpora (per-corpus permission filtering, merged
  tightest-passage-first).
