"""Bootstrap (or refresh) an authority corpus from a JSON section spec.

The scripted half of the authority-backfill workflow (the agent tool
``bootstrap_authority_corpus`` is the conversational half — both route
through :func:`opencontractserver.enrichment.authorities.bootstrap_authority_corpus`):

1. materialise one keyed text document per statute section,
2. optionally publish the corpus (``--public``) so every user's citations
   can resolve against it, and
3. re-link EXTERNAL law references across all corpora citing the
   bootstrapped keys (skip with ``--no-relink``).

Spec file format::

    {
      "aliases": ["Delaware General Corporation Law"],
      "sections": [
        {"key": "dgcl:145", "heading": "DGCL § 145 — Indemnification",
         "text": "...", "source_url": "https://..."},
        ...
      ]
    }

Idempotent and re-runnable: unchanged sections are skipped, changed text
version-ups the existing document.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from opencontractserver.enrichment.authorities import (
    AuthoritySection,
    bootstrap_authority_corpus,
)

User = get_user_model()


class Command(BaseCommand):
    help = (
        "Bootstrap an authority corpus (statute/regulation sections keyed by "
        "canonical key) from a JSON spec, then re-link citing corpora. "
        "Idempotent and re-runnable."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--creator", required=True, help="Username owning the authority corpus."
        )
        parser.add_argument("--title", required=True, help="Authority corpus title.")
        parser.add_argument(
            "--file",
            required=True,
            help="Path to the JSON spec ({aliases?, sections: [{key, heading, "
            "text, source_url?}]}).",
        )
        parser.add_argument(
            "--corpus-id",
            type=int,
            default=None,
            help="Refresh an existing corpus instead of get-or-create by title.",
        )
        parser.add_argument(
            "--public",
            action="store_true",
            help="Publish the corpus so the authority resolves for all users.",
        )
        parser.add_argument(
            "--no-relink",
            action="store_true",
            help="Skip the reactive re-link of corpora citing these keys.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        try:
            user = User.objects.get(username=options["creator"])
        except User.DoesNotExist as exc:
            raise CommandError(f"No user named {options['creator']!r}") from exc

        path = Path(options["file"])
        try:
            spec = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CommandError(f"Could not read spec {path}: {exc}") from exc

        raw_sections = spec.get("sections")
        if not isinstance(raw_sections, list) or not raw_sections:
            raise CommandError("Spec must contain a non-empty 'sections' list.")
        sections: list[AuthoritySection] = []
        for i, sec in enumerate(raw_sections):
            if not isinstance(sec, dict) or not all(
                isinstance(sec.get(f), str) and sec[f].strip()
                for f in ("key", "heading", "text")
            ):
                raise CommandError(
                    f"sections[{i}] must have non-empty 'key', 'heading' and "
                    "'text' (optional 'source_url')."
                )
            sections.append(
                AuthoritySection(
                    key=sec["key"].strip(),
                    heading=sec["heading"].strip(),
                    text=sec["text"],
                    source_url=sec.get("source_url"),
                )
            )

        out = bootstrap_authority_corpus(
            creator_id=user.id,
            corpus_title=options["title"],
            sections=sections,
            aliases=spec.get("aliases"),
            corpus_id=options["corpus_id"],
            make_public=options["public"],
            relink=not options["no_relink"],
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Authority corpus {out['corpus_id']} "
                f"({'created' if out['corpus_created'] else 'updated'}): "
                f"{out['documents_created']} created, "
                f"{out['documents_updated']} updated, "
                f"{out['documents_skipped']} skipped, "
                f"{out['documents_restamped']} restamped."
            )
        )
        relink = out.get("relink")
        if relink is not None:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Re-link: {relink['corpora_relinked']}/"
                    f"{relink['corpora_checked']} corpora upgraded, "
                    f"{relink['law_references_linked']} references linked, "
                    f"{relink['links_restamped']} links restamped, "
                    f"{relink['corpora_failed']} failures."
                )
            )
