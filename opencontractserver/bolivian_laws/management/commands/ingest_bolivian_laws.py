"""Bulk-ingest a directory of Bolivian legal PDFs into per-area corpora.

Usage:

    python manage.py ingest_bolivian_laws --path /data/leyes/ --area constitucional
    python manage.py ingest_bolivian_laws --path /data/leyes/ --auto-classify
    python manage.py ingest_bolivian_laws --path /data/leyes/ --area penal --async

The directory is scanned non-recursively for ``*.pdf`` files (the user
explicitly chose a "flat structure" workflow). For each PDF:

1. SHA-256 dedupe against ``BolivianLegalDocument`` (skip if already
   ingested anywhere).
2. Determine the area: explicit ``--area`` wins; otherwise the LLM
   classifier is used if ``--auto-classify`` is set; otherwise the file
   is skipped with a warning.
3. ``ensure_area_corpus`` (idempotent) and ``ingest_pdf`` (inline) — or
   ``ingest_pdf_async.delay(...)`` if ``--async`` is passed.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from opencontractserver.bolivian_laws.constants import LegalArea, LegalSource
from opencontractserver.bolivian_laws.services.ingestion import (
    classify_pdf_area,
    infer_metadata_from_filename,
    ingest_pdf,
)
from opencontractserver.bolivian_laws.tasks import ingest_pdf_async

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Bulk-ingest Bolivian legal PDFs into per-area corpora."

    def add_arguments(self, parser):
        parser.add_argument(
            "--path",
            required=True,
            help="Directory containing flat PDFs to ingest.",
        )
        parser.add_argument(
            "--area",
            choices=[a.value for a in LegalArea],
            default=None,
            help="Force this area for all PDFs in the batch.",
        )
        parser.add_argument(
            "--auto-classify",
            action="store_true",
            help="Use the LLM classifier when --area is not given.",
        )
        parser.add_argument(
            "--source",
            choices=[s.value for s in LegalSource],
            default=LegalSource.MANUAL,
            help="Source attribution for the batch (default: manual).",
        )
        parser.add_argument(
            "--async",
            action="store_true",
            dest="run_async",
            help="Enqueue Celery tasks instead of processing inline.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List files and resolved areas without ingesting.",
        )

    def handle(self, *args, **options):
        path = Path(options["path"]).expanduser().resolve()
        if not path.is_dir():
            raise CommandError(f"--path must be a directory: {path}")

        forced_area: str | None = options.get("area")
        auto_classify: bool = options.get("auto_classify", False)
        source: str = options["source"]
        run_async: bool = options.get("run_async", False)
        dry_run: bool = options.get("dry_run", False)

        if not forced_area and not auto_classify:
            raise CommandError("Either --area or --auto-classify must be provided.")

        pdf_files = sorted(p for p in path.glob("*.pdf") if p.is_file())
        if not pdf_files:
            self.stdout.write(self.style.WARNING(f"No PDFs found under {path}"))
            return

        self.stdout.write(
            f"Found {len(pdf_files)} PDF(s) under {path}; "
            f"area={forced_area or 'auto'}, source={source}, "
            f"async={run_async}, dry_run={dry_run}"
        )

        ingested = skipped = failed = 0

        for pdf_path in pdf_files:
            inferred = infer_metadata_from_filename(pdf_path.name)
            area = forced_area or inferred.get("area")
            title = inferred.get("title_hint") or pdf_path.stem

            if not area and auto_classify:
                area = asyncio.run(classify_pdf_area(pdf_path, title=title))

            if not area:
                self.stdout.write(
                    self.style.WARNING(f"  SKIP {pdf_path.name}: no area resolved.")
                )
                skipped += 1
                continue

            if dry_run:
                self.stdout.write(f"  DRY  {pdf_path.name} → area={area}")
                continue

            try:
                if run_async:
                    ingest_pdf_async.delay(
                        str(pdf_path),
                        area=area,
                        title=title,
                        source=source,
                        metadata=inferred,
                    )
                    self.stdout.write(f"  QUEUED {pdf_path.name} → {area}")
                    ingested += 1
                else:
                    record = ingest_pdf(
                        pdf_path,
                        area=area,
                        title=title,
                        source=source,
                        metadata=inferred,
                        filename=pdf_path.name,
                    )
                    if record.status == record.Status.INGESTED:
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"  OK   {pdf_path.name} → {area} "
                                f"(record #{record.pk})"
                            )
                        )
                        ingested += 1
                    else:
                        self.stdout.write(
                            f"  DEDUPE {pdf_path.name} (existing #{record.pk})"
                        )
                        skipped += 1
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f"  FAIL {pdf_path.name}: {exc}"))
                failed += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone: ingested={ingested}, skipped={skipped}, failed={failed}"
            )
        )
