"""Coverage for opencontractserver.users.tasks under USE_AUTH0=True.

The Auth0-sync celery tasks are only defined when ``settings.USE_AUTH0`` is
truthy at import time. We exercise ``get_new_auth0_token`` end-to-end here so
the ``request_data`` payload construction is hit by coverage and the happy
path / error path is locked in.
"""

import datetime
import importlib
import json
from types import ModuleType
from typing import ClassVar
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from opencontractserver.users.models import Auth0APIToken


def _reload_users_tasks():
    """Re-import users.tasks so its module-level USE_AUTH0 gate is re-evaluated.

    The conditional task definitions live behind ``if settings.USE_AUTH0:``
    blocks at module scope, so toggling ``USE_AUTH0`` via ``override_settings``
    is not enough by itself — the module must be reloaded with the new value
    in place for the celery task callables to actually exist.
    """
    import opencontractserver.users.tasks as users_tasks

    return importlib.reload(users_tasks)


@override_settings(USE_AUTH0=True)
class GetNewAuth0TokenTaskTests(TestCase):
    """Targeted coverage for ``get_new_auth0_token`` request-payload assembly."""

    users_tasks: ClassVar[ModuleType]

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.users_tasks = _reload_users_tasks()

    @classmethod
    def tearDownClass(cls):
        # Restore module to its USE_AUTH0=False import state so subsequent
        # tests aren't accidentally exposed to Auth0-gated task definitions.
        with override_settings(USE_AUTH0=False):
            _reload_users_tasks()
        super().tearDownClass()

    @patch("opencontractserver.users.tasks.requests.post")
    def test_request_data_is_posted_and_token_persisted(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = json.dumps(
            {"access_token": "fake-token-abc", "expires_in": 3600}
        )
        mock_post.return_value = mock_response

        token = self.users_tasks.get_new_auth0_token()

        self.assertEqual(token, "fake-token-abc")
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        payload = kwargs["json"]
        # All four required Auth0 M2M keys must be on the wire.
        self.assertEqual(
            set(payload.keys()),
            {"grant_type", "client_id", "client_secret", "audience"},
        )
        self.assertTrue(payload["audience"].startswith("https://"))
        self.assertTrue(payload["audience"].endswith("/api/v2/"))

        stored = Auth0APIToken.objects.get(token="fake-token-abc")
        # Production code stores a naive datetime here; normalise the
        # database-roundtripped value before comparing.
        self.assertIsNotNone(stored.expiration_Date)
        now_naive = datetime.datetime.now()
        stored_naive = stored.expiration_Date
        if stored_naive.tzinfo is not None:
            stored_naive = stored_naive.replace(tzinfo=None)
        self.assertGreater(stored_naive, now_naive)

    @patch("opencontractserver.users.tasks.requests.post")
    def test_non_200_response_returns_none_without_persisting(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "boom"
        mock_post.return_value = mock_response

        token_count_before = Auth0APIToken.objects.count()
        token = self.users_tasks.get_new_auth0_token()

        self.assertIsNone(token)
        self.assertEqual(Auth0APIToken.objects.count(), token_count_before)
