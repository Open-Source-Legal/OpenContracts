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

import json
import tarfile
import tempfile
from io import StringIO
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
    PACK_NAME_RE,
    _download_tarball,
    _tarball_url,
    _top_prefix,
    materialise_pack,
)

# A domain pack name and a base pack name have the same grammar and the same
# reason for it — both become path components. One constant, imported, rather
# than two identical regexes that could drift apart.
DOMAIN_NAME_RE = PACK_NAME_RE
DOMAINS_DIR = "domains"

# Tools a domain pack may grant its orchestrator. Closed on purpose, and
# mirrored in the registry's validate_domain.py: C3 says an install FAILS if the
# platform cannot grant a declared tool, and the alternative to failing is an
# agent that silently never calls a misspelled tool — indistinguishable from the
# model choosing not to.
GRANTABLE_TOOLS = frozenset(
    {
        "search_across_corpora",
        "ask_document",
        "search_exact_text",
    }
)


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

            # `domain` came off the command line and is regex-checked; the
            # manifest's own `name` is registry-supplied and was not. It is used
            # to build the orchestrator slug AND the path the instructions are
            # read from, so an unchecked value like "../../../../etc" resolves
            # that read outside the pack — and the traversal guard below cannot
            # catch it, because the guard derives its root from the same field
            # and moves with the attack. A tarball is attacker-shaped input.
            name = str(manifest.get("name") or "")
            if not DOMAIN_NAME_RE.match(name):
                raise CommandError(
                    f"domain.yaml `name` {name!r} must be a slug of the same form "
                    "as the directory name"
                )
            if name != domain:
                raise CommandError(
                    f"domain.yaml `name` {name!r} does not match its directory "
                    f"{domain!r}"
                )

            # C7 — refuse authority smuggled into the composition layer. The
            # validator checks this too; an installer must not trust its input.
            if manifest.get("prefixes") or (domain_dir / "specs").exists():
                raise CommandError(
                    "C7: domain pack declares prefixes or ships specs/. Authority "
                    "text belongs to a base pack, where its provenance and "
                    "approval status live."
                )

            # Deduplicated, order preserved. `pack_dirs` below is a dict and
            # would dedupe silently while the install loop iterated the raw
            # list — so a domain pack naming the same base pack twice would
            # install it, then fail on the second pass looking for a directory
            # that had already been moved, with the first pack's corpora already
            # committed. That is the partial install C1 exists to prevent.
            required: list[str] = []
            for entry in manifest.get("requires") or []:
                if not isinstance(entry, dict) or not entry.get("pack"):
                    raise CommandError(f"malformed `requires` entry: {entry!r}")
                name_ = str(entry["pack"])
                # Same reasoning as the `name` check above, and the same class
                # of bug: this value becomes a path component, and one of its
                # uses is an rmtree. Validated here as well as in
                # `materialise_pack` so the refusal names the manifest field.
                if not PACK_NAME_RE.match(name_):
                    raise CommandError(
                        f"requires[].pack {name_!r} must be a plain slug — it is "
                        "used as a filesystem path component"
                    )
                if name_ not in required:
                    required.append(name_)
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

            # Where each pack's files live. Rebound to the install dir once the
            # packs are materialised, because materialising MOVES them out of the
            # extraction tree and every later read would otherwise hit a path
            # that no longer exists.
            pack_dirs = {name: staged / name for name in required}

            self.stdout.write(f"\nDomain: {manifest.get('title') or domain}")
            self.stdout.write(f"  requires: {', '.join(required)}")

            # Everything decidable from the FILES is decided before anything is
            # written, for --check and for a real install alike. A preflight that
            # only runs under --check is a preflight the install path never gets.
            violations = self._preflight(manifest, pack_dirs)
            violations += self._preflight_base_packs(pack_dirs, options)

            if options["check"]:
                self._report_plan(manifest, pack_dirs)
                if violations:
                    # Exit non-zero. A --check that prints an error and returns
                    # success is worse than no --check: it is a gate that reports
                    # "fine" for the failure it exists to find.
                    raise CommandError(
                        f"{len(violations)} install-contract assertion(s) would be "
                        "unmet. No changes were written.\n  " + "\n  ".join(violations)
                    )
                self.stdout.write("\nNo changes were written.")
                return

            if violations:
                raise CommandError(
                    f"{len(violations)} install-contract assertion(s) unmet; "
                    "refusing to install. Nothing was written.\n  "
                    + "\n  ".join(violations)
                )

            if not options["creator"]:
                raise CommandError("--creator is required to install")

            # --- base packs first ---------------------------------------- #
            #
            # Each is MATERIALISED into the install dir and then loaded from
            # there, exactly as `install_authority_pack` does — never loaded
            # straight from the extraction temp dir. The database gets the
            # sections and the taxonomy either way, but the pack's source_hosts,
            # shape_rules, abbreviations and in-pack providers are read from the
            # directory at runtime, and the temp dir is gone by then. Loading a
            # pack is not installing it.
            for position, pack_name in enumerate(required, start=1):
                self.stdout.write(f"\n--- base pack: {pack_name}")
                try:
                    dest = materialise_pack(staged / pack_name, pack_name, self.stdout)
                    pack_dirs[pack_name] = dest
                    call_command(
                        "load_authority_pack",
                        path=str(dest),
                        creator=options["creator"],
                        public=options["public"],
                        stdout=self.stdout,
                    )
                except CommandError as exc:
                    # Each base pack loads in its own transaction, so the ones
                    # before this are installed and stay. Say so — the bare
                    # error from load_authority_pack leaves the operator unable
                    # to tell a partial install from a no-op, and the install is
                    # idempotent (C6) so a re-run recovers.
                    done = ", ".join(required[: position - 1]) or "none"
                    raise CommandError(
                        f"base pack {pack_name!r} ({position} of {len(required)}) "
                        f"failed to install: {exc}\n"
                        f"  already installed and left in place: {done}\n"
                        "  the wiring was not created; re-run once the pack is "
                        "corrected — installs converge."
                    ) from exc

            self._wire(manifest, pack_dirs, domain_dir, options)

            self.stdout.write(
                self.style.WARNING(
                    "\nRestart web/worker processes to pick up the base packs' "
                    "grammar-tier taxonomy extensions and in-pack providers "
                    "(pack config is cached per process)."
                )
            )

    # ------------------------------------------------------------------ #
    def _report_plan(self, manifest, pack_dirs: dict[str, Path]) -> None:
        group = manifest.get("corpus_group") or {}
        members, excluded = self._member_slugs(pack_dirs, group)
        self.stdout.write(
            f"  corpus group: {group.get('slug')} " f"({len(members)} member corpora)"
        )
        if excluded:
            self.stdout.write(
                f"    excluded (reachable without the group): "
                f"{', '.join(sorted(excluded))}"
            )
        orch = manifest.get("orchestrator") or {}
        self.stdout.write(f"  orchestrator tools: {', '.join(orch.get('tools') or [])}")
        self.stdout.write(
            f"  cross-pack equivalences: " f"{len(manifest.get('equivalences') or [])}"
        )

    def _member_slugs(self, pack_dirs: dict[str, Path], group: dict):
        """Corpus slugs every required base pack contributes, minus exclusions."""
        excluded = {str(s) for s in (group.get("exclude_corpora") or [])}
        members: list[str] = []
        for pack_dir in pack_dirs.values():
            data = (
                yaml.safe_load((pack_dir / "pack.yaml").read_text(encoding="utf-8"))
                or {}
            )
            for corpus in data.get("corpora") or []:
                if not isinstance(corpus, dict):
                    raise CommandError(
                        f"malformed corpus entry in pack.yaml: {corpus!r}"
                    )
                slug = str(corpus.get("slug") or "")
                if slug and slug not in excluded:
                    members.append(slug)
        return members, excluded

    def _section_keys(self, pack_dirs: dict[str, Path]) -> set[str]:
        """Every authority key the required base packs actually define."""
        keys: set[str] = set()
        for pack_dir in pack_dirs.values():
            manifest = (
                yaml.safe_load((pack_dir / "pack.yaml").read_text(encoding="utf-8"))
                or {}
            )
            for corpus in manifest.get("corpora") or []:
                if not isinstance(corpus, dict):
                    raise CommandError(
                        f"malformed corpus entry in pack.yaml: {corpus!r}"
                    )
                spec_rel = corpus.get("spec")
                if not spec_rel:
                    continue
                spec_path = pack_dir / str(spec_rel)
                if not spec_path.is_file():
                    continue
                try:
                    spec = json.loads(spec_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    continue
                for section in spec.get("sections") or []:
                    key = section.get("key")
                    if key:
                        keys.add(str(key))
        return keys

    # ------------------------------------------------------------------ #
    def _preflight_base_packs(self, pack_dirs: dict[str, Path], options) -> list[str]:
        """C1 — every required base pack must *install*, not merely be present.

        Checking that ``pack.yaml`` exists is not what C1 says. A pack that is
        present but invalid passes that check, fails partway down the install
        loop, and leaves packs 1..N-1 written — the partial install that reports
        nothing useful, which is the failure this layer exists to prevent.

        This is cheap enough that there is no tradeoff to weigh: measured at
        ~4s of work for a 978-section pack against ~0.6s per section to install
        it, so preflighting every pack costs well under 1% of the install it
        guards. `load_authority_pack --check` writes nothing and raises on an
        invalid pack.
        """
        if not options["creator"]:
            # --check without a creator: the plan is still worth printing, but
            # say plainly that this assertion was not evaluated rather than let
            # a clean run imply it passed.
            self.stdout.write(
                "  (C1 pack validity not checked — pass --creator to preflight "
                "each base pack)"
            )
            return []

        violations: list[str] = []
        for pack_name, pack_dir in pack_dirs.items():
            sink = StringIO()
            try:
                call_command(
                    "load_authority_pack",
                    path=str(pack_dir),
                    creator=options["creator"],
                    check=True,
                    stdout=sink,
                )
            except CommandError as exc:
                violations.append(
                    f"C1: base pack {pack_name!r} would not install: {exc}"
                )
        return violations

    # ------------------------------------------------------------------ #
    def _preflight(self, manifest, pack_dirs: dict[str, Path]) -> list[str]:
        """Contract assertions decidable from the FILES, before anything is written.

        These used to be split: C2 was reported by ``--check`` as styled text
        that did not affect the exit code, and C4 was named in this module's
        docstring but never actually checked. Both are the same defect in
        different clothes — a gate that cannot fail. They are one list now, and
        both entry points refuse on it.
        """
        violations: list[str] = []

        # C2 — the group must exist and must fit the platform's search cap.
        # An absent slug used to reach `get_or_create(slug=str(None))` and
        # create a group literally named "None", which every malformed domain
        # pack would then share.
        group = manifest.get("corpus_group") or {}
        group_slug = str(group.get("slug") or "")
        if not group_slug:
            violations.append(
                "C2: domain.yaml declares no corpus_group.slug — without a group "
                "there is no cross-corpus retrieval, which is the whole point of "
                "the layer"
            )
        members, _ = self._member_slugs(pack_dirs, group)
        if len(members) > MULTI_CORPUS_SEARCH_MAX_CORPORA:
            violations.append(
                f"C2: the group would hold {len(members)} corpora but "
                f"MULTI_CORPUS_SEARCH_MAX_CORPORA={MULTI_CORPUS_SEARCH_MAX_CORPORA}. "
                "search_across_corpora would search the first N by id and silently "
                "drop the rest — which drops the most recently added corpora. "
                "Reduce the group with corpus_group.exclude_corpora, or raise the cap."
            )

        # C3 — a tool the platform cannot grant is a tool the agent will never
        # call, which is indistinguishable from the model declining to.
        tools = [
            str(t) for t in ((manifest.get("orchestrator") or {}).get("tools") or [])
        ]
        for tool in tools:
            if tool not in GRANTABLE_TOOLS:
                violations.append(
                    f"C3: orchestrator declares tool {tool!r}, which this platform "
                    f"cannot grant (known: {', '.join(sorted(GRANTABLE_TOOLS))})"
                )

        # C4 — every equivalence target must name a section that exists. A row
        # pointing at nothing is a silent no-op after install: the citation still
        # extracts, still folds, and still resolves to nothing.
        keys = self._section_keys(pack_dirs)
        for row in manifest.get("equivalences") or []:
            if not isinstance(row, dict):
                violations.append(f"C4: malformed equivalence row {row!r}")
                continue
            frm, to = str(row.get("from_key", "")), str(row.get("to_key", ""))
            if not frm or not to:
                violations.append(f"C4: malformed equivalence row {row!r}")
                continue
            if frm == to:
                violations.append(f"C4: equivalence row maps {frm!r} onto itself")
            elif to not in keys:
                violations.append(
                    f"C4: equivalence to_key {to!r} names no section in any "
                    "required base pack"
                )
        return violations

    # ------------------------------------------------------------------ #
    @transaction.atomic
    def _wire(
        self, manifest, pack_dirs: dict[str, Path], domain_dir: Path, options
    ) -> None:
        """Create the group, the orchestrator and the cross-pack equivalences."""
        from opencontractserver.agents.models import AgentConfiguration
        from opencontractserver.corpuses.models import Corpus, CorpusGroup
        from opencontractserver.enrichment.services.authority_equivalence_ingest import (
            CREATED,
            SKIPPED_INVALID,
            SKIPPED_OWNED,
            upsert_equivalence,
        )

        user = get_user_model().objects.get(username=options["creator"])
        unmet: list[str] = []

        # --- C2 reachability ------------------------------------------- #
        group_spec = manifest.get("corpus_group") or {}
        wanted, excluded = self._member_slugs(pack_dirs, group_spec)
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
            # `domain_dir` is built from the command-line domain name, which is
            # regex-checked and matched against the manifest's own `name` in
            # handle(). Deriving the root from the manifest here would let the
            # manifest move the root and the guard together.
            root = domain_dir.resolve()
            path = (root / str(rel)).resolve()
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

        # --- cross-pack equivalences -------------------------------------- #
        #
        # Written through the shared upsert rather than the ORM directly. That
        # is not a style preference — a bare `update_or_create(from_key=...)`
        # was wrong three ways against this model:
        #
        #   * the unique constraint is on the PAIR (from_key, to_key), so one
        #     from_key may legitimately have several targets. Keying the upsert
        #     on from_key alone rewrites the target of an existing row, and
        #     raises MultipleObjectsReturned once a second target exists.
        #   * it bypasses the source-ownership guard, so a curator's `manual`
        #     row is silently overwritten AND relabelled `baseline` — the exact
        #     clobber the guard exists to prevent.
        #   * it is the filter-then-write race the shared upsert holds a
        #     select_for_update against.
        #
        # C4 (every to_key resolves) is checked in _preflight, before anything
        # here has run.
        rows = manifest.get("equivalences") or []
        created_rows = converged = skipped_owned = 0
        for row in rows:
            outcome = upsert_equivalence(
                from_key=str(row["from_key"]),
                to_key=str(row["to_key"]),
                # "baseline" = shipped, loader-managed — the same class as a
                # base pack's own rows, which is what these are.
                source="baseline",
                confidence=1.0,
                note=str(row.get("note") or "") or None,
            )
            if outcome == CREATED:
                created_rows += 1
                converged += 1
            elif outcome == SKIPPED_OWNED:
                skipped_owned += 1
            elif outcome == SKIPPED_INVALID:
                # _preflight rejects malformed and self-mapping rows, so this is
                # unreachable — counted as unmet rather than as converged so a
                # divergence between the two validators can never be reported as
                # a successful install.
                unmet.append(
                    f"C4: equivalence row {row['from_key']} -> {row['to_key']} "
                    "was rejected by the shared upsert after passing preflight"
                )
            else:
                converged += 1
        self.stdout.write(
            f"cross-pack equivalences: {converged} row(s) converged "
            f"({created_rows} created)"
            + (
                f", {skipped_owned} left to their existing owner"
                if skipped_owned
                else ""
            )
        )

        # --- C5 honesty --------------------------------------------------- #
        if unmet:
            for item in unmet:
                self.stdout.write(self.style.ERROR(f"  UNMET {item}"))
            raise CommandError(
                f"{len(unmet)} install-contract assertion(s) unmet — rolling back "
                "the wiring. The base packs were installed in their own "
                "transactions and remain; re-run once the domain pack is "
                "corrected.\n  " + "\n  ".join(unmet)
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDomain {manifest['name']!r} installed: "
                f"{len(pack_dirs)} base pack(s), {group.corpora.count()} corpora in "
                f"group {group.slug!r}, orchestrator {agent.slug!r}, {converged} "
                "cross-pack equivalence(s)."
            )
        )
