- Authority verify+license gate (`enrichment/services/authority_gate_service.py`)
  now distinguishes a non-public-domain provider license
  (`blocked_license`) from an off-allowlist source domain (new
  `blocked_domain` state) so operators can filter `AuthorityFrontier` by state
  alone without parsing the `reason` string. A fetched result with no source URL
  is now `unlocated` rather than silently bypassing the domain allowlist on its
  license alone. Adds the `blocked_domain` choice to
  `AuthorityFrontier.discovery_state` (migration `0088`). Per-call agentic bounds
  (`max_agent_requests`, `max_fetch_chars`) are now tunable ClassVars, and
  `candidate_sources` audit entries use a typed `_AuditRecord` schema.
