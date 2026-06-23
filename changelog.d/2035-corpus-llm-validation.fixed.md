- **Invalid per-corpus LLM specs now return a clean field error instead of a
  generic "internal error".** The Corpus Settings model picker is free-text, so a
  user can type an unregistered provider or malformed spec (e.g.
  `not-a-provider:foo`). `Corpus.save()` already rejected these, but the
  model-layer `ValidationError` surfaced through the update mutation as the opaque
  "Mutation failed due to an internal error." `CorpusSerializer.validate_preferred_llm`
  (`config/graphql/serializers.py`) now runs `validate_model_spec` before
  `save()`, so an invalid spec fails serializer validation and the mutation
  returns `ok=false` with the real reason (e.g. "Provider 'not-a-provider' … is
  not registered"). Normalisation of the canonical stored form stays in
  `Corpus.save()` (single source of truth). Also extracted the
  `agenerate_text` default sampling temperature into a named
  `DEFAULT_COMPLETION_TEMPERATURE` constant (`opencontractserver/constants/llm.py`)
  to remove a magic number.
