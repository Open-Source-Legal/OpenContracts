"""Tests for Bolivian Laws constants module."""

from django.test import SimpleTestCase

from opencontractserver.bolivian_laws.constants import (
    AREA_PROFILES,
    AreaProfile,
    LegalArea,
    LegalSource,
    corpus_slug_for_area,
    get_profile,
)


class TestLegalAreaProfiles(SimpleTestCase):
    def test_every_area_has_profile(self):
        for area in LegalArea:
            self.assertIn(area.value, AREA_PROFILES)
            profile = AREA_PROFILES[area.value]
            self.assertIsInstance(profile, AreaProfile)
            self.assertTrue(profile.title.startswith("Bolivia — "))
            self.assertTrue(profile.description)
            self.assertTrue(profile.agent_persona)
            self.assertTrue(profile.agent_instructions)

    def test_get_profile_unknown_raises(self):
        with self.assertRaises(KeyError):
            get_profile("not-a-real-area")

    def test_corpus_slug_is_deterministic(self):
        self.assertEqual(
            corpus_slug_for_area(LegalArea.CONSTITUCIONAL),
            "bolivia-constitucional",
        )
        self.assertEqual(corpus_slug_for_area(LegalArea.PENAL), "bolivia-penal")

    def test_legal_source_choices_present(self):
        self.assertIn("gaceta", {s.value for s in LegalSource})
        self.assertIn("tsj", {s.value for s in LegalSource})
        self.assertIn("tcp", {s.value for s in LegalSource})
        self.assertIn("manual", {s.value for s in LegalSource})
