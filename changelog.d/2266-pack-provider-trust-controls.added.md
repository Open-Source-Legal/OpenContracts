- **An operator can decline to execute in-pack provider code.** Installing an
  authority pack that ships `<pack>/providers/*.py` or
  `<pack>/discovery_providers/*.py` imports that Python into the web and
  worker processes — `tar.extract(..., filter="data")` refuses path traversal
  and setuid bits, but it cannot refuse code. The new
  `AUTHORITY_PACK_LOAD_PROVIDERS` setting (`config/settings/base.py`, default
  `True` — no behavior change for existing installs) lets an operator turn
  this off; when disabled, `opencontractserver/pipeline/registry.py` skips
  the modules without importing them and logs the skip once with a count and
  the module names. Turning it off costs re-fetch and nothing else — the pack
  contract (authority-packs `SOURCE_PROVIDERS.md`, clause P5) requires a pack
  to install and serve its sections with `providers/` deleted.
- **`get_authority_source_provider(class_name)`** (`opencontractserver/pipeline/registry.py`)
  is the supported delegation seam for an in-pack provider that reuses a core
  one (CFR, U.S. Code, Federal Register) instead of shipping its own scraper.
  Accepts a bare class name or a dotted path, refuses an ambiguous leaf rather
  than picking one, and returns `None` instead of raising so a pack degrades
  to "cannot re-fetch" rather than crashing registry build.
- **`install_authority_pack` reports a pack's provider code surface before any
  DB write.** Lists the provider modules a pack ships and, when present, the
  classes/prefixes its optional `providers:` manifest declares — by reading
  files only, never by importing them — and notes when
  `AUTHORITY_PACK_LOAD_PROVIDERS` is off so `--check` shows that the modules
  will not run.
