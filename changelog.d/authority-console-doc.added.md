- **Authority Console architecture doc.** Added
  `docs/architecture/authority-console.md` — an as-built reference for the unified
  Authority Console (PR #2037, issue #1997 management layer): the `/admin/authority`
  tabs and routes, the `AuthorityNamespace`-as-spine model (string-join `detail()`,
  the `source` baseline/manual ownership marker + loader skip, `created_by`),
  `AuthorityNamespaceService` / `AuthoritySourceProviderService` / the
  `AuthorityFrontierService` action verbs over the single `mark()` primitive, the
  one `is_authority_admin` gate, the GraphQL surface, migrations 0099/0100, and a
  Design notes section preserving the chosen architecture and five settled design
  decisions. Wired into the mkdocs `Architecture` nav after Reference-Web Enrichment.
- **Refreshed sibling docs.** Updated `docs/architecture/reference-web-enrichment.md`
  and `docs/guides/ingesting-authorities.md` to name the merged-in tabs (the
  standalone "enrichment runner" → **Runs tab**; the "authority-sources monitor" →
  **Queue tab**) and point at the committed
  `authorities--console-queue--with-data.png` screenshot, replacing references to the
  deleted standalone panels.
