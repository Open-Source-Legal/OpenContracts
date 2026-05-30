# Geocoding reference dataset attribution & regeneration

The offline geocoding utility in `opencontractserver/utils/geocoding/`
ships a curated reference dataset bundled inside the repository so that
parser-time geocoding is fully deterministic, network-free, and
redistributable under the project's MIT licence.

## Sources

| File | Source | Licence |
| --- | --- | --- |
| `data/countries.json` | ISO 3166-1 (alpha-2 / alpha-3) names + Wikipedia approximate centroids | Public domain |
| `data/us_states.json` | USPS state abbreviations + US Census Bureau approximate centroids | Public domain |
| `data/cities.json` | Curated subset of [GeoNames `cities1000`](https://download.geonames.org/export/dump/) (population ≥ 1000) | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) — © GeoNames |

GeoNames data redistributed under the bundled dataset retains its
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) attribution
requirement. The `_meta.source` field inside each JSON file carries the
upstream attribution; do not strip it when serialising.

## Bundled scope

The current bundle is a deliberately small **seed** of the full GeoNames
`cities1000` set:

- ~190 countries (ISO 3166-1 complete)
- 50 US states + DC + 5 territories
- ~150 major world cities, including the ambiguity cases needed by the
  resolver tests (multiple "Paris" rows: FR, US-TX, US-TN, US-KY)

The seed is sufficient for the foundation issue (#1819) and the map UI
(#1820 / #1821) demos but does not cover every city a user might type.
Full `cities1000` coverage is roughly 150k rows / ~5 MB JSON and is
intentionally not committed pending a curation review.

## Regeneration recipe

When richer coverage is required:

1. Download the latest `cities1000.zip` from
   <https://download.geonames.org/export/dump/cities1000.zip> (~12 MB
   compressed, ~30 MB unpacked).
2. Run a one-off conversion script (not yet committed — write to spec
   below). The GeoNames `allCountries`-style TSV columns are:

   ```
   geonameid  name  asciiname  alternatenames  latitude  longitude  feature_class  feature_code  country_code  cc2  admin1_code  admin2_code  admin3_code  admin4_code  population  elevation  dem  timezone  modification_date
   ```

   Filter to `feature_class == 'P'` (populated places) and project to
   the schema used by `cities.json`:

   ```json
   {
     "name": "<name>",
     "country_code": "<country_code>",
     "admin1_code": "<admin1_code>",
     "lat": <latitude>,
     "lng": <longitude>,
     "population": <population as int>,
     "aliases": ["<comma-split asciiname/alternatenames>"]
   }
   ```

3. Place the regenerated file at
   `opencontractserver/utils/geocoding/data/cities.json` and bump
   `_meta.schema_version` if you change the field set.
4. Run the geocoding tests:

   ```bash
   docker compose -f test.yml run django pytest \
     opencontractserver/tests/test_geocoding_service.py -n 4 --dist loadscope
   ```

5. Spot-check ambiguous tokens ("Paris", "Springfield", "London", "Cambridge")
   still resolve to the expected canonical row.

For US states + countries, refreshes are usually unnecessary — both lists
are stable. If a new ISO 3166-1 country is admitted, append a row to
`countries.json` with the official name, alpha-2, alpha-3, approximate
centroid, and any aliases.

## Why offline?

- **Deterministic**: same input → same coords forever. No "the geocoder
  changed its mind" follow-ups when a corpus reindex hits a different
  upstream snapshot.
- **No network at parse time**: batch parsing of large corpuses can't
  tolerate a rate-limited external API.
- **Normalization is free**: "USA" / "United States" / "U.S." all
  canonicalize to the same row in the dataset via the bundled aliases.
- **MIT-friendly**: ISO 3166 is public domain; GeoNames is CC BY 4.0,
  which is redistributable inside the repository under the attribution
  carried in `_meta.source` and this credits page.
