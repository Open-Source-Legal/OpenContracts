- **`manage.py install_authority_pack`** (`opencontractserver/corpuses/management/commands/install_authority_pack.py`):
  one-command fetch+install of authority packs from the new out-of-tree pack registry
  ([Open-Source-Legal/authority-packs](https://github.com/Open-Source-Legal/authority-packs), CC BY-SA 4.0 —
  first catalog entry: the Fort Worth, Texas pack, 147 verbatim law sections). Downloads the registry
  tarball (`--repo`/`--ref` overrides; `--tarball` for air-gapped installs), safely extracts the requested
  pack (tarfile `data` filter + pack-name slug validation + compressed and uncompressed size caps) into the new `AUTHORITY_PACK_INSTALL_DIR`
  (default `<root>/.authority_packs`, gitignored), and delegates validation/install to `load_authority_pack`.
  `authority_pack_dirs()` (`opencontractserver/pipeline/registry.py`) now scans the install dir as an
  implicit bundle root, so fetched packs are discoverable with zero env-var wiring. Also adds
  `AUTHORITY_PACK_REGISTRY_URL` (`config/settings/base.py`) and an "Installing from the pack registry"
  section in `docs/guides/authoring-authority-packs.md`. Packs stay out of the platform repo by policy:
  deployments install only the jurisdictions they want, and pack content licensing (share-alike CC) stays
  separate from the MIT platform license.
