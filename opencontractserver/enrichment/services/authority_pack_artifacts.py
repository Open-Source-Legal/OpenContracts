"""Stored, immutable snapshots of trusted pack directories.

This module never accepts uploads or imports Python. Only the existing privileged
catalog/path installers create artifacts. Registry provider imports retain their
separate AUTHORITY_PACK_LOAD_PROVIDERS gate.
"""

from __future__ import annotations

import errno
import hashlib
import os
import shutil
import tempfile
import threading
import zipfile
from contextlib import contextmanager
from functools import lru_cache, wraps
from pathlib import Path, PurePosixPath
from uuid import uuid4

from django.apps import apps
from django.conf import settings
from django.core.files.base import File
from django.core.management.base import CommandError
from django.db import connection
from django.db.utils import ProgrammingError

MAX_FILES = 10000
MAX_BYTES = 512 * 1024 * 1024
_cache_lock = threading.RLock()


def artifact_files(root: Path) -> list[Path]:
    files = []
    size = 0
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if any(p.startswith(".") or p == "__pycache__" for p in relative.parts):
            continue
        if path.is_symlink():
            raise CommandError("Authority pack artifacts cannot contain symlinks")
        if path.is_file():
            files.append(path)
            size += path.stat().st_size
            if len(files) > MAX_FILES or size > MAX_BYTES:
                raise CommandError(
                    "Authority pack artifact exceeds its file or size limit"
                )
    return sorted(files)


@contextmanager
def snapshot_pack(plan):
    """Freeze all inputs before validation and installation; never read live files again."""
    with tempfile.TemporaryDirectory(prefix="oc-pack-stage-") as temporary:
        root = Path(temporary) / plan.pack_dir.name
        root.mkdir()
        for source in artifact_files(plan.pack_dir):
            target = root / source.relative_to(plan.pack_dir)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        yield root


def persist_artifact(plan, creator):
    from opencontractserver.annotations.models import AuthorityPackArtifact

    declarations = [f"corpus:{c.slug or c.title}" for c in plan.validated_corpora]
    declarations += [
        f"section:{c.slug or c.title}:{s.key}"
        for c in plan.validated_corpora
        for s in c.sections
    ]
    declarations += [
        f"relationship:{r['source_key']}:{r['relationship_type']}:{r['target_key']}"
        for r in plan.relationships
    ]
    if plan.mappings_path:
        from opencontractserver.enrichment.services.authority_pack_service import (
            AuthorityPackService,
        )

        mappings = AuthorityPackService._read_yaml_mapping(
            plan.mappings_path, label="mappings"
        )
        declarations += [f"prefix:{p}" for p in mappings.get("prefixes", {})]
    files = artifact_files(plan.pack_dir)
    artifact = AuthorityPackArtifact(
        pack_id=plan.pack_id,
        fingerprint=plan.fingerprint,
        version=str(plan.manifest.get("version") or plan.fingerprint)[:128],
        directory_name=plan.pack_dir.name,
        contains_code=any(p.suffix == ".py" for p in files),
        declarations=declarations,
        charters={c.slug or c.title: c.charter for c in plan.validated_corpora},
        creator=creator,
    )
    with tempfile.TemporaryFile() as archive:
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zipped:
            for path in files:
                zipped.write(path, path.relative_to(plan.pack_dir).as_posix())
        archive.seek(0)
        artifact.digest = hashlib.file_digest(archive, "sha256").hexdigest()
        archive.seek(0)
        artifact.archive.save(f"{uuid4()}.zip", File(archive), save=False)
    # Verify storage before the activation transaction can publish this version.
    materialize_artifact(artifact, verify_storage=True)
    artifact.save()
    return artifact


def materialize_artifact(artifact, *, verify_storage=False) -> Path:
    """Verify and safely extract shared storage into an expendable local cache."""
    if (
        not artifact.directory_name
        or Path(artifact.directory_name).name != artifact.directory_name
        or artifact.directory_name in (".", "..")
        or len(artifact.digest) != 64
        or any(c not in "0123456789abcdef" for c in artifact.digest)
    ):
        raise CommandError("Invalid authority pack artifact identity")
    root = Path(
        getattr(
            settings,
            "AUTHORITY_PACK_CACHE_DIR",
            Path(tempfile.gettempdir()) / "oc-authority-packs",
        )
    )
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    cache_key = hashlib.sha256(
        f"{artifact.digest}:{artifact.directory_name}".encode()
    ).hexdigest()
    destination = root / cache_key / artifact.directory_name

    def verify_tree():
        from opencontractserver.enrichment.services.authority_pack_service import (
            AuthorityPackService,
        )

        marker = destination.parent / ".complete"
        if (
            not marker.is_file()
            or marker.read_text() != artifact.digest
            or not (destination / "pack.yaml").is_file()
        ):
            raise CommandError(
                "Incomplete authority pack extraction cache; remove the cache and retry"
            )
        if (
            AuthorityPackService.declarative_fingerprint(destination)
            != artifact.fingerprint
        ):
            raise CommandError(
                "Cached authority pack failed fingerprint validation; remove the cache and retry"
            )

    with _cache_lock:
        if not verify_storage and destination.parent.exists():
            verify_tree()
            return destination
        with tempfile.TemporaryDirectory(prefix=".extract-", dir=root) as temporary:
            staging = Path(temporary)
            with tempfile.TemporaryFile() as local:
                with artifact.archive.open("rb") as source:
                    count = 0
                    while chunk := source.read(1024 * 1024):
                        count += len(chunk)
                        if count > MAX_BYTES:
                            raise CommandError(
                                "Stored authority pack archive exceeds its size limit"
                            )
                        local.write(chunk)
                local.seek(0)
                if hashlib.file_digest(local, "sha256").hexdigest() != artifact.digest:
                    raise CommandError(
                        "Stored authority pack archive failed digest validation"
                    )
                local.seek(0)
                with zipfile.ZipFile(local) as zipped:
                    members = zipped.infolist()
                    if (
                        len(members) > MAX_FILES
                        or sum(m.file_size for m in members) > MAX_BYTES
                    ):
                        raise CommandError(
                            "Stored authority pack archive exceeds extraction limits"
                        )
                    seen = set()
                    for member in members:
                        path = PurePosixPath(member.filename)
                        if (
                            path.is_absolute()
                            or ".." in path.parts
                            or "\\" in member.filename
                            or member.filename in seen
                            or member.is_dir()
                            or (member.external_attr >> 16) & 0o170000
                            not in (0, 0o100000)
                        ):
                            raise CommandError(
                                "Unsafe member in stored authority pack archive"
                            )
                        seen.add(member.filename)
                        target = staging / artifact.directory_name / path
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with zipped.open(member) as source, target.open("wb") as output:
                            shutil.copyfileobj(source, output)
                        target.chmod(0o444)
            if not (staging / artifact.directory_name / "pack.yaml").is_file():
                raise CommandError("Stored authority pack has no manifest")
            (staging / ".complete").write_text(artifact.digest)
            try:
                os.rename(staging, destination.parent)
            except OSError as exc:
                # Another process published this same content-addressed version.
                if (
                    exc.errno not in (errno.EEXIST, errno.ENOTEMPTY)
                    or not (destination.parent / ".complete").is_file()
                ):
                    raise
            verify_tree()
    return destination


def active_artifacts():
    if not apps.ready or not getattr(
        settings, "AUTHORITY_PACK_MANAGED_DISCOVERY", True
    ):
        return []
    from opencontractserver.annotations.models import AuthorityPackActivation

    try:
        return list(
            AuthorityPackActivation.objects.filter(active_artifact__isnull=False)
            .select_related("active_artifact")
            .order_by("pack_id")
        )
    except ProgrammingError as exc:
        if (
            connection.in_atomic_block
            or getattr(exc.__cause__, "pgcode", None) != "42P01"
        ):
            raise
        # The table is unavailable during first deployment/migration startup.
        return []


def active_revision():
    return (
        bool(getattr(settings, "AUTHORITY_PACK_LOAD_PROVIDERS", True)),
        tuple((row.pack_id, row.active_artifact_id) for row in active_artifacts()),
    )


def managed_paths():
    return {
        row.pack_id: materialize_artifact(row.active_artifact)
        for row in active_artifacts()
    }


def versioned_pack_cache(function):
    """Keep the existing cache-clear seam while including the shared active version."""

    @lru_cache(maxsize=1)
    def cached(revision):
        return function()

    @wraps(function)
    def wrapped():
        return cached(active_revision())

    setattr(wrapped, "cache_clear", cached.cache_clear)
    return wrapped
