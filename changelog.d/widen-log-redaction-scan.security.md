- Widen the log-redaction invariant from #2446. The scanner moves to
  `opencontractserver/shared/log_redaction_audit.py`, run by
  `opencontractserver/tests/architecture/test_log_redaction.py` (replaces
  `tests/test_pipeline_log_redaction.py`; `SimpleTestCase`, so pytest and
  `manage.py test` both collect it). It covers every module under
  `opencontractserver/` and `config/` instead of `pipeline/` only, and catches a
  mapping logged as the message itself, `%`-style arguments, `str.format`, the
  `%` operator with tuple or dict operands, `+` concatenation, keyword arguments
  (`msg=`, `extra=`), dict/tuple literals including `{**kwargs}`, attribute and
  method expressions (`self._settings`, `self.get_component_settings()`) and the
  transparent wrappers `str`/`repr`/`format`/`dict(**…)`/`vars`/`asdict`/
  `pformat`/`json.dumps`, for names ending in `settings` as well as `kwargs`.
  The text pre-filter is case-insensitive so module-level constants are scanned,
  `redact_sensitive_kwargs` is recognised through `import … as` aliases, and a
  log call that formats an already-safe helper result may carry a trailing
  `# log-redaction: safe` marker. The wider scan found no raw formatting outside
  `pipeline/`.
- Close the credential leak the wider scan surfaced. `AgentConfig.api_key`
  (`opencontractserver/llms/agents/core_agents.py`) is populated from
  `settings.OPENAI_API_KEY` by `get_default_config()` — the constructor used by
  `UnifiedAgentFactory` and by `PydanticAIDocumentAgent.create` — and
  `opencontractserver/llms/agents/pydantic_ai_agents.py` logged the whole config
  at DEBUG on every document-agent creation. Under the shipped `LOGGING` (root
  level INFO in `config/settings/base.py` and `production.py`) the record was
  dropped before reaching a handler; an install that raised
  `opencontractserver.llms.agents.pydantic_ai_agents` or the root logger to
  DEBUG wrote its OpenAI key to the log stream on each creation and should scrub
  those logs and rotate the key. The call site now logs a summary (model, user,
  conversation, storage backend) and the field is `repr=False`.
- `SECRET` pipeline and tool settings are dropped from their `Settings`
  dataclass repr when the component class is defined
  (`opencontractserver/pipeline/base/settings_schema.py::hide_secret_settings_from_repr`,
  called from `PipelineComponentBase.__init_subclass__` and
  `BaseTool.__init_subclass__`), so `f"{self.settings}"` cannot write a key, and
  `opencontractserver/utils/logging.py::redact_sensitive_kwargs` accepts
  dataclass instances so the sanctioned fix works on what the scanner flags.
- The embedder behavioural test builds its component with explicit
  `component_settings` instead of relying on a swallowed database-access error,
  and the three remaining over-long log lines are split like their siblings.
