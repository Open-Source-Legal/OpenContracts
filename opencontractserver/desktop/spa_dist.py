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

import json
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
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:  # pragma: no cover - certifi arrives with base deps
        return ssl.create_default_context()


def _fetch_json(url: str) -> dict:
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


def _release_asset_url(version: str) -> str | None:
    """Find the SPA asset on the version-matched release, then the latest one."""
    api_base = f"https://api.github.com/repos/{GITHUB_REPO}/releases"
    urls = [f"{api_base}/tags/{tag}" for tag in release_tag_candidates(version)]
    urls.append(f"{api_base}/latest")
    for url in urls:
        try:
            asset = find_asset_url(_fetch_json(url))
        except (urllib.error.URLError, OSError, ValueError):
            continue
        if asset:
            return asset
    return None


def safe_extract_zip(archive: zipfile.ZipFile, dest: Path) -> None:
    """Extract ``archive`` under ``dest``, refusing path-traversal members."""
    dest = dest.resolve()
    for member in archive.namelist():
        target = (dest / member).resolve()
        if not target.is_relative_to(dest):
            raise ValueError(f"Refusing to extract unsafe zip member: {member!r}")
    archive.extractall(dest)


def _dist_dir_within(spa_root: Path) -> Path | None:
    """Locate the extracted dist dir (with or without a ``dist/`` prefix)."""
    for candidate in (spa_root / "dist", spa_root):
        if (candidate / "index.html").is_file():
            return candidate
    return None


def download_spa(version: str) -> Path | None:
    """Download + extract the release SPA bundle into app-data. None on failure."""
    asset_url = _release_asset_url(version)
    if not asset_url:
        print(
            "[oc-desktop] No pre-built frontend bundle found on the GitHub "
            "releases for this version."
        )
        return None

    spa_root = paths.subdir("spa")
    print(f"[oc-desktop] Downloading the frontend bundle …\n             {asset_url}")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / SPA_ASSET_NAME
            with urllib.request.urlopen(
                asset_url, timeout=_HTTP_TIMEOUT_SECONDS, context=_ssl_context()
            ) as response, open(zip_path, "wb") as out:
                shutil.copyfileobj(response, out)
            # Replace any stale/partial previous extraction wholesale.
            if spa_root.exists():
                shutil.rmtree(spa_root)
            spa_root.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(zip_path) as archive:
                safe_extract_zip(archive, spa_root)
    except (urllib.error.URLError, OSError, ValueError, zipfile.BadZipFile) as exc:
        print(f"[oc-desktop] Frontend bundle download failed: {exc}")
        return None

    dist = _dist_dir_within(spa_root)
    if not dist:
        print("[oc-desktop] Downloaded bundle did not contain an index.html.")
        return None
    print(f"[oc-desktop] Frontend ready at {dist}.")
    return dist


def build_spa_with_yarn(repo_root: Path) -> Path | None:
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
    """Return a directory containing the built SPA, acquiring one if needed."""
    repo_dist = repo_root / "frontend" / "dist"
    if (repo_dist / "index.html").is_file():
        return repo_dist

    cached = _dist_dir_within(paths.subdir("spa"))
    if cached:
        return cached

    return download_spa(version) or build_spa_with_yarn(repo_root)
