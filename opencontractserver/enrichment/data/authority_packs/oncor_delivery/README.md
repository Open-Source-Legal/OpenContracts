# Oncor Delivery authority pack

This portable pack separates:

- `oncor-current-delivery-tariff`
- `oncor-tariff-history`
- `oncor-service-requirements`

It owns `oncor-tariff`, `oncor-rider`, and `oncor-service-guide`. PUCT approval
records remain PUCT-owned `puct-order` authorities and are linked rather than
duplicated under an Oncor namespace.

Load the pack with:

```bash
python manage.py load_authority_pack \
  --path opencontractserver/enrichment/data/authority_packs/oncor_delivery \
  --creator <email>
```

Adapters emit the shared `AuthoritySourceRecord` contract into the general
authority bootstrap and document-versioning rail. Public availability is not a
license determination: live collection remains subject to approval under the
authority-source gate.
