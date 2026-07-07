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

import posixpath

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import Storage, default_storage


class ObjectNotFound(Exception):
    """Raised when a requested key does not exist in the object store."""


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
        so delete-then-save is required for mutable keys (the manifest). WAL
        and segment keys are unique by construction, making the pattern safe.
        """
        name = self._full(key)
        if self._storage.exists(name):
            self._storage.delete(name)
        saved_as = self._storage.save(name, ContentFile(data))
        if saved_as != name:
            # A concurrent writer raced us between delete() and save() and the
            # backend uniquified our name. Last-writer-wins for mutable keys:
            # replace the existing blob with ours.
            self._storage.delete(name)
            with self._storage.open(saved_as, "rb") as fh:
                payload = fh.read()
            self._storage.delete(saved_as)
            self._storage.save(name, ContentFile(payload))

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
