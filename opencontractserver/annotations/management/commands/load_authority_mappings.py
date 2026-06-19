"""Idempotently load the declarative authority-mappings baseline into the DB.

Re-runnable: upserts ``prefixes:`` into AuthorityNamespace (global) and
``equivalences:`` into AuthorityKeyEquivalence (source="baseline"), never
clobbering ``source="manual"`` overrides or corpus-linked namespaces. Use after
editing ``opencontractserver/enrichment/data/authority_mappings.yaml``.
"""

from django.core.management.base import BaseCommand

from opencontractserver.enrichment.services.authority_mapping_loader import (
    AuthorityMappingLoader,
)


class Command(BaseCommand):
    help = "Load the declarative authority-mappings baseline (prefixes + equivalences)."

    def handle(self, *args, **options):
        summary = AuthorityMappingLoader.load_all()
        ns = summary["namespaces"]
        eq = summary["equivalences"]
        self.stdout.write(
            self.style.SUCCESS(
                "authority namespaces loaded: "
                f"created={ns['created']} updated={ns['updated']} "
                f"skipped_corpus_linked={ns['skipped_corpus_linked']} "
                f"total={ns['total']}"
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                "authority equivalences loaded: "
                f"created={eq['created']} updated={eq['updated']} "
                f"skipped_owned={eq['skipped_owned']} total={eq['total']}"
            )
        )
