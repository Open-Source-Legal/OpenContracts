"""
Tests for ``DocumentVersionService.get_version_counts_by_tree``.

The method replaces the per-document ``.count()`` pattern in
``resolve_version_count`` (config/graphql/document_types.py) with a single
aggregated query, scoped to documents the user is allowed to read so the
badge cannot leak the existence of hidden versions.

These tests cover:

1. Normal case: each version of a document contributes 1 to its tree count.
2. Multiple trees: trees are independent of each other.
3. Visibility scope: a user only counts versions they can read.
4. Outsider: a user with no permissions sees no counts.
5. Request-level cache: the result is memoised on the request object.
6. Resolver integration: ``resolve_version_count`` collapses to a dict lookup
   after the first call and avoids the per-row ``COUNT(*)``.
"""

import logging
import uuid
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from opencontractserver.documents.models import Document
from opencontractserver.documents.services import DocumentVersionService
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()
logger = logging.getLogger(__name__)


def _make_doc(
    user, *, version_tree_id, title: str, is_current: bool = False
) -> Document:
    """Create a Document for the given version tree.

    Mirrors the lightweight pattern in ``test_extract_iterations._make_doc`` so
    rows exist for aggregation without triggering the full parser pipeline.
    """
    return Document.objects.create(
        title=title,
        description="",
        pdf_file="path/to/x.pdf",
        creator=user,
        version_tree_id=version_tree_id,
        is_current=is_current,
        is_public=False,
    )


class GetVersionCountsByTreeTestCase(TestCase):
    """Verify ``get_version_counts_by_tree`` returns the expected counts."""

    def setUp(self):
        self.owner = User.objects.create_user(username="versions_owner", password="x")
        self.outsider = User.objects.create_user(
            username="versions_outsider", password="x"
        )

        # Tree A: 3 versions, all owned and visible to ``self.owner``.
        self.tree_a = uuid.uuid4()
        self.a_v1 = _make_doc(
            self.owner, version_tree_id=self.tree_a, title="a_v1", is_current=False
        )
        self.a_v2 = _make_doc(
            self.owner, version_tree_id=self.tree_a, title="a_v2", is_current=False
        )
        self.a_v3 = _make_doc(
            self.owner, version_tree_id=self.tree_a, title="a_v3", is_current=True
        )

        # Tree B: 2 versions, owned by ``self.owner``.
        self.tree_b = uuid.uuid4()
        self.b_v1 = _make_doc(
            self.owner, version_tree_id=self.tree_b, title="b_v1", is_current=False
        )
        self.b_v2 = _make_doc(
            self.owner, version_tree_id=self.tree_b, title="b_v2", is_current=True
        )

    def test_returns_one_count_per_tree(self):
        """Each version contributes 1 to its tree's count."""
        counts = DocumentVersionService.get_version_counts_by_tree(
            user=self.owner,
        )
        self.assertEqual(counts.get(self.tree_a), 3)
        self.assertEqual(counts.get(self.tree_b), 2)

    def test_outsider_sees_no_counts(self):
        """A user with no permissions sees no counts (and no leak)."""
        counts = DocumentVersionService.get_version_counts_by_tree(
            user=self.outsider,
        )
        self.assertEqual(counts.get(self.tree_a, 0), 0)
        self.assertEqual(counts.get(self.tree_b, 0), 0)

    def test_partial_visibility_only_counts_visible_versions(self):
        """
        A user who can see only a subset of versions in a tree should get a
        count limited to the visible subset — the badge must not leak the
        existence of hidden versions.
        """
        partial_user = User.objects.create_user(
            username="versions_partial", password="x"
        )
        # Grant READ on only one version of tree A.
        set_permissions_for_obj_to_user(partial_user, self.a_v3, [PermissionTypes.READ])

        counts = DocumentVersionService.get_version_counts_by_tree(
            user=partial_user,
        )
        self.assertEqual(counts.get(self.tree_a, 0), 1)
        # Tree B is invisible entirely.
        self.assertEqual(counts.get(self.tree_b, 0), 0)

    def test_superuser_sees_all_versions(self):
        """Superusers bypass visibility filtering."""
        superuser = User.objects.create_superuser(
            username="versions_super", password="x", email="s@example.com"
        )
        counts = DocumentVersionService.get_version_counts_by_tree(
            user=superuser,
        )
        self.assertEqual(counts.get(self.tree_a), 3)
        self.assertEqual(counts.get(self.tree_b), 2)

    def test_request_level_cache_returns_same_result(self):
        """A second call with the same request should return the cached dict."""
        request = SimpleNamespace()
        first = DocumentVersionService.get_version_counts_by_tree(
            user=self.owner, request=request
        )
        # Mutate the underlying data to confirm the cache is being hit.
        Document.objects.filter(pk=self.a_v3.pk).delete()

        second = DocumentVersionService.get_version_counts_by_tree(
            user=self.owner, request=request
        )
        self.assertIs(first, second)
        # Cached value still reflects pre-deletion count.
        self.assertEqual(second.get(self.tree_a), 3)


class ResolveVersionCountIntegrationTestCase(TestCase):
    """
    End-to-end test that ``resolve_version_count`` no longer issues one
    ``COUNT(*)`` per document when called for many documents in the same
    request (simulating a paginated GraphQL connection).
    """

    def setUp(self):
        self.owner = User.objects.create_user(username="resolver_owner", password="x")
        # Build 5 trees with 3 versions each.
        self.trees = [uuid.uuid4() for _ in range(5)]
        self.docs: list[Document] = []
        for tree_idx, tree_id in enumerate(self.trees):
            for v in range(3):
                doc = _make_doc(
                    self.owner,
                    version_tree_id=tree_id,
                    title=f"t{tree_idx}_v{v}",
                    is_current=(v == 2),
                )
                self.docs.append(doc)

    def test_resolver_amortises_over_request(self):
        """
        Calling ``resolve_version_count`` on 15 documents with a shared
        ``info.context`` should perform the aggregation once — subsequent
        resolutions are dict lookups against the cached result.
        """
        from config.graphql.document_types import DocumentType

        # Fake an ``info`` object whose ``.context`` is a writable namespace,
        # mirroring what graphene provides during a GraphQL request.
        info = SimpleNamespace(context=SimpleNamespace(user=self.owner))

        # First call populates the cache.
        first = DocumentType.resolve_version_count(self.docs[0], info)
        self.assertEqual(first, 3)

        # Subsequent calls must not issue any version_tree_id queries — the
        # batched aggregation already populated the per-request cache.
        with CaptureQueriesContext(connection) as captured:
            results = [
                DocumentType.resolve_version_count(doc, info) for doc in self.docs[1:]
            ]
        self.assertTrue(all(r == 3 for r in results))
        version_tree_queries = [
            q["sql"] for q in captured.captured_queries if "version_tree_id" in q["sql"]
        ]
        self.assertEqual(
            version_tree_queries,
            [],
            "Expected no version_tree_id queries on cached calls, "
            f"got: {version_tree_queries}",
        )

    def test_resolver_falls_back_to_one_for_unknown_tree(self):
        """
        A document whose tree is absent from the cache (e.g. invisible to the
        user but somehow reachable from the parent resolver) should resolve
        to 1 — never 0, since the document itself is at minimum one version.
        """
        from config.graphql.document_types import DocumentType

        info = SimpleNamespace(context=SimpleNamespace(user=self.owner))
        # Pre-populate the service's cache with only an unrelated tree so
        # the lookup for self.docs[0].version_tree_id misses and falls back
        # to the default of 1.
        cache_key = f"_doc_version_counts_by_tree_{self.owner.id}"
        setattr(info.context, cache_key, {uuid.uuid4(): 99})

        result = DocumentType.resolve_version_count(self.docs[0], info)
        self.assertEqual(result, 1)
