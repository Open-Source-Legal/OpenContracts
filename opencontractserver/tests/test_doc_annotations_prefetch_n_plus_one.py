"""Regression tests for the corpus / folder document-list badge query.

A document list query that asked for ``docAnnotations(annotationLabel_LabelType:
DOC_TYPE_LABEL)`` per edge used to fire one ``COUNT(*)`` + one ``SELECT
annotations_annotation`` + one ``SELECT annotations_annotationlabel`` + one
recursive ``WITH __rank_table`` on ``corpuses_corpus`` (because ``Corpus`` is
registered as a ``TreeNode`` with ``with_tree_fields=True``) **per
document** — ~240 SQL statements / ~20 s on a 24-doc remote RDS+S3 setup.

The frontend never actually read the connection arms (cursors, totalCount,
the nested ``corpus`` field). It only consumed each annotation's
``annotationLabel.{labelType,text}`` to render a per-card badge. The
connection-shape was the wrong shape.

Fix: a flat list field ``DocumentType.docTypeLabels`` consumes the focused
``_prefetched_doc_annotations`` prefetch directly — no ``DjangoFilterConnectionField``,
no per-doc ``COUNT(*)``, no per-doc ``SELECT``. The connection-shaped
``docAnnotations`` field is kept correct (still applies the focused prefetch
when requested) for any external caller that legitimately needs cursor
pagination over a document's annotations.

These tests pin five independent invariants — each catches a different
regression vector:

1. ``SUPPORTED_FILTER_KEYS`` covers every declared ``AnnotationFilter`` filter
   (any unclassified filter would silently force ``resolve_doc_annotations_optimized``
   into the escape-hatch path that bypasses the prefetch — invisible to the
   user but slow).
2. ``docTypeLabels`` SQL count does NOT scale with the document count.
3. The per-document recursive CTE on ``corpuses_corpus`` does NOT scale with
   the document count (the ``CorpusType.get_node`` request cache).
4. The django-guardian anonymous-user lookup fires at most once per request
   (the ``info.context._anon_user_id`` cache in
   ``AnnotatePermissionsForReadMixin``).
5. ``get_anonymous_user_id`` is idempotent after the first call.

If any of these breaks independently, the corresponding speedup quietly
disappears — there's no functional symptom, only a slower query. Each test
exists so the speedup can't bit-rot silently.
"""

from __future__ import annotations

from typing import Any

from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from graphene.test import Client
from graphql_relay import to_global_id

from config.graphql.corpus_types import CorpusType
from config.graphql.custom_resolvers import (
    SUPPORTED_FILTER_KEYS,
    UNSUPPORTED_FILTER_KEYS,
)
from config.graphql.filters import AnnotationFilter
from config.graphql.permissioning.permission_annotator.mixins import (
    get_anonymous_user_id,
)
from config.graphql.schema import schema
from opencontractserver.annotations.models import (
    DOC_TYPE_LABEL,
    Annotation,
    AnnotationLabel,
)
from opencontractserver.tests.base import BaseFixtureTestCase

# The actual shape the frontend sends after the migration to ``docTypeLabels``.
_BADGE_QUERY = """
query (
  $corpusId: String,
  $folderId: String,
  $first: Int!
) {
  documents(
    inCorpusWithId: $corpusId
    inFolderId: $folderId
    includeCaml: true
    first: $first
  ) {
    edges {
      node {
        id
        slug
        title
        docTypeLabels { labelType text }
      }
    }
  }
}
"""


@override_settings(USE_TZ=True)
class DocTypeLabelsBadgeNPlusOneTests(BaseFixtureTestCase):
    """SQL-shape regressions for the corpus document-list badge query."""

    doc_type_label: Any

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()

        # Each fixture document needs a DOC_TYPE_LABEL annotation so the badge
        # query has something non-trivial to render — and so a regression that
        # re-introduces the FK descriptor storm has rows to amplify against.
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
    # docTypeLabels constant query count
    # ------------------------------------------------------------------ #

    def test_doc_type_labels_query_count_is_constant_in_doc_count(self) -> None:
        """``docTypeLabels`` resolution does not fire per-document SQL.

        ``DocumentType.resolve_doc_type_labels`` consumes
        ``_prefetched_doc_annotations`` (loaded in one batch by
        ``_apply_document_prefetches`` when the ``documents`` resolver detects
        ``docTypeLabels`` in the selection via ``requests_doc_type_labels``).
        A regression that loses the prefetch hook-up, the AST detector, or
        the resolver's prefetch-consumption logic re-introduces one
        ``SELECT`` per document — this test catches that by asserting the
        total query count is essentially the same for 1 document as for
        every document the fixture provides.
        """
        result_small, queries_small = self._capture_badge_queries(first=1)
        result_large, queries_large = self._capture_badge_queries(first=len(self.docs))
        self.assertIsNone(result_large.get("errors"), msg=result_large.get("errors"))
        self.assertIsNone(result_small.get("errors"), msg=result_small.get("errors"))

        # Verify the data actually flows — without this, the count check
        # passes vacuously on an empty/erroring result.
        large_edges = result_large["data"]["documents"]["edges"]
        self.assertEqual(len(large_edges), len(self.docs))
        labels0 = large_edges[0]["node"]["docTypeLabels"]
        self.assertEqual(len(labels0), 1)
        self.assertEqual(labels0[0]["text"], "Test Doc Type")
        self.assertEqual(labels0[0]["labelType"], DOC_TYPE_LABEL)

        # Allow a 2-query slack for incidental work that fires once at the
        # start of an N-doc request (e.g. permission-cache warmup); reject
        # any growth that scales with the document count.
        slack = 2
        self.assertLessEqual(
            len(queries_large),
            len(queries_small) + slack,
            msg=(
                f"docTypeLabels query count scales with document count "
                f"(1 doc → {len(queries_small)} queries; {len(self.docs)} docs "
                f"→ {len(queries_large)}). Likely cause: the focused "
                "_prefetched_doc_annotations prefetch was lost (check "
                "_apply_document_prefetches and requests_doc_type_labels), "
                "or DocumentType.resolve_doc_type_labels stopped reading "
                "from the prefetch."
            ),
        )

    # ------------------------------------------------------------------ #
    # Corpus tree-CTE per-row regression
    # ------------------------------------------------------------------ #

    def test_corpus_tree_cte_does_not_scale_with_document_count(self) -> None:
        """``corpuses_corpus`` recursive CTE does not fire per document.

        ``Corpus`` is a ``TreeNode`` registered with ``with_tree_fields=True``,
        so every ``Corpus.objects.get(pk=...)`` emits a recursive
        ``WITH __rank_table`` CTE. Without the ``CorpusType.get_node`` request
        cache, graphene-django's FK resolver fires one such CTE per
        ``annotation.corpus`` FK-access on the legacy ``docAnnotations`` path.

        The new ``docTypeLabels`` shape never traverses ``annotation.corpus``,
        so it cannot exercise the regression. Use the legacy
        ``docAnnotations { corpus { … } }`` shape instead — that's the only
        request shape capable of producing the per-row CTE storm the cache
        protects against.
        """
        legacy_corpus_query = """
        query ($corpusId: String, $first: Int!) {
          documents(inCorpusWithId: $corpusId includeCaml: true first: $first) {
            edges {
              node {
                id
                docAnnotations(annotationLabel_LabelType: DOC_TYPE_LABEL) {
                  edges { node { id corpus { id title } } }
                }
              }
            }
          }
        }
        """

        def _capture_legacy_queries(first: int):
            client = Client(schema)
            with CaptureQueriesContext(connection) as ctx:
                result = client.execute(
                    legacy_corpus_query,
                    variables={
                        "corpusId": to_global_id("CorpusType", self.corpus.pk),
                        "first": first,
                    },
                    context_value=_FakeRequest(self.user),
                )
            return result, list(ctx.captured_queries)

        result_small, queries_small = _capture_legacy_queries(first=1)
        result_large, queries_large = _capture_legacy_queries(first=len(self.docs))
        self.assertIsNone(result_large.get("errors"), msg=result_large.get("errors"))
        self.assertIsNone(result_small.get("errors"), msg=result_small.get("errors"))

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
                "cache. See config/graphql/corpus_types.py."
            ),
        )

    def test_corpus_get_node_is_request_cached(self) -> None:
        """``CorpusType.get_node`` hits the DB once per pk per request.

        Even where the legacy ``annotation.corpus`` access path isn't reached,
        any FK / relay-Node access into ``Corpus`` (e.g. a relay
        ``node(id: <CorpusType:N>)`` directly, or any GraphQL FK pointing at
        ``CorpusType``) routes through ``CorpusType.get_node``. The request
        cache must collapse N calls for the same pk to a single SQL fetch.
        """

        class _Ctx:
            def __init__(self, user) -> None:
                self.user = user

        info = _FakeInfo(_Ctx(self.user))
        with CaptureQueriesContext(connection) as ctx:
            first = CorpusType.get_node(info, self.corpus.pk)
        first_call_queries = len(ctx.captured_queries)
        self.assertIsNotNone(first)

        with CaptureQueriesContext(connection) as ctx2:
            for _ in range(10):
                cached = CorpusType.get_node(info, self.corpus.pk)
                self.assertEqual(cached.pk, first.pk)
        self.assertEqual(
            len(ctx2.captured_queries),
            0,
            msg=(
                "CorpusType.get_node fired SQL on subsequent calls with the "
                f"same pk ({len(ctx2.captured_queries)} queries for 10 calls)."
                " Expected zero — the result must be cached on "
                "info.context._corpus_node_cache."
            ),
        )
        # Sanity check: the first call did at least one query (the actual
        # lookup) — guards against a vacuous pass if the cache short-circuits
        # on a None sentinel that the test then keeps re-checking.
        self.assertGreaterEqual(first_call_queries, 1)

    # ------------------------------------------------------------------ #
    # Anonymous-user lookup caching
    # ------------------------------------------------------------------ #

    def test_anonymous_user_lookup_is_request_cached(self) -> None:
        """``resolve_my_permissions`` hits the anonymous-user row at most once.

        Without the ``info.context._anon_user_id`` cache,
        ``AnnotatePermissionsForReadMixin.resolve_my_permissions`` issues one
        ``SELECT users_user WHERE username = 'AnonymousUser'`` per node in the
        connection (django-guardian's ``get_anonymous_user`` is uncached). The
        regression is silent — permissions still resolve — so it can only be
        caught by counting queries.
        """
        client = Client(schema)
        request = _FakeRequest(self.user)
        query = (
            "query ($corpusId: String, $first: Int!) {"
            "  documents(inCorpusWithId: $corpusId first: $first "
            "includeCaml: true) {"
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
    # Performance comparison print-out (not an assertion)
    # ------------------------------------------------------------------ #

    def test_print_slap_measurement(self) -> None:
        """Run the new ``docTypeLabels`` shape AND the legacy connection
        shape against the fixture; print median query count + wall-clock so
        the speedup is visible on the test output. Not an assertion — the
        other tests in this module pin the actual invariants. This one
        exists to give a single number to point at when discussing the fix.

        Gated by ``OC_PRINT_SLAP_MEASUREMENT=1`` so a normal CI run doesn't
        emit measurement noise on stderr for every invocation.
        """
        import os

        if os.environ.get("OC_PRINT_SLAP_MEASUREMENT") != "1":
            self.skipTest(
                "Set OC_PRINT_SLAP_MEASUREMENT=1 to print measurement output."
            )

        import statistics
        import time

        client = Client(schema)

        new_shape_query = _BADGE_QUERY
        legacy_shape_query = """
        query ($corpusId: String, $folderId: String, $first: Int!) {
          documents(inCorpusWithId: $corpusId inFolderId: $folderId
                    includeCaml: true first: $first) {
            edges {
              node {
                id
                docAnnotations(annotationLabel_LabelType: DOC_TYPE_LABEL) {
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

        variables = {
            "corpusId": to_global_id("CorpusType", self.corpus.pk),
            "folderId": None,
            "first": len(self.docs),
        }

        def _measure(query: str, iterations: int = 5):
            # Warm up — first run may touch lazy imports, schema build.
            client.execute(
                query, variables=variables, context_value=_FakeRequest(self.user)
            )
            counts: list[int] = []
            walls: list[float] = []
            for _ in range(iterations):
                with CaptureQueriesContext(connection) as ctx:
                    t0 = time.perf_counter()
                    result = client.execute(
                        query,
                        variables=variables,
                        context_value=_FakeRequest(self.user),
                    )
                    walls.append((time.perf_counter() - t0) * 1000)
                counts.append(len(ctx.captured_queries))
            errors = result.get("errors") or []
            return counts, walls, errors

        new_counts, new_walls, new_errors = _measure(new_shape_query)
        legacy_counts, legacy_walls, legacy_errors = _measure(legacy_shape_query)

        n = len(self.docs)
        msg = (
            f"\n--- Slap measurement, {n} documents in fixture corpus ---\n"
            f"New shape (docTypeLabels): "
            f"queries median={int(statistics.median(new_counts))} "
            f"min={min(new_counts)} max={max(new_counts)}; "
            f"wall ms median={statistics.median(new_walls):.0f} "
            f"min={min(new_walls):.0f} max={max(new_walls):.0f}; "
            f"errors={len(new_errors)}\n"
            f"Legacy shape (docAnnotations connection): "
            f"queries median={int(statistics.median(legacy_counts))} "
            f"min={min(legacy_counts)} max={max(legacy_counts)}; "
            f"wall ms median={statistics.median(legacy_walls):.0f} "
            f"min={min(legacy_walls):.0f} max={max(legacy_walls):.0f}; "
            f"errors={len(legacy_errors)}\n"
        )
        # Use sys.stderr so the message appears even without ``-s`` when the
        # test is invoked with the default capture mode (pytest only suppresses
        # *passing* tests' stdout).
        import sys

        sys.stderr.write(msg)
        sys.stderr.flush()

    # ------------------------------------------------------------------ #
    # Helper-level coverage
    # ------------------------------------------------------------------ #

    def test_get_anonymous_user_id_caches_on_request(self) -> None:
        """``get_anonymous_user_id`` memoises on ``info.context``."""

        class _Ctx:
            pass

        info = _FakeInfo(_Ctx())
        with CaptureQueriesContext(connection) as ctx:
            anon_id_first = get_anonymous_user_id(info)
        first_lookup_queries = len(ctx.captured_queries)
        with CaptureQueriesContext(connection) as ctx2:
            anon_id_second = get_anonymous_user_id(info)
        self.assertEqual(anon_id_first, anon_id_second)
        self.assertEqual(
            len(ctx2.captured_queries),
            0,
            msg=(
                "Second call to get_anonymous_user_id fired "
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
