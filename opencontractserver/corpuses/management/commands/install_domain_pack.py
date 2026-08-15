"""Install a DOMAIN pack: base packs plus the wiring that belongs to none of them.

    python manage.py install_domain_pack us-export-control --creator admin --public
    python manage.py install_domain_pack us-export-control --check
    python manage.py install_domain_pack --list

A **base pack** is one body of law — one publisher, one update cadence, one
provenance story, one approval status. A **domain pack** composes base packs and
supplies the parts that exist only because they are installed together:

    * a CorpusGroup, so cross-corpus retrieval reaches every member;
    * an orchestrator AgentConfiguration bound to that group, carrying the
      tools and the persona describing how those bodies of law interact;
    * cross-pack equivalences — citation forms owned by one pack that must fold
      onto keys owned by another.

Without this layer a multi-corpus assembly installs "successfully" and lands
inert: its content is present and correct, and everything except the corpora a
consuming document happens to cite is unreachable.

The install contract (C1-C7) is defined in the registry repo's DOMAIN_PACKS.md
and is the shared spec both sides build to. The assertions this command owns:

    C1 Completeness   — every required base pack installs, or we fail.
    C2 Reachability   — every contributed corpus joins the group; exceeding the
                        platform's group cap is an ERROR, never a silent
                        truncation.
    C3 Addressability — the orchestrator exists, is bound, and has its tools.
    C5 Honesty        — success is not printable while any assertion is unmet.
    C6 Idempotence    — re-running converges; nothing is duplicated.

C4 (every equivalence target resolves) and C7 (a domain pack introduces no
authority of its own) are decidable from the files and are enforced by the
registry's ``scripts/validate_domain.py``; both are re-checked here because an
installer must not trust its input.
"""

from __future__ import annotations

import re
import tarfile
import tempfile
from pathlib import Path

import yaml
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from opencontractserver.constants.tools import MULTI_CORPUS_SEARCH_MAX_CORPORA
from opencontractserver.corpuses.management.commands.install_authority_pack import (
    MAX_EXTRACTED_BYTES,
    _download_tarball,
    _tarball_url,
    _top_prefix,
)

DOMAIN_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
DOMAINS_DIR = "domains"


class Command(BaseCommand):
    help = (
        "Install a domain pack: its required base packs, a corpus group, an "
        "orchestrator agent, and cross-pack equivalences."
    )

    def add_arguments(self, parser):
        parser.add_argument("domain", nargs="?", help="Domain pack name.")
        parser.add_argument(
            "--list",
            action="store_true",
            dest="list_domains",
            help="List domain packs available in the registry and exit.",
        )
        parser.add_argument("--repo", help="Registry repo URL.")
        parser.add_argument("--ref", default="main", help="Branch, tag or commit.")
        parser.add_argument("--tarball", help="Local registry tarball; skips fetch.")
        parser.add_argument("--creator", help="Username owning the seeded corpora.")
        parser.add_argument("--public", action="store_true")
        parser.add_argument(
            "--check",
            action="store_true",
            help="Fetch and report the plan; write nothing.",
        )

    # ------------------------------------------------------------------ #
    # fetch
    # ------------------------------------------------------------------ #
    def _stage(self, options, tmp_path: Path) -> Path:
        """Extract the whole registry. A domain needs its base packs too."""
        if options["tarball"]:
            tarball = Path(options["tarball"])
            if not tarball.is_file():
                raise CommandError(f"--tarball not found: {tarball}")
        else:
            tarball = tmp_path / "registry.tar.gz"
            url = _tarball_url(
                options["repo"] or settings.AUTHORITY_PACK_REGISTRY_URL,
                options["ref"],
            )
            self.stdout.write(f"Fetching {url}")
            _download_tarball(url, tarball)

        staged = tmp_path / "staged"
        with tarfile.open(tarball, "r:gz") as tar:
            prefix = _top_prefix(tar.getnames())
            extracted = 0
            for member in tar.getmembers():
                if not member.name.startswith(prefix + "/"):
                    continue
                extracted += member.size
                if extracted > MAX_EXTRACTED_BYTES:
                    raise CommandError(
                        f"Registry expands past {MAX_EXTRACTED_BYTES} bytes; refusing"
                    )
                member.name = member.name[len(prefix) + 1 :]
                tar.extract(member, path=staged, filter="data")
        return staged

    # ------------------------------------------------------------------ #
    def handle(self, *args, **options):
        domain = options["domain"]
        if not options["list_domains"] and not domain:
            raise CommandError("Provide a domain name, or --list.")
        if domain and not DOMAIN_NAME_RE.match(domain):
            raise CommandError(f"Invalid domain name {domain!r}")

        with tempfile.TemporaryDirectory(prefix="domain-pack-") as tmp:
            staged = self._stage(options, Path(tmp))

            available = (
                sorted(
                    p.parent.name for p in (staged / DOMAINS_DIR).glob("*/domain.yaml")
                )
                if (staged / DOMAINS_DIR).is_dir()
                else []
            )

            if options["list_domains"]:
                for name in available or ["(none)"]:
                    self.stdout.write(name)
                return

            if domain not in available:
                raise CommandError(
                    f"Domain {domain!r} not found in registry "
                    f"(available: {', '.join(available) or 'none'})"
                )

            domain_dir = staged / DOMAINS_DIR / domain
            manifest = (
                yaml.safe_load((domain_dir / "domain.yaml").read_text(encoding="utf-8"))
                or {}
            )

            # C7 — refuse authority smuggled into the composition layer. The
            # validator checks this too; an installer must not trust its input.
            if manifest.get("prefixes") or (domain_dir / "specs").exists():
                raise CommandError(
                    "C7: domain pack declares prefixes or ships specs/. Authority "
                    "text belongs to a base pack, where its provenance and "
                    "approval status live."
                )

            required = [
                str(r["pack"])
                for r in (manifest.get("requires") or [])
                if isinstance(r, dict) and r.get("pack")
            ]
            if not required:
                raise CommandError("domain.yaml declares no `requires`")

            # C1 — every required base pack must be present BEFORE anything is
            # written. A partial install that reports success is the failure
            # this whole layer exists to prevent.
            missing = [p for p in required if not (staged / p / "pack.yaml").is_file()]
            if missing:
                raise CommandError(
                    f"C1: required base pack(s) not in registry: {', '.join(missing)}"
                )

            self.stdout.write(f"\nDomain: {manifest.get('title') or domain}")
            self.stdout.write(f"  requires: {', '.join(required)}")

            if options["check"]:
                self._report_plan(manifest, staged, required)
                self.stdout.write("\nNo changes were written.")
                return

            if not options["creator"]:
                raise CommandError("--creator is required to install")

            # --- base packs first ---------------------------------------- #
            for pack_name in required:
                self.stdout.write(f"\n--- base pack: {pack_name}")
                call_command(
                    "load_authority_pack",
                    path=str(staged / pack_name),
                    creator=options["creator"],
                    public=options["public"],
                )

            self._wire(manifest, staged, required, options)

    # ------------------------------------------------------------------ #
    def _report_plan(self, manifest, staged: Path, required: list[str]) -> None:
        group = manifest.get("corpus_group") or {}
        members, excluded = self._member_slugs(staged, required, group)
        self.stdout.write(
            f"  corpus group: {group.get('slug')} " f"({len(members)} member corpora)"
        )
        if excluded:
            self.stdout.write(
                f"    excluded (reachable without the group): "
                f"{', '.join(sorted(excluded))}"
            )
        if len(members) > MULTI_CORPUS_SEARCH_MAX_CORPORA:
            self.stdout.write(
                self.style.ERROR(
                    f"  C2: {len(members)} corpora exceeds "
                    f"MULTI_CORPUS_SEARCH_MAX_CORPORA={MULTI_CORPUS_SEARCH_MAX_CORPORA}; "
                    "cross-corpus search would silently drop the overflow"
                )
            )
        orch = manifest.get("orchestrator") or {}
        self.stdout.write(f"  orchestrator tools: {', '.join(orch.get('tools') or [])}")
        self.stdout.write(
            f"  cross-pack equivalences: " f"{len(manifest.get('equivalences') or [])}"
        )

    def _member_slugs(self, staged: Path, required: list[str], group: dict):
        """Corpus slugs every required base pack contributes, minus exclusions."""
        excluded = {str(s) for s in (group.get("exclude_corpora") or [])}
        members: list[str] = []
        for pack_name in required:
            data = (
                yaml.safe_load(
                    (staged / pack_name / "pack.yaml").read_text(encoding="utf-8")
                )
                or {}
            )
            for corpus in data.get("corpora") or []:
                slug = str(corpus.get("slug") or "")
                if slug and slug not in excluded:
                    members.append(slug)
        return members, excluded

    # ------------------------------------------------------------------ #
    @transaction.atomic
    def _wire(self, manifest, staged: Path, required: list[str], options) -> None:
        """Create the group, the orchestrator and the cross-pack equivalences."""
        from opencontractserver.agents.models import AgentConfiguration
        from opencontractserver.annotations.models import AuthorityKeyEquivalence
        from opencontractserver.corpuses.models import Corpus, CorpusGroup

        user = get_user_model().objects.get(username=options["creator"])
        unmet: list[str] = []

        # --- C2 reachability ------------------------------------------- #
        group_spec = manifest.get("corpus_group") or {}
        wanted, excluded = self._member_slugs(staged, required, group_spec)
        corpora = list(Corpus.objects.filter(slug__in=wanted))
        found = {c.slug for c in corpora}
        for slug in wanted:
            if slug not in found:
                unmet.append(f"C2: corpus {slug!r} was not created by its base pack")

        if len(corpora) > MULTI_CORPUS_SEARCH_MAX_CORPORA:
            raise CommandError(
                f"C2: the group would hold {len(corpora)} corpora but "
                f"MULTI_CORPUS_SEARCH_MAX_CORPORA={MULTI_CORPUS_SEARCH_MAX_CORPORA}. "
                "search_across_corpora would search the first N by id and silently "
                "drop the rest — which drops the most recently added corpora. "
                "Reduce the group with corpus_group.exclude_corpora, or raise the cap."
            )

        group, created = CorpusGroup.objects.get_or_create(
            slug=str(group_spec.get("slug")),
            defaults={
                "title": group_spec.get("title") or str(group_spec.get("slug")),
                "creator": user,
                "is_public": bool(options["public"]),
            },
        )
        group.corpora.set(corpora)  # C6: set(), not add()
        self.stdout.write(
            f"\ncorpus group {group.slug!r}: {'created' if created else 'updated'}, "
            f"{group.corpora.count()} member corpora"
            + (f" ({len(excluded)} excluded)" if excluded else "")
        )

        # --- C3 addressability ------------------------------------------ #
        orch = manifest.get("orchestrator") or {}
        rel = orch.get("instructions_file")
        instructions = ""
        if rel:
            path = (staged / DOMAINS_DIR / manifest["name"] / str(rel)).resolve()
            root = (staged / DOMAINS_DIR / manifest["name"]).resolve()
            if not str(path).startswith(str(root) + "/") or not path.is_file():
                unmet.append(f"C3: orchestrator instructions_file unreadable: {rel}")
            else:
                instructions = path.read_text(encoding="utf-8")
        tools = [str(t) for t in (orch.get("tools") or [])]

        # The tool takes the group slug as a REQUIRED argument, so an agent that
        # is never told the slug cannot call it — and that failure is
        # indistinguishable from the model choosing not to.
        if "search_across_corpora" in tools and group.slug not in instructions:
            unmet.append(
                f"C3: orchestrator declares search_across_corpora but its "
                f"instructions never name the group slug {group.slug!r}"
            )

        agent, agent_created = AgentConfiguration.objects.get_or_create(
            slug=f"{manifest['name']}-orchestrator",
            defaults={
                "name": f"{manifest.get('title') or manifest['name']} orchestrator",
                "creator": user,
                "is_public": bool(options["public"]),
            },
        )
        agent.system_instructions = instructions
        agent.available_tools = tools
        if orch.get("preferred_llm"):
            agent.preferred_llm = str(orch["preferred_llm"])
        agent.save()
        group.default_agent = agent
        group.save(update_fields=["default_agent"])
        self.stdout.write(
            f"orchestrator {agent.slug!r}: {'created' if agent_created else 'updated'}, "
            f"tools={tools}, {len(instructions):,} chars of instructions"
        )

        # --- C4 resolution ----------------------------------------------- #
        rows = manifest.get("equivalences") or []
        written = 0
        for row in rows:
            frm, to = str(row.get("from_key", "")), str(row.get("to_key", ""))
            if not frm or not to:
                unmet.append(f"C4: malformed equivalence row {row!r}")
                continue
            AuthorityKeyEquivalence.objects.update_or_create(
                from_key=frm,
                # "baseline" = shipped, loader-managed — the same class as a
                # base pack's own rows, which is what these are.
                defaults={
                    "to_key": to,
                    "source": "baseline",
                    "note": str(row.get("note") or "")[:255],
                    "created_by": user,
                },
            )
            written += 1
        self.stdout.write(f"cross-pack equivalences: {written} row(s) converged")

        # --- C5 honesty --------------------------------------------------- #
        if unmet:
            for item in unmet:
                self.stdout.write(self.style.ERROR(f"  UNMET {item}"))
            raise CommandError(
                f"{len(unmet)} install-contract assertion(s) unmet — rolling back. "
                "A domain pack that installs partially is the failure this layer "
                "exists to prevent.\n  " + "\n  ".join(unmet)
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDomain {manifest['name']!r} installed: "
                f"{len(required)} base pack(s), {group.corpora.count()} corpora in "
                f"group {group.slug!r}, orchestrator {agent.slug!r}, {written} "
                "cross-pack equivalence(s)."
            )
        )
