# Texas Electric Law authority pack

This portable pack defines two independently curated corpora:

- `texas-electric-statutes` — current controlling statutory text.
- `texas-large-load-legislative-history` — noncontrolling official history.

The mapping file owns `tx-util`, `tx-sb`, and `tx-hb`. Seed specs contain
explicit review-required locators so an installation is structurally testable
without mistaking a summary for law. The approved source adapters refresh those
locators through the official Texas Constitution and Statutes Service at
`tcss.legis.texas.gov`; retired `statutes.capitol.texas.gov/Docs/...` URLs are
not part of the pack contract.

Load the pack with:

```bash
python manage.py load_authority_pack \
  --path opencontractserver/enrichment/data/authority_packs/texas_electric_law \
  --creator <email>
```

Adapters emit the shared `AuthoritySourceRecord` contract into the general
authority bootstrap and document-versioning rail. The pack does not maintain a
parallel persistence path. Charters, fixture relationships, and golden records
remain pending legal approval until named reviewers are assigned.
