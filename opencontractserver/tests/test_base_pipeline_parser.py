import importlib
import logging
import os
from typing import Optional, cast
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from opencontractserver.annotations.models import (
    Annotation,
    AnnotationLabel,
    Relationship,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.types.dicts import (
    OpenContractDocExport,
    OpenContractsAnnotationPythonType,
    OpenContractsRelationshipPythonType,
)
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

logger = logging.getLogger(__name__)


class TestBasePipelineParser(TestCase):
    test_files: list[str]
    parser_code: str
    parser_path: str

    @classmethod
    def setUpClass(cls) -> None:
        """
        Dynamically create + register a parser file for testing so that our
        Celery-based ingest_doc task can locate it with get_component_by_name(...).
        This approach mimics how test_pipeline_utils creates ephemeral test modules.
        """
        super().setUpClass()

        cls.test_files = []

        # We define ephemeral code for a "MockParser" in opencontractserver/pipeline/parsers.
        # Notice that the class is named MockParser, and we will reference it by
        # "MockParser" in our PREFERRED_PARSERS when we override settings.
        cls.parser_code = r"""
import logging
from opencontractserver.pipeline.base.parser import BaseParser
from opencontractserver.types.dicts import OpenContractDocExport
from typing import Optional

logger = logging.getLogger(__name__)

class MockParser(BaseParser):
    title: str = "MockParser"
    description: str = "A parser for testing KWARGS passing in doc_tasks."
    author: str = "Integration Test"
    dependencies: list[str] = []

    def _parse_document_impl(self, user_id: int, doc_id: int, **kwargs) -> Optional[OpenContractDocExport]:
        logger.info(f"MockParser.parse_document called with kwargs: {kwargs}")
        return None
"""

        # Write ephemeral code to a file in opencontractserver/pipeline/parsers.
        # We'll name it mock_parser.py
        parser_dir = os.path.join(
            os.path.dirname(__file__), "..", "pipeline", "parsers"
        )
        os.makedirs(parser_dir, exist_ok=True)

        cls.parser_path = os.path.join(parser_dir, "mock_parser.py")
        with open(cls.parser_path, "w", encoding="utf-8") as f:
            f.write(cls.parser_code)

        cls.test_files.append(cls.parser_path)

        # Refresh importlib caches so Django can pick up this new file.
        importlib.invalidate_caches()

        # Reload the entire opencontractserver.pipeline.parsers subpackage.
        import opencontractserver.pipeline.parsers

        importlib.reload(opencontractserver.pipeline.parsers)

    @classmethod
    def tearDownClass(cls) -> None:
        """
        Remove the ephemeral test parser file after tests.
        """
        for file_path in getattr(cls, "test_files", []):
            if os.path.exists(file_path):
                os.remove(file_path)
        super().tearDownClass()

    def setUp(self):
        """
        Create a user, a corpus, a Document, etc.
        """
        self.user = get_user_model().objects.create_user(
            username="testuser", password="testpass"
        )
        self.doc = Document.objects.create(
            title="Test Document with ephemeral parser",
            creator=self.user,
        )
        # T-7 (#1463) defense-in-depth: ingest_doc rejects callers without
        # explicit guardian READ permission.
        set_permissions_for_obj_to_user(self.user, self.doc, [PermissionTypes.CRUD])
        self.corpus = Corpus.objects.create(
            title="Test Corpus",
            creator=self.user,
        )

    def test_parser_kwargs_passing_via_ephemeral_parser(self):
        """
        Confirm that ingest_doc looks up 'mock_parser.MockParser' from
        our ephemeral file and passes <parser_name>_kwargs from Django settings.
        """
        from opencontractserver.tasks.doc_tasks import ingest_doc

        # Make sure the doc triggers our ephemeral parser
        self.doc.file_type = "application/mock"
        self.doc.save()

        # Minimal valid parsed data to avoid DocumentParsingError for None return
        mock_parsed_data: OpenContractDocExport = {
            "title": "Test",
            "content": "Test content",
            "description": "",
            "pawls_file_content": [],
            "page_count": 1,
            "doc_labels": [],
            "labelled_text": [],
        }

        # Set parser config directly on PipelineSettings (database is single source of truth)
        from opencontractserver.documents.models import PipelineSettings

        pipeline_settings = PipelineSettings.get_instance(use_cache=False)
        pipeline_settings.preferred_parsers = {
            **pipeline_settings.preferred_parsers,
            "application/mock": "opencontractserver.pipeline.parsers.mock_parser.MockParser",
        }
        pipeline_settings.parser_kwargs = {
            **pipeline_settings.parser_kwargs,
            "opencontractserver.pipeline.parsers.mock_parser.MockParser": {
                "test_key": "test_value"
            },
        }
        pipeline_settings.save()
        PipelineSettings.clear_cache()
        self.addCleanup(PipelineSettings.clear_cache)

        # We'll patch the ephemeral parser's parse_document, verifying that it
        # indeed receives the "test_key" kwarg.
        with patch(
            "opencontractserver.pipeline.parsers.mock_parser.MockParser._parse_document_impl",
            return_value=mock_parsed_data,
        ) as mock_parse:
            # Now call our Celery-based ingest_doc as a task signature
            ingest_doc.s(user_id=self.user.id, doc_id=self.doc.id).apply()

            self.assertTrue(
                mock_parse.called,
                "MockParser._parse_document_impl should have been called by ingest_doc.",
            )
            _, call_kwargs = mock_parse.call_args
            self.assertIn(
                "test_key",
                call_kwargs,
                "Should pass 'test_key' to _parse_document_impl.",
            )
            self.assertEqual(
                call_kwargs["test_key"],
                "test_value",
                "Kwargs from settings should match the ones _parse_document_impl receives.",
            )

    def test_parse_document_component_settings_wins_over_parser_kwargs(self):
        """
        Issue #2115: on a key collision, ``parse_document`` must let the
        schema-validated, GUI-editable ``component_settings`` channel win over
        the legacy, seed-only ``parser_kwargs`` channel -- otherwise editing a
        component's settings via the admin "Advanced Settings" modal has no
        effect whenever the field name was also seeded into PARSER_KWARGS
        (e.g. LlamaParseParser's result_type/extract_layout/num_workers/
        language/verbose). Keys unique to parser_kwargs (e.g. a real secret
        like api_key, which the mutation layer refuses as plaintext in
        component_settings) must still pass through unchanged.
        """
        from dataclasses import dataclass, field

        from opencontractserver.documents.models import PipelineSettings
        from opencontractserver.pipeline.base.parser import BaseParser
        from opencontractserver.pipeline.base.settings_schema import (
            PipelineSetting,
            SettingType,
        )

        class MergePrecedenceParser(BaseParser):
            title = "MergePrecedenceParser"

            @dataclass
            class Settings:
                foo: str = field(
                    default="settings_default",
                    metadata={
                        "pipeline_setting": PipelineSetting(
                            setting_type=SettingType.OPTIONAL,
                            description="Test field for merge-precedence coverage.",
                        )
                    },
                )

            def _parse_document_impl(self, user_id, doc_id, **kwargs):
                return None

        full_path = (
            f"{MergePrecedenceParser.__module__}.{MergePrecedenceParser.__name__}"
        )

        pipeline_settings = PipelineSettings.get_instance(use_cache=False)
        pipeline_settings.parser_kwargs = {
            **pipeline_settings.parser_kwargs,
            full_path: {
                "foo": "from_parser_kwargs",
                "only_in_parser_kwargs": "kw_only_value",
            },
        }
        pipeline_settings.component_settings = {
            **pipeline_settings.component_settings,
            full_path: {"foo": "from_component_settings"},
        }
        pipeline_settings.save()
        PipelineSettings.clear_cache()
        self.addCleanup(PipelineSettings.clear_cache)

        parser = MergePrecedenceParser()
        # Mirror the one production call site (doc_tasks._resolve_parser_for_ingest):
        # direct_kwargs come from PipelineSettings.get_parser_kwargs(...).
        direct_kwargs = pipeline_settings.get_parser_kwargs(full_path)

        with patch.object(
            MergePrecedenceParser, "_parse_document_impl", return_value=None
        ) as mock_impl:
            parser.parse_document(self.user.id, self.doc.id, **direct_kwargs)

        self.assertTrue(mock_impl.called)
        _, call_kwargs = mock_impl.call_args
        self.assertEqual(
            call_kwargs["foo"],
            "from_component_settings",
            "component_settings must win over parser_kwargs on key collision.",
        )
        self.assertEqual(
            call_kwargs["only_in_parser_kwargs"],
            "kw_only_value",
            "Keys unique to parser_kwargs must still pass through unchanged.",
        )

    def test_parse_document_empty_component_settings_value_does_not_clobber_direct_kwargs(
        self,
    ):
        """
        Regression test: an empty-string placeholder in ``component_settings``
        must NOT override a real, truthy value already present in
        ``direct_kwargs``/legacy ``parser_kwargs``.

        Concretely this protects LlamaParse's env-seeded ``api_key``: the
        mutation layer's secret validation (``find_plaintext_secret_keys``)
        explicitly ALLOWS an empty-string placeholder for a SECRET-type field
        in ``component_settings`` (only non-empty plaintext secret values are
        flagged), while the real key is seeded only into legacy
        ``parser_kwargs``. Without this guard, ``component_settings`` winning
        on key collision (issue #2115) would let that empty placeholder wipe
        out the real secret on every parse.
        """
        from dataclasses import dataclass, field

        from opencontractserver.documents.models import PipelineSettings
        from opencontractserver.pipeline.base.parser import BaseParser
        from opencontractserver.pipeline.base.settings_schema import (
            PipelineSetting,
            SettingType,
        )

        class EmptyPlaceholderParser(BaseParser):
            title = "EmptyPlaceholderParser"

            @dataclass
            class Settings:
                api_key: str = field(
                    default="",
                    metadata={
                        "pipeline_setting": PipelineSetting(
                            setting_type=SettingType.SECRET,
                            description="Test secret field for empty-placeholder coverage.",
                        )
                    },
                )

            def _parse_document_impl(self, user_id, doc_id, **kwargs):
                return None

        full_path = (
            f"{EmptyPlaceholderParser.__module__}.{EmptyPlaceholderParser.__name__}"
        )

        pipeline_settings = PipelineSettings.get_instance(use_cache=False)
        pipeline_settings.parser_kwargs = {
            **pipeline_settings.parser_kwargs,
            full_path: {"api_key": "real-secret-value"},
        }
        pipeline_settings.component_settings = {
            **pipeline_settings.component_settings,
            full_path: {"api_key": ""},
        }
        pipeline_settings.save()
        PipelineSettings.clear_cache()
        self.addCleanup(PipelineSettings.clear_cache)

        parser = EmptyPlaceholderParser()
        # Mirror the one production call site (doc_tasks._resolve_parser_for_ingest):
        # direct_kwargs come from PipelineSettings.get_parser_kwargs(...).
        direct_kwargs = pipeline_settings.get_parser_kwargs(full_path)

        with patch.object(
            EmptyPlaceholderParser, "_parse_document_impl", return_value=None
        ) as mock_impl:
            parser.parse_document(self.user.id, self.doc.id, **direct_kwargs)

        self.assertTrue(mock_impl.called)
        _, call_kwargs = mock_impl.call_args
        self.assertEqual(
            call_kwargs["api_key"],
            "real-secret-value",
            "An empty-string placeholder in component_settings must not "
            "clobber a real value from direct_kwargs/parser_kwargs.",
        )

    def test_mock_parser_relationship_import(self):
        """
        Demonstrate a direct usage of a local parser class that returns real annotation data.
        This does NOT rely on ephemeral import, so it won't be discoverable through get_component_by_name,
        but it can still test annotation creation logic in the same suite.
        """
        from opencontractserver.pipeline.base.parser import BaseParser

        class LocalMockParser(BaseParser):
            """
            A mock parser that simulates parsing a document and returns
            an OpenContractDocExport with both annotations and relationships.
            """

            def _parse_document_impl(
                self, user_id: int, doc_id: int, **kwargs
            ) -> Optional[OpenContractDocExport]:
                annotation_data = [
                    {
                        "id": "a1",
                        "annotationLabel": "MockLabelA",
                        "rawText": "Hello World",
                        "page": 1,
                        "annotation_json": {"bounds": [0, 0, 10, 10]},
                        "parent_id": None,
                        "annotation_type": None,
                        "structural": False,
                    },
                    {
                        "id": "a2",
                        "annotationLabel": "MockLabelB",
                        "rawText": "Foo Bar",
                        "page": 1,
                        "annotation_json": {"bounds": [10, 10, 20, 20]},
                        "parent_id": "a1",
                        "annotation_type": None,
                        "structural": True,
                    },
                ]

                relationship_data = [
                    {
                        "id": "r1",
                        "relationshipLabel": "MockRelLabelA",
                        "source_annotation_ids": ["a1"],
                        "target_annotation_ids": ["a2"],
                    }
                ]

                export_data: OpenContractDocExport = {
                    "title": "Mock Document Title",
                    "content": "Some sample content for this mock doc.",
                    "description": None,
                    "pawls_file_content": [],
                    "page_count": 1,
                    "doc_labels": [],
                    "labelled_text": cast(
                        list[OpenContractsAnnotationPythonType], annotation_data
                    ),
                    "relationships": cast(
                        list[OpenContractsRelationshipPythonType], relationship_data
                    ),
                }
                return export_data

        parser = LocalMockParser()

        parsed_data = parser.parse_document(user_id=self.user.id, doc_id=self.doc.id)
        self.assertIsNotNone(
            parsed_data, "Parser should return a valid OpenContractDocExport."
        )
        assert parsed_data is not None

        parser.save_parsed_data(
            user_id=self.user.id,
            doc_id=self.doc.id,
            open_contracts_data=parsed_data,
            corpus_id=self.corpus.id,
            annotation_type="SPAN_LABEL",
        )

        # save_parsed_data internally calls add_document, which may return a new document
        # Refresh and get the actual document in the corpus
        corpus_docs = [dp.document for dp in self.corpus.document_paths.all()]
        self.assertEqual(
            len(corpus_docs), 1, "Should have exactly one document in corpus"
        )
        actual_doc = corpus_docs[0]
        self.assertIn(actual_doc, corpus_docs)

        self.assertEqual(Annotation.objects.count(), 2)
        ann_a = Annotation.objects.get(raw_text="Hello World")
        ann_b = Annotation.objects.get(raw_text="Foo Bar")
        self.assertIsNone(ann_a.parent)
        self.assertEqual(ann_b.parent, ann_a)
        self.assertTrue(ann_b.structural)

        self.assertEqual(Relationship.objects.count(), 1)
        relationship = Relationship.objects.first()
        assert relationship is not None
        assert relationship.relationship_label is not None
        self.assertEqual(relationship.relationship_label.text, "MockRelLabelA")

        label_a = AnnotationLabel.objects.get(text="MockLabelA")
        label_b = AnnotationLabel.objects.get(text="MockLabelB")
        rel_label = AnnotationLabel.objects.get(text="MockRelLabelA")

        self.assertEqual(label_a.label_type, "SPAN_LABEL")
        self.assertEqual(label_b.label_type, "SPAN_LABEL")
        self.assertEqual(rel_label.label_type, "RELATIONSHIP_LABEL")

        logger.info("LocalMockParser relationship import test passed successfully.")

    def test_create_structural_annotation_set_already_exists(self):
        """Test that _create_structural_annotation_set returns early when set exists."""
        from opencontractserver.annotations.models import StructuralAnnotationSet
        from opencontractserver.pipeline.base.parser import BaseParser

        # Create a structural annotation set for the document
        struct_set = StructuralAnnotationSet.objects.create(
            creator=self.user,
            content_hash="existing_hash",
            parser_name="TestParser",
            parser_version="1.0",
            page_count=1,
        )
        self.doc.structural_annotation_set = struct_set
        self.doc.save()

        class LocalParser(BaseParser):
            title = "LocalParser"

            def _parse_document_impl(self, user_id, doc_id, **kwargs):
                return None

        parser = LocalParser()

        # Should return early without creating a new set
        parser._create_structural_annotation_set(self.doc, self.user)

        # Should still have the same structural set
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.structural_annotation_set.pk, struct_set.pk)

    def test_create_structural_annotation_set_no_annotations(self):
        """Test _create_structural_annotation_set with no structural annotations."""
        from opencontractserver.pipeline.base.parser import BaseParser

        class LocalParser(BaseParser):
            title = "LocalParser"

            def _parse_document_impl(self, user_id, doc_id, **kwargs):
                return None

        parser = LocalParser()

        # Document has no structural annotations
        parser._create_structural_annotation_set(self.doc, self.user)

        # Should not create a structural set
        self.doc.refresh_from_db()
        self.assertIsNone(self.doc.structural_annotation_set)

    def test_create_structural_annotation_set_retry_reuses_orphaned_set(self):
        """Test _create_structural_annotation_set reuses orphaned set on retry.

        This tests the retry scenario where:
        1. First attempt creates StructuralAnnotationSet but crashes before document.save()
        2. Retry finds the orphaned set by content hash and links it

        The content hash is document-specific (pdf_file_hash or doc_{pk}), so this
        is NOT about sharing sets between documents - it's about idempotent retries.
        """
        from opencontractserver.annotations.models import StructuralAnnotationSet
        from opencontractserver.pipeline.base.parser import BaseParser

        # Set up a document with a content hash
        self.doc.pdf_file_hash = "doc_specific_hash_abc123"
        self.doc.save()

        # Simulate a previous failed attempt that created an orphaned set
        # (set was created but document wasn't linked before crash)
        orphaned_set = StructuralAnnotationSet.objects.create(
            creator=self.user,
            content_hash="doc_specific_hash_abc123",  # Same hash as document
            parser_name="LocalParser",
            parser_version="1.0",
            page_count=1,
        )

        # Create a structural annotation on the document (from the retry attempt)
        label = AnnotationLabel.objects.create(
            text="StructLabel", creator=self.user, label_type="SPAN_LABEL"
        )
        Annotation.objects.create(
            raw_text="Structural text",
            annotation_label=label,
            document=self.doc,
            creator=self.user,
            structural=True,
        )

        class LocalParser(BaseParser):
            title = "LocalParser"

            def _parse_document_impl(self, user_id, doc_id, **kwargs):
                return None

        parser = LocalParser()
        parser._create_structural_annotation_set(self.doc, self.user)

        # Should reuse the orphaned set from the failed first attempt
        self.doc.refresh_from_db()
        assert self.doc.structural_annotation_set is not None
        self.assertEqual(self.doc.structural_annotation_set.pk, orphaned_set.pk)

    def test_process_document_raises_on_none_return(self):
        """Test process_document raises DocumentParsingError when parser returns None."""
        from opencontractserver.pipeline.base.exceptions import DocumentParsingError
        from opencontractserver.pipeline.base.parser import BaseParser

        class NoneParser(BaseParser):
            title = "NoneParser"

            def _parse_document_impl(self, user_id, doc_id, **kwargs):
                return None

        parser = NoneParser()

        with self.assertRaises(DocumentParsingError) as ctx:
            parser.process_document(user_id=self.user.id, doc_id=self.doc.id)

        self.assertTrue(ctx.exception.is_transient)
        self.assertIn("returned None", str(ctx.exception))
