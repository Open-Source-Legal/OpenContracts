"""Targeted regression tests for the three latent bugs uncovered while
graduating ``opencontractserver.utils.{packaging,sharing}`` from the
mypy baseline (issue #1481, umbrella #1447):

1. ``unpack_label_set_from_export`` previously had an inverted
   ``isinstance(user, str)`` check on a parameter typed
   ``int | UserModel``. The ``int`` branch was unreachable, so any
   call passing an integer user id silently fell through to the
   ``creator=user`` model-instance path and crashed at the database
   layer with a ``ValueError``. This test pins the corrected branch.

2. ``unpack_corpus_from_export`` had the same inverted check.

3. ``make_analysis_public`` raised an uncaught ``AttributeError`` when
   invoked on an Analysis whose ``analyzed_corpus`` was ``None``
   (allowed by the model — the FK is ``SET_NULL`` + ``null=True``).
   The graduated code returns a graceful error response.
"""

from __future__ import annotations

import base64

from django.contrib.auth import get_user_model
from django.test import TestCase

from opencontractserver.analyzer.models import Analysis, Analyzer
from opencontractserver.types.dicts import (
    OpenContractCorpusType,
    OpenContractsLabelSetType,
)
from opencontractserver.users.models import User
from opencontractserver.utils.packaging import (
    unpack_corpus_from_export,
    unpack_label_set_from_export,
)
from opencontractserver.utils.sharing import make_analysis_public

# get_user_model() resolves to type[AbstractBaseUser] which mypy cannot
# use as a type, so import the concrete model directly.
get_user_model()  # touch to keep the runtime import surface stable


# 1x1 transparent PNG, base64-encoded — the smallest legal payload that
# survives the icon decode pipeline in unpack_*_from_export.
_TINY_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8A"
    "AAAASUVORK5CYII="
)


def _icon_payload() -> str:
    """Return a base64 string the unpacker will accept."""
    base64.b64decode(_TINY_PNG_B64)  # sanity: ensures the constant is decodable
    return _TINY_PNG_B64


class UnpackFromExportIntUserIdTests(TestCase):
    """The ``user`` parameter is typed ``int | UserModel``; both branches
    must work. Pre-#1531 the ``int`` branch was unreachable due to an
    inverted isinstance check."""

    user: User

    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = User.objects.create_user(username="int-id-user", password="x")

    def test_unpack_label_set_accepts_integer_user_id(self) -> None:
        """Passing an int user id must build a LabelSet whose creator is
        the matching User row (NOT crash inside ``creator=<int>``)."""
        label_set_data: OpenContractsLabelSetType = {
            "id": "ignored",
            "title": "IntUid LabelSet",
            "description": "via integer user id",
            "icon_data": _icon_payload(),
            "icon_name": "icon.png",
            "creator": "int-id-user",
        }

        result = unpack_label_set_from_export(label_set_data, self.user.id)

        assert result is not None, "LabelSet was not created — int branch must succeed."
        self.assertEqual(result.creator_id, self.user.id)
        self.assertEqual(result.title, "IntUid LabelSet")

    def test_unpack_corpus_accepts_integer_user_id(self) -> None:
        """Same contract for ``unpack_corpus_from_export``: an int user id
        must resolve to the right creator."""
        # Build a label_set first via the same int-id path so this test
        # exercises both functions end-to-end.
        label_set = unpack_label_set_from_export(
            {
                "id": "ignored",
                "title": "Pair LabelSet",
                "description": "",
                "icon_data": _icon_payload(),
                "icon_name": "icon.png",
                "creator": "int-id-user",
            },
            self.user.id,
        )
        assert label_set is not None  # narrow for mypy + sanity

        corpus_data: OpenContractCorpusType = {
            "id": 0,  # ignored on import
            "title": "IntUid Corpus",
            "description": "via integer user id",
            "icon_data": _icon_payload(),
            "icon_name": "icon.png",
            "creator": "int-id-user",
            "label_set": str(label_set.id),
        }

        result = unpack_corpus_from_export(
            data=corpus_data,
            user=self.user.id,
            label_set_id=label_set.id,
            corpus_id=None,
        )

        assert result is not None, "Corpus was not created — int branch must succeed."
        self.assertEqual(result.creator_id, self.user.id)
        self.assertEqual(result.title, "IntUid Corpus")
        self.assertEqual(result.label_set_id, label_set.id)


class MakeAnalysisPublicMissingCorpusTests(TestCase):
    """``Analysis.analyzed_corpus`` is ``SET_NULL`` + ``null=True``, so
    calling ``make_analysis_public`` on an analysis whose corpus has been
    deleted (or never set) must NOT crash. PR #1531 added a graceful
    early-return; this test pins that contract."""

    user: User
    analyzer: Analyzer
    analysis: Analysis

    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = User.objects.create_user(username="orphan-analysis", password="x")
        cls.analyzer = Analyzer.objects.create(
            id="test_orphan_analyzer",
            description="orphan analyzer",
            creator=cls.user,
            manifest={},
            # Constraint requires exactly one of host_gremlin / task_name
            # to be set; pick task_name to keep this test self-contained.
            task_name="opencontractserver.tests.test_packaging_typing_bug_fixes.noop",
        )
        cls.analysis = Analysis.objects.create(
            analyzer=cls.analyzer,
            analyzed_corpus=None,  # the condition under test
            creator=cls.user,
        )

    def test_returns_error_when_analyzed_corpus_is_none(self) -> None:
        # Capture pre-call state so we can confirm the early-return path
        # leaves the analysis untouched (no ``is_public`` flip, no
        # ``backend_lock`` toggle). The previous version of this guard ran
        # AFTER ``analysis.save()`` so ``is_public`` ended up True even on
        # the failure path — a silent state inconsistency.
        was_public_before = self.analysis.is_public
        was_locked_before = self.analysis.backend_lock

        result = make_analysis_public(self.analysis.id)

        self.assertFalse(result["ok"])
        self.assertIn("analyzed_corpus", result["message"])

        self.analysis.refresh_from_db()
        self.assertEqual(self.analysis.is_public, was_public_before)
        self.assertEqual(self.analysis.backend_lock, was_locked_before)
