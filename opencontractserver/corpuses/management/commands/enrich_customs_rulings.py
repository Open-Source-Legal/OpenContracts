"""Run HTS-code + ruling-citation enrichment over a corpus of CBP rulings.

The scripted entry point for
:meth:`opencontractserver.enrichment.services.customs_ruling_citation_service.CustomsRulingCitationService.enrich_corpus`
— see that module's docstring for scope (purpose-built for CBP CROSS-style
ruling corpora, not a general OpenContracts feature).

Example::

    python manage.py enrich_customs_rulings --corpus-id 92 --owner admin
"""

from __future__ import annotations

import json
from typing import Any

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from opencontractserver.enrichment.services.customs_ruling_citation_service import (
    CustomsRulingCitationService,
)

User = get_user_model()


class Command(BaseCommand):
    help = (
        "Detect HTS tariff codes and CBP ruling-number citations across a "
        "corpus's already-ingested documents, persisting HTS_CODE annotations "
        "and CorpusReference/DocumentRelationship rows for resolved citations."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--corpus-id", type=int, required=True, help="Corpus to enrich."
        )
        parser.add_argument(
            "--owner",
            default=None,
            help="Username to run as (provenance + visibility scope). "
            "Defaults to the first superuser.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        if options["owner"]:
            owner = User.objects.filter(username=options["owner"]).first()
            if owner is None:
                raise CommandError(f"No user named {options['owner']!r}.")
        else:
            owner = User.objects.filter(is_superuser=True).order_by("id").first()
            if owner is None:
                raise CommandError("No superuser found; pass --owner explicitly.")

        result = CustomsRulingCitationService.enrich_corpus(
            corpus_id=options["corpus_id"], creator_id=owner.pk
        )
        self.stdout.write(self.style.SUCCESS(json.dumps(result, indent=2)))
