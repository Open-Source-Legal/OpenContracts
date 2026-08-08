- **Documented the authority tagging system and authority packs against what
  #2215 actually shipped**, and wired the pack screenshots the component tests
  have been capturing into the docs that describe them.
  - `docs/architecture/authority-console.md` — the **Authority Packs tab**
    section was four paragraphs with no visuals despite nine
    `admin--authority-packs-tab--*` / `admin--pack-preflight-modal--*`
    screenshots being captured on every screenshot run and referenced by no
    doc. It now shows the catalog, the derived status-badge vocabulary
    (`Invalid` / `Available` / `Partially installed` / `Installed privately` /
    `Partially public` / `Fully public`, per `PacksTab.tsx::packStatus`), the
    empty catalog as the symptom of an unmounted pack directory, and the
    preflight modal — including the `expectedFingerprint` round-trip that
    rejects a pack edited between preflight and install, the publish opt-in's
    charter gate, and the `load_authority_pack --check` headless equivalent.
  - `docs/guides/authoring-authority-packs.md` —
    documents the previously undocumented **`sources.yaml` source plan** and the
    out-of-process collector (`scripts/authority_import/`) that turns it into
    GUI-importable corpus ZIPs; adds the **in-pack import contract** (relative
    imports resolve wherever a pack is mounted, an absolute in-tree dotted path
    silently fails to register the module's providers once sideloaded — the
    defect that stranded 15 providers); points at the schema-v2 fixture pack
    `tests/fixtures/authority_packs/example_utility` as the complete worked
    example alongside v1 `bolivia`; explains the `pack.yaml`-required root scan
    and `E2E_RUN_AUTHORITY_IMPORTS`; and replaces two dead
    `test_grid_dossier_*` test references (those modules moved out of the tree
    with the packs) with the modules that exist.
  - `docs/architecture/reference-web-enrichment.md` — states where the Tier-1
    detection vocabulary comes from, closing the gap between the tagging engine
    and the packs that extend it (`prefixes`/`aliases` plus a pack's optional
    `shape_rules` / `abbreviations`), so standing up detection for a new body of
    law reads as the data change it is.
