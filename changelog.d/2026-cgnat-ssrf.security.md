- **Closed a CGNAT SSRF gap in the authority-source fetch guard (issue #2026).**
  `opencontractserver/utils/safe_http.py::_assert_public_ip` rejected resolved
  addresses via the `ipaddress` property denylist (`is_private` / `is_loopback`
  / `is_link_local` / `is_multicast` / `is_reserved` / `is_unspecified`), but
  RFC 6598 Carrier-Grade NAT shared address space (`100.64.0.0/10`) is
  classified as **neither** private **nor** reserved **nor** global on current
  CPython — verified `is_private == is_reserved == is_global == False` on 3.11
  and 3.12 — so a host resolving into that block would have passed validation
  and been fetched. It is now rejected explicitly and version-independently via
  a `_CGNAT_NETWORK` membership check, with the CIDR pinned in
  `opencontractserver/constants/safe_http.py::CGNAT_SHARED_ADDRESS_SPACE_CIDR`.
  The `.gov` host allowlist already made exploitation hard in practice (an
  attacker would need an allowlisted host to resolve into the block), but the
  IP guard is defence-in-depth and is also reachable by callers that pass a
  custom `allowlist`. Regression coverage in
  `opencontractserver/tests/test_safe_http.py` rejects the CGNAT block and
  proves the adjacent public addresses (`100.63.255.255`, `100.128.0.0`) still
  pass.
