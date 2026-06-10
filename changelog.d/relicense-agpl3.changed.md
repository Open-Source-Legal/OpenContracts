- **Relicensed the project from MIT back to the GNU Affero General Public
  License v3.0 (AGPL-3.0).** Replaced `LICENSE` with the verbatim AGPL-3.0 text;
  set `frontend/package.json` `license` to `AGPL-3.0-only`; switched the license
  badges and prose in `README.md`, `docs/index.md`, `docs/credits/geonames.md`,
  and `CLAUDE.md` to AGPL-3.0; and updated the two per-file MIT headers
  (`config/graphql/filters.py`,
  `opencontractserver/tests/test_annotated_document_import.py`). The cookie
  consent modal's warranty-disclaimer comments
  (`frontend/src/components/cookies/CookieConsent.tsx`) no longer describe the
  shipped license as MIT. AGPL-3.0 is strong copyleft with a network-use
  (Section 13) source-availability requirement, so the prior "no copyleft
  strings attached" / "build proprietary products on it" marketing language was
  rewritten to describe the copyleft terms accurately. The `corpus.license`
  feature field and its tests are unaffected — `"MIT"` there is user-supplied
  corpus metadata, not the project license.
