"""Idempotently load the declarative authority-mappings baseline into the DB.

Re-runnable: upserts source="baseline" equivalences and never clobbers
source="manual" runtime overrides. Use after editing
``opencontractserver/enrichment/data/authority_mappings.yaml``.
"""

from django.core.management.base import BaseCommand

from opencontractserver.enrichment.services.authority_mapping_loader import (
    AuthorityMappingLoader,
)


class Command(BaseCommand):
    help = "Load the declarative authority-mappings baseline (equivalences)."

    def handle(self, *args, **options):
        summary = AuthorityMappingLoader.load()
        self.stdout.write(
            self.style.SUCCESS(
                "authority mappings loaded: "
                f"created={summary['created']} updated={summary['updated']} "
                f"skipped_manual={summary['skipped_manual']} total={summary['total']}"
            )
        )
