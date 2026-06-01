"""
Tests for the types module: enums and TypedDict structures.

Covers enum values, choices(), and ContentModality conversion methods.
"""

from django.test import TestCase

from opencontractserver.types.enums import (
    AnnotationFilterMode,
    ContentModality,
    ExportType,
    JobStatus,
    LabelType,
    PermissionTypes,
)


class TestOpenContractsEnum(TestCase):
    """Tests for OpenContractsEnum base class."""

    def test_choices_returns_list_of_tuples(self):
        choices = ExportType.choices()
        self.assertIsInstance(choices, list)
        for item in choices:
            self.assertIsInstance(item, tuple)
            self.assertEqual(len(item), 2)

    def test_choices_value_name_format(self):
        choices = ExportType.choices()
        values = {c[0] for c in choices}
        names = {c[1] for c in choices}
        self.assertIn("LANGCHAIN", values)
        self.assertIn("LANGCHAIN", names)


class TestExportType(TestCase):
    """Tests for ExportType enum."""

    def test_values(self):
        self.assertEqual(ExportType.LANGCHAIN.value, "LANGCHAIN")
        self.assertEqual(ExportType.OPEN_CONTRACTS.value, "OPEN_CONTRACTS")
        self.assertEqual(ExportType.OPEN_CONTRACTS_V2.value, "OPEN_CONTRACTS_V2")
        self.assertEqual(ExportType.FUNSD.value, "FUNSD")

    def test_is_string_enum(self):
        self.assertIsInstance(ExportType.LANGCHAIN, str)

    def test_member_count(self):
        self.assertEqual(len(ExportType), 4)

    def test_choices_count(self):
        self.assertEqual(len(ExportType.choices()), 4)


class TestLabelType(TestCase):
    """Tests for LabelType enum."""

    def test_values(self):
        self.assertEqual(LabelType.DOC_TYPE_LABEL.value, "DOC_TYPE_LABEL")
        self.assertEqual(LabelType.TOKEN_LABEL.value, "TOKEN_LABEL")
        self.assertEqual(LabelType.RELATIONSHIP_LABEL.value, "RELATIONSHIP_LABEL")
        self.assertEqual(LabelType.SPAN_LABEL.value, "SPAN_LABEL")

    def test_is_string_enum(self):
        self.assertIsInstance(LabelType.DOC_TYPE_LABEL, str)

    def test_member_count(self):
        self.assertEqual(len(LabelType), 4)


class TestJobStatus(TestCase):
    """Tests for JobStatus enum."""

    def test_values(self):
        self.assertEqual(JobStatus.CREATED.value, "CREATED")
        self.assertEqual(JobStatus.QUEUED.value, "QUEUED")
        self.assertEqual(JobStatus.RUNNING.value, "RUNNING")
        self.assertEqual(JobStatus.COMPLETED.value, "COMPLETED")
        self.assertEqual(JobStatus.FAILED.value, "FAILED")
        # ``CANCELLED`` added with deep-research agent — long-running jobs
        # need a cooperative-cancel terminal state distinct from FAILED.
        self.assertEqual(JobStatus.CANCELLED.value, "CANCELLED")

    def test_is_string_enum(self):
        self.assertIsInstance(JobStatus.CREATED, str)

    def test_member_count(self):
        self.assertEqual(len(JobStatus), 6)

    def test_choices(self):
        choices = JobStatus.choices()
        self.assertIsInstance(choices, list)
        self.assertEqual(len(choices), 6)
        # JobStatus.choices uses (key, key) format
        for key, value in choices:
            self.assertIsNotNone(key)
            self.assertIsNotNone(value)


class TestPermissionTypes(TestCase):
    """Tests for PermissionTypes enum."""

    def test_values(self):
        expected = {
            "CREATE",
            "READ",
            "EDIT",
            "UPDATE",
            "DELETE",
            "COMMENT",
            "PERMISSION",
            "PUBLISH",
            "CRUD",
            "ALL",
        }
        actual = {pt.value for pt in PermissionTypes}
        self.assertEqual(actual, expected)

    def test_is_string_enum(self):
        self.assertIsInstance(PermissionTypes.READ, str)

    def test_member_count(self):
        self.assertEqual(len(PermissionTypes), 10)


class TestAnnotationFilterMode(TestCase):
    """Tests for AnnotationFilterMode enum."""

    def test_values(self):
        self.assertEqual(
            AnnotationFilterMode.CORPUS_LABELSET_ONLY.value,
            "CORPUS_LABELSET_ONLY",
        )
        self.assertEqual(
            AnnotationFilterMode.CORPUS_LABELSET_PLUS_ANALYSES.value,
            "CORPUS_LABELSET_PLUS_ANALYSES",
        )
        self.assertEqual(
            AnnotationFilterMode.ANALYSES_ONLY.value,
            "ANALYSES_ONLY",
        )

    def test_member_count(self):
        self.assertEqual(len(AnnotationFilterMode), 3)

    def test_is_string_enum(self):
        # AnnotationFilterMode must be a str-mixin enum so a member and its
        # string value compare equal — build_label_lookups / build_document_export
        # rely on this for the string values delivered by GraphQL/Celery (#1868).
        self.assertIsInstance(AnnotationFilterMode.CORPUS_LABELSET_ONLY, str)
        self.assertEqual(
            AnnotationFilterMode.CORPUS_LABELSET_ONLY, "CORPUS_LABELSET_ONLY"
        )
        self.assertEqual(
            AnnotationFilterMode("ANALYSES_ONLY"), AnnotationFilterMode.ANALYSES_ONLY
        )


class TestContentModality(TestCase):
    """Tests for ContentModality enum and its conversion methods."""

    def test_values(self):
        self.assertEqual(ContentModality.TEXT.value, "TEXT")
        self.assertEqual(ContentModality.IMAGE.value, "IMAGE")
        self.assertEqual(ContentModality.AUDIO.value, "AUDIO")
        self.assertEqual(ContentModality.TABLE.value, "TABLE")
        self.assertEqual(ContentModality.VIDEO.value, "VIDEO")

    def test_is_string_enum(self):
        self.assertIsInstance(ContentModality.TEXT, str)

    def test_member_count(self):
        self.assertEqual(len(ContentModality), 5)

    def test_choices(self):
        choices = ContentModality.choices()
        self.assertIsInstance(choices, list)
        self.assertEqual(len(choices), 5)
        for value, name in choices:
            self.assertIsInstance(value, str)
            self.assertIsInstance(name, str)

    # from_string tests
    def test_from_string_valid(self):
        self.assertEqual(ContentModality.from_string("TEXT"), ContentModality.TEXT)
        self.assertEqual(ContentModality.from_string("IMAGE"), ContentModality.IMAGE)

    def test_from_string_case_insensitive(self):
        self.assertEqual(ContentModality.from_string("text"), ContentModality.TEXT)
        self.assertEqual(ContentModality.from_string("Image"), ContentModality.IMAGE)

    def test_from_string_invalid(self):
        with self.assertRaises(ValueError) as ctx:
            ContentModality.from_string("INVALID")
        self.assertIn("Unknown modality", str(ctx.exception))
        self.assertIn("INVALID", str(ctx.exception))

    def test_from_string_empty(self):
        with self.assertRaises(ValueError):
            ContentModality.from_string("")

    # from_strings tests
    def test_from_strings_valid(self):
        result = ContentModality.from_strings(["TEXT", "IMAGE"])
        self.assertEqual(result, {ContentModality.TEXT, ContentModality.IMAGE})

    def test_from_strings_empty_list(self):
        result = ContentModality.from_strings([])
        self.assertEqual(result, set())

    def test_from_strings_single(self):
        result = ContentModality.from_strings(["TEXT"])
        self.assertEqual(result, {ContentModality.TEXT})

    def test_from_strings_all(self):
        result = ContentModality.from_strings(
            ["TEXT", "IMAGE", "AUDIO", "TABLE", "VIDEO"]
        )
        self.assertEqual(len(result), 5)

    def test_from_strings_invalid_raises(self):
        with self.assertRaises(ValueError):
            ContentModality.from_strings(["TEXT", "INVALID"])

    # to_strings tests
    def test_to_strings(self):
        result = ContentModality.to_strings(
            {ContentModality.TEXT, ContentModality.IMAGE}
        )
        self.assertIsInstance(result, list)
        self.assertEqual(set(result), {"TEXT", "IMAGE"})

    def test_to_strings_empty_set(self):
        result = ContentModality.to_strings(set())
        self.assertEqual(result, [])

    def test_to_strings_single(self):
        result = ContentModality.to_strings({ContentModality.TEXT})
        self.assertEqual(result, ["TEXT"])

    # Round-trip tests
    def test_roundtrip_from_to_strings(self):
        original = ["TEXT", "IMAGE", "AUDIO"]
        modalities = ContentModality.from_strings(original)
        back = ContentModality.to_strings(modalities)
        self.assertEqual(set(back), set(original))


class TestTypedDictStructures(TestCase):
    """Tests that TypedDict classes can be instantiated with proper fields."""

    def test_bounding_box_type(self):
        from opencontractserver.types.dicts import BoundingBoxPythonType

        box: BoundingBoxPythonType = {
            "top": 10,
            "bottom": 100,
            "left": 20,
            "right": 200,
        }
        self.assertEqual(box["top"], 10)
        self.assertEqual(box["bottom"], 100)

    def test_annotation_label_type(self):
        from opencontractserver.types.dicts import AnnotationLabelPythonType

        label: AnnotationLabelPythonType = {
            "id": "1",
            "color": "#FF0000",
            "description": "Test label",
            "icon": "tag",
            "text": "Label",
            "label_type": "TOKEN_LABEL",
        }
        self.assertEqual(label["text"], "Label")
        self.assertEqual(label["label_type"], "TOKEN_LABEL")

    def test_pawls_token_type(self):
        from opencontractserver.types.dicts import PawlsTokenPythonType

        token: PawlsTokenPythonType = {
            "x": 10.0,
            "y": 20.0,
            "width": 50.0,
            "height": 12.0,
            "text": "hello",
        }
        self.assertEqual(token["text"], "hello")
        self.assertEqual(token["x"], 10.0)

    def test_token_id_type(self):
        from opencontractserver.types.dicts import TokenIdPythonType

        token_id: TokenIdPythonType = {
            "pageIndex": 0,
            "tokenIndex": 5,
        }
        self.assertEqual(token_id["pageIndex"], 0)
        self.assertEqual(token_id["tokenIndex"], 5)

    def test_text_span_data(self):
        from opencontractserver.types.dicts import TextSpanData

        span: TextSpanData = {
            "start": 0,
            "end": 10,
            "text": "sample text",
        }
        self.assertEqual(span["start"], 0)
        self.assertEqual(span["end"], 10)

    def test_pawls_page_boundary_type(self):
        from opencontractserver.types.dicts import PawlsPageBoundaryPythonType

        boundary: PawlsPageBoundaryPythonType = {
            "width": 612.0,
            "height": 792.0,
            "index": 0,
        }
        self.assertEqual(boundary["width"], 612.0)
        self.assertEqual(boundary["index"], 0)

    def test_open_contracts_corpus_type(self):
        from opencontractserver.types.dicts import OpenContractCorpusType

        corpus: OpenContractCorpusType = {
            "id": "corpus-1",
            "title": "Test Corpus",
            "description": "A test corpus",
            "icon_data": None,
            "icon_name": None,
            "creator": "user1",
            "label_set": "labelset-1",
        }
        self.assertEqual(corpus["title"], "Test Corpus")
        self.assertEqual(corpus["id"], "corpus-1")
