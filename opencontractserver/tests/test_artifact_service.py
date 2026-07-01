"""Tests for ``ArtifactService`` create-path authorization.

The security invariant under test: minting an :class:`~opencontractserver.
corpuses.models.Artifact` (a shareable corpus "poster") requires an
**authenticated** creator. Anonymous users may view a public corpus's posters
but must never write new rows — there are no anonymous DB writes, and the
``Artifact.creator`` FK is non-null as a DB-level backstop. Creation is also
corpus-as-gate (the source corpus must be READ-visible) and template-validated.
"""

from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.db import IntegrityError
from django.test import TestCase, TransactionTestCase

from opencontractserver.constants.artifacts import _MIN_DATED
from opencontractserver.corpuses.models import Artifact, Corpus
from opencontractserver.corpuses.services.artifact_service import ArtifactService
from opencontractserver.corpuses.services.data_story import DataStory, ProfileRow
from opencontractserver.users.models import User

_TEMPLATE = "spending-beeswarm"  # the only id currently in ARTIFACT_TEMPLATES
# "reference-web" is intentionally NOT registered yet (no frontend renderer), so
# the service treats it as an unknown/rejected template and never offers it.
_DEFERRED_TEMPLATE = "reference-web"


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
        # An outright-unknown id and the deferred ``reference-web`` (no renderer
        # yet, so not in the registry) are both rejected before any DB write.
        before = Artifact.objects.count()
        for bad in ("no-such-template", _DEFERRED_TEMPLATE):
            artifact = ArtifactService.create(self.owner, self.corpus.id, bad)
            self.assertIsNone(artifact)
        self.assertEqual(Artifact.objects.count(), before)


class ArtifactServiceReadAndEditTests(TestCase):
    """Reads (corpus-as-gate), template eligibility, caption + image edits."""

    owner: User
    stranger: User
    private_corpus: Corpus
    public_corpus: Corpus
    artifact: Artifact

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="read-owner", password="x")
        cls.stranger = User.objects.create_user(username="read-stranger", password="x")
        cls.private_corpus = _make_corpus(cls.owner, title="Private Read Corpus")
        cls.public_corpus = _make_corpus(
            cls.owner, title="Public Read Corpus", is_public=True
        )
        artifact = ArtifactService.create(cls.owner, cls.private_corpus.id, _TEMPLATE)
        assert artifact is not None
        cls.artifact = artifact

    # -- get_by_slug ---------------------------------------------------------
    def test_get_by_slug_returns_artifact_for_readable_corpus(self):
        found = ArtifactService.get_by_slug(self.owner, self.artifact.slug)
        self.assertIsNotNone(found)
        assert found is not None
        self.assertEqual(found.id, self.artifact.id)

    def test_get_by_slug_returns_none_for_missing_slug(self):
        self.assertIsNone(ArtifactService.get_by_slug(self.owner, "does-not-exist"))

    def test_get_by_slug_hidden_when_corpus_not_readable(self):
        # stranger cannot read owner's private corpus -> artifact hidden.
        self.assertIsNone(
            ArtifactService.get_by_slug(self.stranger, self.artifact.slug)
        )

    def test_get_by_slug_public_corpus_artifact_is_anonymous_visible(self):
        public_art = ArtifactService.create(
            self.owner, self.public_corpus.id, _TEMPLATE
        )
        assert public_art is not None
        found = ArtifactService.get_by_slug(AnonymousUser(), public_art.slug)
        self.assertIsNotNone(found)
        assert found is not None
        self.assertEqual(found.id, public_art.id)

    # -- list_for_corpus -----------------------------------------------------
    def test_list_for_corpus_returns_artifacts_for_owner(self):
        listed = ArtifactService.list_for_corpus(self.owner, self.private_corpus.id)
        self.assertEqual([a.id for a in listed], [self.artifact.id])

    def test_list_for_corpus_empty_for_unreadable_corpus(self):
        self.assertEqual(
            ArtifactService.list_for_corpus(self.stranger, self.private_corpus.id), []
        )

    # -- templates_for_corpus (data-gated eligibility) -----------------------
    def test_templates_not_eligible_for_empty_corpus(self):
        # No profile extract -> 0 dated -> below threshold -> not eligible. Only
        # the dated-signal template is offered; reference-web is deferred.
        infos = ArtifactService.templates_for_corpus(self.owner, self.private_corpus.id)
        by_id = {t.id: t for t in infos}
        self.assertFalse(by_id[_TEMPLATE].eligible)
        self.assertIn("needs dated documents", by_id[_TEMPLATE].reason)
        self.assertNotIn(_DEFERRED_TEMPLATE, by_id)

    def test_templates_eligible_when_thresholds_met(self):
        story = DataStory(
            total_documents=_MIN_DATED,
            profiles=[
                ProfileRow(
                    document_id=i,
                    title=f"D{i}",
                    slug=None,
                    type=None,
                    party=None,
                    effective_date=f"2021-01-{i:02d}",
                    value=None,
                )
                for i in range(1, _MIN_DATED + 1)
            ],
        )
        with patch(
            "opencontractserver.corpuses.services.data_story."
            "CorpusDataStoryService.build",
            return_value=story,
        ):
            infos = ArtifactService.templates_for_corpus(
                self.owner, self.private_corpus.id
            )
        by_id = {t.id: t for t in infos}
        self.assertTrue(by_id[_TEMPLATE].eligible)
        self.assertIn(f"{_MIN_DATED} dated documents", by_id[_TEMPLATE].reason)

    def test_templates_empty_for_unreadable_corpus(self):
        self.assertEqual(
            ArtifactService.templates_for_corpus(self.stranger, self.private_corpus.id),
            [],
        )

    # -- update_captions -----------------------------------------------------
    def test_update_captions_by_creator(self):
        art = ArtifactService.create(self.owner, self.private_corpus.id, _TEMPLATE)
        assert art is not None
        updated = ArtifactService.update_captions(
            self.owner,
            art.slug,
            title="New Title",
            subtitle="Sub",
            byline="By",
            config={"k": "v"},
        )
        self.assertIsNotNone(updated)
        assert updated is not None
        self.assertEqual(updated.title, "New Title")
        self.assertEqual(updated.subtitle, "Sub")
        self.assertEqual(updated.byline, "By")
        self.assertEqual(updated.config, {"k": "v"})

    def test_update_captions_rejected_for_non_creator(self):
        art = ArtifactService.create(self.owner, self.private_corpus.id, _TEMPLATE)
        assert art is not None
        result = ArtifactService.update_captions(
            self.stranger, art.slug, title="Hijack"
        )
        self.assertIsNone(result)
        art.refresh_from_db()
        self.assertNotEqual(art.title, "Hijack")

    def test_update_captions_allowed_for_superuser(self):
        # ``_can_edit`` grants superusers an admin override on artifacts they did
        # not create. Uses the public corpus because the corpus-as-gate READ runs
        # first and ``Corpus.visible_to_user`` does not blanket-expose private
        # corpora to superusers — so the override only applies to artifacts on
        # corpora the admin can already read.
        admin = User.objects.create_user(
            username="artifact-admin", password="x", is_superuser=True
        )
        art = ArtifactService.create(self.owner, self.public_corpus.id, _TEMPLATE)
        assert art is not None
        updated = ArtifactService.update_captions(admin, art.slug, title="Admin Edit")
        self.assertIsNotNone(updated)
        assert updated is not None
        self.assertEqual(updated.title, "Admin Edit")

    def test_update_captions_missing_slug_returns_none(self):
        self.assertIsNone(
            ArtifactService.update_captions(self.owner, "nope", title="x")
        )

    # -- set_image -----------------------------------------------------------
    def test_set_image_by_creator_persists_png(self):
        art = ArtifactService.create(self.owner, self.private_corpus.id, _TEMPLATE)
        assert art is not None
        result = ArtifactService.set_image(self.owner, art.slug, b"\x89PNG\r\n\x1a\n")
        self.assertIsNotNone(result)
        assert result is not None
        image_name = result.image.name
        self.assertIsNotNone(image_name)
        assert image_name is not None
        self.assertTrue(image_name.endswith(".png"))

    def test_set_image_rejects_non_png_bytes(self):
        # Format validation lives in the service (single home for image
        # handling), not just the GraphQL mutation, so any future caller is
        # protected too. Raised as ValueError — distinct from the None used
        # for not-found/no-permission, which must stay an opaque oracle.
        art = ArtifactService.create(self.owner, self.private_corpus.id, _TEMPLATE)
        assert art is not None
        with self.assertRaises(ValueError):
            ArtifactService.set_image(self.owner, art.slug, b"not a png")

    def test_set_image_rejected_for_non_creator(self):
        art = ArtifactService.create(self.owner, self.private_corpus.id, _TEMPLATE)
        assert art is not None
        result = ArtifactService.set_image(self.stranger, art.slug, b"\x89PNG")
        self.assertIsNone(result)

    def test_set_image_missing_slug_returns_none(self):
        self.assertIsNone(ArtifactService.set_image(self.owner, "nope", b"\x89PNG"))


class ArtifactSaveSlugRetryTests(TransactionTestCase):
    """``Artifact.save`` re-rolls an auto-generated slug on a unique collision.

    ``TransactionTestCase`` runs outside an outer atomic block, so the real
    ``IntegrityError`` raised by the duplicate-slug INSERT does not poison the
    follow-up ``.exists()`` query the retry loop runs (autocommit rolls back
    only the failed statement). A ``TestCase`` would leave the connection in an
    aborted-transaction state and the retry's query would raise instead.
    """

    def setUp(self):
        self.owner = User.objects.create_user(username="slug-retry-owner", password="x")
        self.corpus = _make_corpus(self.owner, title="Slug Retry Corpus")

    def test_save_rerolls_auto_slug_on_collision(self):
        first = Artifact.objects.create(
            corpus=self.corpus, template=_TEMPLATE, creator=self.owner
        )
        # Force the first roll to collide with the existing slug, then succeed
        # on the re-roll — the exact TOCTOU race the retry guards against.
        with patch(
            "opencontractserver.corpuses.models.generate_unique_slug",
            side_effect=[first.slug, "rerolled-artifact-slug"],
        ):
            second = Artifact(
                corpus=self.corpus, template=_TEMPLATE, creator=self.owner
            )
            second.save()
        self.assertEqual(second.slug, "rerolled-artifact-slug")
        self.assertEqual(Artifact.objects.filter(corpus=self.corpus).count(), 2)

    def test_save_reraises_non_slug_integrity_error(self):
        # ``corpus`` is NOT NULL: saving without one trips a different
        # constraint while the freshly-generated slug is unique, so the retry
        # must re-raise rather than loop.
        orphan = Artifact(template=_TEMPLATE, creator=self.owner)
        with self.assertRaises(IntegrityError):
            orphan.save()

    def test_caller_supplied_slug_is_sanitized_not_retried(self):
        from opencontractserver.shared.slug_utils import sanitize_slug

        art = Artifact(
            corpus=self.corpus,
            template=_TEMPLATE,
            creator=self.owner,
            slug="My Custom Slug!",
        )
        art.save()
        self.assertEqual(art.slug, sanitize_slug("My Custom Slug!", max_length=128))
