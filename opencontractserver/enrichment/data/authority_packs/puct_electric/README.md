# PUCT Electric authority pack

This portable pack keeps controlling Commission authorities separate from the
broader proceeding record:

- `puct-electric-rules-and-orders`
- `puct-large-load-proceedings`

It owns `tx-admin-puct`, `puct-project`, and `puct-order`. Other packs reference
PUCT orders through those canonical keys instead of creating publisher-specific
duplicates. The Interchange adapter must preserve every attachment and assign
the proper authority weight; it must not silently discard non-PDF files.

Load the pack with:

```bash
python manage.py load_authority_pack \
  --path opencontractserver/enrichment/data/authority_packs/puct_electric \
  --creator <email>
```

Adapters emit the shared `AuthoritySourceRecord` contract into the general
authority bootstrap and document-versioning rail. Seed locators and
relationships are not production-visible until legal review is complete.
