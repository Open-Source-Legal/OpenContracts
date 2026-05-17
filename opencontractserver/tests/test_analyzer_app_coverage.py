"""Coverage tests for under-tested modules inside ``opencontractserver/analyzer``.

The analyzer app sat at the lowest backend coverage in the repo (~70%).
These tests target the modules the audit flagged as uncovered or
thinly-covered:

  * ``signals.py``        — both signal handlers
  * ``checks.py``         — ``check_unsynced_analyzers`` system check
  * ``startup.py``        — ``sync_analyzers_on_startup``
  * ``admin_views.py``    — ``AnalyzerSyncView`` GET / POST / helpers
  * ``utils.py``          — ``get_gremlin_manifests`` error paths
                            and ``auto_create_doc_analyzers`` edge cases
  * ``management/commands/sync_doc_analyzers.py`` — --dry-run / normal
  * ``views.py``          — ``AnalysisCallbackView`` happy path +
                            ``_create_analysis_notification``
"""

from __future__ import annotations

import io
import logging
from typing import Any
from unittest.mock import MagicMock, patch

import responses
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management import call_command
from django.test import RequestFactory, TestCase, TransactionTestCase
from rest_framework.test import APIRequestFactory

from opencontractserver.analyzer import checks as analyzer_checks
from opencontractserver.analyzer import startup as analyzer_startup
from opencontractserver.analyzer.admin_views import AnalyzerSyncView
from opencontractserver.analyzer.models import Analysis, Analyzer, GremlinEngine
from opencontractserver.analyzer.signals import (
    handle_analysis_completion,
    install_gremlin_on_creation,
)
from opencontractserver.analyzer.utils import (
    auto_create_doc_analyzers,
    get_gremlin_manifests,
)
from opencontractserver.notifications.models import (
    Notification,
    NotificationTypeChoices,
)
from opencontractserver.types.enums import JobStatus

User = get_user_model()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# signals.py
# ---------------------------------------------------------------------------


class InstallGremlinOnCreationTests(TransactionTestCase):
    """``install_gremlin_on_creation`` schedules a Celery chain post-commit."""

    def setUp(self) -> None:
        super().setUp()
        self.user = User.objects.create_user("gremlin_signal_user", password="pw")

    def test_created_true_schedules_on_commit_chain(self) -> None:
        # Capture the ``transaction.on_commit`` callback so we can invoke
        # the chain-assembly lambda synchronously and verify the inner
        # ``request_gremlin_manifest`` → ``install_analyzer_task`` pipeline
        # is wired up correctly without depending on a real Celery broker.
        captured: dict[str, Any] = {}

        with patch("opencontractserver.analyzer.signals.transaction") as mock_tx, patch(
            "opencontractserver.analyzer.signals.request_gremlin_manifest"
        ) as mock_req, patch(
            "opencontractserver.analyzer.signals.install_analyzer_task"
        ) as mock_install, patch(
            "opencontractserver.analyzer.signals.chain"
        ) as mock_chain:
            mock_tx.on_commit = lambda cb: captured.setdefault("cb", cb)
            mock_req.si.return_value = "REQ"
            mock_install.s.return_value = "INSTALL"
            mock_pipeline = MagicMock()
            mock_chain.return_value = mock_pipeline

            install_gremlin_on_creation(
                sender=GremlinEngine, instance=MagicMock(id=99), created=True
            )

            self.assertIn("cb", captured, "handler must register an on_commit callback")
            captured["cb"]()  # Run the chain-assembly lambda.

            mock_req.si.assert_called_with(gremlin_id=99)
            mock_install.s.assert_called_with(gremlin_id=99)
            mock_chain.assert_called()
            mock_pipeline.apply_async.assert_called_once()

    def test_created_false_skips_chain(self) -> None:
        with patch("opencontractserver.analyzer.signals.transaction") as mock_tx, patch(
            "opencontractserver.analyzer.signals.request_gremlin_manifest"
        ) as mock_req, patch(
            "opencontractserver.analyzer.signals.install_analyzer_task"
        ) as mock_install, patch(
            "opencontractserver.analyzer.signals.chain"
        ) as mock_chain:
            mock_tx.on_commit = MagicMock()

            install_gremlin_on_creation(
                sender=GremlinEngine, instance=MagicMock(id=1), created=False
            )
            mock_tx.on_commit.assert_not_called()
            mock_req.si.assert_not_called()
            mock_install.s.assert_not_called()
            mock_chain.assert_not_called()


class HandleAnalysisCompletionTests(TestCase):
    """``handle_analysis_completion`` logs when ``status == 'COMPLETE'``.

    NOTE on string mismatch: ``JobStatus.COMPLETED`` is the enum value
    used in practice (see ``Analysis.status``), but the handler in
    ``signals.py`` checks the literal string ``"COMPLETE"``. The handler
    currently fires only when the caller explicitly assigns the string
    ``"COMPLETE"`` (e.g. tests). This test pins that current behaviour;
    if the production handler is fixed to compare against
    ``JobStatus.COMPLETED.value`` (``"COMPLETED"``), this test should be
    updated to match.
    """

    def test_logs_when_status_is_complete_literal(self) -> None:
        with self.assertLogs("opencontractserver.analyzer.signals", level="INFO") as cm:
            handle_analysis_completion(
                sender=Analysis,
                instance=MagicMock(id=7, status="COMPLETE"),
            )
        self.assertTrue(
            any("Analysis 7 completed" in msg for msg in cm.output),
            f"Expected completion log; got {cm.output!r}",
        )

    def test_silent_when_status_is_completed_enum_value(self) -> None:
        # Documents the known mismatch above — handler doesn't react to the
        # enum value ``"COMPLETED"`` that Analyses actually take. The sentinel
        # must be emitted through the same logger ``assertLogs`` is watching,
        # otherwise ``assertLogs`` raises because nothing landed on that logger.
        signals_logger = logging.getLogger("opencontractserver.analyzer.signals")
        with self.assertLogs("opencontractserver.analyzer.signals", level="INFO") as cm:
            signals_logger.info("sentinel")
            handle_analysis_completion(
                sender=Analysis,
                instance=MagicMock(id=8, status=JobStatus.COMPLETED.value),
            )
        self.assertFalse(
            any("Analysis 8 completed" in msg for msg in cm.output),
            "Handler should not fire for status='COMPLETED' under current logic.",
        )

    def test_silent_when_instance_has_no_status(self) -> None:
        # A bare object with no ``status`` attribute should be a no-op.
        instance = type("Stub", (), {})()  # no .status
        handle_analysis_completion(sender=Analysis, instance=instance)


# ---------------------------------------------------------------------------
# checks.py
# ---------------------------------------------------------------------------


class CheckUnsyncedAnalyzersTests(TestCase):
    """``check_unsynced_analyzers`` emits a Warning per unsync'd task."""

    def test_returns_warning_when_task_not_in_db(self) -> None:
        fake_task = MagicMock()
        fake_task.is_doc_analyzer_task = True

        with patch(
            "opencontractserver.utils.celery_tasks.celery_app"
        ) as mock_celery, patch(
            "opencontractserver.utils.celery_tasks.get_doc_analyzer_task_by_name"
        ) as mock_get, patch(
            "opencontractserver.analyzer.models.Analyzer"
        ) as mock_analyzer:
            mock_celery.tasks = {"some.unsynced.task": fake_task}
            mock_get.return_value = fake_task
            qs = MagicMock()
            qs.exists.return_value = False
            mock_analyzer.objects.filter.return_value = qs

            warnings = analyzer_checks.check_unsynced_analyzers(None)

        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0].id, "analyzer.W001")
        self.assertIn("some.unsynced.task", warnings[0].msg)

    def test_returns_no_warning_when_all_synced(self) -> None:
        fake_task = MagicMock()
        fake_task.is_doc_analyzer_task = True

        with patch(
            "opencontractserver.utils.celery_tasks.celery_app"
        ) as mock_celery, patch(
            "opencontractserver.utils.celery_tasks.get_doc_analyzer_task_by_name"
        ) as mock_get, patch(
            "opencontractserver.analyzer.models.Analyzer"
        ) as mock_analyzer:
            mock_celery.tasks = {"some.synced.task": fake_task}
            mock_get.return_value = fake_task
            qs = MagicMock()
            qs.exists.return_value = True
            mock_analyzer.objects.filter.return_value = qs

            warnings = analyzer_checks.check_unsynced_analyzers(None)

        self.assertEqual(warnings, [])

    def test_swallows_runtime_errors_silently(self) -> None:
        # The ``except Exception`` swallows any failure inside the body;
        # simulate one by having ``celery_app.tasks`` raise on access.
        broken = MagicMock()
        type(broken).tasks = MagicMock(side_effect=RuntimeError("celery exploded"))
        with patch("opencontractserver.utils.celery_tasks.celery_app", new=broken):
            # Function should not raise even if internal access fails.
            warnings = analyzer_checks.check_unsynced_analyzers(None)
        self.assertEqual(warnings, [])

    def test_skips_non_doc_analyzer_tasks(self) -> None:
        with patch(
            "opencontractserver.utils.celery_tasks.celery_app"
        ) as mock_celery, patch(
            "opencontractserver.utils.celery_tasks.get_doc_analyzer_task_by_name"
        ) as mock_get:
            mock_celery.tasks = {"some.regular.task": MagicMock()}
            # Not a doc_analyzer_task → helper returns None
            mock_get.return_value = None

            warnings = analyzer_checks.check_unsynced_analyzers(None)

        self.assertEqual(warnings, [])


# ---------------------------------------------------------------------------
# startup.py
# ---------------------------------------------------------------------------


class SyncAnalyzersOnStartupTests(TestCase):

    def test_calls_auto_create_doc_analyzers(self) -> None:
        with patch(
            "opencontractserver.analyzer.utils.auto_create_doc_analyzers"
        ) as mock_auto:
            analyzer_startup.sync_analyzers_on_startup()
            mock_auto.assert_called_once()

    def test_swallows_exception_and_logs_warning(self) -> None:
        with patch(
            "opencontractserver.analyzer.utils.auto_create_doc_analyzers",
            side_effect=RuntimeError("boom"),
        ), self.assertLogs(
            "opencontractserver.analyzer.startup", level="WARNING"
        ) as cm:
            # Should not propagate the exception
            analyzer_startup.sync_analyzers_on_startup()
        self.assertTrue(
            any("Could not sync analyzers" in msg for msg in cm.output),
            f"Expected warning log; got {cm.output!r}",
        )


# ---------------------------------------------------------------------------
# admin_views.py
# ---------------------------------------------------------------------------


class AnalyzerSyncViewTests(TestCase):

    def setUp(self) -> None:
        super().setUp()
        self.factory = RequestFactory()
        self.staff = User.objects.create_user(
            "sync_view_staff", password="pw", is_staff=True
        )
        self.with_perm = User.objects.create_user(
            "sync_view_with_perm", password="pw", is_staff=True
        )
        perm = Permission.objects.get(codename="add_analyzer")
        self.with_perm.user_permissions.add(perm)

    def test_get_available_analyzers_shape(self) -> None:
        fake_task = MagicMock()
        fake_task.__doc__ = "A docstring"
        fake_task._oc_doc_analyzer_input_schema = {"x": 1}
        fake_task.is_doc_analyzer_task = True

        # Distinct task names without substring overlap so the
        # filter_side_effect can decide exists/missing unambiguously.
        SYNCED = "alpha.task"
        UNSYNCED = "beta.task"
        IRRELEVANT = "gamma.skip_me"

        with patch(
            "opencontractserver.analyzer.admin_views.celery_app"
        ) as mock_celery, patch(
            "opencontractserver.analyzer.admin_views.get_doc_analyzer_task_by_name"
        ) as mock_get, patch(
            "opencontractserver.analyzer.admin_views.Analyzer"
        ) as mock_analyzer:
            mock_celery.tasks = {
                SYNCED: fake_task,
                UNSYNCED: fake_task,
                IRRELEVANT: MagicMock(),
            }
            mock_get.side_effect = lambda name: (
                fake_task if name != IRRELEVANT else None
            )

            def filter_side_effect(*args, **kwargs):
                qs = MagicMock()
                target = kwargs.get("id") or kwargs.get("task_name") or ""
                qs.exists.return_value = target == SYNCED
                return qs

            mock_analyzer.objects.filter.side_effect = filter_side_effect

            view = AnalyzerSyncView()
            rows = view.get_available_analyzers()

        # Only doc_analyzer_tasks are returned; IRRELEVANT is skipped.
        self.assertEqual({r["task_name"] for r in rows}, {SYNCED, UNSYNCED})
        for row in rows:
            self.assertIn("description", row)
            self.assertIn("has_schema", row)
            self.assertIn("exists", row)
        # Sort order: unsynced (False) first, then synced (True).
        self.assertEqual(rows[0]["exists"], False)
        self.assertEqual(rows[-1]["exists"], True)

    def test_post_without_perm_redirects_with_error(self) -> None:
        request = self.factory.post("/admin/analyzer/analyzer/sync/")
        request.user = self.staff  # staff but no add_analyzer perm
        # Attach the message storage required by ``messages.error``
        from django.contrib.messages.storage.fallback import FallbackStorage

        setattr(request, "session", {})
        setattr(request, "_messages", FallbackStorage(request))

        view = AnalyzerSyncView.as_view()
        resp = view(request)
        # Redirects to the changelist with an error message attached.
        self.assertEqual(resp.status_code, 302)

    def test_post_with_perm_invokes_auto_create(self) -> None:
        request = self.factory.post("/admin/analyzer/analyzer/sync/")
        request.user = self.with_perm
        from django.contrib.messages.storage.fallback import FallbackStorage

        setattr(request, "session", {})
        setattr(request, "_messages", FallbackStorage(request))

        with patch(
            "opencontractserver.analyzer.admin_views.auto_create_doc_analyzers"
        ) as mock_auto:
            view = AnalyzerSyncView.as_view()
            resp = view(request)
        mock_auto.assert_called_once()
        self.assertEqual(resp.status_code, 302)


# ---------------------------------------------------------------------------
# utils.py error paths
# ---------------------------------------------------------------------------


class GetGremlinManifestsTests(TransactionTestCase):

    def setUp(self) -> None:
        super().setUp()
        self.user = User.objects.create_user("gremlin_utils_user", password="pw")
        self.gremlin = GremlinEngine.objects.create(
            url="http://gremlin.test", creator=self.user
        )

    @responses.activate
    def test_returns_none_on_http_error(self) -> None:
        responses.add(
            responses.GET,
            self.gremlin.url + "/api/analyzers",
            json={"error": "boom"},
            status=500,
        )
        result = get_gremlin_manifests(self.gremlin.id)
        # On 500 the call .json() succeeds, but ``items`` is missing,
        # so the function will iterate ``None`` and log the error path.
        self.assertIsNone(result)

    @responses.activate
    def test_returns_none_on_malformed_manifest_item(self) -> None:
        # Provide a manifest with items that don't match AnalyzerManifest
        responses.add(
            responses.GET,
            self.gremlin.url + "/api/analyzers",
            json={"items": [{"not_a_real": "field"}]},
            status=200,
        )
        result = get_gremlin_manifests(self.gremlin.id)
        self.assertIsNone(result)

    def test_returns_none_for_unknown_gremlin_id(self) -> None:
        self.assertIsNone(get_gremlin_manifests(999_999))


class AutoCreateDocAnalyzersEdgeCases(TestCase):

    def test_no_users_returns_early(self) -> None:
        # Patch celery_app and the get_doc_analyzer_task_by_name so the
        # iteration body is exercised; UserModel.objects.first() returns
        # None to trigger the early-return path.
        fake_task = MagicMock()
        fake_task.__doc__ = "d"
        fake_task._oc_doc_analyzer_input_schema = None
        fake_task.is_doc_analyzer_task = True

        with patch(
            "opencontractserver.analyzer.utils.celery_app"
        ) as mock_celery, patch(
            "opencontractserver.analyzer.utils.get_doc_analyzer_task_by_name",
            return_value=fake_task,
        ), self.assertLogs(
            "opencontractserver.analyzer.utils", level="WARNING"
        ) as cm:
            mock_celery.tasks = {"any.task": fake_task}
            user_model = MagicMock()
            user_model.objects.filter.return_value.first.return_value = None
            user_model.objects.first.return_value = None
            analyzer_model = MagicMock()
            auto_create_doc_analyzers(
                AnalyzerModel=analyzer_model, UserModel=user_model
            )
        self.assertTrue(any("No user found" in m for m in cm.output))

    def test_celery_app_unavailable_short_circuits(self) -> None:
        with patch("opencontractserver.analyzer.utils.celery_app", None):
            # Should warn and return without crashing.
            with self.assertLogs(
                "opencontractserver.analyzer.utils", level="WARNING"
            ) as cm:
                auto_create_doc_analyzers(
                    AnalyzerModel=MagicMock(), UserModel=MagicMock()
                )
            self.assertTrue(any("Celery or doc_analyzer_task" in m for m in cm.output))

    def test_update_existing_false_skips_update(self) -> None:
        fake_task = MagicMock()
        fake_task.__doc__ = "new docstring"
        fake_task._oc_doc_analyzer_input_schema = {"new": "schema"}
        fake_task.is_doc_analyzer_task = True

        with patch(
            "opencontractserver.analyzer.utils.celery_app"
        ) as mock_celery, patch(
            "opencontractserver.analyzer.utils.get_doc_analyzer_task_by_name",
            return_value=fake_task,
        ):
            mock_celery.tasks = {"some.task": fake_task}

            existing = MagicMock()
            existing.input_schema = {"old": "schema"}
            analyzer_model = MagicMock()
            analyzer_model.DoesNotExist = type("DNE", (Exception,), {})
            analyzer_model.objects.get.return_value = existing
            analyzer_model._meta.get_fields.return_value = [
                MagicMock(name=f) for f in ("input_schema",)
            ]

            user = MagicMock()
            user_model = MagicMock()
            user_model.objects.filter.return_value.first.return_value = user

            auto_create_doc_analyzers(
                AnalyzerModel=analyzer_model,
                UserModel=user_model,
                update_existing=False,
            )

        existing.save.assert_not_called()


# ---------------------------------------------------------------------------
# management/commands/sync_doc_analyzers.py
# ---------------------------------------------------------------------------


class SyncDocAnalyzersCommandTests(TestCase):

    def test_dry_run_does_not_create(self) -> None:
        fake_task = MagicMock(is_doc_analyzer_task=True)
        with patch(
            "opencontractserver.utils.celery_tasks.celery_app"
        ) as mock_celery, patch(
            "opencontractserver.utils.celery_tasks.get_doc_analyzer_task_by_name",
            return_value=fake_task,
        ), patch(
            "opencontractserver.analyzer.management.commands.sync_doc_analyzers."
            "auto_create_doc_analyzers"
        ) as mock_auto:
            mock_celery.tasks = {"x.y.z": fake_task}
            out = io.StringIO()
            call_command("sync_doc_analyzers", dry_run=True, stdout=out)

        mock_auto.assert_not_called()
        self.assertIn("DRY RUN MODE", out.getvalue())

    def test_normal_run_calls_auto_create(self) -> None:
        with patch(
            "opencontractserver.analyzer.management.commands.sync_doc_analyzers."
            "auto_create_doc_analyzers"
        ) as mock_auto:
            out = io.StringIO()
            call_command("sync_doc_analyzers", stdout=out)
        mock_auto.assert_called_once()
        self.assertIn("Successfully synchronized", out.getvalue())


# ---------------------------------------------------------------------------
# views.py — AnalysisCallbackView happy path + notification helper
# ---------------------------------------------------------------------------


class AnalysisCallbackViewHappyPathTests(TransactionTestCase):
    """Exercise the success path of the analysis callback endpoint.

    ``USE_ANALYZER=False`` in default test settings means the
    ``analysis/<int:analysis_id>/complete`` URL is unregistered, so we
    invoke ``AnalysisCallbackView`` directly via ``RequestFactory`` rather
    than relying on URL resolution. Without this approach the test client
    would return 404 silently and the assertions below would pass against
    a no-op.
    """

    def setUp(self) -> None:
        super().setUp()
        from django.conf import settings as dj_settings

        Group.objects.get_or_create(name=dj_settings.DEFAULT_PERMISSIONS_GROUP)
        self.user = User.objects.create_user("callback_user", password="pw")

        # Need a gremlin + analyzer + analysis to receive a callback for.
        self.gremlin = GremlinEngine.objects.create(
            url="http://callback-gremlin.test", creator=self.user
        )
        self.analyzer = Analyzer.objects.create(
            id="callback.analyzer",
            description="x",
            host_gremlin=self.gremlin,
            creator=self.user,
            manifest={},
        )
        self.analysis = Analysis.objects.create(
            analyzer=self.analyzer, creator=self.user
        )

    def _post_callback(self, body: dict, token: str | None) -> Any:
        # ``USE_ANALYZER=False`` in test settings unregisters the URL, so
        # we drive the view directly via ``APIRequestFactory`` instead of
        # going through the resolver. This matches what ``USE_ANALYZER=True``
        # production traffic would land on without forcing every test
        # to flip the feature flag.
        from opencontractserver.analyzer.views import AnalysisCallbackView

        factory = APIRequestFactory()
        headers: dict[str, Any] = {}
        if token is not None:
            headers["HTTP_CALLBACK_TOKEN"] = token
        request = factory.post(
            f"/analysis/{self.analysis.id}/complete",
            body,
            format="json",
            **headers,
        )
        return AnalysisCallbackView.as_view()(request, analysis_id=self.analysis.id)

    def test_valid_callback_with_valid_body_succeeds(self) -> None:
        # Mint plaintext token + persist hash on the Analysis.
        token = self.analysis.rotate_callback_token()
        # Body must conform to ``OpenContractsGeneratedCorpusPythonType``:
        # annotated_docs, doc_labels, text_labels, label_set (all required).
        body: dict[str, Any] = {
            "annotated_docs": {},
            "doc_labels": {},
            "text_labels": {},
            "label_set": {
                "id": "callback-label-set",
                "title": "Callback label set",
                "description": "",
                "icon_data": None,
                "icon_name": "",
                "creator": "callback@test.com",
            },
        }

        with patch(
            "opencontractserver.analyzer.views.import_analysis"
        ) as mock_import, patch(
            "opencontractserver.analyzer.views._create_analysis_notification"
        ) as mock_notif:
            mock_import.si.return_value = MagicMock()
            resp = self._post_callback(body, token)

        self.assertEqual(resp.status_code, 200)
        self.analysis.refresh_from_db()
        self.assertEqual(self.analysis.status, JobStatus.COMPLETED)
        self.assertIsNotNone(self.analysis.analysis_completed)
        self.assertTrue(self.analysis.received_callback_file.name)
        mock_import.si.assert_called_once()
        mock_notif.assert_called_once()
        # First positional arg is the analysis; second kwarg is ``success``.
        call_args = mock_notif.call_args
        self.assertEqual(call_args.kwargs.get("success"), True)

    def test_invalid_body_shape_marks_failed(self) -> None:
        token = self.analysis.rotate_callback_token()
        # Missing required keys → not a valid generated-corpus payload.
        body = {"oops": "not the right shape"}

        with patch(
            "opencontractserver.analyzer.views._create_analysis_notification"
        ) as mock_notif:
            resp = self._post_callback(body, token)

        self.assertEqual(resp.status_code, 400)
        self.analysis.refresh_from_db()
        self.assertEqual(self.analysis.status, JobStatus.FAILED)
        mock_notif.assert_called_once()
        self.assertEqual(mock_notif.call_args.kwargs.get("success"), False)


class CreateAnalysisNotificationTests(TransactionTestCase):
    """Direct unit tests for the notification helper used by the callback."""

    def setUp(self) -> None:
        super().setUp()
        self.user = User.objects.create_user("notif_user", password="pw")
        self.gremlin = GremlinEngine.objects.create(
            url="http://notif-gremlin.test", creator=self.user
        )
        self.analyzer = Analyzer.objects.create(
            id="notif.analyzer",
            description="x",
            host_gremlin=self.gremlin,
            creator=self.user,
            manifest={},
        )
        self.analysis = Analysis.objects.create(
            analyzer=self.analyzer, creator=self.user
        )
        # Wipe any auto-created notifications so we observe only ours.
        Notification.objects.filter(recipient=self.user).delete()

    def test_success_creates_complete_notification(self) -> None:
        from opencontractserver.analyzer import views

        with patch(
            "opencontractserver.analyzer.views.broadcast_notification_via_websocket"
        ) as mock_bcast:
            views._create_analysis_notification(self.analysis, success=True)
        n = Notification.objects.get(recipient=self.user)
        self.assertEqual(n.notification_type, NotificationTypeChoices.ANALYSIS_COMPLETE)
        self.assertEqual(n.data["analysis_id"], self.analysis.id)
        self.assertEqual(n.data["status"], "completed")
        mock_bcast.assert_called_once_with(n)

    def test_failure_creates_failed_notification(self) -> None:
        from opencontractserver.analyzer import views

        with patch(
            "opencontractserver.analyzer.views.broadcast_notification_via_websocket"
        ):
            views._create_analysis_notification(self.analysis, success=False)
        n = Notification.objects.get(recipient=self.user)
        self.assertEqual(n.notification_type, NotificationTypeChoices.ANALYSIS_FAILED)
        self.assertEqual(n.data["status"], "failed")

    def test_swallows_exception_and_logs(self) -> None:
        from opencontractserver.analyzer import views

        with patch(
            "opencontractserver.analyzer.views.Notification.objects.create",
            side_effect=RuntimeError("db down"),
        ), self.assertLogs("opencontractserver.analyzer.views", level="WARNING") as cm:
            # Must NOT propagate the RuntimeError
            views._create_analysis_notification(self.analysis, success=True)
        self.assertTrue(
            any("Failed to create analysis notification" in m for m in cm.output),
            f"Expected warning log; got {cm.output!r}",
        )
