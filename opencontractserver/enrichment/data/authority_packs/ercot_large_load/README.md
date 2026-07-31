# ERCOT Large Load authority pack

This portable pack separates three different research roles:

- `ercot-current-large-load-rules`
- `ercot-large-load-revision-history`
- `ercot-large-load-implementation`

It owns the Planning Guide, Protocol, revision-request, market-notice, and form
namespaces declared in its mapping file. The seed relationship graph covers the
PGRR 145/NPRR 1325 vertical slice without claiming legal approval; every edge
remains gated until a reviewer verifies affected provisions and source records.

Load the pack with:

```bash
python manage.py load_authority_pack \
  --path opencontractserver/enrichment/data/authority_packs/ercot_large_load \
  --creator <email>
```

Adapters emit the shared `AuthoritySourceRecord` contract into the general
authority bootstrap and document-versioning rail. Original PDF, DOCX, and other
artifacts remain on that common ingestion path, with stable source identity kept
separate from document-version identity.
