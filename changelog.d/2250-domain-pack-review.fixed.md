`install_domain_pack`'s C4 preflight (`opencontractserver/corpuses/management/commands/install_domain_pack.py::Command._preflight`)
validated `equivalences[].from_key`/`to_key` without stripping whitespace, while
the shared writer (`upsert_equivalence`) strips before validating — a manifest
row with incidental leading/trailing whitespace could fail preflight and be
refused even though the writer would have accepted it. Preflight now strips
before validating, matching the writer exactly.

A base pack that materialised into `AUTHORITY_PACK_INSTALL_DIR` but then failed
its real (non-`--check`) `load_authority_pack` call left its directory behind
unloaded. Since pipeline discovery unions every discoverable directory's
`source_hosts` into the SSRF allowlist regardless of DB-load state, the failed
pack's hosts stayed live in the trust boundary until the next re-run overwrote
it. The install loop now removes the failed pack's own materialised directory
before re-raising; packs that installed earlier in the same run are untouched.

A plain install (no `--check`) missing `--creator` printed a `--check`-flavoured
"C1 pack validity not checked" hint immediately before the actual
"--creator is required to install" refusal. The hint is now gated to `--check`
runs, where it is accurate.
