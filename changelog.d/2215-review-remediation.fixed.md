- **Obligation finding cards rendered a blank heading.**
  `frontend/src/components/corpuses/CorpusHome/intelligence/embeds/ResearchFindingsEmbed.tsx`
  read `card.owed_by` for the obligation-card heading, a field
  `ObligationCard` (`opencontractserver/enrichment/finding_cards.py`) has never
  had — the stored card is that model's `model_dump()`, which serialises
  `responsible_party`. Every real obligation card therefore rendered an empty
  `<h4>` in production. The component tests stayed green because they
  hand-authored mock payloads carrying `owed_by` and never asserted the heading
  at all. Fixed the field, added heading assertions on BOTH card shapes, and
  added `CardFieldContractTests` in `opencontractserver/tests/test_finding_cards.py`
  to pin the two models' full field-name sets against the TypeScript interface
  that consumes them, so the next rename fails a test instead of a page. The
  agent-facing "either/or" error at `research_tasks.py` also named the
  nonexistent `owed_by` as a parameter; corrected to `responsible_party`.
- **An obligor the evidence never names now renders as such.** The backend
  marks (rather than refuses) an obligation whose `responsible_party` is not
  named in its cited passages via `obligor_grounded=False`; the embed dropped
  the flag, so an inferred attribution looked identical to a grounded one.
- **`finalize_once` only refused a COMPLETED report**
  (`opencontractserver/research/services/research_reports.py`). CANCELLED and
  FAILED are equally "the run already ended", and `reap_stalled_research` can
  put a second worker on one report — so a salvage finalize could overwrite a
  row the other worker had just marked CANCELLED by soft time limit, or FAILED
  with a traceback, producing a COMPLETED report still carrying the other
  worker's `error_message` after the user was notified the run was cancelled.
  Now guards on `is_terminal`.
- **The salvage path still emitted the legacy `budget_exhausted` warning**
  (`opencontractserver/tasks/research_tasks.py`) beside the structured
  `terminal_reason`. Warnings render verbatim to the user
  (`ResearchReportDetail.tsx`), so a run that blew the STEP budget — or simply
  stopped — showed a chip claiming the token budget was gone directly next to
  the reason saying otherwise. Only `terminal_reason` is recorded now.
- **`requires_responses_api` matched model-name prefixes unanchored**
  (`opencontractserver/llms/model_factory.py`), so a hypothetical `gpt-5.60-…`
  would have been routed to the Responses API on the strength of the `gpt-5.6`
  prefix. The match is now anchored on `-` / `.` or whole-name equality.
