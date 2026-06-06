- **Fixed env-configurable zip-import limits being silently frozen to their
  defaults in production.** `opencontractserver/constants/zip_import.py` read
  every limit (`ZIP_MAX_FILE_COUNT`, `ZIP_MAX_TOTAL_SIZE_BYTES`,
  `ZIP_MAX_SINGLE_FILE_SIZE_BYTES`, `ZIP_MAX_FOLDER_COUNT`,
  `ZIP_MAX_SIDECAR_SIZE_BYTES`, `ZIP_DOCUMENT_BATCH_SIZE`,
  `BULK_UPLOAD_OWNER_CACHE_TTL_SECONDS`, …) via a *module-level*
  `getattr(settings, …)`. Because `config/settings/base.py` imports from
  `opencontractserver.constants.*` at the top of the settings module, the
  constants package `__init__` — which eagerly `import *`-ed `zip_import` —
  executed *while settings was still mid-load*, so each limit bound to its
  hard-coded default before `base.py` defined the env-driven value and froze
  there for the life of the process. ConfigMap/`env` overrides of any `ZIP_*`
  limit were therefore permanently inert (these are the zip-bomb / resource-
  exhaustion / path-length security limits, so an operator tightening them got
  the shipped defaults instead). The limits are now read lazily at call time
  through `get_*()` accessors (mirroring the sibling
  `opencontractserver/constants/zip_export.py`), `DEFAULT_*` constants hold the
  fallbacks, and `zip_import` is no longer barrel-imported by
  `opencontractserver/constants/__init__.py` — so settings/`env` overrides are
  honoured at runtime. Consumers updated to call the accessors:
  `opencontractserver/utils/zip_security.py`,
  `opencontractserver/tasks/import_tasks.py`,
  `opencontractserver/document_imports/services.py`. Regression test:
  `opencontractserver/tests/test_constants.py::TestZipImportConstants::test_accessors_reflect_settings_overrides`.
