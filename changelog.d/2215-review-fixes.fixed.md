- `opencontractserver/llms/model_factory.py::build_agent_model` — both
  DB-credential fallback branches (`_construct_model` raising a recoverable
  error, or returning `None`) returned the un-rewritten `spec`, silently
  dropping the `openai-responses:` prefix computed for the GPT-5.6 family.
  A DB-configured install (System Settings model picker) hitting a recoverable
  construction error would re-trigger the exact 400 the Responses-API redirect
  exists to prevent. Both branches now preserve the redirect.
- `opencontractserver/enrichment/grammars.py` — `_ERCOT_GUIDE_RE` was missing
  `re.IGNORECASE` (present on its sibling patterns `_PUCT_TAC_RE` and
  `_ERCOT_REVISION_RE`), silently under-extracting lowercase/mixed-case guide
  headers (e.g. from scanned-document running text).
- `frontend/src/components/widgets/modals/StartResearchModal.tsx` — the
  corpus-group picker query destructured only `data`, so a failed
  `GET_CORPUS_GROUP_OPTIONS` load silently omitted the picker with no
  indication anything went wrong. Now surfaces the error inline via the
  shared `ErrorMessage` widget, consistent with `PacksTab.tsx`.
