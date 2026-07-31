# Test: Backfill authority-prefix bindings and stranded provider relationships

## Purpose

Repair a GridDossier deployment that was sideloaded **before** the pack
manifests declared `authority_prefixes` for every corpus.

Those deployments look healthy — every document imported, with its
provider-authored edges intact in `custom_meta["relationships"]` — but the
authority graph is missing them. `_reconcile_imported_authority_metadata`
(`opencontractserver/tasks/import_tasks_v2.py`) only reconciles documents whose
canonical-key prefix is bound to the corpus being imported, and returns
immediately when the corpus owns no prefix at all. Unbound prefix → silently
skipped corpus.

On the reference DFW deployment this stranded 154 of 396 declared edges: every
PUCT Project 59142 `FILED_IN` (148), 5 Oncor `IMPLEMENTS`, 1 ERCOT-notice
`CITES`.

New installs do not need this: the pack manifests now bind every declared
prefix, and `test_grid_dossier_authority_pack_data.py::
test_every_declared_prefix_is_bound_to_exactly_one_pack_corpus` fails if one
is ever left unbound again.

## Prerequisites

- The four GridDossier packs installed and their ten corpus exports sideloaded.
- A superuser who passes `is_authority_admin` (the reconciler refuses otherwise).
- Namespaces still pack-owned (`source="baseline"`, `baseline_origin=<pack>`);
  the binder refuses to take a manual or foreign row.

## Steps

1. Record the starting graph size, so the delta is checkable.

   ```bash
   docker compose -f local.yml run --rm django python manage.py shell -c "
   from opencontractserver.annotations.models import AuthorityRelationship
   print('rows before:', AuthorityRelationship.objects.count())
   "
   ```

2. Bind each pack corpus to the prefixes it owns, then re-run the production
   reconciler over that corpus's documents. Both steps are idempotent.

   `_bind_corpus_authority_prefixes` takes a `select_for_update` lock, so each
   binding must run inside a transaction; the reconciler does not.

   ```bash
   docker compose -f local.yml run --rm django python manage.py shell -c "
   from django.db import transaction
   from django.contrib.auth import get_user_model
   from opencontractserver.corpuses.models import Corpus
   from opencontractserver.enrichment.services.authority_pack_service import (
       AuthorityPackService,
   )
   from opencontractserver.tasks.import_tasks_v2 import (
       _reconcile_imported_authority_metadata,
   )

   BINDINGS = {
       'ercot-current-large-load-rules': ('ercot_large_load', ['ercot-planning', 'ercot-protocol', 'ercot-operating']),
       'ercot-large-load-revision-history': ('ercot_large_load', ['ercot-pgrr', 'ercot-nprr']),
       'ercot-large-load-implementation': ('ercot_large_load', ['ercot-notice', 'ercot-form']),
       'puct-electric-rules-and-orders': ('puct_electric', ['tx-admin-puct', 'puct-order']),
       'puct-large-load-proceedings': ('puct_electric', ['puct-project']),
       'oncor-current-delivery-tariff': ('oncor_delivery', ['oncor-tariff', 'oncor-rider']),
       'oncor-service-requirements': ('oncor_delivery', ['oncor-service-guide']),
       'texas-electric-statutes': ('texas_electric_law', ['tx-util']),
       'texas-large-load-legislative-history': ('texas_electric_law', ['tx-sb', 'tx-hb']),
   }

   user = get_user_model().objects.filter(is_superuser=True).first()
   service = AuthorityPackService()
   for slug, (origin, prefixes) in BINDINGS.items():
       corpus = Corpus.objects.get(slug=slug)
       with transaction.atomic():
           service._bind_corpus_authority_prefixes(
               corpus_id=corpus.pk, prefixes=tuple(prefixes), origin=origin,
           )
       docs = list(corpus.get_documents())
       _reconcile_imported_authority_metadata(
           corpus=corpus, documents=docs, user_obj=user,
       )
       print(f'{slug}: bound {prefixes}, reconciled {len(docs)} documents')
   "
   ```

3. Confirm the graph now matches the generated manifests.

   ```bash
   docker compose -f local.yml run --rm django python manage.py shell -c "
   import json, glob, collections
   from opencontractserver.annotations.models import AuthorityRelationship
   expected = set()
   for path in glob.glob('imports/manifest.json'):
       for case in json.load(open(path))['cases']:
           for rel in case.get('expectedProviderRelationships') or []:
               expected.add((rel['sourceKey'], rel['relationshipType'], rel['targetKey']))
   have = set(AuthorityRelationship.objects.values_list('source_key', 'relationship_type', 'target_key'))
   print('rows after:', len(have))
   print('declared:', len(expected), 'missing:', len(expected - have))
   print('by type:', dict(collections.Counter(t for _, t, _ in have)))
   "
   ```

## Expected Results

- Step 2 prints one line per corpus and raises nothing. Re-running it is a
  no-op: `_bind_corpus_authority_prefixes` skips prefixes already bound to the
  same corpus, and `upsert_for_source` reconciles rather than duplicates.
- Step 3 reports `missing: 0`.
- On the reference deployment the row count goes 246 → 400.
- `oncor-tariff` binds to `oncor-current-delivery-tariff`, not to
  `oncor-tariff-history`: a prefix binds to exactly one corpus, and the history
  corpus's two lineage edges are declared in the pack's `relationships.yaml`,
  so nothing depends on binding it there.

## Cleanup

None. The bindings are the intended steady state, and the reconciler is
idempotent. To undo a binding for testing, clear it explicitly:

```bash
docker compose -f local.yml run --rm django python manage.py shell -c "
from opencontractserver.annotations.models import AuthorityNamespace
AuthorityNamespace.objects.filter(prefix='puct-project').update(
    authority_corpus=None, is_global=True, baseline_origin='puct_electric',
)
"
```
