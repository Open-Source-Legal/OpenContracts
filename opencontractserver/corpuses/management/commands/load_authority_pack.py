"""Load an *authority pack* — a drop-in bundle of taxonomy + content + personas.

An authority pack stands up a body-of-law family for a jurisdiction as data,
binding to the existing Authority architecture (no bespoke app). This command is
the generic loader: given a pack directory containing a ``pack.yaml`` manifest it

1. loads the pack's declarative authority-mappings YAML into ``AuthorityNamespace``
   / ``AuthorityKeyEquivalence`` (idempotent; never clobbers ``source="manual"``),
2. bootstraps one authority corpus per declared legal area from its JSON section
   spec (idempotent; unchanged sections skipped, changed text version-ups), and
3. writes each area's persona into ``Corpus.corpus_agent_instructions``.

See ``docs/architecture/proposals/0002-authority-packs.md`` and the reference
pack at ``opencontractserver/enrichment/data/authority_packs/bolivia/``.

``--path`` accepts any directory, so out-of-tree packs load identically.

Manifest (``pack.yaml``) shape::

    name: bolivia
    display_name: "Bolivia — Derecho del Estado Plurinacional"
    jurisdiction: bo
    mappings: authority_mappings.bolivia.yaml
    source_hosts:                                        # optional (scraping packs)
      - tcpbolivia.bo                                    # widens the SSRF allowlist
    corpora:
      - title: "Bolivia — Derecho Constitucional"
        spec: specs/constitucional.json
        persona: personas/constitucional.es.txt        # optional
        preferred_embedder: "..."                        # optional
        preferred_llm: "..."                             # optional

A pack may also ship its fetch provider(s) under ``<pack>/providers/*.py``; those
and ``source_hosts`` are discovered from the pack directory at runtime (the
pipeline registry / SSRF allowlist), not persisted by this command. This command
loads the *DB-side* of a pack: taxonomy, per-area corpus content, and personas.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from opencontractserver.enrichment.authorities import (
    bootstrap_authority_corpus,
    read_section_spec,
)
from opencontractserver.enrichment.constants import BASELINE_ORIGIN_CORE
from opencontractserver.enrichment.services.authority_mapping_loader import (
    AuthorityMappingLoader,
)
from opencontractserver.enrichment.services.authority_source_hosts import (
    is_valid_source_host,
)

User = get_user_model()


class Command(BaseCommand):
    help = (
        "Load an authority pack (taxonomy + per-area content + personas) from a "
        "pack directory containing a pack.yaml manifest. Idempotent and re-runnable."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--path", required=True, help="Pack directory (contains pack.yaml)."
        )
        parser.add_argument(
            "--creator", required=True, help="Username owning the seeded corpora."
        )
        parser.add_argument(
            "--public",
            action="store_true",
            help="Publish each corpus so its authorities resolve for all users.",
        )
        parser.add_argument(
            "--no-relink",
            action="store_true",
            help="Skip the reactive re-link of corpora citing the seeded keys.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        pack_dir = Path(options["path"]).resolve()
        manifest_path = pack_dir / "pack.yaml"
        if not manifest_path.is_file():
            raise CommandError(f"No pack.yaml manifest in {pack_dir}")

        try:
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise CommandError(f"Could not parse {manifest_path}: {exc}") from exc

        try:
            creator = User.objects.get(username=options["creator"])
        except User.DoesNotExist as exc:
            raise CommandError(f"No user named {options['creator']!r}") from exc

        # Validate the WHOLE pack BEFORE any DB write. ``_load_taxonomy`` commits
        # AuthorityNamespace / AuthorityKeyEquivalence rows immediately, so every
        # structural check (mappings file present, corpora shape, per-entry
        # title/spec, spec schema, persona file) must pass first — otherwise a
        # malformed corpus entry would abort with the taxonomy already durably
        # written and zero corpora created, a hybrid state the idempotent re-run
        # can't surface as "nothing happened".
        mappings_path = self._resolve_mappings_path(manifest, pack_dir)
        corpora = self._manifest_corpora(manifest)
        if not corpora and mappings_path is None:
            raise CommandError(
                "Pack manifest declares neither 'mappings' nor 'corpora' — "
                "nothing to load. Check the pack.yaml keys for typos."
            )
        if str(manifest.get("name") or pack_dir.name) == BASELINE_ORIGIN_CORE:
            raise CommandError(
                f"Pack name {BASELINE_ORIGIN_CORE!r} is reserved for the shipped "
                "core baseline (it is the namespace rows' baseline_origin stamp); "
                "rename the pack."
            )

        self._validate_source_hosts(manifest)
        if mappings_path is not None:
            # A pack's mappings YAML may carry shape_rules / abbreviations
            # (its citation vocabulary). Validate them fail-fast here rather than
            # let a malformed regex / unknown authority_type be silently skipped
            # at runtime.
            from opencontractserver.enrichment.services.authority_pack_config import (
                validate_pack_taxonomy_extensions,
            )

            try:
                validate_pack_taxonomy_extensions(mappings_path)
            except ValueError as exc:
                raise CommandError(str(exc)) from exc
        validated = [self._validate_corpus_entry(entry, pack_dir) for entry in corpora]

        # ---- DB writes start here (pack fully validated) ----------------------
        # 1) Taxonomy — namespace rows are stamped with this pack's name as
        # their baseline origin so another baseline writer (the core YAML or a
        # different pack) can never silently clobber them, and vice versa.
        if mappings_path is not None:
            origin = str(manifest.get("name") or pack_dir.name)
            self._load_taxonomy(mappings_path, origin=origin)

        # 2) Corpora + content + personas. Defer the reactive re-link until the
        # whole pack has loaded: each bootstrap_authority_corpus(relink=True)
        # scans the full CorpusReference table for its own narrow key set, so an
        # N-corpus pack would run N separate sweeps. Collect every seeded key and
        # run ONE sweep at the end.
        all_keys: list[str] = []
        for title, sections, aliases, persona_text, entry in validated:
            out = bootstrap_authority_corpus(
                creator_id=creator.id,
                corpus_title=title,
                sections=sections,
                aliases=aliases,
                make_public=options["public"],
                relink=False,
            )
            self._apply_corpus_overrides(out["corpus_id"], entry, persona_text)
            all_keys.extend(sec.key for sec in sections)

            self.stdout.write(
                self.style.SUCCESS(
                    f"corpus {out['corpus_id']} ({title}): "
                    f"{out['documents_created']} created, "
                    f"{out['documents_updated']} updated, "
                    f"{out['documents_skipped']} skipped, "
                    f"{out['documents_restamped']} restamped."
                )
            )

        # 3) One reactive re-link across every key the pack seeded.
        if all_keys and not options["no_relink"]:
            from opencontractserver.enrichment.services import EnrichmentService

            relink = EnrichmentService().relink_corpora_for_keys(all_keys)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Re-link: {relink['corpora_relinked']}/"
                    f"{relink['corpora_checked']} corpora upgraded, "
                    f"{relink['law_references_linked']} references linked, "
                    f"{relink['links_restamped']} links restamped, "
                    f"{relink['corpora_failed']} failures."
                )
            )

    @staticmethod
    def _resolve_mappings_path(manifest: dict, pack_dir: Path) -> Path | None:
        """Validate (without loading) the pack's mappings file.

        Returns the resolved path when a mappings file is declared and present,
        or ``None`` when the pack declares no taxonomy (a content-only pack,
        allowed). Raises ``CommandError`` when declared-but-missing — a
        structural error caught up-front, before :meth:`_load_taxonomy` writes
        any AuthorityNamespace rows.
        """
        mappings_rel = manifest.get("mappings")
        if not mappings_rel:
            return None
        mappings_path = pack_dir / mappings_rel
        if not mappings_path.is_file():
            raise CommandError(f"Manifest 'mappings' not found: {mappings_path}")
        return mappings_path

    def _load_taxonomy(self, mappings_path: Path, *, origin: str) -> None:
        """Load a pre-validated authority-mappings YAML into the registry."""
        summary = AuthorityMappingLoader.load_all(path=mappings_path, origin=origin)
        ns, eq = summary["namespaces"], summary["equivalences"]
        self.stdout.write(
            self.style.SUCCESS(
                f"taxonomy loaded: namespaces created={ns['created']} "
                f"updated={ns['updated']} "
                f"skipped_foreign_baseline={ns['skipped_foreign_baseline']} "
                f"total={ns['total']}; "
                f"equivalences created={eq['created']} updated={eq['updated']} "
                f"total={eq['total']}"
            )
        )
        if ns["skipped_foreign_baseline"]:
            self.stdout.write(
                self.style.WARNING(
                    f"{ns['skipped_foreign_baseline']} prefix(es) already owned "
                    "by another baseline origin were left untouched (first "
                    "writer wins) — see the log for the colliding prefixes."
                )
            )

    def _validate_corpus_entry(self, entry: dict, pack_dir: Path) -> tuple:
        """Validate one ``corpora[]`` entry without touching the database.

        Returns ``(title, sections, aliases, persona_text, entry)``. Reading the
        spec and persona here — before any corpus is bootstrapped — keeps a
        malformed entry from stranding a half-loaded pack (taxonomy + earlier
        corpora committed, this one aborted). Raises ``CommandError`` on any
        structural problem.
        """
        title = (entry or {}).get("title")
        spec_rel = (entry or {}).get("spec")
        if not title or not spec_rel:
            raise CommandError("Each corpora[] entry needs a 'title' and a 'spec'.")
        spec_path = pack_dir / spec_rel
        try:
            sections, aliases = read_section_spec(
                spec_path, label=f"corpus {title!r} spec {spec_path}"
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        persona_text = self._read_persona(entry, pack_dir)
        return title, sections, aliases, persona_text, entry

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
        if raw is None:
            return
        if not isinstance(raw, list):
            raise CommandError("Manifest 'source_hosts' must be a list of hostnames.")
        for host in raw:
            if not is_valid_source_host(str(host)):
                raise CommandError(
                    f"Manifest 'source_hosts' entry {host!r} is not a bare hostname "
                    "(e.g. 'tcpbolivia.bo') — no scheme, port, or path."
                )

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
        persona_path = pack_dir / persona_rel
        if not persona_path.is_file():
            raise CommandError(f"persona not found: {persona_path}")
        return persona_path.read_text(encoding="utf-8").strip()

    def _apply_corpus_overrides(
        self, corpus_id: int, entry: dict, persona_text: str | None
    ) -> None:
        """Apply the persona / model overrides a pack corpus declares (if any).

        ``bootstrap_authority_corpus`` creates the corpus but does not carry
        persona/model config, so the pack applies them here. Idempotent: skips
        the SELECT entirely when nothing is declared, and skips the UPDATE when
        every declared value already matches what is stored.
        """
        overrides: dict[str, str] = {}
        if persona_text is not None:
            overrides["corpus_agent_instructions"] = persona_text
        for fld in ("preferred_embedder", "preferred_llm"):
            if entry.get(fld):
                overrides[fld] = entry[fld]
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
