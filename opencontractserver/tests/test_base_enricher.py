"""Tests for the BaseEnricher abstract base class (settings injection)."""

from typing import ClassVar, cast

from django.test import TestCase

from opencontractserver.documents.models import PipelineSettings
from opencontractserver.pipeline.base.enricher import BaseEnricher
from opencontractserver.pipeline.base.file_types import FileTypeEnum
from opencontractserver.types.dicts import OpenContractDocExport


class _RecordingEnricher(BaseEnricher):
    """Test enricher that records the kwargs ``enrich_document`` forwards."""

    title = "Recording Enricher"
    supported_file_types: ClassVar[list[FileTypeEnum]] = [FileTypeEnum.PDF]

    def _enrich_document_impl(self, user_id, doc_id, export_data, **all_kwargs):
        self.received_kwargs = dict(all_kwargs)
        self.received_args = (user_id, doc_id)
        return export_data


class BaseEnricherTests(TestCase):
    """Verify BaseEnricher merges component settings with direct kwargs."""

    def setUp(self):
        PipelineSettings.clear_cache()

    def test_direct_kwargs_forwarded(self):
        """enrich_document forwards direct kwargs to _enrich_document_impl."""
        enricher = _RecordingEnricher()
        export = cast(OpenContractDocExport, {"labelled_text": []})
        result = enricher.enrich_document(7, 11, export, foo="bar")

        self.assertIs(result, export)
        self.assertEqual(enricher.received_args, (7, 11))
        self.assertEqual(enricher.received_kwargs, {"foo": "bar"})

    def test_component_settings_merged_and_overridden(self):
        """Direct kwargs override PipelineSettings component settings."""
        class_path = f"{_RecordingEnricher.__module__}.{_RecordingEnricher.__name__}"
        settings = PipelineSettings.get_instance(use_cache=False)
        settings.component_settings = {class_path: {"foo": "from_db", "baz": "db_only"}}
        settings.save()

        enricher = _RecordingEnricher()
        enricher.enrich_document(
            1, 2, cast(OpenContractDocExport, {"labelled_text": []}), foo="direct"
        )

        # Direct kwarg wins on conflict; DB-only setting is still injected.
        self.assertEqual(enricher.received_kwargs, {"foo": "direct", "baz": "db_only"})

    def test_base_enricher_is_abstract(self):
        """BaseEnricher cannot be instantiated directly."""
        with self.assertRaises(TypeError):
            BaseEnricher()  # type: ignore[abstract]
