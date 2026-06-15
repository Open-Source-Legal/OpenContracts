- Added a jurisdiction + authority-type taxonomy to the reference-enrichment
  engine: `CorpusReference` now carries `jurisdiction`/`authority_type`
  (`opencontractserver/annotations/models.py`), a new `AuthorityNamespace`
  registry table is seeded from the static authority map, and
  `authority_alias_registry` reads it so new bodies of law need no code change.
  Foundation for open-vocabulary authority discovery.
