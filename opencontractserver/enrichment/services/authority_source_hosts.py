"""Effective SSRF allowlist = baseline ∪ pack-declared ``source_hosts``.

A self-contained authority pack that scrapes a live source declares the hosts it
fetches from in its ``pack.yaml`` (``source_hosts: [...]``). Those hosts are
read from every *discoverable* pack directory (the same set the pipeline registry
scans for in-pack providers: in-tree ``authority_packs/`` + the
``AUTHORITY_PACK_PATHS`` setting) and unioned with the hardcoded baseline
``PUBLIC_DOMAIN_SOURCE_HOSTS``.

Trust model: a pack's hosts become allowed exactly when the operator *installs*
the pack (commits it in-tree or lists its directory in ``AUTHORITY_PACK_PATHS``)
— installing the pack IS the trust decision. The union is computed identically in
every process (web + Celery workers) from the same pack directories, so a worker
running discovery sees the same allowlist as the loader. Every pack-added host is
logged once so the trust decisions stay visible. The SSRF *mechanism* itself is
unchanged — HTTPS-only, public-IP, per-redirect-hop revalidation and size caps
still apply (see ``opencontractserver/utils/safe_http.py``); a pack can only widen
*which hosts* are reachable, never relax those checks.
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache

import yaml

from opencontractserver.constants.safe_http import PUBLIC_DOMAIN_SOURCE_HOSTS
from opencontractserver.pipeline.registry import authority_pack_dirs

logger = logging.getLogger(__name__)

# A registrable host / domain: dot-separated lowercase labels (letters, digits,
# hyphens). Deliberately strict — a value with a scheme, path, port or whitespace
# is a manifest error, not a host, and must not silently widen the allowlist.
_HOST_RE = re.compile(
    r"^(?=.{1,253}$)[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$"
)


def is_valid_source_host(host: str) -> bool:
    """True iff *host* is a bare, multi-label registrable hostname (no scheme/port).

    Shared by the runtime allowlist union and the pack loader's fail-fast manifest
    validation so a host is judged by exactly one rule.
    """
    return bool(_HOST_RE.match((host or "").strip().lower().rstrip(".")))


@lru_cache(maxsize=1)
def pack_declared_source_hosts() -> frozenset[str]:
    """Union of every installed pack's ``pack.yaml`` ``source_hosts`` (validated).

    Cached for the process; call :func:`reset_source_hosts_cache` after changing
    the pack set (tests do this alongside ``reset_registry``). Malformed entries
    are logged and skipped — never raised — so one bad manifest cannot break every
    authority fetch.
    """
    hosts: set[str] = set()
    for pack_dir in authority_pack_dirs():
        manifest = pack_dir / "pack.yaml"
        if not manifest.is_file():
            continue
        try:
            data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            logger.warning("Could not parse %s for source_hosts: %s", manifest, exc)
            continue
        declared = data.get("source_hosts")
        if declared is None:
            continue
        if not isinstance(declared, list):
            logger.warning(
                "%s: 'source_hosts' must be a list of hostnames; ignoring", manifest
            )
            continue
        for raw in declared:
            host = str(raw).strip().lower().rstrip(".")
            if not is_valid_source_host(host):
                logger.warning(
                    "%s: ignoring malformed source host %r (want a bare hostname "
                    "like 'tcpbolivia.bo')",
                    manifest,
                    raw,
                )
                continue
            if host not in hosts and host not in PUBLIC_DOMAIN_SOURCE_HOSTS:
                logger.info(
                    "Authority pack %r widens the SSRF allowlist with source host: "
                    "%s",
                    pack_dir.name,
                    host,
                )
            hosts.add(host)
    return frozenset(hosts)


def effective_source_allowlist() -> frozenset[str]:
    """The hardcoded baseline unioned with every installed pack's hosts."""
    return PUBLIC_DOMAIN_SOURCE_HOSTS | pack_declared_source_hosts()


def reset_source_hosts_cache() -> None:
    """Clear the pack-host cache (after changing the installed pack set)."""
    pack_declared_source_hosts.cache_clear()
