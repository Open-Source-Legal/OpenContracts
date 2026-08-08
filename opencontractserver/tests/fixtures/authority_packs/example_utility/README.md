# `example_utility` — authority-pack test fixture

A complete, deliberately fictional schema-v2 authority pack. It exists so the
loader, taxonomy, relationship, and source-plan machinery can be tested against
a realistic multi-corpus pack without the product tree shipping any real
jurisdiction's regulatory data.

Nothing here is a real code, rule, order, or publisher; `publisher.example` is
reserved by RFC 2606 and is never fetched.

It lives under `tests/fixtures/` rather than
`enrichment/data/authority_packs/` on purpose: `authority_pack_dirs()`
enumerates every immediate subdirectory of that root, so a fixture placed there
would become a pack every install scans, registers providers from, and offers
in the Authority Console catalog. Tests mount this one explicitly with
`override_settings(AUTHORITY_PACK_PATHS=[...])` or by passing its path to
`load_authority_pack`.

The shipped example pack that *is* installable is `bolivia`. Real-world packs
are sideloaded — see `docs/guides/authoring-authority-packs.md`.
