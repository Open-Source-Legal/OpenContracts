"""
Minimal object-store adapter used by the object-storage vector search engine.

The engine only needs five blob primitives (put/get/list/delete/exists), so we
adapt Django's Storage API rather than talking to boto3 directly. That means
the index transparently lives wherever ``STORAGE_BACKEND`` points it:

- ``LOCAL``  -> ``FileSystemStorage`` under ``MEDIA_ROOT`` (dev / CI)
- ``AWS``    -> S3 (or any S3-compatible store such as MinIO)
- ``GCP``    -> Google Cloud Storage

All keys are namespaced under ``settings.VECTOR_INDEX_STORAGE_PREFIX``.
"""

from __future__ import annotations

import logging
import posixpath

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import Storage, default_storage

from opencontractserver.constants.search import (
    OBJECT_STORE_PUT_OVERWRITE_MAX_ATTEMPTS,
)

logger = logging.getLogger(__name__)


class ObjectNotFound(Exception):
    """Raised when a requested key does not exist in the object store."""


class ObjectStoreWriteError(Exception):
    """Raised when an overwrite could not be committed (race retries exhausted)."""


class DjangoStorageObjectStore:
    """
    Blob-store primitives over a Django ``Storage`` instance.

    ``storage`` may be a lazy proxy (e.g. ``default_storage``) so that test
    overrides of ``STORAGES`` are honoured. ``prefix`` is resolved lazily from
    settings when not given explicitly, for the same reason.
    """

    def __init__(self, storage: Storage | None = None, prefix: str | None = None):
        self._storage = storage if storage is not None else default_storage
        self._prefix = prefix

    @property
    def prefix(self) -> str:
        if self._prefix is not None:
            return self._prefix
        return settings.VECTOR_INDEX_STORAGE_PREFIX

    def _full(self, key: str) -> str:
        return posixpath.join(self.prefix, key)

    def put_bytes(self, key: str, data: bytes) -> None:
        """
        Write ``data`` at ``key``, overwriting any existing blob.

        Django's ``Storage.save`` never overwrites (it uniquifies the name),
        so overwrite = delete-then-save. If a concurrent writer re-creates
        ``key`` between our delete and save, our blob lands under a
        uniquified stray name: discard the stray and retry the overwrite, so
        the terminal state is always exactly one blob at ``key``. Retries are
        bounded — the only mutable key is the manifest, whose writers are
        serialised by the compaction cache-lock, so contention here means
        that lock was breached (e.g. it expired mid-compaction); after the
        bound we raise ``ObjectStoreWriteError`` so the caller fails visibly
        (a compaction whose manifest never persisted must not report
        success) — the racing writer's blob, itself a valid manifest,
        remains in place.
        """
        name = self._full(key)
        for _ in range(OBJECT_STORE_PUT_OVERWRITE_MAX_ATTEMPTS):
            if self._storage.exists(name):
                self._storage.delete(name)
            saved_as = self._storage.save(name, ContentFile(data))
            if saved_as == name:
                return
            self._storage.delete(saved_as)
        raise ObjectStoreWriteError(
            f"Lost the overwrite race for {name} "
            f"{OBJECT_STORE_PUT_OVERWRITE_MAX_ATTEMPTS} times; the racing "
            "writer's blob was kept and this write was NOT committed."
        )

    def get_bytes(self, key: str) -> bytes:
        name = self._full(key)
        try:
            with self._storage.open(name, "rb") as fh:
                return fh.read()
        except FileNotFoundError as exc:
            raise ObjectNotFound(key) from exc

    def list_keys(self, dir_key: str) -> list[str]:
        """Return sorted file names (not full paths) directly under ``dir_key``."""
        name = self._full(dir_key)
        try:
            _dirs, files = self._storage.listdir(name)
        except FileNotFoundError:
            return []
        return sorted(files)

    def delete(self, key: str) -> None:
        name = self._full(key)
        try:
            self._storage.delete(name)
        except FileNotFoundError:
            # Delete is idempotent: a missing key is already deleted (e.g. a
            # concurrent compaction GC'd the same WAL file first).
            pass

    def exists(self, key: str) -> bool:
        return self._storage.exists(self._full(key))
