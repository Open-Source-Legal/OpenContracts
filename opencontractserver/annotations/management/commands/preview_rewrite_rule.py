"""Dry-run preview of authority prefix rewrite rules (no DB writes).

Rewrite rules are a sparing, reviewed fallback (evaluated after explicit per-key
equivalences). Before adding one to ``authority_mappings.yaml``, preview exactly
which keys it would transform and whether the rewritten key becomes ingestable::

    manage.py preview_rewrite_rule --pattern '^irc:(?P<n>.+)$' --replacement 'usc-26:\\g<n>'
    manage.py preview_rewrite_rule                       # preview the shipped YAML rules
    manage.py preview_rewrite_rule --keys irc:501,dgcl:145   # against explicit keys

With no ``--keys`` the candidate set is the distinct ``AuthorityFrontier``
canonical keys (the wanted-authorities queue) — i.e. the keys a rule would
actually affect in production.
"""

from django.core.management.base import BaseCommand, CommandError

from opencontractserver.enrichment.data import mappings as _mappings


class Command(BaseCommand):
    help = (
        "Preview which authority keys a prefix rewrite rule would transform "
        "(dry-run; no writes)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--pattern",
            default=None,
            help="Ad-hoc rule regex pattern (requires --replacement).",
        )
        parser.add_argument(
            "--replacement",
            default=None,
            help="Ad-hoc rule replacement (requires --pattern).",
        )
        parser.add_argument(
            "--keys",
            default=None,
            help=(
                "Comma-separated candidate keys to test (default: distinct "
                "AuthorityFrontier.canonical_key)."
            ),
        )

    def handle(self, *args, **options):
        pattern, replacement = options["pattern"], options["replacement"]
        if bool(pattern) ^ bool(replacement):
            raise CommandError("--pattern and --replacement must be given together.")

        if pattern:
            try:
                rules = _mappings.iter_rewrite_rules(
                    {
                        "rewrite_rules": [
                            {"pattern": pattern, "replacement": replacement}
                        ]
                    }
                )
            except ValueError as exc:
                raise CommandError(str(exc)) from exc
        else:
            rules = _mappings.iter_rewrite_rules()
            if not rules:
                self.stdout.write("No rewrite_rules in authority_mappings.yaml.")
                return

        candidate_keys = self._candidate_keys(options["keys"])
        self.stdout.write(
            f"Previewing {len(rules)} rule(s) over {len(candidate_keys)} "
            "candidate key(s).\n"
        )
        for rule in rules:
            self._preview_rule(rule, candidate_keys)

    @staticmethod
    def _candidate_keys(keys_arg: str | None) -> list[str]:
        if keys_arg:
            return [k.strip() for k in keys_arg.split(",") if k.strip()]
        from opencontractserver.annotations.models import AuthorityFrontier

        return list(
            AuthorityFrontier.objects.order_by("canonical_key").values_list(
                "canonical_key", flat=True
            )
        )

    def _preview_rule(self, rule: dict, candidate_keys: list[str]) -> None:
        from opencontractserver.enrichment.services.authority_discovery_service import (
            AuthorityDiscoveryService,
        )

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"Rule: {rule['pattern']} -> {rule['replacement']}"
            )
        )
        if rule.get("note"):
            self.stdout.write(f"  ({rule['note']})")

        hits = [
            (key, rewritten)
            for key in candidate_keys
            for rewritten in _mappings.apply_rewrite_rules(key, rules=[rule])
        ]
        if not hits:
            self.stdout.write("  would rewrite 0 keys.")
            return

        self.stdout.write(f"  would rewrite {len(hits)} key(s):")
        for key, rewritten in hits:
            provider_name = AuthorityDiscoveryService._provider_for(rewritten)[0]
            tag = f"[ingestable: {provider_name}]" if provider_name else "[no provider]"
            self.stdout.write(f"    {key} -> {rewritten}  {tag}")
