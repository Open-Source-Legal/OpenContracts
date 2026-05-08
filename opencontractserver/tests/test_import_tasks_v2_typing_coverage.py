"""
Coverage tests for typing-graduated paths in ``import_tasks_v2._setup_corpus_and_labels``.

PR #1482 added explicit ``RuntimeError`` raises when ``unpack_label_set_from_export``
or ``unpack_corpus_from_export`` return ``None`` (previously the code silently
called ``.id`` on ``None`` and crashed deeper with a less informative
``AttributeError``).
"""

from __future__ import annotations

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from opencontractserver.tasks.import_tasks_v2 import _setup_corpus_and_labels

User = get_user_model()


_MINIMAL_EXPORT_DATA: dict = {
    "label_set": {
        "id": "old-id",
        "title": "T",
        "description": "",
        "icon_name": "",
        "icon_data": "",
        "creator_email": "",
        "annotation_labels": [],
    },
    "corpus": {
        "id": "old-corpus",
        "title": "C",
        "description": "",
        "icon_name": "",
        "icon_data": "",
        "creator_email": "",
        "label_set": "ls",
    },
    "doc_labels": {},
    "text_labels": {},
    "annotated_docs": {},
}


class SetupCorpusAndLabelsGuardsTestCase(TestCase):
    """``_setup_corpus_and_labels`` must reject ``None`` from unpackers."""

    def setUp(self):
        self.user = User.objects.create_user(username="setup_user", password="pw")

    @mock.patch(
        "opencontractserver.tasks.import_tasks_v2.unpack_label_set_from_export",
        return_value=None,
    )
    def test_raises_when_label_set_unpack_returns_none(self, _mock_unpack):
        """A ``None`` result from ``unpack_label_set_from_export`` -> RuntimeError."""
        with self.assertRaises(RuntimeError) as cm:
            # ``data_json`` accepts the V1 OR V2 export TypedDict; the test
            # fixture is a structurally-compatible dict — cast for mypy.
            _setup_corpus_and_labels(
                data_json=_MINIMAL_EXPORT_DATA,  # type: ignore[arg-type]
                user_obj=self.user,
                seed_corpus_id=None,
            )
        self.assertIn("label set", str(cm.exception).lower())

    @mock.patch(
        "opencontractserver.tasks.import_tasks_v2.unpack_corpus_from_export",
        return_value=None,
    )
    @mock.patch(
        "opencontractserver.tasks.import_tasks_v2.unpack_label_set_from_export",
    )
    def test_raises_when_corpus_unpack_returns_none(
        self, mock_label_unpack, _mock_corpus_unpack
    ):
        """A ``None`` result from ``unpack_corpus_from_export`` -> RuntimeError."""
        # Stub label-set unpack with a non-null sentinel so we reach the
        # corpus unpack call.
        fake_labelset = mock.MagicMock(id=42)
        mock_label_unpack.return_value = fake_labelset

        with self.assertRaises(RuntimeError) as cm:
            _setup_corpus_and_labels(
                data_json=_MINIMAL_EXPORT_DATA,  # type: ignore[arg-type]
                user_obj=self.user,
                seed_corpus_id=None,
            )
        self.assertIn("corpus", str(cm.exception).lower())
