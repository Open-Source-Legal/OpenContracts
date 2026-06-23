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
- **Closed an IPv4-mapped IPv6 bypass of the same guard.** `_assert_public_ip`
  now unwraps an IPv4-mapped IPv6 address (`::ffff:a.b.c.d`) to its embedded
  IPv4 before the property/CGNAT checks. On CPython 3.11 the IPv6
  `is_private` / `_CGNAT_NETWORK` checks do not reflect the mapped IPv4 for the
  CGNAT-mapped form, so a resolver returning `::ffff:100.64.0.1` would have
  slipped past every check; unwrapping makes the guard version-independent for
  the mapped forms of private/loopback/link-local/CGNAT addresses. The CGNAT
  membership test is additionally guarded by `isinstance(ip, IPv4Address)` so a
  native IPv6 address is skipped rather than relying on `IPv6Address in
  IPv4Network` returning `False` (true only on CPython 3.11+; 3.10 raises
  `TypeError`). Covered by parametrized regressions in `test_safe_http.py`
  (mapped forms rejected; public native IPv6 passes).
