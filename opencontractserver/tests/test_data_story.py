"""Tests for ``CorpusDataStoryService.build`` — the corpus-home data story.

The data story aggregates the action-owned ``Collection Profile`` extract's
completed datacells into per-document profile rows (type / counterparty /
effective date / value), normalising the LLM's noisy output (markdown stripped,
a date parsed out of prose, a numeric value coerced). Reads are corpus-as-gate:
the source corpus must be READ-visible, then every completed cell of that
corpus's action-owned profile extract is read.
"""

from __future__ import annotations

from typing import Any

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from opencontractserver.corpuses.models import (
    Corpus,
    CorpusAction,
    CorpusActionTrigger,
)
from opencontractserver.corpuses.services.data_story import (
    PROFILE_ACTION_NAME,
    PROFILE_COLUMN_DATE,
    PROFILE_COLUMN_PARTY,
    PROFILE_COLUMN_TYPE,
    PROFILE_COLUMN_VALUE,
    CorpusDataStoryService,
    get_or_create_default_profile_fieldset,
)
from opencontractserver.documents.models import Document
from opencontractserver.extracts.models import Column, Datacell, Extract

User = get_user_model()


class CorpusDataStoryServiceTests(TestCase):
    user: Any
    stranger: Any
    corpus: Corpus

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="story-owner", password="x")
        cls.stranger = User.objects.create_user(username="story-stranger", password="x")
        cls.corpus = Corpus.objects.create(title="Story Corpus", creator=cls.user)

    # ------------------------------------------------------------------
    def _profile_extract(self, corpus: Corpus):
        """Build the action-owned ``Collection Profile`` extract.

        ``corpus_action`` must be non-null — ``build`` pins to the action-owned
        accumulating extract so a hand-rolled extract reusing the same fieldset
        cannot shadow it.
        """
        fieldset, _ = get_or_create_default_profile_fieldset(self.user)
        action = CorpusAction.objects.create(
            corpus=corpus,
            fieldset=fieldset,
            trigger=CorpusActionTrigger.ADD_DOCUMENT.value,
            name=PROFILE_ACTION_NAME,
            creator=self.user,
        )
        extract = Extract.objects.create(
            name=f"Action {PROFILE_ACTION_NAME} for {corpus.title}",
            corpus=corpus,
            fieldset=fieldset,
            corpus_action=action,
            creator=self.user,
        )
        return fieldset, extract

    def _cell(self, extract, fieldset, document, column_name, value, *, completed=True):
        column = Column.objects.get(fieldset=fieldset, name=column_name)
        return Datacell.objects.create(
            extract=extract,
            column=column,
            document=document,
            data_definition="profile",
            data={"data": value},
            completed=timezone.now() if completed else None,
            creator=self.user,
        )

    # ------------------------------------------------------------------
    def test_build_aggregates_completed_profile_cells(self):
        fieldset, extract = self._profile_extract(self.corpus)
        doc = Document.objects.create(
            title="Acme MSA", creator=self.user, description=""
        )
        doc._skip_signals = True
        self._cell(
            extract, fieldset, doc, PROFILE_COLUMN_TYPE, "**Services Agreement**"
        )
        self._cell(extract, fieldset, doc, PROFILE_COLUMN_PARTY, "Acme Corp")
        self._cell(
            extract, fieldset, doc, PROFILE_COLUMN_DATE, "Effective as of 2021-03-15."
        )
        self._cell(extract, fieldset, doc, PROFILE_COLUMN_VALUE, "1,250,000.00")

        story = CorpusDataStoryService.build(self.user, self.corpus.pk)
        self.assertIsNotNone(story)
        assert story is not None
        self.assertEqual(story.total_documents, 1)
        self.assertEqual(len(story.profiles), 1)
        row = story.profiles[0]
        self.assertEqual(row.document_id, doc.id)
        self.assertEqual(row.title, "Acme MSA")
        # Normalisation: markdown stripped, date parsed out of prose, value coerced.
        self.assertEqual(row.type, "Services Agreement")
        self.assertEqual(row.party, "Acme Corp")
        self.assertEqual(row.effective_date, "2021-03-15")
        self.assertEqual(row.value, 1250000.0)

    def test_build_ignores_incomplete_cells(self):
        # A cell with ``completed=None`` is excluded (the build filters on
        # ``completed__isnull=False``), so a profile-less corpus stays empty.
        fieldset, extract = self._profile_extract(self.corpus)
        doc = Document.objects.create(
            title="Pending", creator=self.user, description=""
        )
        doc._skip_signals = True
        self._cell(
            extract, fieldset, doc, PROFILE_COLUMN_TYPE, "Agreement", completed=False
        )
        story = CorpusDataStoryService.build(self.user, self.corpus.pk)
        assert story is not None
        self.assertEqual(story.total_documents, 0)
        self.assertEqual(story.profiles, [])

    def test_build_empty_when_no_profile_extract(self):
        # Corpus readable but with no action-owned Collection Profile extract.
        story = CorpusDataStoryService.build(self.user, self.corpus.pk)
        self.assertIsNotNone(story)
        assert story is not None
        self.assertEqual(story.total_documents, 0)
        self.assertEqual(story.profiles, [])

    def test_build_returns_none_for_unreadable_corpus(self):
        # stranger cannot read the owner's private corpus -> None (the resolver
        # maps that to a null field and the embed self-hides).
        self.assertIsNone(CorpusDataStoryService.build(self.stranger, self.corpus.pk))
