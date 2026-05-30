"""Tests for ``GeographicAnnotationService`` — issue #1819.

Covers the three behaviours the map UI (#1820 / #1821) depends on:

1. **Aggregation**: identical ``(label_type, canonical_name, lat, lng)``
   tuples coming from different documents collapse into a single pin
   with a ``document_count`` and bounded ``sample_document_ids`` preview.
2. **MIN(document, corpus) visibility**: a private document in a
   readable corpus does NOT leak to a viewer who lacks document-level
   READ. The corpus-scoped flow is the test surface for this (the
   global flow has its own ``Annotation.objects.visible_to_user``
   contract elsewhere).
3. **Bbox filter**: pins outside the viewport bounding box are excluded;
   antimeridian-crossing boxes wrap around correctly.

Also pins the "geocoded: False" sentinel — annotations created when the
resolver missed must NEVER contribute pins.
"""

from __future__ import annotations

from typing import Any

from django.contrib.auth import get_user_model
from django.test import TestCase

from opencontractserver.annotations.models import (
    TOKEN_LABEL,
    Annotation,
    AnnotationLabel,
)
from opencontractserver.annotations.services import (
    BBox,
    GeographicAnnotationService,
)
from opencontractserver.constants.annotations import (
    OC_CITY_LABEL,
    OC_COUNTRY_LABEL,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


class _GeoFixtureMixin:
    """Build a small corpus with a couple of geocoded annotations.

    Documents:
      * ``doc_public`` — public, viewer can see at document level
      * ``doc_private`` — private (no guardian grant for ``viewer``),
        used to verify MIN(doc, corpus) hides private docs in a shared corpus

    Annotations:
      * Country pin "France" on ``doc_public``
      * Country pin "France" on ``doc_private`` (must NOT contribute to
        viewer's pin count even though the corpus is readable)
      * City pin "Tokyo" on ``doc_public``
      * City pin with ``geocoded: False`` on ``doc_public`` (must be
        excluded from aggregation entirely)
    """

    # Class-level declarations so mypy can see the attrs the
    # ``_build_geo_fixture`` classmethod assigns on ``cls``. Without
    # these the subclasses ``GeographicAnnotationServiceCorpusTests`` /
    # ``GeographicAnnotationServiceGlobalTests`` are flagged
    # ``"no attribute 'owner'"`` etc. The Any typing matches the
    # pattern used elsewhere in this test module where get_user_model()
    # returns a runtime class that isn't ergonomic to spell as a type.
    owner: Any
    viewer: Any
    corpus: Corpus
    doc_public: Document
    doc_private: Document
    country_label: AnnotationLabel
    city_label: AnnotationLabel
    ann_country_public: Annotation
    ann_country_private: Annotation
    ann_city_tokyo: Annotation
    ann_city_failed: Annotation

    @classmethod
    def _build_geo_fixture(cls):
        cls.owner = User.objects.create_user(username="geo-svc-owner", password="x")
        cls.viewer = User.objects.create_user(username="geo-svc-viewer", password="x")

        cls.corpus = Corpus.objects.create(
            title="Geo Service Corpus",
            creator=cls.owner,
            is_public=False,
        )
        # Owner gets full perms on the corpus; viewer gets corpus READ
        # only (so we can test the corpus-as-gate vs MIN-permission split).
        set_permissions_for_obj_to_user(cls.owner, cls.corpus, [PermissionTypes.CRUD])
        set_permissions_for_obj_to_user(cls.viewer, cls.corpus, [PermissionTypes.READ])

        # Public document — viewer can see at document level.
        cls.doc_public = Document.objects.create(
            title="Public Doc",
            creator=cls.owner,
            is_public=True,
            backend_lock=False,
        )
        # Private document — viewer has NO document-level access.
        cls.doc_private = Document.objects.create(
            title="Private Doc",
            creator=cls.owner,
            is_public=False,
            backend_lock=False,
        )

        # Link both documents to the corpus via DocumentPath (the
        # canonical corpus-membership row).
        DocumentPath.objects.create(
            document=cls.doc_public,
            corpus=cls.corpus,
            path="/public.pdf",
            is_current=True,
            is_deleted=False,
            version_number=1,
            creator=cls.owner,
        )
        DocumentPath.objects.create(
            document=cls.doc_private,
            corpus=cls.corpus,
            path="/private.pdf",
            is_current=True,
            is_deleted=False,
            version_number=1,
            creator=cls.owner,
        )

        # Labels — match the conventions the mutations use so the service
        # filter (``annotation_label__text__in=...``) hits the right rows.
        cls.country_label = AnnotationLabel.objects.create(
            text=OC_COUNTRY_LABEL,
            label_type=TOKEN_LABEL,
            creator=cls.owner,
            read_only=True,
        )
        cls.city_label = AnnotationLabel.objects.create(
            text=OC_CITY_LABEL,
            label_type=TOKEN_LABEL,
            creator=cls.owner,
            read_only=True,
        )

        # Annotations — mirror what the mutations write.
        France = {
            "canonical_name": "France",
            "lat": 46.227638,
            "lng": 2.213749,
            "admin_codes": {"iso_alpha2": "FR"},
            "geocoded": True,
        }
        Tokyo = {
            "canonical_name": "Tokyo",
            "lat": 35.6762,
            "lng": 139.6503,
            "admin_codes": {"iso_alpha2": "JP"},
            "geocoded": True,
        }
        FailedCity: dict[str, Any] = {
            "canonical_name": None,
            "lat": None,
            "lng": None,
            "admin_codes": {},
            "geocoded": False,
            "raw_text": "Zzzqqq",
        }

        cls.ann_country_public = Annotation.objects.create(
            page=0,
            raw_text="France",
            document=cls.doc_public,
            corpus=cls.corpus,
            annotation_label=cls.country_label,
            creator=cls.owner,
            annotation_type=TOKEN_LABEL,
            structural=True,
            data=France,
            json={"0": {"bounds": {}, "rawText": "France", "tokensJsons": []}},
        )
        cls.ann_country_private = Annotation.objects.create(
            page=0,
            raw_text="France",
            document=cls.doc_private,
            corpus=cls.corpus,
            annotation_label=cls.country_label,
            creator=cls.owner,
            annotation_type=TOKEN_LABEL,
            structural=True,
            data=France,
            json={"0": {"bounds": {}, "rawText": "France", "tokensJsons": []}},
        )
        cls.ann_city_tokyo = Annotation.objects.create(
            page=0,
            raw_text="Tokyo",
            document=cls.doc_public,
            corpus=cls.corpus,
            annotation_label=cls.city_label,
            creator=cls.owner,
            annotation_type=TOKEN_LABEL,
            structural=True,
            data=Tokyo,
            json={"0": {"bounds": {}, "rawText": "Tokyo", "tokensJsons": []}},
        )
        cls.ann_city_failed = Annotation.objects.create(
            page=0,
            raw_text="Zzzqqq",
            document=cls.doc_public,
            corpus=cls.corpus,
            annotation_label=cls.city_label,
            creator=cls.owner,
            annotation_type=TOKEN_LABEL,
            structural=True,
            data=FailedCity,
            json={"0": {"bounds": {}, "rawText": "Zzzqqq", "tokensJsons": []}},
        )


class GeographicAnnotationServiceCorpusTests(_GeoFixtureMixin, TestCase):
    """Corpus-scoped aggregation."""

    @classmethod
    def setUpTestData(cls):
        cls._build_geo_fixture()

    def test_owner_sees_all_pins(self):
        # Owner has CRUD on the corpus and creates both docs — should see
        # both countries collapsed into one pin (count=2) plus Tokyo.
        # The ungeocodable city must NOT contribute.
        pins = GeographicAnnotationService.aggregate_for_corpus(
            user=self.owner, corpus=self.corpus
        )
        by_name = {p.canonical_name: p for p in pins}
        self.assertIn("France", by_name)
        self.assertEqual(by_name["France"].document_count, 2)
        self.assertEqual(by_name["France"].label_type, "country")
        self.assertIn("Tokyo", by_name)
        self.assertEqual(by_name["Tokyo"].document_count, 1)
        # Failed geocode row must be excluded.
        self.assertNotIn(None, [p.canonical_name for p in pins])

    def test_viewer_min_permission_hides_private_doc_pin(self):
        # MIN(document, corpus): viewer can read the corpus but NOT
        # ``doc_private``. The France pin must show count=1 (only the
        # public-doc occurrence), not 2.
        pins = GeographicAnnotationService.aggregate_for_corpus(
            user=self.viewer, corpus=self.corpus
        )
        france_pins = [p for p in pins if p.canonical_name == "France"]
        self.assertEqual(len(france_pins), 1)
        # Critical: the private document does NOT appear in the count.
        self.assertEqual(france_pins[0].document_count, 1)

    def test_no_corpus_read_returns_empty(self):
        # An outsider with no corpus permissions gets an empty list,
        # NOT a permission error — IDOR-safe (same response as an empty
        # corpus).
        outsider = User.objects.create_user(username="outsider-svc", password="x")
        pins = GeographicAnnotationService.aggregate_for_corpus(
            user=outsider, corpus=self.corpus
        )
        self.assertEqual(pins, [])

    def test_bbox_filter_excludes_outside_pins(self):
        # Bbox covering Europe only — Tokyo (Asia) must be filtered out.
        europe = BBox(south=35.0, west=-10.0, north=60.0, east=30.0)
        pins = GeographicAnnotationService.aggregate_for_corpus(
            user=self.owner, corpus=self.corpus, bbox=europe
        )
        names = [p.canonical_name for p in pins]
        self.assertIn("France", names)
        self.assertNotIn("Tokyo", names)

    def test_label_types_filter(self):
        # ``label_types=["country"]`` → only OC_COUNTRY rows, no Tokyo.
        pins = GeographicAnnotationService.aggregate_for_corpus(
            user=self.owner, corpus=self.corpus, label_types=["country"]
        )
        self.assertEqual([p.canonical_name for p in pins], ["France"])

    def test_sample_document_ids_bounded(self):
        # Add a few more docs so the sample preview cap is exercised.
        # The constant is 5 in the service module.
        for i in range(7):
            doc = Document.objects.create(
                title=f"Extra doc {i}",
                creator=self.owner,
                is_public=True,
                backend_lock=False,
            )
            DocumentPath.objects.create(
                document=doc,
                corpus=self.corpus,
                path=f"/extra-{i}.pdf",
                is_current=True,
                is_deleted=False,
                version_number=1,
                creator=self.owner,
            )
            Annotation.objects.create(
                page=0,
                raw_text="France",
                document=doc,
                corpus=self.corpus,
                annotation_label=self.country_label,
                creator=self.owner,
                annotation_type=TOKEN_LABEL,
                structural=True,
                data={
                    "canonical_name": "France",
                    "lat": 46.227638,
                    "lng": 2.213749,
                    "admin_codes": {"iso_alpha2": "FR"},
                    "geocoded": True,
                },
                json={"0": {"bounds": {}, "rawText": "France", "tokensJsons": []}},
            )

        pins = GeographicAnnotationService.aggregate_for_corpus(
            user=self.owner, corpus=self.corpus, label_types=["country"]
        )
        france = next(p for p in pins if p.canonical_name == "France")
        # 2 originals + 7 extras = 9, but preview is capped at 5.
        self.assertGreaterEqual(france.document_count, 9)
        self.assertLessEqual(len(france.sample_document_ids), 5)


class GeographicAnnotationServiceGlobalTests(_GeoFixtureMixin, TestCase):
    """Global aggregation surface (Discover map)."""

    @classmethod
    def setUpTestData(cls):
        cls._build_geo_fixture()

    def test_owner_sees_pins_globally(self):
        # The global query simply intersects with visible annotations; the
        # owner can see everything in their own corpus, so the pins should
        # match the corpus-scoped view (minus the failed-geocode row).
        pins = GeographicAnnotationService.aggregate_global(user=self.owner)
        names = {p.canonical_name for p in pins}
        self.assertIn("France", names)
        self.assertIn("Tokyo", names)


class GeographicAnnotationServiceMiscTests(TestCase):
    """Smaller behaviours that don't need the full fixture."""

    def test_unknown_label_type_raises(self):
        # The service validates ``label_types`` so a typo (e.g. "city ") in
        # the GraphQL surface fails fast rather than silently returning all
        # rows.
        owner = User.objects.create_user(username="raise-owner", password="x")
        corpus = Corpus.objects.create(title="C", creator=owner)
        with self.assertRaises(ValueError):
            GeographicAnnotationService.aggregate_for_corpus(
                user=owner, corpus=corpus, label_types=["municipality"]
            )

    def test_empty_corpus_returns_empty_list(self):
        # No annotations → empty pin list, NOT an error.
        owner = User.objects.create_user(username="empty-owner", password="x")
        corpus = Corpus.objects.create(title="Empty", creator=owner)
        # Need a document for the corpus to be non-empty document-wise;
        # but here we want truly empty so don't add one.
        set_permissions_for_obj_to_user(owner, corpus, [PermissionTypes.CRUD])
        pins = GeographicAnnotationService.aggregate_for_corpus(
            user=owner, corpus=corpus
        )
        self.assertEqual(pins, [])

    def test_antimeridian_crossing_bbox(self):
        # A bbox crossing the antimeridian: west=170, east=-170 means
        # "from 170°E eastward through 180° to -170°W" — i.e. the strip
        # around the Pacific dateline. Two points: 175°E (in box) and
        # 0° (out of box).
        from opencontractserver.annotations.services.geographic_service import (
            _bbox_contains,
        )

        box = BBox(south=-30.0, west=170.0, north=30.0, east=-170.0)
        self.assertTrue(_bbox_contains(box, 0.0, 175.0))  # 175E in box
        self.assertTrue(_bbox_contains(box, 0.0, -175.0))  # 175W in box
        self.assertFalse(_bbox_contains(box, 0.0, 0.0))  # 0° out
        self.assertFalse(_bbox_contains(box, 50.0, 175.0))  # lat outside

    def test_normal_bbox_does_not_match_outside(self):
        from opencontractserver.annotations.services.geographic_service import (
            _bbox_contains,
        )

        # Europe-ish box. The dateline-crossing path should not fire.
        box = BBox(south=35.0, west=-10.0, north=60.0, east=30.0)
        self.assertTrue(_bbox_contains(box, 48.0, 2.0))  # Paris
        self.assertFalse(_bbox_contains(box, 35.0, 139.0))  # Tokyo

    def test_degenerate_bbox_raises(self):
        # ``south > north`` is degenerate — would silently match nothing and
        # produce a confusing empty-list result. Reject at construction.
        # Longitude is intentionally NOT validated (``west > east`` is the
        # antimeridian-crossing case and must remain legal).
        with self.assertRaises(ValueError):
            BBox(south=60.0, west=-10.0, north=35.0, east=30.0)
        # Equal south/north (a zero-height strip) is still legal — only
        # strict south > north fails.
        BBox(south=50.0, west=-10.0, north=50.0, east=30.0)


class GeographicQueryResolverErrorTests(TestCase):
    """The GraphQL resolvers must wrap the service's ``ValueError`` for an
    unknown ``label_types`` entry as a ``GraphQLError`` rather than letting
    it bubble up as an unhandled 500. Added in response to PR #1823 review.
    """

    def test_corpus_resolver_returns_graphql_error_on_bad_label_type(self):
        from graphene.test import Client
        from graphql_relay import to_global_id

        from config.graphql.schema import schema

        owner = User.objects.create_user(username="resolver-owner", password="x")
        corpus = Corpus.objects.create(title="resolver-c", creator=owner)
        set_permissions_for_obj_to_user(owner, corpus, [PermissionTypes.CRUD])

        class _Ctx:
            def __init__(self, u):
                self.user = u
                self.META = {}
                self.method = "POST"

        client: Any = Client(schema)
        result = client.execute(
            """
            query Q($id: ID!, $lt: [String]) {
              geographicAnnotationsForCorpus(corpusId: $id, labelTypes: $lt) {
                canonicalName
              }
            }
            """,
            variables={
                "id": to_global_id("CorpusType", corpus.pk),
                "lt": ["municipality"],
            },
            context_value=_Ctx(owner),
        )
        # The resolver MUST surface a clean GraphQL error (not an unhandled
        # ``ValueError``) and MUST NOT return data for the field.
        self.assertIn("errors", result)
        self.assertTrue(any("municipality" in str(e) for e in result["errors"]))

    def test_global_resolver_returns_graphql_error_on_bad_label_type(self):
        from graphene.test import Client

        from config.graphql.schema import schema

        owner = User.objects.create_user(username="resolver-owner-g", password="x")

        class _Ctx:
            def __init__(self, u):
                self.user = u
                self.META = {}
                self.method = "POST"

        client: Any = Client(schema)
        result = client.execute(
            """
            query Q($lt: [String]) {
              globalGeographicAnnotations(labelTypes: $lt) {
                canonicalName
              }
            }
            """,
            variables={"lt": ["municipality"]},
            context_value=_Ctx(owner),
        )
        self.assertIn("errors", result)
        self.assertTrue(any("municipality" in str(e) for e in result["errors"]))
