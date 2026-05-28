"""Regression tests for the document list ``docAnnotations`` N+1 storm.

A document list query that asks for ``docAnnotations(annotationLabel_LabelType:
DOC_TYPE_LABEL)`` per edge (the corpus list view's "doc-type" badge) used to
fire one ``COUNT(*)``, one ``SELECT annotations_annotation``, one
``SELECT annotations_annotationlabel`` and one recursive ``WITH __rank_table``
on ``corpuses_corpus`` (because ``Corpus`` is registered as a ``TreeNode`` with
``with_tree_fields=True``) *per document*. On a 24-document folder this
produced ~240 SQL statements and ~20 s wall-clock on a remote RDS+S3 setup.

The root cause was a name mismatch between
``config/graphql/custom_resolvers.SUPPORTED_FILTER_KEYS`` (camelCase GraphQL
arg names) and the snake-case Django ORM lookup names that
``DjangoFilterConnectionField`` actually delivers as kwargs — every request
fell into an "extra-key" escape hatch that returned an unfiltered queryset and
defeated the focused ``_prefetched_doc_annotations`` prefetch.

These tests pin three independent invariants that, together, keep the path
fast:

* ``SUPPORTED_FILTER_KEYS`` contains the snake-case Django lookup names so
  every declared ``AnnotationFilter`` field is recognised.
* The per-document recursive CTE on ``corpuses_corpus`` does NOT scale with
  the document count (``CorpusType.get_node`` request cache).
* The django-guardian anonymous-user lookup happens at most once per request
  (``_get_anonymous_user_id`` cache in
  ``AnnotatePermissionsForReadMixin``).

All three break independently if the optimisation regresses, so we assert each
one explicitly rather than capping a single overall query count.
"""

from __future__ import annotations

from typing import Any

from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from graphene.test import Client
from graphql_relay import to_global_id

from config.graphql.custom_resolvers import (
    SUPPORTED_FILTER_KEYS,
    UNSUPPORTED_FILTER_KEYS,
)
from config.graphql.filters import AnnotationFilter
from config.graphql.permissioning.permission_annotator.mixins import (
    _get_anonymous_user_id,
)
from config.graphql.schema import schema
from opencontractserver.annotations.models import (
    DOC_TYPE_LABEL,
    Annotation,
    AnnotationLabel,
)
from opencontractserver.tests.base import BaseFixtureTestCase

_BADGE_QUERY = """
query (
  $corpusId: String,
  $folderId: String,
  $first: Int!,
  $annotateDocLabels: Boolean!,
  $includeCaml: Boolean
) {
  documents(
    inCorpusWithId: $corpusId
    inFolderId: $folderId
    includeCaml: $includeCaml
    first: $first
  ) {
    edges {
      node {
        id
        slug
        title
        doc_label_annotations: docAnnotations(
          annotationLabel_LabelType: DOC_TYPE_LABEL
        ) @include(if: $annotateDocLabels) {
          edges {
            node {
              id
              annotationLabel { labelType text }
              corpus { title icon preferredEmbedder }
            }
          }
        }
      }
    }
  }
}
"""


@override_settings(USE_TZ=True)
class DocAnnotationsBadgeNPlusOneTests(BaseFixtureTestCase):
    """SQL-shape regressions for the corpus document-list badge query."""

    doc_type_label: Any

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()

        # The fixture documents need a DOC_TYPE_LABEL annotation each so the
        # badge query exercises the corpus / annotation_label FK descriptors
        # on every edge. Without per-doc annotations there's nothing for the
        # would-be N+1 to scale against.
        cls.doc_type_label = AnnotationLabel.objects.create(
            text="Test Doc Type",
            label_type=DOC_TYPE_LABEL,
            creator=cls.user,
        )
        for doc in cls.docs:
            Annotation.objects.create(
                document=doc,
                corpus=cls.corpus,
                annotation_label=cls.doc_type_label,
                creator=cls.user,
                raw_text="",
                page=0,
                json={},
            )

    def _execute_badge_query(self, *, first: int) -> Any:
        client = Client(schema)
        return client.execute(
            _BADGE_QUERY,
            variables={
                "corpusId": to_global_id("CorpusType", self.corpus.pk),
                "folderId": None,
                "first": first,
                "annotateDocLabels": True,
                "includeCaml": True,
            },
            context_value=_FakeRequest(self.user),
        )

    def _capture_badge_queries(self, *, first: int):
        with CaptureQueriesContext(connection) as ctx:
            result = self._execute_badge_query(first=first)
        return result, list(ctx.captured_queries)

    # ------------------------------------------------------------------ #
    # SUPPORTED_FILTER_KEYS drift detection
    # ------------------------------------------------------------------ #

    def test_supported_filter_keys_match_annotation_filter(self) -> None:
        """Every ``AnnotationFilter`` declared filter is classified.

        ``DjangoFilterConnectionField`` passes filter kwargs to the resolver
        using ``AnnotationFilter.base_filters`` keys (snake-case Django
        lookups). If a new filter is added to ``AnnotationFilter`` without
        being added to ``SUPPORTED_FILTER_KEYS`` *or*
        ``UNSUPPORTED_FILTER_KEYS``, every request that supplies it will
        silently land in the ``extra``-key escape hatch and re-introduce the
        N+1 — this test fails first.
        """
        declared = set(AnnotationFilter.base_filters.keys())
        classified = SUPPORTED_FILTER_KEYS | UNSUPPORTED_FILTER_KEYS
        unclassified = declared - classified
        self.assertEqual(
            unclassified,
            set(),
            msg=(
                "AnnotationFilter declares filters not classified in "
                "SUPPORTED_FILTER_KEYS / UNSUPPORTED_FILTER_KEYS: "
                f"{sorted(unclassified)}. Add them to whichever of "
                "config/graphql/custom_resolvers.py's two sets matches the "
                "behaviour you want."
            ),
        )

    # ------------------------------------------------------------------ #
    # Corpus tree-CTE per-row regression
    # ------------------------------------------------------------------ #

    def test_corpus_tree_cte_does_not_scale_with_document_count(self) -> None:
        """The badge query must not fire one ``corpuses_corpus`` CTE per doc.

        ``Corpus`` is a ``TreeNode`` registered with ``with_tree_fields=True``,
        so every ``Corpus.objects.get(pk=...)`` emits a recursive
        ``WITH __rank_table`` CTE. Without the ``CorpusType.get_node`` request
        cache, graphene-django's FK resolver fires one such CTE per
        ``annotation.corpus`` access — i.e. once per document edge.
        """
        # Allow a *small* number of corpus tree CTEs (the documents-folder
        # filter and one cache-miss inside the FK resolver), but assert it
        # does NOT scale with the document count.
        result_small, queries_small = self._capture_badge_queries(first=1)
        result_large, queries_large = self._capture_badge_queries(first=len(self.docs))
        self.assertIsNone(result_large.get("errors"), msg=result_large.get("errors"))

        def _count_corpus_ctes(sqls):
            count = 0
            for q in sqls:
                sql = q["sql"]
                if (
                    "__rank_table" in sql
                    and 'corpuses_corpus"' in sql
                    and "corpusfolder" not in sql
                ):
                    count += 1
            return count

        small = _count_corpus_ctes(queries_small)
        large = _count_corpus_ctes(queries_large)
        self.assertLessEqual(
            large,
            small + 2,
            msg=(
                "corpuses_corpus recursive CTE scales with document count "
                f"(1 doc → {small} CTEs; {len(self.docs)} docs → {large}). "
                "Likely cause: CorpusType.get_node lost its per-request id "
                "cache, or AnnotationType.get_queryset stopped applying "
                "select_related('corpus'). See config/graphql/corpus_types.py "
                "and config/graphql/annotation_types.py."
            ),
        )

    # ------------------------------------------------------------------ #
    # Anonymous-user lookup caching
    # ------------------------------------------------------------------ #

    def test_anonymous_user_lookup_is_request_cached(self) -> None:
        """``resolve_my_permissions`` must hit the anonymous-user row once.

        Without the ``info.context._anon_user_id`` cache,
        ``AnnotatePermissionsForReadMixin.resolve_my_permissions`` issues one
        ``SELECT users_user WHERE username = 'AnonymousUser'`` per node in the
        connection (django-guardian's ``get_anonymous_user`` is uncached). The
        regression is silent — permissions still resolve — so it can only be
        caught by counting queries.
        """
        client = Client(schema)
        request = _FakeRequest(self.user)
        # Build a small query that returns ``myPermissions`` per document edge.
        query = (
            "query ($corpusId: String, $first: Int!) {"
            "  documents(inCorpusWithId: $corpusId first: $first includeCaml: true) {"
            "    edges { node { id myPermissions } }"
            "  }"
            "}"
        )
        with CaptureQueriesContext(connection) as ctx:
            result = client.execute(
                query,
                variables={
                    "corpusId": to_global_id("CorpusType", self.corpus.pk),
                    "first": len(self.docs),
                },
                context_value=request,
            )
        self.assertIsNone(result.get("errors"), msg=result.get("errors"))
        anon_username_lookups = sum(
            1
            for q in ctx.captured_queries
            if 'FROM "users_user"' in q["sql"] and "AnonymousUser" in q["sql"]
        )
        self.assertLessEqual(
            anon_username_lookups,
            1,
            msg=(
                f"Anonymous-user lookup fired {anon_username_lookups} times "
                "for a single document-list request. Expected at most 1 "
                "(cached on info.context._anon_user_id). Check "
                "config/graphql/permissioning/permission_annotator/mixins.py."
            ),
        )

    # ------------------------------------------------------------------ #
    # Helper-level coverage
    # ------------------------------------------------------------------ #

    def test_get_anonymous_user_id_caches_on_request(self) -> None:
        """``_get_anonymous_user_id`` must memoise on ``info.context``."""

        class _Ctx:
            pass

        info = _FakeInfo(_Ctx())
        with CaptureQueriesContext(connection) as ctx:
            anon_id_first = _get_anonymous_user_id(info)
        first_lookup_queries = len(ctx.captured_queries)
        with CaptureQueriesContext(connection) as ctx2:
            anon_id_second = _get_anonymous_user_id(info)
        self.assertEqual(anon_id_first, anon_id_second)
        self.assertEqual(
            len(ctx2.captured_queries),
            0,
            msg=(
                "Second call to _get_anonymous_user_id fired "
                f"{len(ctx2.captured_queries)} queries — expected zero "
                "(cached on info.context._anon_user_id)."
            ),
        )
        # Sanity check: the first call ran at least one query (the actual
        # lookup) — guards against the cache short-circuiting on a None
        # sentinel that we'd then keep re-checking.
        self.assertGreaterEqual(first_lookup_queries, 1)


class _FakeRequest:
    """Minimal request object accepted by graphene resolvers + our middleware."""

    def __init__(self, user) -> None:
        self.user = user

    def build_absolute_uri(self, path: str) -> str:
        return path


class _FakeInfo:
    """Minimal stand-in for ``graphene.ResolveInfo`` for unit-level tests."""

    def __init__(self, context: Any) -> None:
        self.context = context
