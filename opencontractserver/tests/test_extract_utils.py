"""Tests for ``opencontractserver.utils.extract.create_and_setup_extract``.

Mirrors ``test_analysis_utils`` and pins the same framework contract:
every Extract created through the canonical chokepoint must have
guardian CRUD for its creator. Implementers (start_extract agent tool,
GraphQL mutations, CorpusAction pipeline) rely on this invariant.
"""

import logging

from django.contrib.auth import get_user_model
from django.test import TestCase

from opencontractserver.corpuses.models import Corpus, CorpusAction
from opencontractserver.documents.models import Document
from opencontractserver.extracts.models import Column, Extract, Fieldset
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.extract import create_and_setup_extract
from opencontractserver.utils.permissioning import user_has_permission_for_obj

logger = logging.getLogger(__name__)

User = get_user_model()


class CreateAndSetupExtractTestCase(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="extract_user", password="pw")
        self.corpus = Corpus.objects.create(title="Test Corpus", creator=self.user)
        self.fieldset = Fieldset.objects.create(
            name="Test Fieldset",
            description="Test",
            creator=self.user,
        )
        Column.objects.create(
            fieldset=self.fieldset,
            name="col1",
            query="What is foo?",
            output_type="str",
            creator=self.user,
        )
        self.docs = [
            Document.objects.create(title=f"Doc {i}", description="", creator=self.user)
            for i in range(3)
        ]

    def test_creates_extract_with_minimal_args(self):
        extract = create_and_setup_extract(
            self.user.id,
            corpus=self.corpus,
            fieldset=self.fieldset,
        )
        self.assertIsInstance(extract, Extract)
        self.assertEqual(extract.corpus, self.corpus)
        self.assertEqual(extract.fieldset, self.fieldset)
        self.assertEqual(extract.creator_id, self.user.id)
        self.assertIsNone(extract.started)
        self.assertIsNone(extract.finished)
        self.assertIsNone(extract.corpus_action)
        self.assertEqual(extract.documents.count(), 0)

    def test_grants_creator_crud(self):
        """Pins the framework contract — every CRUD permission flows from
        the helper, so no implementer ever has to remember to grant it."""
        extract = create_and_setup_extract(
            self.user.id,
            corpus=self.corpus,
            fieldset=self.fieldset,
        )
        for permission in (
            PermissionTypes.READ,
            PermissionTypes.UPDATE,
            PermissionTypes.DELETE,
        ):
            self.assertTrue(
                user_has_permission_for_obj(
                    self.user,
                    extract,
                    permission,
                    include_group_permissions=True,
                ),
                f"creator should have {permission.name} on Extract "
                f"created via the framework helper",
            )

    def test_links_documents_when_provided(self):
        doc_ids = [d.id for d in self.docs]
        extract = create_and_setup_extract(
            self.user.id,
            corpus=self.corpus,
            fieldset=self.fieldset,
            document_ids=doc_ids,
        )
        self.assertCountEqual(
            list(extract.documents.values_list("id", flat=True)), doc_ids
        )

    def test_marks_started_when_requested(self):
        extract = create_and_setup_extract(
            self.user.id,
            corpus=self.corpus,
            fieldset=self.fieldset,
            mark_started=True,
        )
        self.assertIsNotNone(extract.started)
        self.assertIsNone(extract.finished)

    def test_attaches_corpus_action_lineage(self):
        action = CorpusAction.objects.create(
            name="Test Action",
            corpus=self.corpus,
            fieldset=self.fieldset,
            trigger="add_document",
            creator=self.user,
        )
        extract = create_and_setup_extract(
            self.user.id,
            corpus=self.corpus,
            fieldset=self.fieldset,
            corpus_action=action,
        )
        self.assertEqual(extract.corpus_action_id, action.id)

    def test_default_name_falls_back_when_not_supplied(self):
        extract = create_and_setup_extract(
            self.user.id,
            corpus=self.corpus,
            fieldset=self.fieldset,
        )
        self.assertIn(self.fieldset.name, extract.name)
        self.assertIn(self.corpus.title, extract.name)

    def test_custom_name_is_preserved(self):
        extract = create_and_setup_extract(
            self.user.id,
            corpus=self.corpus,
            fieldset=self.fieldset,
            name="Custom Extract Name",
        )
        self.assertEqual(extract.name, "Custom Extract Name")
