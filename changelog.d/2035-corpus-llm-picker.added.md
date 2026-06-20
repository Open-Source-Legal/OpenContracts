- **Admin GUI for the per-corpus LLM (Singleton registry).** The
  `Corpus.preferred_llm` override was fully plumbed in the backend
  (`resolve_model_spec` chain, `UpdateCorpusMutation`, `CorpusType`) but had no
  frontend surface — it could only be set via the GraphQL console or Django
  shell. Added a **Language Model** card to the Corpus Settings panel
  (`frontend/src/components/corpuses/CorpusSettings.tsx`) backed by a new shared
  `LlmModelPicker` component (`frontend/src/components/common/LlmModelPicker.tsx`),
  which the admin System Settings screen now also consumes (de-duplicating its
  inline provider/model chip list). The picker lists registered providers and
  their suggested models from two new secret-free, `@login_required` queries
  (`GET_LLM_PROVIDERS`, `GET_SYSTEM_DEFAULT_LLM` in `frontend/src/graphql/queries.ts`),
  and when the corpus has no override it shows the inherited install-wide
  default so users understand "leave empty = inherit". Threaded `preferredLlm`
  through `RESOLVE_CORPUS_BY_SLUGS_FULL`, the `UPDATE_CORPUS` mutation, and the
  `CorpusType`/`RawCorpusType` TypeScript types. Empty input clears the override
  (backend normalises `""` → `NULL`).
