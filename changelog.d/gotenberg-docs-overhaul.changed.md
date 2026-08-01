- **Documented Gotenberg-powered file conversion for non-core formats.**
  `docs/upload_methods/supported_formats.md` gained a "Convertible Formats
  (via Gotenberg)" section explaining the ~126 legacy Office/OpenDocument/
  iWork/image/HTML extensions the optional pre-parse converter can turn into
  PDF, how it fits into the ingest pipeline, and its off-by-default posture.
  `docs/pipelines/pipeline_configuration.md` gained a "File Converters
  (Gotenberg)" section with a screenshotted step-by-step walkthrough for
  enabling/disabling conversion via the Admin UI or the `DEFAULT_FILE_CONVERTER`
  env var, plus a note that the `gotenberg` compose service already ships in
  `local.yml`/`production.yml` and needs no compose changes to use.
  `docs/configuration/choose-and-configure-docker-stack.md` gained an
  "Optional Services" section covering `gotenberg` (and pointers for
  `warp-ingest`/`privacy_filter`). Sample `.django` env files
  (`docs/sample_env_files/backend/{local,production}/.django`) now document
  `GOTENBERG_SERVICE_URL`, `GOTENBERG_CONVERTER_TIMEOUT`, and
  `DEFAULT_FILE_CONVERTER`. `README.md`'s "Supported Formats" section and
  documentation table now mention the conversion capability.
- **New `data-testid="file-converter-row"`** on the File Converter row in
  `frontend/src/components/admin/system_settings/FiletypeDefaults.tsx`, used
  by three new `docScreenshot` captures in
  `frontend/tests/system-settings-flows.ct.tsx`'s "file converter on/off"
  suite (disabled row, converter picker modal, enabled row) that back the new
  docs walkthrough.
