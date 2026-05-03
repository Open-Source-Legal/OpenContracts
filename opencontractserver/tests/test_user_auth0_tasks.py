"""
Tests for ``opencontractserver.users.tasks``.

These tasks shuttle data between Auth0 and the local user table:

* ``get_new_auth0_token`` - request a Management API token
* ``ensure_valid_auth0_token`` - reuse a still-live token, otherwise request one
* ``get_user_details_async`` - fetch the remote profile for a user
* ``apply_data_to_user`` - copy that profile onto the local row
* ``sync_remote_user`` - orchestrate the chain of the above

All outbound HTTP is mocked. The tests are gated on ``settings.USE_AUTH0`` so
they only run in environments where the Celery task module is registered.
"""

from __future__ import annotations

import datetime
import importlib
from types import ModuleType
from typing import Any, ClassVar
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from opencontractserver.users.models import Auth0APIToken

User = get_user_model()


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


@override_settings(USE_AUTH0=True)
class Auth0TasksTestCase(TestCase):
    """Cover the post-PR-1499 simplified Auth0 task pipeline.

    ``opencontractserver.users.tasks`` defines its task functions inside an
    ``if settings.USE_AUTH0:`` guard at module load. The default test settings
    disable Auth0, so we reload the module under ``USE_AUTH0=True`` to make
    the task callables available, then restore the original module on teardown.
    """

    tasks: ClassVar[ModuleType]
    _settings_override: ClassVar[Any]

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from django.test.utils import override_settings as _override

        # Reload tasks.py with USE_AUTH0=True so the task functions are defined.
        cls._settings_override = _override(USE_AUTH0=True)
        cls._settings_override.enable()
        from opencontractserver.users import tasks as _tasks

        cls.tasks = importlib.reload(_tasks)

    @classmethod
    def tearDownClass(cls):
        # Restore the original module + setting state.
        from opencontractserver.users import tasks as _tasks

        importlib.reload(_tasks)
        cls._settings_override.disable()
        super().tearDownClass()

    def setUp(self):
        Auth0APIToken.objects.all().delete()
        self.user = User.objects.create_user(
            username="auth0|tasks_user",
            email="prev@example.com",
            email_verified=False,
        )

    # ------------------------------------------------------------------
    # get_new_auth0_token
    # ------------------------------------------------------------------
    def test_get_new_auth0_token_persists_token(self):
        tasks = self.tasks

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "fresh-token-abc",
            "expires_in": 3600,
        }

        with patch.object(tasks.requests, "post", return_value=mock_response) as post:
            result = tasks.get_new_auth0_token.run()

        self.assertEqual(result, "fresh-token-abc")
        # Ensure timeout was passed to the outbound request (no hanging workers).
        self.assertEqual(post.call_args.kwargs["timeout"], tasks.AUTH0_HTTP_TIMEOUT)
        row = Auth0APIToken.objects.get()
        self.assertEqual(row.token, "fresh-token-abc")
        self.assertGreater(row.expiration_Date, _utcnow())

    def test_get_new_auth0_token_request_exception_returns_none(self):
        tasks = self.tasks

        with patch.object(
            tasks.requests, "post", side_effect=tasks.requests.RequestException("boom")
        ):
            result = tasks.get_new_auth0_token.run()

        self.assertIsNone(result)
        self.assertFalse(Auth0APIToken.objects.exists())

    def test_get_new_auth0_token_non_200_returns_none(self):
        tasks = self.tasks

        mock_response = MagicMock()
        mock_response.status_code = 401
        with patch.object(tasks.requests, "post", return_value=mock_response):
            self.assertIsNone(tasks.get_new_auth0_token.run())
        self.assertFalse(Auth0APIToken.objects.exists())

    def test_get_new_auth0_token_malformed_payload_returns_none(self):
        tasks = self.tasks

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"oops": "no_access_token"}

        with patch.object(tasks.requests, "post", return_value=mock_response):
            self.assertIsNone(tasks.get_new_auth0_token.run())
        self.assertFalse(Auth0APIToken.objects.exists())

    def test_get_new_auth0_token_replaces_existing_rows_atomically(self):
        tasks = self.tasks

        # Seed a stale row that should be deleted.
        Auth0APIToken.objects.create(
            token="stale", expiration_Date=_utcnow() - datetime.timedelta(hours=1)
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "replacement",
            "expires_in": 60,
        }

        with patch.object(tasks.requests, "post", return_value=mock_response):
            tasks.get_new_auth0_token.run()

        rows = list(Auth0APIToken.objects.all())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].token, "replacement")

    # ------------------------------------------------------------------
    # ensure_valid_auth0_token
    # ------------------------------------------------------------------
    def test_ensure_valid_returns_existing_live_token(self):
        tasks = self.tasks

        Auth0APIToken.objects.create(
            token="still-good",
            expiration_Date=_utcnow() + datetime.timedelta(minutes=30),
        )

        with patch.object(tasks, "get_new_auth0_token") as new_token:
            result = tasks.ensure_valid_auth0_token.run()

        self.assertEqual(result, "still-good")
        # Crucially: do NOT block the worker via delay().get(); never even fall
        # back to fetching when a live token exists.
        new_token.run.assert_not_called()
        new_token.delay.assert_not_called()

    def test_ensure_valid_fetches_new_when_none_live(self):
        """No live token => fetch synchronously (not via delay().get())."""
        tasks = self.tasks

        # Expired row should be ignored and a fresh fetch issued.
        Auth0APIToken.objects.create(
            token="expired",
            expiration_Date=_utcnow() - datetime.timedelta(minutes=1),
        )

        # Patch the underlying ``run`` so we can assert it's used instead of
        # ``delay().get()``. ``delay`` would block the worker under saturation.
        with patch.object(
            tasks.get_new_auth0_token, "run", return_value="brand-new"
        ) as run_call, patch.object(tasks.get_new_auth0_token, "delay") as delay_call:
            result = tasks.ensure_valid_auth0_token.run()

        self.assertEqual(result, "brand-new")
        run_call.assert_called_once()
        delay_call.assert_not_called()

    # ------------------------------------------------------------------
    # get_user_details_async
    # ------------------------------------------------------------------
    def test_get_user_details_no_token_returns_empty(self):
        tasks = self.tasks

        self.assertEqual(tasks.get_user_details_async.run(None, "auth0|abc"), {})
        self.assertEqual(tasks.get_user_details_async.run("", "auth0|abc"), {})

    def test_get_user_details_url_encodes_pipe_in_sub(self):
        tasks = self.tasks

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"email": "ok@example.com"}

        with patch.object(tasks.requests, "get", return_value=mock_response) as get:
            tasks.get_user_details_async.run("token", "auth0|abc/def")

        url = get.call_args.args[0]
        # ``|`` and ``/`` must be percent-encoded so the API path is well formed.
        self.assertIn("auth0%7Cabc%2Fdef", url)
        self.assertNotIn("auth0|abc/def", url)
        # Bearer scheme + timeout enforced.
        self.assertEqual(
            get.call_args.kwargs["headers"]["Authorization"], "Bearer token"
        )
        self.assertEqual(get.call_args.kwargs["timeout"], tasks.AUTH0_HTTP_TIMEOUT)

    def test_get_user_details_request_exception_returns_empty(self):
        tasks = self.tasks

        with patch.object(
            tasks.requests, "get", side_effect=tasks.requests.RequestException("boom")
        ):
            self.assertEqual(tasks.get_user_details_async.run("t", "auth0|x"), {})

    def test_get_user_details_non_200_returns_empty(self):
        tasks = self.tasks

        mock_response = MagicMock()
        mock_response.status_code = 500
        with patch.object(tasks.requests, "get", return_value=mock_response):
            self.assertEqual(tasks.get_user_details_async.run("t", "auth0|x"), {})

    def test_get_user_details_invalid_json_returns_empty(self):
        tasks = self.tasks

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("nope")
        with patch.object(tasks.requests, "get", return_value=mock_response):
            self.assertEqual(tasks.get_user_details_async.run("t", "auth0|x"), {})

    # ------------------------------------------------------------------
    # apply_data_to_user
    # ------------------------------------------------------------------
    def test_apply_data_skips_empty(self):
        tasks = self.tasks

        tasks.apply_data_to_user.run(None, self.user.username)
        tasks.apply_data_to_user.run({}, self.user.username)
        # Not a dict either.
        tasks.apply_data_to_user.run("oops", self.user.username)

        self.user.refresh_from_db()
        self.assertFalse(self.user.synced)
        self.assertEqual(self.user.email, "prev@example.com")

    def test_apply_data_skips_unknown_user(self):
        tasks = self.tasks

        # Should not raise.
        tasks.apply_data_to_user.run({"email": "x@y.z"}, "no-such-user")

    def test_apply_data_already_synced_is_noop(self):
        tasks = self.tasks

        self.user.synced = True
        self.user.save()

        tasks.apply_data_to_user.run(
            {"email": "newer@example.com", "email_verified": True},
            self.user.username,
        )
        self.user.refresh_from_db()
        # email kept, since synced gates the write.
        self.assertEqual(self.user.email, "prev@example.com")

    def test_apply_data_writes_with_defaults(self):
        tasks = self.tasks

        tasks.apply_data_to_user.run(
            {
                "email": "verified@example.com",
                "email_verified": True,
                "name": "Anne Verified",
                "given_name": "Anne",
                "family_name": "Verified",
                "last_ip": "203.0.113.7",
            },
            self.user.username,
        )

        self.user.refresh_from_db()
        self.assertTrue(self.user.synced)
        self.assertTrue(self.user.is_social_user)
        self.assertTrue(self.user.email_verified)
        self.assertTrue(self.user.is_active)
        self.assertEqual(self.user.email, "verified@example.com")
        self.assertEqual(self.user.name, "Anne Verified")
        self.assertEqual(self.user.given_name, "Anne")
        self.assertEqual(self.user.family_name, "Verified")
        self.assertEqual(self.user.last_ip, "203.0.113.7")
        # last_synced is timezone-aware (post-PR fix).
        last_synced = self.user.last_synced
        assert last_synced is not None  # narrows for mypy + clearer than assertIsNotNone
        self.assertIsNotNone(last_synced.tzinfo)

    def test_apply_data_unverified_email_disables_account(self):
        tasks = self.tasks

        tasks.apply_data_to_user.run(
            {"email": "unverified@example.com", "email_verified": False},
            self.user.username,
        )

        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)
        self.assertFalse(self.user.email_verified)
        self.assertEqual(self.user.email, "unverified@example.com")

    def test_apply_data_uses_get_with_defaults_for_optional_fields(self):
        """``.get()`` defaults guard against KeyError on partial payloads."""
        tasks = self.tasks

        tasks.apply_data_to_user.run(
            {"email_verified": True},  # only one field present
            self.user.username,
        )

        self.user.refresh_from_db()
        # Existing email kept (default fall-through).
        self.assertEqual(self.user.email, "prev@example.com")
        self.assertEqual(self.user.name, "")
        self.assertEqual(self.user.given_name, "")
        self.assertEqual(self.user.family_name, "")

    # ------------------------------------------------------------------
    # sync_remote_user
    # ------------------------------------------------------------------
    def test_sync_remote_user_uses_existing_live_token(self):
        """A live token must be reused (no token-fetch link in the chain)."""
        tasks = self.tasks

        Auth0APIToken.objects.create(
            token="reusable",
            expiration_Date=_utcnow() + datetime.timedelta(minutes=10),
        )

        with patch.object(tasks, "chain") as chain_mock:
            chain_mock.return_value.apply_async.return_value = "async-result"
            result = tasks.sync_remote_user.run(self.user.username)

        self.assertEqual(result, "async-result")
        # Two-step chain: get_user_details_async + apply_data_to_user.
        args, _ = chain_mock.call_args
        self.assertEqual(len(args), 2)

    def test_sync_remote_user_fetches_token_when_none_live(self):
        """No live token => three-step chain that fetches a token first."""
        tasks = self.tasks

        # Only an expired row is present, which must be ignored.
        Auth0APIToken.objects.create(
            token="dead",
            expiration_Date=_utcnow() - datetime.timedelta(minutes=1),
        )

        with patch.object(tasks, "chain") as chain_mock:
            chain_mock.return_value.apply_async.return_value = "async-result"
            tasks.sync_remote_user.run(self.user.username)

        args, _ = chain_mock.call_args
        # Three-step chain: get_new_auth0_token + get_user_details_async + apply.
        self.assertEqual(len(args), 3)
