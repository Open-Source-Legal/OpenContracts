# PUCT Interchange TLS intermediates

`interchange.puc.texas.gov` currently serves a publicly trusted leaf
certificate without sending its two intermediate certificates. The standalone
collector adds this audited bundle to normal platform trust; hostname and
certificate-chain verification remain enabled.

The certificates are the issuing authorities named by the publisher leaf's AIA
chain:

- Cloudflare TLS Issuing ECC CA 1, SHA-256
  `29:64:FD:32:10:EA:68:FA:A2:B4:A8:49:B3:62:43:D3:3F:74:42:9D:1B:43:CE:01:9E:7B:15:4E:AC:77:59:BA`,
  valid through 2033-10-28.
- SSL.com TLS Transit ECC CA R2, SHA-256
  `5D:1B:C3:99:27:4E:64:9E:1C:72:69:7D:E9:1A:54:AD:72:50:88:C5:22:1C:B6:1E:17:EE:9C:29:0B:C4:2A:92`,
  valid through 2037-10-17.
- SSL.com TLS ECC Root CA 2022, SHA-256
  `C3:2F:FD:9F:46:F9:36:D1:6C:36:73:99:09:59:43:4B:9A:D6:0A:AF:BB:9E:7C:F3:36:54:F1:44:CC:1B:A1:43`,
  valid through 2046-08-19. This root is included for standalone images whose
  platform trust store predates the 2022 root.

They add no publisher host and do not bypass the shared SSRF, DNS-pinning,
redirect, size, or TLS-name checks.
