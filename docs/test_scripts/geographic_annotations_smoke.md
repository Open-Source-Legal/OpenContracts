# Test: Geographic annotations end-to-end smoke

## Purpose

Verifies that the foundation laid down in issue #1819 — geocoding
service + OC_COUNTRY/STATE/CITY conventions + auto-creating mutations +
aggregation service — works end-to-end against a real document. Used as
the manual gate before relying on the foundation for the follow-up map
UI work (#1820 / #1821).

## Prerequisites

- Migration `annotations/0075_annotation_data` applied.
- At least one corpus the test user can write to with one PDF or text
  document attached. The instructions below assume the user has SUPERUSER
  rights; if not, swap the corpus + document fetch lines for IDs the user
  owns directly.

## Steps

1. Apply migrations (one-time per fresh DB):

   ```bash
   docker compose -f local.yml run --rm django python manage.py migrate
   ```

2. Open a Django shell and seed a corpus + document via the test fixture
   path if you don't already have one:

   ```bash
   docker compose -f local.yml run --rm django python manage.py shell -c "
   from django.contrib.auth import get_user_model
   from opencontractserver.corpuses.models import Corpus
   from opencontractserver.documents.models import Document
   from opencontractserver.types.enums import PermissionTypes
   from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

   user = get_user_model().objects.filter(is_superuser=True).first()
   corpus = Corpus.objects.create(title='Geo Smoke', creator=user)
   set_permissions_for_obj_to_user(user, corpus, [PermissionTypes.CRUD])
   doc = Document.objects.create(title='Geo Doc', creator=user, is_public=True, backend_lock=False)
   corpus_doc, *_ = corpus.add_document(document=doc, user=user)
   set_permissions_for_obj_to_user(user, corpus_doc, [PermissionTypes.CRUD])
   print('CORPUS', corpus.pk, 'DOC', corpus_doc.pk)
   "
   ```

3. Issue one of each geographic mutation via the GraphQL surface (use
   the IDs printed above):

   ```graphql
   mutation {
     addCountryAnnotation(
       corpusId: "Q29ycHVzVHlwZTox"  # to_global_id('CorpusType', <id>)
       documentId: "RG9jdW1lbnRUeXBlOjE="
       page: 0
       rawText: "France"
       json: { "0": { bounds: {}, rawText: "France", tokensJsons: [] } }
       annotationType: TOKEN_LABEL
     ) {
       ok geocoded message
       annotation { id structural data annotationLabel { text color } }
     }
   }
   ```

4. Confirm the three things that matter for the foundation:

   * The annotation row carries ``structural=True``.
   * ``data`` is a dict shaped like
     ``{"canonical_name": "France", "lat": 46.22..., "lng": 2.21...,
     "admin_codes": {"iso_alpha2": "FR", "iso_alpha3": "FRA"},
     "geocoded": true}``.
   * The corpus now has an ``OC_COUNTRY`` label with
     ``color="#0E3A5F"`` and ``read_only=true``.

5. Repeat with ``addStateAnnotation`` ("Texas" / "TX") and
   ``addCityAnnotation`` ("Paris" — unhinted should resolve to FR;
   ``stateHint="TX"`` should resolve to Paris, Texas).

6. Issue the aggregation query and verify the result:

   ```graphql
   query {
     geographicAnnotationsForCorpus(corpusId: "Q29ycHVzVHlwZTox") {
       canonicalName labelType lat lng documentCount sampleDocumentIds
     }
   }
   ```

   Expected: three pins (France, Texas, Paris). Each ``documentCount=1``,
   each ``sampleDocumentIds`` is a single-element list of the global
   document ID created in step 2.

7. Force an ungeocodable annotation:

   ```graphql
   mutation {
     addCityAnnotation(
       corpusId: "..."
       documentId: "..."
       page: 0
       rawText: "Zzzqqqxxxnnn"
       json: { "0": { bounds: {}, rawText: "Zzzqqqxxxnnn", tokensJsons: [] } }
       annotationType: TOKEN_LABEL
     ) {
       ok geocoded message annotation { data }
     }
   }
   ```

   Expected: ``ok=true``, ``geocoded=false``, ``data.geocoded=false``,
   ``message`` mentions the resolver miss. Re-running the aggregation
   query must NOT include the new annotation as a pin.

## Expected results

- Three OC_* labels exist on the corpus (`OC_COUNTRY`, `OC_STATE`,
  `OC_CITY`) with the correct colors from
  ``opencontractserver/constants/annotations.py``.
- Five annotations exist (3 from step 5, 1 from step 3, 1 from step 7).
  All carry ``structural=True``.
- The aggregation query returns four pins (the ungeocoded row is
  excluded). Pin coordinates match the values bundled in
  ``opencontractserver/utils/geocoding/data/``.

## Cleanup

```bash
docker compose -f local.yml run --rm django python manage.py shell -c "
from opencontractserver.corpuses.models import Corpus
Corpus.objects.filter(title='Geo Smoke').delete()
"
```

## Notes

- This smoke test exercises the canonical user path. For the
  permission-isolation behaviour (private document inside a shared
  corpus → MIN(doc, corpus) hides the pin from non-doc viewers) see
  ``opencontractserver/tests/test_geographic_annotation_service.py``.
- The bundled city dataset is intentionally small (~150 major world
  cities) — see ``docs/credits/geonames.md`` for the regeneration recipe
  when broader coverage is required.
