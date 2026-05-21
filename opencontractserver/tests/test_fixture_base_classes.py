"""Regression tests for the fixture-backed base test classes (issue #1711).

Pins the Phase 3 split of ``BaseFixtureTestCase``:

* ``BaseFixtureTestCase`` is ``TestCase``-backed — the ``test_data.json``
  fixture and the derived corpus/document state are built **once per class**
  (in ``setUpTestData``), not reloaded before every test method.
* ``TransactionFixtureTestCase`` keeps ``TransactionTestCase`` semantics for
  async / websocket / Celery-eager tests that need committed data.
"""

from django.test import TestCase, TransactionTestCase

from opencontractserver.annotations.models import StructuralAnnotationSet
from opencontractserver.tests.base import (
    BaseFixtureTestCase,
    TransactionFixtureTestCase,
    WebsocketFixtureBaseTestCase,
)


class FixtureBaseClassWiringTests(TestCase):
    """The fixture base classes are wired to the intended Django test bases."""

    def test_base_fixture_test_case_is_testcase_backed(self):
        # TestCase wraps each test in a savepoint and loads fixtures once per
        # class — the whole point of the #1711 split.
        self.assertTrue(issubclass(BaseFixtureTestCase, TestCase))

    def test_transaction_fixture_test_case_is_transaction_backed(self):
        self.assertTrue(issubclass(TransactionFixtureTestCase, TransactionTestCase))
        # TestCase is itself a TransactionTestCase subclass; assert the
        # transaction variant is NOT the rollback-per-test TestCase.
        self.assertFalse(issubclass(TransactionFixtureTestCase, TestCase))

    def test_websocket_base_uses_the_transaction_variant(self):
        self.assertTrue(
            issubclass(WebsocketFixtureBaseTestCase, TransactionFixtureTestCase)
        )


class BaseFixtureLoadsOncePerClassTests(BaseFixtureTestCase):
    """``setUpTestData`` (fixture + corpus build) runs once per class.

    Under the pre-#1711 ``TransactionTestCase`` base the 18 MB fixture reloaded
    before every test method; this counter would then climb past 1.
    """

    _build_count = 0

    @classmethod
    def setUpTestData(cls):
        BaseFixtureLoadsOncePerClassTests._build_count += 1
        super().setUpTestData()

    def test_setup_test_data_ran_once_a(self):
        self.assertEqual(BaseFixtureLoadsOncePerClassTests._build_count, 1)

    def test_setup_test_data_ran_once_b(self):
        # A second test method in the same class — if the fixture/corpus build
        # reloaded per test the counter would now be 2.
        self.assertEqual(BaseFixtureLoadsOncePerClassTests._build_count, 1)

    def test_fixture_state_is_available(self):
        self.assertEqual(self.user.username, "testuser")
        self.assertEqual(len(self.docs), 4)
        self.assertIsNotNone(self.corpus.pk)
        # doc / doc2 / doc3 stay identity-consistent with docs[...].
        self.assertIs(self.doc, self.docs[0])
        self.assertIs(self.doc2, self.docs[1])
        self.assertIs(self.doc3, self.docs[2])
        # The regenerated fixture is already in the StructuralAnnotationSet
        # schema — every corpus document references one, with no per-test
        # migration loop needed.
        self.assertTrue(StructuralAnnotationSet.objects.exists())
        for doc in self.docs:
            self.assertIsNotNone(doc.structural_annotation_set_id)
