"""Stored pack versions, rollback, live-process refresh and publication policy."""

import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Event
from unittest.mock import patch

import yaml
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import close_old_connections, connection
from django.test import TransactionTestCase, override_settings

from opencontractserver.annotations.models import (
    AuthorityPackActivation,
    AuthorityPackArtifact,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.enrichment.services.authority_pack_artifacts import (
    materialize_artifact,
)
from opencontractserver.enrichment.services.authority_pack_config import (
    pack_declared_shape_rules,
)
from opencontractserver.enrichment.services.authority_pack_service import (
    AuthorityPackService,
)
from opencontractserver.pipeline.registry import (
    get_all_authority_source_providers_cached,
)
from opencontractserver.users.models import User

PROVIDER = """from opencontractserver.pipeline.base.base_authority_source_provider import BaseAuthoritySourceProvider
class ManagedPackProvider(BaseAuthoritySourceProvider):
    title = "Managed {version}"
    description = "Fixture provider"
    author = "test"
    supported_prefixes = ("managed-pack",)
    def can_handle(self, key): return key.startswith("managed-pack:")
    def _locate_impl(self, key, **kwargs): raise NotImplementedError
    def _fetch_impl(self, request, **kwargs): raise NotImplementedError
"""


class PackActivationTests(TransactionTestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "managed_pack"
        self.source.mkdir()
        self.admin = User.objects.create_user(
            username="activation-admin", is_superuser=True, is_usage_capped=False
        )
        self.regular = User.objects.create_user(username="activation-reader")
        override = override_settings(
            AUTHORITY_PACK_MANAGED_DISCOVERY=True,
            AUTHORITY_PACK_PATHS=[str(self.source)],
            AUTHORITY_PACK_ROOTS=[],
            AUTHORITY_PACK_INSTALL_DIR=str(self.root / "installed"),
            AUTHORITY_PACK_CACHE_DIR=str(self.root / "cache"),
            MEDIA_ROOT=str(self.root / "storage"),
        )
        override.enable()
        self.addCleanup(override.disable)
        self.write_pack("v1")

    def write_pack(self, version, *, approved=False, sections=True):
        (self.source / "providers").mkdir(exist_ok=True)
        (self.source / "providers" / "managed.py").write_text(
            PROVIDER.format(version=version)
        )
        (self.source / "pack.yaml").write_text(
            yaml.safe_dump(
                {
                    "schema_version": 2,
                    "name": "managed_pack",
                    "version": version,
                    "mappings": "mappings.yaml",
                    "corpora": [
                        {
                            "slug": "managed-pack-corpus",
                            "title": "Managed pack corpus",
                            "charter": "charter.yaml",
                            "spec": "sections.json",
                        }
                    ],
                }
            )
        )
        (self.source / "charter.yaml").write_text(
            yaml.safe_dump(
                {
                    "purpose": "Regression fixture",
                    "approval_status": (
                        "approved" if approved else "pending_legal_review"
                    ),
                }
            )
        )
        (self.source / "sections.json").write_text(
            json.dumps(
                {
                    "sections": (
                        [
                            {
                                "key": "managed-pack:1",
                                "heading": f"Heading {version}",
                                "text": f"Body {version}",
                            }
                        ]
                        if sections
                        else []
                    )
                }
            )
        )
        (self.source / "mappings.yaml").write_text(
            yaml.safe_dump(
                {
                    "prefixes": {
                        "managed-pack": {
                            "display_name": "Managed pack",
                            "authority_type": "statute",
                            "jurisdiction": "test",
                        }
                    },
                    "equivalences": [],
                    "rewrite_rules": [],
                    "shape_rules": [
                        {
                            "pattern": "^managed-grammar$",
                            "jurisdiction": version,
                            "authority_type": "statute",
                        }
                    ],
                }
            )
        )

    def install(self, *, public=False):
        return AuthorityPackService.install_path(
            self.source, creator=self.admin, make_public=public, relink=False
        )

    def snapshot(self):
        plans = AuthorityPackService.catalog(self.admin)
        plan = next(p for p in plans if p.pack_id == "managed_pack")
        providers = [
            p.title
            for p in get_all_authority_source_providers_cached()
            if p.class_name.endswith(".ManagedPackProvider")
        ]
        grammar = [
            jurisdiction
            for pattern, jurisdiction, _ in pack_declared_shape_rules()
            if pattern.pattern == "^managed-grammar$"
        ]
        return plan.active_version, providers, grammar

    def child(self, cache_name):
        # This process has independent module caches and local extraction files.
        script = """import json, sys, django
django.setup()
from django.conf import settings
from django.db import connection
connection.close()
settings.DATABASES["default"]["NAME"] = sys.argv[1]
settings.AUTHORITY_PACK_MANAGED_DISCOVERY = True
settings.AUTHORITY_PACK_PATHS = []
settings.AUTHORITY_PACK_ROOTS = []
settings.AUTHORITY_PACK_INSTALL_DIR = sys.argv[2] + "/unused"
settings.AUTHORITY_PACK_CACHE_DIR = sys.argv[2]
settings.MEDIA_ROOT = sys.argv[3]
from opencontractserver.users.models import User
from opencontractserver.enrichment.services.authority_pack_service import AuthorityPackService
from opencontractserver.enrichment.services.authority_pack_config import pack_declared_shape_rules
from opencontractserver.pipeline.registry import get_all_authority_source_providers_cached
for line in sys.stdin:
    plans = AuthorityPackService.catalog(User.objects.get(pk=int(sys.argv[4])))
    plan = next(p for p in plans if p.pack_id == "managed_pack")
    providers = [p.title for p in get_all_authority_source_providers_cached()
                 if p.class_name.endswith(".ManagedPackProvider")]
    grammar = [j for pattern, j, _ in pack_declared_shape_rules() if pattern.pattern == "^managed-grammar$"]
    print(json.dumps([plan.active_version, providers, grammar]), flush=True)
"""
        process = subprocess.Popen(
            [
                sys.executable,
                "-u",
                "-c",
                script,
                connection.settings_dict["NAME"],
                str(self.root / cache_name),
                str(self.root / "storage"),
                str(self.admin.pk),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            env=os.environ.copy(),
        )

        def close():
            process.terminate()
            process.wait(timeout=10)

        self.addCleanup(close)
        return process

    def read_child(self, child):
        import select

        child.stdin.write("read\n")
        child.stdin.flush()
        self.assertTrue(
            select.select([child.stdout], [], [], 45)[0],
            "child failed to report a pack version",
        )
        return json.loads(child.stdout.readline())

    def test_restart_and_running_processes_observe_the_same_active_version_without_manual_cache_resets(
        self,
    ):
        self.install()
        self.assertEqual(self.snapshot(), ("v1", ["Managed v1"], ["v1"]))
        running = self.child("worker-cache")
        self.assertEqual(self.read_child(running), ["v1", ["Managed v1"], ["v1"]])
        self.write_pack("v2")
        self.install()
        shutil.rmtree(self.source)
        self.assertEqual(self.snapshot(), ("v2", ["Managed v2"], ["v2"]))
        self.assertEqual(self.read_child(running), ["v2", ["Managed v2"], ["v2"]])
        restarted = self.child("new-web-cache")
        self.assertEqual(self.read_child(restarted), ["v2", ["Managed v2"], ["v2"]])
        self.assertEqual(AuthorityPackArtifact.objects.count(), 2)

    def test_interrupted_activation_rolls_back_content_and_keeps_prior_artifact_with_visible_error(
        self,
    ):
        self.install()
        original = AuthorityPackActivation.objects.get(
            pack_id="managed_pack"
        ).active_artifact_id
        self.write_pack("v2")
        # Fail after all content writes but before the active pointer commits.
        with patch.object(
            AuthorityPackActivation,
            "save",
            side_effect=RuntimeError("interrupted activation"),
        ):
            with self.assertRaisesRegex(RuntimeError, "interrupted activation"):
                self.install()
        activation = AuthorityPackActivation.objects.get(pack_id="managed_pack")
        self.assertEqual(activation.active_artifact_id, original)
        self.assertIn("interrupted activation", activation.last_error)
        document = (
            Corpus.objects.get(slug="managed-pack-corpus")._get_active_documents().get()
        )
        with document.txt_extract_file.open("r") as text:
            self.assertEqual(text.read(), "Body v1")
        self.assertEqual(self.snapshot(), ("v1", ["Managed v1"], ["v1"]))
        self.assertEqual(
            AuthorityPackService.activation_status(self.admin)[0]["status"], "failed"
        )

    def test_concurrent_installs_serialize_database_content_and_active_artifact(self):
        barrier = Barrier(2)

        def install():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return self.install().pack.active_fingerprint
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            fingerprints = list(pool.map(lambda _: install(), range(2)))
        self.assertEqual(fingerprints[0], fingerprints[1])
        self.assertEqual(AuthorityPackActivation.objects.count(), 1)
        self.assertEqual(Corpus.objects.filter(slug="managed-pack-corpus").count(), 1)
        self.assertEqual(
            Corpus.objects.get(slug="managed-pack-corpus")
            ._get_active_documents()
            .count(),
            1,
        )

    def test_provider_change_after_preflight_is_rejected_before_activation(self):
        plan = AuthorityPackService.preflight_path(self.source, creator=self.admin)
        (self.source / "providers" / "managed.py").write_text(
            PROVIDER.format(version="changed")
        )
        with self.assertRaisesRegex(CommandError, "changed after preflight"):
            AuthorityPackService.install_path(
                self.source, creator=self.admin, expected_fingerprint=plan.fingerprint
            )
        self.assertFalse(AuthorityPackActivation.objects.exists())

    def test_storage_failure_and_invalid_stored_archive_cannot_activate_a_new_version(
        self,
    ):
        self.install()
        original = AuthorityPackActivation.objects.get().active_artifact_id
        self.write_pack("v2")
        with patch(
            "opencontractserver.enrichment.services.authority_pack_artifacts.materialize_artifact",
            side_effect=CommandError("digest failure"),
        ):
            with self.assertRaisesRegex(CommandError, "digest failure"):
                self.install()
        self.assertEqual(
            AuthorityPackActivation.objects.get().active_artifact_id, original
        )
        for member in ("../escape", "/absolute", "folder\\escape"):
            with self.subTest(member=member):
                archive = io.BytesIO()
                with zipfile.ZipFile(archive, "w") as zipped:
                    zipped.writestr(member, "invalid")
                artifact = AuthorityPackArtifact(
                    directory_name="safe",
                    digest=hashlib.sha256(archive.getvalue()).hexdigest(),
                )
                artifact.archive.save(
                    "bad.zip", ContentFile(archive.getvalue()), save=False
                )
                with self.assertRaisesRegex(CommandError, "Unsafe member"):
                    materialize_artifact(artifact)
        self.assertFalse((self.root / "escape").exists())

    def test_api_and_command_require_an_admin_and_approved_charters_for_publication(
        self,
    ):
        preflight = AuthorityPackService.preflight_path(self.source, creator=self.admin)
        for user in (self.regular, self.admin):
            with self.subTest(user=user.username):
                result = AuthorityPackService.install(
                    user,
                    pack_id="managed_pack",
                    expected_fingerprint=preflight.fingerprint,
                    publish=True,
                    relink=False,
                )
                self.assertFalse(result.ok)
                with self.assertRaises(CommandError):
                    call_command(
                        "load_authority_pack",
                        path=str(self.source),
                        creator=user.username,
                        public=True,
                        no_relink=True,
                        stdout=io.StringIO(),
                    )
        self.assertFalse(AuthorityPackArtifact.objects.exists())
        self.install()
        artifact = AuthorityPackActivation.objects.get().active_artifact
        assert artifact is not None
        self.assertEqual(
            artifact.charters["managed-pack-corpus"]["approval_status"],
            "pending_legal_review",
        )
        self.assertFalse(Corpus.objects.get(slug="managed-pack-corpus").is_public)
        self.assertEqual(AuthorityPackService.activation_status(self.regular), [])
        self.write_pack("v2", approved=True)
        call_command(
            "load_authority_pack",
            path=str(self.source),
            creator=self.admin.username,
            public=True,
            no_relink=True,
            stdout=io.StringIO(),
        )
        self.assertTrue(Corpus.objects.get(slug="managed-pack-corpus").is_public)
        self.write_pack("v3")
        with self.assertRaisesRegex(CommandError, "not approved"):
            self.install()  # Updating public content must satisfy the same policy.
        artifact = AuthorityPackActivation.objects.get().active_artifact
        assert artifact is not None
        self.assertEqual(artifact.version, "v2")

    def test_provider_import_gate_applies_to_restored_artifacts(self):
        self.install()
        shutil.rmtree(self.source)
        with override_settings(AUTHORITY_PACK_LOAD_PROVIDERS=False):
            self.assertEqual(self.snapshot(), ("v1", [], ["v1"]))

    def test_identical_archive_bytes_in_differently_named_packs_get_independent_complete_caches(
        self,
    ):
        from types import SimpleNamespace

        from opencontractserver.enrichment.services.authority_pack_artifacts import (
            persist_artifact,
        )

        # The archive has no directory-name entry; both ZIPs are byte-identical.
        original = AuthorityPackService.preflight_path(self.source, creator=self.admin)
        first = persist_artifact(original, self.admin)
        second = SimpleNamespace(
            **{
                field: getattr(first, field)
                for field in ("digest", "fingerprint", "archive")
            },
            directory_name="other_pack",
        )
        first_path = materialize_artifact(first)
        second_path = materialize_artifact(second, verify_storage=True)
        self.assertNotEqual(first_path.parent, second_path.parent)
        self.assertTrue((first_path / "pack.yaml").is_file())
        self.assertTrue((second_path / "pack.yaml").is_file())
        self.assertEqual(materialize_artifact(second), second_path)

    def test_tampered_cached_provider_is_rejected_before_a_fresh_registry_can_import_it(
        self,
    ):
        from opencontractserver.pipeline.registry import reset_registry

        self.install()
        artifact = AuthorityPackActivation.objects.get().active_artifact
        assert artifact is not None
        cached = materialize_artifact(artifact)
        provider = cached / "providers" / "managed.py"
        provider.chmod(0o644)
        sentinel = self.root / "untrusted-import"
        provider.write_text(
            f"from pathlib import Path\nPath({str(sentinel)!r}).write_text('executed')\n"
        )
        reset_registry()  # Simulate a new registry without trusting previous imports.
        for _ in range(2):
            with self.assertRaisesRegex(CommandError, "fingerprint validation"):
                get_all_authority_source_providers_cached()
        self.assertFalse(sentinel.exists())

    def test_false_completion_marker_is_rejected(self):
        self.install()
        artifact = AuthorityPackActivation.objects.get().active_artifact
        assert artifact is not None
        cached = materialize_artifact(artifact)
        (cached.parent / ".complete").write_text("another digest")
        with self.assertRaisesRegex(CommandError, "Incomplete authority pack"):
            materialize_artifact(artifact)

    def test_stale_failure_cannot_overwrite_a_newer_successful_activation_status(self):
        from django.db.models import QuerySet

        self.install()
        self.write_pack("v2")
        failing_source = self.root / "failed" / "managed_pack"
        shutil.copytree(self.source, failing_source)
        self.write_pack("v3")
        paused, release = Event(), Event()
        original_save, original_update = AuthorityPackActivation.save, QuerySet.update

        def fail_v2(activation, *args, **kwargs):
            if (
                activation.active_artifact
                and activation.active_artifact.version == "v2"
            ):
                raise RuntimeError("v2 failed")
            return original_save(activation, *args, **kwargs)

        def pause_failure(queryset, **kwargs):
            if (
                queryset.model is AuthorityPackActivation
                and kwargs.get("last_error") == "v2 failed"
            ):
                paused.set()
                if not release.wait(timeout=15):
                    raise RuntimeError("failure status was not released")
            return original_update(queryset, **kwargs)

        def failed_install():
            close_old_connections()
            try:
                AuthorityPackService.install_path(
                    failing_source, creator=self.admin, relink=False
                )
            finally:
                close_old_connections()

        with patch.object(AuthorityPackActivation, "save", fail_v2), patch.object(
            QuerySet, "update", pause_failure
        ):
            with ThreadPoolExecutor(max_workers=1) as pool:
                failure = pool.submit(failed_install)
                try:
                    self.assertTrue(paused.wait(timeout=15))
                    self.install()
                finally:
                    release.set()
                with self.assertRaisesRegex(RuntimeError, "v2 failed"):
                    failure.result(timeout=15)
        activation = AuthorityPackActivation.objects.get()
        assert activation.active_artifact is not None
        self.assertEqual(activation.active_artifact.version, "v3")
        self.assertEqual(activation.last_error, "")
        self.assertEqual(
            activation.attempted_fingerprint, activation.active_artifact.fingerprint
        )
