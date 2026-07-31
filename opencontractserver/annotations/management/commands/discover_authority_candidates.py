"""Operator entrypoint for authority DISCOVERY (Phase 2, issue #2054).

Crawls a publisher's index/listing page(s) for candidate documents nobody has
cited yet, and seeds ``AuthorityFrontier`` so the existing discovery/crawl
runtime can pick them up later (see
``AuthorityFrontierService.seed_from_discovery``). This is a deliberately thin,
backend-only surface — no admin UI (explicitly out of scope for issue #2054); a
superuser-invocable management command (or the Django shell, calling the same
service methods directly) is the intended operator surface.

See ``docs/architecture/proposals/0002-authority-packs.md`` §7 and
``docs/guides/authoring-authority-packs.md``.

Example — crawl a listing page whose rows look like
``<a href="/doc/2024-1234">Gaceta Oficial 2024-1234</a>``::

    manage.py discover_authority_candidates \\
      --index-url https://example.gov/gaceta/listing \\
      --link-pattern '<a href="(?P<url>/doc/(?P<id>[^"]+))">(?P<title>[^<]+)</a>' \\
      --canonical-key-template '{prefix}:{id}' \\
      --prefix bo-gaceta \\
      --dry-run

``--dry-run`` prints discovered candidates without writing to the frontier —
useful for iterating on ``--link-pattern`` against a real index page before
committing. Every fetch is SSRF-gated (``opencontractserver/utils/safe_http.py``)
regardless of ``--dry-run``: an index URL whose host is not on the effective
allowlist is rejected before any request is made.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError

from opencontractserver.enrichment.constants import DISCOVERY_DEFAULT_MAX_CANDIDATES
from opencontractserver.enrichment.services.authority_frontier_service import (
    AuthorityFrontierService,
)
from opencontractserver.pipeline.authority_discovery_providers.listing_index_provider import (
    ListingIndexDiscoveryProvider,
    ListingIndexRule,
)
from opencontractserver.pipeline.registry import (
    get_all_authority_discovery_providers_cached,
)


class Command(BaseCommand):
    help = (
        "Crawl a publisher's index/listing page(s) for undiscovered authority "
        "candidates and seed AuthorityFrontier (Phase 2, issue #2054)."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--index-url",
            action="append",
            required=True,
            dest="index_urls",
            help="Index/listing page URL to crawl. Repeatable for pagination.",
        )
        parser.add_argument(
            "--link-pattern",
            help=(
                "Regex applied to the fetched index page HTML (re.finditer). "
                "MUST define a named group 'url'; MAY define others (e.g. 'id', "
                "'title') consumed by --canonical-key-template. Required unless "
                "--provider is supplied."
            ),
        )
        parser.add_argument(
            "--canonical-key-template",
            help="str.format template consuming 'prefix' + the regex's named "
            "groups, e.g. '{prefix}:{id}'. Required unless --provider is supplied.",
        )
        parser.add_argument(
            "--prefix",
            help=(
                "canonical_key prefix/authority for the config-driven listing "
                "provider, e.g. 'bo-gaceta'. Required unless --provider is supplied."
            ),
        )
        parser.add_argument(
            "--provider",
            help=(
                "Registered BaseAuthorityDiscoveryProvider class name or full class "
                "path. Selects an in-pack/core bespoke parser instead of requiring "
                "--link-pattern/--canonical-key-template/--prefix."
            ),
        )
        parser.add_argument(
            "--max-candidates",
            type=int,
            default=DISCOVERY_DEFAULT_MAX_CANDIDATES,
            help=f"Per-run candidate cap (default {DISCOVERY_DEFAULT_MAX_CANDIDATES}).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print discovered candidates without seeding AuthorityFrontier.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        provider_name = (options.get("provider") or "").strip()
        discover_kwargs: dict[str, object] = {}
        if provider_name:
            rule_values = [
                options.get("link_pattern"),
                options.get("canonical_key_template"),
                options.get("prefix"),
            ]
            if any(rule_values):
                raise CommandError(
                    "--provider cannot be combined with --link-pattern, "
                    "--canonical-key-template, or --prefix."
                )
            matches = [
                definition
                for definition in get_all_authority_discovery_providers_cached()
                if provider_name in {definition.name, definition.class_name}
            ]
            if not matches:
                raise CommandError(
                    f"Unknown authority discovery provider {provider_name!r}."
                )
            if len(matches) > 1:
                full_names = ", ".join(sorted(d.class_name for d in matches))
                raise CommandError(
                    f"Ambiguous authority discovery provider {provider_name!r}; "
                    f"use a full class path ({full_names})."
                )
            provider_class = matches[0].component_class
            if provider_class is None:  # pragma: no cover - registry invariant
                raise CommandError(
                    f"Authority discovery provider {provider_name!r} is unavailable."
                )
            provider = provider_class()
        else:
            missing = [
                option
                for option in ("link_pattern", "canonical_key_template", "prefix")
                if not options.get(option)
            ]
            if missing:
                rendered = ", ".join(f"--{name.replace('_', '-')}" for name in missing)
                raise CommandError(
                    f"{rendered} required when --provider is not supplied."
                )
            try:
                discover_kwargs["rule"] = ListingIndexRule(
                    link_pattern=options["link_pattern"],
                    canonical_key_template=options["canonical_key_template"],
                    prefix=options["prefix"],
                )
            except ValueError as exc:
                raise CommandError(str(exc)) from exc
            provider = ListingIndexDiscoveryProvider()

        discovery_provider_name = type(provider).__name__
        exclude_identities = (
            set()
            if options["dry_run"]
            else AuthorityFrontierService.discovery_identities_for_provider(
                discovery_provider_name
            )
        )
        try:
            result = provider.discover_candidates(
                options["index_urls"],
                max_candidates=options["max_candidates"],
                exclude_identities=exclude_identities,
                **discover_kwargs,
            )
        except (PermissionError, ValueError) as exc:
            raise CommandError(str(exc)) from exc

        for url, reason in result.skipped_index_urls.items():
            self.stderr.write(self.style.WARNING(f"skipped {url}: {reason}"))

        self.stdout.write(
            f"discovered {len(result.candidates)} candidate(s)"
            f"{' (capped)' if result.capped else ''}"
            + (
                f"; skipped {result.excluded_count} previously seeded"
                if result.excluded_count
                else ""
            )
        )
        for candidate in result.candidates:
            self.stdout.write(f"  {candidate.canonical_key}  {candidate.url}")

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("--dry-run: frontier not updated."))
            return

        seeded = AuthorityFrontierService.seed_from_discovery(
            result.candidates,
            discovery_provider=discovery_provider_name,
        )
        self.stdout.write(
            self.style.SUCCESS(
                "frontier seeded: "
                f"created={seeded['discovery_created']} "
                f"appended={seeded['discovery_appended']} "
                f"skipped={seeded['discovery_skipped']}"
            )
        )
