"""Tests for the ingest-time enrichment stage.

Covers the ``run_enrichers`` chain runner and the wiring of the enrichment
stage into ``BaseParser.process_document``. ``save_parsed_data`` is mocked so
these tests exercise the parse -> enrich -> save chain without the persistence
or embedding machinery.
"""

from collections.abc import Mapping
from typing import Any, ClassVar, cast
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from opencontractserver.annotations.models import TOKEN_LABEL
from opencontractserver.documents.models import Document, PipelineSettings
from opencontractserver.pipeline.base.enricher import BaseEnricher
from opencontractserver.pipeline.base.file_types import FileTypeEnum
from opencontractserver.pipeline.base.parser import BaseParser
from opencontractserver.pipeline.utils import run_enrichers
from opencontractserver.types.dicts import OpenContractDocExport
from opencontractserver.users.models import User

PDF_MIME = "application/pdf"


# --------------------------------------------------------------------------- #
# Test doubles (referenced by full dotted path via get_component_by_name)
# --------------------------------------------------------------------------- #
class _MarkerEnricher(BaseEnricher):
    """Appends one identifiable marker entry to labelled_text."""

    title = "Marker Enricher"
    supported_file_types: ClassVar[list[FileTypeEnum]] = [FileTypeEnum.PDF]
    MARKER = "?"

    def _enrich_document_impl(self, user_id, doc_id, export_data, **all_kwargs):
        entry = {
            "id": f"stub-{self.MARKER}",
            "annotationLabel": "STUB",
            "rawText": self.MARKER,
            "page": 0,
            "annotation_json": {},
            "parent_id": None,
            "annotation_type": TOKEN_LABEL,
            "structural": False,
        }
        new = dict(export_data)
        new["labelled_text"] = list(export_data.get("labelled_text", [])) + [entry]
        return new


class _EnricherA(_MarkerEnricher):
    MARKER = "A"


class _EnricherB(_MarkerEnricher):
    MARKER = "B"


class _BoomEnricher(BaseEnricher):
    """An enricher that always raises — used to verify failure isolation."""

    title = "Boom Enricher"
    supported_file_types: ClassVar[list[FileTypeEnum]] = [FileTypeEnum.PDF]

    def _enrich_document_impl(self, user_id, doc_id, export_data, **all_kwargs):
        raise RuntimeError("enricher boom")


class _StubParser(BaseParser):
    """A parser whose _parse_document_impl returns a preset export payload."""

    title = "Stub Parser"
    supported_file_types: ClassVar[list[FileTypeEnum]] = [FileTypeEnum.PDF]
    export_payload: "dict | None" = None

    def _parse_document_impl(self, user_id, doc_id, **all_kwargs):
        return self.export_payload


_A_PATH = f"{__name__}._EnricherA"
_B_PATH = f"{__name__}._EnricherB"
_BOOM_PATH = f"{__name__}._BoomEnricher"
_PARSER_PATH = "opencontractserver.pipeline.parsers.oc_text_parser.TxtParser"


def _markers(export: Mapping[str, Any]) -> list[str]:
    """Return the marker strings appended by _MarkerEnricher instances."""
    return [
        a["rawText"]
        for a in export.get("labelled_text", [])
        if a.get("annotationLabel") == "STUB"
    ]


class RunEnrichersTests(TestCase):
    """Tests for the run_enrichers chain runner."""

    def setUp(self):
        PipelineSettings._invalidate_cache()

    def test_empty_list_returns_input_unchanged(self):
        export = cast(OpenContractDocExport, {"labelled_text": []})
        result = run_enrichers([], 1, 1, export)
        self.assertIs(result, export)

    def test_chain_composes_in_order(self):
        result = run_enrichers(
            [_A_PATH, _B_PATH],
            1,
            1,
            cast(OpenContractDocExport, {"labelled_text": []}),
        )
        self.assertEqual(_markers(result), ["A", "B"])

    def test_failing_enricher_is_isolated(self):
        """A raising enricher is skipped; the chain continues, no exception."""
        result = run_enrichers(
            [_A_PATH, _BOOM_PATH, _B_PATH],
            1,
            1,
            cast(OpenContractDocExport, {"labelled_text": []}),
        )
        # A and B still applied; the boom enricher contributed nothing.
        self.assertEqual(_markers(result), ["A", "B"])

    def test_non_enricher_class_skipped(self):
        """A path that resolves to a non-BaseEnricher class is skipped."""
        export = cast(OpenContractDocExport, {"labelled_text": []})
        result = run_enrichers([_PARSER_PATH], 1, 1, export)
        self.assertEqual(_markers(result), [])

    def test_unresolvable_path_skipped(self):
        """A class path that cannot be imported is skipped, not fatal."""
        export = cast(OpenContractDocExport, {"labelled_text": []})
        result = run_enrichers(["does.not.exist.Nope"], 1, 1, export)
        self.assertEqual(_markers(result), [])


class ProcessDocumentEnrichmentWiringTests(TestCase):
    """Tests that BaseParser.process_document runs the configured chain."""

    user: User

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = User.objects.create_user(
            username="enrich_wiring_user", password="pw"
        )

    def setUp(self):
        PipelineSettings._invalidate_cache()
        self.doc = Document.objects.create(
            creator=self.user,
            title="Wiring Doc",
            file_type=PDF_MIME,
            page_count=1,
            processing_started=timezone.now(),
        )

    def _set_enrichers(self, paths: list[str]) -> None:
        settings = PipelineSettings.get_instance(use_cache=False)
        settings.preferred_enrichers = {PDF_MIME: paths} if paths else {}
        settings.save()

    def _run(self) -> dict:
        """Run process_document with save_parsed_data mocked; return the
        OpenContractDocExport that would have been persisted."""
        parser = _StubParser()
        parser.export_payload = {"labelled_text": [], "content": ""}
        with patch.object(BaseParser, "save_parsed_data") as mock_save:
            parser.process_document(self.user.id, self.doc.id, corpus_id=None)
        self.assertTrue(mock_save.called)
        # process_document passes the export positionally today; fall back to
        # the keyword name so this survives a future signature change.
        call = mock_save.call_args
        if len(call.args) > 2:
            return call.args[2]
        return call.kwargs["open_contracts_data"]

    def test_configured_enricher_runs(self):
        self._set_enrichers([_A_PATH])
        persisted = self._run()
        self.assertEqual(_markers(persisted), ["A"])

    def test_no_enrichers_when_unconfigured(self):
        self._set_enrichers([])
        persisted = self._run()
        self.assertEqual(_markers(persisted), [])

    def test_multiple_enrichers_chain_in_order(self):
        self._set_enrichers([_A_PATH, _B_PATH])
        persisted = self._run()
        self.assertEqual(_markers(persisted), ["A", "B"])

    def test_failing_enricher_does_not_break_ingestion(self):
        """A raising enricher must not stop the document from being saved."""
        self._set_enrichers([_BOOM_PATH])
        # Must not raise — save_parsed_data is still reached.
        persisted = self._run()
        self.assertEqual(_markers(persisted), [])

    def test_enrichment_stage_swallows_resolution_failure(self):
        """Even a failure resolving the enricher list returns parsed_data.

        ``_run_enrichment_stage`` wraps the whole resolution+run path so that
        an unexpected error (here: a non-existent document id, which makes the
        ``file_type`` lookup raise ``Document.DoesNotExist``) is logged and the
        un-enriched data is returned rather than failing ingestion.
        """
        parser = _StubParser()
        parsed = cast(OpenContractDocExport, {"labelled_text": [], "content": ""})
        result = parser._run_enrichment_stage(self.user.id, 99_999_999, parsed)
        self.assertIs(result, parsed)
