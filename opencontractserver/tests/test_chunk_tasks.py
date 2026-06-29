"""Tests for the chunked-parse Celery tasks (run eager)."""

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings

from opencontractserver.documents.models import Document
from opencontractserver.pipeline.chunk_artifacts import (
    chunk_output_key,
    read_chunk_result,
    write_chunk_pdf,
    write_chunk_result,
)
from opencontractserver.tasks.chunk_tasks import (
    parse_document_chunk,
    reassemble_and_save_chunks,
)
from opencontractserver.tests.helpers import make_test_pdf
from opencontractserver.tests.test_chunked_parser import (
    _FakeChunkedParser,
    _make_chunk_result,
)
from opencontractserver.utils.pdf_splitting import get_pdf_page_count

User = get_user_model()

# Registry name (dotted path) of the fake parser.
_FAKE = "opencontractserver.tests.test_chunked_parser._FakeChunkedParser"


class _NoneReturningChunkedParser(_FakeChunkedParser):
    """Chunked parser whose chunk impl returns None (simulates bad output)."""

    def _parse_single_chunk_impl(self, *args, **kwargs):
        return None


_NONE_PARSER = "opencontractserver.tests.test_chunk_tasks._NoneReturningChunkedParser"

# Module-level dict populated by _KwargRecordingChunkedParser so the test can
# inspect which kwargs were forwarded to _parse_single_chunk_impl.
_RECORDED_KWARGS: dict = {}


class _KwargRecordingChunkedParser(_FakeChunkedParser):
    """Records the kwargs passed to its chunk impl, for kwargs-threading tests."""

    def _parse_single_chunk_impl(self, *args, **kwargs):
        _RECORDED_KWARGS.clear()
        _RECORDED_KWARGS.update(kwargs)
        # Inline minimal body so we can pass *args positionally the same way
        # the base fake does, without relying on super() positional-arg forwarding.
        chunk_pdf_bytes = kwargs.get("chunk_pdf_bytes") or (
            args[2] if len(args) > 2 else b""
        )
        return _make_chunk_result(num_pages=get_pdf_page_count(chunk_pdf_bytes))


_KWREC_PARSER = "opencontractserver.tests.test_chunk_tasks._KwargRecordingChunkedParser"


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
class TestChunkTasks(TestCase):
    def _doc(self, pages: int):
        user = User.objects.create_user(username="ct", password="x")
        doc = Document(creator=user, title="t")
        doc.save()
        doc.pdf_file.save(f"doc_{doc.id}.pdf", ContentFile(make_test_pdf(pages)))
        return doc, user

    def test_parse_document_chunk_writes_result_and_returns_key(self):
        doc, user = self._doc(2)
        in_key = write_chunk_pdf(doc.id, 0, make_test_pdf(2))
        out_key = parse_document_chunk.apply(
            kwargs=dict(
                user_id=user.id,
                doc_id=doc.id,
                parser_name=_FAKE,
                chunk_index=0,
                total_chunks=1,
                page_offset=0,
                input_key=in_key,
            )
        ).get()
        self.assertEqual(out_key, chunk_output_key(doc.id, 0))
        result = read_chunk_result(out_key)
        self.assertEqual(result["page_count"], 2)

    def test_reassemble_and_save_persists_document(self):
        doc, user = self._doc(4)
        out0 = write_chunk_result(doc.id, 0, _make_chunk_result(num_pages=2))
        out1 = write_chunk_result(doc.id, 1, _make_chunk_result(num_pages=2))
        reassemble_and_save_chunks.apply(
            args=([out0, out1],),
            kwargs=dict(
                doc_id=doc.id,
                user_id=user.id,
                parser_name=_FAKE,
                corpus_id=None,
                page_offsets=[0, 2],
            ),
        ).get()
        doc.refresh_from_db()
        self.assertTrue(doc.pawls_parse_file)

    def test_parse_chunk_raises_on_none_result(self):
        from opencontractserver.pipeline.base.exceptions import DocumentParsingError

        doc, user = self._doc(2)
        in_key = write_chunk_pdf(doc.id, 0, make_test_pdf(2))
        with self.assertRaises(DocumentParsingError):
            parse_document_chunk.apply(
                kwargs=dict(
                    user_id=user.id,
                    doc_id=doc.id,
                    parser_name=_NONE_PARSER,
                    chunk_index=0,
                    total_chunks=1,
                    page_offset=0,
                    input_key=in_key,
                )
            ).get()

    def test_load_chunked_parser_rejects_non_chunking_parser(self):
        from opencontractserver.tasks.chunk_tasks import _load_chunked_parser

        with self.assertRaises(ValueError):
            _load_chunked_parser(
                "opencontractserver.pipeline.parsers.oc_text_parser.TxtParser"
            )

    def test_parse_chunk_threads_parser_kwargs(self):
        """parse_document_chunk must forward get_parser_kwargs to _parse_single_chunk_impl.

        The synchronous ingest path loads per-request flags (e.g. force_ocr) from
        PipelineSettings.get_parser_kwargs and passes them through process_document →
        parse_document → _parse_document_impl → _parse_single_chunk_impl.  The chord
        path must replicate this so large (chunked) documents honour the same
        admin-configured flags.
        """
        from unittest.mock import patch

        doc, user = self._doc(2)
        in_key = write_chunk_pdf(doc.id, 0, make_test_pdf(2))
        with patch(
            "opencontractserver.documents.models.PipelineSettings.get_parser_kwargs",
            return_value={"force_ocr": True},
        ):
            parse_document_chunk.apply(
                kwargs=dict(
                    user_id=user.id,
                    doc_id=doc.id,
                    parser_name=_KWREC_PARSER,
                    chunk_index=0,
                    total_chunks=1,
                    page_offset=0,
                    input_key=in_key,
                )
            ).get()
        self.assertEqual(_RECORDED_KWARGS.get("force_ocr"), True)

    def test_ingest_doc_large_pdf_replaces_with_chord_when_not_eager(self):
        """For a large doc with a chunked parser and eager=False, ingest_doc must
        dispatch via self.replace(chord(...)) and NOT call process_document."""
        from unittest.mock import patch

        from opencontractserver.tasks import doc_tasks

        doc, user = self._doc(6)  # max_pages_per_chunk=2, min=2 → 3 chunks
        # ingest_doc gates the chord path on current_app.conf.task_always_eager.
        # override_settings IS the correct lever here: Celery loads its conf via
        # config_from_object("django.conf:settings", namespace="CELERY") and reads
        # task_always_eager lazily, so CELERY_TASK_ALWAYS_EAGER=False propagates to
        # current_app.conf at access time. (Patching conf.task_always_eager directly
        # does NOT work — it reads through the lazy Django-settings loader.)
        with override_settings(CELERY_TASK_ALWAYS_EAGER=False):
            with patch.object(
                doc_tasks,
                "_resolve_parser_for_ingest",
                return_value=(
                    "opencontractserver.tests.test_chunked_parser._FakeChunkedParser",
                    _FakeChunkedParser(),
                    {},
                ),
            ), patch(
                "opencontractserver.pipeline.base.parser.BaseParser.process_document"
            ) as inline_parse, patch.object(
                doc_tasks.ingest_doc, "replace", side_effect=RuntimeError("replaced")
            ) as replace_mock:
                with self.assertRaises(RuntimeError):
                    doc_tasks.ingest_doc.apply(
                        kwargs=dict(user_id=user.id, doc_id=doc.id)
                    ).get()
                replace_mock.assert_called_once()
                inline_parse.assert_not_called()

    def test_ingest_doc_large_pdf_falls_back_when_chunk_count_exceeds_limit(self):
        """Do not enqueue more chord header tasks than max_concurrent_chunks."""
        from unittest.mock import patch

        from opencontractserver.tasks import doc_tasks

        doc, user = self._doc(8)  # max_pages_per_chunk=2, min=2 → 4 chunks
        parser = _FakeChunkedParser()
        parser.max_concurrent_chunks = 3
        with override_settings(CELERY_TASK_ALWAYS_EAGER=False):
            with patch.object(
                doc_tasks,
                "_resolve_parser_for_ingest",
                return_value=(
                    "opencontractserver.tests.test_chunked_parser._FakeChunkedParser",
                    parser,
                    {},
                ),
            ), patch.object(
                doc_tasks.ingest_doc, "replace"
            ) as replace_mock, patch.object(
                _FakeChunkedParser, "process_document", return_value=None
            ) as inline_parse:
                result = doc_tasks.ingest_doc.apply(
                    kwargs=dict(user_id=user.id, doc_id=doc.id)
                ).get()
                self.assertEqual(result["status"], "success")
                replace_mock.assert_not_called()
                inline_parse.assert_called_once()
