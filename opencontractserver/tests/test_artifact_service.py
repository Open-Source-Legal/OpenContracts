"""Tests for ``ArtifactService`` create-path authorization.

The security invariant under test: minting an :class:`~opencontractserver.
corpuses.models.Artifact` (a shareable corpus "poster") requires an
**authenticated** creator. Anonymous users may view a public corpus's posters
but must never write new rows — there are no anonymous DB writes, and the
``Artifact.creator`` FK is non-null as a DB-level backstop. Creation is also
corpus-as-gate (the source corpus must be READ-visible) and template-validated.
"""

from __future__ import annotations

from django.contrib.auth.models import AnonymousUser
from django.test import TestCase

from opencontractserver.corpuses.models import Artifact, Corpus
from opencontractserver.corpuses.services.artifact_service import ArtifactService
from opencontractserver.users.models import User

_TEMPLATE = "spending-beeswarm"  # a valid id in ARTIFACT_TEMPLATES


def _make_corpus(creator: User, *, title: str, is_public: bool = False) -> Corpus:
    """Create a corpus without firing the branding/Celery post_save signals."""
    corpus = Corpus(title=title, creator=creator, is_public=is_public)
    corpus._skip_signals = True
    corpus.save()
    return corpus


class ArtifactServiceCreateAuthTests(TestCase):
    owner: User
    other: User
    corpus: Corpus

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="artifact-owner", password="x")
        cls.other = User.objects.create_user(username="artifact-other", password="x")
        # A private corpus the owner can read but ``other`` cannot.
        cls.corpus = _make_corpus(cls.owner, title="Owner Collection")

    def test_authenticated_creator_can_mint_on_readable_corpus(self):
        artifact = ArtifactService.create(self.owner, self.corpus.id, _TEMPLATE)
        self.assertIsNotNone(artifact)
        assert artifact is not None  # narrow Artifact | None for the type checker
        self.assertEqual(artifact.creator_id, self.owner.id)
        self.assertEqual(artifact.corpus_id, self.corpus.id)
        self.assertEqual(artifact.template, _TEMPLATE)

    def test_anonymous_user_cannot_mint_and_writes_no_row(self):
        before = Artifact.objects.count()
        artifact = ArtifactService.create(AnonymousUser(), self.corpus.id, _TEMPLATE)
        self.assertIsNone(artifact)
        # Defense in depth: nothing was written to the DB.
        self.assertEqual(Artifact.objects.count(), before)

    def test_anonymous_user_cannot_mint_even_on_public_corpus(self):
        public = _make_corpus(self.owner, title="Public Collection", is_public=True)
        before = Artifact.objects.count()
        artifact = ArtifactService.create(AnonymousUser(), public.id, _TEMPLATE)
        self.assertIsNone(artifact)
        self.assertEqual(Artifact.objects.count(), before)

    def test_authenticated_user_cannot_mint_on_unreadable_corpus(self):
        # ``other`` cannot read ``owner``'s private corpus -> corpus-as-gate denies.
        before = Artifact.objects.count()
        artifact = ArtifactService.create(self.other, self.corpus.id, _TEMPLATE)
        self.assertIsNone(artifact)
        self.assertEqual(Artifact.objects.count(), before)

    def test_unknown_template_is_rejected(self):
        before = Artifact.objects.count()
        artifact = ArtifactService.create(
            self.owner, self.corpus.id, "no-such-template"
        )
        self.assertIsNone(artifact)
        self.assertEqual(Artifact.objects.count(), before)
