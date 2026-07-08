# Generate / Regenerate the GraphQL Schema File

The GraphQL layer is **strawberry-graphql** (migrated from graphene — see
`docs/architecture/graphql_strawberry_migration.md`). The served schema's
shape is pinned by a golden SDL contract at
`config/graphql/schema.graphql`, enforced by
`opencontractserver/tests/test_schema_parity.py`.

**Regenerate the golden SDL** (do this deliberately, only when you intend to
change the public API surface — the parity test will otherwise fail):

```bash
docker compose -f local.yml run django python manage.py shell -c \
  "from config.graphql.schema import schema; from graphql import print_schema; \
   open('config/graphql/schema.graphql','w').write(print_schema(schema._schema))"
```

Then review the diff to `config/graphql/schema.graphql` — it is the
human-readable record of every type/field/argument the API exposes.
