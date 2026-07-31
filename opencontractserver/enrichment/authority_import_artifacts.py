"""Build OpenContracts corpus-import artifacts from authority source records.

This module is deliberately independent of the web application runtime.  It is
used by ``scripts/authority_import/build_authority_imports.py`` after external
source providers have fetched publisher material.  The output is the existing
OpenContracts V2 corpus-export ZIP format, so an administrator can sideload it
through the normal corpus import GUI.

The collector reuses the authority pack's registered discovery and source
providers.  It does not introduce another provider or crawler abstraction.
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
import zipfile
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urlsplit

import yaml

from opencontractserver.constants.safe_http import PUBLIC_DOMAIN_SOURCE_HOSTS
from opencontractserver.enrichment.authorities import AuthoritySection
from opencontractserver.enrichment.authority_sources import (
    AuthoritySourceRecord,
    AuthorityWeight,
    InstrumentType,
    RelationshipType,
    SourceRelationship,
    normalize_source_status,
    parse_authority_date,
    parse_optional_bool,
)
from opencontractserver.enrichment.constants import ALL_AUTHORITY_TYPES
from opencontractserver.enrichment.services.authority_source_hosts import (
    parse_source_hosts_declaration,
)
from opencontractserver.pipeline.base.base_authority_discovery_provider import (
    DiscoveryCandidate,
)
from opencontractserver.shared.utils import sanitize_corpus_filename
from opencontractserver.utils.safe_http import scoped_default_allowlist

SOURCE_PLAN_FILENAME = "sources.yaml"
IMPORTS_DIRNAME = "imports"
IMPORT_INDEX_FILENAME = "index.json"
SCRAPE_REPORT_FILENAME = "scrape-report.json"
SOURCE_PLAN_SCHEMA_VERSION = 1
ARTIFACT_FORMAT_VERSION = "2.0"

_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
_CORPUS_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,126}[a-z0-9])?$")
_CANONICAL_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9-]*:.+$")
_ALLOWED_SOURCE_KEYS = {
    "id",
    "ingestion_mode",
    "corpus_slug",
    "discovery_provider",
    "index_urls",
    "discovery_kwargs",
    "candidates",
    "canonical_keys",
    "source_provider",
    "fetch_kwargs",
    "candidate_filters",
    "metadata",
    "parent_relationship_type",
}
_INGESTION_MODES = {"full_content", "link_only"}
_FILTER_KEYS = {
    "include_title",
    "exclude_title",
    "include_url",
    "exclude_url",
}
_REQUIRED_LINK_ONLY_AUTHORITY_METADATA = (
    "authority_family",
    "instrument_type",
    "publisher",
    "jurisdiction",
    "status",
    "authority_weight",
)
_AUTHORITY_METADATA_STRING_FIELDS = {
    "authority_family",
    "publisher",
    "jurisdiction",
    "authority_type",
    "review_status",
    "version_label",
}
_AUTHORITY_METADATA_DATE_FIELDS = {
    "filed_date",
    "issued_date",
    "published_date",
    "effective_from",
    "effective_until",
}
_PROMOTED_CANDIDATE_EXTRA_METADATA_FIELDS = (
    "version_label",
    "current_version",
    "filed_date",
    "issued_date",
    "published_date",
    "effective_from",
    "effective_until",
)
_BUILDER_OWNED_METADATA_FIELDS = {
    "artifact_content_hash",
    "artifact_mime_type",
    "authority",
    "authority_aliases",
    "authority_provider_fields",
    "canonical_key",
    "content_hash",
    "discovery_metadata",
    "ingestion_mode",
    "pack_fingerprint",
    "pack_origin",
    "parent_proceeding",
    "publisher_evidence",
    "publisher_source_content_hash",
    "publisher_source_member",
    "publisher_source_mime_type",
    "publisher_source_packaging",
    "publisher_title",
    "relationships",
    "retrieved_at",
    "rights_status",
    "rights_approved",
    "source_identifier",
    "source_mime_type",
    "source_plan_fingerprint",
    "source_plan_id",
    "source_url",
}
_PUBLISHER_SOURCE_PACKAGING_DOCUMENT = "document"
_PUBLISHER_SOURCE_PACKAGING_SIDECAR = "sidecar"
_LINK_MANIFEST_PREFIXES = (
    "link-only authority source",
    "link only authority source",
)


class SourcePlanError(ValueError):
    """Raised when an external source plan is malformed."""


@dataclass(frozen=True)
class CollectedAuthorityRecord:
    """One provider result plus the source-plan entry that produced it."""

    record: AuthoritySourceRecord | AuthoritySection
    source_id: str
    corpus_slug: str | None = None
    display_title: str | None = None
    ingestion_mode: str = "full_content"
    rights_approved: bool = False


@dataclass(frozen=True)
class ArtifactCase:
    """One generated ZIP and a deterministic document sentinel for GUI tests."""

    pack_name: str
    corpus_slug: str
    corpus_title: str
    export_zip_path: str
    expected_document_title: str
    expected_content_text: str
    expected_canonical_keys: tuple[str, ...]
    expected_document_count: int
    expected_provider_relationships: tuple[tuple[str, str, str], ...]
    source_plan_fingerprint: str
    pack_fingerprint: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "packName": self.pack_name,
            "corpusSlug": self.corpus_slug,
            "corpusTitle": self.corpus_title,
            "exportZipPath": self.export_zip_path,
            "expectedDocumentTitle": self.expected_document_title,
            "expectedContentText": self.expected_content_text,
            "expectedCanonicalKeys": list(self.expected_canonical_keys),
            "expectedDocumentCount": self.expected_document_count,
            "expectedProviderRelationships": [
                {
                    "sourceKey": source_key,
                    "relationshipType": relationship_type,
                    "targetKey": target_key,
                }
                for source_key, relationship_type, target_key in (
                    self.expected_provider_relationships
                )
            ],
            "sourcePlanFingerprint": self.source_plan_fingerprint,
            "packFingerprint": self.pack_fingerprint,
        }


@dataclass(frozen=True)
class ArtifactBuildResult:
    """Generated artifacts for one authority pack."""

    pack_name: str
    output_dir: Path
    zip_paths: tuple[Path, ...]
    cases: tuple[ArtifactCase, ...]
    validation_warnings: Mapping[str, tuple[str, ...]]


@dataclass
class CollectionReport:
    """Auditable result of running one pack's external source plan."""

    pack_name: str
    plan_path: str
    discovered: int = 0
    fetched: int = 0
    linked: int = 0
    rights_approved: bool = False
    source_plan_fingerprint: str = ""
    pack_fingerprint: str = ""
    decisions: list[dict[str, str]] = field(default_factory=list)
    artifact_warnings: list[dict[str, Any]] = field(default_factory=list)
    skipped: list[dict[str, str]] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "pack_name": self.pack_name,
            "plan_path": self.plan_path,
            "discovered": self.discovered,
            "fetched": self.fetched,
            "linked": self.linked,
            "rights_approved": self.rights_approved,
            "source_plan_fingerprint": self.source_plan_fingerprint,
            "pack_fingerprint": self.pack_fingerprint,
            "decisions": self.decisions,
            "artifact_warnings": self.artifact_warnings,
            "skipped": self.skipped,
            "errors": self.errors,
        }


def read_source_plan(path: Path) -> dict[str, Any]:
    """Read and strictly validate a pack-local ``sources.yaml``."""

    path = Path(path)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise SourcePlanError(f"Could not read source plan {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise SourcePlanError(f"{path}: source plan must be a YAML mapping")
    if raw.get("schema_version") != SOURCE_PLAN_SCHEMA_VERSION:
        raise SourcePlanError(
            f"{path}: schema_version must be {SOURCE_PLAN_SCHEMA_VERSION}"
        )
    sources = raw.get("sources")
    if not isinstance(sources, list) or not sources:
        raise SourcePlanError(f"{path}: sources must be a non-empty list")

    seen_ids: set[str] = set()
    for index, source in enumerate(sources):
        label = f"{path}: sources[{index}]"
        if not isinstance(source, dict):
            raise SourcePlanError(f"{label} must be a mapping")
        unknown = set(source) - _ALLOWED_SOURCE_KEYS
        if unknown:
            raise SourcePlanError(f"{label} has unknown keys: {sorted(unknown)}")
        source_id = source.get("id")
        if not isinstance(source_id, str) or not source_id.strip():
            raise SourcePlanError(f"{label}.id must be a non-empty string")
        if source_id in seen_ids:
            raise SourcePlanError(f"{label}.id duplicates {source_id!r}")
        seen_ids.add(source_id)
        ingestion_mode = source.get("ingestion_mode")
        if ingestion_mode not in _INGESTION_MODES:
            raise SourcePlanError(
                f"{label}.ingestion_mode must be one of {sorted(_INGESTION_MODES)}"
            )

        modes = (
            "discovery_provider" in source,
            "candidates" in source,
            "canonical_keys" in source,
        )
        if sum(modes) != 1:
            raise SourcePlanError(
                f"{label} must declare exactly one of discovery_provider, "
                "candidates, or canonical_keys"
            )
        if "discovery_provider" in source:
            _require_string(source["discovery_provider"], f"{label}.discovery_provider")
            urls = source.get("index_urls")
            if not isinstance(urls, list) or not urls:
                raise SourcePlanError(
                    f"{label}.index_urls must be a non-empty list for discovery"
                )
            for url_index, url in enumerate(urls):
                _require_http_url(url, f"{label}.index_urls[{url_index}]")
        elif "index_urls" in source:
            raise SourcePlanError(
                f"{label}.index_urls is only valid with discovery_provider"
            )

        if "canonical_keys" in source:
            keys = source["canonical_keys"]
            if not isinstance(keys, list) or not keys:
                raise SourcePlanError(
                    f"{label}.canonical_keys must be a non-empty list"
                )
            for key_index, key in enumerate(keys):
                _require_canonical_key(key, f"{label}.canonical_keys[{key_index}]")

        if "candidates" in source:
            candidates = source["candidates"]
            if not isinstance(candidates, list) or not candidates:
                raise SourcePlanError(f"{label}.candidates must be a non-empty list")
            for candidate_index, candidate in enumerate(candidates):
                _validate_candidate(candidate, f"{label}.candidates[{candidate_index}]")

        for kwargs_key in ("discovery_kwargs", "fetch_kwargs"):
            value = source.get(kwargs_key, {})
            if not isinstance(value, dict):
                raise SourcePlanError(f"{label}.{kwargs_key} must be a mapping")
        provider_name = source.get("source_provider")
        if provider_name is not None:
            _require_string(provider_name, f"{label}.source_provider")
        corpus_slug = source.get("corpus_slug")
        if corpus_slug is not None and (
            not isinstance(corpus_slug, str)
            or not _CORPUS_SLUG_RE.fullmatch(corpus_slug)
        ):
            raise SourcePlanError(f"{label}.corpus_slug is invalid")
        if ingestion_mode == "link_only" and not corpus_slug:
            raise SourcePlanError(
                f"{label}.corpus_slug is required for link_only ingestion"
            )
        _validate_authority_metadata(source.get("metadata", {}), f"{label}.metadata")
        parent_relationship_type = source.get("parent_relationship_type")
        if parent_relationship_type is not None:
            if ingestion_mode != "link_only":
                raise SourcePlanError(
                    f"{label}.parent_relationship_type is only valid for "
                    "link_only ingestion"
                )
            _normalize_relationship_type(
                parent_relationship_type,
                f"{label}.parent_relationship_type",
            )
        _validate_candidate_filters(source.get("candidate_filters"), label)
    return raw


def collect_from_source_plan(
    pack_dir: Path,
    *,
    plan_path: Path | None = None,
    rights_approved: bool = False,
) -> tuple[list[CollectedAuthorityRecord], CollectionReport]:
    """Collect with a pack-scoped expansion of the existing SSRF allowlist."""

    pack_dir = Path(pack_dir).resolve()
    manifest = _read_pack_manifest(pack_dir)
    declared_hosts = parse_source_hosts_declaration(manifest.get("source_hosts"))
    allowlist = frozenset((*PUBLIC_DOMAIN_SOURCE_HOSTS, *declared_hosts))
    with scoped_default_allowlist(allowlist):
        return _collect_from_source_plan_impl(
            pack_dir,
            plan_path=plan_path,
            rights_approved=rights_approved,
        )


def _resolved_provider_kwargs(
    pack_dir: Path,
    raw_kwargs: Mapping[str, Any],
    *,
    label: str,
) -> dict[str, Any]:
    """Resolve pack-relative additive CA files without allowing path escape."""

    resolved = dict(raw_kwargs)
    raw_certificates = resolved.get("extra_ca_certificates")
    if raw_certificates is None:
        return resolved
    if not isinstance(raw_certificates, list) or not raw_certificates:
        raise SourcePlanError(
            f"{label}.extra_ca_certificates must be a non-empty list of "
            "pack-relative PEM paths"
        )

    pack_root = pack_dir.resolve()
    certificate_pems: list[str] = []
    for index, raw_path in enumerate(raw_certificates):
        item_label = f"{label}.extra_ca_certificates[{index}]"
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise SourcePlanError(f"{item_label} must be a pack-relative PEM path")
        relative = Path(raw_path)
        if relative.is_absolute():
            raise SourcePlanError(f"{item_label} must be pack-relative")
        candidate = (pack_root / relative).resolve()
        try:
            candidate.relative_to(pack_root)
        except ValueError as exc:
            raise SourcePlanError(f"{item_label} escapes the authority pack") from exc
        try:
            if not candidate.is_file():
                raise SourcePlanError(f"{item_label} does not name a readable file")
            if candidate.stat().st_size > 1024 * 1024:
                raise SourcePlanError(
                    f"{item_label} exceeds the 1 MiB certificate limit"
                )
            pem = candidate.read_text(encoding="ascii")
        except SourcePlanError:
            raise
        except (OSError, UnicodeError) as exc:
            raise SourcePlanError(f"{item_label} could not be read as PEM") from exc
        if (
            "-----BEGIN CERTIFICATE-----" not in pem
            or "-----END CERTIFICATE-----" not in pem
            or "PRIVATE KEY" in pem
        ):
            raise SourcePlanError(
                f"{item_label} must contain CA certificate PEM and no private key"
            )
        certificate_pems.append(pem)
    resolved["extra_ca_certificates"] = tuple(certificate_pems)
    return resolved


def _collect_from_source_plan_impl(
    pack_dir: Path,
    *,
    plan_path: Path | None = None,
    rights_approved: bool = False,
) -> tuple[list[CollectedAuthorityRecord], CollectionReport]:
    """Run registered pack providers described by a source plan.

    Provider failures are isolated per candidate and recorded.  Callers decide
    whether a non-empty ``report.errors`` is fatal (the CLI is strict unless
    ``--allow-partial`` is supplied).
    """

    pack_dir = Path(pack_dir).resolve()
    manifest = _read_pack_manifest(pack_dir)
    pack_name = _pack_name(manifest, pack_dir)
    plan_path = _source_plan_path(pack_dir, manifest, plan_path)
    plan = read_source_plan(plan_path)
    source_plan_fingerprint = _file_fingerprint(plan_path)
    pack_fingerprint = _pack_fingerprint(pack_dir)
    report = CollectionReport(
        pack_name=pack_name,
        plan_path=str(plan_path),
        rights_approved=rights_approved,
        source_plan_fingerprint=source_plan_fingerprint,
        pack_fingerprint=pack_fingerprint,
    )
    collected: list[CollectedAuthorityRecord] = []
    collected_keys: set[str] = set()

    source_definitions, discovery_definitions = _provider_definitions()
    for source in plan["sources"]:
        source_id = source["id"]
        try:
            discovery_kwargs = _resolved_provider_kwargs(
                pack_dir,
                source.get("discovery_kwargs") or {},
                label=f"{source_id}.discovery_kwargs",
            )
            fetch_kwargs = _resolved_provider_kwargs(
                pack_dir,
                source.get("fetch_kwargs") or {},
                label=f"{source_id}.fetch_kwargs",
            )
        except SourcePlanError as exc:
            report.errors.append(
                {
                    "source_id": source_id,
                    "candidate": "<provider-kwargs>",
                    "error": str(exc),
                }
            )
            continue
        candidates: list[tuple[str, DiscoveryCandidate | None]] = []
        if "discovery_provider" in source:
            try:
                provider_cls = _resolve_provider(
                    source["discovery_provider"],
                    discovery_definitions,
                    kind="discovery",
                )
                result = provider_cls().discover_candidates(
                    source["index_urls"],
                    **discovery_kwargs,
                )
                report.discovered += len(result.candidates)
                if result.capped:
                    report.errors.append(
                        {
                            "source_id": source_id,
                            "candidate": "<discovery>",
                            "error": (
                                "discovery result was capped; refusing a partial "
                                "full-corpus source set"
                            ),
                        }
                    )
                    continue
                for index_url, reason in sorted(result.skipped_index_urls.items()):
                    report.errors.append(
                        {
                            "source_id": source_id,
                            "candidate": index_url,
                            "error": reason,
                        }
                    )
                candidates.extend(
                    (candidate.canonical_key, candidate)
                    for candidate in result.candidates
                )
            except Exception as exc:  # noqa: BLE001 - report one source, continue
                report.errors.append(
                    {
                        "source_id": source_id,
                        "candidate": "<discovery>",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
                continue
        elif "candidates" in source:
            candidates.extend(
                (
                    item["canonical_key"],
                    DiscoveryCandidate(
                        canonical_key=item["canonical_key"],
                        url=item.get("url") or "",
                        title=item.get("publisher_title") or item.get("title"),
                        extra={
                            **_static_candidate_extra(item),
                            **(
                                {"display_title": item["display_title"]}
                                if item.get("display_title")
                                else {}
                            ),
                        },
                    ),
                )
                for item in source["candidates"]
            )
            report.discovered += len(candidates)
        else:
            candidates.extend((key, None) for key in source["canonical_keys"])
            report.discovered += len(candidates)

        filtered_candidates = _filter_candidates(
            candidates,
            source.get("candidate_filters"),
            source_id=source_id,
            report=report,
        )
        explicit_source_cls = None
        if source.get("source_provider"):
            try:
                explicit_source_cls = _resolve_provider(
                    source["source_provider"],
                    source_definitions,
                    kind="source",
                )
            except SourcePlanError as exc:
                report.errors.append(
                    {
                        "source_id": source_id,
                        "candidate": "<provider>",
                        "error": str(exc),
                    }
                )
                continue

        for canonical_key, candidate in filtered_candidates:
            if canonical_key in collected_keys:
                report.skipped.append(
                    {
                        "source_id": source_id,
                        "candidate": canonical_key,
                        "reason": "duplicate canonical_key already collected",
                    }
                )
                continue
            try:
                link_metadata: dict[str, Any] | None = None
                link_relationships: tuple[SourceRelationship, ...] = ()
                if source["ingestion_mode"] == "link_only":
                    link_metadata, link_relationships = _link_only_metadata(
                        source=source,
                        candidate=candidate,
                        canonical_key=canonical_key,
                    )
                provider_cls = explicit_source_cls or _route_source_provider(
                    canonical_key, source_definitions
                )
                provider = provider_cls()
                request = provider.locate(
                    canonical_key,
                    discovery_candidate=candidate,
                    **fetch_kwargs,
                )
                if source["ingestion_mode"] == "link_only":
                    if link_metadata is None:
                        raise RuntimeError(
                            "link-only metadata was not prepared — this is a bug"
                        )
                    publisher_title = (
                        (candidate.title if candidate is not None else None)
                        or request.citation
                        or canonical_key
                    )
                    title = (
                        candidate.extra.get("display_title")
                        if candidate is not None
                        else None
                    ) or publisher_title
                    source_identifier = (
                        candidate.extra.get("source_identifier")
                        if candidate is not None
                        else None
                    ) or canonical_key
                    stub = AuthoritySection(
                        key=canonical_key,
                        heading=str(title),
                        text=(
                            "Link-only authority source. Full publisher content "
                            "was not fetched because rights approval is required.\n\n"
                            f"Official source: {request.url}"
                        ),
                        source_url=request.url,
                        metadata={
                            **link_metadata,
                            "rights_status": "LINK_ONLY",
                            "ingestion_mode": "link_only",
                            "source_url": request.url,
                            "source_identifier": str(source_identifier),
                            "retrieved_at": datetime.now(tz=timezone.utc).isoformat(),
                            "publisher_evidence": [
                                {
                                    "source": "URL",
                                    "value": request.url,
                                    "locator": request.url,
                                }
                            ],
                            "publisher_title": str(publisher_title),
                            "discovery_metadata": _json_safe(
                                _candidate_discovery_metadata(candidate)
                            ),
                        },
                        relationships=link_relationships,
                    )
                    collected.append(
                        CollectedAuthorityRecord(
                            record=stub,
                            source_id=source_id,
                            corpus_slug=source["corpus_slug"],
                            display_title=str(title),
                            ingestion_mode="link_only",
                            rights_approved=False,
                        )
                    )
                    report.linked += 1
                    report.decisions.append(
                        {
                            "source_id": source_id,
                            "candidate": canonical_key,
                            "ingestion_mode": "link_only",
                            "verdict": "link_only",
                            "reason": "source provider fetch intentionally skipped",
                        }
                    )
                    collected_keys.add(canonical_key)
                    continue
                records = list(provider.fetch(request, **fetch_kwargs))
                if not records:
                    raise ValueError("source provider returned no records")
                returned_keys: set[str] = set()
                for record in records:
                    _require_publisher_content_record(
                        record,
                        source_id=source_id,
                        canonical_key=canonical_key,
                    )
                    if record.key in returned_keys:
                        raise ValueError(
                            "source provider returned duplicate canonical_key "
                            f"{record.key!r} for {canonical_key!r}"
                        )
                    if record.key in collected_keys:
                        raise ValueError(
                            "source provider expanded "
                            f"{canonical_key!r} to already-collected canonical_key "
                            f"{record.key!r}"
                        )
                    returned_keys.add(record.key)
                from opencontractserver.enrichment.services.authority_gate_service import (
                    GATE_OK,
                    AuthorityGateService,
                )

                rights_values = {
                    str(record.rights_status)
                    for record in records
                    if isinstance(record, AuthoritySourceRecord)
                }
                if len(rights_values) > 1:
                    raise ValueError(
                        "source provider returned mixed rights_status values"
                    )
                rights_status = next(iter(rights_values), None)
                decision = AuthorityGateService.evaluate(
                    canonical_key=canonical_key,
                    sections=records,
                    provider_license=str(getattr(provider, "license", "")),
                    require_approval_for_agentic=bool(
                        getattr(provider, "requires_approval", False)
                    ),
                    rights_status=rights_status,
                    rights_approved=rights_approved,
                    publisher_evidence_verifier=provider.verify_publisher_evidence,
                )
                report.decisions.append(
                    {
                        "source_id": source_id,
                        "candidate": canonical_key,
                        "ingestion_mode": "full_content",
                        "verdict": decision.verdict,
                        "reason": decision.reason,
                    }
                )
                if decision.verdict != GATE_OK:
                    raise PermissionError(
                        f"authority gate refused full content: {decision.reason}"
                    )
                for record in records:
                    if isinstance(record, AuthoritySourceRecord):
                        if not provider.can_handle(record.canonical_key):
                            raise ValueError(
                                f"source provider expanded {canonical_key!r} to "
                                f"unsupported canonical_key "
                                f"{record.canonical_key!r}"
                            )
                        if not provider.verify_publisher_evidence(
                            record.canonical_key, record
                        ):
                            raise ValueError(
                                "publisher evidence did not verify canonical_key"
                            )
                    elif not isinstance(record, AuthoritySection):
                        raise TypeError(
                            "source provider must return AuthoritySourceRecord "
                            "or AuthoritySection"
                        )
                    collected.append(
                        CollectedAuthorityRecord(
                            record=record,
                            source_id=source_id,
                            corpus_slug=source.get("corpus_slug"),
                            display_title=(
                                str(candidate.extra["display_title"])
                                if candidate is not None
                                and record.key == canonical_key
                                and candidate.extra.get("display_title")
                                else None
                            ),
                            ingestion_mode="full_content",
                            rights_approved=rights_approved,
                        )
                    )
                    report.fetched += 1
                collected_keys.update(record.key for record in records)
            except Exception as exc:  # noqa: BLE001 - one candidate must not abort run
                report.errors.append(
                    {
                        "source_id": source_id,
                        "candidate": canonical_key,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
    return collected, report


def _require_publisher_content_record(
    record: AuthoritySourceRecord | AuthoritySection,
    *,
    source_id: str,
    canonical_key: str,
) -> None:
    """Fail closed when a ``full_content`` provider did not return source bytes.

    ``AuthoritySection`` is a useful compatibility type for the in-app
    authority bootstrap, but it contains only normalized text.  A standalone
    full-content collector needs the richer record so the V2 artifact can
    prove and preserve the exact publisher response separately from any
    portable text representation.
    """

    if not isinstance(record, AuthoritySourceRecord):
        raise TypeError(
            f"{source_id}: full_content provider for {canonical_key!r} must "
            "return AuthoritySourceRecord with publisher bytes"
        )
    if not record.content:
        # AuthoritySourceRecord validates this at construction time; keep the
        # boundary check explicit so custom/test providers cannot bypass the
        # full-content contract with a malformed instance.
        raise ValueError(
            f"{source_id}: full_content provider for {canonical_key!r} "
            "returned zero publisher bytes"
        )
    if str(record.rights_status) == "LINK_ONLY":
        raise PermissionError(
            f"{source_id}: full_content provider for {canonical_key!r} "
            "returned rights_status LINK_ONLY"
        )
    if record.metadata.get("link_only") is True:
        raise ValueError(
            f"{source_id}: full_content provider for {canonical_key!r} "
            "returned a link-only manifest"
        )
    if (
        record.extracted_text is None
        and record.metadata.get("text_extraction_deferred_to_pipeline") is True
    ):
        sample = (
            record.content[:512].decode("utf-8", errors="ignore").lstrip().casefold()
        )
    else:
        sample = (record.extracted_text or record.text)[:512].lstrip().casefold()
    if any(sample.startswith(prefix) for prefix in _LINK_MANIFEST_PREFIXES):
        raise ValueError(
            f"{source_id}: full_content provider for {canonical_key!r} "
            "returned link-manifest text instead of publisher content"
        )


def build_authority_import_artifacts(
    pack_dir: Path,
    records: Iterable[
        CollectedAuthorityRecord | AuthoritySourceRecord | AuthoritySection
    ],
    *,
    output_dir: Path | None = None,
    supported_mime_types: Iterable[str] | None = None,
    converter_extensions: Iterable[str] | None = None,
) -> ArtifactBuildResult:
    """Build one deterministic V2 corpus-import ZIP per populated pack corpus."""

    pack_dir = Path(pack_dir).resolve()
    manifest = _read_pack_manifest(pack_dir)
    pack_name = _pack_name(manifest, pack_dir)
    source_plan_path = _source_plan_path(pack_dir, manifest, None)
    source_plan_fingerprint = _file_fingerprint(source_plan_path)
    pack_fingerprint = _pack_fingerprint(pack_dir)
    corpora = _manifest_corpora(manifest)
    by_slug: dict[str, list[CollectedAuthorityRecord]] = defaultdict(list)

    for item in records:
        wrapped = (
            item
            if isinstance(item, CollectedAuthorityRecord)
            else CollectedAuthorityRecord(item, source_id="direct")
        )
        slug = (
            wrapped.record.corpus_slug
            if isinstance(wrapped.record, AuthoritySourceRecord)
            else wrapped.corpus_slug
        )
        if not slug:
            raise SourcePlanError(
                f"{wrapped.source_id}: AuthoritySection {wrapped.record.key!r} "
                "requires source corpus_slug"
            )
        if slug not in corpora:
            raise SourcePlanError(
                f"{wrapped.source_id}: record targets undeclared corpus {slug!r}"
            )
        by_slug[slug].append(wrapped)

    destination = Path(output_dir or (pack_dir / IMPORTS_DIRNAME)).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    supported_mimes = frozenset(
        supported_mime_types
        if supported_mime_types is not None
        else _configured_supported_mime_types()
    )
    convertible_extensions = frozenset(
        str(extension).strip().lstrip(".").casefold()
        for extension in (
            converter_extensions
            if converter_extensions is not None
            else _registered_converter_extensions()
        )
        if str(extension).strip().lstrip(".")
    )
    zip_paths: list[Path] = []
    cases: list[ArtifactCase] = []
    validation_warnings: dict[str, tuple[str, ...]] = {}
    for corpus_slug in sorted(by_slug):
        corpus_entry = corpora[corpus_slug]
        normalized_records = _normalize_records(
            by_slug[corpus_slug],
            pack_dir=pack_dir,
            corpus_entry=corpus_entry,
            pack_name=pack_name,
            supported_mime_types=supported_mimes,
            converter_extensions=convertible_extensions,
            source_plan_fingerprint=source_plan_fingerprint,
            pack_fingerprint=pack_fingerprint,
        )
        archive_path = destination / f"{corpus_slug}.zip"
        data_json, members = _build_export_payload(
            pack_name=pack_name,
            corpus_entry=corpus_entry,
            records=normalized_records,
            corpus_config=_corpus_export_config(
                pack_dir=pack_dir,
                manifest=manifest,
                corpus_entry=corpus_entry,
            ),
        )
        _write_deterministic_zip(archive_path, data_json, members)
        from opencontractserver.utils.validate_export import validate_export

        validation = validate_export(archive_path)
        if not validation.ok:
            raise SourcePlanError(
                f"Generated OpenContracts export {archive_path} is invalid: "
                + "; ".join(validation.errors)
            )
        validation_warnings[archive_path.name] = tuple(validation.warnings)
        zip_paths.append(archive_path)

        sentinel_record = normalized_records[0]
        cases.append(
            ArtifactCase(
                pack_name=pack_name,
                corpus_slug=corpus_slug,
                corpus_title=str(corpus_entry["title"]),
                export_zip_path=str(archive_path),
                expected_document_title=sentinel_record["title"],
                expected_content_text=_content_sentinel(sentinel_record["content"]),
                expected_canonical_keys=tuple(
                    sorted(record["canonical_key"] for record in normalized_records)
                ),
                expected_document_count=len(normalized_records),
                expected_provider_relationships=tuple(
                    sorted(
                        {
                            (
                                str(record["canonical_key"]),
                                str(relationship["relationship_type"]),
                                str(relationship["target_key"]),
                            )
                            for record in normalized_records
                            for relationship in record["custom_meta"].get(
                                "relationships", []
                            )
                        }
                    )
                ),
                source_plan_fingerprint=source_plan_fingerprint,
                pack_fingerprint=pack_fingerprint,
            )
        )

    index_path = destination / IMPORT_INDEX_FILENAME
    local_rows = []
    for case in cases:
        row = case.as_dict()
        row["exportZipPath"] = Path(case.export_zip_path).name
        local_rows.append(row)
    index_path.write_text(
        json.dumps({"cases": local_rows}, indent=2) + "\n", encoding="utf-8"
    )
    return ArtifactBuildResult(
        pack_name=pack_name,
        output_dir=destination,
        zip_paths=tuple(zip_paths),
        cases=tuple(cases),
        validation_warnings=validation_warnings,
    )


def write_collection_report(output_dir: Path, report: CollectionReport) -> Path:
    """Write an auditable, deterministic collection report."""

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / SCRAPE_REPORT_FILENAME
    path.write_text(
        json.dumps(report.as_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def write_aggregate_manifest(path: Path, cases: Iterable[ArtifactCase]) -> Path:
    """Write the cross-pack manifest consumed by the browser E2E."""

    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for case in cases:
        row = case.as_dict()
        absolute_zip = Path(case.export_zip_path)
        if absolute_zip.is_absolute():
            row["exportZipPath"] = os.path.relpath(absolute_zip, path.parent)
        rows.append(row)
    path.write_text(json.dumps({"cases": rows}, indent=2) + "\n", encoding="utf-8")
    return path


def _normalize_records(
    records: Sequence[CollectedAuthorityRecord],
    *,
    pack_dir: Path,
    corpus_entry: Mapping[str, Any],
    pack_name: str,
    supported_mime_types: frozenset[str],
    converter_extensions: frozenset[str],
    source_plan_fingerprint: str,
    pack_fingerprint: str,
) -> list[dict[str, Any]]:
    aliases = _corpus_aliases(pack_dir, corpus_entry)
    normalized: list[dict[str, Any]] = []
    seen_keys: dict[str, str] = {}
    seen_names: set[str] = set()
    for wrapped in sorted(records, key=lambda item: item.record.key):
        record = wrapped.record
        if wrapped.ingestion_mode not in _INGESTION_MODES:
            raise SourcePlanError(
                f"{wrapped.source_id}: unsupported ingestion_mode "
                f"{wrapped.ingestion_mode!r}"
            )
        if wrapped.ingestion_mode == "full_content":
            _require_publisher_content_record(
                record,
                source_id=wrapped.source_id,
                canonical_key=record.key,
            )
        canonical_key = record.key.strip()
        if not _CANONICAL_KEY_RE.fullmatch(canonical_key):
            raise SourcePlanError(
                f"{wrapped.source_id}: invalid canonical_key {canonical_key!r}"
            )
        if isinstance(record, AuthoritySourceRecord):
            source_content_bytes = record.content
            rendition_content_bytes = record.portable_rendition_content
            rendition_mime_type = record.portable_rendition_mime_type
            rendition_filename = record.portable_rendition_filename
            extraction_deferred = (
                record.extracted_text is None
                and record.metadata.get("text_extraction_deferred_to_pipeline") is True
            )
            content_text = (
                record.extracted_text
                if record.extracted_text is not None
                else (
                    "Text extraction is deferred to the configured OpenContracts "
                    f"ingestion pipeline for publisher source {record.canonical_key}."
                    if extraction_deferred
                    else record.text
                )
            )
            source_mime_type = record.mime_type
            metadata = record.as_document_metadata()
            metadata["relationships"] = _artifact_provider_relationships(
                record,
                source_id=wrapped.source_id,
            )
            source_url = record.source_url
            source_identifier = record.source_identifier
            retrieved_at = record.retrieved_at.isoformat()
        else:
            rendition_content_bytes = None
            rendition_mime_type = None
            rendition_filename = None
            extraction_deferred = False
            content_text = record.text
            source_content_bytes = content_text.encode("utf-8")
            source_mime_type = "text/plain"
            metadata = dict(record.metadata)
            metadata.update(
                {
                    "canonical_key": canonical_key,
                    "content_hash": hashlib.sha256(source_content_bytes).hexdigest(),
                    "source_mime_type": source_mime_type,
                    "relationships": [
                        relationship.as_dict() for relationship in record.relationships
                    ],
                }
            )
            source_url = record.source_url
            raw_identifier = metadata.get("source_identifier")
            source_identifier = (
                str(raw_identifier)
                if isinstance(raw_identifier, (str, int)) and str(raw_identifier)
                else canonical_key
            )
            raw_retrieved_at = metadata.get("retrieved_at")
            retrieved_at = (
                str(raw_retrieved_at)
                if isinstance(raw_retrieved_at, str) and raw_retrieved_at
                else datetime.now(tz=timezone.utc).isoformat()
            )

        source_filename = _publisher_source_filename(
            record,
            source_url=source_url,
            canonical_key=canonical_key,
            converter_extensions=converter_extensions,
        )
        source_extension = PurePosixPath(source_filename).suffix.lstrip(".").casefold()
        source_digest = hashlib.sha256(source_content_bytes).hexdigest()
        source_is_convertible = (
            bool(source_extension) and source_extension in converter_extensions
        )
        # Conversion routing is extension-based. A converter-supported
        # extension wins even when signature sniffing also calls the bytes
        # text/plain (HTML/RTF are common examples); storing those as text
        # would bypass the configured converter.
        source_is_native = (
            source_mime_type in supported_mime_types and not source_is_convertible
        )
        source_is_document = source_is_native or source_is_convertible
        rendition_extension = (
            PurePosixPath(rendition_filename).suffix.lstrip(".").casefold()
            if rendition_filename is not None
            else ""
        )
        rendition_is_convertible = (
            bool(rendition_extension) and rendition_extension in converter_extensions
        )
        rendition_is_native = (
            rendition_mime_type in supported_mime_types and not rendition_is_convertible
            if rendition_mime_type is not None
            else False
        )
        rendition_is_document = rendition_is_native or rendition_is_convertible
        if rendition_content_bytes is not None and not rendition_is_document:
            raise SourcePlanError(
                f"{wrapped.source_id}: {canonical_key!r} portable rendition "
                f"{rendition_filename!r} is neither native nor supported by a "
                "registered file converter"
            )
        artifact_uses_rendition = (
            not source_is_document and rendition_content_bytes is not None
        )
        if extraction_deferred and not (source_is_document or artifact_uses_rendition):
            raise SourcePlanError(
                f"{wrapped.source_id}: {canonical_key!r} deferred text extraction "
                f"but source extension {source_extension!r} is neither native nor "
                "supported by a registered file converter and has no portable "
                "rendition"
            )
        if source_is_document:
            artifact_content_bytes = source_content_bytes
            artifact_mime_type = (
                source_mime_type if source_is_native else "application/octet-stream"
            )
            artifact_extension = source_extension
            artifact_is_convertible = source_is_convertible
        elif artifact_uses_rendition:
            artifact_content_bytes = rendition_content_bytes
            artifact_mime_type = (
                rendition_mime_type
                if rendition_is_native
                else "application/octet-stream"
            )
            artifact_extension = rendition_extension
            artifact_is_convertible = rendition_is_convertible
        else:
            # The verified extracted text is the portable, ingestible document
            # for HTML/XML or a binary type unsupported by the target pipeline.
            # For full-content records the exact publisher bytes are added as a
            # hash-bound V2 sidecar below and restored to Document.original_file
            # by the ordinary V2 importer.
            artifact_content_bytes = content_text.encode("utf-8")
            artifact_mime_type = "text/plain"
            artifact_extension = ""
            artifact_is_convertible = False
        artifact_digest = hashlib.sha256(artifact_content_bytes).hexdigest()

        prior_digest = seen_keys.get(canonical_key)
        if prior_digest is not None:
            if prior_digest != source_digest:
                raise SourcePlanError(
                    f"canonical_key {canonical_key!r} produced multiple contents"
                )
            continue
        seen_keys[canonical_key] = source_digest

        document_title = wrapped.display_title or record.heading
        preserve_artifact_extension = bool(artifact_extension) and (
            source_is_document or artifact_uses_rendition
        )
        filename = sanitize_corpus_filename(
            f"{document_title}.{artifact_extension}"
            if preserve_artifact_extension
            and not document_title.casefold().endswith(f".{artifact_extension}")
            else document_title
        )
        if filename in seen_names:
            # Distinct official records routinely share a publisher title
            # ("Bill Analysis", "Attachment", etc.). The V2 archive member,
            # unlike the displayed Document title, must be unique. Prefix the
            # member with a digest of its stable canonical identity so the
            # disambiguator survives the shared filename sanitizer's
            # right-truncation of long publisher titles.
            identity_prefix = hashlib.sha256(canonical_key.encode("utf-8")).hexdigest()[
                :16
            ]
            filename = sanitize_corpus_filename(
                f"{identity_prefix} {document_title}"
                + (f".{artifact_extension}" if preserve_artifact_extension else "")
            )
        if filename in seen_names:
            raise SourcePlanError(
                f"canonical identities collide at sanitized filename {filename!r}"
            )
        seen_names.add(filename)

        publisher_source_packaging: str | None = None
        publisher_source_member: str | None = None
        if wrapped.ingestion_mode == "full_content":
            publisher_source_packaging = (
                _PUBLISHER_SOURCE_PACKAGING_DOCUMENT
                if source_is_document
                else _PUBLISHER_SOURCE_PACKAGING_SIDECAR
            )
            publisher_source_member = (
                filename
                if source_is_document
                else _publisher_source_sidecar_member(
                    source_url=source_url,
                    canonical_key=canonical_key,
                    source_digest=source_digest,
                )
            )

        custom_meta = {
            **_json_safe(metadata),
            "canonical_key": canonical_key,
            "authority": canonical_key.split(":", 1)[0],
            "pack_origin": pack_name,
            "source_plan_fingerprint": source_plan_fingerprint,
            "pack_fingerprint": pack_fingerprint,
            "ingestion_mode": wrapped.ingestion_mode,
            "rights_approved": wrapped.rights_approved,
            "artifact_content_hash": artifact_digest,
            "artifact_mime_type": artifact_mime_type,
            "publisher_source_filename": source_filename,
            "conversion_required": artifact_is_convertible,
            "authority_provider_fields": sorted(str(key) for key in metadata),
        }
        if artifact_uses_rendition:
            custom_meta.update(
                {
                    "portable_rendition_filename": rendition_filename,
                    "portable_rendition_content_hash": artifact_digest,
                    "portable_rendition_mime_type": rendition_mime_type,
                }
            )
        if publisher_source_member is not None:
            custom_meta.update(
                {
                    "publisher_source_member": publisher_source_member,
                    "publisher_source_content_hash": source_digest,
                    "publisher_source_mime_type": source_mime_type,
                    "publisher_source_packaging": publisher_source_packaging,
                }
            )
        if aliases:
            custom_meta["authority_aliases"] = aliases
        normalized.append(
            {
                "canonical_key": canonical_key,
                "title": document_title,
                "description": (
                    f"Authority source {canonical_key}"
                    + (f" ({source_url})" if source_url else "")
                ),
                "content": content_text,
                "content_bytes": artifact_content_bytes,
                "source_content_bytes": source_content_bytes,
                "content_hash": artifact_digest,
                "source_content_hash": source_digest,
                "mime_type": artifact_mime_type,
                "source_mime_type": source_mime_type,
                "filename": filename,
                "custom_meta": custom_meta,
                "source_url": source_url,
                "source_identifier": source_identifier,
                "retrieved_at": retrieved_at,
                "source_id": wrapped.source_id,
                "publisher_source_member": publisher_source_member,
                "publisher_source_packaging": publisher_source_packaging,
                "source_plan_fingerprint": source_plan_fingerprint,
                "pack_fingerprint": pack_fingerprint,
            }
        )
    if not normalized:
        raise SourcePlanError(f"corpus {corpus_entry['slug']!r} has no records")
    return normalized


def _artifact_provider_relationships(
    record: AuthoritySourceRecord,
    *,
    source_id: str,
) -> list[dict[str, object]]:
    """Keep externally collected graph edges provisional and auditable."""

    normalized: list[dict[str, object]] = []
    for relationship in record.relationships:
        if relationship.verified:
            raise SourcePlanError(
                f"{source_id}: provider relationship from "
                f"{record.canonical_key!r} to {relationship.target_key!r} "
                "must not be pre-verified by a standalone collector"
            )
        relationship_metadata = {
            **dict(relationship.metadata),
            "review_status": "pending_legal_review",
            "source_plan_id": source_id,
            "provenance": (
                relationship.metadata.get("provenance") or "authority_source_provider"
            ),
            "source_url": record.source_url,
        }
        normalized.append(
            {
                "target_key": relationship.target_key,
                "relationship_type": str(relationship.relationship_type),
                "verified": False,
                "metadata": _json_safe(relationship_metadata),
            }
        )
    return normalized


def _publisher_source_filename(
    record: AuthoritySourceRecord | AuthoritySection,
    *,
    source_url: str,
    canonical_key: str,
    converter_extensions: frozenset[str],
) -> str:
    """Resolve the publisher filename that drives extension-based conversion."""

    metadata = record.metadata
    explicit = metadata.get("publisher_source_filename") or metadata.get(
        "archive_member_name"
    )
    if explicit is not None:
        if not isinstance(explicit, str) or not explicit.strip():
            raise SourcePlanError(
                f"{canonical_key}: publisher_source_filename must be non-empty text"
            )
        if "\\" in explicit:
            raise SourcePlanError(
                f"{canonical_key}: publisher_source_filename uses backslashes"
            )
        name = PurePosixPath(explicit).name
    else:
        name = PurePosixPath(unquote(urlsplit(source_url).path)).name
    name = name or canonical_key
    current_extension = PurePosixPath(name).suffix.lstrip(".").casefold()
    source_mime_type = (
        record.mime_type if isinstance(record, AuthoritySourceRecord) else "text/plain"
    )
    guessed_extension = (
        (mimetypes.guess_extension(source_mime_type, strict=False) or "")
        .lstrip(".")
        .casefold()
    )
    if (
        current_extension not in converter_extensions
        and guessed_extension in converter_extensions
    ):
        # Some official HTML endpoints end in a rule number or route segment
        # ("/25.214/", "/PGRR145") rather than ".html". Give the exact
        # publisher bytes the converter extension implied by their verified
        # MIME so the existing extension-keyed import pipeline can route them.
        name = f"{name}.{guessed_extension}"
    return name


def _publisher_source_sidecar_member(
    *,
    source_url: str,
    canonical_key: str,
    source_digest: str,
) -> str:
    """Return a deterministic, flat ZIP member for publisher source bytes."""

    raw_name = unquote(Path(urlsplit(source_url).path).name)
    if not raw_name:
        raw_name = canonical_key
    # Put the full digest before the publisher filename so truncation retains
    # the collision-resistant identity while sanitize_corpus_filename keeps a
    # useful original extension when one exists.
    return sanitize_corpus_filename(
        f"publisher-source-{source_digest}-{raw_name}",
        fallback=f"publisher-source-{source_digest}",
    )


def _build_export_payload(
    *,
    pack_name: str,
    corpus_entry: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
    corpus_config: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, bytes]]:
    annotated_docs: dict[str, dict[str, Any]] = {}
    document_paths: list[dict[str, Any]] = []
    members: dict[str, bytes] = {}
    source_name = f"authority:{pack_name}"[:255]
    for record in records:
        filename = str(record["filename"])
        content_bytes = bytes(record["content_bytes"])
        if filename in members and members[filename] != content_bytes:
            raise SourcePlanError(f"ZIP member {filename!r} has conflicting contents")
        members[filename] = content_bytes
        publisher_source_member = record.get("publisher_source_member")
        publisher_source_packaging = record.get("publisher_source_packaging")
        if publisher_source_packaging == _PUBLISHER_SOURCE_PACKAGING_SIDECAR:
            if not isinstance(publisher_source_member, str):
                raise SourcePlanError(
                    f"{record['canonical_key']}: sidecar packaging requires a "
                    "publisher_source_member"
                )
            source_content_bytes = bytes(record["source_content_bytes"])
            prior_source = members.get(publisher_source_member)
            if prior_source is not None and prior_source != source_content_bytes:
                raise SourcePlanError(
                    f"ZIP source member {publisher_source_member!r} has "
                    "conflicting contents"
                )
            members[publisher_source_member] = source_content_bytes
        annotated_docs[filename] = {
            "title": record["title"],
            "description": record["description"],
            "content": record["content"],
            "pawls_file_content": [],
            "page_count": 0,
            "file_type": record["mime_type"],
            "pdf_file_hash": record["content_hash"],
            "custom_meta": record["custom_meta"],
            "doc_labels": [],
            "labelled_text": [],
            "relationships": [],
        }
        document_paths.append(
            {
                # Filename is the V2 export's unambiguous document identity.
                # Content hashes are not: two link-only canonical records can
                # intentionally point at the same publisher URL and therefore
                # have identical stub bytes. The existing importer indexes
                # annotated_docs by filename specifically for this fallback.
                "document_ref": filename,
                "folder_path": None,
                "path": f"/documents/{filename}",
                "version_number": 1,
                "parent_version_number": None,
                "is_current": True,
                "is_deleted": False,
                "created": record["retrieved_at"],
                "ingestion_source_name": source_name,
                "external_id": record["source_identifier"],
                "ingestion_metadata": {
                    "canonical_key": record["canonical_key"],
                    "source_url": record["source_url"],
                    "source_identifier": record["source_identifier"],
                    "retrieved_at": record["retrieved_at"],
                    "content_hash": record["content_hash"],
                    "source_content_hash": record["source_content_hash"],
                    "source_mime_type": record["source_mime_type"],
                    "artifact_content_hash": record["content_hash"],
                    "artifact_mime_type": record["mime_type"],
                    "pack_origin": pack_name,
                    "source_plan_id": record["source_id"],
                    "source_plan_fingerprint": record["source_plan_fingerprint"],
                    "pack_fingerprint": record["pack_fingerprint"],
                    **(
                        {
                            "publisher_source_member": publisher_source_member,
                            "publisher_source_content_hash": record[
                                "source_content_hash"
                            ],
                            "publisher_source_mime_type": record["source_mime_type"],
                            "publisher_source_packaging": (publisher_source_packaging),
                        }
                        if publisher_source_member is not None
                        else {}
                    ),
                },
            }
        )

    title = str(corpus_entry["title"])
    description = str(corpus_entry.get("description") or "")
    data_json = {
        "version": ARTIFACT_FORMAT_VERSION,
        "annotated_docs": annotated_docs,
        "doc_labels": {},
        "text_labels": {},
        "corpus": {
            "id": 0,
            "title": title,
            "description": description,
            "icon_name": "corpus.png",
            "icon_data": "",
            "creator": "authority-import-builder",
            "label_set": "0",
            "slug": corpus_entry["slug"],
            "post_processors": corpus_config["post_processors"],
            "preferred_embedder": corpus_config["preferred_embedder"],
            "corpus_agent_instructions": corpus_config["corpus_agent_instructions"],
            "document_agent_instructions": corpus_config["document_agent_instructions"],
            "allow_comments": True,
        },
        "label_set": {
            "id": "0",
            "title": f"{title} Labels",
            "description": f"Labels for {title}",
            "icon_name": "labelset.png",
            "icon_data": "",
            "creator": "authority-import-builder",
        },
        "structural_annotation_sets": {},
        "folders": [],
        "document_paths": document_paths,
        "relationships": [],
        "agent_config": {
            "corpus_agent_instructions": corpus_config["corpus_agent_instructions"],
            "document_agent_instructions": corpus_config["document_agent_instructions"],
        },
        "md_description": None,
        "md_description_revisions": [],
        "post_processors": corpus_config["post_processors"],
        "ingestion_sources": [
            {
                "name": source_name,
                "source_type": "crawler",
                "config": {},
                "active": False,
            }
        ],
    }
    return data_json, members


def _write_deterministic_zip(
    path: Path, data_json: Mapping[str, Any], members: Mapping[str, bytes]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        _write_zip_member(
            archive,
            "data.json",
            (json.dumps(data_json, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        )
        for filename in sorted(members):
            _write_zip_member(archive, filename, members[filename])


def _write_zip_member(archive: zipfile.ZipFile, name: str, content: bytes) -> None:
    info = zipfile.ZipInfo(name, date_time=_ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    archive.writestr(info, content)


def _provider_definitions() -> tuple[Sequence[Any], Sequence[Any]]:
    from opencontractserver.pipeline.registry import (
        get_all_authority_discovery_providers_cached,
        get_all_authority_source_providers_cached,
    )

    source = sorted(
        get_all_authority_source_providers_cached(),
        key=lambda item: (
            getattr(item.component_class, "priority", 100),
            item.class_name,
        ),
    )
    discovery = sorted(
        get_all_authority_discovery_providers_cached(),
        key=lambda item: item.class_name,
    )
    return source, discovery


def _configured_supported_mime_types() -> frozenset[str]:
    """Return portable target MIME types from the existing pipeline registry."""

    try:
        from opencontractserver.pipeline.registry import get_allowed_mime_types

        allowed = frozenset(get_allowed_mime_types())
    except Exception:  # noqa: BLE001 - standalone fallback is intentionally narrow
        allowed = frozenset()
    # Plain text is the guaranteed artifact fallback and does not need a
    # document parser service. Keep it even in a minimal standalone process.
    return frozenset((*allowed, "text/plain"))


def _registered_converter_extensions() -> frozenset[str]:
    """Return source extensions handled by existing registered converters."""

    try:
        from opencontractserver.pipeline.registry import (
            get_all_file_converters_cached,
        )

        extensions = {
            str(extension).strip().lstrip(".").casefold()
            for definition in get_all_file_converters_cached()
            for extension in getattr(
                definition.component_class,
                "supported_extensions",
                (),
            )
            if str(extension).strip().lstrip(".")
        }
    except Exception:  # noqa: BLE001 - standalone fallback stays fail-closed
        extensions = set()
    return frozenset(extensions)


def _resolve_provider(name: str, definitions: Sequence[Any], *, kind: str) -> type:
    matches = [
        definition.component_class
        for definition in definitions
        if name
        in {
            definition.name,
            definition.class_name,
            definition.component_class.__name__,
        }
    ]
    if len(matches) != 1:
        raise SourcePlanError(
            f"{kind} provider {name!r} resolved to {len(matches)} registered classes"
        )
    return matches[0]


def _route_source_provider(canonical_key: str, definitions: Sequence[Any]) -> type:
    for definition in definitions:
        provider_cls = definition.component_class
        provider = provider_cls()
        if getattr(provider_cls, "enabled", True) and provider.can_handle(
            canonical_key
        ):
            return provider_cls
    raise SourcePlanError(
        f"no registered authority source provider handles {canonical_key!r}"
    )


def _filter_candidates(
    candidates: Sequence[tuple[str, DiscoveryCandidate | None]],
    filters: Mapping[str, Any] | None,
    *,
    source_id: str,
    report: CollectionReport,
) -> list[tuple[str, DiscoveryCandidate | None]]:
    if not filters:
        return list(candidates)
    compiled = {
        key: [re.compile(pattern, re.IGNORECASE) for pattern in values]
        for key, values in filters.items()
    }
    kept = []
    for canonical_key, candidate in candidates:
        title = (candidate.title if candidate else "") or ""
        url = (candidate.url if candidate else "") or ""
        include_title = compiled.get("include_title", [])
        include_url = compiled.get("include_url", [])
        excluded = (
            (
                include_title
                and not any(pattern.search(title) for pattern in include_title)
            )
            or (include_url and not any(pattern.search(url) for pattern in include_url))
            or any(
                pattern.search(title) for pattern in compiled.get("exclude_title", [])
            )
            or any(pattern.search(url) for pattern in compiled.get("exclude_url", []))
        )
        if excluded:
            report.skipped.append(
                {
                    "source_id": source_id,
                    "candidate": canonical_key,
                    "reason": "candidate_filters",
                }
            )
        else:
            kept.append((canonical_key, candidate))
    return kept


def _read_pack_manifest(pack_dir: Path) -> dict[str, Any]:
    path = pack_dir / "pack.yaml"
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise SourcePlanError(f"Could not read authority pack {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise SourcePlanError(f"{path}: pack manifest must be a mapping")
    return raw


def _source_plan_path(
    pack_dir: Path,
    manifest: Mapping[str, Any],
    override: Path | None,
) -> Path:
    raw_path: Path | str = (
        override
        if override is not None
        else str(manifest.get("sources") or SOURCE_PLAN_FILENAME)
    )
    path = (
        Path(raw_path).resolve()
        if Path(raw_path).is_absolute()
        else (pack_dir / Path(raw_path)).resolve()
    )
    if pack_dir not in path.parents:
        raise SourcePlanError("source plan escapes the authority pack directory")
    if not path.is_file():
        raise SourcePlanError(f"source plan not found: {path}")
    return path


def _file_fingerprint(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _pack_fingerprint(pack_dir: Path) -> str:
    from opencontractserver.enrichment.services.authority_pack_service import (
        AuthorityPackService,
    )

    return AuthorityPackService.declarative_fingerprint(pack_dir)


def _corpus_export_config(
    *,
    pack_dir: Path,
    manifest: Mapping[str, Any],
    corpus_entry: Mapping[str, Any],
) -> dict[str, Any]:
    """Mirror the pack shell's non-content configuration into its artifact."""

    persona_text = None
    persona_rel = corpus_entry.get("persona")
    if persona_rel:
        persona_path = (pack_dir / str(persona_rel)).resolve()
        if pack_dir not in persona_path.parents:
            raise SourcePlanError("corpus persona escapes the pack directory")
        try:
            persona_text = persona_path.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError) as exc:
            raise SourcePlanError(
                f"Could not read corpus persona {persona_path}: {exc}"
            ) from exc

    raw_processors = corpus_entry.get(
        "post_processors", manifest.get("post_processors", [])
    )
    if raw_processors is None:
        raw_processors = []
    if not isinstance(raw_processors, list) or not all(
        isinstance(value, str) for value in raw_processors
    ):
        raise SourcePlanError("post_processors must be a list of strings")
    return {
        "post_processors": list(raw_processors),
        "preferred_embedder": corpus_entry.get("preferred_embedder"),
        "corpus_agent_instructions": persona_text,
        "document_agent_instructions": corpus_entry.get("document_agent_instructions"),
    }


def _manifest_corpora(manifest: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    raw = manifest.get("corpora")
    if not isinstance(raw, list) or not raw:
        raise SourcePlanError("pack manifest must declare a non-empty corpora list")
    result: dict[str, dict[str, Any]] = {}
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise SourcePlanError(f"pack corpora[{index}] must be a mapping")
        slug = entry.get("slug")
        title = entry.get("title")
        if not isinstance(slug, str) or not _CORPUS_SLUG_RE.fullmatch(slug):
            raise SourcePlanError(f"pack corpora[{index}].slug is invalid")
        if not isinstance(title, str) or not title.strip():
            raise SourcePlanError(f"pack corpora[{index}].title is required")
        if slug in result:
            raise SourcePlanError(f"pack declares duplicate corpus slug {slug!r}")
        result[slug] = entry
    return result


def _corpus_aliases(
    pack_dir: Path, corpus_entry: Mapping[str, Any]
) -> list[str] | None:
    spec_rel = corpus_entry.get("spec")
    if not spec_rel:
        return None
    spec_path = (pack_dir / str(spec_rel)).resolve()
    if pack_dir not in spec_path.parents:
        raise SourcePlanError("corpus spec escapes the pack directory")
    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SourcePlanError(f"Could not read corpus spec {spec_path}: {exc}") from exc
    aliases = spec.get("aliases")
    if aliases is None:
        return None
    if not isinstance(aliases, list) or not all(
        isinstance(alias, str) for alias in aliases
    ):
        raise SourcePlanError(f"{spec_path}: aliases must be a list of strings")
    return aliases


def _pack_name(manifest: Mapping[str, Any], pack_dir: Path) -> str:
    value = manifest.get("name") or pack_dir.name
    if not isinstance(value, str) or not value.strip():
        raise SourcePlanError("pack name must be a non-empty string")
    return value.strip()


def _content_sentinel(value: str) -> str:
    normalized = " ".join(value.split())
    if not normalized:
        raise SourcePlanError("authority record has no extracted text")
    return normalized[:160]


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(item) for item in value]
    raise SourcePlanError(
        f"authority metadata contains non-JSON value {type(value).__name__}"
    )


def _require_string(value: Any, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise SourcePlanError(f"{label} must be a non-empty string")


def _require_http_url(value: Any, label: str) -> None:
    if not isinstance(value, str) or not value.startswith("https://"):
        raise SourcePlanError(f"{label} must be an HTTPS URL")


def _require_canonical_key(value: Any, label: str) -> None:
    if not isinstance(value, str) or not _CANONICAL_KEY_RE.fullmatch(value):
        raise SourcePlanError(f"{label} is not a canonical authority key")


def _normalize_relationship_type(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise SourcePlanError(f"{label} must be a relationship type string")
    try:
        return RelationshipType(value).value
    except ValueError as exc:
        allowed = ", ".join(item.value for item in RelationshipType)
        raise SourcePlanError(
            f"{label} must be one of {allowed}; got {value!r}"
        ) from exc


def _validate_authority_metadata(value: Any, label: str) -> dict[str, Any]:
    """Validate and normalize one plan/provider authority metadata mapping."""

    if not isinstance(value, dict):
        raise SourcePlanError(f"{label} must be a mapping")
    if any(not isinstance(key, str) or not key.strip() for key in value):
        raise SourcePlanError(f"{label} keys must be non-empty strings")
    reserved = set(value) & _BUILDER_OWNED_METADATA_FIELDS
    if reserved:
        raise SourcePlanError(
            f"{label} cannot set builder-owned fields: {sorted(reserved)}"
        )

    normalized = _json_safe(value)
    try:
        json.dumps(normalized, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise SourcePlanError(f"{label} must contain JSON-safe values: {exc}") from exc

    for field_name in _AUTHORITY_METADATA_STRING_FIELDS:
        if field_name in normalized:
            _require_string(normalized[field_name], f"{label}.{field_name}")
    if "authority_type" in normalized and normalized["authority_type"] not in {
        *ALL_AUTHORITY_TYPES
    }:
        raise SourcePlanError(
            f"{label}.authority_type must be one of {sorted(ALL_AUTHORITY_TYPES)}"
        )
    if "instrument_type" in normalized:
        try:
            normalized["instrument_type"] = InstrumentType(
                normalized["instrument_type"]
            ).value
        except (TypeError, ValueError) as exc:
            raise SourcePlanError(
                f"{label}.instrument_type is not a recognized instrument type"
            ) from exc
    if "authority_weight" in normalized:
        try:
            normalized["authority_weight"] = AuthorityWeight(
                normalized["authority_weight"]
            ).value
        except (TypeError, ValueError) as exc:
            raise SourcePlanError(
                f"{label}.authority_weight is not a recognized authority weight"
            ) from exc
    if "status" in normalized:
        try:
            normalized["status"] = normalize_source_status(normalized["status"])
        except (TypeError, ValueError) as exc:
            raise SourcePlanError(
                f"{label}.status is not a recognized source status"
            ) from exc
    if "current_version" in normalized:
        try:
            normalized["current_version"] = parse_optional_bool(
                normalized["current_version"],
                field_name=f"{label}.current_version",
            )
        except ValueError as exc:
            raise SourcePlanError(str(exc)) from exc
    for field_name in _AUTHORITY_METADATA_DATE_FIELDS:
        if field_name not in normalized:
            continue
        try:
            parsed = parse_authority_date(normalized[field_name])
        except ValueError as exc:
            raise SourcePlanError(f"{label}.{field_name}: {exc}") from exc
        normalized[field_name] = parsed.isoformat() if parsed is not None else None
    return normalized


def _static_candidate_extra(candidate: Mapping[str, Any]) -> dict[str, Any]:
    """Build the same nested metadata shape live discovery providers emit."""

    extra = dict(candidate.get("extra") or {})
    nested = _validate_authority_metadata(
        extra.pop("metadata", {}),
        "candidate.extra.metadata",
    )
    declared = _validate_authority_metadata(
        candidate.get("metadata", {}),
        "candidate.metadata",
    )
    if nested or declared:
        extra["metadata"] = {**nested, **declared}
    return extra


def _candidate_discovery_metadata(
    candidate: DiscoveryCandidate | None,
) -> dict[str, Any]:
    """Return provider discovery provenance without the merge-only helper."""

    if candidate is None:
        return {}
    return {key: value for key, value in candidate.extra.items() if key != "metadata"}


def _candidate_promoted_metadata(
    candidate: DiscoveryCandidate | None,
    *,
    canonical_key: str,
) -> dict[str, Any]:
    """Normalize legacy direct candidate fields promoted onto the document."""

    if candidate is None:
        return {}
    return _validate_authority_metadata(
        {
            key: candidate.extra[key]
            for key in _PROMOTED_CANDIDATE_EXTRA_METADATA_FIELDS
            if key in candidate.extra and candidate.extra[key] not in (None, "")
        },
        f"candidate {canonical_key!r}.extra",
    )


def _link_only_metadata(
    *,
    source: Mapping[str, Any],
    candidate: DiscoveryCandidate | None,
    canonical_key: str,
) -> tuple[dict[str, Any], tuple[SourceRelationship, ...]]:
    """Merge legal metadata and optionally derive one typed parent edge."""

    source_metadata = _validate_authority_metadata(
        source.get("metadata", {}),
        f"source {source.get('id')!r}.metadata",
    )
    candidate_metadata = _validate_authority_metadata(
        candidate.extra.get("metadata", {}) if candidate is not None else {},
        f"candidate {canonical_key!r}.metadata",
    )
    metadata = {
        "review_status": "pending_legal_review",
        **source_metadata,
        **candidate_metadata,
        **_candidate_promoted_metadata(
            candidate,
            canonical_key=canonical_key,
        ),
    }
    missing = [
        field_name
        for field_name in _REQUIRED_LINK_ONLY_AUTHORITY_METADATA
        if field_name not in metadata
        or not isinstance(metadata[field_name], str)
        or not metadata[field_name].strip()
    ]
    if missing:
        raise SourcePlanError(
            f"link_only candidate {canonical_key!r} is missing required authority "
            f"metadata fields: {', '.join(missing)}"
        )

    relationships: tuple[SourceRelationship, ...] = ()
    relationship_type = source.get("parent_relationship_type")
    parent_key = candidate.extra.get("parent_key") if candidate is not None else None
    if relationship_type is not None and parent_key is not None:
        _require_canonical_key(parent_key, f"candidate {canonical_key!r}.parent_key")
        relationship_metadata: dict[str, Any] = {
            "review_status": "pending_legal_review",
            "source_plan_id": source["id"],
            "provenance": "source_plan_parent_key",
        }
        if candidate is not None and candidate.url:
            relationship_metadata["candidate_url"] = candidate.url
        relationship = SourceRelationship(
            target_key=parent_key,
            relationship_type=_normalize_relationship_type(
                relationship_type,
                f"source {source.get('id')!r}.parent_relationship_type",
            ),
            verified=False,
            metadata=relationship_metadata,
        )
        metadata["parent_proceeding"] = parent_key
        relationships = (relationship,)
    return metadata, relationships


def _validate_candidate(candidate: Any, label: str) -> None:
    if not isinstance(candidate, dict):
        raise SourcePlanError(f"{label} must be a mapping")
    unknown = set(candidate) - {
        "canonical_key",
        "url",
        "title",
        "publisher_title",
        "display_title",
        "extra",
        "metadata",
    }
    if unknown:
        raise SourcePlanError(f"{label} has unknown keys: {sorted(unknown)}")
    _require_canonical_key(candidate.get("canonical_key"), f"{label}.canonical_key")
    if candidate.get("url") is not None:
        _require_http_url(candidate["url"], f"{label}.url")
    if (
        candidate.get("title") is not None
        and candidate.get("publisher_title") is not None
    ):
        raise SourcePlanError(f"{label} cannot declare both title and publisher_title")
    for title_key in ("title", "publisher_title", "display_title"):
        if candidate.get(title_key) is not None:
            _require_string(candidate[title_key], f"{label}.{title_key}")
    extra = candidate.get("extra", {})
    if not isinstance(extra, dict):
        raise SourcePlanError(f"{label}.extra must be a mapping")
    _validate_authority_metadata(candidate.get("metadata", {}), f"{label}.metadata")
    _validate_authority_metadata(
        extra.get("metadata", {}),
        f"{label}.extra.metadata",
    )
    _validate_authority_metadata(
        {
            key: extra[key]
            for key in _PROMOTED_CANDIDATE_EXTRA_METADATA_FIELDS
            if key in extra
        },
        f"{label}.extra",
    )
    if extra.get("parent_key") is not None:
        _require_canonical_key(extra["parent_key"], f"{label}.extra.parent_key")


def _validate_candidate_filters(value: Any, label: str) -> None:
    if value is None:
        return
    if not isinstance(value, dict):
        raise SourcePlanError(f"{label}.candidate_filters must be a mapping")
    unknown = set(value) - _FILTER_KEYS
    if unknown:
        raise SourcePlanError(
            f"{label}.candidate_filters has unknown keys: {sorted(unknown)}"
        )
    for key, patterns in value.items():
        if not isinstance(patterns, list) or not all(
            isinstance(pattern, str) and pattern for pattern in patterns
        ):
            raise SourcePlanError(
                f"{label}.candidate_filters.{key} must be a list of regex strings"
            )
        for pattern in patterns:
            try:
                re.compile(pattern)
            except re.error as exc:
                raise SourcePlanError(
                    f"{label}.candidate_filters.{key} invalid regex {pattern!r}: {exc}"
                ) from exc
