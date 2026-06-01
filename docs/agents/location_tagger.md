# Location Tagger Agent

The **Location Tagger** is a built-in, global default agent that automatically
finds place names in a document and turns them into *geocoded* annotations:
`OC_COUNTRY`, `OC_STATE`, and `OC_CITY`. Each annotation it creates carries the
resolved coordinates and administrative codes in its `data` payload, so the
places show up as pins on the **Discover** and **Corpus Home** maps.

It is wired to run through the ordinary
[corpus-actions](../walkthrough/step-9-corpus-actions.md) framework — the
same execution path used by the built-in Document Assistant and Corpus
Assistant — so you configure it once on a corpus and it runs automatically.

## What it does

For every place mention it recognises, the agent calls the
`add_annotations_from_exact_strings` tool with the appropriate label and a set
of *hints*. When the label is one of the geographic labels
(`OC_COUNTRY` / `OC_STATE` / `OC_CITY`), the tool routes the string through the
offline geocoding service ([#1819](https://github.com/Open-Source-Legal/cite/issues/1819))
and stores the result on the annotation:

```json
{
  "canonical_name": "Austin",
  "lat": 30.2672,
  "lng": -97.7431,
  "admin_codes": { "iso_alpha2": "US", "admin1": "TX" },
  "geocoded": true
}
```

Non-geographic labels are unaffected — the `hints` field is simply ignored for
them, so existing callers of the tool keep working unchanged.

## Configuration walkthrough

1. **Migrate.** After deploying, run migrations. The Location Tagger appears as
   a global, public agent in the agent picker:

   ```bash
   docker compose -f production.yml --profile migrate up migrate
   ```

   > **Note — the migration is a one-time snapshot.** It copies
   > `DEFAULT_LOCATION_TAGGER_INSTRUCTIONS` from settings into the agent's
   > `system_instructions` column at creation time. If you later improve the
   > prompt in `config/settings/base.py`, **existing databases keep the old
   > prompt** — update the `Location Tagger` agent record via the Django admin
   > (or a follow-up data migration) to pick up the revision.

   > **Note — a superuser must exist when the migration runs.** The agent is
   > created with a `creator`, so the migration looks for an existing superuser.
   > In environments where migrations run **before** any superuser is seeded
   > (e.g. an ephemeral CI database, or a containerised first boot where
   > migrations precede fixtures), it logs a warning and skips creation rather
   > than failing the migration — which means **the agent is never created**. If
   > the **Location Tagger** is absent from the agent picker after deploying,
   > seed a superuser and then either re-run the data migration
   > (`python manage.py migrate agents 0014 && python manage.py migrate agents 0015`)
   > or create the agent record from the Django admin.

2. **Add a corpus action.** On the corpus you want tagged, create a
   `CorpusAction` that points at the **Location Tagger** agent and choose a
   trigger:

   | Trigger        | When it fires                              | Use it to…                          |
   | -------------- | ------------------------------------------ | ----------------------------------- |
   | `ADD_DOCUMENT` | Every time a document is added to the corpus | Auto-tag new uploads as they arrive |
   | `MANUAL_BATCH` | When you run the action on demand          | Back-fill an existing corpus        |

3. **Upload or back-fill.** With `ADD_DOCUMENT`, upload a document containing
   place mentions and the action fires automatically. With `MANUAL_BATCH`,
   trigger the action to sweep documents already in the corpus.

4. **See the pins.** Open **Corpus Home** (or **Discover**) and switch to the
   map view; the geocoded annotations render as pins.

## Worked example

Given a paragraph such as:

> "The summit was held in **Paris, France**, with follow-up meetings in
> **Austin, Texas** and **Paris, Texas**."

the agent emits three city annotations, disambiguated via hints:

| Mention         | Label       | `hints` sent by the agent          | Resolved `admin_codes`            |
| --------------- | ----------- | ---------------------------------- | --------------------------------- |
| Paris, France   | `OC_CITY`   | `{ "country": "FR" }`              | `{ "iso_alpha2": "FR" }`          |
| Austin, Texas   | `OC_CITY`   | `{ "country": "US", "state": "TX" }` | `{ "iso_alpha2": "US", "admin1": "TX" }` |
| Paris, Texas    | `OC_CITY`   | `{ "country": "US", "state": "TX" }` | `{ "iso_alpha2": "US", "admin1": "TX" }` |

Without the `state` hint, "Paris" would be ambiguous; the hint lets the
geocoder pick **Paris, TX** over **Paris, France**.

## Limitations

- **Offline reference dataset.** Resolution uses the bundled reference data
  (ISO 3166-1 countries, US states, and a curated set of cities). Places not in
  the dataset cannot be geocoded and are skipped.
- **No ambiguous-name resolution beyond hints.** Disambiguation relies on the
  `country` / `state` hints the agent supplies. A bare, ambiguous place name
  resolves to the dataset's best single match.
- **Exact-string matching.** Annotations are created only where the place name
  appears verbatim in the document text.
- **Re-runs are not deduplicated yet.** Running the tagger again over an
  already-tagged document may create duplicate annotations; idempotent
  re-tagging is a planned follow-up.

## Related

- [#1819](https://github.com/Open-Source-Legal/cite/issues/1819) — geocoding foundation (`resolve_place`, `OC_*` labels)
- [#1820](https://github.com/Open-Source-Legal/cite/issues/1820) / [#1821](https://github.com/Open-Source-Legal/cite/issues/1821) — the Discover and Corpus Home map views
