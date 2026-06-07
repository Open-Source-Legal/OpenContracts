import importlib
import os

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase
from graphene.test import Client

from config.graphql.schema import schema
from opencontractserver.documents.models import PipelineSettings
from opencontractserver.pipeline.registry import reset_registry

User = get_user_model()


class TestContext:
    def __init__(self, user):
        self.user = user


class PipelineComponentQueriesTestCase(TestCase):
    test_files: list[str]
    parser_code: str
    embedder_code: str
    thumbnailer_code: str
    post_processor_code: str
    parser_path: str
    embedder_path: str
    thumbnailer_path: str
    post_processor_path: str

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Dynamically create test components
        cls.test_files = []
        cls.create_test_components()

        # Reload the importlib caches and modules
        importlib.invalidate_caches()
        importlib.reload(importlib.import_module("opencontractserver.pipeline.parsers"))
        importlib.reload(
            importlib.import_module("opencontractserver.pipeline.embedders")
        )
        importlib.reload(
            importlib.import_module("opencontractserver.pipeline.thumbnailers")
        )
        importlib.reload(
            importlib.import_module("opencontractserver.pipeline.post_processors")
        )

        # Reset the pipeline registry to force re-discovery of components
        reset_registry()

    @classmethod
    def tearDownClass(cls):
        # Remove the test components
        cls.remove_test_components()
        # Reset registry to remove test components from cache
        reset_registry()
        super().tearDownClass()

    @classmethod
    def create_test_components(cls):
        """Creates test pipeline components by writing files to appropriate directories."""
        cls.parser_code = '''
from opencontractserver.pipeline.base.parser import BaseParser
from opencontractserver.pipeline.base.file_types import FileTypeEnum
from opencontractserver.types.dicts import OpenContractDocExport
from typing import Optional, List

class TestParser(BaseParser):
    """
    A test parser for unit testing.
    """

    title: str = "Test Parser"
    description: str = "A test parser for unit testing."
    author: str = "Test Author"
    dependencies: List[str] = []
    supported_file_types: List[FileTypeEnum] = [FileTypeEnum.PDF]

    def _parse_document_impl(self, user_id: int, doc_id: int, **all_kwargs) -> Optional[OpenContractDocExport]:
        return None
'''

        cls.embedder_code = '''
from opencontractserver.pipeline.base.embedder import BaseEmbedder
from opencontractserver.pipeline.base.file_types import FileTypeEnum
from typing import Optional, List

class TestEmbedder(BaseEmbedder):
    """
    A test embedder for unit testing.
    """

    title: str = "Test Embedder"
    description: str = "A test embedder for unit testing."
    author: str = "Test Author"
    dependencies: List[str] = []
    vector_size: int = 128
    supported_file_types: List[FileTypeEnum] = [FileTypeEnum.PDF, FileTypeEnum.TXT, FileTypeEnum.DOCX]

    def _embed_text_impl(self, text: str, **all_kwargs) -> Optional[List[float]]:
        # Return a dummy embedding vector
        return [0.0] * self.vector_size
'''

        cls.thumbnailer_code = '''
from opencontractserver.pipeline.base.thumbnailer import BaseThumbnailGenerator
from opencontractserver.pipeline.base.file_types import FileTypeEnum
from typing import Optional, List, Tuple

class TestThumbnailer(BaseThumbnailGenerator):
    """
    A test thumbnail generator for unit testing.
    """

    title: str = "Test Thumbnailer"
    description: str = "A test thumbnailer for unit testing."
    author: str = "Test Author"
    dependencies: List[str] = []
    supported_file_types: List[FileTypeEnum] = [FileTypeEnum.PDF]

    def _generate_thumbnail_impl(
        self, txt_content: Optional[str], pdf_bytes: Optional[bytes], **all_kwargs
    ) -> Optional[Tuple[bytes, str]]:
        return None
'''

        cls.post_processor_code = '''
from opencontractserver.pipeline.base.post_processor import BasePostProcessor
from typing import Tuple, Optional, List
from opencontractserver.pipeline.base.file_types import FileTypeEnum
from opencontractserver.types.dicts import OpenContractsExportDataJsonPythonType

class TestPostProcessor(BasePostProcessor):
    """
    A test post-processor for unit testing.
    """

    title: str = "Test PostProcessor"
    description: str = "A test post-processor for unit testing."
    author: str = "Test Author"
    dependencies: list[str] = []
    supported_file_types: List[FileTypeEnum] = [FileTypeEnum.PDF]

    def _process_export_impl(
        self,
        zip_bytes: bytes,
        export_data: OpenContractsExportDataJsonPythonType,
        **all_kwargs,
    ) -> Tuple[bytes, OpenContractsExportDataJsonPythonType]:
        return zip_bytes, export_data
'''

        # Define the file paths for the components
        cls.parser_path = os.path.join(
            os.path.dirname(__file__), "..", "pipeline", "parsers", "test_parser.py"
        )
        cls.embedder_path = os.path.join(
            os.path.dirname(__file__), "..", "pipeline", "embedders", "test_embedder.py"
        )
        cls.thumbnailer_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "pipeline",
            "thumbnailers",
            "test_thumbnailer.py",
        )
        cls.post_processor_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "pipeline",
            "post_processors",
            "test_post_processor.py",
        )

        # Ensure package __init__.py files exist
        parser_init = os.path.join(os.path.dirname(cls.parser_path), "__init__.py")
        embedder_init = os.path.join(os.path.dirname(cls.embedder_path), "__init__.py")
        thumbnailer_init = os.path.join(
            os.path.dirname(cls.thumbnailer_path), "__init__.py"
        )
        post_processor_init = os.path.join(
            os.path.dirname(cls.post_processor_path), "__init__.py"
        )

        for init_file in [
            parser_init,
            embedder_init,
            thumbnailer_init,
            post_processor_init,
        ]:
            if not os.path.exists(init_file):
                with open(init_file, "w"):
                    pass  # Create empty __init__.py

        # Create the test component files
        os.makedirs(os.path.dirname(cls.parser_path), exist_ok=True)
        with open(cls.parser_path, "w") as f:
            f.write(cls.parser_code)
        cls.test_files.append(cls.parser_path)

        os.makedirs(os.path.dirname(cls.embedder_path), exist_ok=True)
        with open(cls.embedder_path, "w") as f:
            f.write(cls.embedder_code)
        cls.test_files.append(cls.embedder_path)

        os.makedirs(os.path.dirname(cls.thumbnailer_path), exist_ok=True)
        with open(cls.thumbnailer_path, "w") as f:
            f.write(cls.thumbnailer_code)
        cls.test_files.append(cls.thumbnailer_path)

        # Create the post processor file
        os.makedirs(os.path.dirname(cls.post_processor_path), exist_ok=True)
        with open(cls.post_processor_path, "w") as f:
            f.write(cls.post_processor_code)
        cls.test_files.append(cls.post_processor_path)

    @classmethod
    def remove_test_components(cls):
        """Removes the test component files."""
        for file_path in cls.test_files:
            if os.path.exists(file_path):
                os.remove(file_path)
        cls.test_files = []

    # Class-level constants for test component paths.  Every test that
    # relies on a specific component being configured should reference
    # these constants rather than relying on implicit setUp state.
    TEST_PARSER = "opencontractserver.pipeline.parsers.test_parser.TestParser"
    TEST_EMBEDDER = "opencontractserver.pipeline.embedders.test_embedder.TestEmbedder"
    TEST_THUMBNAILER = (
        "opencontractserver.pipeline.thumbnailers.test_thumbnailer.TestThumbnailer"
    )
    TEST_POST_PROCESSOR = "opencontractserver.pipeline.post_processors.test_post_processor.TestPostProcessor"

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpassword"
        )
        self.superuser = User.objects.create_superuser(
            username="adminuser", password="adminpassword"
        )
        self.graphene_client = Client(schema, context_value=TestContext(self.user))
        self.superuser_client = Client(
            schema, context_value=TestContext(self.superuser)
        )

        settings_instance = PipelineSettings.get_instance(use_cache=False)
        settings_instance.preferred_parsers = {
            "application/pdf": self.TEST_PARSER,
        }
        settings_instance.preferred_embedders = {
            "application/pdf": self.TEST_EMBEDDER,
        }
        settings_instance.preferred_thumbnailers = {
            "application/pdf": self.TEST_THUMBNAILER,
        }
        settings_instance.default_embedder = self.TEST_EMBEDDER
        settings_instance.component_settings = {
            self.TEST_POST_PROCESSOR: {},
        }
        settings_instance.save()

    def test_pipeline_components_query(self):
        """Test querying all pipeline components without any filters."""
        query = """
        query {
            pipelineComponents {
                parsers {
                    name
                    title
                    description
                    author
                    supportedFileTypes
                    componentType
                    inputSchema
                }
                embedders {
                    name
                    title
                    description
                    author
                    vectorSize
                    supportedFileTypes
                    componentType
                    inputSchema
                }
                thumbnailers {
                    name
                    title
                    description
                    author
                    supportedFileTypes
                    componentType
                    inputSchema
                }
                postProcessors {
                    name
                    title
                    description
                    author
                    componentType
                    inputSchema
                }
            }
        }
        """

        result = self.graphene_client.execute(query)
        self.assertIsNone(result.get("errors"))

        data = result["data"]["pipelineComponents"]
        parsers = data["parsers"]
        embedders = data["embedders"]
        thumbnailers = data["thumbnailers"]
        post_processors = data["postProcessors"]

        parser_names = [parser["name"] for parser in parsers]
        embedder_names = [embedder["name"] for embedder in embedders]
        thumbnailer_names = [thumbnailer["name"] for thumbnailer in thumbnailers]
        post_processor_names = [pp["name"] for pp in post_processors]

        self.assertIn("TestParser", parser_names)
        self.assertIn("TestEmbedder", embedder_names)
        self.assertIn("TestThumbnailer", thumbnailer_names)
        self.assertIn("TestPostProcessor", post_processor_names)

    def test_pipeline_components_query_requires_auth(self):
        """Test that pipelineComponents requires authentication."""
        query = """
        query {
            pipelineComponents {
                parsers {
                    name
                }
            }
        }
        """
        client = Client(schema, context_value=TestContext(AnonymousUser()))
        result = client.execute(query)
        self.assertIsNotNone(result.get("errors"))

    def test_pipeline_components_query_non_superuser_filters_configured(self):
        """Test non-superusers only see configured components.

        setUp configures TEST_PARSER, TEST_EMBEDDER, TEST_THUMBNAILER (via
        preferred_* mappings and default_embedder) and TEST_POST_PROCESSOR
        (via component_settings).  Only these should be returned for a
        regular (non-superuser) request.
        """
        query = """
        query {
            pipelineComponents {
                parsers { name }
                embedders { name }
                thumbnailers { name }
            }
        }
        """
        result = self.graphene_client.execute(query)
        self.assertIsNone(result.get("errors"))

        data = result["data"]["pipelineComponents"]

        parser_names = [p["name"] for p in data["parsers"]]
        self.assertIn("TestParser", parser_names)
        self.assertNotIn("DoclingParser", parser_names)

        embedder_names = [e["name"] for e in data["embedders"]]
        self.assertIn("TestEmbedder", embedder_names)

        thumbnailer_names = [t["name"] for t in data["thumbnailers"]]
        self.assertIn("TestThumbnailer", thumbnailer_names)

    def test_pipeline_components_query_with_mimetype(self):
        """Test querying pipeline components filtered by mimetype."""
        query = """
        query($mimetype: FileTypeEnum!) {
            pipelineComponents(mimetype: $mimetype) {
                parsers {
                    name
                    title
                    supportedFileTypes
                    componentType
                    inputSchema
                }
                embedders {
                    name
                    title
                    supportedFileTypes
                    componentType
                    inputSchema
                }
                thumbnailers {
                    name
                    title
                    supportedFileTypes
                    componentType
                    inputSchema
                }
                postProcessors {
                    name
                    title
                    description
                    author
                    componentType
                    inputSchema
                }
            }
        }
        """

        variables = {"mimetype": "PDF"}  # This should match the backend enum names

        result = self.superuser_client.execute(query, variables=variables)
        self.assertIsNone(result.get("errors"))

        data = result["data"]["pipelineComponents"]
        parsers = data["parsers"]
        embedders = data["embedders"]
        thumbnailers = data["thumbnailers"]
        post_processors = data["postProcessors"]

        # Since our test components support PDF, they should be included
        parser_titles = [parser["title"] for parser in parsers]
        thumbnailer_titles = [thumbnailer["title"] for thumbnailer in thumbnailers]

        self.assertIn("Test Parser", parser_titles)
        self.assertIn("Test Thumbnailer", thumbnailer_titles)

        # Embedders are not filtered by mimetype in our implementation
        embedder_titles = [embedder["title"] for embedder in embedders]
        self.assertIn("Test Embedder", embedder_titles)

        post_processor_titles = [pp["title"] for pp in post_processors]
        self.assertIn("Test PostProcessor", post_processor_titles)

    def test_pipeline_components_query_with_mimetype_docx(self):
        """Test querying pipeline components filtered to DOCX file type.

        DOCX has parser support (LlamaParse, Docxodus) and thumbnailer support
        (DocxThumbnailGenerator). This test verifies the filtering behavior.
        """

        # Use the enum value, not the full MIME type
        query = """
        query($mimetype: FileTypeEnum) {
            pipelineComponents(mimetype: $mimetype) {
                parsers {
                    name
                    title
                }
                embedders {
                    name
                    title
                }
                thumbnailers {
                    name
                    title
                }
            }
        }
        """

        variables = {"mimetype": "DOCX"}

        result = self.superuser_client.execute(query, variables=variables)
        self.assertIsNone(result.get("errors"))

        data = result["data"]["pipelineComponents"]

        # DocxodusServiceParser supports DOCX
        parsers = data["parsers"]
        parser_titles = [parser["title"] for parser in parsers]
        self.assertIn("Docxodus Parser (REST)", parser_titles)

        # DocxThumbnailGenerator supports DOCX
        thumbnailers = data["thumbnailers"]
        self.assertGreaterEqual(len(thumbnailers), 1)

        # Embedders are included regardless of mimetype in our utils
        embedders = data["embedders"]
        # Our test embedder should be included
        embedder_titles = [embedder["title"] for embedder in embedders]
        self.assertIn("Test Embedder", embedder_titles)

    def test_enabled_field_all_enabled_when_empty(self):
        """When enabled_components is empty (default), all components should have enabled: true."""
        # Ensure enabled_components is empty (the default)
        settings_instance = PipelineSettings.get_instance(use_cache=False)
        settings_instance.enabled_components = []
        settings_instance.save()

        query = """
        query {
            pipelineComponents {
                parsers {
                    name
                    className
                    enabled
                }
                embedders {
                    name
                    className
                    enabled
                }
                thumbnailers {
                    name
                    className
                    enabled
                }
                postProcessors {
                    name
                    className
                    enabled
                }
            }
        }
        """

        # Use superuser client to see all components (not filtered by configured)
        result = self.superuser_client.execute(query)
        self.assertIsNone(result.get("errors"))

        data = result["data"]["pipelineComponents"]

        # Every component across all categories should have enabled=True
        for category in ["parsers", "embedders", "thumbnailers", "postProcessors"]:
            components = data[category]
            self.assertGreater(
                len(components), 0, f"Expected at least one component in {category}"
            )
            for component in components:
                self.assertTrue(
                    component["enabled"],
                    f"Component {component['name']} in {category} should be enabled "
                    f"when enabled_components is empty, but got enabled=False",
                )

    def test_enabled_field_reflects_enabled_list(self):
        """When enabled_components has specific paths, only those should have enabled: true."""
        # Pick the test parser as the only enabled component
        enabled_path = "opencontractserver.pipeline.parsers.test_parser.TestParser"

        settings_instance = PipelineSettings.get_instance(use_cache=False)
        settings_instance.enabled_components = [enabled_path]
        settings_instance.save()

        query = """
        query {
            pipelineComponents {
                parsers {
                    name
                    className
                    enabled
                }
                embedders {
                    name
                    className
                    enabled
                }
                thumbnailers {
                    name
                    className
                    enabled
                }
                postProcessors {
                    name
                    className
                    enabled
                }
            }
        }
        """

        # Use superuser client to see all components
        result = self.superuser_client.execute(query)
        self.assertIsNone(result.get("errors"))

        data = result["data"]["pipelineComponents"]

        # TestParser should be enabled
        parsers = data["parsers"]
        test_parser = next((p for p in parsers if p["name"] == "TestParser"), None)
        self.assertIsNotNone(test_parser, "TestParser should be in the results")
        assert test_parser is not None
        self.assertTrue(
            test_parser["enabled"],
            "TestParser should be enabled since it's in the enabled_components list",
        )

        # All other parsers should be disabled
        for parser in parsers:
            if parser["name"] != "TestParser":
                self.assertFalse(
                    parser["enabled"],
                    f"Parser {parser['name']} should be disabled since it's "
                    f"not in the enabled_components list",
                )

        # All embedders, thumbnailers, and post processors should be disabled
        for category in ["embedders", "thumbnailers", "postProcessors"]:
            components = data[category]
            for component in components:
                self.assertFalse(
                    component["enabled"],
                    f"Component {component['name']} in {category} should be disabled "
                    f"since it's not in the enabled_components list",
                )

    def test_supported_mime_types_query(self):
        """Test the supportedMimeTypes query returns dynamically-derived MIME types."""
        query = """
        query {
            supportedMimeTypes {
                mimetype
                fileType
                label
                fullySupported
                stageCoverage {
                    parser
                    embedder
                    thumbnailer
                }
            }
        }
        """

        result = self.graphene_client.execute(query)
        self.assertIsNone(result.get("errors"))

        mime_types = result["data"]["supportedMimeTypes"]
        self.assertGreater(len(mime_types), 0)

        # Build lookup by file type
        by_file_type = {mt["fileType"]: mt for mt in mime_types}

        # PDF should be fully supported (has test parser + test embedder + test thumbnailer)
        self.assertIn("pdf", by_file_type)
        pdf_entry = by_file_type["pdf"]
        self.assertEqual(pdf_entry["mimetype"], "application/pdf")
        self.assertEqual(pdf_entry["label"], "PDF")
        self.assertTrue(pdf_entry["fullySupported"])
        self.assertTrue(pdf_entry["stageCoverage"]["parser"])
        self.assertTrue(pdf_entry["stageCoverage"]["embedder"])
        self.assertTrue(pdf_entry["stageCoverage"]["thumbnailer"])

        # TXT should have parser and embedder, check thumbnailer dynamically
        self.assertIn("txt", by_file_type)
        txt_entry = by_file_type["txt"]
        self.assertEqual(txt_entry["mimetype"], "text/plain")
        self.assertTrue(txt_entry["stageCoverage"]["parser"])
        self.assertTrue(txt_entry["stageCoverage"]["embedder"])

        # DOCX now has parser, embedder, and thumbnailer (DocxThumbnailGenerator)
        self.assertIn("docx", by_file_type)
        docx_entry = by_file_type["docx"]
        self.assertTrue(docx_entry["stageCoverage"]["thumbnailer"])
        self.assertTrue(docx_entry["fullySupported"])

    def test_supported_mime_types_allows_anonymous(self):
        """Test that supportedMimeTypes is accessible to anonymous users."""
        query = """
        query {
            supportedMimeTypes {
                mimetype
                fileType
            }
        }
        """
        client = Client(schema, context_value=TestContext(AnonymousUser()))
        result = client.execute(query)
        self.assertIsNone(result.get("errors"))
        mime_types = result["data"]["supportedMimeTypes"]
        self.assertGreater(len(mime_types), 0)
