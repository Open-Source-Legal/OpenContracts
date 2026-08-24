"""A renamed authority section must version up, not fork into a second document.

Regression coverage for a silent-correctness bug found while rebuilding a real
authority pack (ITAR) whose section headings changed between installs.

``bootstrap_authority_corpus`` locates an existing document by canonical key,
but when the text differed it handed the write to
``create_or_update_text_document``, which derives the corpus path from the
TITLE. A changed heading therefore landed the new body at a NEW path and left
the previous document current. Both then carried the same
``custom_meta.canonical_key``, and ``find_authority_target`` orders by ``id``
and takes the first — so the SUPERSEDED document won every lookup and the key
silently resolved to stale text.

Nothing about this is visible from the install summary except the word
"created" where "updated" belonged, which is why it needs a test rather than a
reviewer's attention.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.enrichment.authorities import (
    AuthoritySection,
    bootstrap_authority_corpus,
    find_authority_target,
)

User = get_user_model()

KEY = "test-usml:viii"
CORPUS_TITLE = "Renamed Section Corpus"
CORPUS_SLUG = "renamed-section-corpus"


class AuthoritySectionRenameTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="rename-tester", password="test")

    def _install(self, heading: str, text: str) -> None:
        bootstrap_authority_corpus(
            creator_id=self.user.pk,
            corpus_title=CORPUS_TITLE,
            corpus_slug=CORPUS_SLUG,
            sections=[
                AuthoritySection(
                    key=KEY,
                    heading=heading,
                    text=text,
                    source_url="https://www.ecfr.gov/current/title-22",
                )
            ],
            relink=False,
        )

    def _live_documents(self) -> list[Document]:
        corpus = Corpus.objects.get(title=CORPUS_TITLE)
        ids = DocumentPath.objects.filter(
            corpus=corpus, is_current=True, is_deleted=False
        ).values_list("document_id", flat=True)
        return list(
            Document.objects.filter(
                id__in=ids, custom_meta__canonical_key=KEY
            ).order_by("id")
        )

    def test_renamed_section_versions_up_instead_of_forking(self) -> None:
        self._install(
            "USML Category VIII — Aircraft and Related Articles",
            "[STUB — replace with verbatim text]",
        )
        self._install(
            "USML Category VIII — Aircraft and Related Articles "
            "(22 C.F.R. § 121.1, Category VIII)",
            "(a) Aircraft, whether manned, unmanned, remotely piloted...",
        )

        live = self._live_documents()
        self.assertEqual(
            len(live),
            1,
            "a renamed section must leave exactly one live document for its key; "
            f"found {[(d.id, d.title) for d in live]}",
        )
        self.assertEqual(
            live[0].title,
            "USML Category VIII — Aircraft and Related "
            "Articles (22 C.F.R. § 121.1, Category VIII)",
        )

    def test_renamed_section_resolves_to_the_new_text(self) -> None:
        """The failure that actually bit: the key resolved to the stale body."""
        self._install("Heading One", "[STUB — replace with verbatim text]")
        self._install("Heading Two — now with a citation", "verbatim operative text")

        target = find_authority_target(KEY, self.user)
        assert target is not None  # narrows for mypy; the assertion is the point
        self.assertEqual(target.title, "Heading Two — now with a citation")

    def test_unchanged_heading_still_versions_up(self) -> None:
        """The pre-existing path must keep working."""
        self._install("Stable Heading", "first body")
        first = self._live_documents()
        self._install("Stable Heading", "second body")
        second = self._live_documents()

        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 1)
        self.assertNotEqual(
            first[0].id, second[0].id, "changed text should produce a new version"
        )
