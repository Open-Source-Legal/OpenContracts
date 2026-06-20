- **Authority discovery: municipal citation grammar (Tier-2a, issue #1995).**
  The reference-enrichment engine now detects municipal-code and ordinance
  citations, completing the federal/state/municipal trio deliberately deferred
  from Phase 1 (#1990). Two layers, mirroring the established state-code table +
  bare-act open-vocabulary pattern:
  - **Known municipal codes** — a new `MUNICIPAL_CODE_ABBREVIATIONS` table
    (`opencontractserver/enrichment/abbreviations.py`) maps exact code names
    (e.g. "San Francisco Municipal Code", "S.F. Mun. Code", "N.Y.C. Admin.
    Code", "Houston Code of Ordinances") to a `muni-<city-slug>` canonical-key
    prefix, the full hierarchical jurisdiction (`us-ca-san-francisco`), and
    `authority_type=municipal-ordinance`, at `_CONF_MUNICIPAL` (0.8). Adding a
    city is a data edit, never a grammar change.
  - **Open-vocabulary shape grammar** — `GenericCitationExtractor` now matches
    `[City] Municipal Code § N`, `Mun. Code §`, `Code of Ordinances §`, and
    `Ordinance No. N` forms for cities outside the table
    (`opencontractserver/enrichment/grammars.py`), keyed under the SAME
    `muni-<city-slug>` namespace (jurisdiction left `None` — free text reveals a
    city but not its state) at `_CONF_MUNICIPAL_GENERIC` (0.6). A captured city
    therefore shares its prefix with any table entry for the same city, so the
    two never fragment, and adding the city to the table later upgrades existing
    mentions instead of orphaning them.
  - **Precision guards** (held to the federal/state bar): a `§`/`Section`/`Sec.`
    + number anchor is mandatory (so prose like "the city adopted a new
    Municipal Code" never matches); the code phrase must be capitalised
    (lowercase "municipal code" is excluded); "Administrative Code" is kept out
    of the open-vocab grammar so "Texas Administrative Code" (a STATE
    regulation) is never mis-tagged municipal; the table pass claims its span so
    a known code never double-emits with its generic shadow; and every municipal
    confidence is calibrated below structured federal cites (< 0.9).
  - `classify_prefix` (`opencontractserver/enrichment/constants.py`) recognises
    the `muni` / `muni-<city>` prefix family by shape, so a municipal key is
    never stranded at `(None, None)` authority_type in the frontier or
    governance graph. No migration or `AuthorityNamespace` seed is required
    (table candidates carry their taxonomy on the candidate, exactly like the
    state codes). Tests: golden cross-municipality corpus, false-positive
    guards, confidence calibration, OCR tolerance, and dedup in
    `opencontractserver/tests/test_generic_grammars.py`,
    `test_abbreviations.py`, `test_enrichment_classification_constants.py`.
