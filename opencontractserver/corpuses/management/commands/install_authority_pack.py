"""Fetch an authority pack from the pack registry repo and install it.

The one-command install path for out-of-tree authority packs::

    python manage.py install_authority_pack fort_worth --creator admin --public
    python manage.py install_authority_pack --list
    python manage.py install_authority_pack fort_worth --check       # fetch + preflight only
    python manage.py install_authority_pack fort_worth --fetch-only  # materialise, no DB writes

The registry is any git host serving ``<repo>/archive/<ref>.tar.gz`` tarballs
(GitHub does) whose repository root contains one directory per pack — the
layout of https://github.com/Open-Source-Legal/authority-packs. Default repo
comes from ``settings.AUTHORITY_PACK_REGISTRY_URL``; override with ``--repo``,
or skip the network entirely with ``--tarball /path/to/archive.tar.gz``
(air-gapped installs, tests).

Fetched packs land in ``settings.AUTHORITY_PACK_INSTALL_DIR`` — an implicit
pack bundle root scanned by ``authority_pack_dirs()`` — and are then installed
via the existing ``load_authority_pack`` command (preflight validation,
idempotent convergence, ``--public`` publication, post-install re-link). The
install dir is a managed fetch cache: re-installing a pack replaces its
directory (rmtree + move, not an atomic swap — a crash mid-replace leaves the
pack absent until the command is re-run). Hand-curated packs belong in
``AUTHORITY_PACK_PATHS``/``ROOTS``.

Grammar-tier pack taxonomy extensions (``abbreviations``/``shape_rules``) are
``lru_cache``d per process, so web/worker processes need a restart after a
first-time install — the command prints the reminder.
"""

import re
import shutil
import tarfile
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

# Pack directories are addressed by name inside the install dir; constrain to a
# conservative slug so a hostile registry listing can never traverse paths.
PACK_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")

# Ceiling on the fetched archive; packs are text and compress well, so anything
# near this size is a mistake, not a pack.
MAX_TARBALL_BYTES = 500 * 1024 * 1024

# Ceiling on the *uncompressed* bytes extracted from the archive, so a small
# malicious gzip can't expand into something enormous during extraction.
MAX_EXTRACTED_BYTES = 2 * 1024 * 1024 * 1024

DOWNLOAD_TIMEOUT_SECONDS = 120


def _download_tarball(url: str, dest: Path) -> None:
    """Stream ``url`` to ``dest``, enforcing scheme and size limits.

    Isolated so tests (and air-gapped flows) can bypass it via ``--tarball``.
    """
    import requests

    if not url.lower().startswith(("http://", "https://")):
        raise CommandError(f"Registry URL must be http(s), got: {url}")

    with requests.get(url, stream=True, timeout=DOWNLOAD_TIMEOUT_SECONDS) as resp:
        if resp.status_code != 200:
            raise CommandError(
                f"Registry tarball fetch failed (HTTP {resp.status_code}): {url}"
            )
        written = 0
        with open(dest, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                written += len(chunk)
                if written > MAX_TARBALL_BYTES:
                    raise CommandError(
                        f"Registry tarball exceeds {MAX_TARBALL_BYTES} bytes; refusing"
                    )
                fh.write(chunk)


def _tarball_url(repo: str, ref: str) -> str:
    return f"{repo.rstrip('/')}/archive/{ref}.tar.gz"


def _top_prefix(names: list[str]) -> str:
    """Return the single top-level directory prefix of a git archive tarball."""
    tops = {n.split("/", 1)[0] for n in names if n and not n.startswith("/")}
    tops.discard("")
    if len(tops) != 1:
        raise CommandError(
            f"Unexpected tarball layout (top-level entries: {sorted(tops)[:5]}...); "
            "expected a single git-archive root directory"
        )
    return next(iter(tops))


def materialise_pack(staged_pack: Path, pack: str, stdout=None) -> Path:
    """Move an extracted pack into ``AUTHORITY_PACK_INSTALL_DIR``; return its path.

    Loading a pack into the database is only half of installing it. The install
    dir is an implicit discovery root (``pipeline.registry.authority_pack_dirs``),
    and three things are read from the pack DIRECTORY at runtime rather than from
    the database:

      * ``source_hosts`` — unioned into the SSRF allowlist, so a pack that
        fetches from a live source can only reach it while its directory is
        discoverable. "Installing the pack IS the trust decision."
      * ``shape_rules`` and ``abbreviations`` — the pack's citation vocabulary,
        merged into ``classify_prefix`` and the Tier-2a grammar.
      * in-pack provider modules, which register with the pipeline registry.

    A caller that loads straight from a temporary extraction directory gets the
    sections and the taxonomy rows and silently loses all three, with nothing
    failing at install time — which is why this is shared rather than
    reimplemented per command.
    """
    # `pack` is used as a path component twice below, and one of those uses is
    # an rmtree. `Path.__truediv__` does not collapse or reject `..`, so a value
    # like "../../../../var/lib/x" resolves outside the install root and would
    # delete whatever is there. Callers are expected to validate their input,
    # but this is the destructive primitive — it validates for itself rather
    # than trusting every present and future caller to have done it.
    if not PACK_NAME_RE.match(pack):
        raise CommandError(
            f"Pack name {pack!r} is not a plain slug; refusing to use it as a path"
        )
    if not (staged_pack / "pack.yaml").is_file():
        raise CommandError(
            f"Extracted pack {pack!r} is missing pack.yaml; refusing to install"
        )
    install_root = Path(settings.AUTHORITY_PACK_INSTALL_DIR).expanduser()
    install_root.mkdir(parents=True, exist_ok=True)
    dest = install_root / pack
    if dest.exists():
        if stdout is not None:
            stdout.write(f"Replacing previously fetched pack at {dest}")
        shutil.rmtree(dest)
    shutil.move(str(staged_pack), str(dest))
    return dest


def _report_pack_providers(pack_dir, stdout, style) -> None:
    """Print the provider modules a pack ships, if any. Never imports them.

    Installing a pack that ships ``providers/`` imports its Python into the web
    and worker processes, so the operator should be able to see that surface
    before the install writes anything. Reads the filesystem and, when present,
    the OPTIONAL ``providers:`` declaration in pack.yaml — never the modules.
    """
    from pathlib import Path as _Path

    pack_dir = _Path(pack_dir)
    shipped: list[tuple[str, str]] = []
    for subdir in ("providers", "discovery_providers"):
        component_dir = pack_dir / subdir
        if not component_dir.is_dir():
            continue
        for py in sorted(component_dir.glob("*.py")):
            if not py.name.startswith("_"):
                shipped.append((subdir, py.name))
    if not shipped:
        return

    stdout.write(
        style.WARNING(
            f"This pack ships {len(shipped)} provider module(s). Loading the pack "
            "IMPORTS them into the web and worker processes:"
        )
    )
    for subdir, name in shipped:
        stdout.write(f"    {subdir}/{name}")

    # The declaration is optional and descriptive; show it when a pack has one
    # so the claimed prefixes are visible without reading Python.
    try:
        import yaml

        manifest = yaml.safe_load((pack_dir / "pack.yaml").read_text()) or {}
        for entry in manifest.get("providers") or []:
            stdout.write(
                f"    declares: {entry.get('class')} "
                f"prefixes={entry.get('supported_prefixes')} "
                f"delegates_to={entry.get('delegates_to') or '-'}"
            )
    except Exception:  # noqa: BLE001 - a missing/!parsing manifest is not fatal here
        pass

    from django.conf import settings

    if not getattr(settings, "AUTHORITY_PACK_LOAD_PROVIDERS", True):
        stdout.write(
            style.SUCCESS(
                "    AUTHORITY_PACK_LOAD_PROVIDERS is off — these will NOT be "
                "imported. The pack's text still installs and serves."
            )
        )


class Command(BaseCommand):
    help = (
        "Fetch an authority pack from the pack registry repo into "
        "AUTHORITY_PACK_INSTALL_DIR and install it via load_authority_pack."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "pack",
            nargs="?",
            help="Pack name (top-level directory in the registry repo)",
        )
        parser.add_argument(
            "--list",
            action="store_true",
            dest="list_packs",
            help="List packs available in the registry repo and exit",
        )
        parser.add_argument(
            "--repo",
            default=None,
            help="Registry repo URL (default: settings.AUTHORITY_PACK_REGISTRY_URL)",
        )
        parser.add_argument(
            "--ref",
            default="main",
            help="Branch, tag, or commit to fetch (default: main)",
        )
        parser.add_argument(
            "--tarball",
            default=None,
            help="Path to a local registry tarball; skips the network fetch",
        )
        parser.add_argument(
            "--creator",
            default=None,
            help="Username that owns the seeded corpora (required unless "
            "--list or --fetch-only; load_authority_pack needs it even for --check)",
        )
        parser.add_argument(
            "--public",
            action="store_true",
            help="Publish the pack's corpora (passed through to load_authority_pack)",
        )
        parser.add_argument(
            "--check",
            action="store_true",
            help="Fetch, then preflight-validate only; write nothing to the DB",
        )
        parser.add_argument(
            "--fetch-only",
            action="store_true",
            help="Materialise the pack into the install dir without installing",
        )
        parser.add_argument(
            "--no-relink",
            action="store_true",
            help="Skip the post-install reference re-link sweep",
        )

    def handle(self, *args, **options):
        repo = options["repo"] or settings.AUTHORITY_PACK_REGISTRY_URL
        pack = options["pack"]
        if not options["list_packs"] and not pack:
            raise CommandError("Provide a pack name, or --list to see what's available")
        if pack and not PACK_NAME_RE.match(pack):
            raise CommandError(
                f"Invalid pack name {pack!r} (expected lowercase slug like 'fort_worth')"
            )

        with tempfile.TemporaryDirectory(prefix="authority-pack-") as tmp:
            tmp_path = Path(tmp)
            if options["tarball"]:
                tarball = Path(options["tarball"])
                if not tarball.is_file():
                    raise CommandError(f"--tarball not found: {tarball}")
            else:
                tarball = tmp_path / "registry.tar.gz"
                url = _tarball_url(repo, options["ref"])
                self.stdout.write(f"Fetching {url}")
                _download_tarball(url, tarball)

            with tarfile.open(tarball, "r:gz") as tar:
                names = tar.getnames()
                prefix = _top_prefix(names)

                pack_dirs = sorted(
                    {
                        n.split("/")[1]
                        for n in names
                        if n.count("/") == 2 and n.endswith("/pack.yaml")
                    }
                )
                if options["list_packs"]:
                    if not pack_dirs:
                        self.stdout.write("No packs found in the registry repo.")
                    for name in pack_dirs:
                        self.stdout.write(name)
                    return

                if pack not in pack_dirs:
                    raise CommandError(
                        f"Pack {pack!r} not found in registry (available: "
                        f"{', '.join(pack_dirs) or 'none'})"
                    )

                # Extract only the requested pack, stripping the archive's
                # top-level prefix. The 'data' filter refuses absolute paths,
                # parent-directory traversal, symlink escapes, and device
                # members, and the running size cap bounds decompression-bomb
                # expansion — the registry repo is trusted-ish, but a tarball
                # is attacker-shaped input and costs nothing to sanitise.
                want = f"{prefix}/{pack}/"
                staged = tmp_path / "staged"
                extracted = 0
                for member in tar.getmembers():
                    if not member.name.startswith(want):
                        continue
                    extracted += member.size
                    if extracted > MAX_EXTRACTED_BYTES:
                        raise CommandError(
                            f"Pack {pack!r} expands past {MAX_EXTRACTED_BYTES} "
                            "bytes; refusing"
                        )
                    member.name = member.name[len(prefix) + 1 :]
                    tar.extract(member, path=staged, filter="data")

            dest = materialise_pack(staged / pack, pack, self.stdout)
            self.stdout.write(self.style.SUCCESS(f"Pack materialised at {dest}"))

        if options["fetch_only"]:
            self.stdout.write(
                "Fetch-only: skipping install. Run load_authority_pack --path "
                f"{dest} to install."
            )
            return

        if not options["creator"]:
            raise CommandError(
                "--creator is required to install or preflight (or use --fetch-only)"
            )

        # Say what code this pack will run, BEFORE any DB writes, and without
        # importing it — reporting a pack's providers by executing them would
        # defeat the point. Static file listing only.
        _report_pack_providers(dest, self.stdout, self.style)

        call_command(
            "load_authority_pack",
            path=str(dest),
            creator=options["creator"],
            check=options["check"],
            public=options["public"],
            no_relink=options["no_relink"],
            stdout=self.stdout,
        )

        if not options["check"]:
            self.stdout.write(
                self.style.WARNING(
                    "Restart web/worker processes to pick up the pack's grammar-tier "
                    "taxonomy extensions (pack config is cached per process)."
                )
            )
