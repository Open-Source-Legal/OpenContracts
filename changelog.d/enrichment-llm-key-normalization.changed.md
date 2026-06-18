- **LLM-derived citation keys are normalized to cut open-vocabulary noise.**
  `opencontractserver/enrichment/llm_citation_extractor.py` now (a) folds locator
  separators so the same authority cited two ways collapses to one key
  (`eu:2017/1129` → `eu:2017-1129`; subsection punctuation `.`/`(`/`)` is left
  untouched), and (b) flags locator-less `act:*` references — a body of law or
  loose phrase with no section number (`act:gaap`, `act:applicable-law`,
  `act:guam-administrative-adjudication-law`) — as `needs_review`, so they
  surface for triage but never auto-promote into the persisted reference web or
  crawl frontier. Reversible; nothing is dropped. A numbered key (`act:asc-606`)
  or a real prefix (`irc:163`) is unaffected.
