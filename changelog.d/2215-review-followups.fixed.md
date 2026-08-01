- **Deep research audit log / findings scratchpad no longer lose a concurrent
  append.** `ResearchReportService.append_tool_call` and `append_finding`
  (`opencontractserver/research/services/research_reports.py`) did a non-atomic
  `refresh_from_db` → append → `save()`. Every tool call now routes through
  `append_tool_call` via `_audited` (`opencontractserver/tasks/research_tasks.py`),
  and `reap_stalled_research` can re-enqueue a RUNNING report while the original
  worker is still writing — so the later `save()` clobbered the earlier append,
  silently dropping an audit entry and undercounting the `calls_made` that feeds
  the step-budget notice. Both now do the read-modify-write under
  `select_for_update()` inside `transaction.atomic()`.
- **Authority packs sharing a directory basename no longer collide in
  `sys.modules`.** `opencontractserver/pipeline/registry.py` keyed each pack's
  synthetic import namespace on the pack directory's basename alone, while
  `authority_pack_dirs()` de-duplicates by *resolved path*. Two different packs
  reached through different `AUTHORITY_PACK_ROOTS` entries but sharing a
  basename both landed on `_authority_pack.<name>`, and
  `_ensure_synthetic_package` re-pointed the first pack's package at the second
  pack's directory — silently resolving the first pack's provider names to the
  other pack's code, and moving the `__module__`-based host-ownership checks in
  `authority_source_hosts` onto the wrong pack. New `_pack_namespaces()` keeps
  the plain basename when unique and appends a short path digest on collision,
  with a warning.
- **A publisher-sidecar storage error no longer aborts an entire pack import.**
  `_attach_publisher_original_file` at `opencontractserver/tasks/import_tasks_v2.py:540`
  sat ahead of the `try` that gives every other per-document step in
  `_import_document_with_annotations` its failure isolation, so one document's
  storage error propagated out and killed the whole run instead of skipping that
  document. It now returns the same `(None, {})` the outer handler does, honouring
  the caller's documented "accept partial state on failure" contract on every path.
