"""Import act↔USC equivalences from the OLRC USC popular-name table.

Fetches the public-domain popular-name table from uscode.house.gov (already on
PUBLIC_DOMAIN_SOURCE_HOSTS) and upserts the derivable Statutes-at-Large ↔ USC
bridges as ``source="popular_name"`` (idempotent, never clobbers
baseline/manual/uslm rows). ``--file`` imports from a local HTML snapshot
instead of fetching (offline / reproducible runs).
"""

from django.core.management.base import BaseCommand

from opencontractserver.enrichment.services.popular_name_importer import (
    OLRC_POPULAR_NAMES_URL,
    PopularNameTableImporter,
)


class Command(BaseCommand):
    help = "Import act↔USC equivalences from the OLRC USC popular-name table."

    def add_arguments(self, parser):
        parser.add_argument(
            "--url",
            default=OLRC_POPULAR_NAMES_URL,
            help=f"Popular-name table URL (default: {OLRC_POPULAR_NAMES_URL}).",
        )
        parser.add_argument(
            "--file",
            default=None,
            help="Import from a local HTML snapshot instead of fetching.",
        )

    def handle(self, *args, **options):
        html = None
        if options["file"]:
            with open(options["file"], encoding="utf-8") as fh:
                html = fh.read()

        summary = PopularNameTableImporter.import_table(html=html, url=options["url"])
        self.stdout.write(
            self.style.SUCCESS(
                "popular-name table imported: "
                f"created={summary['created']} updated={summary['updated']} "
                f"skipped_owned={summary['skipped_owned']} "
                f"skipped_invalid={summary['skipped_invalid']} "
                f"parsed={summary['parsed']}"
            )
        )
