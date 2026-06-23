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
  (mapped forms rejected; public native IPv6 passes). Other IPv6-embedded-IPv4
  forms (NAT64 `64:ff9b::/96` + RFC 8215 `64:ff9b:1::/48`, 6to4 `2002::/16`,
  Teredo `2001:0::/32`, deprecated IPv4-compatible `::/96`) need no special
  handling — CPython already flags those whole prefixes `is_private`/
  `is_reserved` on 3.11 and 3.12 — and `test_ipv6_embedded_ipv4_tunnels_rejected`
  now pins that coverage so a future Python change couldn't silently open the
  hole.
- **Strip per-service credentials on cross-host redirects in `safe_fetch_bytes`.**
  Request headers are now dropped of `Authorization` / `Cookie` /
  `Proxy-Authorization` (`CROSS_HOST_STRIPPED_HEADERS`) when a redirect crosses to
  a different host (RFC 9110 §15.4). httpx — unlike browsers / `requests` —
  forwards request headers verbatim across origins, so without this a future
  caller passing a `.gov` API credential could leak it from one allowlisted host
  to another (e.g. `ecfr.gov` → `federalregister.gov`) while following a redirect.
  No current caller passes credentials, so this is forward-looking hardening; the
  default `User-Agent` is preserved across the hop. The cross-origin test compares
  `netloc` (host **and** port), so a same-host/different-port redirect
  (`ecfr.gov` → `ecfr.gov:9000`, a different service) also strips. Covered by
  `TestSafeFetchBytesCredentialStripping` (cross-host, cross-port, same-host).
- **`_assert_public_ip` now fails CLOSED on an empty DNS result.**
  `socket.getaddrinfo` can return an empty list **without** raising `gaierror` on
  some resolver configs; the per-address loop would then be a no-op and the host
  declared safe (fail-open) while httpx still resolves independently at connect
  time. It now raises `SSRFValidationError` when no addresses resolve. Covered by
  `test_empty_getaddrinfo_rejected`.
- **Redirect-loop robustness in `safe_fetch_bytes`.** The hop check now keys off
  `r.has_redirect_location` rather than `r.is_redirect` — in httpx `is_redirect`
  is true for *any* 3xx, so a `304 Not Modified` (or any non-`Location` 3xx) was
  treated as a redirect, resolved `Location: ""` back to the current URL, and
  looped to the redirect cap with a misleading "exceeded N redirects". A present-
  but-empty `Location:` now fails fast with a clear error, and a negative
  `Content-Length` (e.g. `-1`, which parsed cleanly and slipped the `> max_bytes`
  guard) is rejected as malformed. None are SSRF bypasses (the loop is bounded
  and the streamed-bytes cap is the real backstop), but they remove wasted hops
  and misleading diagnostics under server misbehaviour. Covered by
  `test_empty_location_header_rejected`, `test_non_location_3xx_not_followed_as_redirect`,
  and `test_negative_content_length_raises`.
