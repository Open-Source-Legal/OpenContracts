# Corpus Auto-Branding (Logo + Readme.CAML)

When a corpus is created, OpenContracts can automatically generate two
artifacts so a brand-new collection does not start blank:

1. **A `Readme.CAML` article** — written by a corpus-scoped LLM agent that
   researches the corpus title/description with `web_search` and saves the
   article via the `update_corpus_description` tool.
2. **A square logo** — generated with the OpenAI Images API, with a
   deterministic PIL "monogram" fallback so a logo is always produced even when
   image generation is unavailable.

The whole flow is **best-effort**: it runs asynchronously after the corpus is
durably committed and never blocks (or rolls back) corpus creation.

## Trigger and gating

A `post_save` receiver on `Corpus`
(`opencontractserver/corpuses/signals.py::trigger_corpus_branding_on_creation`)
queues the work on `transaction.on_commit`. It only fires for genuine,
user-facing corpora that opted in:

| Guard | Condition to proceed |
|-------|----------------------|
| Creation only | `created is True` (never on update) |
| Fixtures/tests | `_skip_signals` not set |
| Install kill-switch | `settings.CORPUS_AUTO_BRANDING_ENABLED` is `True` |
| Personal corpus | `is_personal is False` (the auto "My Documents" corpus is skipped) |
| Per-corpus opt-out | `Corpus.auto_branding_enabled is True` |
| Uploaded image | `corpus.icon` is empty (uploading an icon opts the corpus out) |
| Has a creator | `creator_id` is set |

This is the "global hook" the feature is configured with: the **signal** is the
hook, the **setting** is the global switch, and `auto_branding_enabled` +
the icon guard are the per-corpus opt-outs.

## Execution

```
Corpus.save(created=True)
  └─ post_save signal (guards) ── transaction.on_commit ─▶ generate_corpus_branding.delay(...)
       └─ run_corpus_branding_async(corpus_id, user_id)      # services/branding.py
            ├─ _generate_readme:  agents.for_corpus(tools=[web_search, update_corpus_description]).chat(...)
            └─ _generate_logo:    agenerate_logo_image(...)  ─▶ CorpusService.update_icon(...)
```

* `generate_corpus_branding` (`opencontractserver/tasks/corpus_tasks.py`) is a
  thin Celery wrapper that runs the async orchestrator and retries a couple of
  times on hard failure.
* The README step reuses the **agent-corpus-action** execution pattern (see
  `tasks/agent_tasks.py`): a corpus agent with `skip_approval_gate=True` and a
  goal-oriented system prompt whose user-supplied title/description are fenced
  with `<user_content>` (prompt-injection hardening). The agent persists the
  article itself via `update_corpus_description`, which routes through
  `CorpusService.update_description` (creator-gated, versioned `Readme.CAML`).
* The README step is skipped when the corpus already has a `Readme.CAML`
  (`corpus.readme_caml_document_id` set), e.g. a forked/imported corpus.

## Logo generation

`opencontractserver/utils/image_generation.py::agenerate_logo_image` is the
single entry point and always returns `(image_bytes, extension)`:

1. **AI (preferred):** if `CORPUS_LOGO_GENERATION_ENABLED` is `True` **and**
   `OPENAI_API_KEY` is set, it calls the OpenAI Images API
   (`gpt-image-1`, `1024x1024`) over `httpx` and decodes the `b64_json` (or
   fetches the returned `url`).
2. **Monogram fallback:** otherwise — or if the API errors — it renders the
   corpus initials on a deterministic background color (stable per corpus) with
   Pillow. No network required, so branding degrades gracefully.

The bytes are written to `Corpus.icon` through the new creator-gated
`CorpusService.update_icon`, which uses `ContentFile` + the configured storage
backend (LOCAL / S3 / GCP).

## Configuration

| Setting / field | Default | Effect |
|-----------------|---------|--------|
| `CORPUS_AUTO_BRANDING_ENABLED` (env: same) | `True` | Master switch for the whole feature. Set `False` to disable install-wide. |
| `CORPUS_LOGO_GENERATION_ENABLED` (env: same) | `True` | Toggles AI logo generation. When `False`, the monogram fallback is used. |
| `OPENAI_API_KEY` | `""` | Required for AI logo generation; absent ⇒ monogram fallback. |
| `Corpus.auto_branding_enabled` | `True` | Per-corpus opt-out, settable via `CorpusSerializer` / `autoBrandingEnabled` on `CorpusType`. |

> **Tests:** `CORPUS_AUTO_BRANDING_ENABLED` is `False` in
> `config/settings/test.py` so corpus creation in the suite never dispatches the
> task (which would otherwise run eagerly under `CELERY_TASK_ALWAYS_EAGER`).
> Branding tests opt back in with `@override_settings(...)` and mock external
> calls (`opencontractserver/tests/test_corpus_branding.py`).

## Network policy note

Both steps make **outbound** calls (the search provider for `web_search` and the
OpenAI Images API for logos). They are therefore subject to the environment's
network policy. When outbound access is blocked or the providers are
unconfigured, the README step simply omits web research and the logo step uses
the monogram fallback — the corpus is still created successfully.

## Extending

* **Different image provider:** swap the implementation of `_generate_ai_logo`
  in `utils/image_generation.py` (mirrors the provider pattern in
  `llms/tools/web_search_tools.py`). The fallback contract (`always returns
  bytes`) should be preserved.
* **Richer README:** adjust the agent tool set / system prompt in
  `services/branding.py` (`CORPUS_BRANDING_AGENT_TOOLS`,
  `_build_branding_system_prompt`).
* **Make it user-configurable per install:** the `auto_branding_enabled` field
  is already exposed through the corpus serializer/type for a frontend toggle.
