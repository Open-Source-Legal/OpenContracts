"""Run the Bolivian-laws scrapers on demand.

Usage:

    python manage.py scrape_bolivian_laws --source gaceta
    python manage.py scrape_bolivian_laws --all --since-days 7
    python manage.py scrape_bolivian_laws --source tcp --max-entries 5 --sync

``--sync`` runs the scrape inline in this process (useful for the
initial bootstrap or manual backfills). Without it, the command
enqueues Celery tasks and returns immediately.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from opencontractserver.bolivian_laws.scrapers import SCRAPERS
from opencontractserver.bolivian_laws.tasks import (
    scrape_and_ingest_all,
    scrape_and_ingest_source,
)


class Command(BaseCommand):
    help = "Scrape one or all Bolivian legal sources and ingest new PDFs."

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument(
            "--source",
            choices=sorted(SCRAPERS.keys()),
            help="Run a single source (gaceta | tsj | tcp).",
        )
        group.add_argument(
            "--all",
            action="store_true",
            dest="run_all",
            help="Run every registered source.",
        )
        parser.add_argument(
            "--since-days",
            type=int,
            default=None,
            help=(
                "Only ingest entries whose published_at is within the last "
                "N days (when the listing exposes a date)."
            ),
        )
        parser.add_argument(
            "--max-entries",
            type=int,
            default=None,
            help="Cap the number of entries processed per source.",
        )
        parser.add_argument(
            "--sync",
            action="store_true",
            help="Run inline instead of enqueuing Celery tasks.",
        )
        parser.add_argument(
            "--user-id",
            type=int,
            default=None,
            help="Attribute created corpora/documents to this user ID.",
        )

    def handle(self, *args, **options):
        source = options.get("source")
        run_all = options.get("run_all", False)
        since_days = options.get("since_days")
        max_entries = options.get("max_entries")
        run_sync = options.get("sync", False)
        user_id = options.get("user_id")

        if run_all:
            if run_sync:
                summaries = []
                for key in SCRAPERS:
                    summary = scrape_and_ingest_source.run(
                        key,
                        since_days=since_days,
                        max_entries=max_entries,
                        user_id=user_id,
                    )
                    summaries.append(summary)
                self.stdout.write(self.style.SUCCESS(str(summaries)))
            else:
                task_ids = scrape_and_ingest_all.delay(
                    since_days=since_days,
                    max_entries_per_source=max_entries,
                )
                self.stdout.write(
                    self.style.SUCCESS(f"Enqueued fan-out task: {task_ids.id}")
                )
            return

        if source not in SCRAPERS:
            raise CommandError(f"Unknown source: {source!r}")

        if run_sync:
            summary = scrape_and_ingest_source.run(
                source,
                since_days=since_days,
                max_entries=max_entries,
                user_id=user_id,
            )
            self.stdout.write(self.style.SUCCESS(str(summary)))
        else:
            result = scrape_and_ingest_source.delay(
                source,
                since_days=since_days,
                max_entries=max_entries,
                user_id=user_id,
            )
            self.stdout.write(
                self.style.SUCCESS(f"Enqueued task {result.id} for {source}")
            )
