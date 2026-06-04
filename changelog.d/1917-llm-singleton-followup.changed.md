- **LLM provider credential follow-ups (PR #1897 review, issue #1917).** Code-quality
  hardening for the DB-configurable LLM credential feature:
  - Added a public, documented `PipelineSettings.clear_cache()` classmethod
    (`opencontractserver/documents/models.py`) as the canonical way to drop the
    cached singleton; the existing `_invalidate_cache()` is now a thin
    backwards-compatible alias that delegates to it. Tests and admin/CLI tooling
    that write the singleton out-of-band no longer have to reach for the private
    underscore method.
  - `opencontractserver/tests/test_llm_model_factory.py`: assert the credentialed
    model against pydantic-ai's exported abstract base `pydantic_ai.models.Model`
    (`assertIsInstance`) instead of the fragile `type(result).__name__.endswith("Model")`
    class-name string, which would have silently broken on an upstream rename of
    `OpenAIChatModel`; switched cache resets to the new `clear_cache()` (dropping a
    redundant `cache.delete()` + `_invalidate_cache()` double call); and added
    `self.addCleanup(reset_registry)` to every `setUp` so the pipeline-component
    registry is restored symmetrically after each test rather than only reset
    before it.
  - The correctness/security items from the same review — narrowing the
    `except Exception` fallbacks to explicit recoverable-error tuples, the
    `base_url`-without-`api_key` warning, `urlparse` scheme validation of a
    DB-configured `base_url`, and the `test_colonless_spec_returned_unchanged`
    comment — were already addressed in `opencontractserver/llms/model_factory.py`
    / the test before #1897 merged. The aiohttp `<3.14` cap (#1920) and the
    per-call credential-read cost (#1921) are tracked as separate follow-up issues.
