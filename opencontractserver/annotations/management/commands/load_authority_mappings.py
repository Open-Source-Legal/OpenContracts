"""Idempotently load the declarative authority-mappings baseline into the DB.

Re-runnable: upserts ``prefixes:`` into AuthorityNamespace (global) and
``equivalences:`` into AuthorityKeyEquivalence (source="baseline"), never
clobbering ``source="manual"`` overrides, corpus-linked namespaces, or a
baseline prefix another writer origin owns. Use after editing
``opencontractserver/enrichment/data/authority_mappings.yaml``.

``--include-packs`` additionally merge-loads every installed authority pack's
mappings YAML (every pack ``pipeline.registry.authority_pack_dirs`` finds), each
stamped with the pack's name as its baseline origin — one command converges the
whole installed taxonomy.
"""

from django.core.management.base import BaseCommand

from opencontractserver.enrichment.constants import BASELINE_ORIGIN_CORE
from opencontractserver.enrichment.services.authority_mapping_loader import (
    AuthorityMappingLoader,
)


class Command(BaseCommand):
    help = (
        "Load the declarative authority-mappings baseline (prefixes + "
        "equivalences); --include-packs also merge-loads every installed "
        "authority pack's mappings YAML."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--include-packs",
            action="store_true",
            help=(
                "Also load every installed authority pack's mappings YAML "
                "(in-tree authority_packs/ + sideloaded pack roots/paths), each "
                "stamped with its pack name as baseline origin."
            ),
        )

    def handle(self, *args, **options):
        if options["include_packs"]:
            results = AuthorityMappingLoader.load_installed()
        else:
            results = {BASELINE_ORIGIN_CORE: AuthorityMappingLoader.load_all()}
        for origin, summary in results.items():
            self._report(origin, summary)

    def _report(self, origin: str, summary: dict) -> None:
        if "error" in summary:
            # A malformed pack YAML was skipped (per-pack fault isolation in
            # load_installed); surface it without failing the other packs.
            self.stderr.write(
                self.style.WARNING(f"[{origin}] SKIPPED: {summary['error']}")
            )
            return
        ns = summary["namespaces"]
        eq = summary["equivalences"]
        self.stdout.write(
            self.style.SUCCESS(
                f"[{origin}] authority namespaces loaded: "
                f"created={ns['created']} updated={ns['updated']} "
                f"skipped_corpus_linked={ns['skipped_corpus_linked']} "
                f"skipped_manual={ns['skipped_manual']} "
                f"skipped_foreign_baseline={ns['skipped_foreign_baseline']} "
                f"total={ns['total']}"
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"[{origin}] authority equivalences loaded: "
                f"created={eq['created']} updated={eq['updated']} "
                f"skipped_owned={eq['skipped_owned']} total={eq['total']}"
            )
        )
