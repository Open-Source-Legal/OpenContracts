- **Reconciled `CorpusVote` migration state with the model** (migration
  `corpuses/0057`): migration `0049` created the three `CorpusVote` indexes
  with explicit names (`corpuses_co_corpus__vote_idx`, …) while the model
  declares them unnamed (Django auto-hashed names), and the `backend_lock`
  field's `db_index=True` was missing from migration state. The drift made
  `makemigrations --check` fail on every branch. Operations are three
  Postgres `ALTER INDEX … RENAME` calls plus one index-state alter — no data
  changes.
