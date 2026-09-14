"""Disabling an account takes effect on the next session-authenticated request."""

from django.contrib.auth import HASH_SESSION_KEY, load_backend
from django.test import TestCase, override_settings

from config.jwt_auth.shortcuts import get_token
from opencontractserver.corpuses.models import Corpus
from opencontractserver.users.models import User

BACKENDS = (
    "django.contrib.auth.backends.ModelBackend",
    "config.jwt_auth.backends.JSONWebTokenBackend",
    "config.graphql_auth0_auth.backends.Auth0RemoteUserJSONWebTokenBackend",
    "config.admin_auth.backends.Auth0AdminBackend",
)


@override_settings(AUTHENTICATION_BACKENDS=BACKENDS)
class InactiveSessionAccountTests(TestCase):
    def setUp(self):
        self.actor = User.objects.create_user(username="session-owner")
        publisher = User.objects.create_user(username="session-publisher")
        Corpus.objects.create(creator=publisher, title="Published", is_public=True)
        Corpus.objects.create(creator=self.actor, title="Session private")

    def titles(self, token=None):
        response = self.client.post(
            "/graphql/",
            {"query": "{ corpuses { edges { node { title } } } }"},
            content_type="application/json",
            headers={"Authorization": f"Bearer {token}"} if token else {},
        )
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertNotIn("errors", result)
        return {edge["node"]["title"] for edge in result["data"]["corpuses"]["edges"]}

    def test_backends_reload_active_state_without_extra_queries(self):
        for path in BACKENDS:
            with self.subTest(backend=path):
                backend = load_backend(path)
                User.objects.filter(pk=self.actor.pk).update(is_active=True)
                with self.assertNumQueries(1):
                    self.assertEqual(backend.get_user(self.actor.pk), self.actor)
                User.objects.filter(pk=self.actor.pk).update(is_active=False)
                with self.assertNumQueries(1):
                    self.assertIsNone(backend.get_user(self.actor.pk))
                self.assertIsNone(backend.get_user(-1))

    def test_deactivation_removes_private_access_on_the_next_request(self):
        for path in BACKENDS:
            with self.subTest(backend=path):
                User.objects.filter(pk=self.actor.pk).update(is_active=True)
                self.client.force_login(self.actor, backend=path)
                self.assertEqual(
                    self.titles(), {"Published", "Session private", "My Documents"}
                )
                User.objects.filter(pk=self.actor.pk).update(is_active=False)
                self.assertEqual(self.titles(), {"Published"})

    def test_rejected_session_can_use_another_valid_token(self):
        alternate = User.objects.create_user(username="session-alternate")
        Corpus.objects.create(creator=alternate, title="Alternate private")
        for path in BACKENDS:
            with self.subTest(backend=path):
                self.client.force_login(self.actor, backend=path)
                User.objects.filter(pk=self.actor.pk).update(is_active=False)
                self.assertEqual(
                    self.titles(get_token(alternate)),
                    {"Published", "Alternate private", "My Documents"},
                )

    def test_django_still_rejects_invalid_session_hashes(self):
        for path in BACKENDS:
            with self.subTest(backend=path):
                self.client.force_login(self.actor, backend=path)
                session = self.client.session
                session[HASH_SESSION_KEY] = "invalid-hash"
                session.save()
                self.assertEqual(self.titles(), {"Published"})
