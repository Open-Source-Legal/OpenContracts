# Test: Location Tagger end-to-end (upload → corpus action → map pins)

## Purpose
Verify that the **Location Tagger** default agent, when wired as a
`CorpusAction`, auto-creates geocoded `OC_COUNTRY` / `OC_STATE` / `OC_CITY`
annotations on documents and that those annotations surface as pins on the
Corpus Home map.

## Prerequisites
- Migrations applied through the migration that creates the Location Tagger
  agent (agents app `0015_create_location_tagger_agent`).
- At least one superuser exists (the default agent is created with the first
  superuser as its creator).
- A corpus you can add documents to.
- An LLM backend configured (the agent runs through the normal agent stack).

## Steps

1. Confirm the default agent exists.
   ```bash
   docker compose -f local.yml run --rm django python manage.py shell -c "
   from opencontractserver.agents.models import AgentConfiguration
   a = AgentConfiguration.objects.get(name='Location Tagger')
   print(a.scope, a.is_active, a.is_public, a.available_tools, a.badge_config)
   "
   ```
   Expected: `GLOBAL True True ['add_annotations_from_exact_strings'] {...globe...}`.

2. Create a corpus action that runs the Location Tagger on document add.
   ```bash
   docker compose -f local.yml run --rm django python manage.py shell -c "
   from opencontractserver.agents.models import AgentConfiguration
   from opencontractserver.corpuses.models import Corpus, CorpusAction
   from django.contrib.auth import get_user_model
   User = get_user_model()
   u = User.objects.filter(is_superuser=True).first()
   corpus = Corpus.objects.first()
   agent = AgentConfiguration.objects.get(name='Location Tagger')
   CorpusAction.objects.create(
       name='Auto location tagger',
       corpus=corpus,
       agent_config=agent,
       task_instructions=(
           'Find every country, U.S. state, and city mentioned in the document '
           'and tag them as OC_COUNTRY / OC_STATE / OC_CITY, supplying '
           'country/state hints to disambiguate ambiguous names.'
       ),
       trigger='add_document',
       creator=u,
   )
   print('CorpusAction created for corpus', corpus.id)
   "
   ```

3. Upload a document containing known place mentions (e.g. a text/PDF file
   mentioning 'Paris, France' and 'Austin, Texas'). The `ADD_DOCUMENT`
   trigger fires the agent asynchronously.

4. Inspect the created annotations and their geocoded `data`.
   ```bash
   docker compose -f local.yml run --rm django python manage.py shell -c "
   from opencontractserver.annotations.models import Annotation
   from opencontractserver.constants.annotations import (
       OC_CITY_LABEL, OC_COUNTRY_LABEL, OC_STATE_LABEL,
   )
   qs = Annotation.objects.filter(
       annotation_label__text__in=[OC_COUNTRY_LABEL, OC_STATE_LABEL, OC_CITY_LABEL]
   )
   for a in qs:
       print(a.annotation_label.text, a.raw_text, a.data)
   "
   ```

5. Open Corpus Home for the corpus in the frontend and switch to the map view.

## Expected Results
- Step 1: the Location Tagger agent is present, active, public, global, and
  exposes only `add_annotations_from_exact_strings`.
- Step 4: each geographic annotation's `data` contains `canonical_name`,
  `lat`, `lng`, and `admin_codes`; e.g. 'Austin' →
  `admin_codes == {"iso_alpha2": "US", "admin1": "TX"}`, and 'Paris, France' →
  `admin_codes["iso_alpha2"] == "FR"`.
- Step 5: pins appear on the Corpus Home map at the resolved coordinates.

## Cleanup
```bash
docker compose -f local.yml run --rm django python manage.py shell -c "
from opencontractserver.annotations.models import Annotation
from opencontractserver.constants.annotations import (
    OC_CITY_LABEL, OC_COUNTRY_LABEL, OC_STATE_LABEL,
)
from opencontractserver.corpuses.models import CorpusAction
# Scope the cleanup to the corpus this test targeted. A global
# annotation_label__text__in delete would wipe OC_* annotations across EVERY
# corpus in the database — never run that against a populated staging/prod DB.
action = CorpusAction.objects.filter(name='Auto location tagger').first()
if action is not None:
    Annotation.objects.filter(
        corpus=action.corpus,
        annotation_label__text__in=[OC_COUNTRY_LABEL, OC_STATE_LABEL, OC_CITY_LABEL],
    ).delete()
    action.delete()
"
```
