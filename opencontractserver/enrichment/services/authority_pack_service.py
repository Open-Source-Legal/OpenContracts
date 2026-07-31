"""Reusable authority-pack catalog, preflight, and installation service.

Authority packs are trusted, server-installed definitions.  This service is the
single implementation used by the management command and GraphQL: it validates
the whole pack before writing, fingerprints every declarative file consumed by
the loader, and installs through the existing authority-corpus bootstrap rail.
It deliberately does not fetch or scrape corpus content.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import yaml
from django.core.management.base import CommandError
from django.db import transaction
from django.utils.text import slugify

from opencontractserver.enrichment.authorities import (
    bootstrap_authority_corpus,
    read_section_spec,
)
from opencontractserver.enrichment.constants import (
    BASELINE_ORIGIN_CORE,
    BASELINE_ORIGIN_MAX_LENGTH,
)
from opencontractserver.enrichment.data.mappings import is_valid_prefix
from opencontractserver.enrichment.services.authority_mapping_loader import (
    AuthorityMappingLoader,
)
from opencontractserver.enrichment.services.authority_pack_config import (
    pack_origin_name,
)
from opencontractserver.enrichment.services.authority_permissions import (
    DENIED,
    is_authority_admin,
)
from opencontractserver.enrichment.services.authority_source_hosts import (
    parse_source_hosts_declaration,
)
from opencontractserver.pipeline.registry import authority_pack_dirs
from opencontractserver.shared.services.conventions import ServiceResult

_PACK_CORPUS_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,126}[a-z0-9])?$")
_CANONICAL_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9-]*:.+$")


@dataclass(frozen=True)
class _ValidatedCorpus:
    title: str
    slug: str | None
    description: str
    sections: list
    aliases: list[str] | None
    persona_text: str | None
    metadata_schema: dict | None
    entry: dict
    authority_prefixes: tuple[str, ...] = ()
    charter: dict | None = None


@dataclass(frozen=True)
class AuthorityPackCorpusPlan:
    """Side-effect-free status for one corpus declared by a pack."""

    slug: str
    title: str
    approval_status: str
    installed: bool
    is_public: bool
    corpus_id: int | None
    action: str
    section_count: int


@dataclass(frozen=True)
class AuthorityPackPlan:
    """Validated public preflight plus private data needed for installation."""

    pack_id: str
    name: str
    display_name: str
    description: str
    jurisdiction: str
    schema_version: int
    fingerprint: str
    source_hosts: tuple[str, ...]
    valid: bool
    validation_error: str | None
    approval_status: str
    can_install: bool
    can_publish: bool
    corpora: tuple[AuthorityPackCorpusPlan, ...]
    pack_dir: Path | None = field(default=None, repr=False, compare=False)
    manifest: dict = field(default_factory=dict, repr=False, compare=False)
    mappings_path: Path | None = field(default=None, repr=False, compare=False)
    validated_corpora: tuple[_ValidatedCorpus, ...] = field(
        default=(), repr=False, compare=False
    )
    existing_corpus_ids: dict[str, int] = field(
        default_factory=dict, repr=False, compare=False
    )
    relationships: tuple[dict, ...] = field(default=(), repr=False, compare=False)
    origin: str = field(default="", repr=False, compare=False)

    @property
    def total_corpora(self) -> int:
        return len(self.corpora)

    @property
    def installed_count(self) -> int:
        return sum(corpus.installed for corpus in self.corpora)

    @property
    def public_count(self) -> int:
        return sum(corpus.is_public for corpus in self.corpora)

    @property
    def installed(self) -> bool:
        return bool(self.corpora) and self.installed_count == self.total_corpora

    @property
    def fully_public(self) -> bool:
        return bool(self.corpora) and self.public_count == self.total_corpora


@dataclass(frozen=True)
class AuthorityPackInstallResult:
    """Structured result shared by command and API adapters."""

    pack: AuthorityPackPlan
    taxonomy_summary: dict | None
    corpus_summaries: tuple[dict, ...]
    relationship_summary: dict
    relink_summary: dict | None

    def as_dict(self) -> dict:
        created = sum(
            int(summary.get("documents_created", 0))
            for summary in self.corpus_summaries
        )
        updated = sum(
            int(summary.get("documents_updated", 0))
            + int(summary.get("documents_metadata_updated", 0))
            + int(summary.get("documents_restamped", 0))
            for summary in self.corpus_summaries
        )
        return {
            "corpora": len(self.corpus_summaries),
            "documents_created": created,
            "documents_updated": updated,
            "relationships": dict(self.relationship_summary),
            "relink": self.relink_summary,
        }


class AuthorityPackService:
    """Catalog and install trusted packs through one reusable service."""

    @classmethod
    def catalog(cls, user) -> list[AuthorityPackPlan]:
        """Return server-configured packs for an authority administrator.

        Invalid packs remain visible with a validation error so an operator can
        repair the configured artifact.  A non-admin receives an empty catalog,
        matching the other authority-admin read surfaces.
        """
        if not is_authority_admin(user):
            return []

        directories = [path.resolve() for path in authority_pack_dirs()]
        identities = [cls._best_effort_pack_id(path) for path in directories]
        duplicates = {
            pack_id for pack_id in identities if identities.count(pack_id) > 1
        }
        plans: list[AuthorityPackPlan] = []
        for pack_dir, pack_id in zip(directories, identities, strict=True):
            if pack_id in duplicates:
                plans.append(
                    cls._invalid_plan(
                        pack_dir,
                        f"Pack id {pack_id!r} is declared by more than one "
                        "configured authority-pack directory.",
                    )
                )
                continue
            try:
                plans.append(cls.preflight_path(pack_dir, creator=user))
            except (CommandError, OSError, UnicodeError) as exc:
                plans.append(cls._invalid_plan(pack_dir, str(exc)))
        return sorted(plans, key=lambda plan: (plan.display_name.lower(), plan.pack_id))

    @classmethod
    def preflight(cls, user, pack_id: str) -> AuthorityPackPlan | None:
        """Validate one trusted catalog entry without changing database state."""
        if not is_authority_admin(user):
            return None
        try:
            pack_dir = cls._resolve_catalog_pack(pack_id)
        except CommandError:
            return None
        try:
            return cls.preflight_path(pack_dir, creator=user)
        except (CommandError, OSError, UnicodeError) as exc:
            return cls._invalid_plan(pack_dir, str(exc))

    @classmethod
    def install(
        cls,
        user,
        *,
        pack_id: str,
        expected_fingerprint: str,
        publish: bool = False,
        relink: bool = True,
    ) -> ServiceResult[AuthorityPackInstallResult]:
        """Install one catalog pack for the current administrator.

        Only an opaque catalog id is accepted; callers cannot submit a path,
        archive, URL, or manifest.  The expected fingerprint closes the gap
        between a UI preflight and the write.
        """
        if not is_authority_admin(user):
            return ServiceResult.failure(DENIED)
        try:
            pack_dir = cls._resolve_catalog_pack(pack_id)
            plan = cls.preflight_path(pack_dir, creator=user)
            if not expected_fingerprint or plan.fingerprint != expected_fingerprint:
                return ServiceResult.failure(
                    "Authority pack changed after preflight; refresh and review it again."
                )
            if publish and not plan.can_publish:
                return ServiceResult.failure(
                    "This authority pack is not approved for public installation."
                )
            installed = cls._install_plan(
                plan, creator=user, make_public=publish, relink=relink
            )
            refreshed = cls.preflight_path(pack_dir, creator=user)
            return ServiceResult.success(replace(installed, pack=refreshed))
        except (CommandError, OSError, UnicodeError) as exc:
            return ServiceResult.failure(str(exc))

    @classmethod
    def install_path(
        cls,
        pack_dir: Path,
        *,
        creator,
        make_public: bool = False,
        relink: bool = True,
        expected_fingerprint: str | None = None,
    ) -> AuthorityPackInstallResult:
        """Operator-facing path adapter retained for the management command."""
        plan = cls.preflight_path(Path(pack_dir).resolve(), creator=creator)
        if (
            expected_fingerprint is not None
            and plan.fingerprint != expected_fingerprint
        ):
            raise CommandError(
                "Authority pack changed after preflight; validate it again."
            )
        return cls._install_plan(
            plan, creator=creator, make_public=make_public, relink=relink
        )

    @classmethod
    def preflight_path(cls, pack_dir: Path, *, creator) -> AuthorityPackPlan:
        """Fully validate an operator-selected directory without writing."""
        pack_dir = Path(pack_dir).resolve()
        manifest = cls._read_manifest(pack_dir)
        schema_version = manifest.get("schema_version", 1)
        if type(schema_version) is not int or schema_version not in (1, 2):
            raise CommandError(
                f"Unsupported pack schema_version {schema_version!r}; expected 1 or 2."
            )

        mappings_path = cls._resolve_mappings_path(manifest, pack_dir)
        corpora = cls._manifest_corpora(manifest)
        if not corpora and mappings_path is None:
            raise CommandError(
                "Pack manifest declares neither 'mappings' nor 'corpora' — "
                "nothing to load. Check the pack.yaml keys for typos."
            )
        origin = pack_origin_name(pack_dir, manifest)
        if origin.lower() == BASELINE_ORIGIN_CORE:
            raise CommandError(
                f"Pack name {BASELINE_ORIGIN_CORE!r} is reserved for the shipped "
                "core baseline (it is the namespace rows' baseline_origin stamp); "
                "rename the pack."
            )
        if len(origin) > BASELINE_ORIGIN_MAX_LENGTH:
            raise CommandError(
                f"Pack name {origin!r} exceeds {BASELINE_ORIGIN_MAX_LENGTH} "
                "characters (the baseline_origin column width); shorten it."
            )

        cls._validate_source_hosts(manifest)
        if mappings_path is not None:
            from opencontractserver.enrichment.services.authority_pack_config import (
                validate_pack_taxonomy_extensions,
            )

            try:
                validate_pack_taxonomy_extensions(mappings_path)
            except ValueError as exc:
                raise CommandError(str(exc)) from exc

        default_metadata_schema = manifest.get("metadata_schema")
        validated = [
            cls()._validate_corpus_entry(
                entry,
                pack_dir,
                schema_version=schema_version,
                default_metadata_schema=default_metadata_schema,
            )
            for entry in corpora
        ]
        cls._validate_unique_corpus_slugs(validated)
        cls._validate_unique_authority_prefix_bindings(validated)
        if mappings_path is None and any(
            corpus.authority_prefixes for corpus in validated
        ):
            raise CommandError(
                "A corpus with 'authority_prefixes' requires the pack manifest "
                "to declare 'mappings'."
            )
        existing_corpus_ids = cls._preflight_corpus_identities(validated, creator)
        relationships = cls._collect_relationship_declarations(
            validated,
            cls._read_relationships(manifest, pack_dir),
        )
        if mappings_path is not None:
            cls._validate_declared_prefixes(mappings_path, validated, relationships)

        corpus_plans = cls._corpus_plans(
            validated, creator=creator, existing_corpus_ids=existing_corpus_ids
        )
        approval_status = cls._pack_approval_status(corpus_plans)
        can_publish = bool(corpus_plans) and all(
            corpus.approval_status.lower() == "approved" for corpus in corpus_plans
        )
        return AuthorityPackPlan(
            pack_id=origin,
            name=origin,
            display_name=str(manifest.get("display_name") or origin),
            description=str(manifest.get("description") or ""),
            jurisdiction=str(manifest.get("jurisdiction") or ""),
            schema_version=schema_version,
            fingerprint=cls._fingerprint(manifest, pack_dir),
            source_hosts=parse_source_hosts_declaration(manifest.get("source_hosts")),
            valid=True,
            validation_error=None,
            approval_status=approval_status,
            can_install=True,
            can_publish=can_publish,
            corpora=tuple(corpus_plans),
            pack_dir=pack_dir,
            manifest=manifest,
            mappings_path=mappings_path,
            validated_corpora=tuple(validated),
            existing_corpus_ids=existing_corpus_ids,
            relationships=tuple(relationships),
            origin=origin,
        )

    @classmethod
    def _install_plan(
        cls,
        plan: AuthorityPackPlan,
        *,
        creator,
        make_public: bool,
        relink: bool,
    ) -> AuthorityPackInstallResult:
        if not plan.valid or plan.pack_dir is None:
            raise CommandError(plan.validation_error or "Authority pack is invalid.")

        all_keys: list[str] = []
        corpus_summaries: list[dict] = []
        taxonomy_summary: dict | None = None
        with transaction.atomic():
            if plan.mappings_path is not None:
                taxonomy_summary = cls._load_taxonomy(
                    plan.mappings_path, origin=plan.origin
                )

            service = cls()
            for corpus_spec in plan.validated_corpora:
                out = bootstrap_authority_corpus(
                    creator_id=creator.id,
                    corpus_title=corpus_spec.title,
                    sections=corpus_spec.sections,
                    aliases=corpus_spec.aliases,
                    corpus_id=(
                        plan.existing_corpus_ids.get(corpus_spec.slug)
                        if corpus_spec.slug
                        else None
                    ),
                    corpus_slug=corpus_spec.slug,
                    corpus_description=corpus_spec.description,
                    pack_origin=plan.origin,
                    make_public=make_public,
                    relink=False,
                )
                service._bind_corpus_authority_prefixes(
                    corpus_id=out["corpus_id"],
                    prefixes=corpus_spec.authority_prefixes,
                    origin=plan.origin,
                )
                service._apply_corpus_overrides(
                    out["corpus_id"], corpus_spec.entry, corpus_spec.persona_text
                )
                if corpus_spec.metadata_schema:
                    service._apply_metadata_schema(
                        out["corpus_id"], corpus_spec.metadata_schema, creator
                    )
                all_keys.extend(section.key for section in corpus_spec.sections)
                corpus_summaries.append(
                    {
                        "title": corpus_spec.title,
                        "slug": corpus_spec.slug,
                        **out,
                    }
                )

            from opencontractserver.enrichment.services.authority_relationship_service import (
                AuthorityRelationshipService,
            )

            relationship_summary = AuthorityRelationshipService.load_declarations(
                list(plan.relationships), origin=plan.origin
            )

        relink_summary = None
        if all_keys and relink:
            from opencontractserver.enrichment.services import EnrichmentService

            relink_summary = EnrichmentService().relink_corpora_for_keys(all_keys)
        return AuthorityPackInstallResult(
            pack=plan,
            taxonomy_summary=taxonomy_summary,
            corpus_summaries=tuple(corpus_summaries),
            relationship_summary=relationship_summary,
            relink_summary=relink_summary,
        )

    @staticmethod
    def _read_manifest(pack_dir: Path) -> dict:
        manifest_path = pack_dir / "pack.yaml"
        if not manifest_path.is_file():
            raise CommandError(f"No pack.yaml manifest in {pack_dir}")
        try:
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as exc:
            raise CommandError(f"Could not parse {manifest_path}: {exc}") from exc
        if not isinstance(manifest, dict):
            raise CommandError("pack.yaml must contain a top-level mapping.")
        return manifest

    @classmethod
    def _resolve_catalog_pack(cls, pack_id: str) -> Path:
        if not isinstance(pack_id, str) or not pack_id:
            raise CommandError(DENIED)
        matches = [
            path.resolve()
            for path in authority_pack_dirs()
            if cls._best_effort_pack_id(path.resolve()) == pack_id
        ]
        if len(matches) != 1:
            raise CommandError(DENIED)
        return matches[0]

    @classmethod
    def _best_effort_pack_id(cls, pack_dir: Path) -> str:
        try:
            manifest = cls._read_manifest(pack_dir)
        except (CommandError, OSError, UnicodeError):
            return pack_dir.name
        return pack_origin_name(pack_dir, manifest)

    @classmethod
    def _invalid_plan(cls, pack_dir: Path, error: str) -> AuthorityPackPlan:
        manifest: dict = {}
        try:
            manifest = cls._read_manifest(pack_dir)
        except (CommandError, OSError, UnicodeError):
            pass
        pack_id = pack_origin_name(pack_dir, manifest)
        # Catalog responses must not disclose the server's filesystem layout.
        public_error = error.replace(str(pack_dir.resolve()), f"<pack:{pack_id}>")
        fingerprint = ""
        manifest_path = pack_dir / "pack.yaml"
        if manifest_path.is_file():
            try:
                fingerprint = cls._hash_files(pack_dir, [manifest_path])
            except (CommandError, OSError):
                pass
        schema_version = manifest.get("schema_version", 1)
        if type(schema_version) is not int:
            schema_version = 1
        source_hosts: tuple[str, ...] = ()
        try:
            source_hosts = parse_source_hosts_declaration(manifest.get("source_hosts"))
        except ValueError:
            pass
        return AuthorityPackPlan(
            pack_id=pack_id,
            name=pack_id,
            display_name=str(manifest.get("display_name") or pack_id),
            description=str(manifest.get("description") or ""),
            jurisdiction=str(manifest.get("jurisdiction") or ""),
            schema_version=schema_version,
            fingerprint=fingerprint,
            source_hosts=source_hosts,
            valid=False,
            validation_error=public_error,
            approval_status="invalid",
            can_install=False,
            can_publish=False,
            corpora=(),
            pack_dir=pack_dir,
            manifest=manifest,
        )

    @staticmethod
    def _corpus_plans(
        corpora: list[_ValidatedCorpus],
        *,
        creator,
        existing_corpus_ids: dict[str, int],
    ) -> list[AuthorityPackCorpusPlan]:
        from opencontractserver.corpuses.models import Corpus

        plans: list[AuthorityPackCorpusPlan] = []
        for corpus_spec in corpora:
            corpus_id = (
                existing_corpus_ids.get(corpus_spec.slug) if corpus_spec.slug else None
            )
            existing = None
            if corpus_id is not None:
                existing = Corpus.objects.filter(pk=corpus_id).first()
            elif corpus_spec.slug is None:
                existing = Corpus.objects.filter(
                    creator=creator, title=corpus_spec.title
                ).first()
                corpus_id = existing.id if existing is not None else None
            approval_status = str(
                (corpus_spec.charter or {}).get("approval_status", "unspecified")
            )
            plans.append(
                AuthorityPackCorpusPlan(
                    slug=corpus_spec.slug
                    or slugify(corpus_spec.title)[:128]
                    or f"corpus-{len(plans) + 1}",
                    title=corpus_spec.title,
                    approval_status=approval_status,
                    installed=existing is not None,
                    is_public=bool(existing and existing.is_public),
                    corpus_id=corpus_id,
                    action="UPDATE" if existing is not None else "CREATE",
                    section_count=len(corpus_spec.sections),
                )
            )
        return plans

    @staticmethod
    def _pack_approval_status(corpora: list[AuthorityPackCorpusPlan]) -> str:
        statuses = {
            corpus.approval_status.strip().lower() or "unspecified"
            for corpus in corpora
        }
        if not statuses:
            return "not_applicable"
        if len(statuses) == 1:
            return statuses.pop()
        if "pending_legal_review" in statuses:
            return "pending_legal_review"
        return "mixed"

    @classmethod
    def _fingerprint(cls, manifest: dict, pack_dir: Path) -> str:
        files = [pack_dir / "pack.yaml"]
        for key in ("mappings", "relationships", "metadata_schema", "sources"):
            if manifest.get(key):
                files.append(
                    cls._pack_file(pack_dir, manifest[key], label=f"Manifest {key!r}")
                )
        for index, entry in enumerate(cls._manifest_corpora(manifest)):
            if not isinstance(entry, dict):
                continue
            for key in ("spec", "persona", "charter", "metadata_schema"):
                if entry.get(key):
                    files.append(
                        cls._pack_file(
                            pack_dir,
                            entry[key],
                            label=f"corpora[{index}] {key!r}",
                        )
                    )
        return cls._hash_files(pack_dir, files)

    @classmethod
    def declarative_fingerprint(cls, pack_dir: Path) -> str:
        """Fingerprint trusted declarative pack inputs without installing them."""

        pack_dir = Path(pack_dir).resolve()
        return cls._fingerprint(cls._read_manifest(pack_dir), pack_dir)

    @staticmethod
    def _hash_files(pack_dir: Path, files: list[Path]) -> str:
        root = pack_dir.resolve()
        digest = hashlib.sha256()
        unique = sorted({path.resolve() for path in files}, key=lambda p: p.as_posix())
        for path in unique:
            try:
                relative = path.relative_to(root).as_posix()
            except ValueError as exc:
                raise CommandError(
                    f"Authority pack file escapes its directory: {path}"
                ) from exc
            payload = path.read_bytes()
            relative_bytes = relative.encode("utf-8")
            digest.update(len(relative_bytes).to_bytes(8, "big"))
            digest.update(relative_bytes)
            digest.update(len(payload).to_bytes(8, "big"))
            digest.update(payload)
        return f"sha256:{digest.hexdigest()}"

    @staticmethod
    def _pack_file(pack_dir: Path, relative: Any, *, label: str) -> Path:
        if not isinstance(relative, str) or not relative.strip():
            raise CommandError(f"{label} must be a non-empty relative path.")
        root = pack_dir.resolve()
        path = (root / relative).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise CommandError(
                f"{label} escapes the authority pack directory."
            ) from exc
        if not path.is_file():
            raise CommandError(f"{label} not found: {path}")
        return path

    @staticmethod
    def _resolve_mappings_path(manifest: dict, pack_dir: Path) -> Path | None:
        """Validate (without loading) the pack's mappings file."""
        mappings_rel = manifest.get("mappings")
        if not mappings_rel:
            return None
        return AuthorityPackService._pack_file(
            pack_dir, mappings_rel, label="Manifest 'mappings'"
        )

    @staticmethod
    def _load_taxonomy(mappings_path: Path, *, origin: str) -> dict:
        """Load a pre-validated authority-mappings YAML into the registry."""
        return AuthorityMappingLoader.load_all(path=mappings_path, origin=origin)

    def _validate_corpus_entry(
        self,
        entry: dict,
        pack_dir: Path,
        *,
        schema_version: int = 1,
        default_metadata_schema: str | None = None,
    ) -> _ValidatedCorpus:
        """Validate one ``corpora[]`` entry without touching the database.

        Reading the spec, persona, charter and metadata schema here — before
        any corpus is bootstrapped — keeps a
        malformed entry from stranding a half-loaded pack (taxonomy + earlier
        corpora committed, this one aborted). Raises ``CommandError`` on any
        structural problem.
        """
        if not isinstance(entry, dict):
            raise CommandError("Each corpora[] entry must be a mapping.")
        title = entry.get("title")
        spec_rel = entry.get("spec")
        if not title or not spec_rel:
            raise CommandError("Each corpora[] entry needs a 'title' and a 'spec'.")
        if not isinstance(title, str) or not title.strip():
            raise CommandError("Each corpora[] entry needs a non-empty string 'title'.")
        slug = entry.get("slug")
        if schema_version >= 2 and not slug:
            raise CommandError(
                f"Pack schema v2 corpus {title!r} must declare a stable 'slug'."
            )
        if slug is not None and (
            not isinstance(slug, str) or not _PACK_CORPUS_SLUG_RE.fullmatch(slug)
        ):
            raise CommandError(
                f"Corpus {title!r} slug {slug!r} must be 1-128 lowercase "
                "letters/digits/hyphens, with no leading or trailing hyphen."
            )
        authority_prefixes = self._validate_authority_prefixes(entry, title=title)
        description = entry.get("description", "")
        if not isinstance(description, str):
            raise CommandError(f"Corpus {title!r} description must be a string.")
        spec_path = self._pack_file(pack_dir, spec_rel, label=f"Corpus {title!r} spec")
        try:
            sections, aliases = read_section_spec(
                spec_path, label=f"corpus {title!r} spec {spec_path}"
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        persona_text = self._read_persona(entry, pack_dir)

        charter_rel = entry.get("charter")
        charter = None
        if schema_version >= 2 and not charter_rel:
            raise CommandError(f"Pack schema v2 corpus {title!r} needs a 'charter'.")
        if charter_rel:
            charter = self._read_yaml_mapping(
                self._pack_file(
                    pack_dir,
                    charter_rel,
                    label=f"Corpus {title!r} charter",
                ),
                label=f"corpus {title!r} charter",
            )
            if not charter.get("purpose"):
                raise CommandError(
                    f"Corpus {title!r} charter must declare a non-empty 'purpose'."
                )

        metadata_rel = entry.get("metadata_schema", default_metadata_schema)
        metadata_schema = (
            self._read_metadata_schema(
                self._pack_file(
                    pack_dir,
                    metadata_rel,
                    label=f"Corpus {title!r} metadata schema",
                ),
                title=title,
            )
            if metadata_rel
            else None
        )
        default_weight = entry.get("default_authority_weight")
        if default_weight is not None:
            from opencontractserver.enrichment.authority_sources import AuthorityWeight

            try:
                normalized_default_weight = AuthorityWeight(default_weight).value
            except ValueError as exc:
                raise CommandError(
                    f"Corpus {title!r} has unknown default_authority_weight "
                    f"{default_weight!r}."
                ) from exc
            sections = [
                (
                    section
                    if "authority_weight" in section.metadata
                    else replace(
                        section,
                        metadata_defaults={
                            "authority_weight": normalized_default_weight,
                            **dict(section.metadata_defaults),
                        },
                    )
                )
                for section in sections
            ]
        return _ValidatedCorpus(
            title=title.strip(),
            slug=slug,
            description=description.strip(),
            sections=sections,
            aliases=aliases,
            persona_text=persona_text,
            metadata_schema=metadata_schema,
            entry=entry,
            authority_prefixes=authority_prefixes,
            charter=charter,
        )

    @staticmethod
    def _validate_authority_prefixes(
        entry: dict,
        *,
        title: str,
    ) -> tuple[str, ...]:
        """Validate explicit namespace ownership for one corpus declaration."""

        if "authority_prefixes" not in entry:
            return ()
        raw = entry["authority_prefixes"]
        if not isinstance(raw, list):
            raise CommandError(f"Corpus {title!r} authority_prefixes must be a list.")
        normalized: list[str] = []
        for index, value in enumerate(raw):
            prefix = value.strip() if isinstance(value, str) else ""
            if not is_valid_prefix(prefix) or len(prefix) > 64:
                raise CommandError(
                    f"Corpus {title!r} authority_prefixes[{index}] must be a "
                    "lowercase authority prefix of at most 64 characters."
                )
            if prefix in normalized:
                raise CommandError(
                    f"Corpus {title!r} repeats authority prefix {prefix!r}."
                )
            normalized.append(prefix)
        return tuple(normalized)

    @staticmethod
    def _read_yaml_mapping(path: Path, *, label: str) -> dict:
        if not path.is_file():
            raise CommandError(f"{label} not found: {path}")
        try:
            parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise CommandError(f"Could not parse {label} {path}: {exc}") from exc
        if not isinstance(parsed, dict):
            raise CommandError(f"{label} {path} must contain a mapping.")
        return parsed

    @classmethod
    def _read_metadata_schema(cls, path: Path, *, title: str) -> dict:
        schema = cls._read_yaml_mapping(path, label=f"corpus {title!r} metadata schema")
        if schema.get("version", 1) != 1:
            raise CommandError(
                f"Corpus {title!r} metadata schema has unsupported version "
                f"{schema.get('version')!r}."
            )
        fields = schema.get("fields")
        if not isinstance(fields, list) or not fields:
            raise CommandError(
                f"Corpus {title!r} metadata schema needs a non-empty 'fields' list."
            )
        from opencontractserver.extracts.services.metadata import MetadataService

        seen: set[str] = set()
        for index, field_spec in enumerate(fields):
            if not isinstance(field_spec, dict):
                raise CommandError(
                    f"Corpus {title!r} metadata fields[{index}] must be a mapping."
                )
            name = field_spec.get("name")
            data_type = field_spec.get("data_type")
            if not isinstance(name, str) or not name.strip():
                raise CommandError(
                    f"Corpus {title!r} metadata fields[{index}] needs a name."
                )
            if name in seen:
                raise CommandError(
                    f"Corpus {title!r} metadata schema repeats field {name!r}."
                )
            seen.add(name)
            if data_type not in MetadataService.METADATA_DATA_TYPES:
                raise CommandError(
                    f"Corpus {title!r} metadata field {name!r} has invalid "
                    f"data_type {data_type!r}."
                )
            validation_config = field_spec.get("validation_config", {})
            if not isinstance(validation_config, dict):
                raise CommandError(
                    f"Corpus {title!r} metadata field {name!r} "
                    "validation_config must be a mapping."
                )
            if data_type in {"CHOICE", "MULTI_CHOICE"} and not isinstance(
                validation_config.get("choices"), list
            ):
                raise CommandError(
                    f"Corpus {title!r} metadata field {name!r} requires "
                    "validation_config.choices."
                )
        return schema

    @staticmethod
    def _validate_unique_corpus_slugs(corpora: list[_ValidatedCorpus]) -> None:
        slugs = [corpus.slug for corpus in corpora if corpus.slug is not None]
        duplicates = sorted({slug for slug in slugs if slugs.count(slug) > 1})
        if duplicates:
            raise CommandError("Pack repeats corpus slug(s): " + ", ".join(duplicates))

    @staticmethod
    def _validate_unique_authority_prefix_bindings(
        corpora: list[_ValidatedCorpus],
    ) -> None:
        owners: dict[str, str] = {}
        for corpus in corpora:
            for prefix in corpus.authority_prefixes:
                prior_owner = owners.get(prefix)
                if prior_owner is not None:
                    raise CommandError(
                        f"Authority prefix {prefix!r} is bound by both corpus "
                        f"{prior_owner!r} and corpus {corpus.title!r}; a namespace "
                        "can belong to only one corpus."
                    )
                owners[prefix] = corpus.title

    @staticmethod
    def _preflight_corpus_identities(
        corpora: list[_ValidatedCorpus], creator
    ) -> dict[str, int]:
        """Resolve v2 stable identities and reject collisions before writes."""

        from opencontractserver.corpuses.models import Corpus

        resolved: dict[str, int] = {}
        for corpus_spec in corpora:
            if corpus_spec.slug is None:
                continue
            by_slug = list(
                Corpus.objects.filter(
                    creator=creator, slug=corpus_spec.slug
                ).values_list("id", "title")
            )
            if len(by_slug) > 1:  # defensive: DB uniqueness should make this impossible
                raise CommandError(
                    f"Corpus slug {corpus_spec.slug!r} is ambiguous for creator."
                )
            if by_slug:
                resolved[corpus_spec.slug] = by_slug[0][0]
                continue
            by_title = list(
                Corpus.objects.filter(
                    creator=creator, title=corpus_spec.title
                ).values_list("id", "slug")
            )
            if len(by_title) > 1:
                raise CommandError(
                    f"Corpus title {corpus_spec.title!r} is ambiguous for creator."
                )
            if by_title:
                existing_id, existing_slug = by_title[0]
                if existing_slug and existing_slug != corpus_spec.slug:
                    raise CommandError(
                        f"Corpus {corpus_spec.title!r} already has slug "
                        f"{existing_slug!r}; refusing to replace it with "
                        f"{corpus_spec.slug!r}."
                    )
                resolved[corpus_spec.slug] = existing_id
        return resolved

    @classmethod
    def _validate_declared_prefixes(
        cls,
        mappings_path: Path,
        corpora: list[_ValidatedCorpus],
        relationships: list[dict],
    ) -> None:
        mappings = cls._read_yaml_mapping(
            mappings_path, label="pack authority mappings"
        )
        raw_prefixes = mappings.get("prefixes")
        if not isinstance(raw_prefixes, dict) or not raw_prefixes:
            raise CommandError(
                f"Pack mappings {mappings_path} needs a non-empty 'prefixes' mapping."
            )
        declared = set(raw_prefixes)
        for corpus_spec in corpora:
            for prefix in corpus_spec.authority_prefixes:
                if prefix not in declared:
                    raise CommandError(
                        f"Corpus {corpus_spec.title!r} binds authority prefix "
                        f"{prefix!r}, which this pack does not declare."
                    )
            for section in corpus_spec.sections:
                prefix = section.key.split(":", 1)[0]
                if prefix not in declared:
                    raise CommandError(
                        f"Corpus {corpus_spec.title!r} key {section.key!r} uses "
                        f"prefix {prefix!r}, which this pack does not declare."
                    )
        for relationship in relationships:
            source_key = relationship["source_key"]
            prefix = source_key.split(":", 1)[0]
            if prefix not in declared:
                raise CommandError(
                    f"Relationship source {source_key!r} uses prefix {prefix!r}, "
                    "which this pack does not declare."
                )

    @classmethod
    def _read_relationships(cls, manifest: dict, pack_dir: Path) -> list[dict]:
        relationship_rel = manifest.get("relationships")
        if not relationship_rel:
            return []
        parsed = cls._read_yaml_mapping(
            cls._pack_file(
                pack_dir, relationship_rel, label="Manifest 'relationships'"
            ),
            label="pack relationships",
        )
        schema_version = parsed.get("schema_version", 1)
        if type(schema_version) is not int or schema_version != 1:
            raise CommandError(
                "Pack relationships schema_version must be 1; "
                f"got {schema_version!r}."
            )
        declarations = parsed.get("relationships")
        if not isinstance(declarations, list):
            raise CommandError(
                "Pack relationships file must contain a 'relationships' list."
            )
        from opencontractserver.enrichment.authority_sources import (
            RelationshipType,
            SourceRelationship,
        )

        validated: list[dict] = []
        seen: set[tuple[str, str, str]] = set()
        for index, declaration in enumerate(declarations):
            if not isinstance(declaration, dict):
                raise CommandError(f"relationships[{index}] must be a mapping.")
            source_key = declaration.get("source_key")
            if not isinstance(source_key, str) or not _CANONICAL_KEY_RE.fullmatch(
                source_key
            ):
                raise CommandError(
                    f"relationships[{index}] has invalid source_key {source_key!r}."
                )
            try:
                relationship = SourceRelationship(
                    target_key=declaration["target_key"],
                    relationship_type=declaration["relationship_type"],
                    verified=declaration.get("verified", False),
                    metadata=declaration.get("metadata", {}),
                )
                RelationshipType(relationship.relationship_type)
            except (KeyError, TypeError, ValueError) as exc:
                raise CommandError(f"relationships[{index}] is invalid: {exc}") from exc
            identity = (
                source_key,
                str(relationship.relationship_type),
                relationship.target_key,
            )
            if identity in seen:
                raise CommandError(
                    f"Pack relationships file repeats edge {identity!r}."
                )
            seen.add(identity)
            validated.append(
                {
                    "source_key": source_key,
                    **relationship.as_dict(),
                }
            )
        return validated

    @staticmethod
    def _collect_relationship_declarations(
        corpora: list[_ValidatedCorpus],
        manifest_declarations: list[dict],
    ) -> list[dict]:
        """Build the one authoritative baseline set for a pack reload."""

        combined = list(manifest_declarations)
        seen = {
            (
                declaration["source_key"],
                declaration["relationship_type"],
                declaration["target_key"],
            )
            for declaration in combined
        }
        for corpus_spec in corpora:
            for section in corpus_spec.sections:
                for relationship in section.relationships:
                    identity = (
                        section.key,
                        str(relationship.relationship_type),
                        relationship.target_key,
                    )
                    if identity in seen:
                        raise CommandError(
                            "Pack repeats relationship edge across its manifest "
                            f"and section specs: {identity!r}."
                        )
                    seen.add(identity)
                    combined.append(
                        {
                            "source_key": section.key,
                            **relationship.as_dict(),
                        }
                    )
        return combined

    @staticmethod
    def _validate_source_hosts(manifest: dict) -> None:
        """Fail-fast on a malformed ``source_hosts`` declaration.

        ``source_hosts`` widen the SSRF allowlist for this pack's scraping
        provider(s); they are discovered from the pack directory at runtime (this
        command does NOT persist them), but validating their shape here surfaces a
        manifest typo at load time rather than as a silent ``GATE_BLOCKED_DOMAIN``
        during a later fetch.
        """
        raw = manifest.get("source_hosts")
        try:
            parse_source_hosts_declaration(raw)
        except ValueError as exc:
            raise CommandError(f"Manifest {exc}.") from exc

    @staticmethod
    def _manifest_corpora(manifest: dict) -> list:
        """Return the manifest's ``corpora`` list, distinguishing omitted (a
        taxonomy-only pack, allowed) from null/wrong-type (a malformed manifest,
        rejected) so a typo can't silently no-op."""
        raw = manifest.get("corpora")
        if raw is None:
            if "corpora" in manifest:
                raise CommandError(
                    "Manifest 'corpora' is null; provide a list or omit the key."
                )
            return []
        if not isinstance(raw, list):
            raise CommandError("Manifest 'corpora' must be a list.")
        return raw

    @staticmethod
    def _read_persona(entry: dict, pack_dir: Path) -> str | None:
        """Read the persona file a corpus entry declares (validated up-front)."""
        persona_rel = (entry or {}).get("persona")
        if not persona_rel:
            return None
        persona_path = AuthorityPackService._pack_file(
            pack_dir, persona_rel, label="persona"
        )
        return persona_path.read_text(encoding="utf-8").strip()

    @staticmethod
    def _bind_corpus_authority_prefixes(
        *,
        corpus_id: int,
        prefixes: tuple[str, ...],
        origin: str,
    ) -> None:
        """Bind explicitly declared, pack-owned namespaces to one corpus.

        The targeted archive importer deliberately trusts only prefixes linked
        to the exact destination corpus. This pack install step establishes
        that link without relaxing the importer: a pack may bind only baseline
        namespace rows created from its own mappings, and may never take a
        manual, foreign, or differently corpus-scoped row.
        """

        if not prefixes:
            return

        from opencontractserver.annotations.models import AuthorityNamespace

        namespaces = {
            namespace.prefix: namespace
            for namespace in AuthorityNamespace.objects.select_for_update().filter(
                prefix__in=prefixes
            )
        }
        missing = sorted(set(prefixes) - set(namespaces))
        if missing:
            raise CommandError(
                "Cannot bind authority prefix(es) missing from the namespace "
                f"registry: {', '.join(missing)}."
            )

        for prefix in prefixes:
            namespace = namespaces[prefix]
            if namespace.authority_corpus_id == corpus_id:
                continue
            if namespace.authority_corpus_id is not None:
                raise CommandError(
                    f"Authority prefix {prefix!r} is already bound to corpus "
                    f"{namespace.authority_corpus_id}; refusing to move it to "
                    f"corpus {corpus_id}."
                )
            if namespace.source != "baseline" or namespace.baseline_origin != origin:
                owner = (
                    "manual"
                    if namespace.source != "baseline"
                    else namespace.baseline_origin or "unattributed baseline"
                )
                raise CommandError(
                    f"Authority prefix {prefix!r} is owned by {owner!r}; "
                    f"pack {origin!r} cannot bind it."
                )

            namespace.authority_corpus_id = corpus_id
            namespace.is_global = False
            # Once linked, the namespace is corpus/bootstrap-owned rather than
            # taxonomy-baseline-owned. Mapping reloads already preserve all
            # corpus-linked rows before considering baseline origin.
            namespace.baseline_origin = None
            namespace.save(
                update_fields=[
                    "authority_corpus",
                    "is_global",
                    "baseline_origin",
                    "modified",
                ]
            )

    def _apply_corpus_overrides(
        self, corpus_id: int, entry: dict, persona_text: str | None
    ) -> None:
        """Apply the persona / model overrides a pack corpus declares (if any).

        ``bootstrap_authority_corpus`` creates the corpus but does not carry
        persona/model config, so the pack applies them here. Idempotent: skips
        the SELECT entirely when nothing is declared, and skips the UPDATE when
        every declared value already matches what is stored.
        """
        overrides: dict[str, object] = {}
        if persona_text is not None:
            overrides["corpus_agent_instructions"] = persona_text
        for fld in ("preferred_embedder", "preferred_llm"):
            if entry.get(fld):
                overrides[fld] = entry[fld]
        if entry.get("slug"):
            overrides.update(
                {
                    "slug": entry["slug"],
                    "title": entry["title"].strip(),
                    # Pack-managed authority corpora should not start an unrelated
                    # LLM branding job while deterministic seed data is loading.
                    "auto_branding_enabled": bool(
                        entry.get("auto_branding_enabled", False)
                    ),
                }
            )
            if "description" in entry:
                overrides["description"] = entry["description"].strip()
        if not overrides:
            return

        from opencontractserver.corpuses.models import Corpus

        corpus = Corpus.objects.get(pk=corpus_id)
        changed = [fld for fld, val in overrides.items() if getattr(corpus, fld) != val]
        if not changed:
            return
        for fld in changed:
            setattr(corpus, fld, overrides[fld])
        # Include "modified": Corpus.save() bumps it, but update_fields would
        # otherwise filter that write back out and leave the column stale.
        corpus.save(update_fields=[*changed, "modified"])

    @staticmethod
    def _apply_metadata_schema(corpus_id: int, schema: dict, creator) -> None:
        """Create missing fields in the existing corpus metadata subsystem."""

        from opencontractserver.corpuses.models import Corpus
        from opencontractserver.extracts.models import Column, Fieldset
        from opencontractserver.types.enums import PermissionTypes
        from opencontractserver.utils.permissioning import (
            set_permissions_for_obj_to_user,
        )

        corpus = Corpus.objects.get(pk=corpus_id)
        fieldset = Fieldset.objects.filter(corpus=corpus).first()
        if fieldset is None:
            fieldset = Fieldset.objects.create(
                name=f"{corpus.title} Authority Metadata",
                description="Shared typed metadata emitted by authority source providers.",
                corpus=corpus,
                creator=creator,
            )
            set_permissions_for_obj_to_user(
                creator, fieldset, [PermissionTypes.CRUD], is_new=True
            )
        for display_order, field_spec in enumerate(schema["fields"]):
            existing = Column.objects.filter(
                fieldset=fieldset,
                name=field_spec["name"],
                is_manual_entry=True,
            ).first()
            if existing is not None:
                if existing.data_type != field_spec["data_type"]:
                    raise CommandError(
                        f"Metadata column {field_spec['name']!r} already has "
                        f"type {existing.data_type!r}, not "
                        f"{field_spec['data_type']!r}; curator-owned schema "
                        "was not overwritten."
                    )
                continue
            column = Column.objects.create(
                fieldset=fieldset,
                name=field_spec["name"],
                data_type=field_spec["data_type"],
                validation_config=field_spec.get("validation_config", {}),
                is_manual_entry=True,
                output_type=field_spec["data_type"].lower(),
                help_text=field_spec.get("help_text"),
                display_order=display_order,
                creator=creator,
            )
            set_permissions_for_obj_to_user(
                creator, column, [PermissionTypes.CRUD], is_new=True
            )
