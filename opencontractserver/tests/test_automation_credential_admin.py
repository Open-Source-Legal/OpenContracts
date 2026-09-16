"""Exercise the admin API through HTTP, including CLI interoperability."""

import io
import json
from datetime import timedelta
from typing import Any
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from graphql import GraphQLObjectType
from guardian.shortcuts import get_perms
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from rest_framework.test import APIClient

from config.graphql.schema import schema
from opencontractserver.corpuses.models import Corpus
from opencontractserver.users.models import AutomationCredential
from opencontractserver.users.services import automation_credentials as credentials

METADATA = """
    id userId username name scopes corpusIds status
    expiresAt revokedAt createdAt rotatedAt
"""
MINT = """
mutation Mint($user: ID!, $name: String!, $scopes: [String!]!, $corpuses: [ID!],
              $all: Boolean! = false, $days: Int! = 30) {
  mintAutomationCredential(userId: $user, name: $name, scopes: $scopes,
    corpusIds: $corpuses, allCorpuses: $all, expiresDays: $days) {
    token credential { id userId name scopes corpusIds expiresAt status }
  }
}
"""


@override_settings(CELERY_TASK_ALWAYS_EAGER=False)
class AutomationCredentialAdminTests(TestCase):
    client: APIClient

    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_user(username="admin", is_superuser=True)
        self.principal = User.objects.create_user(
            username="service", is_profile_public=False
        )
        self.staff = User.objects.create_user(username="staff", is_staff=True)
        self.inactive = User.objects.create_user(username="inactive", is_active=False)
        self.corpus = Corpus.objects.create(title="Selected corpus", creator=self.admin)

        self.client = APIClient()
        self.client.force_login(self.admin)

    def graphql(self, query, variables=None):
        response = self.client.post(
            "/graphql/", {"query": query, "variables": variables or {}}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        return response

    def data(self, query, variables=None):
        response = self.graphql(query, variables)
        body = response.json()
        self.assertNotIn("errors", body, body)
        self.assertIn("no-store", response["Cache-Control"])
        return body["data"]

    def mint_arguments(self, **overrides):
        return {
            "user": str(self.principal.pk),
            "name": "nightly",
            "scopes": ["corpus:read"],
            "corpuses": [str(self.corpus.pk)],
            **overrides,
        }

    def cli_credential(self):
        output = io.StringIO()
        call_command(
            "automation_credential",
            "mint",
            "--user",
            self.principal.username,
            "--name",
            "from CLI",
            "--scope",
            "corpus:read",
            "--all-corpuses",
            stdout=output,
        )
        return json.loads(output.getvalue())

    def test_mint_defaults_to_thirty_days_without_granting_principal_permissions(self):
        before = timezone.now()
        with self.assertLogs(credentials.logger.name, level="INFO") as logs:
            result = self.data(MINT, self.mint_arguments())["mintAutomationCredential"]
        self.assertIn(
            f"actor_id={self.admin.pk} principal_id={self.principal.pk}", logs.output[0]
        )
        self.assertNotIn(result["token"], "\n".join(logs.output))
        credential = AutomationCredential.objects.get(pk=result["credential"]["id"])
        self.assertEqual(result["credential"]["userId"], str(self.principal.pk))
        self.assertEqual(credential.corpus_ids, [self.corpus.pk])
        self.assertEqual(credential.scopes, ["corpus:read"])
        assert credential.expires_at is not None
        self.assertGreaterEqual(credential.expires_at, before + timedelta(days=30))
        self.assertLessEqual(credential.expires_at, timezone.now() + timedelta(days=30))
        self.assertEqual(get_perms(self.principal, self.corpus), [])
        self.assertEqual(
            credentials.authenticate_token(result["token"]).pk, credential.pk
        )
        self.assertNotIn(result["token"].split(".", 1)[1], credential.secret_hash)

    def test_cli_credential_can_be_inspected_rotated_and_revoked_with_separate_audit_actor(
        self,
    ):
        original = self.cli_credential()
        credential_id = original["id"]
        listed = self.data(
            "{ automationCredentials { items { " + METADATA + " } totalCount } }"
        )["automationCredentials"]
        self.assertEqual(listed["totalCount"], 1)
        self.assertEqual(listed["items"][0]["id"], credential_id)
        inspect = (
            "query($id: UUID!) { automationCredential(id: $id) { " + METADATA + " } }"
        )
        detail = self.data(inspect, {"id": credential_id})["automationCredential"]
        self.assertEqual(detail, listed["items"][0])
        with self.assertLogs(credentials.logger.name, level="INFO") as logs:
            rotated = self.data(
                """mutation($id: UUID!) {
                  rotateAutomationCredential(id: $id) {
                    token credential { id scopes corpusIds expiresAt rotatedAt }
                  }
                }""",
                {"id": credential_id},
            )["rotateAutomationCredential"]
            self.assertEqual(rotated["credential"]["id"], credential_id)
            self.assertEqual(rotated["credential"]["scopes"], detail["scopes"])
            self.assertEqual(rotated["credential"]["corpusIds"], detail["corpusIds"])
            self.assertEqual(rotated["credential"]["expiresAt"], detail["expiresAt"])
            self.assertIsNotNone(rotated["credential"]["rotatedAt"])
            with self.assertRaises(AuthenticationFailed):
                credentials.authenticate_token(original["token"])
            self.assertEqual(
                str(credentials.authenticate_token(rotated["token"]).pk), credential_id
            )
            revoke = "mutation($id: UUID!) { revokeAutomationCredential(id: $id) { status revokedAt } }"
            revoked = self.data(revoke, {"id": credential_id})[
                "revokeAutomationCredential"
            ]
            self.assertEqual(revoked["status"], "revoked")
            self.assertEqual(
                self.data(revoke, {"id": credential_id})["revokeAutomationCredential"],
                revoked,
            )
            with self.assertRaises(AuthenticationFailed):
                credentials.authenticate_token(rotated["token"])
        for event in ("rotated", "revoked"):
            entry = next(line for line in logs.output if f"credential {event}" in line)
            self.assertIn(
                f"actor_id={self.admin.pk} principal_id={self.principal.pk}", entry
            )
        for token in (original["token"], rotated["token"]):
            self.assertNotIn(token, "\n".join(logs.output))
            self.assertNotIn(token, json.dumps(listed))
        metadata_type = schema._schema.get_type("AutomationCredentialMetadata")
        self.assertIsInstance(metadata_type, GraphQLObjectType)
        assert isinstance(metadata_type, GraphQLObjectType)
        fields = metadata_type.fields
        self.assertEqual(set(fields), set(METADATA.split()))

    def test_every_management_operation_requires_an_active_superuser_login(self):
        original = self.cli_credential()
        operations = [
            ("{ automationCredentials { totalCount } }", {}),
            ("{ automationCredentialScopes }", {}),
            ('{ automationCredentialChoices(kind: "principal") { totalCount } }', {}),
            (
                "query($id: UUID!) { automationCredential(id: $id) { id } }",
                {"id": original["id"]},
            ),
            (MINT, self.mint_arguments()),
            (
                "mutation($id: UUID!) { rotateAutomationCredential(id: $id) { token } }",
                {"id": original["id"]},
            ),
            (
                "mutation($id: UUID!) { revokeAutomationCredential(id: $id) { id } }",
                {"id": original["id"]},
            ),
        ]
        for actor in (None, self.principal, self.staff, self.inactive):
            self.client.logout()
            if actor:
                self.client.force_login(actor)
            for query, variables in operations:
                with self.subTest(actor=actor, query=query):
                    self.assertEqual(
                        self.graphql(query, variables).json()["errors"][0]["message"],
                        "An active superuser login is required.",
                    )
        self.inactive.is_superuser = True
        with self.assertRaises(PermissionDenied):
            credentials.require_management(self.inactive)
        self.client.force_login(self.admin)
        _, token = credentials.mint(
            user=self.admin,
            name="superuser automation",
            scopes=list(credentials.Scope),
            corpus_ids=None,
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Automation {token}")
        for query, variables in operations:
            with self.subTest(query=query):
                self.assertEqual(
                    self.graphql(query, variables).json()["errors"][0]["message"],
                    credentials.DENIED,
                )
        credential = AutomationCredential.objects.get(pk=original["id"])
        self.assertIsNone(credential.revoked_at)
        self.assertIsNone(credential.rotated_at)
        self.assertEqual(AutomationCredential.objects.count(), 2)

    def test_automation_management_root_rejects_the_entire_mixed_mutation(self):
        original = self.cli_credential()
        _, token = credentials.mint(
            user=self.admin,
            name="automation",
            scopes=list(credentials.Scope),
            corpus_ids=None,
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Automation {token}")
        before = Corpus.objects.count()
        result = self.graphql(
            """
            mutation($id: UUID!) {
              first: createCorpus(title: "Must not be created") { ok }
              ...Denied
            }
            fragment Denied on Mutation {
              second: revokeAutomationCredential(id: $id) { id }
            }
        """,
            {"id": original["id"]},
        ).json()
        self.assertEqual(result["errors"][0]["message"], credentials.DENIED)
        self.assertIsNone(result.get("data"))
        self.assertEqual(Corpus.objects.count(), before)

    def test_invalid_mint_inputs_never_create_a_credential(self):
        cases: list[dict[str, Any]] = [
            {"user": str(self.inactive.pk)},
            {"user": "999999999"},
            {"user": "not-an-id"},
            {"name": " "},
            {"name": "x" * 101},
            {"scopes": []},
            {"scopes": ["unknown"]},
            {"days": 0},
            {"days": -1},
            {"days": 2147483647},
            {"corpuses": []},
            {"corpuses": None},
            {"corpuses": ["999999999"]},
            {"corpuses": ["invalid"]},
            {"all": True},
        ]
        for overrides in cases:
            with self.subTest(overrides=overrides):
                result = self.graphql(MINT, self.mint_arguments(**overrides)).json()
                self.assertIn("errors", result)
                self.assertFalse(AutomationCredential.objects.exists())
        minted = self.data(MINT, self.mint_arguments(all=True, corpuses=None, days=1))[
            "mintAutomationCredential"
        ]
        self.assertIsNone(minted["credential"]["corpusIds"])

    def test_lifecycle_writes_recheck_an_administrator_changed_since_authentication(
        self,
    ):
        original = self.cli_credential()
        row = AutomationCredential.objects.get(pk=original["id"])
        for change in ({"is_active": False}, {"is_superuser": False}):
            get_user_model().objects.filter(pk=self.admin.pk).update(**change)
            # self.admin still represents the active superuser loaded at auth.
            for operation in ("mint", "rotate", "revoke"):
                with self.subTest(change=change, operation=operation):
                    with self.assertRaises(PermissionDenied):
                        if operation == "mint":
                            credentials.mint(
                                user=self.principal,
                                actor=self.admin,
                                name="rejected",
                                scopes=["corpus:read"],
                                corpus_ids=None,
                            )
                        else:
                            getattr(credentials, operation)(row.pk, actor=self.admin)
                    row.refresh_from_db()
                    self.assertIsNone(row.revoked_at)
                    self.assertIsNone(row.rotated_at)
                    self.assertEqual(AutomationCredential.objects.count(), 1)
            get_user_model().objects.filter(pk=self.admin.pk).update(
                is_active=True, is_superuser=True
            )
        self.assertEqual(credentials.authenticate_token(original["token"]).pk, row.pk)

    def test_mint_rechecks_a_principal_deactivated_after_selection(self):
        get_user_model().objects.filter(pk=self.principal.pk).update(is_active=False)
        with self.assertRaisesMessage(ValueError, "Principal must be active"):
            credentials.mint(
                user=self.principal,
                actor=self.admin,
                name="rejected",
                scopes=["corpus:read"],
                corpus_ids=None,
            )
        self.assertFalse(AutomationCredential.objects.exists())

    def test_choices_are_paginated_and_include_private_active_principals_by_id(self):
        query = """query($kind: String!, $search: String!, $offset: Int!) {
          automationCredentialChoices(kind: $kind, search: $search, limit: 1, offset: $offset) {
            totalCount items { id label }
          }
        }"""
        page = self.data(
            query, {"kind": "principal", "search": str(self.principal.pk), "offset": 0}
        )["automationCredentialChoices"]
        self.assertEqual(
            page["items"],
            [{"id": str(self.principal.pk), "label": self.principal.username}],
        )
        page = self.data(
            query, {"kind": "principal", "search": "inactive", "offset": 0}
        )["automationCredentialChoices"]
        self.assertEqual(page["items"], [])
        get_user_model().objects.create_user(username="service-other")
        first = self.data(
            query, {"kind": "principal", "search": "service", "offset": 0}
        )["automationCredentialChoices"]
        second = self.data(
            query, {"kind": "principal", "search": "service", "offset": 1}
        )["automationCredentialChoices"]
        self.assertEqual(first["totalCount"], 2)
        self.assertNotEqual(first["items"], second["items"])
        page = self.data(query, {"kind": "corpus", "search": "Selected", "offset": 0})[
            "automationCredentialChoices"
        ]
        self.assertEqual(
            page["items"], [{"id": str(self.corpus.pk), "label": self.corpus.title}]
        )
        scopes = self.data("{ automationCredentialScopes }")[
            "automationCredentialScopes"
        ]
        self.assertEqual(scopes, [scope.value for scope in credentials.Scope])

    def test_status_pagination_and_unusable_credentials_cannot_be_rotated(self):
        for status in ("active", "expired", "revoked", "inactive principal"):
            minted = self.cli_credential()
            row = AutomationCredential.objects.get(pk=minted["id"])
            if status == "expired":
                row.expires_at = timezone.now() - timedelta(seconds=1)
            elif status == "revoked":
                row.revoked_at = timezone.now()
            elif status == "inactive principal":
                row.user = self.inactive
            row.save()
        query = """query($offset: Int!, $limit: Int!) {
          automationCredentials(offset: $offset, limit: $limit) { totalCount items { id status } }
        }"""
        pages = [
            self.data(query, {"offset": offset, "limit": 1})["automationCredentials"]
            for offset in range(4)
        ]
        self.assertEqual({page["totalCount"] for page in pages}, {4})
        items = [page["items"][0] for page in pages]
        self.assertEqual(len({item["id"] for item in items}), 4)
        self.assertEqual(
            [item["status"] for item in items],
            ["inactive principal", "revoked", "expired", "active"],
        )
        rotate = (
            "mutation($id: UUID!) { rotateAutomationCredential(id: $id) { token } }"
        )
        for item in items[:3]:
            self.assertIn("errors", self.graphql(rotate, {"id": item["id"]}).json())
            self.assertIsNone(
                AutomationCredential.objects.get(pk=item["id"]).rotated_at
            )
        for id in (str(uuid4()), "invalid"):
            self.assertIn("errors", self.graphql(rotate, {"id": id}).json())
        for variables in (
            {"offset": -1, "limit": 1},
            {"offset": 0, "limit": 0},
            {"offset": 0, "limit": 101},
        ):
            self.assertIn("errors", self.graphql(query, variables).json())
