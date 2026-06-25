- **Authority packs can now ship their own source provider.** The pipeline
  registry discovers `BaseAuthoritySourceProvider` subclasses from
  `<pack>/providers/*.py` — both for in-tree packs under
  `opencontractserver/enrichment/data/authority_packs/` and for out-of-tree pack
  directories listed in the new `AUTHORITY_PACK_PATHS` setting (env var). A pack's
  scraper now lives *with* its authority, so copying the pack directory to another
  OpenContracts install brings the provider with it — no more dropping a `.py` into
  core's `pipeline/authority_source_providers/` package
  (`opencontractserver/pipeline/registry.py`, `config/settings/base.py`). Provider
  modules are imported by file path under a collision-free synthetic module name;
  an import failure is logged and skipped, never crashing registry build. Secrets
  stay in the `PipelineSettings` encrypted vault (keyed by provider class path),
  never in pack files.
- **Duplicate authority-provider prefixes now warn at registry build.** Two
  providers claiming the same `supported_prefixes` family (e.g. a pack provider
  shadowing a core one) previously registered silently; `_provider_for` then
  resolved them non-deterministically by priority-then-discovery-order. The
  registry now logs a warning identifying both claimants.
