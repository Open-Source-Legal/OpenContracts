- **Redact SECRET-typed parser settings from the parser log line.**
  `BaseParser.parse_document` (`opencontractserver/pipeline/base/parser.py`)
  logged the merged component settings at INFO **without** redaction, so any
  `SettingType.SECRET` field returned by `get_component_settings()` (decrypted) —
  e.g. `LlamaParseParser`/`WarpIngestParser`'s `api_key` — was written to logs in
  plaintext on every parse. It now runs the same `redact_sensitive_kwargs()` pass
  the embedder/post-processor/enricher base classes already apply to their
  equivalent log line, so secrets are masked as `***`.
