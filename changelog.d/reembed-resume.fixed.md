- `reEmbedCorpus` can now finish a migration it started. `reembed_corpus`
  (`opencontractserver/tasks/corpus_tasks.py`) writes `preferred_embedder`
  *before* queueing work and caps each dispatch at `MAX_REEMBED_TASKS_PER_RUN`
  (500 batches × `EMBEDDING_BATCH_SIZE` = 50k annotations), so any corpus larger
  than that cap ended its first run already labelled with the new embedder while
  most of its annotations still carried the old one. The mutation's no-op guard
  compared only the embedder path, so every retry answered *"Corpus already uses
  this embedder. No re-embedding needed."* with `ok: true` — leaving the corpus
  permanently half-migrated, its unembedded tail invisible to vector search, and
  nothing anywhere reporting a problem. Observed live on a 77k-annotation corpus
  that stopped at 38% and could not be resumed through any API or UI path.
  The guard now also requires zero outstanding annotations, via the new
  `CorpusService.count_annotations_missing_embeddings`
  (`opencontractserver/corpuses/services/corpus_service.py`), and a resumed run
  reports how many annotations remain
  (`config/graphql/corpus_mutations.py::_mutate_ReEmbedCorpus`). Regression
  tests: `opencontractserver/tests/test_embedder_management.py::TestReEmbedCorpusResume`.
