"""Tests for the Location Tagger default agent and its geocoding integration
into ``add_annotations_from_exact_strings`` — issue #1822.

The agent itself is an LLM-driven corpus action; the deterministic, valuable
surface to pin in unit tests is:

1. The default agent the migration registers (config, tools, badge, slug,
   idempotency).
2. The geocoding behaviour the tool gained — ``OC_COUNTRY`` / ``OC_STATE`` /
   ``OC_CITY`` spans get a geocoded ``Annotation.data`` payload with
   hint-based disambiguation, while every other label is untouched
   (backward compatible).

The full LLM round-trip (agent → tool call → pins on the map) is exercised by
the manual script ``docs/test_scripts/location_tagger_end_to_end.md``.
"""

from __future__ import annotations

import importlib

from django.apps import apps as global_apps
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase
from django.utils import timezone

from opencontractserver.agents.models import AgentConfiguration
from opencontractserver.annotations.models import SPAN_LABEL, Annotation
from opencontractserver.constants.annotations import (
    OC_CITY_LABEL,
    OC_COUNTRY_LABEL,
    OC_STATE_LABEL,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.llms.tools.core_tools import add_annotations_from_exact_strings

User = get_user_model()

# The migration module name starts with a digit, so import it via importlib.
_MIGRATION = importlib.import_module(
    "opencontractserver.agents.migrations.0015_create_location_tagger_agent"
)


class LocationTaggerAgentRegistrationTests(TestCase):
    """The data migration registers a correctly-configured global agent."""

    def test_migration_creates_location_tagger_agent(self):
        # Like 0002 / 0004, the forward function is a no-op without a
        # superuser, so create one then run it against the live app registry.
        User.objects.create_superuser("loc-super", "loc@example.com", "pw")

        _MIGRATION.create_location_tagger_agent(global_apps, None)

        agent = AgentConfiguration.objects.get(name="Location Tagger")
        self.assertEqual(agent.scope, "GLOBAL")
        self.assertTrue(agent.is_active)
        self.assertTrue(agent.is_public)
        self.assertEqual(agent.available_tools, ["add_annotations_from_exact_strings"])
        self.assertEqual(agent.badge_config.get("icon"), "globe")
        self.assertEqual(agent.badge_config.get("label"), "Location Tagger")
        self.assertEqual(agent.slug, "location-tagger")
        # Pin the migration→settings wiring: the seeded prompt is exactly the
        # configured production instructions, not the concise fallback.
        from django.conf import settings

        self.assertEqual(
            agent.system_instructions, settings.DEFAULT_LOCATION_TAGGER_INSTRUCTIONS
        )

    def test_migration_is_idempotent(self):
        User.objects.create_superuser("loc-super2", "loc2@example.com", "pw")
        _MIGRATION.create_location_tagger_agent(global_apps, None)
        _MIGRATION.create_location_tagger_agent(global_apps, None)
        self.assertEqual(
            AgentConfiguration.objects.filter(name="Location Tagger").count(), 1
        )


class _GeoToolFixture(TestCase):
    """A text document whose extract contains known, geocodable place names.

    Built in ``setUp`` (not ``setUpClass``) so the ``txt_extract_file`` is
    materialised into whatever ``MEDIA_ROOT`` the per-test ``media_storage``
    fixture is pointing at — the same staleness pitfall the sibling
    ``test_llm_annotation_tools`` works around.
    """

    # Includes a guaranteed non-place token ("Zzzqqqx") for the miss test and
    # a plain word ("branch") for the non-geographic-label test.
    DOC_TEXT = (
        "Headquarters in Paris and France, with a branch in Texas. Ref Zzzqqqx end."
    )

    def setUp(self):
        self.user = User.objects.create_user("loc_tool_user", password="pw")
        self.corpus = Corpus.objects.create(title="Geo Tool Corpus", creator=self.user)

        doc = Document.objects.create(
            creator=self.user,
            title="Geo Text Doc",
            file_type="text/plain",
            processing_started=timezone.now(),  # skip processing signal
        )
        # FieldFile.save() commits the instance (save=True default), so no
        # explicit doc.save() is needed afterwards.
        doc.txt_extract_file.save("geo.txt", ContentFile(self.DOC_TEXT.encode()))
        # add_document returns the corpus-isolated copy the tool annotates.
        self.doc, _, _ = self.corpus.add_document(document=doc, user=self.user)

    def _annotate(self, items):
        return add_annotations_from_exact_strings(
            items,
            document_id=self.doc.id,
            corpus_id=self.corpus.id,
            creator_id=self.user.id,
        )


class LocationTaggerGeocodingTests(_GeoToolFixture):
    """The tool geocodes OC_* labels and leaves everything else alone."""

    def test_country_label_is_geocoded(self):
        ids = self._annotate(
            [{"label_text": OC_COUNTRY_LABEL, "exact_string": "France"}]
        )
        self.assertGreaterEqual(len(ids), 1)
        ann = Annotation.objects.get(pk=ids[0])
        self.assertIsNotNone(ann.data)
        self.assertTrue(ann.data["geocoded"])
        self.assertEqual(ann.data["canonical_name"], "France")
        self.assertEqual(ann.data["admin_codes"]["iso_alpha2"], "FR")
        self.assertIsNotNone(ann.data["lat"])
        self.assertIsNotNone(ann.data["lng"])

    def test_state_label_is_geocoded(self):
        ids = self._annotate([{"label_text": OC_STATE_LABEL, "exact_string": "Texas"}])
        ann = Annotation.objects.get(pk=ids[0])
        self.assertTrue(ann.data["geocoded"])
        self.assertEqual(ann.data["canonical_name"], "Texas")
        self.assertEqual(ann.data["admin_codes"]["admin1"], "TX")
        self.assertEqual(ann.data["admin_codes"]["iso_alpha2"], "US")

    def test_city_hints_disambiguate_paris_to_texas(self):
        ids = self._annotate(
            [
                {
                    "label_text": OC_CITY_LABEL,
                    "exact_string": "Paris",
                    "hints": {"country": "US", "state": "TX"},
                }
            ]
        )
        ann = Annotation.objects.get(pk=ids[0])
        self.assertTrue(ann.data["geocoded"])
        self.assertEqual(ann.data["admin_codes"]["iso_alpha2"], "US")
        self.assertEqual(ann.data["admin_codes"]["admin1"], "TX")
        # Paris, TX sits at a negative (western) longitude, unlike Paris, FR.
        self.assertLess(ann.data["lng"], 0)

    def test_city_without_hints_still_geocodes(self):
        # An unhinted geographic span still flows through the tool and gets a
        # geocoded payload. Which *specific* place an ambiguous name resolves to
        # (unhinted "Paris" → Paris, FR by population) is the geocoder's
        # responsibility and is pinned in
        # ``test_geocoding_service.test_ambiguous_picks_largest_by_population``;
        # re-asserting the country here would couple this tool-integration test
        # to the geocoder's dataset internals.
        ids = self._annotate([{"label_text": OC_CITY_LABEL, "exact_string": "Paris"}])
        ann = Annotation.objects.get(pk=ids[0])
        self.assertIsNotNone(ann.data)
        self.assertTrue(ann.data["geocoded"])

    def test_ungeocodable_geo_span_marks_not_geocoded(self):
        # A geo label on text that is not a known place still creates the
        # annotation (user's work survives) but with geocoded=False so the
        # map aggregation skips it.
        ids = self._annotate([{"label_text": OC_CITY_LABEL, "exact_string": "Zzzqqqx"}])
        ann = Annotation.objects.get(pk=ids[0])
        self.assertIsNotNone(ann.data)
        self.assertFalse(ann.data["geocoded"])
        self.assertIsNone(ann.data["canonical_name"])
        # The miss sentinel preserves the original text so the map aggregation
        # can trace unresolved annotations.
        self.assertEqual(ann.data["raw_text"], "Zzzqqqx")

    def test_non_geographic_label_leaves_data_null(self):
        # Backward compatibility: a normal label must NOT get a data payload.
        ids = self._annotate([{"label_text": "ContractTerm", "exact_string": "branch"}])
        ann = Annotation.objects.get(pk=ids[0])
        self.assertIsNone(ann.data)

    def test_geocoding_resolved_once_and_reused_for_each_occurrence(self):
        """When a place name appears twice, both annotations carry the geocoded
        data, and the disk-reading resolver runs once per *item* — not once per
        *occurrence* (the resolve-before-transaction optimisation; review #2)."""
        from unittest.mock import patch

        import opencontractserver.annotations.services.geographic_service as geo_svc

        # A document where "Paris" occurs twice.
        doc = Document.objects.create(
            creator=self.user,
            title="Twice-Paris Doc",
            file_type="text/plain",
            processing_started=timezone.now(),
        )
        doc.txt_extract_file.save(
            "twice.txt", ContentFile(b"Paris is lovely. We also adore Paris.")
        )
        corpus_doc, _, _ = self.corpus.add_document(document=doc, user=self.user)

        real_builder = geo_svc.build_geocoded_annotation_data
        # ``add_annotations_from_exact_strings`` imports the builder lazily from
        # this module at call time, so patching the source attribute is seen.
        with patch.object(
            geo_svc,
            "build_geocoded_annotation_data",
            side_effect=real_builder,
        ) as spy:
            ids = add_annotations_from_exact_strings(
                [{"label_text": OC_CITY_LABEL, "exact_string": "Paris"}],
                document_id=corpus_doc.id,
                corpus_id=self.corpus.id,
                creator_id=self.user.id,
            )

        # Two occurrences ⇒ two annotations, both carrying identical geocoded data.
        self.assertEqual(len(ids), 2)
        anns = list(Annotation.objects.filter(pk__in=ids))
        self.assertEqual(len(anns), 2)
        for ann in anns:
            self.assertIsNotNone(ann.data)
            self.assertTrue(ann.data["geocoded"])
            self.assertEqual(ann.data["admin_codes"]["iso_alpha2"], "FR")
            # Assert per-annotation inside the loop: queryset order is
            # non-deterministic without an ``order_by``, so a check after the
            # loop would only validate whichever row happened to come last.
            self.assertEqual(ann.annotation_type, SPAN_LABEL)
        # Resolver invoked exactly once for the single item, not per occurrence.
        self.assertEqual(spy.call_count, 1)

    def test_hints_ignored_for_non_geographic_label(self):
        # Hints on a non-geo label are silently ignored (no crash, no data).
        ids = self._annotate(
            [
                {
                    "label_text": "ContractTerm",
                    "exact_string": "branch",
                    "hints": {"country": "US"},
                }
            ]
        )
        ann = Annotation.objects.get(pk=ids[0])
        self.assertIsNone(ann.data)

    def test_non_string_hint_values_are_coerced_not_crashed(self):
        # LLM output can violate the declared ``dict[str, str]`` hint shape —
        # e.g. an int country code or a null state. Such values must be coerced
        # (and ``None`` dropped) at the tool boundary; before the fix they
        # reached the geocoder's ``str.strip().lower()`` and raised
        # ``AttributeError``. The span is still created and geocoded.
        ids = self._annotate(
            [
                {
                    "label_text": OC_CITY_LABEL,
                    "exact_string": "Paris",
                    "hints": {"country": 123, "state": None},
                }
            ]
        )
        ann = Annotation.objects.get(pk=ids[0])
        self.assertIsNotNone(ann.data)
        self.assertTrue(ann.data["geocoded"])
