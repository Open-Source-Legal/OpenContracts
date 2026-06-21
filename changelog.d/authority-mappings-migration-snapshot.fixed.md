- Fixed a fresh-database migration break introduced by adding the `created_by`
  column to `AuthorityKeyEquivalence`: data migration
  `0092_load_authority_mappings_baseline` called the *live*-model
  `AuthorityMappingLoader.load()`, whose ORM now `SELECT`s `created_by_id`
  before migration 0094 creates that column. The migration now snapshots the
  loader's equivalence upsert against the historical model (`apps.get_model`) —
  identical end state, no live-model column drift — as the migration's own note
  always anticipated. Already-applied databases are unaffected (the migration
  does not re-run).
