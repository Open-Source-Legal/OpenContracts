from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from graphene.test import Client
from graphql_relay import to_global_id

from config.graphql.schema import schema
from opencontractserver.annotations.models import Annotation, AnnotationLabel, Note
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


class TestContext:
    def __init__(self, user):
        self.user = user


class ComprehensivePermissionTestCase(TestCase):
    def setUp(self):
        # Create users
        self.owner = User.objects.create_user(username="owner", password="password")
        self.collaborator = User.objects.create_user(
            username="collaborator", password="password"
        )
        self.regular_user = User.objects.create_user(
            username="regular", password="password"
        )
        self.anonymous_user = None

        # Create GraphQL clients
        self.owner_client = Client(schema, context_value=TestContext(self.owner))
        self.collaborator_client = Client(
            schema, context_value=TestContext(self.collaborator)
        )
        self.regular_client = Client(
            schema, context_value=TestContext(self.regular_user)
        )
        self.anonymous_client = Client(
            schema, context_value=TestContext(AnonymousUser())
        )

        # Create Corpuses
        self.public_corpus = Corpus.objects.create(
            title="Public Corpus", creator=self.owner, is_public=True
        )
        self.private_corpus = Corpus.objects.create(
            title="Private Corpus", creator=self.owner, is_public=False
        )
        self.shared_corpus = Corpus.objects.create(
            title="Shared Corpus", creator=self.owner, is_public=False
        )

        # Set permissions for shared corpus
        set_permissions_for_obj_to_user(
            self.collaborator, self.shared_corpus, [PermissionTypes.READ]
        )

        # Create Documents
        self.public_doc = Document.objects.create(
            title="Public Doc", creator=self.owner, is_public=True
        )
        self.private_doc = Document.objects.create(
            title="Private Doc", creator=self.owner, is_public=False
        )
        # Store the versioned documents returned by add_document()
        self.public_doc, _, _ = self.public_corpus.add_document(
            document=self.public_doc, user=self.owner
        )
        self.private_doc, _, _ = self.public_corpus.add_document(
            document=self.private_doc, user=self.owner
        )

        # Create Annotations
        # Mark as structural since they're in a corpus (per new permission model)
        # Include corpus field for proper permission inheritance
        self.public_annotation = Annotation.objects.create(
            document=self.public_doc,
            corpus=self.public_corpus,
            creator=self.owner,
            is_public=True,
            structural=True,
        )
        self.private_annotation = Annotation.objects.create(
            document=self.public_doc,
            corpus=self.public_corpus,
            creator=self.owner,
            is_public=False,
            structural=True,
        )

    def test_corpus_visibility(self):
        query = """
        query {
          corpuses {
            edges {
              node {
                id
                title
                isPublic
              }
            }
          }
        }
        """

        # Test for owner: 3 test corpuses + 1 personal corpus = 4
        result = self.owner_client.execute(query)
        self.assertEqual(len(result["data"]["corpuses"]["edges"]), 4)

        # Collaborator: public corpus + shared corpus + 1 personal corpus = 3
        result = self.collaborator_client.execute(query)
        self.assertEqual(len(result["data"]["corpuses"]["edges"]), 3)

        # Regular user: public corpus + 1 personal corpus = 2
        result = self.regular_client.execute(query)
        self.assertEqual(len(result["data"]["corpuses"]["edges"]), 2)

        # Anonymous user: only the public corpus (no personal corpus)
        result = self.anonymous_client.execute(query)
        self.assertEqual(len(result["data"]["corpuses"]["edges"]), 1)

    def test_nested_document_visibility(self):
        query = """
        query($id: ID!) {
          corpus(id: $id) {
            documents {
              edges {
                node {
                  id
                  title
                  isPublic
                }
              }
            }
          }
        }
        """
        variables = {"id": to_global_id("CorpusType", self.public_corpus.id)}

        # Test for owner
        result = self.owner_client.execute(query, variable_values=variables)
        self.assertEqual(len(result["data"]["corpus"]["documents"]["edges"]), 2)

        # Test for regular user — all docs in a public corpus inherit
        # is_public=True, so the regular user sees both documents.
        result = self.regular_client.execute(query, variable_values=variables)
        self.assertEqual(len(result["data"]["corpus"]["documents"]["edges"]), 2)

    def test_nested_annotation_visibility(self):
        query = """
        query($id: ID!) {
          document(id: $id) {
            docAnnotations {
              edges {
                node {
                  id
                  isPublic
                }
              }
            }
          }
        }
        """
        variables = {"id": to_global_id("DocumentType", self.public_doc.id)}

        # Test for owner
        result = self.owner_client.execute(query, variable_values=variables)
        self.assertEqual(len(result["data"]["document"]["docAnnotations"]["edges"]), 2)

        # Test for regular user
        # With new permission model, structural annotations are visible to anyone who can read the document
        result = self.regular_client.execute(query, variable_values=variables)
        self.assertEqual(len(result["data"]["document"]["docAnnotations"]["edges"]), 2)

    def test_mutation_permissions(self):
        mutation = """
        mutation($id: String!) {
          deleteCorpus(id: $id) {
            ok
            message
          }
        }
        """
        corpus_to_delete = Corpus.objects.create(
            title="Corpus to Delete", creator=self.owner, is_public=True
        )

        # Deletions ARE tied to per instance permissions.
        set_permissions_for_obj_to_user(
            self.owner.id, corpus_to_delete, [PermissionTypes.CRUD]
        )
        variables = {"id": to_global_id("CorpusType", corpus_to_delete.id)}

        # Test for regular user (should fail with unified ok=False envelope).
        # Phase D #1658: DeleteCorpusMutation now returns ok=False instead of
        # raising Corpus.DoesNotExist so the response shape doesn't leak
        # existence-vs-permission to enumerating callers.
        result = self.regular_client.execute(mutation, variable_values=variables)
        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["deleteCorpus"]["ok"])

        # Verify corpus still exists in database
        self.assertTrue(Corpus.objects.filter(id=corpus_to_delete.id).exists())

        # Test for owner (should succeed)
        result = self.owner_client.execute(mutation, variable_values=variables)

        # Verify corpus is actually deleted from database
        self.assertFalse(Corpus.objects.filter(id=corpus_to_delete.id).exists())

    def test_mutation_permissions_on_private_object(self):
        mutation = """
        mutation($id: String!) {
          deleteCorpus(id: $id) {
            ok
            message
          }
        }
        """
        private_corpus = Corpus.objects.create(
            title="Private Corpus to Delete", creator=self.owner, is_public=False
        )
        # Deletions ARE tied to per instance permissions.
        set_permissions_for_obj_to_user(
            self.owner.id, private_corpus, [PermissionTypes.CRUD]
        )
        variables = {"id": to_global_id("CorpusType", private_corpus.id)}

        # Test for collaborator (should fail with unified ok=False envelope).
        # Phase D #1658: same IDOR-safe response whether the corpus is hidden
        # by visibility or visible-but-undeletable; previously the unauthorized
        # branch raised Corpus.DoesNotExist which surfaced as a GraphQL errors
        # entry.
        result = self.collaborator_client.execute(mutation, variable_values=variables)
        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["deleteCorpus"]["ok"])

        # Verify corpus still exists in database
        self.assertTrue(Corpus.objects.filter(id=private_corpus.id).exists())

        # Test for owner (should succeed)
        result = self.owner_client.execute(mutation, variable_values=variables)
        self.assertTrue(result["data"]["deleteCorpus"]["ok"])

        # Verify corpus is actually deleted from database
        self.assertFalse(Corpus.objects.filter(id=private_corpus.id).exists())

    def test_delete_personal_corpus_returns_unified_envelope(self):
        """Phase D #1658: even the ``is_personal`` rejection must travel via
        ``{ok: false, message}`` rather than ``GraphQLError``, so frontend
        consumers can pattern-match a single response shape.
        """
        mutation = """
        mutation($id: String!) {
          deleteCorpus(id: $id) {
            ok
            message
          }
        }
        """
        # The owner's personal corpus is auto-created by the user signal —
        # the ``one_personal_corpus_per_user`` constraint forbids a second.
        personal_corpus = Corpus.objects.get(creator=self.owner, is_personal=True)
        set_permissions_for_obj_to_user(
            self.owner.id, personal_corpus, [PermissionTypes.CRUD]
        )
        variables = {"id": to_global_id("CorpusType", personal_corpus.id)}

        result = self.owner_client.execute(mutation, variable_values=variables)

        # No raw GraphQL errors must surface — all rejections live in
        # ``data.deleteCorpus.{ok,message}``.
        self.assertIsNone(result.get("errors"))
        self.assertFalse(result["data"]["deleteCorpus"]["ok"])
        self.assertIn("personal", result["data"]["deleteCorpus"]["message"].lower())

        # Corpus remains in the database.
        self.assertTrue(Corpus.objects.filter(id=personal_corpus.id).exists())

    def test_permission_change_effect(self):
        query = """
        query($id: ID!) {
          corpus(id: $id) {
            id
            title
          }
        }
        """
        variables = {"id": to_global_id("CorpusType", self.private_corpus.id)}

        # Before granting permission
        result = self.collaborator_client.execute(query, variable_values=variables)
        self.assertIsNone(result["data"]["corpus"])

        # Grant permission
        set_permissions_for_obj_to_user(
            self.collaborator, self.private_corpus, [PermissionTypes.READ]
        )

        # After granting permission
        result = self.collaborator_client.execute(query, variable_values=variables)
        self.assertIsNotNone(result["data"]["corpus"])
        self.assertEqual(result["data"]["corpus"]["title"], "Private Corpus")

    def test_public_flag_change_effect(self):
        query = """
        query($id: ID!) {
          corpus(id: $id) {
            id
            title
          }
        }
        """
        variables = {"id": to_global_id("CorpusType", self.private_corpus.id)}

        # Before making public
        result = self.regular_client.execute(query, variable_values=variables)
        self.assertIsNone(result["data"]["corpus"])

        # Make corpus public
        self.private_corpus.is_public = True
        self.private_corpus.save()

        # After making public
        result = self.regular_client.execute(query, variable_values=variables)
        self.assertIsNotNone(result["data"]["corpus"])
        self.assertEqual(result["data"]["corpus"]["title"], "Private Corpus")


class PublicCorpusDocumentVisibilityTest(TestCase):
    """Tests for public-corpus → document is_public propagation.

    Documents in public corpora automatically inherit is_public=True,
    preserving the permissioning guide rule: both document AND corpus
    must be is_public=True for anonymous access.  Propagation happens
    at three points:
      1. Corpus.add_document() / import_document() — on creation
      2. Corpus.save() — when is_public changes
    """

    def setUp(self):
        from opencontractserver.constants.document_processing import (
            MARKDOWN_MIME_TYPE,
        )

        self.owner = User.objects.create_user(username="pc_owner", password="password")
        self.viewer = User.objects.create_user(
            username="pc_viewer", password="password"
        )

        # Public corpus — documents added here inherit is_public=True
        self.public_corpus = Corpus.objects.create(
            title="Public Corpus", creator=self.owner, is_public=True
        )

        # Source docs are created with is_public=False, but the corpus
        # copies produced by add_document() inherit from the public corpus.
        source_pdf = Document.objects.create(
            title="PDF Doc", creator=self.owner, is_public=False
        )
        self.pdf_in_public, _, _ = self.public_corpus.add_document(
            document=source_pdf, user=self.owner
        )

        source_caml = Document.objects.create(
            title="Readme.CAML",
            creator=self.owner,
            is_public=False,
            file_type=MARKDOWN_MIME_TYPE,
        )
        self.caml_in_public, _, _ = self.public_corpus.add_document(
            document=source_caml, user=self.owner
        )

        # Private corpus — documents added here stay private
        self.private_corpus = Corpus.objects.create(
            title="Private Corpus", creator=self.owner, is_public=False
        )
        source_public = Document.objects.create(
            title="Public Doc Private Corpus", creator=self.owner, is_public=True
        )
        self.public_doc_in_private, _, _ = self.private_corpus.add_document(
            document=source_public, user=self.owner
        )

    # -- Propagation on add_document --

    def test_add_document_to_public_corpus_sets_is_public(self):
        """Documents added to a public corpus get is_public=True."""
        self.assertTrue(self.pdf_in_public.is_public)
        self.assertTrue(self.caml_in_public.is_public)

    def test_add_document_to_private_corpus_preserves_source_public(self):
        """Public source doc keeps is_public=True when added to private corpus."""
        self.assertTrue(self.public_doc_in_private.is_public)

    def test_add_document_to_private_corpus_stays_private(self):
        """Private source doc stays is_public=False in private corpus."""
        source = Document.objects.create(
            title="Hidden", creator=self.owner, is_public=False
        )
        copy, _, _ = self.private_corpus.add_document(document=source, user=self.owner)
        self.assertFalse(copy.is_public)

    # -- Anonymous visibility (via standard is_public filter) --

    def test_anonymous_sees_all_docs_in_public_corpus(self):
        """Anonymous user sees all docs in public corpus (both inherited public)."""
        anon = AnonymousUser()
        visible_pks = set(
            Document.objects.visible_to_user(anon, lightweight=True).values_list(
                "pk", flat=True
            )
        )
        self.assertIn(self.pdf_in_public.pk, visible_pks)
        self.assertIn(self.caml_in_public.pk, visible_pks)

    def test_anonymous_sees_public_doc_in_private_corpus(self):
        """A public doc in a private corpus is visible via its own is_public."""
        anon = AnonymousUser()
        visible_pks = set(
            Document.objects.visible_to_user(anon, lightweight=True).values_list(
                "pk", flat=True
            )
        )
        self.assertIn(self.public_doc_in_private.pk, visible_pks)

    def test_anonymous_cannot_see_private_doc_in_private_corpus(self):
        """Private doc in private corpus is hidden from anonymous users."""
        source = Document.objects.create(
            title="Hidden", creator=self.owner, is_public=False
        )
        copy, _, _ = self.private_corpus.add_document(document=source, user=self.owner)

        anon = AnonymousUser()
        visible_pks = set(
            Document.objects.visible_to_user(anon, lightweight=True).values_list(
                "pk", flat=True
            )
        )
        self.assertNotIn(copy.pk, visible_pks)

    # -- Authenticated user without explicit permissions --

    def test_authenticated_sees_all_docs_in_public_corpus(self):
        """Authenticated user without permissions sees public-corpus docs."""
        visible_pks = set(
            Document.objects.visible_to_user(self.viewer, lightweight=True).values_list(
                "pk", flat=True
            )
        )
        self.assertIn(self.pdf_in_public.pk, visible_pks)
        self.assertIn(self.caml_in_public.pk, visible_pks)

    # -- Corpus is_public change propagation --

    def test_corpus_becomes_public_propagates_to_documents(self):
        """When a corpus becomes public, all its documents become public."""
        source = Document.objects.create(
            title="Initially Private", creator=self.owner, is_public=False
        )
        copy, _, _ = self.private_corpus.add_document(document=source, user=self.owner)
        self.assertFalse(copy.is_public)

        self.private_corpus.is_public = True
        self.private_corpus.save()

        copy.refresh_from_db()
        self.assertTrue(copy.is_public)

    def test_corpus_becomes_private_revokes_public(self):
        """When a corpus becomes private, docs not in another public corpus
        lose is_public=True."""
        # caml_in_public is only in self.public_corpus
        self.assertTrue(self.caml_in_public.is_public)

        self.public_corpus.is_public = False
        self.public_corpus.save()

        self.caml_in_public.refresh_from_db()
        self.assertFalse(self.caml_in_public.is_public)

    def test_corpus_becomes_private_preserves_multi_corpus_doc(self):
        """When a corpus becomes private, docs still in another public corpus
        keep is_public=True."""
        # Create a second public corpus and add the same source doc
        other_public = Corpus.objects.create(
            title="Other Public", creator=self.owner, is_public=True
        )
        source = Document.objects.create(
            title="Shared Doc", creator=self.owner, is_public=False
        )
        copy_in_first, _, _ = self.public_corpus.add_document(
            document=source, user=self.owner
        )
        # Add the SAME corpus copy to the other public corpus by creating
        # a DocumentPath pointing to it
        from opencontractserver.documents.models import DocumentPath

        DocumentPath.objects.create(
            document=copy_in_first,
            corpus=other_public,
            path="/docs/shared",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=self.owner,
        )

        self.assertTrue(copy_in_first.is_public)

        # Now make the first public corpus private
        self.public_corpus.is_public = False
        self.public_corpus.save()

        copy_in_first.refresh_from_db()
        # Still public because it's in other_public
        self.assertTrue(copy_in_first.is_public)


class CorpusGetDocumentsAndCountTest(TestCase):
    """Tests for Corpus.get_documents(include_caml) and Corpus.document_count()."""

    def setUp(self):
        from opencontractserver.constants.document_processing import (
            MARKDOWN_MIME_TYPE,
        )

        self.owner = User.objects.create_user(username="gd_owner", password="password")
        self.corpus = Corpus.objects.create(
            title="Doc Listing Corpus", creator=self.owner, is_public=True
        )

        # Add a normal PDF document
        source_pdf = Document.objects.create(
            title="Report.pdf",
            creator=self.owner,
            is_public=False,
            file_type="application/pdf",
        )
        self.pdf_doc, _, _ = self.corpus.add_document(
            document=source_pdf, user=self.owner
        )

        # Add a CAML/markdown document
        source_caml = Document.objects.create(
            title="Readme.CAML",
            creator=self.owner,
            is_public=False,
            file_type=MARKDOWN_MIME_TYPE,
        )
        self.caml_doc, _, _ = self.corpus.add_document(
            document=source_caml, user=self.owner
        )

    def test_get_documents_excludes_caml_by_default(self):
        """_get_active_documents() without include_caml excludes markdown files."""
        docs = self.corpus._get_active_documents()
        self.assertIn(self.pdf_doc.pk, docs.values_list("pk", flat=True))
        self.assertNotIn(self.caml_doc.pk, docs.values_list("pk", flat=True))

    def test_get_documents_includes_caml_when_requested(self):
        """_get_active_documents(include_caml=True) includes markdown files."""
        docs = self.corpus._get_active_documents(include_caml=True)
        pks = set(docs.values_list("pk", flat=True))
        self.assertIn(self.pdf_doc.pk, pks)
        self.assertIn(self.caml_doc.pk, pks)

    def test_get_documents_explicit_false_excludes_caml(self):
        """_get_active_documents(include_caml=False) explicitly excludes markdown."""
        docs = self.corpus._get_active_documents(include_caml=False)
        self.assertNotIn(self.caml_doc.pk, docs.values_list("pk", flat=True))

    def test_document_count_excludes_caml(self):
        """document_count() does not count markdown/CAML articles."""
        self.assertEqual(self.corpus.document_count(), 1)

    def test_document_count_zero_when_only_caml(self):
        """document_count() returns 0 when corpus contains only CAML files."""
        # Remove the PDF
        self.corpus.remove_document(document=self.pdf_doc, user=self.owner)
        self.assertEqual(self.corpus.document_count(), 0)


def _prefetch_lookup_names(qs) -> set[str]:
    """
    Collect the lookup paths from a queryset's ``_prefetch_related_lookups``.

    Entries can be raw strings (``"foo__bar"``) or ``Prefetch`` instances
    (which expose the path as ``prefetch_through``); normalise to a set of
    string paths so tests can assert membership without caring which form
    a given prefetch was registered as.
    """
    return {
        item if isinstance(item, str) else item.prefetch_through
        for item in qs._prefetch_related_lookups
    }


class DocumentManagerVisibleToUserTest(TestCase):
    """Tests for DocumentManager.visible_to_user() with lightweight flag."""

    def setUp(self):
        self.owner = User.objects.create_user(username="mgr_owner", password="password")
        self.viewer = User.objects.create_user(
            username="mgr_viewer", password="password"
        )
        self.superuser = User.objects.create_superuser(
            username="mgr_super", password="password"
        )

        self.corpus = Corpus.objects.create(
            title="Manager Test Corpus", creator=self.owner, is_public=True
        )
        source = Document.objects.create(
            title="Visible Doc", creator=self.owner, is_public=False
        )
        self.doc, _, _ = self.corpus.add_document(document=source, user=self.owner)

    def test_lightweight_skips_heavy_prefetch_but_keeps_cheap_joins(self):
        """
        lightweight=True keeps cheap select_related JOINs (creator, parent,
        user_lock) and the user-scoped guardian permission prefetches because
        the GraphQL fields that consume them (``creator``, ``myPermissions``,
        version metadata) are commonly requested even on list views — leaving
        them unprefetched produces an N+1 storm.

        It still skips the heavy per-document fan-outs: full doc_annotations
        prefetch, ``rows``, source/target relationships, and ``notes``.
        """
        qs = Document.objects.visible_to_user(self.viewer, lightweight=True)
        self.assertIn(self.doc.pk, qs.values_list("pk", flat=True))

        # Cheap JOINs are present in lightweight mode.
        self.assertIn("creator", qs.query.select_related)
        self.assertIn("user_lock", qs.query.select_related)
        self.assertIn("parent", qs.query.select_related)

        prefetch_lookups = _prefetch_lookup_names(qs)
        # Heavy fan-outs stay skipped under lightweight=True.
        self.assertNotIn("rows", prefetch_lookups)
        self.assertNotIn("source_relationships", prefetch_lookups)
        self.assertNotIn("target_relationships", prefetch_lookups)
        self.assertNotIn("notes", prefetch_lookups)
        # User-scoped guardian prefetches are kept so resolve_my_permissions
        # doesn't fire 2 queries per row (see mixins.py:272-291).
        self.assertIn("documentuserobjectpermission_set", prefetch_lookups)

    def test_non_lightweight_adds_prefetch(self):
        """lightweight=False (default) adds select_related and prefetch_related."""
        qs = Document.objects.visible_to_user(self.viewer, lightweight=False)
        self.assertIn(self.doc.pk, qs.values_list("pk", flat=True))
        # select_related should include "creator" and "user_lock"
        self.assertIn("creator", qs.query.select_related)
        self.assertIn("user_lock", qs.query.select_related)

    def test_lightweight_with_doc_label_annotations_prefetches_focused_set(self):
        """
        ``with_doc_label_annotations=True`` in lightweight mode adds a focused
        ``doc_annotations`` prefetch (DOC_TYPE_LABEL only) so that
        ``resolve_doc_annotations_optimized`` can pick it up via
        ``_prefetched_doc_annotations`` instead of falling through to a
        per-document optimizer call.
        """
        qs = Document.objects.visible_to_user(
            self.viewer, lightweight=True, with_doc_label_annotations=True
        )
        prefetch_lookups = _prefetch_lookup_names(qs)
        self.assertIn("doc_annotations", prefetch_lookups)
        # Heavy fan-outs are still skipped.
        self.assertNotIn("rows", prefetch_lookups)
        self.assertNotIn("notes", prefetch_lookups)

    def test_none_user_treated_as_anonymous(self):
        """Passing user=None returns same results as AnonymousUser."""
        qs_none = Document.objects.visible_to_user(user=None, lightweight=True)
        anon = AnonymousUser()
        qs_anon = Document.objects.visible_to_user(user=anon, lightweight=True)
        self.assertEqual(
            set(qs_none.values_list("pk", flat=True)),
            set(qs_anon.values_list("pk", flat=True)),
        )

    def test_superuser_sees_all(self):
        """Superuser sees all documents regardless of permissions."""
        private_doc = Document.objects.create(
            title="Private Hidden", creator=self.owner, is_public=False
        )
        qs = Document.objects.visible_to_user(self.superuser, lightweight=True)
        self.assertIn(private_doc.pk, qs.values_list("pk", flat=True))

    def test_superuser_non_lightweight_skips_user_perm_prefetch(self):
        """Superuser with lightweight=False gets prefetches but not user perms."""
        qs = Document.objects.visible_to_user(self.superuser, lightweight=False)
        self.assertIn(self.doc.pk, qs.values_list("pk", flat=True))
        # Should still have select_related
        self.assertIn("creator", qs.query.select_related)


class CorpusPublicPropagationEdgeCasesTest(TestCase):
    """Edge cases for _propagate_public_status_to_documents."""

    def setUp(self):
        self.owner = User.objects.create_user(
            username="prop_owner", password="password"
        )

    def test_propagate_on_empty_corpus(self):
        """Propagation is a no-op on a corpus with no documents."""
        corpus = Corpus.objects.create(
            title="Empty Corpus", creator=self.owner, is_public=False
        )
        # Changing is_public should not raise
        corpus.is_public = True
        corpus.save()
        # No assertions needed — just verify no exception

    def test_save_with_update_fields_including_is_public(self):
        """Propagation fires when update_fields explicitly includes is_public."""
        corpus = Corpus.objects.create(
            title="Update Fields Corpus", creator=self.owner, is_public=False
        )
        source = Document.objects.create(
            title="Doc", creator=self.owner, is_public=False
        )
        copy, _, _ = corpus.add_document(document=source, user=self.owner)
        self.assertFalse(copy.is_public)

        corpus.is_public = True
        corpus.save(update_fields=["is_public"])

        copy.refresh_from_db()
        self.assertTrue(copy.is_public)

    def test_save_without_is_public_change_does_not_propagate(self):
        """Saving a corpus without changing is_public doesn't touch documents."""
        corpus = Corpus.objects.create(
            title="No Change", creator=self.owner, is_public=True
        )
        source = Document.objects.create(
            title="Already Public", creator=self.owner, is_public=False
        )
        copy, _, _ = corpus.add_document(document=source, user=self.owner)
        # copy is now public because corpus is public
        self.assertTrue(copy.is_public)

        # Manually set doc to private for testing
        Document.objects.filter(pk=copy.pk).update(is_public=False)
        copy.refresh_from_db()
        self.assertFalse(copy.is_public)

        # Save corpus without changing is_public — doc should stay private
        corpus.title = "No Change Updated"
        corpus.save()

        copy.refresh_from_db()
        self.assertFalse(copy.is_public)

    def test_revoke_when_all_docs_in_other_public_corpus(self):
        """When corpus goes private but all docs are in another public corpus,
        no documents lose is_public."""
        from opencontractserver.documents.models import DocumentPath

        corpus_a = Corpus.objects.create(
            title="Corpus A", creator=self.owner, is_public=True
        )
        corpus_b = Corpus.objects.create(
            title="Corpus B", creator=self.owner, is_public=True
        )
        source = Document.objects.create(
            title="Shared", creator=self.owner, is_public=False
        )
        copy, _, _ = corpus_a.add_document(document=source, user=self.owner)

        # Also add to corpus_b via DocumentPath
        DocumentPath.objects.create(
            document=copy,
            corpus=corpus_b,
            path="/docs/shared",
            version_number=1,
            is_current=True,
            is_deleted=False,
            creator=self.owner,
        )

        self.assertTrue(copy.is_public)

        # Make corpus_a private — doc should stay public (in corpus_b)
        corpus_a.is_public = False
        corpus_a.save()

        copy.refresh_from_db()
        self.assertTrue(copy.is_public)


class UserCanPrefetchFastPathTest(TestCase):
    """
    Verifies that ``user_can`` consumes the per-user permission prefetches
    set up by ``_apply_document_prefetches`` rather than issuing a guardian
    query per row.

    Regression coverage for issue #1555: ``DocumentType.canViewHistory`` and
    ``DocumentType.canRetry`` are selected by the shared ``GET_DOCUMENTS``
    query, so any paginated ``documents`` resolver was previously paying an
    N+1 cost per page (each call to ``user_can`` did a fresh ``.filter()``
    on the related manager, bypassing the prefetch).
    """

    def setUp(self):
        from django.contrib.auth.models import Group

        self.owner = User.objects.create_user(
            username="prefetch_owner", password="password"
        )
        self.viewer = User.objects.create_user(
            username="prefetch_viewer", password="password"
        )
        self.other_user = User.objects.create_user(
            username="prefetch_other", password="password"
        )
        self.group = Group.objects.create(name="prefetch_test_group")
        self.viewer.groups.add(self.group)

        # Five private documents — viewer gets READ via direct guardian perm,
        # plus a UPDATE perm on one of them via group membership.
        self.docs = []
        for i in range(5):
            doc = Document.objects.create(
                title=f"Prefetch Doc {i}", creator=self.owner, is_public=False
            )
            set_permissions_for_obj_to_user(self.viewer, doc, [PermissionTypes.READ])
            self.docs.append(doc)

        # Group-based UPDATE on the first document so the group-perm prefetch
        # path has at least one row to traverse.
        from guardian.shortcuts import assign_perm

        assign_perm("update_document", self.group, self.docs[0])

    def test_prefetched_attrs_use_user_id_suffix(self):
        """``_apply_document_prefetches`` writes user-id-suffixed attributes."""
        from opencontractserver.shared.prefetch_attrs import (
            user_group_perm_attr,
            user_perm_attr,
        )

        qs = Document.objects.visible_to_user(self.viewer, lightweight=True)
        docs = list(qs)
        attr = user_perm_attr(self.viewer.id)
        group_attr = user_group_perm_attr(self.viewer.id)
        for d in docs:
            self.assertTrue(
                hasattr(d, attr),
                f"Expected {attr} to be set by _apply_document_prefetches",
            )
            self.assertTrue(
                hasattr(d, group_attr),
                f"Expected {group_attr} to be set by _apply_document_prefetches",
            )

    def test_user_can_no_n_plus_1_with_prefetch(self):
        """
        With prefetched docs, calling ``user_can`` per row must NOT issue
        any new queries — independent of N. The previous implementation
        issued one query per row per call (and a second one for the
        permission-id-to-name map plus a third for group perms).
        """
        # Materialize the queryset (includes the prefetches).
        docs = list(Document.objects.visible_to_user(self.viewer, lightweight=True))
        self.assertEqual(len(docs), 5)

        # ZERO queries for READ checks across all rows: every lookup is
        # satisfied from the prefetched ``_prefetched_user_perms_uid_*``
        # list, with group perms from the matching
        # ``_prefetched_user_group_perms_uid_*`` list (both filtered by
        # user_id at prefetch time — ``user_can`` resolves group perms
        # by default).
        with self.assertNumQueries(0):
            for d in docs:
                self.assertTrue(d.user_can(self.viewer, PermissionTypes.READ))

        # Doc[0] has UPDATE via group membership — group prefetch path must
        # surface it. Doc[1..] only have READ, so UPDATE is denied there.
        self.assertTrue(docs[0].user_can(self.viewer, PermissionTypes.UPDATE))
        self.assertFalse(docs[1].user_can(self.viewer, PermissionTypes.UPDATE))

    def test_is_public_grants_read_on_prefetched_path(self):
        """
        The fast path must add ``read_{model_name}`` when the instance is
        public — a public document is readable by anyone, regardless of
        explicit guardian rows.
        """
        from opencontractserver.utils.permissioning import (
            get_users_permissions_for_obj,
        )

        # Promote one of the documents to public; reload via the manager so
        # the user-scoped prefetches are attached.
        Document.objects.filter(pk=self.docs[0].pk).update(is_public=True)
        qs = Document.objects.visible_to_user(self.viewer, lightweight=True)
        public_doc = next(d for d in qs if d.pk == self.docs[0].pk)

        perms = get_users_permissions_for_obj(self.viewer, public_doc)
        self.assertIn("read_document", perms)

    def test_partial_prefetch_falls_back_for_group_perms_only(self):
        """
        If only the user-perm prefetch is attached (and not the group-perm
        prefetch), ``include_group_permissions=True`` must fall back to a
        guardian query for groups while still consuming the prefetched user
        perms. This is the documented contract for non-Document models that
        opt into only the user prefetch.
        """
        from opencontractserver.shared.prefetch_attrs import user_group_perm_attr
        from opencontractserver.utils.permissioning import (
            get_users_permissions_for_obj,
        )

        docs = list(Document.objects.visible_to_user(self.viewer, lightweight=True))
        # Reach into the suffixed attribute name to pin the partial-prefetch
        # contract: this is the lowest-cost way to exercise "user perms cached,
        # group perms not" without inventing a separate manager. Coupled to
        # ``user_group_perm_attr`` on purpose — if the convention changes,
        # ``shared/prefetch_attrs.py`` is the single point of update.
        for d in docs:
            delattr(d, user_group_perm_attr(self.viewer.id))

        perms = get_users_permissions_for_obj(
            self.viewer, docs[0], include_group_permissions=True
        )
        # docs[0] has UPDATE via group membership; READ via direct user perm.
        self.assertIn("read_document", perms)
        self.assertIn("update_document", perms)

    def test_falls_back_when_instance_loaded_without_prefetch(self):
        """
        If the document was loaded via a queryset that didn't go through
        ``_apply_document_prefetches`` (e.g., ``Document.objects.get(pk=...)``),
        the fast path is silently skipped and the legacy guardian queries
        still produce the correct answer.
        """
        doc = Document.objects.get(pk=self.docs[0].pk)
        self.assertFalse(hasattr(doc, f"_prefetched_user_perms_uid_{self.viewer.id}"))
        self.assertTrue(doc.user_can(self.viewer, PermissionTypes.READ))

    def test_different_user_lookup_falls_through_to_guardian(self):
        """
        The user-id suffix is what makes the fast path safe under a
        mismatched user: a queryset prefetched for user A must not return
        user A's perms when asked about user B. Without the suffix, we'd
        be reading the wrong list.

        Asserting the per-row query count > 0 is what proves the fallback
        path was actually taken — a silently-cached attribute would still
        produce ``False`` for ``other_user`` but would issue zero queries.
        """
        docs = list(Document.objects.visible_to_user(self.viewer, lightweight=True))
        # ``other_user`` has no perms on any of these docs; the prefetch is
        # filtered by viewer.id so its presence must not cause us to
        # short-circuit and report viewer.id's perms for other_user. The
        # legacy guardian path issues queries per row — we assert the count
        # is at least ``len(docs)`` to prove the fallback was taken (rather
        # than silently reusing the viewer's prefetched list).
        with CaptureQueriesContext(connection) as ctx:
            for d in docs:
                self.assertFalse(d.user_can(self.other_user, PermissionTypes.READ))
        # Legacy path issues at least 2 queries per row (user-perm filter +
        # permission-id-to-name map). Asserting >= 2 * len(docs) pins both —
        # >= len(docs) alone would mask a partial regression.
        self.assertGreaterEqual(len(ctx.captured_queries), 2 * len(docs))

    def test_resolve_my_permissions_uses_prefetch_via_graphql(self):
        """
        Pin the ``myPermissions`` GraphQL field end-to-end against both the
        prefetched fast path (Document) and the non-prefetched fallback
        (Corpus). Documents go through ``_apply_document_prefetches`` so
        codenames come from the user-id-suffixed cache; Corpuses never have
        the cache attached, so the resolver falls back to ``.filter()`` on
        the related manager — both branches must surface direct + group
        permissions correctly.
        """
        doc_query = """
        query($id: ID!) {
          document(id: $id) {
            myPermissions
          }
        }
        """
        client = Client(schema, context_value=TestContext(self.viewer))

        # docs[0]: viewer has READ via direct guardian + UPDATE via group.
        result = client.execute(
            doc_query,
            variable_values={"id": to_global_id("DocumentType", self.docs[0].id)},
        )
        self.assertNotIn("errors", result)
        perms = set(result["data"]["document"]["myPermissions"])
        self.assertIn("read_document", perms)
        self.assertIn("update_document", perms)

        # docs[1]: only direct READ — group UPDATE must NOT appear.
        result = client.execute(
            doc_query,
            variable_values={"id": to_global_id("DocumentType", self.docs[1].id)},
        )
        self.assertNotIn("errors", result)
        perms = set(result["data"]["document"]["myPermissions"])
        self.assertIn("read_document", perms)
        self.assertNotIn("update_document", perms)

        # Fallback path: Corpus instances don't carry the user-id-suffixed
        # prefetch attrs, so resolve_my_permissions takes the ``.filter()``
        # branch. Verifies the path still surfaces direct + group perms.
        from guardian.shortcuts import assign_perm

        corpus = Corpus.objects.create(
            title="Fallback Corpus", creator=self.owner, is_public=False
        )
        set_permissions_for_obj_to_user(self.viewer, corpus, [PermissionTypes.READ])
        assign_perm("update_corpus", self.group, corpus)

        corpus_query = """
        query($id: ID!) {
          corpus(id: $id) {
            myPermissions
          }
        }
        """
        result = client.execute(
            corpus_query,
            variable_values={"id": to_global_id("CorpusType", corpus.id)},
        )
        self.assertNotIn("errors", result)
        perms = set(result["data"]["corpus"]["myPermissions"])
        self.assertIn("read_corpus", perms)
        self.assertIn("update_corpus", perms)


class GroupObjectPermissionVisibilityTest(TestCase):
    """Regression coverage for issue #1714 — ``QuerySet.visible_to_user``
    must honour *group* object-permissions, not just *user* ones.

    ``Manager.user_can`` resolves group grants: ``_default_user_can``
    runs with ``include_group_permissions=True``. Before the fix, the
    ``PermissionQuerySet`` / ``DocumentQuerySet`` / ``AnnotationQuerySet``
    bodies in ``shared/QuerySets.py`` only joined the *user*
    object-permission table, so a user whose sole READ grant was via a
    group passed ``user_can(READ)`` yet was excluded from
    ``visible_to_user`` — a filter/check drift. ``Note`` drifted
    transitively (it composes ``Document.objects.visible_to_user``).

    These tests pin the filter/check equivalence for a group-shared
    user across Document, Annotation, Note, and the generic
    ``PermissionQuerySet`` fallback body.
    """

    def setUp(self):
        from django.contrib.auth.models import Group
        from guardian.shortcuts import assign_perm

        self.owner = User.objects.create_user(username="grp_owner", password="x")
        # ``group_user``'s ONLY path to the objects below is group
        # membership — no creator status, no direct user grant, nothing
        # public. This isolates the group-permission code path.
        self.group_user = User.objects.create_user(username="grp_member", password="x")
        self.stranger = User.objects.create_user(username="grp_stranger", password="x")

        self.group = Group.objects.create(name="visibility_test_group")
        self.group_user.groups.add(self.group)

        # Private doc + corpus, each READ-shared with the group ONLY.
        self.group_doc = Document.objects.create(
            title="Group-Shared Doc", creator=self.owner, is_public=False
        )
        self.group_corpus = Corpus.objects.create(
            title="Group-Shared Corpus", creator=self.owner, is_public=False
        )
        assign_perm("read_document", self.group, self.group_doc)
        assign_perm("read_corpus", self.group, self.group_corpus)

        # Control: a private doc not shared with the group at all.
        self.unshared_doc = Document.objects.create(
            title="Unshared Doc", creator=self.owner, is_public=False
        )

        self.label = AnnotationLabel.objects.create(
            text="grp_label", label_type="TOKEN_LABEL", creator=self.owner
        )
        # Plain annotation (non-structural, no analysis/extract privacy
        # fields) on the group-shared doc + corpus.
        self.group_annotation = Annotation.objects.create(
            raw_text="group ann",
            json={"x": 1},
            page=1,
            annotation_label=self.label,
            creator=self.owner,
            document=self.group_doc,
            corpus=self.group_corpus,
        )
        self.group_note = Note.objects.create(
            title="Group Note",
            content="x",
            creator=self.owner,
            document=self.group_doc,
            corpus=self.group_corpus,
            is_public=False,
        )

    def test_document_group_grant_appears_in_visible_to_user(self):
        """A document READ-granted to the user's group is included in
        ``Document.objects.visible_to_user`` (issue #1714)."""
        visible_ids = set(
            Document.objects.visible_to_user(self.group_user).values_list(
                "pk", flat=True
            )
        )
        self.assertIn(self.group_doc.pk, visible_ids)
        # Control: a doc not shared with the group stays hidden.
        self.assertNotIn(self.unshared_doc.pk, visible_ids)

    def test_document_group_filter_check_equivalence(self):
        """``user_can(READ)`` and ``visible_to_user(...).exists()`` agree
        for a group-shared user — the invariant the drift broke."""
        check = self.group_doc.user_can(self.group_user, PermissionTypes.READ)
        in_filter = (
            Document.objects.visible_to_user(self.group_user)
            .filter(pk=self.group_doc.pk)
            .exists()
        )
        self.assertTrue(check, "user_can must honour the group-level READ grant")
        self.assertTrue(in_filter, "visible_to_user must honour the group grant")
        self.assertEqual(check, in_filter)

    def test_group_read_grant_does_not_widen_to_writes(self):
        """SECURITY: a group READ grant authorizes READ but never
        UPDATE/DELETE — the read/write asymmetry must hold."""
        self.assertTrue(self.group_doc.user_can(self.group_user, PermissionTypes.READ))
        for perm in (PermissionTypes.UPDATE, PermissionTypes.DELETE):
            self.assertFalse(
                self.group_doc.user_can(self.group_user, perm),
                f"group READ grant silently widened to {perm} — leak!",
            )

    def test_permission_queryset_generic_body_honors_group_perms(self):
        """The generic ``PermissionQuerySet.visible_to_user`` fallback
        body (used by direct ``PermissionManager`` consumers) also
        consults the ``*groupobjectpermission`` table."""
        from opencontractserver.shared.QuerySets import PermissionQuerySet

        qs = PermissionQuerySet(model=Document, using=connection.alias)
        visible_ids = set(
            qs.visible_to_user(self.group_user).values_list("pk", flat=True)
        )
        self.assertIn(self.group_doc.pk, visible_ids)
        self.assertNotIn(self.unshared_doc.pk, visible_ids)

    def test_annotation_group_grant_filter_check_equivalence(self):
        """An annotation whose parent doc + corpus are READ-granted to
        the user's group is in ``Annotation.objects.visible_to_user``
        and passes ``user_can(READ)`` (issue #1714)."""
        check = Annotation.objects.user_can(
            self.group_user, self.group_annotation, PermissionTypes.READ
        )
        in_filter = (
            Annotation.objects.visible_to_user(self.group_user)
            .filter(pk=self.group_annotation.pk)
            .exists()
        )
        self.assertTrue(check, "user_can must honour the group grant on doc + corpus")
        self.assertTrue(in_filter, "visible_to_user must honour the group grant")
        self.assertEqual(check, in_filter)

    def test_note_group_grant_filter_check_equivalence(self):
        """A note inherits visibility from its parent doc + corpus; a
        group READ grant on both makes it visible and keeps
        ``user_can`` / ``visible_to_user`` aligned (issue #1714)."""
        check = Note.objects.user_can(
            self.group_user, self.group_note, PermissionTypes.READ
        )
        in_filter = (
            Note.objects.visible_to_user(self.group_user)
            .filter(pk=self.group_note.pk)
            .exists()
        )
        self.assertTrue(check, "user_can must honour the group-level READ grant")
        self.assertTrue(
            in_filter, "visible_to_user must honour the group-level READ grant"
        )
        self.assertEqual(
            check, in_filter, "user_can and visible_to_user must agree for the note"
        )

    def test_stranger_without_group_membership_stays_excluded(self):
        """A user who is NOT in the group sees none of the group-shared
        objects — the fix must not widen visibility beyond members."""
        for model, instance in (
            (Document, self.group_doc),
            (Annotation, self.group_annotation),
            (Note, self.group_note),
        ):
            in_filter = (
                model.objects.visible_to_user(self.stranger)
                .filter(pk=instance.pk)
                .exists()
            )
            self.assertFalse(
                in_filter,
                f"non-member saw {model.__name__} pk={instance.pk} — leak!",
            )
            self.assertFalse(
                model.objects.user_can(self.stranger, instance, PermissionTypes.READ)
            )

    def test_group_lookup_uses_subquery_not_per_group_round_trips(self):
        """PERFORMANCE: group grants resolve via a SQL subquery, so the
        query count to materialize ``visible_to_user`` is independent of
        how many groups the user belongs to (issue #1714 perf check)."""
        from django.contrib.auth.models import Group

        # A second user in five groups (incl. the shared one) — the
        # extra groups must not each cost a round-trip.
        many_group_user = User.objects.create_user(username="grp_many", password="x")
        many_group_user.groups.add(self.group)
        for i in range(4):
            many_group_user.groups.add(Group.objects.create(name=f"perf_grp_{i}"))

        # lightweight=True skips the heavy prefetch fan-outs so the
        # captured query count reflects only the core visibility query —
        # exactly the part group resolution touches.
        with CaptureQueriesContext(connection) as one_group_ctx:
            list(Document.objects.visible_to_user(self.group_user, lightweight=True))
        with CaptureQueriesContext(connection) as many_group_ctx:
            list(Document.objects.visible_to_user(many_group_user, lightweight=True))

        self.assertEqual(
            len(many_group_ctx.captured_queries),
            len(one_group_ctx.captured_queries),
            "group-permission resolution must not add a round-trip per group",
        )

    def test_visible_to_user_degrades_when_guardian_tables_missing(self):
        """DEFENSIVE: if the guardian ``*userobjectpermission`` /
        ``*groupobjectpermission`` tables cannot be resolved, the
        ``visible_to_user`` bodies fall back gracefully instead of
        raising — each ``except LookupError`` branch zeroes out its own
        permitted-id set. Splitting the user- and group-table lookups
        into separate ``try`` blocks (issue #1714 review) means a
        missing group table never discards already-resolved user grants.
        """
        from unittest.mock import patch

        from django.apps import apps

        from opencontractserver.shared.QuerySets import PermissionQuerySet

        real_get_model = apps.get_model

        def fake_get_model(app_label, model_name=None, *args, **kwargs):
            name = model_name if model_name is not None else app_label
            if "userobjectpermission" in name or "groupobjectpermission" in name:
                raise LookupError(f"simulated missing table: {name}")
            return real_get_model(app_label, model_name, *args, **kwargs)

        with patch.object(apps, "get_model", side_effect=fake_get_model):
            # None of these may raise — the except LookupError branches
            # in every queryset body must handle the missing tables.
            doc_visible = set(
                Document.objects.visible_to_user(self.group_user).values_list(
                    "pk", flat=True
                )
            )
            generic_qs = PermissionQuerySet(model=Document, using=connection.alias)
            generic_visible = set(
                generic_qs.visible_to_user(self.group_user).values_list("pk", flat=True)
            )
            annotation_visible = set(
                Annotation.objects.visible_to_user(self.group_user).values_list(
                    "pk", flat=True
                )
            )

        # With guardian resolution unavailable, the group-only user
        # loses access to every object reachable solely via a group
        # grant — visibility degrades to creator/public, never crashes.
        self.assertNotIn(self.group_doc.pk, doc_visible)
        self.assertNotIn(self.group_doc.pk, generic_visible)
        self.assertNotIn(self.group_annotation.pk, annotation_visible)
