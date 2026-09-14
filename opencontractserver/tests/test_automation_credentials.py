"""HTTP-level capability, lifecycle and upload-ownership regression tests."""

import io
import json
from datetime import timedelta
from typing import Any
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from graphql import GraphQLObjectType
from rest_framework.test import APIClient

from config.graphql.automation import OPERATIONS
from config.graphql.schema import schema
from opencontractserver.corpuses.models import Corpus
from opencontractserver.document_imports.models import ChunkedUploadSession
from opencontractserver.tests.test_document_imports_rest import TXT_BYTES, _make_zip
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.users.models import AutomationCredential
from opencontractserver.users.services import automation_credentials as credentials
from opencontractserver.users.services.automation_credentials import Scope
from opencontractserver.utils.ids import to_global_id
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user


@override_settings(CELERY_TASK_ALWAYS_EAGER=False)
class AutomationCredentialTests(TestCase):
    client: APIClient

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="automation", password="pw", is_usage_capped=False
        )
        self.other_user = get_user_model().objects.create_user(username="other")
        self.corpus = Corpus.objects.create(title="Allowed", creator=self.user)
        self.other_corpus = Corpus.objects.create(title="Other", creator=self.user)
        for corpus in (self.corpus, self.other_corpus):
            set_permissions_for_obj_to_user(self.user, corpus, [PermissionTypes.CRUD])
        self.client = APIClient()
        self.credential, self.token = self.mint()
        self.login(self.token)

    def mint(self, *, user=None, scopes=None, all_corpuses=False, corpus_ids=None):
        return credentials.mint(
            user=user or self.user,
            name="test automation",
            scopes=list(Scope) if scopes is None else scopes,
            corpus_ids=None if all_corpuses else (corpus_ids or [self.corpus.pk]),
            expires_at=timezone.now() + timedelta(days=1),
        )

    def login(self, token):
        self.client.credentials(HTTP_AUTHORIZATION=f"Automation {token}")

    def graphql(self, query, variables=None, operation=None):
        return self.client.post(
            "/graphql/",
            {
                "query": query,
                "variables": variables or {},
                "operationName": operation,
            },
            format="json",
        ).json()

    def corpus_query(self, corpus=None):
        return self.graphql(
            "query($id: ID!) { corpus(id: $id) { id title } }",
            {
                "id": to_global_id("CorpusType", (corpus or self.corpus).pk),
            },
        )

    def upload(self, corpus=None, **extra):
        from django.core.files.uploadedfile import SimpleUploadedFile

        return self.client.post(
            "/api/imports/documents/",
            {
                "file": SimpleUploadedFile("example.txt", TXT_BYTES, "text/plain"),
                "title": "Imported",
                "add_to_corpus_id": str((corpus or self.corpus).pk),
                **extra,
            },
            format="multipart",
        )

    def start(self, *, kind="document", metadata=None):
        return self.client.post(
            "/api/imports/chunked/start/",
            {
                "kind": kind,
                "filename": "example.txt",
                "total_size": len(TXT_BYTES),
                "chunk_size": len(TXT_BYTES),
                "total_chunks": 1,
                "metadata": (
                    metadata
                    if metadata is not None
                    else {
                        "title": "Chunked",
                        "add_to_corpus_id": str(self.corpus.pk),
                    }
                ),
            },
            format="json",
        )

    def part(self, upload_id):
        from django.core.files.uploadedfile import SimpleUploadedFile

        return self.client.put(
            f"/api/imports/chunked/{upload_id}/parts/0/",
            {
                "file": SimpleUploadedFile("part", TXT_BYTES),
            },
            format="multipart",
        )

    def complete(self, upload_id):
        return self.client.post(
            f"/api/imports/chunked/{upload_id}/complete/", {}, format="json"
        )

    def status(self, upload_id):
        return self.client.get(f"/api/imports/chunked/{upload_id}/")

    def test_same_credential_reads_graphql_and_imports_rest(self):
        result = self.corpus_query()
        self.assertNotIn("errors", result)
        self.assertEqual(result["data"]["corpus"]["title"], self.corpus.title)
        response = self.upload()
        self.assertEqual(response.status_code, 201, response.content)

    def test_same_credential_supports_all_zip_imports_direct_and_chunked(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        archive = _make_zip({"example.txt": TXT_BYTES})
        for kind, route, target in (
            ("documents_zip", "documents-zip", "add_to_corpus_id"),
            ("zip_to_corpus", "zip-to-corpus", "corpus_id"),
            ("corpus_export", "corpus", "corpus_id"),
        ):
            with self.subTest(kind=kind):
                metadata = {target: str(self.corpus.pk)}
                response = self.client.post(
                    f"/api/imports/{route}/",
                    {
                        **metadata,
                        "file": SimpleUploadedFile(
                            "import.zip", archive, "application/zip"
                        ),
                    },
                    format="multipart",
                )
                self.assertEqual(response.status_code, 202, response.content)
                response = self.client.post(
                    "/api/imports/chunked/start/",
                    {
                        "kind": kind,
                        "filename": "import.zip",
                        "total_size": len(archive),
                        "chunk_size": len(archive),
                        "total_chunks": 1,
                        "metadata": metadata,
                    },
                    format="json",
                )
                self.assertEqual(response.status_code, 201, response.content)
                upload_id = response.json()["upload_id"]
                response = self.client.put(
                    f"/api/imports/chunked/{upload_id}/parts/0/",
                    {
                        "file": SimpleUploadedFile("part", archive),
                    },
                    format="multipart",
                )
                self.assertEqual(response.status_code, 200, response.content)
                self.assertEqual(self.status(upload_id).status_code, 200)
                response = self.complete(upload_id)
                self.assertEqual(response.status_code, 202, response.content)

    def test_cross_corpus_and_unbound_imports_denied(self):
        self.assertIn("errors", self.corpus_query(self.other_corpus))
        self.assertEqual(self.upload(self.other_corpus).status_code, 403)
        self.assertEqual(self.upload(add_to_corpus_id="").status_code, 403)
        self.assertIn("errors", self.graphql("{ corpuses { edges { node { id } } } }"))

    def test_read_does_not_allow_writes_or_publication(self):
        _, token = self.mint(scopes=[Scope.CORPUS_READ])
        self.login(token)
        self.assertNotIn("errors", self.corpus_query())
        self.assertEqual(self.upload().status_code, 403)
        self.assertEqual(self.start().status_code, 403)
        result = self.graphql(
            "mutation($id: ID!) { setCorpusVisibility(corpusId: $id, isPublic: true) { ok } }",
            {
                "id": to_global_id("CorpusType", self.corpus.pk),
            },
        )
        self.assertIn("errors", result)

    def test_public_import_requires_publication_scope(self):
        _, token = self.mint(scopes=[Scope.DOCUMENT_IMPORT])
        self.login(token)
        self.assertEqual(self.upload(make_public="true").status_code, 403)
        self.assertEqual(
            self.start(
                metadata={
                    "title": "Test",
                    "add_to_corpus_id": str(self.corpus.pk),
                    "make_public": True,
                }
            ).status_code,
            403,
        )

    def test_corpus_export_requires_configuration_and_publication(self):
        _, token = self.mint(scopes=[Scope.DOCUMENT_IMPORT])
        self.login(token)
        self.assertEqual(
            self.start(
                kind="corpus_export",
                metadata={
                    "corpus_id": str(self.corpus.pk),
                },
            ).status_code,
            403,
        )

    def test_scopes_do_not_grant_principal_permissions(self):
        _, token = self.mint(user=self.other_user)
        self.login(token)
        result = self.corpus_query()
        self.assertIsNone(result["data"]["corpus"])
        self.assertNotEqual(self.upload().status_code, 201)
        self.assertNotEqual(self.start().status_code, 201)

    def test_creation_requires_explicit_global_scope(self):
        query = 'mutation { createCorpus(title: "Created by automation") { ok objId } }'
        self.assertIn("errors", self.graphql(query))
        _, token = self.mint(scopes=[Scope.CORPUS_CREATE], all_corpuses=True)
        self.login(token)
        result = self.graphql(query)
        self.assertNotIn("errors", result)
        self.assertTrue(result["data"]["createCorpus"]["ok"], result)

    def test_configuration_scope_does_not_publish(self):
        _, token = self.mint(scopes=[Scope.CORPUS_CONFIGURE])
        self.login(token)
        result = self.graphql(
            'mutation($id: String!) { updateCorpus(id: $id, title: "Configured") { ok } }',
            {
                "id": to_global_id("CorpusType", self.corpus.pk),
            },
        )
        self.assertTrue(result["data"]["updateCorpus"]["ok"], result)
        self.corpus.refresh_from_db()
        self.assertEqual(self.corpus.title, "Configured")
        self.assertFalse(self.corpus.is_public)

    def test_mixed_mutation_denial_prevents_all_side_effects(self):
        _, token = self.mint(scopes=[Scope.CORPUS_CREATE], all_corpuses=True)
        self.login(token)
        before = Corpus.objects.count()
        result = self.graphql("""mutation {
            allowed: createCorpus(title: "Must not exist") { ok }
            ...Denied
        }
        fragment Denied on Mutation {
            forbidden: setCorpusVisibility(corpusId: "invalid", isPublic: true) { ok }
        }""")
        self.assertIn("errors", result)
        self.assertEqual(Corpus.objects.count(), before)

    def test_operation_selection_alias_fragments_defaults_and_directives(self):
        result = self.graphql(
            """query Selected($id: ID!, $skip: Boolean! = true) {
            alias: corpus(id: $id) { ...Metadata }
            adminWorkerUploads @skip(if: $skip) { totalCount }
        }
        query Unselected { me { id } }
        fragment Metadata on CorpusType { id title }
        """,
            {"id": to_global_id("CorpusType", self.corpus.pk)},
            "Selected",
        )
        self.assertNotIn("errors", result)
        self.assertEqual(result["data"]["alias"]["title"], self.corpus.title)

    def test_nested_relationship_and_token_escalation_denied(self):
        result = self.graphql(
            "query($id: ID!) { corpus(id: $id) { creator { email } } }",
            {
                "id": to_global_id("CorpusType", self.corpus.pk),
            },
        )
        self.assertIn("errors", result)
        self.assertIn("errors", self.graphql("{ me { id } }"))
        self.assertIn(
            "errors",
            self.graphql(
                'mutation { tokenAuth(username: "automation", password: "pw") { token } }'
            ),
        )

    def test_repeated_fragment_chain_does_not_repeat_scope_checks(self):
        fragments = [
            f"fragment F{i} on Query {{ ...F{i+1} ...F{i+1} }}" for i in range(12)
        ]
        fragments.append("fragment F12 on Query { corpus(id: $id) { id } }")
        with patch(
            "config.graphql.automation.require_scope", wraps=credentials.require_scope
        ) as gate:
            result = self.graphql(
                "query($id: ID!) { ...F0 ...F0 } " + " ".join(fragments),
                {"id": to_global_id("CorpusType", self.corpus.pk)},
            )
        self.assertNotIn("errors", result)
        self.assertEqual(gate.call_count, 1)

    def test_merged_fields_check_every_nested_selection(self):
        result = self.graphql(
            """query($id: ID!) {
            corpus(id: $id) { id }
            corpus(id: $id) { creator { email } }
        }""",
            {"id": to_global_id("CorpusType", self.corpus.pk)},
        )
        self.assertIn("errors", result)
        self.assertIsNone(result["data"])

    def test_authority_admin_requires_principal_role_and_scope(self):
        _, token = self.mint(all_corpuses=True)
        self.login(token)
        self.assertIn("errors", self.graphql("{ authorityPacks { id } }"))
        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])
        with patch(
            "config.graphql.authority_pack_api.AuthorityPackService.catalog",
            return_value=[],
        ):
            self.assertNotIn("errors", self.graphql("{ authorityPacks { id } }"))
        _, token = self.mint(scopes=[Scope.CORPUS_READ], all_corpuses=True)
        self.login(token)
        self.assertIn("errors", self.graphql("{ authorityPacks { id } }"))
        self.login(self.token)
        self.assertIn("errors", self.graphql("{ authorityPacks { id } }"))

    def test_global_diagnostics_and_repair_require_their_scopes(self):
        _, token = self.mint(scopes=[Scope.CORPUS_READ], all_corpuses=True)
        self.login(token)
        self.assertIn("errors", self.graphql("{ adminWorkerUploads { totalCount } }"))
        self.assertIn(
            "errors",
            self.graphql(
                'mutation { retryDocumentProcessing(documentId: "1") { ok } }'
            ),
        )
        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])
        _, token = self.mint(scopes=[Scope.INGESTION_READ], all_corpuses=True)
        self.login(token)
        result = self.graphql(
            "{ adminWorkerUploads(limit: 1) { totalCount items { id } } }"
        )
        self.assertNotIn("errors", result)

    def test_expiry_revocation_inactive_and_rotation_revalidate_each_request(self):
        for change in (
            {"expires_at": timezone.now() - timedelta(seconds=1)},
            {"revoked_at": timezone.now()},
        ):
            with self.subTest(change=change):
                credential, token = self.mint()
                self.login(token)
                self.assertNotIn("errors", self.corpus_query())
                AutomationCredential.objects.filter(pk=credential.pk).update(**change)
                self.assertIn("errors", self.corpus_query())
                self.assertEqual(self.upload().status_code, 401)
        self.login(self.token)
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        self.assertIn("errors", self.corpus_query())
        self.assertEqual(self.upload().status_code, 401)

    def test_explicit_credential_cannot_bypass_scopes_or_revocation_with_session(self):
        self.client.force_login(self.user)
        self.assertIn("errors", self.corpus_query(self.other_corpus))
        credentials.revoke(self.credential.pk)
        self.assertIn("errors", self.corpus_query())

    def test_chunked_rotation_preserves_owner_and_completes(self):
        response = self.start()
        self.assertEqual(response.status_code, 201, response.content)
        upload_id = response.json()["upload_id"]
        self.assertEqual(self.part(upload_id).status_code, 200)
        rotated, token = credentials.rotate(self.credential.pk)
        self.assertEqual(rotated.pk, self.credential.pk)
        self.assertEqual(self.status(upload_id).status_code, 401)
        self.login(token)
        self.assertEqual(self.status(upload_id).status_code, 200)
        result = self.complete(upload_id)
        self.assertEqual(result.status_code, 201, result.content)

    def test_chunked_other_credential_even_same_user_and_corpus_cannot_resume(self):
        upload_id = self.start().json()["upload_id"]
        _, token = self.mint()
        self.login(token)
        for response in (
            self.status(upload_id),
            self.part(upload_id),
            self.complete(upload_id),
        ):
            self.assertEqual(response.status_code, 404, response.content)
        self.assertEqual(
            ChunkedUploadSession.objects.get(pk=upload_id).parts.count(), 0
        )

    def test_chunked_cross_user_and_session_auth_cannot_resume(self):
        upload_id = self.start().json()["upload_id"]
        _, token = self.mint(user=self.other_user)
        self.login(token)
        self.assertEqual(self.status(upload_id).status_code, 404)
        self.client.credentials()
        self.client.force_authenticate(user=self.user)
        self.assertEqual(self.status(upload_id).status_code, 404)

    def test_chunked_rechecks_scope_and_corpus_at_every_stage(self):
        upload_id = self.start().json()["upload_id"]
        changes_to_test: list[dict[str, list]] = [
            {"scopes": []},
            {"corpus_ids": [self.other_corpus.pk]},
        ]
        for changes in changes_to_test:
            with self.subTest(changes=changes):
                AutomationCredential.objects.filter(pk=self.credential.pk).update(
                    **changes
                )
                for response in (
                    self.status(upload_id),
                    self.part(upload_id),
                    self.complete(upload_id),
                ):
                    self.assertEqual(response.status_code, 403, response.content)
                AutomationCredential.objects.filter(pk=self.credential.pk).update(
                    scopes=list(Scope),
                    corpus_ids=[self.corpus.pk],
                )
        self.assertEqual(
            ChunkedUploadSession.objects.get(pk=upload_id).status, "PENDING"
        )

    def test_chunked_rechecks_principal_corpus_permission(self):
        upload_id = self.start().json()["upload_id"]
        self.corpus.creator = self.other_user
        self.corpus.save(update_fields=["creator"])
        self.corpus.corpususerobjectpermission_set.filter(user=self.user).delete()
        for response in (
            self.status(upload_id),
            self.part(upload_id),
            self.complete(upload_id),
        ):
            self.assertEqual(response.status_code, 404, response.content)

    def test_command_lifecycle_and_logs_never_inspect_secrets(self):
        output = io.StringIO()
        with self.assertLogs(
            "opencontractserver.users.services.automation_credentials", level="INFO"
        ) as logs:
            call_command(
                "automation_credential",
                "mint",
                "--user",
                self.user.username,
                "--name",
                "CLI",
                "--scope",
                "corpus:read",
                "--corpus",
                str(self.corpus.pk),
                stdout=output,
            )
            minted = json.loads(output.getvalue())
            secret = minted["token"]
            output = io.StringIO()
            call_command(
                "automation_credential", "inspect", minted["id"], stdout=output
            )
            inspected = json.loads(output.getvalue())
            self.assertNotIn("token", inspected)
            self.assertNotIn("secret_hash", inspected)
            self.assertNotIn(secret, output.getvalue())
            row = AutomationCredential.objects.get(pk=minted["id"])
            self.assertNotIn(secret.split(".")[1], row.secret_hash)
            output = io.StringIO()
            call_command("automation_credential", "rotate", minted["id"], stdout=output)
            rotated = json.loads(output.getvalue())
            self.login(secret)
            self.assertIn("errors", self.corpus_query())
            self.login(rotated["token"])
            self.assertNotIn("errors", self.corpus_query())
            call_command(
                "automation_credential", "revoke", minted["id"], stdout=io.StringIO()
            )
            self.assertIn("errors", self.corpus_query())
        self.assertNotIn(secret, "\n".join(logs.output))
        self.assertNotIn(rotated["token"], "\n".join(logs.output))

    def test_malformed_credentials_fail_closed(self):
        for token in (
            "",
            "unknown",
            "not-a-uuid.secret",
            f"{self.credential.pk}.wrong",
            "a b",
        ):
            with self.subTest(token=token):
                self.login(token)
                self.assertIn("errors", self.corpus_query())
                self.assertEqual(self.upload().status_code, 401)

    def test_invalid_provisioning_and_revoked_rotation_fail_closed(self):
        from django.core.management.base import CommandError
        from rest_framework.exceptions import AuthenticationFailed

        invalid_arguments: list[dict[str, Any]] = [
            {"scopes": ["unknown"]},
            {"scopes": []},
            {"expires_at": timezone.now() - timedelta(days=1)},
        ]
        for overrides in invalid_arguments:
            arguments = {
                "user": self.user,
                "name": "test",
                "scopes": [Scope.CORPUS_READ],
                "corpus_ids": [self.corpus.pk],
                **overrides,
            }
            with self.assertRaises(ValueError):
                credentials.mint(**arguments)
        original_hash = self.credential.secret_hash
        credentials.revoke(self.credential.pk)
        with self.assertRaises(AuthenticationFailed):
            credentials.rotate(self.credential.pk)
        with self.assertRaises(CommandError):
            call_command(
                "automation_credential",
                "mint",
                "--user",
                self.user.username,
                "--name",
                "invalid",
                "--scope",
                "corpus:read",
                "--all-corpuses",
                "--expires-days",
                "0",
                stdout=io.StringIO(),
            )
        self.credential.refresh_from_db()
        self.assertEqual(self.credential.secret_hash, original_hash)

    def test_credential_owner_binding_does_not_block_user_deletion(self):
        upload_id = self.start().json()["upload_id"]
        self.user.delete()
        self.assertFalse(ChunkedUploadSession.objects.filter(pk=upload_id).exists())
        self.assertFalse(
            AutomationCredential.objects.filter(pk=self.credential.pk).exists()
        )

    def test_policy_names_and_corpus_arguments_match_served_schema(self):
        for parent, policies in OPERATIONS.items():
            parent_type = schema._schema.get_type(parent)
            self.assertIsInstance(parent_type, GraphQLObjectType)
            assert isinstance(parent_type, GraphQLObjectType)
            fields = parent_type.fields
            for name, (_, corpus_arg) in policies.items():
                self.assertIn(name, fields)
                if corpus_arg is not None:
                    self.assertIn(corpus_arg, fields[name].args)
