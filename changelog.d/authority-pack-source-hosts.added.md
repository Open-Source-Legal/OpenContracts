- **Authority packs can declare their own SSRF source hosts.** A scraping pack
  lists the hosts it fetches from in `pack.yaml` (`source_hosts: [...]`); those are
  read from every installed pack (in-tree under `authority_packs/` or on the
  `AUTHORITY_PACK_PATHS` setting) and unioned with the hardcoded
  `PUBLIC_DOMAIN_SOURCE_HOSTS` baseline at runtime, so a fetching pack is portable
  as a directory without editing `constants/safe_http.py`. The union is injected
  into the pure `safe_http` util via a registered provider
  (`register_allowlist_provider`) so the util never imports the enrichment layer;
  every pack-added host is logged. The SSRF mechanism is unchanged (HTTPS-only,
  public-IP, per-redirect-hop revalidation, size caps) — a pack only widens *which*
  hosts are reachable, and only once installed (the install is the trust decision).
  `AuthorityGateService` now consults the same effective allowlist as the fetch.
  `load_authority_pack` validates `source_hosts` shape fail-fast. New module
  `opencontractserver/enrichment/services/authority_source_hosts.py`; tests in
  `test_authority_source_hosts.py`.
