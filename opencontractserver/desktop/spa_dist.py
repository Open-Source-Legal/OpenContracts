"""Acquire the pre-built React SPA for the desktop launcher.

A minimally technical end user has no Node/yarn toolchain, so requiring
``cd frontend && yarn build`` was the single biggest setup cliff. Instead, the
release workflow (``.github/workflows/docker-build-release.yml``) attaches the
built ``frontend/dist`` as a ``opencontracts-frontend-dist.zip`` asset to every
GitHub release, and this module downloads + extracts it into the per-user
app-data dir on first launch. Resolution order (see ``ensure_spa``):

1. a repo-local ``frontend/dist`` (a developer already built it),
2. a previously downloaded copy under app-data ``spa/``,
3. download the release asset (the tag matching this checkout's version, then
   the latest release),
4. build with yarn if a Node toolchain happens to be present (developers),
5. give up with a clear message — the API still runs, the UI is unavailable.

Standard library only (urllib/zipfile); ``certifi``'s CA bundle is used when
importable because python.org macOS builds ship without system root certs.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import ssl
import subprocess
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from opencontractserver.desktop import paths

GITHUB_REPO = "Open-Source-Legal/OpenContracts"
SPA_ASSET_NAME = "opencontracts-frontend-dist.zip"
_HTTP_TIMEOUT_SECONDS = 30
# Defense-in-depth cap on the bundle download — the real dist is ~15 MB, so
# anything approaching this deliberately generous ceiling is wrong, full stop.
MAX_BUNDLE_BYTES = 500 * 1024 * 1024


def release_tag_candidates(version: str) -> list[str]:
    """Map the package ``__version__`` to likely release-tag spellings.

    ``opencontractserver.__version__`` is PEP 440 (``3.0.0b4``) while the repo
    tags releases as ``v3.0.0.b4`` (dot before the pre-release segment), so try
    both spellings before falling back to the latest release.
    """
    dotted = re.sub(r"(\d)((?:a|b|rc)\d+)$", r"\1.\2", version)
    candidates = [f"v{version}"]
    if dotted != version:
        candidates.append(f"v{dotted}")
    return candidates


def _ssl_context() -> ssl.SSLContext:
    # An explicit CA override (corporate proxy, custom bundle) must win — the
    # default context honors SSL_CERT_FILE/SSL_CERT_DIR. certifi is only the
    # fallback for interpreters with no usable system roots (python.org macOS
    # builds ship without them until "Install Certificates.command" is run).
    if os.environ.get("SSL_CERT_FILE") or os.environ.get("SSL_CERT_DIR"):
        return ssl.create_default_context()
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:  # pragma: no cover - certifi arrives with base deps
        return ssl.create_default_context()


def _fetch_json(url: str) -> dict:  # pragma: no cover - network
    request = urllib.request.Request(
        url, headers={"Accept": "application/vnd.github+json"}
    )
    with urllib.request.urlopen(
        request, timeout=_HTTP_TIMEOUT_SECONDS, context=_ssl_context()
    ) as response:
        return json.load(response)


def find_asset_url(release: dict, asset_name: str = SPA_ASSET_NAME) -> str | None:
    """Pull the download URL for ``asset_name`` out of a GitHub release payload."""
    for asset in release.get("assets", []):
        if asset.get("name") == asset_name:
            url = asset.get("browser_download_url")
            return str(url) if url else None
    return None


def _release_asset_urls(
    version: str,
) -> tuple[str, str | None] | None:  # pragma: no cover - network
    """Find the SPA asset (and its ``.sha256`` sibling, when published).

    Checks the version-matched release first, then the latest one. Returns
    ``(bundle_url, checksum_url_or_None)``; None when no bundle exists.
    """
    api_base = f"https://api.github.com/repos/{GITHUB_REPO}/releases"
    urls = [f"{api_base}/tags/{tag}" for tag in release_tag_candidates(version)]
    urls.append(f"{api_base}/latest")
    for url in urls:
        try:
            release = _fetch_json(url)
        except (urllib.error.URLError, OSError, ValueError):
            continue
        asset = find_asset_url(release)
        if asset:
            return asset, find_asset_url(release, f"{SPA_ASSET_NAME}.sha256")
    return None


def _verify_checksum(zip_path: Path, checksum_url: str) -> bool:
    """Compare the bundle's SHA-256 to the release's published ``.sha256``."""
    import hashlib

    with urllib.request.urlopen(  # pragma: no cover - network
        checksum_url, timeout=_HTTP_TIMEOUT_SECONDS, context=_ssl_context()
    ) as response:
        # A real sidecar is <200 bytes; cap the read like the bundle download
        # caps its own, so a misbehaving host can't balloon memory.
        tokens = response.read(4096).decode("utf-8", "replace").split()
    if not tokens:
        # Empty/mangled sidecar (truncated response, proxy interstitial):
        # ValueError keeps this on download_spa's graceful-degrade path
        # instead of crashing the launcher with an IndexError.
        raise ValueError("checksum file was empty or malformed")
    expected = tokens[0].lower()
    digest = hashlib.sha256()
    with open(zip_path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest() == expected


def safe_extract_zip(archive: zipfile.ZipFile, dest: Path) -> None:
    """Extract ``archive`` under ``dest``, refusing unsafe members.

    Rejects path traversal (``../``, absolute paths — the post-join
    ``is_relative_to`` check catches both) and symlink members (a link
    pointing outside ``dest`` would let a later member write through it).
    Our CI-built bundle contains neither; refusing is pure defense-in-depth.
    """
    import stat

    dest = dest.resolve()
    for info in archive.infolist():
        target = (dest / info.filename).resolve()
        if not target.is_relative_to(dest):
            raise ValueError(
                f"Refusing to extract unsafe zip member: {info.filename!r}"
            )
        if stat.S_ISLNK(info.external_attr >> 16):
            raise ValueError(
                f"Refusing to extract symlink zip member: {info.filename!r}"
            )
    archive.extractall(dest)


def _dist_dir_within(spa_root: Path) -> Path | None:
    """Locate the extracted dist dir (with or without a ``dist/`` prefix)."""
    for candidate in (spa_root / "dist", spa_root):
        if (candidate / "index.html").is_file():
            return candidate
    return None


def _version_stamp(spa_root: Path) -> Path:
    return spa_root / ".version"


def _cached_version_matches(spa_root: Path, version: str) -> bool:
    """True when the cached bundle was fetched for this checkout's version.

    A cache without a stamp (pre-stamp download, manual copy) counts as a
    mismatch so it gets refreshed — ``ensure_spa`` still falls back to it when
    the refresh fails (offline), so nothing is lost.
    """
    stamp = _version_stamp(spa_root)
    try:
        return stamp.read_text(encoding="utf-8").strip() == version
    except OSError:
        return False


def download_spa(version: str) -> Path | None:  # pragma: no cover - network
    """Download + extract the release SPA bundle into app-data. None on failure."""
    found = _release_asset_urls(version)
    if not found:
        print(
            "[oc-desktop] No pre-built frontend bundle found on the GitHub "
            "releases for this version\n             (or the GitHub API's "
            "anonymous rate limit was hit — retry in an hour)."
        )
        return None
    asset_url, checksum_url = found

    spa_root = paths.subdir("spa")
    # Download + extract into a STAGING sibling and only swap it in after the
    # whole pipeline (checksum, extraction, index.html present) succeeded — a
    # failed refresh must never destroy a previously working cached copy
    # (which is exactly what ensure_spa falls back to).
    staging = spa_root.with_name(spa_root.name + ".new")
    print(f"[oc-desktop] Downloading the frontend bundle …\n             {asset_url}")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / SPA_ASSET_NAME
            with urllib.request.urlopen(
                asset_url, timeout=_HTTP_TIMEOUT_SECONDS, context=_ssl_context()
            ) as response, open(zip_path, "wb") as out:
                copied = 0
                while chunk := response.read(1 << 20):
                    copied += len(chunk)
                    if copied > MAX_BUNDLE_BYTES:
                        raise ValueError(
                            "frontend bundle exceeds the "
                            f"{MAX_BUNDLE_BYTES // (1024 * 1024)} MB safety cap"
                        )
                    out.write(chunk)
            # Integrity gate: releases publish a .sha256 next to the bundle
            # (see docker-build-release.yml); a mismatch means a corrupted or
            # tampered asset, so refuse it. Older releases without the sibling
            # asset fall back to TLS-only trust.
            if checksum_url and not _verify_checksum(zip_path, checksum_url):
                print(
                    "[oc-desktop] Frontend bundle failed its SHA-256 integrity "
                    "check; refusing to install it."
                )
                return None
            if staging.exists():
                shutil.rmtree(staging)
            # Private like the rest of app-data (staging becomes spa/ below).
            paths.ensure_private_dir(staging)
            with zipfile.ZipFile(zip_path) as archive:
                safe_extract_zip(archive, staging)
            if not _dist_dir_within(staging):
                print("[oc-desktop] Downloaded bundle did not contain an index.html.")
                shutil.rmtree(staging, ignore_errors=True)
                return None
            # Success — swap the verified staging dir into place. The old
            # cache is moved ASIDE (not deleted) until the swap has succeeded
            # and restored on failure, so no failure mode — including a rename
            # blocked by AV/indexer file locks — destroys a working copy.
            backup = spa_root.with_name(spa_root.name + ".old")
            if backup.exists():
                shutil.rmtree(backup, ignore_errors=True)
            if spa_root.exists():
                spa_root.rename(backup)
            try:
                staging.rename(spa_root)
            except OSError:
                if backup.exists():
                    backup.rename(spa_root)
                raise
            shutil.rmtree(backup, ignore_errors=True)
    except (urllib.error.URLError, OSError, ValueError, zipfile.BadZipFile) as exc:
        print(f"[oc-desktop] Frontend bundle download failed: {exc}")
        shutil.rmtree(staging, ignore_errors=True)
        return None

    dist = _dist_dir_within(spa_root)
    if not dist:  # unreachable after the staging check; belt-and-braces
        return None
    # Stamp the cache with the version it was fetched FOR (not necessarily the
    # release it came from — the latest-release fallback still satisfies this
    # checkout), so ensure_spa can detect staleness after an upgrade.
    with contextlib.suppress(OSError):
        _version_stamp(spa_root).write_text(f"{version}\n", encoding="utf-8")
    print(f"[oc-desktop] Frontend ready at {dist}.")
    return dist


def build_spa_with_yarn(repo_root: Path) -> Path | None:  # pragma: no cover
    """Developer fallback: build ``frontend/dist`` with a local yarn toolchain."""
    yarn = shutil.which("yarn")
    if not yarn:
        return None
    frontend = repo_root / "frontend"
    print(
        "[oc-desktop] Node toolchain detected — building the frontend with yarn "
        "(a few minutes) …"
    )
    for step in (["install", "--frozen-lockfile"], ["build"]):
        result = subprocess.run([yarn, *step], cwd=str(frontend))
        if result.returncode != 0:
            print(f"[oc-desktop] `yarn {' '.join(step)}` failed; skipping SPA build.")
            return None
    dist = frontend / "dist"
    return dist if (dist / "index.html").is_file() else None


def ensure_spa(repo_root: Path, version: str) -> Path | None:
    """Return a directory containing the built SPA, acquiring one if needed.

    A cached download is reused only when its version stamp matches this
    checkout's ``version`` — otherwise a fresh download is attempted first so a
    backend upgrade cannot silently keep serving a stale frontend. When the
    refresh fails (offline), the stale cache is still better than no UI, so it
    is returned with a warning.
    """
    repo_dist = repo_root / "frontend" / "dist"
    if (repo_dist / "index.html").is_file():
        return repo_dist

    spa_root = paths.subdir("spa")
    cached = _dist_dir_within(spa_root)
    if cached and _cached_version_matches(spa_root, version):
        print(f"[oc-desktop] Using the downloaded frontend bundle at {cached}.")
        return cached

    fresh = download_spa(version) or build_spa_with_yarn(repo_root)
    if fresh:
        return fresh
    # Re-resolve rather than trusting the pre-download value: a failed swap
    # restores the cache, but only a live re-check proves it's still on disk.
    cached = _dist_dir_within(spa_root)
    if cached:
        print(
            "[oc-desktop] WARNING: could not refresh the frontend bundle for "
            f"version {version}; reusing the previously downloaded copy. It may "
            "be out of date — relaunch with internet access to update it."
        )
        return cached
    return None
