"""Tests for ``CorpusService`` — Corpus-row CRUD service (issue #1716, Phase 2B).

``CorpusService`` owns the write surface of the ``Corpus`` row: deletion,
visibility changes, markdown-description versioning, the create-time
creator-permission grant, and the update-time embedder guard. These tests
exercise each method directly (the GraphQL mutation contract is covered by the
existing corpus-mutation tests).
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from opencontractserver.corpuses.models import Corpus
from opencontractserver.corpuses.services import CorpusService
from opencontractserver.types.enums import PermissionTypes

User = get_user_model()


class TestCorpusServiceUpdateDescription(TestCase):
    """``CorpusService.update_description`` — creator-only, versioned."""

    def setUp(self):
        self.creator = User.objects.create_user(
            username="cs_desc_creator", email="cs_desc_creator@test.com"
        )
        self.other = User.objects.create_user(
            username="cs_desc_other", email="cs_desc_other@test.com"
        )
        self.corpus = Corpus.objects.create(
            title="Desc Corpus", creator=self.creator, is_public=False
        )

    def test_creator_updates_description_creates_revision(self):
        result = CorpusService.update_description(
            self.creator, self.corpus, "# New description"
        )
        self.assertTrue(result.ok)
        assert result.value is not None
        self.assertEqual(result.value.version, 1)

    def test_unchanged_content_returns_success_with_no_revision(self):
        # Identical to the (empty) current description — no revision created.
        result = CorpusService.update_description(self.creator, self.corpus, "")
        self.assertTrue(result.ok)
        self.assertIsNone(result.value)

    def test_non_creator_is_denied(self):
        result = CorpusService.update_description(self.other, self.corpus, "# Hijack")
        self.assertFalse(result.ok)
        self.assertIn("permission", result.error.lower())


class TestCorpusServiceDeleteCorpus(TestCase):
    """``CorpusService.delete_corpus`` — personal / lock / permission gates.

    Corpora here are created via ``Corpus.objects.create()`` rather than
    ``CreateCorpusMutation``, so no guardian object permissions are granted.
    The creator still clears ``require_permission(..., DELETE)`` via the
    creator short-circuit in ``_default_user_can`` (``creator_id == user.id``
    → True); the ``test_non_owner_without_permission_is_denied`` case proves
    a *non*-creator without an explicit grant is correctly denied, so the
    creator paths are not passing vacuously.
    """

    def setUp(self):
        self.creator = User.objects.create_user(
            username="cs_del_creator", email="cs_del_creator@test.com"
        )
        self.other = User.objects.create_user(
            username="cs_del_other", email="cs_del_other@test.com"
        )

    def _make_corpus(self, **kwargs):
        defaults = {
            "title": "Del Corpus",
            "creator": self.creator,
            "is_public": False,
        }
        defaults.update(kwargs)
        return Corpus.objects.create(**defaults)

    def test_creator_can_delete(self):
        corpus = self._make_corpus()
        pk = corpus.pk
        result = CorpusService.delete_corpus(self.creator, corpus)
        self.assertTrue(result.ok)
        self.assertFalse(Corpus.objects.filter(pk=pk).exists())

    def test_personal_corpus_cannot_be_deleted(self):
        # Every user gets exactly one personal corpus auto-created on signup
        # (the ``one_personal_corpus_per_user`` constraint forbids a second).
        corpus = Corpus.objects.get(creator=self.creator, is_personal=True)
        result = CorpusService.delete_corpus(self.creator, corpus)
        self.assertFalse(result.ok)
        self.assertIn("personal", result.error.lower())
        self.assertTrue(Corpus.objects.filter(pk=corpus.pk).exists())

    def test_corpus_locked_by_another_user_cannot_be_deleted(self):
        corpus = self._make_corpus(user_lock=self.other)
        result = CorpusService.delete_corpus(self.creator, corpus)
        self.assertFalse(result.ok)
        self.assertIn("locked", result.error.lower())
        self.assertTrue(Corpus.objects.filter(pk=corpus.pk).exists())

    def test_non_owner_without_permission_is_denied(self):
        corpus = self._make_corpus()
        result = CorpusService.delete_corpus(self.other, corpus)
        self.assertFalse(result.ok)
        self.assertTrue(Corpus.objects.filter(pk=corpus.pk).exists())


class TestCorpusServiceSetVisibility(TestCase):
    """``CorpusService.set_visibility`` — PERMISSION-gated visibility change.

    As in ``TestCorpusServiceDeleteCorpus``, the corpus is created directly
    (no guardian grants). The creator clears ``require_permission(...,
    PERMISSION)`` via the creator short-circuit in ``_default_user_can``;
    ``test_user_without_permission_is_denied`` proves a non-creator without
    an explicit grant is denied, so the creator paths are not vacuous.
    """

    def setUp(self):
        self.creator = User.objects.create_user(
            username="cs_vis_creator", email="cs_vis_creator@test.com"
        )
        self.other = User.objects.create_user(
            username="cs_vis_other", email="cs_vis_other@test.com"
        )
        self.corpus = Corpus.objects.create(
            title="Vis Corpus", creator=self.creator, is_public=False
        )

    def test_make_public_dispatches_cascade_task(self):
        with patch(
            "opencontractserver.tasks.permissioning_tasks.make_corpus_public_task"
        ) as mock_task:
            result = CorpusService.set_visibility(self.creator, self.corpus, True)
        self.assertTrue(result.ok)
        mock_task.si.assert_called_once_with(corpus_id=self.corpus.pk)

    def test_make_private_updates_flag(self):
        self.corpus.is_public = True
        self.corpus.save(update_fields=["is_public"])
        result = CorpusService.set_visibility(self.creator, self.corpus, False)
        self.assertTrue(result.ok)
        self.corpus.refresh_from_db()
        self.assertFalse(self.corpus.is_public)

    def test_no_op_when_already_at_target_visibility(self):
        result = CorpusService.set_visibility(self.creator, self.corpus, False)
        self.assertTrue(result.ok)
        assert result.value is not None
        self.assertIn("already", result.value.lower())

    def test_user_without_permission_is_denied(self):
        result = CorpusService.set_visibility(self.other, self.corpus, True)
        self.assertFalse(result.ok)
        self.corpus.refresh_from_db()
        self.assertFalse(self.corpus.is_public)


class TestCorpusServiceEmbedderGuard(TestCase):
    """``CorpusService.assert_embedder_change_allowed`` — issue #437 guard."""

    def setUp(self):
        self.creator = User.objects.create_user(
            username="cs_emb_creator", email="cs_emb_creator@test.com"
        )
        self.corpus = Corpus.objects.create(
            title="Embedder Corpus",
            creator=self.creator,
            preferred_embedder="embedder.A",
        )

    def test_same_embedder_is_allowed(self):
        self.assertEqual(
            CorpusService.assert_embedder_change_allowed(self.corpus, "embedder.A"),
            "",
        )

    def test_different_embedder_allowed_when_corpus_empty(self):
        with patch.object(Corpus, "has_documents", return_value=False):
            self.assertEqual(
                CorpusService.assert_embedder_change_allowed(self.corpus, "embedder.B"),
                "",
            )

    def test_different_embedder_blocked_when_corpus_has_documents(self):
        with patch.object(Corpus, "has_documents", return_value=True):
            error = CorpusService.assert_embedder_change_allowed(
                self.corpus, "embedder.B"
            )
        self.assertIn("reEmbedCorpus", error)


class TestCorpusServiceGrantCreatorPermissions(TestCase):
    """``CorpusService.grant_creator_permissions`` — CRUD + PUBLISH + PERMISSION."""

    def test_grants_full_management_rights(self):
        owner = User.objects.create_user(
            username="cs_grant_owner", email="cs_grant_owner@test.com"
        )
        # Grant to a non-owner so the assertions exercise the explicit grant
        # rather than the creator's implicit full access.
        grantee = User.objects.create_user(
            username="cs_grant_grantee", email="cs_grant_grantee@test.com"
        )
        corpus = Corpus.objects.create(title="Grant Corpus", creator=owner)

        self.assertFalse(corpus.user_can(grantee, PermissionTypes.PERMISSION))

        CorpusService.grant_creator_permissions(grantee, corpus)

        for perm in (
            PermissionTypes.CRUD,
            PermissionTypes.PUBLISH,
            PermissionTypes.PERMISSION,
        ):
            self.assertTrue(corpus.user_can(grantee, perm))
