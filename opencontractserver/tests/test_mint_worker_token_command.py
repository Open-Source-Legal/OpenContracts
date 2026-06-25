"""``manage.py mint_worker_token`` — the one-command server-side setup step for
the remote-ingest worker (``scripts/remote_ingest``).

The command resolves an acting superuser, creates (or reuses) a worker service
account, mints a corpus-scoped ``CorpusAccessToken``, and prints the plaintext
token exactly once. These tests pin every branch: account create / reuse /
deactivated-reject, the superuser resolution paths (named, unknown, non-super,
default, none), and the two service-failure → ``CommandError`` mappings.
"""

from __future__ import annotations

from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from opencontractserver.annotations.models import LabelSet
from opencontractserver.corpuses.models import Corpus
from opencontractserver.shared.services.conventions import ServiceResult
from opencontractserver.worker_uploads.models import WorkerAccount

User = get_user_model()

_CMD = "opencontractserver.worker_uploads.management.commands.mint_worker_token"


class MintWorkerTokenCommandTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            username="mint_root",
            password="testpass",
            email="mint_root@test.com",
        )
        cls.label_set = LabelSet.objects.create(title="Mint LS", creator=cls.superuser)
        cls.corpus = Corpus.objects.create(
            title="Rig Corpus",
            creator=cls.superuser,
            label_set=cls.label_set,
        )

    def _call(self, **kwargs) -> str:
        out = StringIO()
        call_command("mint_worker_token", stdout=out, **kwargs)
        return out.getvalue()

    def test_mints_token_for_new_worker_account(self):
        out = self._call(
            corpus=self.corpus.id,
            worker_name="rig-new",
            description="Fort Worth rig",
            rate_limit=10,
            expires_days=30,
        )
        self.assertIn("Created worker account 'rig-new'", out)
        self.assertIn("OC_WORKER_TOKEN=", out)
        self.assertIn(f"OC_CORPUS_ID={self.corpus.id}", out)

        account = WorkerAccount.objects.get(name="rig-new")
        self.assertEqual(account.access_tokens.count(), 1)
        token = account.access_tokens.first()
        self.assertEqual(token.corpus_id, self.corpus.id)
        self.assertIsNotNone(token.expires_at)  # --expires-days was supplied

    def test_reuses_existing_active_account(self):
        WorkerAccount.create_with_user(name="rig-reuse", creator=self.superuser)
        out = self._call(corpus=self.corpus.id, worker_name="rig-reuse")
        self.assertIn("Reusing existing worker account 'rig-reuse'", out)
        self.assertIn("OC_WORKER_TOKEN=", out)
        # No duplicate account was created.
        self.assertEqual(WorkerAccount.objects.filter(name="rig-reuse").count(), 1)

    def test_deactivated_account_is_rejected(self):
        account = WorkerAccount.create_with_user(
            name="rig-dead", creator=self.superuser
        )
        account.is_active = False
        account.save(update_fields=["is_active"])
        with self.assertRaisesMessage(CommandError, "deactivated"):
            self._call(corpus=self.corpus.id, worker_name="rig-dead")

    def test_as_user_resolves_named_superuser(self):
        out = self._call(
            corpus=self.corpus.id, worker_name="rig-named", as_user="mint_root"
        )
        self.assertIn("OC_WORKER_TOKEN=", out)

    def test_as_user_unknown_username_errors(self):
        with self.assertRaisesMessage(CommandError, "not found"):
            self._call(corpus=self.corpus.id, worker_name="rig-x", as_user="ghost")

    def test_as_user_non_superuser_errors(self):
        User.objects.create_user(username="plain_joe", password="p")
        with self.assertRaisesMessage(CommandError, "not a superuser"):
            self._call(corpus=self.corpus.id, worker_name="rig-x", as_user="plain_joe")

    def test_unreachable_corpus_surfaces_token_mint_error(self):
        # A nonexistent corpus id collapses onto the IDOR-safe "not found"
        # failure, which the command maps to a CommandError.
        with self.assertRaisesMessage(CommandError, "Could not mint token"):
            self._call(corpus=999999, worker_name="rig-badcorpus")

    def test_worker_account_creation_failure_surfaces_command_error(self):
        with mock.patch(
            f"{_CMD}.WorkerAccountService.create_worker_account",
            return_value=ServiceResult.failure("synthetic create failure"),
        ):
            with self.assertRaisesMessage(
                CommandError, "Could not create worker account"
            ):
                self._call(corpus=self.corpus.id, worker_name="rig-failcreate")


class MintWorkerTokenNoSuperuserTests(TestCase):
    """No acting superuser can be resolved → the command aborts up front."""

    def test_no_active_superuser_errors(self):
        # The migrated baseline may already contain a superuser; deactivate every
        # superuser inside this test's transaction so the default resolution path
        # genuinely finds none. (Rolled back at test teardown.)
        User.objects.filter(is_superuser=True).update(is_active=False)
        with self.assertRaisesMessage(CommandError, "No active superuser"):
            call_command(
                "mint_worker_token",
                corpus=1,
                worker_name="rig-nosu",
                stdout=StringIO(),
            )
