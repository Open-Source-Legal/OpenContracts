"""Tests for the OC_COUNTRY / OC_STATE / OC_CITY auto-creating mutations.

Issue #1819. Each mutation:

1. Validates document + corpus visibility (IDOR-safe).
2. Calls the offline geocoder.
3. Ensures the relevant ``OC_*`` label exists on the corpus.
4. Creates the annotation with ``structural=True``, stamping the geocoded
   ``data`` payload (or the ``geocoded: False`` sentinel on miss).

Tests cover the happy path + permission failure + ungeocodable text path
for one mutation in detail and lightly verify the other two follow the
same contract — the shared body ``_create_geographic_annotation`` is the
real implementation, so over-testing each wrapper is just duplication.
"""

from __future__ import annotations

from typing import Any

from django.contrib.auth import get_user_model
from django.test import TestCase
from graphene.test import Client
from graphql_relay import to_global_id

from config.graphql.schema import schema
from opencontractserver.annotations.models import (
    Annotation,
    AnnotationLabel,
)
from opencontractserver.constants.annotations import (
    OC_CITY_LABEL,
    OC_COUNTRY_LABEL,
    OC_STATE_LABEL,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


ADD_COUNTRY_MUTATION = """
    mutation AddCountryAnnotation(
        $corpusId: String!
        $documentId: String!
        $page: Int!
        $rawText: String!
        $json: GenericScalar!
        $annotationType: LabelType!
    ) {
        addCountryAnnotation(
            corpusId: $corpusId
            documentId: $documentId
            page: $page
            rawText: $rawText
            json: $json
            annotationType: $annotationType
        ) {
            ok
            message
            geocoded
            annotation {
                id
                rawText
                structural
                data
                annotationLabel { text color }
            }
        }
    }
"""

ADD_STATE_MUTATION = """
    mutation AddStateAnnotation(
        $corpusId: String!
        $documentId: String!
        $page: Int!
        $rawText: String!
        $json: GenericScalar!
        $annotationType: LabelType!
        $countryHint: String
    ) {
        addStateAnnotation(
            corpusId: $corpusId
            documentId: $documentId
            page: $page
            rawText: $rawText
            json: $json
            annotationType: $annotationType
            countryHint: $countryHint
        ) {
            ok
            message
            geocoded
            annotation {
                id
                data
                annotationLabel { text }
            }
        }
    }
"""

ADD_CITY_MUTATION = """
    mutation AddCityAnnotation(
        $corpusId: String!
        $documentId: String!
        $page: Int!
        $rawText: String!
        $json: GenericScalar!
        $annotationType: LabelType!
        $countryHint: String
        $stateHint: String
    ) {
        addCityAnnotation(
            corpusId: $corpusId
            documentId: $documentId
            page: $page
            rawText: $rawText
            json: $json
            annotationType: $annotationType
            countryHint: $countryHint
            stateHint: $stateHint
        ) {
            ok
            message
            geocoded
            annotation {
                id
                data
                annotationLabel { text }
            }
        }
    }
"""


class _MutationContext:
    """Minimal info.context stand-in for graphene.test.Client."""

    def __init__(self, user):
        self.user = user


class _BaseGeoMutationTestCase(TestCase):
    """Shared fixture: owner / outsider / corpus / document with permissions."""

    def setUp(self):
        self.owner = User.objects.create_user(username="geo-owner", password="x")
        self.outsider = User.objects.create_user(username="geo-outsider", password="x")

        original_doc = Document.objects.create(
            title="Geo Doc",
            creator=self.owner,
            is_public=False,
            backend_lock=False,
        )
        self.corpus = Corpus.objects.create(
            title="Geo Corpus", creator=self.owner, is_public=False
        )
        # ``add_document`` returns the corpus-scoped copy that mutations
        # actually annotate against — matches the flow used by the URL
        # annotation tests so the IDOR contract is identical.
        self.document, _, _ = self.corpus.add_document(
            document=original_doc, user=self.owner
        )
        set_permissions_for_obj_to_user(
            self.owner, self.document, [PermissionTypes.CRUD]
        )
        set_permissions_for_obj_to_user(self.owner, self.corpus, [PermissionTypes.CRUD])

        # graphene ships without ``py.typed``, so mypy treats ``Client``
        # as a concrete class without the inline-annotated ``.execute``
        # method. Sister test modules (``test_url_annotation`` etc.)
        # are baselined; this PR is type-checked, so annotate as Any
        # to bypass the known graphene/mypy gap without silencing the
        # whole module.
        self.client: Any = Client(schema)

    def _vars(self, **extra):
        """Compose the shared GraphQL variables block."""
        base = {
            "corpusId": to_global_id("CorpusType", self.corpus.pk),
            "documentId": to_global_id("DocumentType", self.document.pk),
            "page": 0,
            "rawText": extra.pop("rawText", "anchor"),
            "json": {"0": {"bounds": {}, "rawText": "anchor", "tokensJsons": []}},
            "annotationType": "TOKEN_LABEL",
        }
        base.update(extra)
        return base


class AddCountryAnnotationTests(_BaseGeoMutationTestCase):
    """Happy / miss / IDOR coverage for ``addCountryAnnotation``."""

    def test_owner_creates_country_annotation_and_label(self):
        # The mutation must (a) create the OC_COUNTRY label on first use,
        # (b) write the resolved coordinates into ``data``, and (c) mark
        # the annotation structural so the platform's read-only invariant
        # for structural rows applies to it.
        before_labels = AnnotationLabel.objects.filter(text=OC_COUNTRY_LABEL).count()
        result = self.client.execute(
            ADD_COUNTRY_MUTATION,
            variables=self._vars(rawText="France"),
            context_value=_MutationContext(self.owner),
        )
        self.assertNotIn("errors", result, msg=result.get("errors"))
        payload = result["data"]["addCountryAnnotation"]
        self.assertTrue(payload["ok"], msg=payload.get("message"))
        self.assertTrue(payload["geocoded"])
        self.assertEqual(
            payload["annotation"]["annotationLabel"]["text"], OC_COUNTRY_LABEL
        )
        self.assertTrue(payload["annotation"]["structural"])
        data = payload["annotation"]["data"]
        self.assertEqual(data["canonical_name"], "France")
        self.assertAlmostEqual(data["lat"], 46.227638, places=4)
        self.assertEqual(data["admin_codes"]["iso_alpha2"], "FR")
        # Label was minted exactly once.
        self.assertEqual(
            AnnotationLabel.objects.filter(text=OC_COUNTRY_LABEL).count(),
            before_labels + 1,
        )

    def test_country_alias_resolves(self):
        # The mutation flows through the same alias map the unit tests
        # cover — confirm a code form still hits canonical name.
        result = self.client.execute(
            ADD_COUNTRY_MUTATION,
            variables=self._vars(rawText="USA"),
            context_value=_MutationContext(self.owner),
        )
        payload = result["data"]["addCountryAnnotation"]
        self.assertTrue(payload["geocoded"])
        self.assertEqual(
            payload["annotation"]["data"]["canonical_name"], "United States"
        )

    def test_outsider_cannot_create_country_annotation(self):
        # IDOR coverage: the same unified "not found or no permission"
        # message that the URL mutation returns must apply here.
        before = Annotation.objects.count()
        result = self.client.execute(
            ADD_COUNTRY_MUTATION,
            variables=self._vars(rawText="France"),
            context_value=_MutationContext(self.outsider),
        )
        payload = result["data"]["addCountryAnnotation"]
        self.assertFalse(payload["ok"])
        self.assertIsNone(payload["annotation"])
        # Critically: nothing written.
        self.assertEqual(Annotation.objects.count(), before)

    def test_empty_raw_text_rejected_without_creating_annotation(self):
        # Guard added in response to PR #1823 review: an empty / whitespace
        # span shouldn't create a no-op ``geocoded=False`` annotation that
        # silently pollutes the user's annotation set. The mutation must
        # return ``ok=False`` with a clear message and write nothing.
        before = Annotation.objects.count()
        for blank in ("", "   ", "\t\n"):
            result = self.client.execute(
                ADD_COUNTRY_MUTATION,
                variables=self._vars(rawText=blank),
                context_value=_MutationContext(self.owner),
            )
            payload = result["data"]["addCountryAnnotation"]
            self.assertFalse(payload["ok"])
            self.assertIsNone(payload["annotation"])
            self.assertIn("raw_text", payload["message"])
        self.assertEqual(Annotation.objects.count(), before)

    def test_ungeocodable_text_still_creates_annotation(self):
        # The spec is explicit: the user's labelling work survives a
        # resolver miss; only the map aggregation skips the row.
        before = Annotation.objects.count()
        result = self.client.execute(
            ADD_COUNTRY_MUTATION,
            variables=self._vars(rawText="Zzzqqqxxxnnnoppp"),
            context_value=_MutationContext(self.owner),
        )
        payload = result["data"]["addCountryAnnotation"]
        self.assertTrue(payload["ok"])
        # geocoded=False is the signal the aggregation service uses to
        # exclude the row from map pins.
        self.assertFalse(payload["geocoded"])
        self.assertIn("did not resolve", payload["message"])
        # Annotation written; ``data['geocoded']`` is False.
        self.assertEqual(Annotation.objects.count(), before + 1)
        ann = Annotation.objects.latest("created")
        self.assertFalse(ann.data["geocoded"])
        self.assertIsNone(ann.data["canonical_name"])

    def test_label_marked_read_only(self):
        # Structural OC_* labels are platform-managed; the read-only flag
        # prevents users from re-editing them later (only superusers can).
        # The mutation must set this on label creation.
        self.client.execute(
            ADD_COUNTRY_MUTATION,
            variables=self._vars(rawText="France"),
            context_value=_MutationContext(self.owner),
        )
        label = AnnotationLabel.objects.get(text=OC_COUNTRY_LABEL)
        self.assertTrue(label.read_only)

    def test_idempotent_label_on_repeat(self):
        # Two country annotations in the same corpus must reuse the label.
        self.client.execute(
            ADD_COUNTRY_MUTATION,
            variables=self._vars(rawText="France"),
            context_value=_MutationContext(self.owner),
        )
        self.client.execute(
            ADD_COUNTRY_MUTATION,
            variables=self._vars(rawText="Germany"),
            context_value=_MutationContext(self.owner),
        )
        self.assertEqual(
            AnnotationLabel.objects.filter(text=OC_COUNTRY_LABEL).count(), 1
        )


class AddStateAnnotationTests(_BaseGeoMutationTestCase):
    """Light coverage for ``addStateAnnotation`` — shared body in detail above."""

    def test_state_annotation_with_usps_code(self):
        result = self.client.execute(
            ADD_STATE_MUTATION,
            variables=self._vars(rawText="TX"),
            context_value=_MutationContext(self.owner),
        )
        self.assertNotIn("errors", result, msg=result.get("errors"))
        payload = result["data"]["addStateAnnotation"]
        self.assertTrue(payload["geocoded"])
        self.assertEqual(
            payload["annotation"]["annotationLabel"]["text"], OC_STATE_LABEL
        )
        self.assertEqual(payload["annotation"]["data"]["canonical_name"], "Texas")
        self.assertEqual(payload["annotation"]["data"]["admin_codes"]["admin1"], "TX")


class AddCityAnnotationTests(_BaseGeoMutationTestCase):
    """City coverage — includes the disambiguation hint flow."""

    def test_unhinted_paris_resolves_to_france(self):
        # No hints → population tie-break picks the largest "Paris" row.
        result = self.client.execute(
            ADD_CITY_MUTATION,
            variables=self._vars(rawText="Paris"),
            context_value=_MutationContext(self.owner),
        )
        payload = result["data"]["addCityAnnotation"]
        self.assertTrue(payload["geocoded"])
        self.assertEqual(
            payload["annotation"]["data"]["admin_codes"]["iso_alpha2"], "FR"
        )

    def test_state_hint_disambiguates_paris(self):
        # The state hint must override population tie-break.
        result = self.client.execute(
            ADD_CITY_MUTATION,
            variables=self._vars(rawText="Paris", countryHint="US", stateHint="TX"),
            context_value=_MutationContext(self.owner),
        )
        payload = result["data"]["addCityAnnotation"]
        self.assertEqual(
            payload["annotation"]["data"]["admin_codes"]["iso_alpha2"], "US"
        )
        self.assertEqual(payload["annotation"]["data"]["admin_codes"]["admin1"], "TX")
        # Coordinates change accordingly — Paris, TX is ~95.5W, not ~2.3E.
        self.assertLess(payload["annotation"]["data"]["lng"], 0)

    def test_city_label_carries_color(self):
        # OC_CITY label color must match the constant — this is the only
        # automated check that the auto-created label gets the right
        # presentation (the frontend constants mirror these).
        from opencontractserver.constants.annotations import OC_CITY_LABEL_COLOR

        self.client.execute(
            ADD_CITY_MUTATION,
            variables=self._vars(rawText="Tokyo"),
            context_value=_MutationContext(self.owner),
        )
        label = AnnotationLabel.objects.get(text=OC_CITY_LABEL)
        self.assertEqual(label.color, OC_CITY_LABEL_COLOR)
