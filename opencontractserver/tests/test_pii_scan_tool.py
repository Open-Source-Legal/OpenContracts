"""Tests for the scan_and_annotate_pii tool (privacy-filter client mocked)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from opencontractserver.annotations.models import SPAN_LABEL, TOKEN_LABEL, Annotation
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.llms.tools.core_tools._privacy_filter_client import Detection
from opencontractserver.llms.tools.core_tools.pii import (
    ENTITY_GROUP_LABELS,
    _persist_annotations_sync,
    ascan_and_annotate_pii,
)
from opencontractserver.tests.fixtures import (
    SAMPLE_PAWLS_FILE_ONE_PATH,
    SAMPLE_TXT_FILE_ONE_PATH,
)

User = get_user_model()


def _det(
    group: str, start: int, end: int, score: float = 0.95, text: str = ""
) -> Detection:
    return Detection(entity_group=group, score=score, start=start, end=end, text=text)


class _PiiPersistEmbeddingNoopMixin:
    """Stub out the on-commit Celery enqueue that
    ``_persist_annotations_sync`` registers per persisted annotation.

    Why:
    ``_persist_annotations_sync`` schedules
    ``calculate_embedding_for_annotation_text`` via
    ``transaction.on_commit`` inside an atomic block. With
    ``CELERY_TASK_ALWAYS_EAGER=True`` (see ``config/settings/test.py``)
    the task runs inline once the block commits. The eager task body
    reads the default embedder path from the ``PipelineSettings``
    singleton row seeded by migration 0031. But
    ``TransactionTestCase`` truncates *all* tables (incl.
    ``documents_pipelinesettings``) between tests by default
    (``serialized_rollback=False``), so any prior class on the same
    pytest-xdist ``--dist loadscope`` worker can leave us with no
    default embedder and the eager retry chain raises out of the
    on_commit callback. Tests in this module don't exercise embedding
    behaviour at all, so the cleanest fix is to patch the module-level
    ``_queue_embed`` factory to return a no-op callback for the
    duration of every test. Surgical and free of cross-test ordering
    surprises.
    """

    def setUp(self) -> None:  # noqa: D401
        super().setUp()  # type: ignore[misc]
        self._embed_patcher = patch(
            "opencontractserver.llms.tools.core_tools.pii._queue_embed",
            return_value=(lambda: None),
        )
        self._embed_patcher.start()
        self.addCleanup(self._embed_patcher.stop)  # type: ignore[attr-defined]


@override_settings(
    PRIVACY_FILTER_URL="http://privacy_filter:8000",
    PRIVACY_FILTER_API_KEY="dev-only-not-secret",
)
class ScanAndAnnotateTextTests(_PiiPersistEmbeddingNoopMixin, TransactionTestCase):

    def setUp(self) -> None:
        super().setUp()
        self.user = User.objects.create_user("pii_text_user", password="pw")
        self.corpus = Corpus.objects.create(title="PII Text Corpus", creator=self.user)

        self.txt_doc = Document.objects.create(
            creator=self.user,
            title="PII Text Doc",
            file_type="text/plain",
            processing_started=timezone.now(),
        )
        self.txt_doc.txt_extract_file.save(
            SAMPLE_TXT_FILE_ONE_PATH.name,
            ContentFile(SAMPLE_TXT_FILE_ONE_PATH.read_bytes()),
        )
        self.txt_doc, _, _ = self.corpus.add_document(
            document=self.txt_doc,
            user=self.user,
        )

        with self.txt_doc.txt_extract_file.open("r") as f:
            self.doc_text = f.read()

    async def test_text_doc_creates_span_label_annotations(self) -> None:
        # Place a fake email-shaped slice in the actual doc_text at offset 10.
        start = 10
        end = 30
        fake = [_det("private_email", start, end)]

        with patch(
            "opencontractserver.llms.tools.core_tools.pii.adetect_pii",
            new=AsyncMock(return_value=fake),
        ):
            result = await ascan_and_annotate_pii(
                document_id=self.txt_doc.id,
                corpus_id=self.corpus.id,
                creator_id=self.user.id,
            )

        assert result["detection_count"] == 1
        assert result["by_entity_group"] == {"private_email": 1}
        assert len(result["annotation_ids"]) == 1

        ann = await Annotation.objects.aget(pk=result["annotation_ids"][0])
        assert ann.annotation_type == SPAN_LABEL
        assert ann.json == {"start": start, "end": end}
        assert ann.raw_text == self.doc_text[start:end]
        assert ann.document_id == self.txt_doc.id

        from opencontractserver.annotations.models import AnnotationLabel

        label = await AnnotationLabel.objects.aget(pk=ann.annotation_label_id)
        expected_text, expected_color, expected_icon = ENTITY_GROUP_LABELS[
            "private_email"
        ]
        assert label.text == expected_text
        assert label.color == expected_color
        assert label.icon == expected_icon
        assert label.label_type == SPAN_LABEL

    async def test_corpus_action_id_propagates_to_created_annotations(self) -> None:
        """When a CorpusAction triggers the scan, its id must be carried
        through onto every persisted Annotation so action-trail rollups can
        attribute the PII labels back to the triggering action."""
        from asgiref.sync import sync_to_async

        from opencontractserver.corpuses.models import CorpusAction

        action = await sync_to_async(CorpusAction.objects.create)(
            name="trigger_pii_scan",
            corpus=self.corpus,
            trigger="add_document",
            task_instructions="Scan for PII on every new doc.",
            creator=self.user,
        )

        fake = [_det("private_email", 10, 30)]

        with patch(
            "opencontractserver.llms.tools.core_tools.pii.adetect_pii",
            new=AsyncMock(return_value=fake),
        ):
            result = await ascan_and_annotate_pii(
                document_id=self.txt_doc.id,
                corpus_id=self.corpus.id,
                creator_id=self.user.id,
                corpus_action_id=action.id,
            )

        assert result["detection_count"] == 1
        ann = await Annotation.objects.aget(pk=result["annotation_ids"][0])
        assert ann.corpus_action_id == action.id


@override_settings(
    PRIVACY_FILTER_URL="http://privacy_filter:8000",
    PRIVACY_FILTER_API_KEY="dev-only-not-secret",
)
class ScanAndAnnotatePdfTests(_PiiPersistEmbeddingNoopMixin, TransactionTestCase):

    def setUp(self) -> None:
        super().setUp()
        self.user = User.objects.create_user("pii_pdf_user", password="pw")
        self.corpus = Corpus.objects.create(title="PII PDF Corpus", creator=self.user)

        pawls_json = SAMPLE_PAWLS_FILE_ONE_PATH.read_text()
        self.pdf_doc = Document.objects.create(
            creator=self.user,
            title="PII PDF Doc",
            file_type="application/pdf",
            page_count=len(json.loads(pawls_json)),
            processing_started=timezone.now(),
        )
        self.pdf_doc.pawls_parse_file.save(
            SAMPLE_PAWLS_FILE_ONE_PATH.name, ContentFile(pawls_json.encode())
        )
        self.pdf_doc, _, _ = self.corpus.add_document(
            document=self.pdf_doc,
            user=self.user,
        )

        # Build the same doc_text the tool will see so we can pick a valid
        # (start, end) range that actually maps to tokens.
        import json as _json

        from plasmapdf.models.PdfDataLayer import build_translation_layer

        from opencontractserver.utils.compact_pawls import expand_pawls_pages

        with self.pdf_doc.pawls_parse_file.open("r") as f:
            pawls_tokens = expand_pawls_pages(_json.load(f))
        layer = build_translation_layer(pawls_tokens)
        self.doc_text = layer.doc_text

        # Find a real word in the doc_text to use as the fake "PII" target.
        target = "Agreement"
        idx = self.doc_text.find(target)
        assert idx >= 0, "Test fixture must contain the string 'Agreement'."
        self.det_start = idx
        self.det_end = idx + len(target)

    async def test_pdf_doc_creates_token_label_annotations(self) -> None:
        fake = [_det("person_name", self.det_start, self.det_end)]

        with patch(
            "opencontractserver.llms.tools.core_tools.pii.adetect_pii",
            new=AsyncMock(return_value=fake),
        ):
            result = await ascan_and_annotate_pii(
                document_id=self.pdf_doc.id,
                corpus_id=self.corpus.id,
                creator_id=self.user.id,
            )

        assert result["detection_count"] == 1
        assert result["by_entity_group"] == {"person_name": 1}
        assert len(result["annotation_ids"]) == 1

        ann = await Annotation.objects.aget(pk=result["annotation_ids"][0])
        assert ann.annotation_type == TOKEN_LABEL
        # PlasmaPDF returns a MultipageAnnotationJson; ensure key shape.
        assert isinstance(ann.json, dict)
        assert ann.json  # non-empty
        assert "Agreement" in ann.raw_text

        from opencontractserver.annotations.models import AnnotationLabel

        label = await AnnotationLabel.objects.aget(pk=ann.annotation_label_id)
        expected_text, _, _ = ENTITY_GROUP_LABELS["person_name"]
        assert label.text == expected_text
        assert label.label_type == TOKEN_LABEL


@override_settings(
    PRIVACY_FILTER_URL="http://privacy_filter:8000",
    PRIVACY_FILTER_API_KEY="dev-only-not-secret",
)
class ScanAndAnnotateKnobsTests(_PiiPersistEmbeddingNoopMixin, TransactionTestCase):

    def setUp(self) -> None:
        super().setUp()
        self.user = User.objects.create_user("pii_knob_user", password="pw")
        self.corpus = Corpus.objects.create(title="PII Knob Corpus", creator=self.user)
        self.txt_doc = Document.objects.create(
            creator=self.user,
            title="Knob Doc",
            file_type="text/plain",
            processing_started=timezone.now(),
        )
        self.txt_doc.txt_extract_file.save(
            SAMPLE_TXT_FILE_ONE_PATH.name,
            ContentFile(SAMPLE_TXT_FILE_ONE_PATH.read_bytes()),
        )
        self.txt_doc, _, _ = self.corpus.add_document(
            document=self.txt_doc,
            user=self.user,
        )
        with self.txt_doc.txt_extract_file.open("r") as f:
            self.doc_text = f.read()

    async def _call(self, fake_detections, **kwargs) -> dict:
        with patch(
            "opencontractserver.llms.tools.core_tools.pii.adetect_pii",
            new=AsyncMock(return_value=fake_detections),
        ):
            return await ascan_and_annotate_pii(
                document_id=self.txt_doc.id,
                corpus_id=self.corpus.id,
                creator_id=self.user.id,
                **kwargs,
            )

    async def test_dry_run_does_not_persist(self) -> None:
        fake = [_det("private_email", 10, 30)]
        result = await self._call(fake, dry_run=True)
        assert result["annotation_ids"] == []
        assert len(result["detections"]) == 1
        n = await Annotation.objects.filter(document_id=self.txt_doc.id).acount()
        assert n == 0

    async def test_min_score_filters_low_confidence(self) -> None:
        fake = [
            _det("private_email", 10, 30, score=0.4),
            _det("private_email", 50, 70, score=0.95),
        ]
        result = await self._call(fake, min_score=0.6)
        assert result["detection_count"] == 1
        assert result["by_entity_group"] == {"private_email": 1}

    async def test_entity_groups_allowlist(self) -> None:
        fake = [
            _det("private_email", 10, 30),
            _det("phone_number", 50, 70),
            _det("person_name", 80, 100),
        ]
        result = await self._call(fake, entity_groups=["private_email", "person_name"])
        assert result["detection_count"] == 2
        assert set(result["by_entity_group"].keys()) == {"private_email", "person_name"}

    async def test_entity_groups_rejects_unknown_group(self) -> None:
        """Typos in entity_groups must surface as a clear error, not a silent
        no-op detection-count of 0.
        """

        async def _fake_detect(text: str):
            return []

        with patch(
            "opencontractserver.llms.tools.core_tools.pii.adetect_pii",
            new=_fake_detect,
        ):
            with self.assertRaises(ValueError) as ctx:
                await ascan_and_annotate_pii(
                    document_id=self.txt_doc.id,
                    corpus_id=self.corpus.id,
                    creator_id=self.user.id,
                    entity_groups=["private_email", "typo_email"],
                )
        self.assertIn("typo_email", str(ctx.exception))

    async def test_char_range_scopes_scan_and_remaps_offsets(self) -> None:
        # The mock receives a *slice* of doc_text; its offsets are
        # slice-relative. The tool must remap them to global coords.
        slice_start = 100
        slice_end = 400
        fake_local = [_det("private_email", 5, 25)]

        captured: dict[str, str] = {}

        async def _fake_detect(text: str):
            captured["text"] = text
            return fake_local

        with patch(
            "opencontractserver.llms.tools.core_tools.pii.adetect_pii",
            new=_fake_detect,
        ):
            result = await ascan_and_annotate_pii(
                document_id=self.txt_doc.id,
                corpus_id=self.corpus.id,
                creator_id=self.user.id,
                start_char=slice_start,
                end_char=slice_end,
            )

        assert captured["text"] == self.doc_text[slice_start:slice_end]
        assert result["detection_count"] == 1
        ann = await Annotation.objects.aget(pk=result["annotation_ids"][0])
        # Global offsets = slice_start + local.
        assert ann.json == {"start": slice_start + 5, "end": slice_start + 25}
        assert ann.raw_text == self.doc_text[slice_start + 5 : slice_start + 25]

    async def test_inverted_char_range_returns_empty_without_calling_service(
        self,
    ) -> None:
        # start_char > end_char (or any range that resolves to s >= e) is an
        # explicit no-op: we must short-circuit before issuing a request
        # against the privacy-filter service.
        called = {"count": 0}

        async def _fake_detect(text: str):
            called["count"] += 1
            return []

        with patch(
            "opencontractserver.llms.tools.core_tools.pii.adetect_pii",
            new=_fake_detect,
        ):
            result = await ascan_and_annotate_pii(
                document_id=self.txt_doc.id,
                corpus_id=self.corpus.id,
                creator_id=self.user.id,
                start_char=400,
                end_char=100,
            )

        assert called["count"] == 0
        assert result == {
            "document_id": self.txt_doc.id,
            "scanned_chars": 0,
            "detection_count": 0,
            "by_entity_group": {},
            "annotation_ids": [],
            "detections": [],
        }


@override_settings(
    PRIVACY_FILTER_URL="http://privacy_filter:8000",
    PRIVACY_FILTER_API_KEY="dev-only-not-secret",
)
class ScanAndAnnotateEdgeCaseTests(_PiiPersistEmbeddingNoopMixin, TransactionTestCase):

    def setUp(self) -> None:
        super().setUp()
        self.user = User.objects.create_user("pii_edge_user", password="pw")
        self.corpus = Corpus.objects.create(title="PII Edge Corpus", creator=self.user)
        self.txt_doc = Document.objects.create(
            creator=self.user,
            title="Edge Doc",
            file_type="text/plain",
            processing_started=timezone.now(),
        )
        self.txt_doc.txt_extract_file.save(
            SAMPLE_TXT_FILE_ONE_PATH.name,
            ContentFile(SAMPLE_TXT_FILE_ONE_PATH.read_bytes()),
        )
        self.txt_doc, _, _ = self.corpus.add_document(
            document=self.txt_doc,
            user=self.user,
        )

    async def test_oob_detection_skipped(self) -> None:
        # End past the end of doc_text — should be skipped, not crash.
        with self.txt_doc.txt_extract_file.open("r") as f:
            doc_len = len(f.read())
        fake = [_det("private_email", doc_len - 5, doc_len + 100)]
        with patch(
            "opencontractserver.llms.tools.core_tools.pii.adetect_pii",
            new=AsyncMock(return_value=fake),
        ):
            result = await ascan_and_annotate_pii(
                document_id=self.txt_doc.id,
                corpus_id=self.corpus.id,
                creator_id=self.user.id,
            )
        # Zero annotations, zero crashes.
        assert result["annotation_ids"] == []

    async def test_unsupported_file_type_raises(self) -> None:
        from asgiref.sync import sync_to_async

        def _create_png_doc():
            png_doc = Document.objects.create(
                creator=self.user,
                title="PNG Doc",
                file_type="image/png",
                processing_started=timezone.now(),
            )
            doc, _, _ = self.corpus.add_document(document=png_doc, user=self.user)
            return doc

        png_doc = await sync_to_async(_create_png_doc)()
        with patch(
            "opencontractserver.llms.tools.core_tools.pii.adetect_pii",
            new=AsyncMock(return_value=[]),
        ):
            with self.assertRaises(ValueError):
                await ascan_and_annotate_pii(
                    document_id=png_doc.id,
                    corpus_id=self.corpus.id,
                    creator_id=self.user.id,
                )

    async def test_document_not_in_corpus_raises(self) -> None:
        from asgiref.sync import sync_to_async

        def _create_other_corpus():
            return Corpus.objects.create(title="Other", creator=self.user)

        other_corpus = await sync_to_async(_create_other_corpus)()
        with patch(
            "opencontractserver.llms.tools.core_tools.pii.adetect_pii",
            new=AsyncMock(return_value=[]),
        ):
            with self.assertRaises(ValueError):
                await ascan_and_annotate_pii(
                    document_id=self.txt_doc.id,
                    corpus_id=other_corpus.id,
                    creator_id=self.user.id,
                )

    @override_settings(PRIVACY_FILTER_URL="")
    async def test_service_unconfigured_raises_runtime_error(self) -> None:
        # Use the *real* client (not mocked) — settings drive the failure path.
        with self.assertRaises(RuntimeError) as exc:
            await ascan_and_annotate_pii(
                document_id=self.txt_doc.id,
                corpus_id=self.corpus.id,
                creator_id=self.user.id,
            )
        assert "not configured" in str(exc.exception).lower()


class ScanAndAnnotateRegistryTests(TestCase):
    """Confirm the tool is registered with the correct flags and parameters."""

    def test_tool_registered_with_correct_flags(self) -> None:
        from opencontractserver.llms.tools.tool_registry import (
            AVAILABLE_TOOLS,
            ToolCategory,
        )

        match = [t for t in AVAILABLE_TOOLS if t.name == "scan_and_annotate_pii"]
        assert len(match) == 1, "Tool must be registered exactly once."
        td = match[0]
        assert td.category == ToolCategory.ANNOTATIONS
        assert td.requires_corpus is True
        assert td.requires_approval is True
        assert td.requires_write_permission is True
        param_names = {p[0] for p in td.parameters}
        assert param_names == {
            "min_score",
            "entity_groups",
            "dry_run",
            "start_char",
            "end_char",
        }

    def test_tool_resolves_to_runtime_callable(self) -> None:
        from opencontractserver.llms.tools.tool_registry import (
            ToolFunctionRegistry,
        )

        registry = ToolFunctionRegistry.get()
        core_tool = registry.to_core_tool("scan_and_annotate_pii")
        assert (
            core_tool is not None
        ), "Tool missing from FUNCTION_MAP — agents cannot invoke it at runtime."
        # CoreTool exposes the metadata fields too; confirm consistency.
        assert core_tool.metadata.name == "scan_and_annotate_pii"
        assert core_tool.requires_approval is True
        assert core_tool.requires_write_permission is True


@override_settings(
    PRIVACY_FILTER_URL="http://privacy_filter:8000",
    PRIVACY_FILTER_API_KEY="dev-only-not-secret",
)
class PersistAnnotationsLabelRaceTests(_PiiPersistEmbeddingNoopMixin, TestCase):
    """Regression guard for the accepted-duplicate behavior of
    ``Corpus.ensure_label_and_labelset`` under PostgreSQL READ COMMITTED.

    The lookup at ``corpuses/models.py``'s ``ensure_label_and_labelset`` is a
    check-then-create wrapped in ``transaction.atomic()``, but with no
    DB-level uniqueness on ``AnnotationLabel(text, label_type)`` two
    concurrent transactions can both pass ``filter().first()`` before either
    commits its ``create()``, so each one inserts a fresh label. The PII
    scan tool accepts that rare duplicate — the inner atomic block in
    ``_persist_annotations_sync`` only inserts ``Annotation`` rows (no
    cross-row uniqueness), so the much larger annotation batch never rolls
    back due to a peer scan racing on the label table.

    This test documents that contract. If somebody later adds a
    ``UniqueConstraint(fields=["text", "label_type"], ...)`` on
    ``AnnotationLabel``, this test fails and they are forced to revisit the
    trade-off described in ``pii.py``'s ``_persist_annotations_sync``
    block comment.
    """

    def setUp(self) -> None:
        super().setUp()  # _PiiPersistEmbeddingNoopMixin handles the patcher.
        self.user = User.objects.create_user("pii_race_user", password="pw")
        self.corpus = Corpus.objects.create(title="PII Race Corpus", creator=self.user)

        self.txt_doc = Document.objects.create(
            creator=self.user,
            title="PII Race Doc",
            file_type="text/plain",
            processing_started=timezone.now(),
        )
        self.txt_doc.txt_extract_file.save(
            SAMPLE_TXT_FILE_ONE_PATH.name,
            ContentFile(SAMPLE_TXT_FILE_ONE_PATH.read_bytes()),
        )
        self.txt_doc, _, _ = self.corpus.add_document(
            document=self.txt_doc,
            user=self.user,
        )
        with self.txt_doc.txt_extract_file.open("r") as f:
            self.doc_text = f.read()

    def test_persist_annotations_sync_duplicate_label_race(self) -> None:
        from opencontractserver.annotations.models import AnnotationLabel, LabelSet

        expected_label_text = ENTITY_GROUP_LABELS["private_email"][0]

        # First scan: normal path — one label created, one annotation persisted.
        persisted_1 = _persist_annotations_sync(
            doc=self.txt_doc,
            corpus=self.corpus,
            pdf_layer=None,
            creator_id=self.user.id,
            corpus_action_id=None,
            file_type="text/plain",
            detections=[_det("private_email", 10, 30)],
            doc_text=self.doc_text,
        )
        self.assertEqual(len(persisted_1), 1)
        self.assertEqual(
            AnnotationLabel.objects.filter(
                text=expected_label_text, label_type=SPAN_LABEL
            ).count(),
            1,
        )

        # Reload corpus state so the patched method sees a non-None label_set.
        self.corpus.refresh_from_db()

        # Simulate the post-race outcome: ensure_label_and_labelset's
        # filter(...).first() returned None even though a label already
        # exists, so a fresh AnnotationLabel is inserted.
        #
        # NOTE: this mock's keyword arguments must stay in sync with
        # ``Corpus.ensure_label_and_labelset``'s real signature
        # (opencontractserver/corpuses/models.py). If that method grows a
        # new keyword arg, this mock will silently swallow it and the race
        # simulation will drift — update the kwargs here when that happens.
        def race_ensure(
            self_corpus,
            *,
            label_text,
            creator_id,
            label_type,
            color="#05313d",
            description="",
            icon="tags",
        ):
            if self_corpus.label_set is None:
                self_corpus.label_set = LabelSet.objects.create(
                    title=f"Corpus {self_corpus.pk} Set",
                    description="Auto-created label set",
                    creator_id=creator_id,
                )
                self_corpus.save(update_fields=["label_set", "modified"])
            label = AnnotationLabel.objects.create(
                text=label_text,
                label_type=label_type,
                color=color,
                description=description,
                icon=icon,
                creator_id=creator_id,
            )
            self_corpus.label_set.annotation_labels.add(label)
            return label

        with patch.object(Corpus, "ensure_label_and_labelset", new=race_ensure):
            persisted_2 = _persist_annotations_sync(
                doc=self.txt_doc,
                corpus=self.corpus,
                pdf_layer=None,
                creator_id=self.user.id,
                corpus_action_id=None,
                file_type="text/plain",
                detections=[_det("private_email", 50, 70)],
                doc_text=self.doc_text,
            )

        # Annotation insert still succeeds under the simulated race.
        self.assertEqual(len(persisted_2), 1)

        # Two labels now exist for the same (text, label_type) — the
        # accepted duplicate the comment in pii.py describes.
        self.assertEqual(
            AnnotationLabel.objects.filter(
                text=expected_label_text, label_type=SPAN_LABEL
            ).count(),
            2,
        )

        # The two annotations point at different label rows (each scan
        # carries its own race-created label forward onto its annotation).
        ann_1_id = persisted_1[0][0]
        ann_2_id = persisted_2[0][0]
        ann_1 = Annotation.objects.get(pk=ann_1_id)
        ann_2 = Annotation.objects.get(pk=ann_2_id)
        self.assertNotEqual(ann_1.annotation_label_id, ann_2.annotation_label_id)


@override_settings(
    PRIVACY_FILTER_URL="http://privacy.test",
    PRIVACY_FILTER_API_KEY="dev-only-not-secret",
)
class PersistAnnotationsUnknownGroupTests(_PiiPersistEmbeddingNoopMixin, TestCase):
    """Defensive coverage: ``_persist_annotations_sync`` is called via a
    sync_to_async wrapper inside ``ascan_and_annotate_pii``, which already
    rejects unknown entity groups at the public-API boundary
    (``test_entity_groups_rejects_unknown_group``). The lower-level helper
    must also fail safely if a future caller bypasses that boundary check
    and hands it a detection with a group that is not in
    ``ENTITY_GROUP_LABELS``."""

    def setUp(self) -> None:
        super().setUp()  # _PiiPersistEmbeddingNoopMixin handles the patcher.
        self.user = User.objects.create_user("pii_unknown_user", password="pw")
        self.corpus = Corpus.objects.create(
            title="PII Unknown Group Corpus", creator=self.user
        )
        self.txt_doc = Document.objects.create(
            creator=self.user,
            title="PII Unknown Group Doc",
            file_type="text/plain",
            processing_started=timezone.now(),
        )
        self.txt_doc.txt_extract_file.save(
            SAMPLE_TXT_FILE_ONE_PATH.name,
            ContentFile(SAMPLE_TXT_FILE_ONE_PATH.read_bytes()),
        )
        self.txt_doc, _, _ = self.corpus.add_document(
            document=self.txt_doc,
            user=self.user,
        )
        with self.txt_doc.txt_extract_file.open("r") as f:
            self.doc_text = f.read()

    def test_unknown_entity_group_is_skipped_silently(self) -> None:
        """An unknown ``entity_group`` is filtered out of ``needed_groups``
        (so no spurious ``AnnotationLabel`` is ever created) AND skipped in
        the per-detection loop (so no annotation is persisted). The known
        group in the same batch still lands."""
        from opencontractserver.annotations.models import AnnotationLabel

        existing_label_ids = set(AnnotationLabel.objects.values_list("id", flat=True))

        persisted = _persist_annotations_sync(
            doc=self.txt_doc,
            corpus=self.corpus,
            pdf_layer=None,
            creator_id=self.user.id,
            corpus_action_id=None,
            file_type="text/plain",
            detections=[
                _det("private_email", 10, 30),
                _det("not_a_real_group_X", 40, 60),
            ],
            doc_text=self.doc_text,
        )

        # Exactly one annotation persisted (the known group).
        self.assertEqual(len(persisted), 1)

        # No label was created for the unknown group — the only new label
        # is for ``private_email``.
        expected_known_label = ENTITY_GROUP_LABELS["private_email"][0]
        new_labels = AnnotationLabel.objects.exclude(id__in=existing_label_ids)
        new_label_texts = list(new_labels.values_list("text", flat=True))
        self.assertEqual(new_label_texts, [expected_known_label])
