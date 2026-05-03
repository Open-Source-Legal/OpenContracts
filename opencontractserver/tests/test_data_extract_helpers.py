"""Targeted unit tests for the small helpers introduced alongside the
benchmark harness: retrieval-citation linking, model-override allowlist
guard, and the cross-encoder reranker scoring path.

These are pure-Python helpers that don't go through the agent runtime,
so they can be exercised with mocked message logs and lightweight
fixtures without spinning up a full extraction.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from opencontractserver.annotations.models import (
    SPAN_LABEL,
    Annotation,
    AnnotationLabel,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.extracts.models import (
    Column,
    Datacell,
    Extract,
    Fieldset,
)

User = get_user_model()


def _build_datacell_with_annotations(test):
    """Return a ``(datacell, annotation_ids)`` tuple wired up minimally."""
    user = User.objects.create_user(
        username="extract_helpers_user", password="testpass"
    )
    corpus = Corpus.objects.create(title="ExtractHelpers Corpus", creator=user)
    document = Document.objects.create(
        title="ExtractHelpers Doc",
        creator=user,
        file_type="text/plain",
    )
    corpus.add_document(document=document, user=user)

    label = AnnotationLabel.objects.create(
        text="ExtractHelpersLabel", creator=user, label_type=SPAN_LABEL
    )

    annotations = [
        Annotation.objects.create(
            document=document,
            corpus=corpus,
            annotation_label=label,
            annotation_type=SPAN_LABEL,
            raw_text=f"hit {i}",
            json={"start": i, "end": i + 4},
            creator=user,
            page=1,
        )
        for i in range(3)
    ]

    fieldset = Fieldset.objects.create(name="ExtractHelpers FS", creator=user)
    column = Column.objects.create(
        fieldset=fieldset,
        name="Hits",
        query="anything",
        output_type="str",
        creator=user,
    )
    extract = Extract.objects.create(
        name="ExtractHelpers Extract",
        corpus=corpus,
        fieldset=fieldset,
        creator=user,
    )
    datacell = Datacell.objects.create(
        extract=extract,
        column=column,
        document=document,
        creator=user,
        data={"data": "anything"},
    )
    return datacell, [a.id for a in annotations]


class LinkRetrievalCitationsTests(TestCase):
    """Cover ``_link_retrieval_citations``'s defensive filtering path."""

    def test_real_ids_are_linked_to_sources(self) -> None:
        from asgiref.sync import async_to_sync

        from opencontractserver.tasks.data_extract_tasks import (
            _link_retrieval_citations,
        )

        datacell, annotation_ids = _build_datacell_with_annotations(self)

        async_to_sync(_link_retrieval_citations)(datacell, annotation_ids)

        datacell.refresh_from_db()
        self.assertEqual(
            set(datacell.sources.values_list("id", flat=True)),
            set(annotation_ids),
        )

    def test_non_int_and_negative_ids_are_dropped(self) -> None:
        from asgiref.sync import async_to_sync

        from opencontractserver.tasks.data_extract_tasks import (
            _link_retrieval_citations,
        )

        datacell, annotation_ids = _build_datacell_with_annotations(self)

        # Inject a hostile mix: floats, negative ints, strings, valid ids
        async_to_sync(_link_retrieval_citations)(
            datacell,
            [None, -1, 0, "5", 1.5, *annotation_ids],
        )

        datacell.refresh_from_db()
        # Only the real positive ints survive the filter
        self.assertEqual(
            set(datacell.sources.values_list("id", flat=True)),
            set(annotation_ids),
        )

    def test_missing_ids_silently_ignored(self) -> None:
        """A row deleted between retrieval and link must not blow up."""
        from asgiref.sync import async_to_sync

        from opencontractserver.tasks.data_extract_tasks import (
            _link_retrieval_citations,
        )

        datacell, annotation_ids = _build_datacell_with_annotations(self)
        # Reference an annotation id that doesn't exist plus the real ones
        bogus_id = max(annotation_ids) + 9999

        async_to_sync(_link_retrieval_citations)(datacell, [bogus_id, *annotation_ids])

        datacell.refresh_from_db()
        # The bogus id is silently filtered; real ids still link
        self.assertEqual(
            set(datacell.sources.values_list("id", flat=True)),
            set(annotation_ids),
        )

    def test_empty_input_is_a_noop(self) -> None:
        from asgiref.sync import async_to_sync

        from opencontractserver.tasks.data_extract_tasks import (
            _link_retrieval_citations,
        )

        datacell, _ = _build_datacell_with_annotations(self)

        async_to_sync(_link_retrieval_citations)(datacell, [])
        async_to_sync(_link_retrieval_citations)(datacell, [None, "abc", -1])

        datacell.refresh_from_db()
        self.assertEqual(datacell.sources.count(), 0)


# Failure-mode classification (`_classify_none_result` and the
# `NONE_RESULT_*` constants) is covered by
# ``test_data_extract_failure_classification.py``.


class ModelOverrideAllowlistTests(TestCase):
    """``BENCHMARK_ALLOWED_MODEL_OVERRIDES`` guard fires before any Datacell
    work runs, so a rejected override marks the cell as failed without
    touching the agent runtime.
    """

    def setUp(self) -> None:
        self.user = User.objects.create_user(
            username="allowlist_user", password="testpass"
        )
        corpus = Corpus.objects.create(title="Allowlist Corpus", creator=self.user)
        document = Document.objects.create(
            title="Allowlist Doc", creator=self.user, file_type="text/plain"
        )
        corpus.add_document(document=document, user=self.user)
        fieldset = Fieldset.objects.create(name="fs", creator=self.user)
        column = Column.objects.create(
            fieldset=fieldset,
            name="col",
            query="anything",
            output_type="str",
            creator=self.user,
        )
        extract = Extract.objects.create(
            corpus=corpus, fieldset=fieldset, name="ex", creator=self.user
        )
        self.cell = Datacell.objects.create(
            extract=extract,
            column=column,
            document=document,
            data_definition="x",
            creator=self.user,
        )

    def test_unknown_model_override_marks_cell_failed(self) -> None:
        from django.test import override_settings

        from opencontractserver.tasks.data_extract_tasks import (
            doc_extract_query_task,
        )

        with override_settings(
            BENCHMARK_ALLOWED_MODEL_OVERRIDES=["openai:gpt-4o-mini"]
        ):
            # The task re-raises after marking the cell failed; the
            # operator-facing celery worker logs the error and the cell
            # carries the explanation in its stacktrace for ops review.
            with self.assertRaises(ValueError):
                doc_extract_query_task.si(
                    self.cell.id, model_override="anthropic:not-allowed"
                ).apply().get()

        self.cell.refresh_from_db()
        self.assertIsNotNone(self.cell.failed)
        self.assertIn(
            "BENCHMARK_ALLOWED_MODEL_OVERRIDES",
            self.cell.stacktrace or "",
        )
