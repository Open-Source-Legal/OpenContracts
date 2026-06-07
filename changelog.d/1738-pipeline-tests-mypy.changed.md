- **Graduated the `pipeline & parsers` test domain out of the mypy baseline
  (#1738).** Removed the 14 `[mypy-opencontractserver.tests.test_*]`
  `ignore_errors` blocks for the document-parsing pipeline
  (registry/settings/utils core + the Docling/LlamaParse/Markdown/Text/chunked
  parsers): `test_base_pipeline_parser`, `test_pipeline_component_base`,
  `test_pipeline_component_queries`, `test_pipeline_hardening`,
  `test_pipeline_registry`, `test_pipeline_settings`,
  `test_pipeline_settings_schema`, `test_pipeline_utils`, `test_chunked_parser`,
  `test_markdown_parser`, `test_doc_parser_docling_rest`,
  `test_doc_parser_docxodus`, `test_doc_parser_llamaparse`,
  `test_txt_ingestor_pipeline`. Pruned the corresponding 216 lines from
  `docs/typing/mypy_baseline.txt` (3591 → 3375) and fixed the 227 errors that
  surfaced. Fixes use the established patterns from prior chunks: class-level
  annotations for `setUpClass` attributes (the recommended fix from #1479), the
  graphene `self.client` → `self.graphene_client` rename, `assert ... is not
  None` narrowing of Optional ORM/parse returns, and `cast(...)` / typed
  literals (`BoundingBoxPythonType`, `TokenIdPythonType`) for the parser
  helpers' intentionally-partial dict fixtures, plus `ClassVar` /
  override-signature fixes on the module-level probe embedders in
  `test_pipeline_utils`.
- **Fixed a latent typing gap in `get_components_by_mimetype`
  (`opencontractserver/pipeline/utils.py`).** The signature declared
  `file_type: Optional[FileTypeEnum]`, but the body already converts MIME
  strings via `FileTypeEnum.from_mimetype` (a documented backward-compat path);
  the parameter is now `Optional[Union[str, FileTypeEnum]]`, matching the
  implementation. This let a now-unused `# type: ignore[arg-type]` be removed
  from the lone string-passing caller in
  `opencontractserver/tasks/doc_tasks.py`. The full project surface
  (`mypy --config-file mypy.ini opencontractserver config`) stays clean under
  both the pre-commit pin (`mypy==2.0.0`) and CI's pin (`mypy==2.1.0`).
