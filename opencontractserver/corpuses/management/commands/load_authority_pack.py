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
    corpora:
      - title: "Bolivia — Derecho Constitucional"
        spec: specs/constitucional.json
        persona: personas/constitucional.es.txt        # optional
        preferred_embedder: "..."                        # optional
        preferred_llm: "..."                             # optional
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from opencontractserver.enrichment.authorities import (
    AuthoritySection,
    bootstrap_authority_corpus,
)
from opencontractserver.enrichment.services.authority_mapping_loader import (
    AuthorityMappingLoader,
)

User = get_user_model()


def _parse_sections(spec_path: Path) -> tuple[list[AuthoritySection], list[str] | None]:
    """Read and validate a JSON section spec into ``AuthoritySection`` objects.

    Mirrors the validation in the ``bootstrap_authority`` command so a pack spec
    and a standalone spec are held to the same contract.
    """
    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CommandError(f"Could not read spec {spec_path}: {exc}") from exc

    raw_sections = spec.get("sections")
    if not isinstance(raw_sections, list) or not raw_sections:
        raise CommandError(f"{spec_path}: must contain a non-empty 'sections' list.")

    sections: list[AuthoritySection] = []
    for i, sec in enumerate(raw_sections):
        if not isinstance(sec, dict) or not all(
            isinstance(sec.get(f), str) and sec[f].strip()
            for f in ("key", "heading", "text")
        ):
            raise CommandError(
                f"{spec_path}: sections[{i}] must have non-empty 'key', 'heading' "
                "and 'text' (optional 'source_url')."
            )
        sections.append(
            AuthoritySection(
                key=sec["key"].strip(),
                heading=sec["heading"].strip(),
                text=sec["text"],
                source_url=sec.get("source_url"),
            )
        )
    return sections, spec.get("aliases")


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

        # 1) Taxonomy ------------------------------------------------------------
        mappings_rel = manifest.get("mappings")
        if mappings_rel:
            mappings_path = pack_dir / mappings_rel
            if not mappings_path.is_file():
                raise CommandError(f"Manifest 'mappings' not found: {mappings_path}")
            summary = AuthorityMappingLoader.load_all(path=mappings_path)
            ns, eq = summary["namespaces"], summary["equivalences"]
            self.stdout.write(
                self.style.SUCCESS(
                    f"taxonomy loaded: namespaces created={ns['created']} "
                    f"updated={ns['updated']} total={ns['total']}; "
                    f"equivalences created={eq['created']} updated={eq['updated']} "
                    f"total={eq['total']}"
                )
            )

        # 2) Corpora + content + personas ---------------------------------------
        corpora = manifest.get("corpora") or []
        if not isinstance(corpora, list):
            raise CommandError("Manifest 'corpora' must be a list.")

        for entry in corpora:
            title = (entry or {}).get("title")
            spec_rel = (entry or {}).get("spec")
            if not title or not spec_rel:
                raise CommandError("Each corpora[] entry needs a 'title' and a 'spec'.")
            spec_path = pack_dir / spec_rel
            if not spec_path.is_file():
                raise CommandError(f"corpus {title!r}: spec not found: {spec_path}")

            sections, aliases = _parse_sections(spec_path)
            out = bootstrap_authority_corpus(
                creator_id=creator.id,
                corpus_title=title,
                sections=sections,
                aliases=aliases,
                make_public=options["public"],
                relink=not options["no_relink"],
            )
            self._apply_corpus_overrides(out["corpus_id"], entry, pack_dir)

            self.stdout.write(
                self.style.SUCCESS(
                    f"corpus {out['corpus_id']} ({title}): "
                    f"{out['documents_created']} created, "
                    f"{out['documents_updated']} updated, "
                    f"{out['documents_skipped']} skipped."
                )
            )

    def _apply_corpus_overrides(
        self, corpus_id: int, entry: dict, pack_dir: Path
    ) -> None:
        """Set the persona / model overrides a pack corpus declares (if any).

        ``bootstrap_authority_corpus`` creates the corpus but does not carry
        persona/model config, so the pack applies them here.
        """
        from opencontractserver.corpuses.models import Corpus

        fields: list[str] = []
        corpus = Corpus.objects.get(pk=corpus_id)

        persona_rel = entry.get("persona")
        if persona_rel:
            persona_path = pack_dir / persona_rel
            if not persona_path.is_file():
                raise CommandError(f"persona not found: {persona_path}")
            corpus.corpus_agent_instructions = persona_path.read_text(
                encoding="utf-8"
            ).strip()
            fields.append("corpus_agent_instructions")

        for fld in ("preferred_embedder", "preferred_llm"):
            if entry.get(fld):
                setattr(corpus, fld, entry[fld])
                fields.append(fld)

        if fields:
            corpus.save(update_fields=fields)
