"""Exercise self-service credential boundaries through HTTP and the CLI."""

import io
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from typing import Any
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import OperationalError, connection, connections, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from graphql import GraphQLObjectType
from guardian.shortcuts import assign_perm, get_perms
from psycopg2.errors import LockNotAvailable
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from rest_framework.test import APIClient

from config.graphql.schema import schema
from opencontractserver.corpuses.models import Corpus
from opencontractserver.users.models import AutomationCredential
from opencontractserver.users.services import automation_credentials as credentials
from opencontractserver.utils.ids import to_global_id

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
SELF_MINT = MINT.replace("$user: ID!, ", "").replace("userId: $user, ", "")


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
            "user": str(self.admin.pk),
            "name": "nightly",
            "scopes": ["corpus:read"],
            "corpuses": [str(self.corpus.pk)],
            **overrides,
        }

    def cli_credential(self, user=None):
        output = io.StringIO()
        call_command(
            "automation_credential",
            "mint",
            "--user",
            (user or self.admin).username,
            "--name",
            "from CLI",
            "--scope",
            "corpus:read",
            "--all-corpuses",
            stdout=output,
        )
        return json.loads(output.getvalue())

    def test_regular_user_mints_for_self_with_thirty_day_expiry_and_unchanged_permissions(
        self,
    ):
        self.client.force_login(self.principal)
        self.corpus.creator = self.principal
        self.corpus.save()
        permissions_before = get_perms(self.principal, self.corpus)
        before = timezone.now()
        with self.assertLogs(credentials.logger.name, level="INFO") as logs:
            result = self.data(SELF_MINT, self.mint_arguments())[
                "mintAutomationCredential"
            ]
        self.assertIn(
            f"actor_id={self.principal.pk} principal_id={self.principal.pk}",
            logs.output[0],
        )
        self.assertNotIn(result["token"], "\n".join(logs.output))
        credential = AutomationCredential.objects.get(pk=result["credential"]["id"])
        self.assertEqual(result["credential"]["userId"], str(self.principal.pk))
        self.assertEqual(credential.corpus_ids, [self.corpus.pk])
        self.assertEqual(credential.scopes, ["corpus:read"])
        assert credential.expires_at is not None
        self.assertGreaterEqual(credential.expires_at, before + timedelta(days=30))
        self.assertLessEqual(credential.expires_at, timezone.now() + timedelta(days=30))
        self.assertEqual(get_perms(self.principal, self.corpus), permissions_before)
        self.assertEqual(
            credentials.authenticate_token(result["token"]).pk, credential.pk
        )
        self.assertNotIn(result["token"].split(".", 1)[1], credential.secret_hash)

    def test_own_cli_credential_can_be_inspected_rotated_and_revoked(
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
                f"actor_id={self.admin.pk} principal_id={self.admin.pk}", entry
            )
        for token in (original["token"], rotated["token"]):
            self.assertNotIn(token, "\n".join(logs.output))
            self.assertNotIn(token, json.dumps(listed))
        metadata_type = schema._schema.get_type("AutomationCredentialMetadata")
        self.assertIsInstance(metadata_type, GraphQLObjectType)
        assert isinstance(metadata_type, GraphQLObjectType)
        fields = metadata_type.fields
        self.assertEqual(set(fields), set(METADATA.split()))

    def test_every_management_operation_requires_an_active_interactive_login(self):
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
        for actor in (None, self.inactive):
            self.client.logout()
            if actor:
                self.client.force_login(actor)
            for query, variables in operations:
                with self.subTest(actor=actor, query=query):
                    self.assertEqual(
                        self.graphql(query, variables).json()["errors"][0]["message"],
                        "An active login is required.",
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

    def test_lifecycle_writes_recheck_an_actor_deactivated_since_authentication(
        self,
    ):
        original = self.cli_credential()
        row = AutomationCredential.objects.get(pk=original["id"])
        get_user_model().objects.filter(pk=self.admin.pk).update(is_active=False)
        # self.admin still represents the active superuser loaded at auth.
        for operation in ("mint", "rotate", "revoke"):
            with self.subTest(operation=operation):
                with self.assertRaises(PermissionDenied):
                    if operation == "mint":
                        credentials.mint(
                            user=self.admin,
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

    def test_cli_mint_rechecks_a_principal_deactivated_since_loading(self):
        get_user_model().objects.filter(pk=self.principal.pk).update(is_active=False)
        with self.assertRaisesMessage(ValueError, "Principal must be active"):
            credentials.mint(
                user=self.principal,
                name="rejected",
                scopes=["corpus:read"],
                corpus_ids=None,
            )
        self.assertFalse(AutomationCredential.objects.exists())

    def test_even_admins_cannot_mint_or_rotate_another_users_token(self):
        original = self.cli_credential(self.principal)
        row = AutomationCredential.objects.get(pk=original["id"])
        secret_hash = row.secret_hash
        for actor in (self.admin, self.staff):
            self.client.force_login(actor)
            with self.subTest(actor=actor.username):
                result = self.graphql(
                    MINT, self.mint_arguments(user=str(self.principal.pk))
                ).json()
                self.assertIn("errors", result)
                result = self.graphql(
                    "mutation($id: UUID!) { rotateAutomationCredential(id: $id) { token } }",
                    {"id": original["id"]},
                ).json()
                self.assertIn("errors", result)
                row.refresh_from_db()
                self.assertEqual(row.secret_hash, secret_hash)
                self.assertIsNone(row.rotated_at)
                self.assertEqual(AutomationCredential.objects.count(), 1)
        self.assertEqual(credentials.authenticate_token(original["token"]).pk, row.pk)

    def test_regular_users_only_list_inspect_rotate_and_revoke_their_own_tokens(self):
        own_corpus = Corpus.objects.create(title="My corpus", creator=self.staff)
        own, token = credentials.mint(
            user=self.staff,
            name="Mine",
            scopes=["corpus:read"],
            corpus_ids=[own_corpus.pk],
        )
        foreign = self.cli_credential()
        self.client.force_login(self.staff)
        page = self.data("{ automationCredentials { items { id } totalCount } }")[
            "automationCredentials"
        ]
        self.assertEqual(page, {"items": [{"id": str(own.pk)}], "totalCount": 1})
        inspect = "query($id: UUID!) { automationCredential(id: $id) { name } }"
        self.assertEqual(
            self.data(inspect, {"id": str(own.pk)})["automationCredential"],
            {"name": "Mine"},
        )
        revoke = (
            "mutation($id: UUID!) { revokeAutomationCredential(id: $id) { status } }"
        )
        for query in (inspect, revoke):
            errors = []
            for credential_id in (foreign["id"], str(uuid4())):
                result = self.graphql(query, {"id": credential_id}).json()
                errors.append(result["errors"][0]["message"])
            self.assertEqual(errors, ["Invalid credential operation or arguments."] * 2)
        rotated = self.data(
            "mutation($id: UUID!) { rotateAutomationCredential(id: $id) { token } }",
            {"id": str(own.pk)},
        )["rotateAutomationCredential"]["token"]
        with self.assertRaises(AuthenticationFailed):
            credentials.authenticate_token(token)
        self.assertEqual(credentials.authenticate_token(rotated).pk, own.pk)
        self.assertEqual(
            self.data(revoke, {"id": str(own.pk)})["revokeAutomationCredential"][
                "status"
            ],
            "revoked",
        )
        self.assertEqual(
            str(credentials.authenticate_token(foreign["token"]).pk), foreign["id"]
        )

    def test_admins_can_inspect_and_revoke_another_users_token(self):
        original = self.cli_credential(self.principal)
        page = self.data("{ automationCredentials { items { id } totalCount } }")[
            "automationCredentials"
        ]
        self.assertEqual(page["items"], [{"id": original["id"]}])
        self.assertEqual(
            self.data(
                "query($id: UUID!) { automationCredential(id: $id) { userId } }",
                {"id": original["id"]},
            )["automationCredential"]["userId"],
            str(self.principal.pk),
        )
        with self.assertLogs(credentials.logger.name, level="INFO") as logs:
            self.data(
                "mutation($id: UUID!) { revokeAutomationCredential(id: $id) { id } }",
                {"id": original["id"]},
            )
        self.assertIn(
            f"actor_id={self.admin.pk} principal_id={self.principal.pk}", logs.output[0]
        )
        with self.assertRaises(AuthenticationFailed):
            credentials.authenticate_token(original["token"])

    def test_non_admin_choices_only_include_owned_corpuses_and_corpus_scopes(self):
        owned = [
            Corpus.objects.create(title=f"Contracts {i}", creator=self.principal)
            for i in range(2)
        ]
        self.corpus.title = "Contracts shared"
        self.corpus.is_public = True
        self.corpus.save()
        assign_perm("change_corpus", self.principal, self.corpus)
        self.client.force_login(self.principal)
        query = """query($offset: Int!, $search: String!) {
          automationCredentialChoices(kind: "corpus", search: $search, limit: 1, offset: $offset) {
            totalCount items { id label }
          }
        }"""
        for offset, corpus in enumerate(owned):
            page = self.data(query, {"offset": offset, "search": "Contracts"})[
                "automationCredentialChoices"
            ]
            self.assertEqual(
                page,
                {
                    "totalCount": 2,
                    "items": [{"id": str(corpus.pk), "label": corpus.title}],
                },
            )
        page = self.data(query, {"offset": 0, "search": str(self.corpus.pk)})[
            "automationCredentialChoices"
        ]
        self.assertEqual(page, {"totalCount": 0, "items": []})
        scopes = self.data("{ automationCredentialScopes }")[
            "automationCredentialScopes"
        ]
        self.assertEqual(
            set(scopes),
            {
                "corpus:read",
                "corpus:configure",
                "corpus:publish",
                "document:import",
                "ingestion:repair",
            },
        )
        for actor in (self.principal, self.admin):
            self.client.force_login(actor)
            choices = self.data(
                '{ automationCredentialChoices(kind: "principal") { items { id } totalCount } }'
            )["automationCredentialChoices"]
            self.assertEqual(
                choices, {"items": [{"id": str(actor.pk)}], "totalCount": 1}
            )

    def test_non_admin_mint_rejects_global_scopes_and_foreign_corpuses(self):
        owned = Corpus.objects.create(title="My corpus", creator=self.principal)
        self.corpus.is_public = True
        self.corpus.save()
        assign_perm("change_corpus", self.principal, self.corpus)
        self.client.force_login(self.principal)
        cases = [
            {"scopes": [scope]}
            for scope in (
                "corpus:create",
                "ingestion:read",
                "authority:admin",
                "pipeline:read",
                "pipeline:configure",
            )
        ] + [
            {"all": True, "corpuses": None},
            {"corpuses": [str(self.corpus.pk)]},
            {"corpuses": [str(owned.pk), to_global_id("CorpusType", self.corpus.pk)]},
            {"corpuses": []},
        ]
        for overrides in cases:
            with self.subTest(overrides=overrides):
                args = self.mint_arguments(
                    user=str(self.principal.pk), corpuses=[str(owned.pk)]
                )
                args.update(overrides)
                self.assertIn("errors", self.graphql(MINT, args).json())
                self.assertFalse(AutomationCredential.objects.exists())
        result = self.data(
            MINT,
            self.mint_arguments(
                user=str(self.principal.pk),
                corpuses=[to_global_id("CorpusType", owned.pk)],
                scopes=["corpus:configure", "document:import"],
            ),
        )["mintAutomationCredential"]
        self.assertEqual(result["credential"]["corpusIds"], [str(owned.pk)])
        self.assertEqual(
            credentials.authenticate_token(result["token"]).user_id, self.principal.pk
        )

    def test_demotion_rechecks_scope_and_corpus_limits_before_issuing_secrets(self):
        original = self.cli_credential()
        get_user_model().objects.filter(pk=self.admin.pk).update(is_superuser=False)
        with self.assertRaises(PermissionDenied):
            credentials.mint(
                user=self.admin,
                actor=self.admin,
                name="Global",
                scopes=["pipeline:configure"],
                corpus_ids=None,
            )
        with self.assertRaises(PermissionDenied):
            credentials.rotate(original["id"], actor=self.admin)
        row = AutomationCredential.objects.get(pk=original["id"])
        self.assertIsNone(row.rotated_at)
        self.assertEqual(AutomationCredential.objects.count(), 1)
        # Revocation must remain available even for an over-broad legacy credential.
        credentials.revoke(row.pk, actor=self.admin)
        with self.assertRaises(AuthenticationFailed):
            credentials.authenticate_token(original["token"])

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


@override_settings(CELERY_TASK_ALWAYS_EAGER=False)
class CredentialIssuanceConcurrencyTests(TransactionTestCase):
    def test_corpus_ownership_cannot_change_between_authorization_and_secret_issuance(
        self,
    ):
        owner = get_user_model().objects.create_user(username="owner")
        recipient = get_user_model().objects.create_user(username="recipient")
        corpus = Corpus.objects.create(title="Owned corpus", creator=owner)
        credential, _ = credentials.mint(
            user=owner, name="Existing", scopes=["corpus:read"], corpus_ids=[corpus.pk]
        )

        def attempt_concurrent_transfer():
            try:
                with transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute("SET LOCAL lock_timeout = '200ms'")
                    Corpus.objects.filter(pk=corpus.pk).update(creator=recipient)
                return "transferred"
            except OperationalError as exc:
                if not isinstance(exc.__cause__, LockNotAvailable):
                    raise
                return "blocked"
            finally:
                connections.close_all()

        new_secret = credentials._new_secret

        def transfer_before_secret_is_saved(row):
            with ThreadPoolExecutor(max_workers=1) as executor:
                result = executor.submit(attempt_concurrent_transfer).result(timeout=5)
            self.assertEqual(result, "blocked")
            return new_secret(row)

        for operation in ("mint", "rotate"):
            with self.subTest(operation=operation):
                Corpus.objects.filter(pk=corpus.pk).update(creator=owner)
                with patch.object(
                    credentials, "_new_secret", transfer_before_secret_is_saved
                ):
                    if operation == "mint":
                        _, token = credentials.mint(
                            actor=owner,
                            user=owner,
                            name="New",
                            scopes=["corpus:read"],
                            corpus_ids=[corpus.pk],
                        )
                    else:
                        _, token = credentials.rotate(credential.pk, actor=owner)
                self.assertEqual(
                    credentials.authenticate_token(token).user_id, owner.pk
                )
        # The lock must be released when the transaction completes.
        self.assertEqual(attempt_concurrent_transfer(), "transferred")
        corpus.refresh_from_db()
        self.assertEqual(corpus.creator_id, recipient.pk)
