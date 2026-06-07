import importlib
import inspect
import logging
import os
import sys
import unittest
from typing import Any, ClassVar, cast

from django.test import TestCase, override_settings

from opencontractserver.pipeline.base.embedder import BaseEmbedder
from opencontractserver.pipeline.base.file_types import FileTypeEnum
from opencontractserver.pipeline.base.parser import BaseParser
from opencontractserver.pipeline.base.thumbnailer import BaseThumbnailGenerator
from opencontractserver.pipeline.utils import (
    get_all_embedders,
    get_all_parsers,
    get_all_post_processors,
    get_all_subclasses,
    get_all_thumbnailers,
    get_component_by_name,
    get_components_by_mimetype,
    get_default_embedder_for_filetype,
    get_dimension_from_embedder,
    get_metadata_by_component_name,
    get_metadata_for_component,
    run_post_processors,
)
from opencontractserver.types.dicts import OpenContractsExportDataJsonPythonType

logger = logging.getLogger(__name__)


class TestPipelineUtils(TestCase):
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
        """
        Set up temporary test components in the appropriate packages.
        """
        cls.test_files = []

        # Define the test components as strings
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

    def _parse_document_impl(self, user_id: int, doc_id: int) -> Optional[OpenContractDocExport]:
        # Return None or a dummy OpenContractDocExport for testing purposes
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
    supported_file_types = [FileTypeEnum.PDF, FileTypeEnum.TXT]

    def _embed_text_impl(self, text: str) -> Optional[List[float]]:
        # Return a dummy embedding vector
        return [0.0] * self.vector_size

class TestEmbedder384(BaseEmbedder):
    """
    A test embedder with 384 dimensions.
    """

    title: str = "Test Embedder 384"
    description: str = "A test embedder with 384 dimensions."
    author: str = "Test Author"
    dependencies: List[str] = []
    vector_size: int = 384
    supported_file_types = [FileTypeEnum.PDF]

    def _embed_text_impl(self, text: str) -> Optional[List[float]]:
        # Return a dummy embedding vector
        return [0.0] * self.vector_size

class TestEmbedder768(BaseEmbedder):
    """
    A test embedder with 768 dimensions.
    """

    title: str = "Test Embedder 768"
    description: str = "A test embedder with 768 dimensions."
    author: str = "Test Author"
    dependencies: List[str] = []
    vector_size: int = 768
    supported_file_types = [FileTypeEnum.TXT]

    def _embed_text_impl(self, text: str) -> Optional[List[float]]:
        # Return a dummy embedding vector
        return [0.0] * self.vector_size
'''

        cls.thumbnailer_code = '''
from opencontractserver.pipeline.base.thumbnailer import BaseThumbnailGenerator
from opencontractserver.pipeline.base.file_types import FileTypeEnum
from typing import Optional, List
from django.core.files.base import File

class TestThumbnailer(BaseThumbnailGenerator):
    """
    A test thumbnail generator for unit testing.
    """

    title: str = "Test Thumbnailer"
    description: str = "A test thumbnailer for unit testing."
    author: str = "Test Author"
    dependencies: List[str] = []
    supported_file_types: List[FileTypeEnum] = [FileTypeEnum.PDF]

    def _generate_thumbnail_impl(self, file_bytes: bytes) -> Optional[File]:
        # Return None or a dummy File object for testing purposes
        return None
'''

        cls.post_processor_code = '''
from opencontractserver.pipeline.base.post_processor import BasePostProcessor
from opencontractserver.types.dicts import OpenContractsExportDataJsonPythonType
from opencontractserver.pipeline.base.file_types import FileTypeEnum
from typing import List, Tuple
import logging

logger = logging.getLogger(__name__)

class TestPostProcessor(BasePostProcessor):
    """
    A test post-processor for unit testing.
    """

    title: str = "Test PostProcessor"
    description: str = "A test post-processor for unit testing."
    author: str = "Test Author"
    dependencies: List[str] = []
    supported_file_types: List[FileTypeEnum] = [FileTypeEnum.PDF]

    def _process_export_impl(
        self,
        zip_bytes: bytes,
        export_data: OpenContractsExportDataJsonPythonType,
        **all_kwargs,
    ) -> Tuple[bytes, OpenContractsExportDataJsonPythonType]:
        # Add logging to debug the process
        logger.info("TestPostProcessor.process_export called")
        logger.info(f"Input export_data: {export_data}")

        # Add a test field to export data
        new_export_data = export_data.copy()
        new_export_data["test_field"] = "test_value"

        logger.info(f"Modified export_data: {new_export_data}")
        return zip_bytes, new_export_data
'''

        # Define the file paths for the components
        cls.parser_path = os.path.join(
            os.path.dirname(__file__), "..", "pipeline", "parsers", "test_parser.py"
        )
        cls.embedder_path = os.path.join(
            os.path.dirname(__file__), "..", "pipeline", "embedders", "temp_embedder.py"
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

        os.makedirs(os.path.dirname(cls.post_processor_path), exist_ok=True)
        with open(cls.post_processor_path, "w") as f:
            f.write(cls.post_processor_code)
        cls.test_files.append(cls.post_processor_path)

        # Reload the importlib caches and modules
        importlib.invalidate_caches()

        # Force a direct import of the test modules to ensure they're loaded
        if cls.parser_path not in sys.path:
            sys.path.insert(0, os.path.dirname(os.path.dirname(cls.parser_path)))

        # Reload and then directly import the modules to force discovery
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

        # Force import the new modules directly
        try:
            from opencontractserver.pipeline.embedders.temp_embedder import (  # noqa
                TestEmbedder,
                TestEmbedder384,
                TestEmbedder768,
            )
            from opencontractserver.pipeline.parsers.test_parser import (  # noqa
                TestParser,
            )
            from opencontractserver.pipeline.post_processors.test_post_processor import (  # noqa
                TestPostProcessor,
            )
            from opencontractserver.pipeline.thumbnailers.test_thumbnailer import (  # noqa
                TestThumbnailer,
            )

            logger.info("Successfully imported test classes after reloading")
        except ImportError as e:
            logger.error(f"Failed to import test classes: {e}")

        # Verify the embedders were loaded correctly
        embedders = get_all_embedders()
        embedder_titles = [embedder.title for embedder in embedders]
        logger.info(f"Available embedder titles after reload: {embedder_titles}")

        # make sure the package directory is importable
        sys.modules.pop(
            "opencontractserver.pipeline.post_processors.test_post_processor", None
        )
        importlib.invalidate_caches()
        importlib.import_module(
            "opencontractserver.pipeline.post_processors.test_post_processor"
        )

    @classmethod
    def tearDownClass(cls):
        """
        Remove the temporary test components after tests are completed.
        """
        for file_path in cls.test_files:
            if os.path.exists(file_path):
                os.remove(file_path)
        # Optionally, you can remove the __pycache__ directories
        # in the package directories to clean up compiled files

    def setUp(self):
        """Set up fresh test components before each test."""
        # Create post processor file if we're going to execute it...
        os.makedirs(os.path.dirname(self.post_processor_path), exist_ok=True)
        with open(self.post_processor_path, "w") as f:
            f.write(self.post_processor_code)

        # Reload the module to ensure we have fresh code
        importlib.invalidate_caches()
        importlib.reload(
            importlib.import_module("opencontractserver.pipeline.post_processors")
        )

        # Force direct import
        try:
            from opencontractserver.pipeline.post_processors.test_post_processor import (  # noqa
                TestPostProcessor,
            )
        except ImportError as e:
            logger.error(f"Failed to import TestPostProcessor in setUp: {e}")

    def test_get_all_subclasses(self):
        """
        Test get_all_subclasses function to ensure it returns all subclasses of a base class within a module.
        """
        # Test parsers
        parsers = cast(
            list[type[BaseParser]],
            get_all_subclasses("opencontractserver.pipeline.parsers", BaseParser),
        )
        parser_titles = [parser.title for parser in parsers]
        self.assertIn("Test Parser", parser_titles)

        # Test embedders
        embedders = cast(
            list[type[BaseEmbedder]],
            get_all_subclasses("opencontractserver.pipeline.embedders", BaseEmbedder),
        )
        embedder_titles = [embedder.title for embedder in embedders]
        self.assertIn("Test Embedder", embedder_titles)

        # Test thumbnailers
        thumbnailers = cast(
            list[type[BaseThumbnailGenerator]],
            get_all_subclasses(
                "opencontractserver.pipeline.thumbnailers", BaseThumbnailGenerator
            ),
        )
        thumbnailer_titles = [thumbnailer.title for thumbnailer in thumbnailers]
        self.assertIn("Test Thumbnailer", thumbnailer_titles)

    def test_get_all_parsers(self):
        """
        Test get_all_parsers function to ensure it returns all parser classes.
        """
        parsers = get_all_parsers()
        parser_titles = [parser.title for parser in parsers]
        self.assertIn("Test Parser", parser_titles)

    def test_get_all_embedders(self):
        """
        Test get_all_embedders function to ensure it returns all embedder classes.
        """
        embedders = get_all_embedders()
        embedder_titles = [embedder.title for embedder in embedders]
        self.assertIn("Test Embedder", embedder_titles)

    def test_get_all_thumbnailers(self):
        """
        Test get_all_thumbnailers function to ensure it returns all thumbnail generator classes.
        """
        thumbnailers = get_all_thumbnailers()
        thumbnailer_titles = [thumbnailer.title for thumbnailer in thumbnailers]
        self.assertIn("Test Thumbnailer", thumbnailer_titles)

    def test_get_components_by_mimetype(self):
        """
        Test get_components_by_mimetype function to ensure it returns correct components for a given mimetype.
        """
        # Test with detailed=False
        components = get_components_by_mimetype("application/pdf", detailed=False)
        parsers = components.get("parsers", [])
        embedders = components.get("embedders", [])
        thumbnailers = components.get("thumbnailers", [])

        parser_titles = [parser.title for parser in parsers]
        embedder_titles = [embedder.title for embedder in embedders]
        thumbnailer_titles = [thumbnailer.title for thumbnailer in thumbnailers]

        self.assertIn("Test Parser", parser_titles)
        self.assertIn("Test Embedder", embedder_titles)
        self.assertIn("Test Thumbnailer", thumbnailer_titles)

        # Test with detailed=True
        components_detailed = get_components_by_mimetype(
            "application/pdf", detailed=True
        )
        parser_titles_detailed = [
            comp["title"] for comp in components_detailed["parsers"]
        ]
        embedder_titles_detailed = [
            comp["title"] for comp in components_detailed["embedders"]
        ]
        thumbnailer_titles_detailed = [
            comp["title"] for comp in components_detailed["thumbnailers"]
        ]

        self.assertIn("Test Parser", parser_titles_detailed)
        self.assertIn("Test Embedder", embedder_titles_detailed)
        self.assertIn("Test Thumbnailer", thumbnailer_titles_detailed)

    def test_get_metadata_for_component(self):
        """
        Test get_metadata_for_component function to ensure it returns correct metadata for a given component.
        """
        from opencontractserver.pipeline.parsers.test_parser import TestParser

        metadata = get_metadata_for_component(TestParser)
        self.assertEqual(metadata["title"], "Test Parser")
        self.assertEqual(metadata["description"], "A test parser for unit testing.")
        self.assertEqual(metadata["author"], "Test Author")
        self.assertEqual(metadata["dependencies"], [])
        self.assertEqual(metadata["supported_file_types"], [FileTypeEnum.PDF])

    def test_get_metadata_by_component_name(self):
        """
        Test get_metadata_by_component_name function to ensure it returns correct metadata when given a component name.
        """
        metadata = get_metadata_by_component_name("test_parser")
        self.assertEqual(metadata["title"], "Test Parser")
        self.assertEqual(metadata["description"], "A test parser for unit testing.")
        self.assertEqual(metadata["author"], "Test Author")
        self.assertEqual(metadata["dependencies"], [])
        self.assertEqual(metadata["supported_file_types"], [FileTypeEnum.PDF])

    def test_get_component_by_name(self):
        """
        Test get_component_by_name function to ensure it returns the correct class.
        """
        # Test parser component
        component = get_component_by_name("test_parser")
        from opencontractserver.pipeline.parsers.test_parser import TestParser

        self.assertEqual(component, TestParser)

        # Test embedder component
        component = get_component_by_name("temp_embedder")
        from opencontractserver.pipeline.embedders.temp_embedder import TestEmbedder

        self.assertEqual(component, TestEmbedder)

        # Test thumbnailer component
        component = get_component_by_name("test_thumbnailer")
        from opencontractserver.pipeline.thumbnailers.test_thumbnailer import (
            TestThumbnailer,
        )

        self.assertEqual(component, TestThumbnailer)

        # Test post-processor component
        component = get_component_by_name("test_post_processor")
        from opencontractserver.pipeline.post_processors.test_post_processor import (
            TestPostProcessor,
        )

        self.assertEqual(component, TestPostProcessor)

        # Test non-existing component
        with self.assertRaises(ValueError) as context:
            get_component_by_name("non_existing_component")
        self.assertTrue(
            "Component 'non_existing_component' not found." in str(context.exception)
        )

    def test_run_post_processors(self):
        """
        Test run_post_processors function to ensure it correctly loads and runs post-processors.
        """
        # Create test data
        test_zip_bytes = b"test zip content"
        test_export_data = {
            "annotated_docs": {},
            "corpus": {
                "title": "Test Corpus",
                "description": "Test Description",
                "icon": None,
            },
            "label_set": {
                "title": "Test Label Set",
                "description": "Test Description",
                "icon": None,
            },
            "doc_labels": {},
            "text_labels": {},
        }

        # Run post-processor
        processor_paths = [
            "opencontractserver.pipeline.post_processors.test_post_processor.TestPostProcessor"
        ]

        # Add debug logging
        logger.info("Before running post-processors")
        logger.info(f"Initial export data: {test_export_data}")

        # Force reload of the module to ensure we're using the freshly written version
        import importlib

        module = importlib.import_module(
            "opencontractserver.pipeline.post_processors.test_post_processor"
        )
        importlib.reload(module)

        processor_class = get_component_by_name(
            "opencontractserver.pipeline.post_processors.test_post_processor.TestPostProcessor"
        )
        logger.info(
            "Loaded %s from %s", processor_class, inspect.getfile(processor_class)
        )
        logger.info("abstract? %s", inspect.isabstract(processor_class))
        logger.info("source:\n%s", inspect.getsource(processor_class))

        modified_zip_bytes, modified_export_data = run_post_processors(
            processor_paths,
            test_zip_bytes,
            cast(OpenContractsExportDataJsonPythonType, test_export_data),
        )

        # Add more debug logging
        logger.info("After running post-processors...")
        logger.info(f"Modified export data: {modified_export_data}")

        # Verify post-processor was applied
        self.assertEqual(modified_zip_bytes, test_zip_bytes)  # Zip bytes unchanged
        self.assertEqual(
            modified_export_data.get("test_field"), "test_value"
        )  # New field added

        # Test with invalid processor path
        with self.assertRaises(ValueError):
            run_post_processors(
                ["invalid.processor.path"],
                test_zip_bytes,
                cast(OpenContractsExportDataJsonPythonType, test_export_data),
            )

    def test_get_all_post_processors(self):
        """
        Test get_all_post_processors function to ensure it returns all post-processor classes.
        """
        post_processors = get_all_post_processors()
        post_processor_titles = [processor.title for processor in post_processors]
        self.assertIn("Test PostProcessor", post_processor_titles)

    def test_get_dimension_from_embedder(self):
        """
        Test get_dimension_from_embedder function to ensure it correctly extracts dimensions.
        """
        # Get the test embedder class
        embedders = get_all_embedders()
        temp_embedder = next((e for e in embedders if e.title == "Test Embedder"), None)
        temp_embedder_384 = next(
            (e for e in embedders if e.title == "Test Embedder 384"), None
        )
        assert temp_embedder is not None
        assert temp_embedder_384 is not None

        # Test with class
        self.assertEqual(get_dimension_from_embedder(temp_embedder), 128)
        self.assertEqual(get_dimension_from_embedder(temp_embedder_384), 384)

        self.assertEqual(
            get_dimension_from_embedder(
                "opencontractserver.pipeline.embedders.temp_embedder.TestEmbedder"
            ),
            128,
        )
        self.assertEqual(
            get_dimension_from_embedder(
                "opencontractserver.pipeline.embedders.temp_embedder.TestEmbedder384"
            ),
            384,
        )

        with override_settings(DEFAULT_EMBEDDING_DIMENSION=768):
            self.assertEqual(get_dimension_from_embedder("non.existent.Embedder"), 768)

    def test_get_default_embedder_for_filetype(self) -> None:
        """get_default_embedder_for_filetype delegates to get_preferred_embedder
        which reads from the PipelineSettings singleton."""
        from unittest.mock import patch

        mock_embedders = {
            "application/pdf": "opencontractserver.pipeline.embedders.temp_embedder.TestEmbedder384",
            "text/plain": "opencontractserver.pipeline.embedders.temp_embedder.TestEmbedder768",
        }

        with patch(
            "opencontractserver.pipeline.utils.get_preferred_embedder"
        ) as mock_get_pref:
            # Simulate get_preferred_embedder returning classes via import
            import importlib

            def side_effect(mimetype):
                path = mock_embedders.get(mimetype)
                if not path:
                    return None
                module_path, class_name = path.rsplit(".", 1)
                module = importlib.import_module(module_path)
                return getattr(module, class_name)

            mock_get_pref.side_effect = side_effect

            # Test getting embedder for PDF with dimension 384
            embedder = get_default_embedder_for_filetype("application/pdf")
            assert embedder is not None
            self.assertEqual(embedder.title, "Test Embedder 384")

            # Test getting embedder for TXT with dimension 768
            embedder = get_default_embedder_for_filetype("text/plain")
            assert embedder is not None
            self.assertEqual(embedder.title, "Test Embedder 768")

            # Test getting embedder for non-existent mimetype falls back
            # to the global default embedder (not None)
            with patch(
                "opencontractserver.pipeline.utils.get_default_embedder",
                return_value=None,
            ):
                embedder = get_default_embedder_for_filetype("application/json")
                self.assertIsNone(embedder)

    def test_find_embedder_for_filetype(self) -> None:
        """
        Test find_embedder_for_filetype function with different input types and scenarios.

        Sets embedder values directly on PipelineSettings (database is single source of truth).
        """
        from opencontractserver.documents.models import PipelineSettings
        from opencontractserver.pipeline.base.file_types import FileTypeEnum
        from opencontractserver.pipeline.utils import (
            find_embedder_for_filetype,
            get_default_embedder,
        )

        # Set values directly on PipelineSettings (database is single source of truth)
        pipeline_settings = PipelineSettings.get_instance(use_cache=False)
        pipeline_settings.preferred_embedders = {
            "application/pdf": "opencontractserver.pipeline.embedders.temp_embedder.TestEmbedder384",
            "text/plain": "opencontractserver.pipeline.embedders.temp_embedder.TestEmbedder768",
        }
        pipeline_settings.default_embedder = (
            "opencontractserver.pipeline.embedders.temp_embedder.TestEmbedder"
        )
        pipeline_settings.save()
        PipelineSettings.clear_cache()
        # Ensure cache is cleared after TestCase rolls back the transaction,
        # so stale values don't leak to other tests on the same xdist worker.
        self.addCleanup(PipelineSettings.clear_cache)

        # Get the default embedder for comparison
        default_embedder = get_default_embedder()
        assert default_embedder is not None
        self.assertEqual(default_embedder.title, "Test Embedder")

        # Test with mimetype string
        embedder = find_embedder_for_filetype("application/pdf")
        assert embedder is not None
        self.assertEqual(embedder.title, "Test Embedder 384")

        embedder = find_embedder_for_filetype("text/plain")
        assert embedder is not None
        self.assertEqual(embedder.title, "Test Embedder 768")

        # Test with FileTypeEnum
        embedder = find_embedder_for_filetype(FileTypeEnum.PDF)
        assert embedder is not None
        self.assertEqual(embedder.title, "Test Embedder 384")

        embedder = find_embedder_for_filetype(FileTypeEnum.TXT)
        assert embedder is not None
        self.assertEqual(embedder.title, "Test Embedder 768")

        # Test with unknown mimetype — falls back to the global default embedder
        embedder = find_embedder_for_filetype("application/unknown")
        assert embedder is not None
        self.assertEqual(embedder.title, "Test Embedder")

        # Test with DOCX FileTypeEnum — falls back to the global default embedder
        embedder = find_embedder_for_filetype(FileTypeEnum.DOCX)
        assert embedder is not None
        self.assertEqual(embedder.title, "Test Embedder")

    def test_find_embedder_for_filetype_error_handling(self) -> None:
        """
        Test find_embedder_for_filetype error handling when embedder path can't be loaded.
        """
        from opencontractserver.documents.models import PipelineSettings
        from opencontractserver.pipeline.utils import find_embedder_for_filetype

        # Set a non-existent embedder path directly on PipelineSettings
        pipeline_settings = PipelineSettings.get_instance(use_cache=False)
        pipeline_settings.preferred_embedders = {
            "application/pdf": "non.existent.EmbedderClass",
        }
        pipeline_settings.default_embedder = (
            "opencontractserver.pipeline.embedders.temp_embedder.TestEmbedder"
        )
        pipeline_settings.save()
        PipelineSettings.clear_cache()
        self.addCleanup(PipelineSettings.clear_cache)

        # When a preferred embedder can't be loaded, the function falls back
        # to the global default embedder
        embedder = find_embedder_for_filetype("application/pdf")
        assert embedder is not None
        self.assertEqual(embedder.title, "Test Embedder")


# NOTE: the ``TestEmbedder*`` classes earlier in this file live inside the
# ``cls.embedder_code`` STRING (they are source written to a temp module at
# runtime), so they are NOT importable at module scope. The cache tests below
# therefore define their own real, module-level embedder classes. They are
# named without a ``Test`` prefix so pytest does not try to collect them as
# test cases.
class _CacheProbeEmbedderA(BaseEmbedder):
    """Minimal real embedder for exercising the instance cache."""

    title = "Cache Probe Embedder A"
    description = "Probe embedder A for cache tests."
    author = "Test Author"
    dependencies: ClassVar[list[str]] = []
    vector_size = 16
    supported_file_types = [FileTypeEnum.PDF, FileTypeEnum.TXT]

    def _embed_text_impl(self, text: str, **kwargs: Any) -> list[float] | None:
        return [0.0] * self.vector_size


class _CacheProbeEmbedderB(BaseEmbedder):
    """A second probe embedder so distinct-path isolation can be asserted."""

    title = "Cache Probe Embedder B"
    description = "Probe embedder B for cache tests."
    author = "Test Author"
    dependencies: ClassVar[list[str]] = []
    vector_size = 32
    supported_file_types = [FileTypeEnum.PDF]

    def _embed_text_impl(self, text: str, **kwargs: Any) -> list[float] | None:
        return [0.0] * self.vector_size


class _FailingProbeEmbedder(BaseEmbedder):
    """Probe embedder whose construction always fails.

    Used to lock in the intentional divergence from the reranker cache:
    ``get_embedder_instance`` must propagate construction exceptions rather
    than swallowing them, and must NOT cache the broken state.
    """

    title = "Failing Probe Embedder"
    description = "Probe embedder that raises on construction."
    author = "Test Author"
    dependencies: ClassVar[list[str]] = []
    vector_size = 16
    supported_file_types = [FileTypeEnum.PDF]

    def __init__(self, *args, **kwargs):
        raise RuntimeError("simulated embedder construction failure")

    def _embed_text_impl(self, text: str, **kwargs: Any) -> list[float] | None:
        return [0.0] * self.vector_size


class TestEmbedderInstanceCache(TestCase):
    """Covers the process-local embedder instance cache.

    Mirrors ``PipelineUtilityTest`` for rerankers in
    ``test_reranker.py``: constructing an embedder is expensive (DB read +
    PBKDF2 secret decryption), so ``get_embedder_instance`` caches the
    instance keyed by ``(class_path, PipelineSettings.modified)``.
    """

    def setUp(self) -> None:
        from opencontractserver.pipeline.utils import invalidate_embedder_cache

        invalidate_embedder_cache()
        self.addCleanup(invalidate_embedder_cache)

    def test_instance_is_cached_per_class_path(self) -> None:
        from opencontractserver.pipeline.utils import get_embedder_instance

        first = get_embedder_instance(_CacheProbeEmbedderA, "tests.ProbeA")
        second = get_embedder_instance(_CacheProbeEmbedderA, "tests.ProbeA")
        self.assertIs(first, second, "Instance should be process-cached.")
        self.assertIsInstance(first, _CacheProbeEmbedderA)

    def test_distinct_paths_get_distinct_instances(self) -> None:
        from opencontractserver.pipeline.utils import get_embedder_instance

        a = get_embedder_instance(_CacheProbeEmbedderA, "tests.ProbeA")
        b = get_embedder_instance(_CacheProbeEmbedderB, "tests.ProbeB")
        self.assertIsNot(a, b)
        self.assertIsInstance(a, _CacheProbeEmbedderA)
        self.assertIsInstance(b, _CacheProbeEmbedderB)

    def test_default_class_path_is_derived_from_class(self) -> None:
        """Omitting ``embedder_path`` keys on the class's module+name."""
        from opencontractserver.pipeline.utils import get_embedder_instance

        first = get_embedder_instance(_CacheProbeEmbedderA)
        second = get_embedder_instance(_CacheProbeEmbedderA)
        self.assertIs(first, second)

    def test_settings_write_busts_cache(self) -> None:
        """Saving PipelineSettings bumps ``modified`` → fresh instance."""
        from opencontractserver.documents.models import PipelineSettings
        from opencontractserver.pipeline.utils import get_embedder_instance

        first = get_embedder_instance(_CacheProbeEmbedderA, "tests.ProbeA")

        # A settings write bumps ``modified`` (auto_now), which is part of the
        # cache key, so the next lookup misses and rebuilds.
        instance = PipelineSettings.get_instance()
        instance.save()
        PipelineSettings.clear_cache()
        self.addCleanup(PipelineSettings.clear_cache)

        second = get_embedder_instance(_CacheProbeEmbedderA, "tests.ProbeA")
        self.assertIsNot(
            first, second, "Settings write should invalidate the cached instance."
        )

    def test_invalidate_clears_cache(self) -> None:
        from opencontractserver.pipeline.utils import (
            get_embedder_instance,
            invalidate_embedder_cache,
        )

        first = get_embedder_instance(_CacheProbeEmbedderA, "tests.ProbeA")
        invalidate_embedder_cache()
        second = get_embedder_instance(_CacheProbeEmbedderA, "tests.ProbeA")
        self.assertIsNot(first, second)

    def test_construction_failure_propagates_and_is_not_cached(self) -> None:
        """Unlike the reranker cache, construction errors propagate.

        Embedding is mandatory for vector search, so a failed construction
        must surface to the caller rather than degrading to ``None``. The
        broken instance must also NOT be cached, so a subsequent lookup of a
        working class path still succeeds.
        """
        from opencontractserver.documents.models import PipelineSettings
        from opencontractserver.pipeline.utils import (
            _EMBEDDER_INSTANCE_CACHE,
            get_embedder_instance,
        )

        with self.assertRaises(RuntimeError):
            get_embedder_instance(_FailingProbeEmbedder, "tests.Failing")

        # The failed construction must not have populated the cache.
        self.assertNotIn(
            ("tests.Failing", PipelineSettings.get_instance().modified),
            _EMBEDDER_INSTANCE_CACHE,
        )

        # A working class path still resolves after the failure.
        working = get_embedder_instance(_CacheProbeEmbedderA, "tests.ProbeA")
        self.assertIsInstance(working, _CacheProbeEmbedderA)


if __name__ == "__main__":
    unittest.main()
