- **Deleted the dead `THUMBNAIL_TASKS` dict** (`config/settings/base.py`) —
  it had zero references anywhere in the codebase, and its referenced task
  paths (`opencontractserver.tasks.doc_tasks.extract_pdf_thumbnail`/
  `extract_txt_thumbnail`/`extract_docx_thumbnail`) do not exist as functions
  in `doc_tasks.py`; thumbnailer resolution is handled entirely by
  `PipelineSettings.preferred_thumbnailers` today. Updated
  `docs/pipelines/pipeline_overview.md`'s stale "Component Registration"
  example that still showed `THUMBNAIL_TASKS`, and fixed a leftover
  `docling_parser.DoclingParser` (non-`_rest`, nonexistent module) example
  path in the `ENABLED_COMPONENTS` comment.
- **Corrected `PipelineSettings.get_component_settings()`'s docstring** (`opencontractserver/documents/models.py`):
  it claimed a Django-settings fallback was "handled by
  `PipelineComponentBase.get_component_settings()`", but that method
  (`opencontractserver/pipeline/base/base_component.py`) implements no such
  fallback — it only calls `PipelineSettings.get_full_component_settings()`
  and returns `{}` when empty (component `Settings` dataclass defaults apply
  from there). Reworded the docstring to stop promising a fallback mechanism
  that isn't implemented.
