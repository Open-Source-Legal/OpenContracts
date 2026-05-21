"""
Tests for ``DocumentType._assert_user_can_read``.

The helper consolidates four previously inline ``creator == user or
user.is_superuser`` checks in ``config/graphql/document_types.py`` and
delegates the visibility decision to ``Document.objects.visible_to_user``.
These tests ensure the consolidated helper preserves behaviour for the
public/anonymous/owner/superuser/shared/no-access matrix and exercise the
public-corpus propagation path that the manager-based check unlocks.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase
from graphql import GraphQLError

from config.graphql.document_types import DocumentType
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


def _info_for(user) -> object:
    """Build a minimal stand-in for ``GraphQLResolveInfo`` carrying ``user``."""
    return type("Info", (), {"context": type("Ctx", (), {"user": user})()})()


class DocumentTypeReadPermissionTests(TestCase):
    """Cover the public/private + auth/anon + creator/sharee matrix."""

    def setUp(self) -> None:
        self.owner = User.objects.create_user(username="owner", password="pw")
        self.other = User.objects.create_user(username="other", password="pw")
        self.shared = User.objects.create_user(username="shared", password="pw")
        self.superuser = User.objects.create_superuser(
            username="root", password="pw", email="root@example.com"
        )

        self.private_doc = Document.objects.create(
            title="Private", creator=self.owner, is_public=False
        )
        self.public_doc = Document.objects.create(
            title="Public", creator=self.owner, is_public=True
        )

        # Grant ``shared`` explicit read permission on the private document.
        set_permissions_for_obj_to_user(
            self.shared, self.private_doc, [PermissionTypes.READ]
        )

    def test_anonymous_blocked_for_private_doc(self) -> None:
        with self.assertRaises(GraphQLError) as cm:
            DocumentType._assert_user_can_read(
                self.private_doc, _info_for(AnonymousUser())
            )
        self.assertIn("Authentication required", str(cm.exception))

    def test_anonymous_allowed_for_public_doc(self) -> None:
        anon = AnonymousUser()
        result = DocumentType._assert_user_can_read(self.public_doc, _info_for(anon))
        self.assertIs(result, anon)

    def test_creator_allowed(self) -> None:
        result = DocumentType._assert_user_can_read(
            self.private_doc, _info_for(self.owner)
        )
        self.assertEqual(result, self.owner)

    def test_superuser_allowed(self) -> None:
        result = DocumentType._assert_user_can_read(
            self.private_doc, _info_for(self.superuser)
        )
        self.assertEqual(result, self.superuser)

    def test_user_with_explicit_read_allowed(self) -> None:
        result = DocumentType._assert_user_can_read(
            self.private_doc, _info_for(self.shared)
        )
        self.assertEqual(result, self.shared)

    def test_authenticated_user_without_access_blocked(self) -> None:
        with self.assertRaises(GraphQLError) as cm:
            DocumentType._assert_user_can_read(self.private_doc, _info_for(self.other))
        self.assertIn("do not have access", str(cm.exception))

    def test_public_doc_visible_to_unrelated_user(self) -> None:
        result = DocumentType._assert_user_can_read(
            self.public_doc, _info_for(self.other)
        )
        self.assertEqual(result, self.other)

    def test_public_doc_short_circuits_without_db_query(self) -> None:
        """
        Public documents must short-circuit before hitting
        ``visible_to_user(user).filter(...).exists()`` so high-traffic public
        reads aren't penalised. Asserts the helper returns immediately when
        ``self.is_public`` is ``True`` regardless of whether the user could be
        resolved through the manager.
        """
        from unittest.mock import patch

        with patch.object(Document.objects, "visible_to_user") as visible:
            DocumentType._assert_user_can_read(
                self.public_doc, _info_for(AnonymousUser())
            )
            visible.assert_not_called()

    def test_anonymous_private_doc_short_circuits_without_db_query(self) -> None:
        """
        Anonymous access to a private document must reject before hitting the
        DB. ``visible_to_user(AnonymousUser())`` collapses to ``is_public=True``
        so the lookup is guaranteed to return False — skipping it preserves the
        old hot-path ordering and avoids an unnecessary round-trip.
        """
        from unittest.mock import patch

        with patch.object(Document.objects, "visible_to_user") as visible:
            with self.assertRaises(GraphQLError):
                DocumentType._assert_user_can_read(
                    self.private_doc, _info_for(AnonymousUser())
                )
            visible.assert_not_called()

    def test_doc_in_public_corpus_visible_to_anonymous(self) -> None:
        """
        A document added to a public corpus gets ``is_public=True`` propagated
        onto its corpus-isolated copy (see ``Corpus.add_document`` — public
        corpus → public doc). The helper, going through
        ``Document.objects.visible_to_user``, must then grant read access to
        anonymous users on that copy. This pins the corpus-scoped visibility
        path the helper relies on.
        """
        public_corpus = Corpus.objects.create(
            title="Public Corpus", creator=self.owner, is_public=True
        )
        corpus_copy, _, _ = public_corpus.add_document(
            document=self.private_doc, user=self.owner
        )
        self.assertTrue(
            corpus_copy.is_public,
            "Adding a private doc to a public corpus should propagate "
            "is_public=True onto the corpus-isolated copy",
        )

        anon = AnonymousUser()
        result = DocumentType._assert_user_can_read(corpus_copy, _info_for(anon))
        self.assertIs(result, anon)
