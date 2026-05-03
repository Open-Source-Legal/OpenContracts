from django.apps import apps
from django.core.management.base import BaseCommand

from opencontractserver.annotations.label_set_seeds import create_default_labelset


class Command(BaseCommand):
    help = (
        "Seed the install-wide default LabelSet (and its starter labels). "
        "Idempotent — safe to run multiple times."
    )

    def handle(self, *args, **options):
        create_default_labelset(apps, None)
        self.stdout.write(self.style.SUCCESS("Default labelset seeded."))
