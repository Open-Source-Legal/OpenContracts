from typing import Any

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandParser

from opencontractserver.analyzer.models import Analyzer
from opencontractserver.analyzer.utils import auto_create_doc_analyzers


class Command(BaseCommand):
    help = "Synchronize doc_analyzer_task decorated functions with Analyzer database"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be created without making changes",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        UserModel = get_user_model()

        if options["dry_run"]:
            self.stdout.write("DRY RUN MODE - No changes will be made")

            from opencontractserver.utils.celery_tasks import (
                celery_app,
                get_doc_analyzer_task_by_name,
            )

            created_count = 0
            existing_count = 0

            for task_name in celery_app.tasks.keys():
                analyzer_task = get_doc_analyzer_task_by_name(task_name)
                if analyzer_task is None:
                    continue

                analyzer_id = task_name
                exists = (
                    Analyzer.objects.filter(id=analyzer_id).exists()
                    or Analyzer.objects.filter(task_name=task_name).exists()
                )

                if exists:
                    existing_count += 1
                    self.stdout.write(f"  EXISTS: {task_name}")
                else:
                    created_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(f"  WOULD CREATE: {task_name}")
                    )

            self.stdout.write(
                f"\nSummary: {created_count} would be created, {existing_count} already exist"
            )
        else:
            auto_create_doc_analyzers(AnalyzerModel=Analyzer, UserModel=UserModel)
            self.stdout.write(
                self.style.SUCCESS("Successfully synchronized doc-based analyzers")
            )
