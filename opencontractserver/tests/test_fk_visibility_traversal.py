"""Regression tests for permission-filtered singular FK object traversal.

graphene-django auto-converted a to-one FK whose target ``DjangoObjectType``
overrode ``get_queryset`` into a permission-filtered resolver
(``convert_field_to_djangomodel``): an invisible FK target resolved to
``null``. The strawberry port initially declared these FKs as plain getattr
fields, which leaked the target row's fields across a permission boundary
(e.g. ``AnnotationType.corpus`` / ``CorpusReferenceType.targetDocument`` /
``ConversationType.chatWithCorpus`` pointing at a private corpus/document).

``config.graphql.core.relay.resolve_visible_fk`` reinstates the target type's
visibility hook for singular FK fields; these tests pin both branches of it
(``get_queryset`` and ``get_node``), the non-null ``DocumentPathType.document``
list-level MIN filter that closes the same leak where the field cannot be
null, and one end-to-end schema query.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from graphql_relay import to_global_id

from config.graphql.core.relay import resolve_visible_fk
from config.graphql.schema import schema
from config.graphql.testing import Client
from opencontractserver.conversations.models import Conversation
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentPath
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


class _Ctx:
    """Minimal Django-request-like GraphQL context (carries ``user``)."""

    def __init__(self, user):
        self.user = user
        self.META = {}


class _Info:
    """Minimal ``strawberry.Info``-like stand-in for direct resolver calls."""

    def __init__(self, user):
        self.context = _Ctx(user)


class _Row:
    """Lightweight stand-in for a Django row exposing only FK id columns."""

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class FkVisibilityHelperTests(TestCase):
    """``resolve_visible_fk`` filters through the target type's visibility hook."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.owner = User.objects.create_user(username="fk_owner", password="pw")
        cls.outsider = User.objects.create_user(username="fk_outsider", password="pw")

        cls.private_corpus = Corpus.objects.create(
            title="Private Corpus", creator=cls.owner, is_public=False
        )
        set_permissions_for_obj_to_user(
            cls.owner, cls.private_corpus, [PermissionTypes.CRUD]
        )

        cls.private_doc = Document.objects.create(
            title="Private Doc", creator=cls.owner, is_public=False
        )
        set_permissions_for_obj_to_user(
            cls.owner, cls.private_doc, [PermissionTypes.CRUD]
        )

        # Private conversations whose FKs point at the private corpus/document.
        # A Conversation may attach to a corpus OR a document, not both
        # (``chat_type_mutual_exclusivity_constraint``), so use two rows.
        cls.conversation = Conversation.objects.create(
            title="Conv-corpus",
            creator=cls.owner,
            is_public=False,
            chat_with_corpus=cls.private_corpus,
        )
        cls.conversation_doc = Conversation.objects.create(
            title="Conv-doc",
            creator=cls.owner,
            is_public=False,
            chat_with_document=cls.private_doc,
        )

    # --- get_queryset branch (CorpusType / DocumentType) ------------------- #

    def test_get_queryset_target_hidden_for_outsider(self) -> None:
        info = _Info(self.outsider)
        self.assertIsNone(
            resolve_visible_fk(
                self.conversation, info, "chat_with_corpus_id", "CorpusType"
            ),
            "private corpus leaked through a plain FK field",
        )
        self.assertIsNone(
            resolve_visible_fk(
                self.conversation_doc, info, "chat_with_document_id", "DocumentType"
            ),
            "private document leaked through a plain FK field",
        )

    def test_get_queryset_target_visible_for_owner(self) -> None:
        info = _Info(self.owner)
        self.assertEqual(
            resolve_visible_fk(
                self.conversation, info, "chat_with_corpus_id", "CorpusType"
            ),
            self.private_corpus,
        )
        self.assertEqual(
            resolve_visible_fk(
                self.conversation_doc, info, "chat_with_document_id", "DocumentType"
            ),
            self.private_doc,
        )

    # --- get_node branch (ConversationType) -------------------------------- #

    def test_get_node_target_hidden_for_outsider(self) -> None:
        row = _Row(conversation_id=self.conversation.pk)
        self.assertIsNone(
            resolve_visible_fk(
                row, _Info(self.outsider), "conversation_id", "ConversationType"
            ),
            "private conversation leaked through a plain FK field",
        )

    def test_get_node_target_visible_for_owner(self) -> None:
        row = _Row(conversation_id=self.conversation.pk)
        self.assertEqual(
            resolve_visible_fk(
                row, _Info(self.owner), "conversation_id", "ConversationType"
            ),
            self.conversation,
        )

    # --- edge cases -------------------------------------------------------- #

    def test_null_fk_returns_none(self) -> None:
        self.assertIsNone(
            resolve_visible_fk(
                _Row(corpus_id=None), _Info(self.owner), "corpus_id", "CorpusType"
            )
        )

    def test_malformed_fk_returns_none(self) -> None:
        # A non-numeric id reaching an ``int(pk)`` hook must not raise.
        self.assertIsNone(
            resolve_visible_fk(
                _Row(conversation_id="not-a-pk"),
                _Info(self.owner),
                "conversation_id",
                "ConversationType",
            )
        )


class DocumentPathMinVisibilityTests(TestCase):
    """DocumentPath list enforces MIN(document, corpus) — the non-null
    ``DocumentPathType.document`` cannot resolve to null, so paths pointing at
    documents the caller may not see are excluded at the list level."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.owner = User.objects.create_user(username="dp_owner", password="pw")
        cls.viewer = User.objects.create_user(username="dp_viewer", password="pw")

        # Public corpus: readable by anyone (corpus-as-gate would surface all
        # of its paths).
        cls.corpus = Corpus.objects.create(
            title="Public Corpus", creator=cls.owner, is_public=True
        )
        cls.public_doc = Document.objects.create(
            title="Public Doc", creator=cls.owner, is_public=True
        )
        cls.private_doc = Document.objects.create(
            title="Private Doc", creator=cls.owner, is_public=False
        )
        set_permissions_for_obj_to_user(
            cls.owner, cls.private_doc, [PermissionTypes.CRUD]
        )
        for doc in (cls.public_doc, cls.private_doc):
            DocumentPath.objects.create(
                document=doc,
                corpus=cls.corpus,
                folder=None,
                path=f"/{doc.title}",
                version_number=1,
                parent=None,
                is_current=True,
                is_deleted=False,
                creator=cls.owner,
                backend_lock=False,
                is_public=doc.is_public,
            )

    def _visible_document_ids(self, user):
        from config.graphql.document_types import _get_queryset_DocumentPathType

        qs = _get_queryset_DocumentPathType(DocumentPath.objects.all(), _Info(user))
        return set(qs.values_list("document_id", flat=True))

    def test_private_document_path_excluded_for_non_owner(self) -> None:
        doc_ids = self._visible_document_ids(self.viewer)
        self.assertIn(self.public_doc.id, doc_ids)
        self.assertNotIn(
            self.private_doc.id,
            doc_ids,
            "a private document's path is listed in a public corpus (leak)",
        )

    def test_owner_sees_all_paths(self) -> None:
        doc_ids = self._visible_document_ids(self.owner)
        self.assertIn(self.public_doc.id, doc_ids)
        self.assertIn(self.private_doc.id, doc_ids)


class FkVisibilitySchemaTests(TestCase):
    """End-to-end: a nullable FK to an invisible target resolves to ``null``
    through the served schema (``CorpusType.parent``)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.owner = User.objects.create_user(username="s_owner", password="pw")
        cls.outsider = User.objects.create_user(username="s_outsider", password="pw")

        cls.private_parent = Corpus.objects.create(
            title="Secret Parent", creator=cls.owner, is_public=False
        )
        set_permissions_for_obj_to_user(
            cls.owner, cls.private_parent, [PermissionTypes.CRUD]
        )
        cls.public_child = Corpus.objects.create(
            title="Public Child",
            creator=cls.owner,
            is_public=True,
            parent=cls.private_parent,
        )

    def _query_parent_as(self, user):
        return Client(schema).execute(
            "query($id: ID!) { corpus(id: $id) { id parent { id title } } }",
            variables={"id": to_global_id("CorpusType", self.public_child.id)},
            context_value=_Ctx(user),
        )

    def test_outsider_cannot_see_private_parent_corpus(self) -> None:
        result = self._query_parent_as(self.outsider)
        node = result["data"]["corpus"]
        self.assertIsNotNone(node, f"public child not visible: {result}")
        self.assertIsNone(
            node["parent"],
            "private parent corpus leaked via CorpusType.parent traversal",
        )

    def test_owner_sees_private_parent_corpus(self) -> None:
        result = self._query_parent_as(self.owner)
        node = result["data"]["corpus"]
        self.assertIsNotNone(node["parent"], f"owner denied their own parent: {result}")
        self.assertEqual(
            node["parent"]["id"],
            to_global_id("CorpusType", self.private_parent.id),
        )
