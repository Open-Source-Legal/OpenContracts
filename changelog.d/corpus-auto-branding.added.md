- **Auto-generate a corpus logo and `Readme.CAML` article on creation.** When a
  corpus is created without an uploaded icon, a `post_save` signal
  (`opencontractserver/corpuses/signals.py`) dispatches a best-effort branding
  task (`generate_corpus_branding` in `opencontractserver/tasks/corpus_tasks.py`).
  The orchestrator (`opencontractserver/corpuses/services/branding.py`) runs a
  corpus-scoped LLM agent that researches the title/description via `web_search`
  and writes the `Readme.CAML` article through `update_corpus_description`, then
  generates a square logo via the OpenAI Images API
  (`opencontractserver/utils/image_generation.py`) with a deterministic PIL
  "monogram" fallback when image generation is disabled/unconfigured, persisting
  it through the new creator-gated `CorpusService.update_icon`.
  Opt-out is layered: the install-wide `CORPUS_AUTO_BRANDING_ENABLED` /
  `CORPUS_LOGO_GENERATION_ENABLED` settings, the per-corpus
  `Corpus.auto_branding_enabled` flag (exposed on `CorpusSerializer` /
  `CorpusType`), uploading an icon at creation, and personal "My Documents"
  corpora are always skipped. Branding never blocks corpus creation. Migration
  `corpuses/0056_corpus_auto_branding_enabled`.
