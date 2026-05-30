"""Unit tests for the Phase 1 service-layer foundation.

Covers ``ServiceResult`` (no DB), ``get_for_user_or_none`` (DB), and
``BaseService`` (DB). See
docs/refactor_plans/2026-05-19-service-layer-phase1-foundation-plan.md.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from opencontractserver.corpuses.models import Corpus
from opencontractserver.shared.services.base import BaseService
from opencontractserver.shared.services.conventions import (
    ServiceResult,
    get_for_user_or_none,
)
from opencontractserver.types.enums import PermissionTypes

User = get_user_model()


class TestServiceResult(SimpleTestCase):
    """SCENARIO: ServiceResult is the uniform write-operation envelope.

    BUSINESS RULE: a result is successful exactly when its error string is
    empty; it also tuple-unpacks to ``(value, error)`` so legacy callers
    written against the ``(obj, error)`` convention keep working.
    """

    def test_success_has_value_and_is_ok(self):
        result = ServiceResult.success(42)
        self.assertEqual(result.value, 42)
        self.assertEqual(result.error, "")
        self.assertTrue(result.ok)

    def test_failure_has_error_and_is_not_ok(self):
        result = ServiceResult.failure("boom")
        self.assertIsNone(result.value)
        self.assertEqual(result.error, "boom")
        self.assertFalse(result.ok)

    def test_failure_rejects_empty_error(self):
        with self.assertRaises(ValueError):
            ServiceResult.failure("")

    def test_tuple_unpacking_yields_value_then_error(self):
        value, error = ServiceResult.success("doc")
        self.assertEqual(value, "doc")
        self.assertEqual(error, "")
        value, error = ServiceResult.failure("nope")
        self.assertIsNone(value)
        self.assertEqual(error, "nope")


class TestGetForUserOrNone(TestCase):
    """SCENARIO: get_for_user_or_none is the IDOR-safe single-object lookup.

    BUSINESS RULE: it returns the instance only when it exists AND the user
    holds the requested permission. Every other case — not-found,
    permission-denied, malformed pk — returns None, so a caller cannot
    distinguish "does not exist" from "exists but forbidden".
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner", email="owner@test.com", password="test"
        )
        self.other = User.objects.create_user(
            username="other", email="other@test.com", password="test"
        )
        self.corpus = Corpus.objects.create(
            title="Owned Corpus", creator=self.owner, is_public=False
        )

    def test_owner_gets_instance(self):
        result = get_for_user_or_none(Corpus, self.corpus.pk, self.owner)
        self.assertEqual(result, self.corpus)

    def test_other_user_gets_none(self):
        result = get_for_user_or_none(Corpus, self.corpus.pk, self.other)
        self.assertIsNone(result)

    def test_nonexistent_pk_gets_none(self):
        result = get_for_user_or_none(Corpus, 999999999, self.owner)
        self.assertIsNone(result)

    def test_malformed_pk_gets_none(self):
        result = get_for_user_or_none(Corpus, "not-a-pk", self.owner)
        self.assertIsNone(result)

    def test_overflow_pk_gets_none(self):
        # A pk far larger than the IntegerField column can hold raises
        # OverflowError on .get(); it must be treated as not-found.
        result = get_for_user_or_none(Corpus, 99999999999999999999999999, self.owner)
        self.assertIsNone(result)

    def test_anonymous_user_gets_none_for_private_corpus(self):
        from django.contrib.auth.models import AnonymousUser

        result = get_for_user_or_none(Corpus, self.corpus.pk, AnonymousUser())
        self.assertIsNone(result)

    def test_none_user_gets_none_for_private_corpus(self):
        result = get_for_user_or_none(Corpus, self.corpus.pk, None)
        self.assertIsNone(result)

    def test_permission_argument_is_honored(self):
        # Owner has full CRUD on their own corpus, so UPDATE also resolves.
        result = get_for_user_or_none(
            Corpus, self.corpus.pk, self.owner, PermissionTypes.UPDATE
        )
        self.assertEqual(result, self.corpus)


class TestBaseServiceLookup(TestCase):
    """SCENARIO: BaseService exposes the shared fetch primitives.

    BUSINESS RULE: ``get_or_none`` is the IDOR-safe single-object lookup
    and ``filter_visible`` returns the permission-filtered queryset — both
    delegate to the existing manager API so a subclass never re-implements
    permission logic.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username="bs_owner", email="bs_owner@test.com", password="test"
        )
        self.other = User.objects.create_user(
            username="bs_other", email="bs_other@test.com", password="test"
        )
        self.corpus = Corpus.objects.create(
            title="BaseService Corpus", creator=self.owner, is_public=False
        )

    def test_get_or_none_returns_instance_for_owner(self):
        self.assertEqual(
            BaseService.get_or_none(Corpus, self.corpus.pk, self.owner),
            self.corpus,
        )

    def test_get_or_none_returns_none_for_other_user(self):
        self.assertIsNone(BaseService.get_or_none(Corpus, self.corpus.pk, self.other))

    def test_filter_visible_includes_owned_corpus(self):
        visible_ids = set(
            BaseService.filter_visible(Corpus, self.owner).values_list("pk", flat=True)
        )
        self.assertIn(self.corpus.pk, visible_ids)

    def test_filter_visible_excludes_corpus_for_other_user(self):
        visible_ids = set(
            BaseService.filter_visible(Corpus, self.other).values_list("pk", flat=True)
        )
        self.assertNotIn(self.corpus.pk, visible_ids)

    def test_filter_visible_qs_preserves_incoming_filter(self):
        """``filter_visible_qs`` must intersect with prior filters in one pass.

        Issue #1782 regression: the legacy
        ``filter_visible(...).values('pk') | queryset.filter(pk__in=...)``
        pattern produced a correlated subquery over the full model table.
        ``filter_visible_qs`` chains the queryset's own ``visible_to_user``
        method, keeping the visibility predicate in the same WHERE tree as
        any prior ``.filter(...)`` clauses on the incoming queryset.
        """
        # Another corpus owned by the same user — would be returned by an
        # unfiltered ``visible_to_user`` query but must be excluded by the
        # incoming ``.filter(pk=...)`` clause we chain onto.
        other_corpus = Corpus.objects.create(
            title="Other Owned Corpus", creator=self.owner, is_public=False
        )

        prefiltered = Corpus.objects.filter(pk=self.corpus.pk)
        result = BaseService.filter_visible_qs(prefiltered, self.owner)

        # The pre-filter survives: exactly the corpus we asked for,
        # not the other one the user can see.
        self.assertEqual(list(result), [self.corpus])
        self.assertNotIn(other_corpus, result)

        # And the visibility filter is a single SQL pass: the compiled
        # query references the corpus table no more times than the
        # baseline queryset already does. The legacy
        # ``pk__in=<filter_visible.values('pk')>`` pattern added an extra
        # ``IN (SELECT … FROM corpuses_corpus …)`` subquery — an extra
        # full-table scan on top of the baseline. ``filter_visible_qs``
        # chains the queryset's own ``visible_to_user``, so the FROM count
        # against the model's own table must match the baseline (subqueries
        # against guardian permission tables are fine and expected).
        #
        # Comparing against the baseline rather than asserting an absolute
        # count keeps the test robust to model-level concerns like
        # django-tree-queries' recursive CTE, which adds its own FROM
        # reference to the corpus table irrespective of visibility logic.
        #
        # ``str(queryset.query)`` renders parameterized SQL via Django's
        # internal ``Query.as_sql()`` rather than the exact string the DB
        # backend receives. The output format is stable within a Django
        # minor version but has changed subtly across majors. Re-verify on
        # any Django major upgrade — if the quoting or alias style shifts,
        # both ``baseline_from_count`` and ``result_from_count`` should
        # shift in lockstep, so the *equality* assertion stays valid even
        # when the absolute counts move. The test fails loudly here rather
        # than silently if that ever stops being true.
        corpus_table = Corpus._meta.db_table
        baseline_from_count = str(prefiltered.query).count(f'FROM "{corpus_table}"')
        result_from_count = str(result.query).count(f'FROM "{corpus_table}"')
        self.assertEqual(
            result_from_count,
            baseline_from_count,
            f"filter_visible_qs added {result_from_count - baseline_from_count} "
            f"extra FROM(s) against {corpus_table!r} on top of the baseline "
            f"({baseline_from_count}). Compiled SQL: {result.query}",
        )

    def test_filter_visible_qs_excludes_other_user(self):
        """The ownership filter excludes objects owned by a different user."""
        prefiltered = Corpus.objects.filter(pk=self.corpus.pk)
        result = BaseService.filter_visible_qs(prefiltered, self.other)
        self.assertNotIn(self.corpus, result)

    def test_filter_visible_qs_rejects_exotic_input(self):
        """Inputs without ``visible_to_user`` now fail CLOSED (raise).

        Real callers always pass a QuerySet or RelatedManager — both expose
        ``visible_to_user``. An input that lacks it is a wiring bug, and a
        permission gate must surface that loudly rather than returning the
        rows unfiltered: the previous pass-through behaviour was fail-open
        and could silently leak every row if a non-permissioned shape
        (prefetched cache, custom proxy, plain list) ever reached it.
        """

        class _Exotic:
            pass

        with self.assertRaises(TypeError):
            BaseService.filter_visible_qs(_Exotic(), self.owner)


class TestBaseServiceRequirePermission(TestCase):
    """SCENARIO: require_permission is the uniform write-operation gate.

    BUSINESS RULE: it returns an empty string when the user holds the
    permission, and a human-readable denial string otherwise — so a
    service can feed the return value straight into ServiceResult.failure.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username="rp_owner", email="rp_owner@test.com", password="test"
        )
        self.other = User.objects.create_user(
            username="rp_other", email="rp_other@test.com", password="test"
        )
        self.corpus = Corpus.objects.create(
            title="RequirePermission Corpus", creator=self.owner, is_public=False
        )

    def test_owner_passes_returns_empty_string(self):
        error = BaseService.require_permission(
            self.corpus, self.owner, PermissionTypes.UPDATE
        )
        self.assertEqual(error, "")

    def test_other_user_denied_returns_nonempty_error(self):
        error = BaseService.require_permission(
            self.corpus, self.other, PermissionTypes.UPDATE
        )
        # Pin the denial-string format contract, not just the substring.
        self.assertTrue(
            error.startswith("Permission denied: cannot "),
            f"unexpected denial string format: {error!r}",
        )
        self.assertIn("Corpus", error)

    def test_custom_error_message_is_used_on_denial(self):
        error = BaseService.require_permission(
            self.corpus,
            self.other,
            PermissionTypes.UPDATE,
            error_message="You cannot edit this corpus",
        )
        self.assertEqual(error, "You cannot edit this corpus")

    def test_custom_error_message_ignored_on_success(self):
        error = BaseService.require_permission(
            self.corpus,
            self.owner,
            PermissionTypes.UPDATE,
            error_message="You cannot edit this corpus",
        )
        self.assertEqual(error, "")


class TestBaseServiceLogAction(TestCase):
    """SCENARIO: log_action emits a structured who-did-what log line.

    BUSINESS RULE: every service mutation logs the action, the object, and
    the acting user in one consistent format.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            username="log_owner", email="log_owner@test.com", password="test"
        )
        self.corpus = Corpus.objects.create(
            title="Log Corpus", creator=self.owner, is_public=False
        )

    def test_log_action_emits_info_line_with_action_model_and_user(self):
        with self.assertLogs(
            "opencontractserver.shared.services.base", level="INFO"
        ) as captured:
            BaseService.log_action("Created", self.corpus, self.owner)
        joined = "\n".join(captured.output)
        self.assertIn("Created", joined)
        self.assertIn("Corpus", joined)
        self.assertIn(str(self.corpus.pk), joined)
        self.assertIn(str(self.owner.id), joined)

    def test_log_action_includes_extra_kwargs(self):
        with self.assertLogs(
            "opencontractserver.shared.services.base", level="INFO"
        ) as captured:
            BaseService.log_action("Updated", self.corpus, self.owner, field="title")
        self.assertIn("field='title'", "\n".join(captured.output))


class TestServicesPackageExports(SimpleTestCase):
    """SCENARIO: the package root re-exports the shared building blocks.

    BUSINESS RULE: callers import from the package
    (``from opencontractserver.shared.services import BaseService``) so the
    individual module layout can change without breaking imports.
    """

    def test_package_reexports_public_names(self):
        from opencontractserver.shared.services import (
            BaseService as ExportedBaseService,
        )
        from opencontractserver.shared.services import (
            ServiceResult as ExportedServiceResult,
        )
        from opencontractserver.shared.services import (
            get_for_user_or_none as exported_lookup,
        )

        self.assertIs(ExportedBaseService, BaseService)
        self.assertIs(ExportedServiceResult, ServiceResult)
        self.assertTrue(callable(exported_lookup))
