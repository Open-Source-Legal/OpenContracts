- **`get_authority_source_provider()` could resolve to the wrong component type.**
  `opencontractserver/pipeline/registry.py` — its primary lookup went through
  `PipelineComponentRegistry.get_by_name` / `get_by_class_name`, dicts shared by
  every component family (parsers, embedders, LLM providers, ...). A class-name
  collision with an unrelated component would silently return an instance of
  the wrong type, which would only fail later and outside this function's
  `try/except`, when the pack called `.can_handle(...)` on it. The lookup is
  now scoped to `get_all_authority_source_providers_cached()` throughout,
  matching the type-safety guarantee already stated in the docstring and
  already applied on the ambiguous-leaf fallback path.
