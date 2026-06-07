"""
Tests for the pipeline component registry.

Tests the cached registry pattern that provides efficient access to
pipeline components (parsers, embedders, thumbnailers, post-processors).
"""

from unittest.mock import patch

from django.test import TestCase

from opencontractserver.pipeline.base.file_types import (
    FILE_TYPE_TO_MIME,
    FileTypeEnum,
)
from opencontractserver.pipeline.registry import (
    ComponentType,
    PipelineComponentDefinition,
    PipelineComponentRegistry,
    get_all_components_cached,
    get_all_embedders_cached,
    get_all_enrichers_cached,
    get_all_parsers_cached,
    get_all_post_processors_cached,
    get_all_thumbnailers_cached,
    get_allowed_mime_types,
    get_component_by_name_cached,
    get_components_by_mimetype_cached,
    get_registry,
    get_supported_mime_types,
    reset_registry,
)


class TestPipelineComponentDefinition(TestCase):
    """Tests for PipelineComponentDefinition dataclass."""

    def test_to_dict_basic(self):
        """Test basic conversion to dictionary."""
        defn = PipelineComponentDefinition(
            name="TestParser",
            class_name="test.module.TestParser",
            component_type=ComponentType.PARSER,
            title="Test Parser",
            module_name="test_module",
            description="A test parser",
            author="Test Author",
            dependencies=("dep1", "dep2"),
            supported_file_types=("application/pdf",),
            input_schema={"type": "object"},
        )

        result = defn.to_dict()

        self.assertEqual(result["name"], "TestParser")
        self.assertEqual(result["class_name"], "test.module.TestParser")
        self.assertEqual(result["component_type"], "parser")
        self.assertEqual(result["title"], "Test Parser")
        self.assertEqual(result["dependencies"], ["dep1", "dep2"])
        self.assertEqual(result["supported_file_types"], ["application/pdf"])
        self.assertNotIn("vector_size", result)

    def test_to_dict_with_vector_size(self):
        """Test that embedders include vector_size."""
        defn = PipelineComponentDefinition(
            name="TestEmbedder",
            class_name="test.module.TestEmbedder",
            component_type=ComponentType.EMBEDDER,
            title="Test Embedder",
            module_name="test_module",
            description="A test embedder",
            author="Test Author",
            dependencies=(),
            supported_file_types=(),
            vector_size=768,
        )

        result = defn.to_dict()

        self.assertEqual(result["vector_size"], 768)

    def test_frozen_dataclass(self):
        """Test that definition is immutable."""
        defn = PipelineComponentDefinition(
            name="TestParser",
            class_name="test.module.TestParser",
            component_type=ComponentType.PARSER,
            title="Test Parser",
            module_name="test_module",
            description="A test parser",
            author="Test Author",
            dependencies=(),
            supported_file_types=(),
        )

        with self.assertRaises(Exception):
            defn.name = "ChangedName"  # type: ignore[misc]  # read-only property


class TestPipelineComponentRegistry(TestCase):
    """Tests for PipelineComponentRegistry singleton."""

    def setUp(self):
        """Reset registry before each test."""
        reset_registry()

    def tearDown(self):
        """Reset registry after each test."""
        reset_registry()

    def test_singleton_pattern(self):
        """Test that registry is a singleton."""
        registry1 = get_registry()
        registry2 = get_registry()
        self.assertIs(registry1, registry2)

    def test_registry_has_parsers(self):
        """Test that registry discovers parsers."""
        registry = get_registry()
        self.assertIsInstance(registry.parsers, tuple)
        # Should have at least one parser (DoclingParser, LlamaParseParser, etc.)
        self.assertGreater(len(registry.parsers), 0)

    def test_registry_has_embedders(self):
        """Test that registry discovers embedders."""
        registry = get_registry()
        self.assertIsInstance(registry.embedders, tuple)
        # Should have at least one embedder
        self.assertGreater(len(registry.embedders), 0)

    def test_registry_has_thumbnailers(self):
        """Test that registry discovers thumbnailers."""
        registry = get_registry()
        self.assertIsInstance(registry.thumbnailers, tuple)
        # Should have at least one thumbnailer
        self.assertGreater(len(registry.thumbnailers), 0)

    def test_get_by_name(self):
        """Test looking up component by name."""
        registry = get_registry()
        # Get first parser name
        if registry.parsers:
            parser_name = registry.parsers[0].name
            result = registry.get_by_name(parser_name)
            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result.name, parser_name)

    def test_get_by_name_not_found(self):
        """Test looking up non-existent component."""
        registry = get_registry()
        result = registry.get_by_name("NonExistentParser")
        self.assertIsNone(result)

    def test_get_by_class_name(self):
        """Test looking up component by full class name."""
        registry = get_registry()
        if registry.parsers:
            class_name = registry.parsers[0].class_name
            result = registry.get_by_class_name(class_name)
            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result.class_name, class_name)

    def test_get_parsers_for_filetype_pdf(self):
        """Test getting parsers for PDF files."""
        registry = get_registry()
        # FileTypeEnum.PDF.value is "pdf", not the MIME type
        pdf_parsers = registry.get_parsers_for_filetype("pdf")
        self.assertIsInstance(pdf_parsers, list)
        # Should have at least one PDF parser
        self.assertGreater(len(pdf_parsers), 0)

    def test_get_parsers_for_filetype_unknown(self):
        """Test getting parsers for unknown file type."""
        registry = get_registry()
        result = registry.get_parsers_for_filetype("application/unknown")
        self.assertEqual(result, [])


class TestModuleLevelFunctions(TestCase):
    """Tests for module-level convenience functions."""

    def setUp(self):
        """Reset registry before each test."""
        reset_registry()

    def tearDown(self):
        """Reset registry after each test."""
        reset_registry()

    def test_get_all_parsers_cached(self):
        """Test cached parser retrieval."""
        parsers = get_all_parsers_cached()
        self.assertIsInstance(parsers, tuple)
        self.assertGreater(len(parsers), 0)
        # All should be PipelineComponentDefinition
        for p in parsers:
            self.assertIsInstance(p, PipelineComponentDefinition)
            self.assertEqual(p.component_type, ComponentType.PARSER)

    def test_get_all_embedders_cached(self):
        """Test cached embedder retrieval."""
        embedders = get_all_embedders_cached()
        self.assertIsInstance(embedders, tuple)
        self.assertGreater(len(embedders), 0)
        for e in embedders:
            self.assertIsInstance(e, PipelineComponentDefinition)
            self.assertEqual(e.component_type, ComponentType.EMBEDDER)

    def test_get_all_thumbnailers_cached(self):
        """Test cached thumbnailer retrieval."""
        thumbnailers = get_all_thumbnailers_cached()
        self.assertIsInstance(thumbnailers, tuple)
        for t in thumbnailers:
            self.assertIsInstance(t, PipelineComponentDefinition)
            self.assertEqual(t.component_type, ComponentType.THUMBNAILER)

    def test_get_all_post_processors_cached(self):
        """Test cached post-processor retrieval."""
        post_processors = get_all_post_processors_cached()
        self.assertIsInstance(post_processors, tuple)
        for p in post_processors:
            self.assertIsInstance(p, PipelineComponentDefinition)
            self.assertEqual(p.component_type, ComponentType.POST_PROCESSOR)

    def test_get_component_by_name_cached(self):
        """Test cached component lookup by name."""
        # First, get a known parser name
        parsers = get_all_parsers_cached()
        if parsers:
            parser_name = parsers[0].name
            result = get_component_by_name_cached(parser_name)
            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result.name, parser_name)

    def test_get_components_by_mimetype_cached_pdf(self):
        """Test getting components for PDF MIME type."""
        result = get_components_by_mimetype_cached("application/pdf")

        self.assertIn("parsers", result)
        self.assertIn("embedders", result)
        self.assertIn("thumbnailers", result)
        self.assertIn("post_processors", result)

        # Should have PDF-compatible parsers
        self.assertGreater(len(result["parsers"]), 0)

    def test_get_all_components_cached(self):
        """Test getting all components grouped by type."""
        result = get_all_components_cached()

        self.assertIn("parsers", result)
        self.assertIn("embedders", result)
        self.assertIn("thumbnailers", result)
        self.assertIn("post_processors", result)

        # Each should be a tuple
        self.assertIsInstance(result["parsers"], tuple)
        self.assertIsInstance(result["embedders"], tuple)

    def test_caching_is_effective(self):
        """Test that registry is only initialized once."""
        # Get first registry
        reset_registry()
        registry1 = get_registry()

        # Get second registry - should be same instance
        registry2 = get_registry()

        # Singleton should return same instance
        self.assertIs(registry1, registry2)

    def test_reset_registry(self):
        """Test that reset_registry clears the singleton."""
        _ = get_registry()  # First access
        reset_registry()
        registry_after_reset = get_registry()
        # Should be a new instance after reset
        self.assertIsNotNone(registry_after_reset)


class TestRegistryPerformance(TestCase):
    """Tests for registry performance characteristics."""

    def setUp(self):
        """Reset registry before each test."""
        reset_registry()

    def tearDown(self):
        """Reset registry after each test."""
        reset_registry()

    def test_subsequent_access_is_fast(self):
        """Test that subsequent registry access doesn't re-scan."""
        import time

        # First access (cold)
        start = time.perf_counter()
        _ = get_registry()
        first_access = time.perf_counter() - start

        # Multiple subsequent accesses (should be near-instant)
        total_subsequent = 0.0
        for _ in range(100):
            start = time.perf_counter()
            _ = get_registry()
            total_subsequent += time.perf_counter() - start

        avg_subsequent = total_subsequent / 100

        # Subsequent accesses should be much faster than first
        # (This is more of a sanity check than a strict assertion)
        self.assertLess(
            avg_subsequent,
            first_access * 0.1,  # At least 10x faster
            "Subsequent access should be much faster than first access",
        )


class TestDefinitionSettingsSchema(TestCase):
    """Tests for settings_schema in PipelineComponentDefinition."""

    def test_to_dict_includes_settings_schema(self):
        """to_dict() includes settings_schema in output."""
        defn = PipelineComponentDefinition(
            name="TestParser",
            class_name="test.module.TestParser",
            component_type=ComponentType.PARSER,
            title="Test Parser",
            module_name="test_module",
            description="A test parser",
            author="Test Author",
            dependencies=(),
            supported_file_types=(),
            settings_schema=({"name": "api_key", "type": "secret", "required": True},),
        )
        result = defn.to_dict()
        self.assertEqual(
            result["settings_schema"],
            [{"name": "api_key", "type": "secret", "required": True}],
        )

    def test_to_dict_empty_settings_schema(self):
        """to_dict() includes empty settings_schema by default."""
        defn = PipelineComponentDefinition(
            name="TestParser",
            class_name="test.module.TestParser",
            component_type=ComponentType.PARSER,
            title="Test Parser",
            module_name="test_module",
            description="A test parser",
            author="Test Author",
            dependencies=(),
            supported_file_types=(),
        )
        result = defn.to_dict()
        self.assertEqual(result["settings_schema"], [])


class TestCreateDefinitionSettingsSchemaError(TestCase):
    """Tests for the exception path in _create_definition settings_schema extraction."""

    def setUp(self):
        reset_registry()

    def tearDown(self):
        reset_registry()

    def test_create_definition_handles_settings_schema_exception(self):
        """_create_definition gracefully handles errors extracting settings_schema."""
        registry = PipelineComponentRegistry.__new__(PipelineComponentRegistry)
        # Initialize minimal state to call _create_definition
        registry._by_name = {}
        registry._by_class_name = {}

        # Create a dummy class with a broken Settings that causes get_settings_schema
        # to raise
        class BrokenSettingsComponent:
            __module__ = "test.module"
            supported_file_types = []
            supported_modalities = set()

        with patch(
            "opencontractserver.pipeline.base.settings_schema.get_settings_schema",
            side_effect=Exception("Schema extraction failed"),
        ):
            defn = registry._create_definition(
                BrokenSettingsComponent, ComponentType.PARSER
            )
            # Should still return a definition with empty settings_schema
            self.assertEqual(defn.settings_schema, ())
            self.assertEqual(defn.name, "BrokenSettingsComponent")


class TestSupportedMimeTypes(TestCase):
    """Tests for get_supported_mime_types() and get_allowed_mime_types()."""

    def setUp(self):
        reset_registry()

    def tearDown(self):
        reset_registry()

    def test_get_supported_mime_types_returns_all_file_types(self):
        """Every FileTypeEnum member should appear in the result."""
        from opencontractserver.pipeline.base.file_types import FileTypeEnum

        result = get_supported_mime_types()
        file_types = {entry["file_type"] for entry in result}
        for ft in FileTypeEnum:
            self.assertIn(ft.value, file_types)

    def test_get_supported_mime_types_structure(self):
        """Each entry should have the expected keys and types."""
        result = get_supported_mime_types()
        for entry in result:
            self.assertIn("mimetype", entry)
            self.assertIn("file_type", entry)
            self.assertIn("label", entry)
            self.assertIn("fully_supported", entry)
            self.assertIn("stage_coverage", entry)
            self.assertIsInstance(entry["fully_supported"], bool)
            self.assertIn("parser", entry["stage_coverage"])
            self.assertIn("embedder", entry["stage_coverage"])
            self.assertIn("thumbnailer", entry["stage_coverage"])

    def test_get_supported_mime_types_pdf_has_parser(self):
        """PDF should have at least one parser available.

        Registers a minimal mock parser so the test is self-contained rather
        than relying on a specific parser being installed in the test env.
        """
        registry = get_registry()
        mock_parser = PipelineComponentDefinition(
            name="MockPdfParser",
            class_name="tests.MockPdfParser",
            component_type=ComponentType.PARSER,
            title="Mock PDF Parser",
            module_name="mock",
            description="Mock parser for test",
            author="test",
            dependencies=(),
            supported_file_types=("pdf",),
        )
        registry._parsers_by_filetype.setdefault("pdf", []).append(mock_parser)
        get_supported_mime_types.cache_clear()

        result = get_supported_mime_types()
        by_file_type = {e["file_type"]: e for e in result}
        self.assertIn("pdf", by_file_type)
        self.assertTrue(by_file_type["pdf"]["stage_coverage"]["parser"])

    def test_get_allowed_mime_types_returns_sequence(self):
        """get_allowed_mime_types should return a sequence of MIME type strings."""
        allowed = get_allowed_mime_types()
        self.assertIsInstance(allowed, (list, tuple))
        for mime in allowed:
            self.assertIsInstance(mime, str)
            self.assertIn("/", mime)

    def test_get_allowed_mime_types_includes_legacy_aliases(self):
        """Legacy MIME aliases should be included if their canonical type is supported.

        Registers a mock parser and embedder for txt so the non-fallback path
        runs and legacy alias expansion (application/txt → text/plain) is tested.
        """
        registry = get_registry()

        mock_parser = PipelineComponentDefinition(
            name="MockTxtParser",
            class_name="tests.MockTxtParser",
            component_type=ComponentType.PARSER,
            title="Mock TXT Parser",
            module_name="mock",
            description="Mock parser for test",
            author="test",
            dependencies=(),
            supported_file_types=("txt",),
        )
        registry._parsers_by_filetype.setdefault("txt", []).append(mock_parser)

        mock_embedder = PipelineComponentDefinition(
            name="MockEmbedder",
            class_name="tests.MockEmbedder",
            component_type=ComponentType.EMBEDDER,
            title="Mock Embedder",
            module_name="mock",
            description="Mock embedder for test",
            author="test",
            dependencies=(),
            supported_file_types=(),
        )
        registry._embedders = registry._embedders + (mock_embedder,)

        get_supported_mime_types.cache_clear()
        get_allowed_mime_types.cache_clear()

        allowed = get_allowed_mime_types()
        self.assertIn("text/plain", allowed)
        self.assertIn("application/txt", allowed)

    def test_fully_supported_requires_parser_and_embedder(self):
        """A file type is fully_supported if it has a parser and embedder.

        Thumbnailer is optional — file types without a thumbnailer (e.g. DOCX)
        are still uploadable and processable.
        """
        result = get_supported_mime_types()
        for entry in result:
            coverage = entry["stage_coverage"]
            expected = coverage["parser"] and coverage["embedder"]
            self.assertEqual(
                entry["fully_supported"],
                expected,
                f"fully_supported mismatch for {entry['file_type']}: "
                f"coverage={coverage}, fully_supported={entry['fully_supported']}",
            )

    def test_get_components_by_mimetype_cached_unknown_mime(self):
        """Unknown MIME type returns empty component lists."""
        result = get_components_by_mimetype_cached("application/x-unknown-test")
        self.assertEqual(result["parsers"], [])
        self.assertEqual(result["embedders"], [])
        self.assertEqual(result["thumbnailers"], [])
        self.assertEqual(result["post_processors"], [])

    def test_get_supported_mime_types_skips_unmapped_filetype(self):
        """FileTypeEnum members without a MIME mapping are skipped with a warning."""
        get_supported_mime_types.cache_clear()
        with patch.dict(FILE_TYPE_TO_MIME, {"pdf": "application/pdf"}, clear=True):
            get_supported_mime_types.cache_clear()
            result = get_supported_mime_types()
            file_types = {entry["file_type"] for entry in result}
            # Only "pdf" should be present since we cleared all other mappings
            self.assertIn("pdf", file_types)
            self.assertNotIn("txt", file_types)
            self.assertNotIn("docx", file_types)

    def test_get_allowed_mime_types_falls_back_when_empty(self):
        """When no components are registered, fall back to settings."""
        from django.conf import settings

        get_supported_mime_types.cache_clear()
        get_allowed_mime_types.cache_clear()

        # Mock get_supported_mime_types to return entries with no fully_supported
        with patch(
            "opencontractserver.pipeline.registry.get_supported_mime_types",
            return_value=tuple(
                [
                    {
                        "mimetype": "application/pdf",
                        "file_type": "pdf",
                        "label": "PDF",
                        "fully_supported": False,
                        "stage_coverage": {
                            "parser": False,
                            "embedder": False,
                            "thumbnailer": False,
                        },
                    }
                ]
            ),
        ):
            get_allowed_mime_types.cache_clear()
            result = get_allowed_mime_types()
            # Should fall back to settings.ALLOWED_DOCUMENT_MIMETYPES
            expected = tuple(getattr(settings, "ALLOWED_DOCUMENT_MIMETYPES", []))
            self.assertEqual(result, expected)
            self.assertTrue(len(result) > 0)


class TestFileTypeEnum(TestCase):
    """Tests for FileTypeEnum methods and properties."""

    def test_from_mimetype_known(self):
        """from_mimetype returns correct enum for known MIME types."""
        self.assertEqual(
            FileTypeEnum.from_mimetype("application/pdf"), FileTypeEnum.PDF
        )
        self.assertEqual(FileTypeEnum.from_mimetype("text/plain"), FileTypeEnum.TXT)

    def test_from_mimetype_unknown(self):
        """from_mimetype returns None for unknown MIME types."""
        self.assertIsNone(FileTypeEnum.from_mimetype("application/x-nonexistent"))

    def test_from_mimetype_legacy_alias(self):
        """from_mimetype resolves legacy MIME aliases."""
        result = FileTypeEnum.from_mimetype("application/txt")
        self.assertEqual(result, FileTypeEnum.TXT)

    def test_mimetype_property(self):
        """mimetype property returns canonical MIME type string."""
        self.assertEqual(FileTypeEnum.PDF.mimetype, "application/pdf")
        self.assertEqual(FileTypeEnum.TXT.mimetype, "text/plain")
        self.assertEqual(
            FileTypeEnum.DOCX.mimetype,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

    def test_label_property(self):
        """label property returns human-readable labels."""
        self.assertEqual(FileTypeEnum.PDF.label, "PDF")
        self.assertEqual(FileTypeEnum.TXT.label, "Plain Text")
        self.assertEqual(FileTypeEnum.DOCX.label, "Word Document")


class TestEnricherRegistry(TestCase):
    """Tests that the registry discovers ingest-time enrichers."""

    def setUp(self):
        reset_registry()

    def tearDown(self):
        reset_registry()

    def test_component_type_has_enricher(self):
        """The ENRICHER component type is defined."""
        self.assertEqual(ComponentType.ENRICHER.value, "enricher")

    def test_pdf_outline_enricher_discovered(self):
        """PdfOutlineEnricher is auto-discovered as an ENRICHER component."""
        enrichers = get_all_enrichers_cached()
        self.assertIsInstance(enrichers, tuple)
        self.assertIn("PdfOutlineEnricher", {e.name for e in enrichers})
        for enricher in enrichers:
            self.assertEqual(enricher.component_type, ComponentType.ENRICHER)

    def test_enrichers_for_pdf_filetype(self):
        """PdfOutlineEnricher is registered for the PDF file type."""
        registry = get_registry()
        pdf_enrichers = registry.get_enrichers_for_filetype("pdf")
        self.assertIn("PdfOutlineEnricher", {e.name for e in pdf_enrichers})

    def test_get_by_name_resolves_enricher(self):
        """The enricher is resolvable by class name through the registry."""
        defn = get_registry().get_by_name("PdfOutlineEnricher")
        self.assertIsNotNone(defn)
        assert defn is not None
        self.assertEqual(defn.component_type, ComponentType.ENRICHER)

    def test_components_by_mimetype_includes_enrichers(self):
        """get_components_by_mimetype_cached exposes an 'enrichers' key."""
        result = get_components_by_mimetype_cached("application/pdf")
        self.assertIn("enrichers", result)
        self.assertIn("PdfOutlineEnricher", {e.name for e in result["enrichers"]})
        # Unknown MIME types still return the key (as an empty list).
        unknown = get_components_by_mimetype_cached("application/x-nope-test")
        self.assertEqual(unknown["enrichers"], [])

    def test_all_components_includes_enrichers(self):
        """get_all_components_cached groups enrichers under 'enrichers'."""
        result = get_all_components_cached()
        self.assertIn("enrichers", result)
        self.assertIsInstance(result["enrichers"], tuple)
