- New guide **Ingesting Authorities & Adding Providers**
  (`docs/guides/ingesting-authorities.md`, in the mkdocs **Guides** nav section):
  runnable procedures for ingesting a provider-supported authority source
  (surgical shell via `AuthorityDiscoveryService.discover_and_bootstrap`, a
  bounded `CrawlAuthoritiesService.crawl`, and the `/admin/enrichment` runner UI)
  and for adding a new `BaseAuthoritySourceProvider` to flip an authority from
  `unsupported` to supported (contract, skeleton, registry/allowlist/license
  gotchas, and the `AuthorityKeyEquivalence` / agentic-locator no-code
  alternatives). Cross-linked from the reference-web architecture doc. Adds two
  CT-generated documentation screenshots — the enrichment runner with the
  authority crawl enabled and advanced bounds expanded
  (`EnrichmentRunner.ct.tsx`), and the authority-sources monitor filtered to the
  `unsupported` state (`AuthoritySourcesMonitor.ct.tsx`). The mkdocs **Guides**
  section also adopts the previously unlisted CAML import guide.
