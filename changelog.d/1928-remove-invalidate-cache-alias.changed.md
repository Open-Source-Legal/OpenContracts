- **Removed the `PipelineSettings._invalidate_cache()` alias (issue #1928, follow-up
  from PR #1922 / issue #1917).** PR #1922 introduced the public, documented
  `PipelineSettings.clear_cache()` classmethod and left `_invalidate_cache()` as a
  thin backwards-compatible alias, migrating only the file it was already touching.
  This change finishes the job:
  - Deleted the `_invalidate_cache()` classmethod from
    `opencontractserver/documents/models.py` — it had no callers left.
  - Migrated all 37 remaining `PipelineSettings._invalidate_cache()` call sites
    (including the `addCleanup(PipelineSettings._invalidate_cache)` pairs) to
    `PipelineSettings.clear_cache()` across `opencontractserver/conftest.py` and ten
    test modules (`test_pipeline_settings.py`, `test_pipeline_component_base.py`,
    `test_pipeline_utils.py`, `test_base_pipeline_parser.py`, `test_base_enricher.py`,
    `test_enricher_pipeline.py`, `test_web_search_tool.py`,
    `test_migrate_pipeline_settings_command.py`, `test_zip_import_integration.py`,
    `test_import_v2_reingest_remap.py`).
  - Pure mechanical cleanup with no behavior change: `clear_cache()` is the method the
    alias already delegated to. Honors CLAUDE.md's "no dead code / DRY" principle now
    that a single public entry point covers every caller.
