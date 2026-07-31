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

import inspect
import logging
import re
from functools import lru_cache
from pathlib import Path

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


def parse_source_hosts_declaration(raw: object) -> tuple[str, ...]:
    """Validate and normalize one manifest ``source_hosts`` declaration."""

    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ValueError("'source_hosts' must be a list of hostnames")
    hosts: list[str] = []
    for value in raw:
        if not isinstance(value, str) or not is_valid_source_host(value):
            raise ValueError(
                f"source_hosts entry {value!r} is not a bare hostname "
                "(e.g. 'tcpbolivia.bo')"
            )
        hosts.append(value.strip().lower().rstrip("."))
    return tuple(dict.fromkeys(hosts))


@lru_cache(maxsize=None)
def source_hosts_for_pack_component(component_class: type) -> tuple[str, ...]:
    """Resolve an in-pack component to its owning manifest's narrow hosts."""

    try:
        component_path = Path(inspect.getfile(component_class)).resolve()
    except (OSError, TypeError):
        return ()
    for raw_pack_dir in authority_pack_dirs():
        pack_dir = raw_pack_dir.resolve()
        if not component_path.is_relative_to(pack_dir):
            continue
        manifest_path = pack_dir / "pack.yaml"
        if not manifest_path.is_file():
            raise ValueError(
                f"in-pack component {component_class.__name__} has no pack.yaml"
            )
        try:
            data = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise ValueError(f"could not parse {manifest_path}: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError(f"{manifest_path}: pack.yaml must contain a mapping")
        hosts = parse_source_hosts_declaration(data.get("source_hosts"))
        if not hosts:
            raise ValueError(
                f"in-pack component {component_class.__name__} has no declared "
                f"source_hosts in {manifest_path}"
            )
        return hosts
    return ()


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
        if not isinstance(data, dict):
            logger.warning("%s: pack.yaml must contain a mapping; ignoring", manifest)
            continue
        raw_declared = data.get("source_hosts")
        declared: tuple[str, ...]
        if raw_declared is None:
            declared = ()
        elif not isinstance(raw_declared, list):
            logger.warning(
                "%s: 'source_hosts' must be a list of hostnames; "
                "ignoring declaration",
                manifest,
            )
            continue
        else:
            valid_hosts: list[str] = []
            for raw_host in raw_declared:
                try:
                    valid_hosts.extend(parse_source_hosts_declaration([raw_host]))
                except ValueError as exc:
                    logger.warning(
                        "%s: %s; ignoring entry",
                        manifest,
                        exc,
                    )
            declared = tuple(dict.fromkeys(valid_hosts))
        for host in declared:
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
    source_hosts_for_pack_component.cache_clear()
