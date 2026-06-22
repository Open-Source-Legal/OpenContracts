#!/usr/bin/env python3
"""
oc_bulk_import.py — resumable bulk-import driver for large local PDF corpora.

Feeds a local directory tree of PDFs into an OpenContracts corpus through the
existing ``POST /api/imports/zip-to-corpus/`` endpoint, which preserves the
folder hierarchy and runs the full parse pipeline (Docling/text -> PAWLs ->
embeddings). Designed for very large collections (hundreds of thousands of
files) where a single bulk upload is inappropriate.

Why this design (see scripts/bulk_import/README.md for the full rationale):

* The server has NO content de-duplication and NO queue backpressure, so the
  CLIENT owns resumability and pacing. A SQLite ledger records which batches
  landed; re-running skips finished work. Re-importing the same relative path
  upversions (new version, not a duplicate), so re-submitting a failed batch is
  safe.
* Files are packed into ZIPs that stay comfortably under the server's import
  caps (file count / total size / folder count). Each file's POSIX path
  relative to ``--root-dir`` becomes its ZIP arcname, which is exactly what the
  server turns into the corpus folder tree.
* The real bottleneck is parsing, not upload. The driver paces itself against
  the corpus's in-flight count (``documentStats.processingCount``) so the parse
  backlog stays bounded instead of detonating the whole collection at once.

Subcommands::

    plan     Scan the tree and compute the batch plan into the ledger (no network).
    run      Submit pending/failed batches (resumable, paced, concurrent).
    verify   Reconcile landed documents against the ledger; mark batches verified.
    status   Print ledger + live corpus counts.
    create-corpus   Convenience: create a corpus and print its global id.

Auth (three modes, in priority order — see ``OCClient``):

* ``--worker-token`` / ``OC_WORKER_TOKEN`` — a ``CorpusAccessToken`` sent to the
  import endpoints as ``Authorization: WorkerKey <token>``. The recommended mode
  and the only one that works on Auth0 backends. The corpus is taken from the
  token binding, so ``--corpus-id`` must reference it and ``create-corpus`` is
  unavailable (the corpus must pre-exist to mint a token).
* ``--token`` / ``OC_TOKEN`` — a raw JWT used for both REST and GraphQL.
* username/password (``OC_USERNAME`` / ``OC_PASSWORD``) — exchanged for a JWT via
  the ``tokenAuth`` GraphQL mutation (non-Auth0 only) and re-exchanged
  automatically on a 401, covering multi-day runs.

Dependencies: Python 3.9+ and ``requests`` (``pip install requests``).
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import logging
import os
import random
import sqlite3
import sys
import threading
import time
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import PurePosixPath
from zipfile import ZIP_DEFLATED, ZipFile

import requests

logger = logging.getLogger("oc_bulk_import")

# --- Defaults --------------------------------------------------------------
# Conservative per-ZIP targets, kept well under the server caps (1000 files /
# 500 MB / 500 folders) so a little server-side ancestor-folder counting or a
# few skipped entries never tips a batch over a hard limit. Raise the server
# caps via env (see README) before raising these.
DEFAULT_TARGET_FILES = 500
DEFAULT_TARGET_BYTES = 250 * 1024 * 1024
DEFAULT_TARGET_FOLDERS = 400

# Files at or above this size are skipped by the server's zip validator, so the
# driver routes them to the single-document endpoint instead. Mirrors the
# server's ZIP_MAX_SINGLE_FILE_SIZE_BYTES (default 100 MB) — keep in sync if that
# server cap is changed, or oversize files will be packed into ZIPs and silently
# dropped by the validator. (Override per-run with ``--single-file-cap``.)
DEFAULT_SINGLE_FILE_CAP = 100 * 1024 * 1024

# How many ZIPs to have in flight at once. Each 500-file ZIP injects ~500 parse
# tasks, so keep this small; the parse backlog — not HTTP — is the constraint.
DEFAULT_MAX_INFLIGHT = 4

# Backpressure: pause submitting when the corpus has more than HIGH documents
# still processing (backend_lock=True), resume once it drains below LOW.
DEFAULT_QUEUE_HIGH = 5000
DEFAULT_QUEUE_LOW = 2000

DEFAULT_MAX_ATTEMPTS = 5
# Comma-separated extension allowlist (split in _extensions); ".pdf" by default.
DEFAULT_EXTENSIONS = ".pdf"

# Retry/backoff for transient HTTP failures.
_BACKOFF_BASE_SECONDS = 2.0
_BACKOFF_CAP_SECONDS = 300.0
_HTTP_MAX_RETRIES = 6  # transient-failure attempts per HTTP request
# Backoff jitter multiplier range [_JITTER_MIN, _JITTER_MIN + _JITTER_SPAN).
_JITTER_MIN = 0.5
_JITTER_SPAN = 0.5
_HASH_BLOCK = 1024 * 1024

# Chunked-upload transport (mirrors the frontend importHttp.ts / UPLOAD consts).
# Large ZIP batches and oversize single files are sliced into parts that stay
# under any reverse-proxy body limit (Cloudflare: 100 MB) and the server's
# CHUNKED_UPLOAD_PART_MAX_BYTES (90 MB). A payload at or under the threshold is
# sent as one multipart POST; above it, via /api/imports/chunked/*.
# Deliberately equal (not a copy-paste slip): the threshold to *switch on*
# chunking equals the per-part size, so a payload that fits in a single part
# (``size <= CHUNK_THRESHOLD_BYTES`` -> exactly one chunk) is sent as one direct
# multipart POST instead, and only ``size > threshold`` (>= 2 parts) chunks.
CHUNK_SIZE_BYTES = 50 * 1024 * 1024
CHUNK_THRESHOLD_BYTES = 50 * 1024 * 1024
CHUNK_CONCURRENCY = 4
CHUNK_MAX_ATTEMPTS = 3
CHUNK_RETRY_BASE_SECONDS = 0.5

# Relay type name for corpus global ids (matches CorpusType in the schema).
_CORPUS_GRAPHQL_TYPE = "CorpusType"

# Ledger batch states (stored verbatim in the `batches.status` column):
#   PENDING    planned, not yet sent
#   SUBMITTED  accepted by the server (202), awaiting reconciliation
#   VERIFIED   confirmed landed in the corpus
#   FAILED     submission failed; re-sent on the next `run`
#   PARKED     retries exhausted; terminal — never re-sent automatically

# Member kinds.
KIND_ZIP = "zip"
KIND_OVERSIZE = "oversize_single"


# --- Helpers ---------------------------------------------------------------
def _to_global_corpus_id(value: str) -> str:
    """Return a Relay global id for GraphQL. A bare integer pk is encoded as
    ``base64("CorpusType:<pk>")``; an already-global id is returned unchanged.

    The REST import endpoints accept either form, but ``documentStats``'s
    ``inCorpusWithId`` filter decodes a global id with no pk fallback, so the
    CLI normalizes here to keep a numeric ``--corpus-id`` from crashing it."""
    s = str(value).strip()
    if s.isdigit():
        return base64.b64encode(f"{_CORPUS_GRAPHQL_TYPE}:{s}".encode()).decode()
    return s


def _should_chunk(size: int) -> bool:
    """Whether a payload is large enough to require the chunked endpoints."""
    return size > CHUNK_THRESHOLD_BYTES


def _iter_chunks(stream, chunk_size: int):
    """Yield successive byte slices of ``stream`` (a seekable file-like),
    rewinding it first. At most one ``chunk_size`` slice is held at a time."""
    stream.seek(0)
    while True:
        block = stream.read(chunk_size)
        if not block:
            return
        yield block


# --- Data structures -------------------------------------------------------
@dataclass
class FileEntry:
    """One local file selected for import."""

    rel_path: str  # POSIX path relative to root; becomes the ZIP arcname
    abs_path: str
    size: int
    kind: str
    sha256: str = ""


@dataclass
class Batch:
    """A planned unit of work: one ZIP, or one oversize single file."""

    batch_id: str
    kind: str
    members: list[FileEntry] = field(default_factory=list)

    @property
    def file_count(self) -> int:
        return len(self.members)

    @property
    def byte_size(self) -> int:
        return sum(m.size for m in self.members)


# --- Ledger ----------------------------------------------------------------
class Ledger:
    """SQLite-backed, crash-resumable record of batches and their members.

    Thread-safe via a single lock: ``run`` submits batches concurrently, but
    ledger writes are short, so serializing them is simpler and plenty fast.
    """

    def __init__(self, path: str) -> None:
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript("""
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );
                CREATE TABLE IF NOT EXISTS batches (
                    batch_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    job_id TEXT,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    file_count INTEGER NOT NULL,
                    byte_size INTEGER NOT NULL,
                    last_error TEXT,
                    created_at REAL,
                    submitted_at REAL,
                    verified_at REAL
                );
                CREATE TABLE IF NOT EXISTS members (
                    batch_id TEXT NOT NULL,
                    rel_path TEXT NOT NULL,
                    abs_path TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    sha256 TEXT,
                    kind TEXT NOT NULL,
                    PRIMARY KEY (batch_id, rel_path)
                );
                CREATE INDEX IF NOT EXISTS idx_batches_status
                    ON batches(status);
                """)
            self._conn.commit()

    # -- meta ---------------------------------------------------------------
    def get_meta(self, key: str) -> str | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM meta WHERE key = ?", (key,)
            ).fetchone()
        return row["value"] if row else None

    def set_meta(self, key: str, value: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO meta(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
            self._conn.commit()

    def set_meta_default(self, key: str, value: str) -> str:
        """Set ``key`` to ``value`` only if absent; return the effective value."""
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM meta WHERE key = ?", (key,)
            ).fetchone()
            if row is not None:
                return row["value"]
            self._conn.execute(
                "INSERT INTO meta(key, value) VALUES(?, ?)", (key, value)
            )
            self._conn.commit()
            return value

    # -- planning -----------------------------------------------------------
    def upsert_batches(self, batches: Iterable[Batch]) -> int:
        """Insert any not-yet-known batches. Existing rows are left untouched so
        status/attempts survive a re-plan. Returns the number newly inserted."""
        inserted = 0
        now = time.time()
        with self._lock:
            for batch in batches:
                cur = self._conn.execute(
                    "INSERT OR IGNORE INTO batches"
                    "(batch_id, kind, status, file_count, byte_size, created_at) "
                    "VALUES(?, ?, 'PENDING', ?, ?, ?)",
                    (
                        batch.batch_id,
                        batch.kind,
                        batch.file_count,
                        batch.byte_size,
                        now,
                    ),
                )
                if cur.rowcount:
                    inserted += 1
                    self._conn.executemany(
                        "INSERT OR IGNORE INTO members"
                        "(batch_id, rel_path, abs_path, size, sha256, kind) "
                        "VALUES(?, ?, ?, ?, ?, ?)",
                        [
                            (
                                batch.batch_id,
                                m.rel_path,
                                m.abs_path,
                                m.size,
                                m.sha256,
                                m.kind,
                            )
                            for m in batch.members
                        ],
                    )
            self._conn.commit()
        return inserted

    # -- selection ----------------------------------------------------------
    def batch_ids_to_submit(self) -> list[str]:
        """Batches still needing submission (PENDING or FAILED). SUBMITTED rows
        are left to ``verify`` so we never needlessly re-parse an accepted ZIP."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT batch_id FROM batches WHERE status IN ('PENDING','FAILED') "
                "ORDER BY batch_id"
            ).fetchall()
        return [r["batch_id"] for r in rows]

    def load_members(self, batch_id: str) -> list[FileEntry]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT rel_path, abs_path, size, sha256, kind FROM members "
                "WHERE batch_id = ? ORDER BY rel_path",
                (batch_id,),
            ).fetchall()
        return [
            FileEntry(
                r["rel_path"], r["abs_path"], r["size"], r["kind"], r["sha256"] or ""
            )
            for r in rows
        ]

    def batch_kind(self, batch_id: str) -> str:
        with self._lock:
            row = self._conn.execute(
                "SELECT kind FROM batches WHERE batch_id = ?", (batch_id,)
            ).fetchone()
        return row["kind"] if row else KIND_ZIP

    # -- state transitions --------------------------------------------------
    def mark_submitted(self, batch_id: str, job_id: str | None) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE batches SET status='SUBMITTED', job_id=?, "
                "attempts=attempts+1, submitted_at=?, last_error=NULL "
                "WHERE batch_id=?",
                (job_id, time.time(), batch_id),
            )
            self._conn.commit()

    def mark_failed(self, batch_id: str, error: str, max_attempts: int) -> bool:
        """Record a failed submission (attempts++). If retries are now exhausted,
        move the batch to the terminal PARKED state so it is excluded from future
        runs (otherwise it would be re-listed forever, failing each run). Returns
        True if the batch was parked."""
        with self._lock:
            self._conn.execute(
                "UPDATE batches SET status='FAILED', attempts=attempts+1, "
                "last_error=? WHERE batch_id=?",
                (error[:2000], batch_id),
            )
            row = self._conn.execute(
                "SELECT attempts FROM batches WHERE batch_id=?", (batch_id,)
            ).fetchone()
            parked = bool(row) and row["attempts"] >= max_attempts
            if parked:
                self._conn.execute(
                    "UPDATE batches SET status='PARKED' WHERE batch_id=?", (batch_id,)
                )
            self._conn.commit()
        return parked

    def mark_parked(self, batch_id: str) -> None:
        """Move a batch to the terminal PARKED state (retries exhausted)."""
        with self._lock:
            self._conn.execute(
                "UPDATE batches SET status='PARKED' WHERE batch_id=?", (batch_id,)
            )
            self._conn.commit()

    def mark_verified_all_submitted(self) -> int:
        with self._lock:
            cur = self._conn.execute(
                "UPDATE batches SET status='VERIFIED', verified_at=? "
                "WHERE status='SUBMITTED'",
                (time.time(),),
            )
            self._conn.commit()
            return cur.rowcount

    def attempts(self, batch_id: str) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT attempts FROM batches WHERE batch_id=?", (batch_id,)
            ).fetchone()
        return row["attempts"] if row else 0

    # -- reporting ----------------------------------------------------------
    def status_counts(self) -> dict[str, int]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT status, COUNT(*) AS n FROM batches GROUP BY status"
            ).fetchall()
        return {r["status"]: r["n"] for r in rows}

    def submitted_member_count(self) -> int:
        """Distinct files in SUBMITTED or VERIFIED batches — i.e. how many
        documents we expect to have landed in the corpus."""
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) AS n FROM members m JOIN batches b "
                "ON m.batch_id = b.batch_id "
                "WHERE b.status IN ('SUBMITTED','VERIFIED')"
            ).fetchone()
        return row["n"] if row else 0

    def total_member_count(self) -> int:
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) AS n FROM members").fetchone()
        return row["n"] if row else 0


# --- API client ------------------------------------------------------------
class APIError(Exception):
    pass


class OCClient:
    """Thin OpenContracts API client for the multipart/chunked import endpoints
    and the GraphQL queries the driver needs, with retry/backoff.

    Three auth modes (resolved by ``_make_client``), in priority order:

    * ``worker_token`` — a ``CorpusAccessToken`` sent to the REST/chunked import
      endpoints as ``Authorization: WorkerKey <token>``. GraphQL calls (only
      ``documentStats``, which needs no auth) go unauthenticated; ``create-corpus``
      is unavailable (the corpus must pre-exist to mint a token).
    * ``bearer_token`` — a raw JWT used for both REST and GraphQL (works on
      non-Auth0 backends, or on Auth0 with a real Auth0 token).
    * username/password — exchanged for a JWT via ``tokenAuth`` (non-Auth0 only);
      re-exchanged automatically on a 401 for multi-day runs.
    """

    _TOKEN_AUTH_QUERY = (
        "mutation($u:String!,$p:String!){tokenAuth(username:$u,password:$p){token}}"
    )
    _CREATE_CORPUS_QUERY = (
        "mutation($t:String!,$d:String){createCorpus(title:$t,description:$d)"
        "{ok message objId}}"
    )

    def __init__(
        self,
        api_base: str,
        timeout: int = 600,
        worker_token: str | None = None,
        bearer_token: str | None = None,
    ) -> None:
        self.api_base = api_base.rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()
        self._worker_token = worker_token
        self._token: str | None = bearer_token
        self._username: str | None = None
        self._password: str | None = None
        self._auth_lock = threading.Lock()

    def set_password_credentials(self, username: str, password: str) -> None:
        """Remember username/password so a 401 can trigger a re-exchange."""
        self._username = username
        self._password = password

    @property
    def _can_reauth(self) -> bool:
        return bool(self._username and self._password) and not self._worker_token

    # -- auth ---------------------------------------------------------------
    def authenticate(self, username: str, password: str) -> None:
        """Exchange username/password for a JWT via ``tokenAuth``.

        Only ``token`` is selected — the project does not install
        graphql_jwt's long-running ``refresh_token`` app, so requesting
        ``refreshToken`` makes the whole mutation error. Multi-day runs are
        covered by re-authenticating on a 401 (see ``_request``)."""
        self.set_password_credentials(username, password)
        data = self._graphql(
            self._TOKEN_AUTH_QUERY, {"u": username, "p": password}, _auth=False
        )
        token = (data.get("tokenAuth") or {}).get("token")
        if not token:
            raise APIError("tokenAuth returned no token (check credentials)")
        self._token = token
        # Do not log the username: static analysis taints it as
        # credential-derived. A static confirmation is enough.
        logger.info("Authenticated successfully")

    def rest_headers(self) -> dict[str, str]:
        """Auth header for the REST/chunked import endpoints."""
        if self._worker_token:
            return {"Authorization": f"WorkerKey {self._worker_token}"}
        if self._token:
            return {"Authorization": f"Bearer {self._token}"}
        return {}

    def graphql_headers(self) -> dict[str, str]:
        """Auth header for GraphQL. A WorkerKey is REST-only and is never sent
        here. A bearer JWT *is* used when present — including alongside a worker
        token — so ``documentStats`` (the only query used) can read a PRIVATE
        corpus's in-flight count for backpressure. With only a worker token the
        query runs unauthenticated, so a private corpus reports 0 and pacing is
        disabled (see the run-time warning in ``cmd_run`` and the README)."""
        if self._token:
            return {"Authorization": f"Bearer {self._token}"}
        return {}

    # -- transport ----------------------------------------------------------
    def _request(
        self,
        method: str,
        url: str,
        *,
        surface: str = "rest",
        _auth: bool = True,
        **kwargs,
    ):
        """One HTTP request with bounded exponential backoff. Honors Retry-After
        on 429, retries 5xx/network errors, and — in username/password mode only
        — re-authenticates once on a 401. ``surface`` selects the auth header set
        ('rest' -> WorkerKey/Bearer, 'graphql' -> Bearer or none)."""
        extra_headers = kwargs.pop("headers", {})
        files = kwargs.get("files")
        attempt = 0
        reauthed = False
        while True:
            attempt += 1
            # Rewind any multipart file streams so a retry re-sends the full
            # body — after the first send a BytesIO / file handle sits at EOF
            # and would otherwise upload nothing.
            if files:
                for value in files.values():
                    stream = value[1] if isinstance(value, (tuple, list)) else value
                    if hasattr(stream, "seek"):
                        stream.seek(0)
            auth_headers = {}
            if _auth:
                auth_headers = (
                    self.graphql_headers()
                    if surface == "graphql"
                    else self.rest_headers()
                )
            try:
                headers = {**auth_headers, **extra_headers}
                resp = self._session.request(
                    method, url, headers=headers, timeout=self.timeout, **kwargs
                )
            except requests.RequestException as exc:
                if attempt > _HTTP_MAX_RETRIES:
                    raise APIError(f"network error after {attempt} tries: {exc}")
                self._sleep_backoff(attempt)
                continue

            if resp.status_code == 401 and _auth:
                if not reauthed and self._can_reauth:
                    reauthed = True
                    with self._auth_lock:
                        try:
                            self.authenticate(self._username, self._password)
                            ok = True
                        except APIError:
                            ok = False
                    if ok:
                        attempt -= 1  # the re-auth round-trip shouldn't burn a retry
                        continue
                raise APIError(
                    "401 Unauthorized — the server rejected the credentials. "
                    "Supply a valid OC_WORKER_TOKEN or OC_TOKEN, or use "
                    "OC_USERNAME / OC_PASSWORD on a non-Auth0 backend."
                )

            if resp.status_code == 429:
                retry_after = resp.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else self._backoff(attempt)
                logger.warning("429 throttled; sleeping %.0fs", delay)
                time.sleep(min(delay, _BACKOFF_CAP_SECONDS))
                continue

            if resp.status_code >= 500:
                if attempt > _HTTP_MAX_RETRIES:
                    raise APIError(f"server {resp.status_code}: {resp.text[:300]}")
                self._sleep_backoff(attempt)
                continue

            return resp

    @staticmethod
    def _backoff(attempt: int) -> float:
        return min(_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)), _BACKOFF_CAP_SECONDS)

    def _sleep_backoff(self, attempt: int) -> None:
        # Jitter avoids synchronized retries across the in-flight pool.
        delay = self._backoff(attempt) * (_JITTER_MIN + random.random() * _JITTER_SPAN)
        time.sleep(delay)

    # -- graphql ------------------------------------------------------------
    def _graphql(self, query: str, variables: dict, *, _auth: bool = True) -> dict:
        resp = self._request(
            "POST",
            f"{self.api_base}/graphql/",
            surface="graphql",
            _auth=_auth,
            json={"query": query, "variables": variables},
        )
        if resp.status_code != 200:
            raise APIError(f"graphql HTTP {resp.status_code}: {resp.text[:300]}")
        body = resp.json()
        if body.get("errors"):
            raise APIError(f"graphql errors: {json.dumps(body['errors'])[:400]}")
        return body["data"]

    # -- high-level operations ---------------------------------------------
    def document_stats(self, corpus_id: str) -> dict[str, int]:
        query = (
            "query($c:String!){documentStats(inCorpusWithId:$c)"
            "{totalDocs processingCount processedCount}}"
        )
        # documentStats decodes inCorpusWithId as a Relay global id with no pk
        # fallback, so normalize a bare numeric id before sending.
        try:
            data = self._graphql(query, {"c": _to_global_corpus_id(corpus_id)})
        except APIError as exc:
            raise APIError(
                f"documentStats failed for corpus {corpus_id!r} (expected a "
                f"global id or numeric pk): {exc}"
            )
        return data["documentStats"]

    def create_corpus(self, title: str, description: str = "") -> str:
        data = self._graphql(self._CREATE_CORPUS_QUERY, {"t": title, "d": description})
        result = data["createCorpus"]
        if not result.get("ok"):
            raise APIError(f"createCorpus failed: {result.get('message')}")
        # DRFMutation returns a flat ``objId`` (a Relay global id), not obj{id}.
        return result["objId"]

    # -- chunked transport (ported from frontend importHttp.ts) -------------
    def _put_part(
        self, upload_id: str, index: int, filename: str, block: bytes
    ) -> None:
        resp = self._request(
            "PUT",
            f"{self.api_base}/api/imports/chunked/{upload_id}/parts/{index}/",
            files={
                "file": (
                    f"{filename}.part{index}",
                    BytesIO(block),
                    "application/octet-stream",
                )
            },
        )
        if resp.status_code not in (200, 201):
            raise APIError(
                f"chunked part {index} HTTP {resp.status_code}: {resp.text[:200]}"
            )

    def upload_in_chunks(
        self,
        kind: str,
        stream,
        filename: str,
        total_size: int,
        metadata: dict,
    ) -> dict:
        """Drive ``/api/imports/chunked/*`` for a large payload: ``start`` ->
        PUT each part (concurrently, retried via ``_request``, idempotent) ->
        ``complete``. Returns the parsed ``complete`` body, which has the same
        shape as the single-shot endpoint. ``stream`` must be a seekable binary
        file-like; parts are read on demand under a lock so peak memory stays
        ~``CHUNK_CONCURRENCY * CHUNK_SIZE_BYTES`` regardless of file size."""
        total_chunks = max(1, (total_size + CHUNK_SIZE_BYTES - 1) // CHUNK_SIZE_BYTES)
        start = self._request(
            "POST",
            f"{self.api_base}/api/imports/chunked/start/",
            json={
                "kind": kind,
                "filename": filename,
                "total_size": total_size,
                "chunk_size": CHUNK_SIZE_BYTES,
                "total_chunks": total_chunks,
                "metadata": metadata,
            },
        )
        if start.status_code not in (200, 201):
            raise APIError(
                f"chunked start HTTP {start.status_code}: {start.text[:300]}"
            )
        upload_id = start.json().get("upload_id")
        if not upload_id:
            raise APIError(f"chunked start returned no upload_id: {start.text[:200]}")

        read_lock = threading.Lock()

        def _put(index: int) -> None:
            with read_lock:
                stream.seek(index * CHUNK_SIZE_BYTES)
                block = stream.read(CHUNK_SIZE_BYTES)
            self._put_part(upload_id, index, filename, block)

        workers = min(CHUNK_CONCURRENCY, total_chunks)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            # list() forces evaluation so the first part failure propagates.
            list(pool.map(_put, range(total_chunks)))

        comp = self._request(
            "POST",
            f"{self.api_base}/api/imports/chunked/{upload_id}/complete/",
        )
        if comp.status_code not in (200, 201, 202):
            raise APIError(
                f"chunked complete HTTP {comp.status_code}: {comp.text[:300]}"
            )
        return comp.json()

    def submit_zip_to_corpus(
        self,
        corpus_id: str,
        zip_stream: BytesIO,
        filename: str,
        make_public: bool = False,
    ) -> str:
        """Submit a ZIP to the corpus, preserving folders. Large ZIPs go via the
        chunked endpoints; small ones via a single multipart POST. Returns the
        server job_id (audit only — not pollable; verify by corpus count).

        ``zip_stream`` is consumed in place; ``_request`` / the chunk reader
        rewind it as needed so retries re-send the full body."""
        zip_stream.seek(0, os.SEEK_END)
        size = zip_stream.tell()
        zip_stream.seek(0)
        if _should_chunk(size):
            body = self.upload_in_chunks(
                "zip_to_corpus",
                zip_stream,
                filename,
                size,
                {"corpus_id": corpus_id, "make_public": bool(make_public)},
            )
            if not body.get("ok", True):
                raise APIError(f"zip-to-corpus (chunked) rejected: {body}")
            return body.get("job_id", "")
        resp = self._request(
            "POST",
            f"{self.api_base}/api/imports/zip-to-corpus/",
            files={"file": (filename, zip_stream, "application/zip")},
            data={"corpus_id": corpus_id, "make_public": str(make_public).lower()},
        )
        if resp.status_code not in (200, 202):
            raise APIError(f"zip-to-corpus HTTP {resp.status_code}: {resp.text[:300]}")
        body = resp.json()
        if not body.get("ok", True):
            raise APIError(f"zip-to-corpus rejected: {body}")
        return body.get("job_id", "")

    def submit_single_document(
        self,
        corpus_id: str,
        file_path: str,
        title: str,
        make_public: bool = False,
        folder_path: str | None = None,
    ) -> None:
        """Submit one file to /api/imports/documents/ (oversize-file fallback).
        Files above the chunk threshold (which all >=100 MB oversize files are)
        stream via the chunked endpoints to avoid the server's in-memory buffer
        and any reverse-proxy body limit. ``folder_path`` (a POSIX path) places
        the document in the matching nested corpus folder."""
        basename = os.path.basename(file_path)
        size = os.path.getsize(file_path)
        if _should_chunk(size):
            metadata = {
                "title": title,
                "filename": basename,
                "add_to_corpus_id": corpus_id,
                "make_public": bool(make_public),
            }
            if folder_path:
                metadata["add_to_folder_path"] = folder_path
            with open(file_path, "rb") as fh:
                body = self.upload_in_chunks("document", fh, basename, size, metadata)
            if not body.get("ok", True):
                raise APIError(f"single-doc (chunked) rejected: {body}")
            return
        data = {
            "title": title,
            "filename": basename,
            "add_to_corpus_id": corpus_id,
            "make_public": str(make_public).lower(),
        }
        if folder_path:
            data["add_to_folder_path"] = folder_path
        with open(file_path, "rb") as fh:
            resp = self._request(
                "POST",
                f"{self.api_base}/api/imports/documents/",
                files={"file": (basename, fh)},
                data=data,
            )
        if resp.status_code not in (200, 201, 202):
            raise APIError(f"single-doc HTTP {resp.status_code}: {resp.text[:300]}")


# --- Scanning & batching ---------------------------------------------------
def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(_HASH_BLOCK), b""):
            h.update(block)
    return h.hexdigest()


def scan_files(
    root: str,
    extensions: set[str],
    single_file_cap: int,
    include_all: bool,
    compute_hash: bool,
) -> list[FileEntry]:
    """Walk ``root`` and select files, classifying oversize ones for the
    single-document fallback. Returns entries sorted by relative path so the
    batch plan is deterministic across runs."""
    root = os.path.abspath(root)
    entries: list[FileEntry] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Skip hidden directories in place (deterministic, avoids junk).
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for name in sorted(filenames):
            if name.startswith("."):
                continue
            ext = os.path.splitext(name)[1].lower()
            if not include_all and ext not in extensions:
                continue
            abs_path = os.path.join(dirpath, name)
            try:
                size = os.path.getsize(abs_path)
            except OSError:
                logger.warning("Cannot stat %s; skipping", abs_path)
                continue
            rel = PurePosixPath(os.path.relpath(abs_path, root).replace(os.sep, "/"))
            kind = KIND_OVERSIZE if size >= single_file_cap else KIND_ZIP
            sha = _sha256(abs_path) if compute_hash else ""
            entries.append(FileEntry(str(rel), abs_path, size, kind, sha))
    # Sort the full list authoritatively: os.walk ordering is platform-dependent
    # even though we sort within each directory, and the batch plan must be
    # byte-for-byte identical across runs/machines for the ledger to resume.
    entries.sort(key=lambda e: e.rel_path)
    return entries


def _ancestor_dirs(rel_path: str) -> set[str]:
    """Every folder the server must create for a file, e.g. ``a/b/c.pdf`` ->
    {``a``, ``a/b``}."""
    parent = PurePosixPath(rel_path).parent
    dirs: set[str] = set()
    while parent != PurePosixPath("."):
        dirs.add(str(parent))
        parent = parent.parent
    return dirs


def _batch_id(members: list[FileEntry]) -> str:
    """Content-addressed, resume-stable id from the sorted member paths."""
    h = hashlib.blake2b(digest_size=16)
    for m in sorted(members, key=lambda e: e.rel_path):
        h.update(m.rel_path.encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def plan_batches(
    entries: list[FileEntry],
    target_files: int,
    target_bytes: int,
    target_folders: int,
) -> list[Batch]:
    """Greedy, deterministic multi-constraint bin-packing. Entries are already
    sorted by relative path, so files in the same folder pack together and each
    ZIP touches few folders. A new batch is opened whenever adding the next file
    would breach ANY target."""
    batches: list[Batch] = []
    cur: list[FileEntry] = []
    cur_bytes = 0
    cur_dirs: set[str] = set()

    def flush() -> None:
        nonlocal cur, cur_bytes, cur_dirs
        if cur:
            batches.append(Batch(_batch_id(cur), KIND_ZIP, list(cur)))
            cur, cur_bytes, cur_dirs = [], 0, set()

    for entry in entries:
        if entry.kind == KIND_OVERSIZE:
            # Each oversize file is its own one-member batch (single-doc path).
            batches.append(Batch(_batch_id([entry]), KIND_OVERSIZE, [entry]))
            continue
        entry_dirs = _ancestor_dirs(entry.rel_path)
        new_dirs = cur_dirs | entry_dirs
        would_break = (
            len(cur) + 1 > target_files
            or cur_bytes + entry.size > target_bytes
            or len(new_dirs) > target_folders
        )
        if would_break:
            flush()
            new_dirs = entry_dirs
        cur.append(entry)
        cur_bytes += entry.size
        cur_dirs = new_dirs
    flush()
    return batches


def build_zip_stream(members: list[FileEntry]) -> BytesIO:
    """Build a ZIP in memory, writing each member at its relative path (arcname)
    so the server reconstructs the folder tree. Returns the buffer positioned at
    0, ready to stream to ``requests`` — avoiding the extra full-size copy that
    ``BytesIO.getvalue()`` would make (peak RAM stays ~1x the ZIP size)."""
    buf = BytesIO()
    with ZipFile(buf, "w", ZIP_DEFLATED) as zf:
        for m in members:
            zf.write(m.abs_path, arcname=m.rel_path)
    buf.seek(0)
    return buf


# --- Backpressure governor -------------------------------------------------
class QueueGovernor:
    """Blocks submission while the corpus parse backlog is too deep. Polls
    ``documentStats.processingCount`` at most once per interval and shares the
    reading across the in-flight pool."""

    def __init__(
        self,
        client: OCClient,
        corpus_id: str,
        high: int,
        low: int,
        poll_interval: float = 15.0,
    ) -> None:
        self._client = client
        self._corpus_id = corpus_id
        self._high = high
        self._low = low
        self._interval = poll_interval
        self._lock = threading.Lock()
        self._last_poll = 0.0
        self._processing = 0

    def _maybe_poll(self) -> int:
        now = time.time()
        with self._lock:
            if now - self._last_poll < self._interval:
                return self._processing
            # Claim the poll slot before releasing the lock so concurrent
            # workers see "recently polled" and reuse the cached value instead
            # of all issuing duplicate requests.
            self._last_poll = now

        # Poll OUTSIDE the lock — a slow request (up to the 600s timeout) must
        # not block every other worker that only wants the cached count.
        try:
            stats = self._client.document_stats(self._corpus_id)
        except APIError as exc:
            logger.warning("documentStats poll failed: %s", exc)
            # Reset the slot we claimed so the next caller retries immediately
            # instead of trusting a stale count for a full poll interval.
            with self._lock:
                self._last_poll = 0.0
            return self._processing
        with self._lock:
            self._processing = int(stats.get("processingCount", 0))
            return self._processing

    def wait(self) -> None:
        if self._high <= 0:
            return
        processing = self._maybe_poll()
        if processing <= self._high:
            return
        logger.info(
            "Backpressure: %d docs processing (> %d); pausing submission",
            processing,
            self._high,
        )
        while processing > self._low:
            time.sleep(self._interval)
            processing = self._maybe_poll()
        logger.info("Backpressure cleared: %d docs processing", processing)


class _NullGovernor:
    """No-op backpressure governor used for offline dry runs."""

    def wait(self) -> None:  # noqa: D401 - trivial
        return None


# --- Commands --------------------------------------------------------------
def _credentials(args: argparse.Namespace) -> tuple[str | None, str | None]:
    """Resolve (username, password) from flags or OC_USERNAME / OC_PASSWORD."""
    return (
        args.username or os.environ.get("OC_USERNAME"),
        args.password or os.environ.get("OC_PASSWORD"),
    )


def _worker_token(args: argparse.Namespace) -> str | None:
    return args.worker_token or os.environ.get("OC_WORKER_TOKEN")


def _bearer_token(args: argparse.Namespace) -> str | None:
    return args.token or os.environ.get("OC_TOKEN")


def _make_client(args: argparse.Namespace, *, require_auth: bool = True) -> OCClient:
    worker_token = _worker_token(args)
    bearer_token = _bearer_token(args)
    client = OCClient(
        args.api_base,
        timeout=args.timeout,
        worker_token=worker_token,
        bearer_token=bearer_token,
    )
    # A pre-supplied token carries its own credential — nothing to exchange.
    if worker_token or bearer_token:
        return client
    username, password = _credentials(args)
    if username and password:
        client.authenticate(username, password)
    elif require_auth:
        raise SystemExit(
            "Authentication required: set OC_WORKER_TOKEN (recommended for "
            "Auth0 / production), OC_TOKEN, or OC_USERNAME / OC_PASSWORD."
        )
    return client


def _extensions(args: argparse.Namespace) -> set[str]:
    return {
        e if e.startswith(".") else f".{e}"
        for e in (x.strip().lower() for x in args.ext.split(","))
        if e
    }


def cmd_plan(args: argparse.Namespace, ledger: Ledger) -> int:
    entries = scan_files(
        args.root_dir,
        _extensions(args),
        args.single_file_cap,
        args.all_files,
        args.hash,
    )
    if not entries:
        logger.error("No matching files under %s", args.root_dir)
        return 1
    batches = plan_batches(
        entries, args.target_files, args.target_bytes, args.target_folders
    )
    ledger.set_meta("root_dir", os.path.abspath(args.root_dir))
    inserted = ledger.upsert_batches(batches)

    zip_batches = [b for b in batches if b.kind == KIND_ZIP]
    oversize = [b for b in batches if b.kind == KIND_OVERSIZE]
    total_bytes = sum(e.size for e in entries)
    logger.info("Planned %d file(s), %.1f GB total", len(entries), total_bytes / 1e9)
    logger.info(
        "  %d ZIP batch(es), %d oversize single(s); %d new to ledger",
        len(zip_batches),
        len(oversize),
        inserted,
    )
    if zip_batches:
        max_files = max(b.file_count for b in zip_batches)
        max_gb = max(b.byte_size for b in zip_batches) / 1e9
        logger.info("  largest ZIP: %d files / %.2f GB", max_files, max_gb)
    return 0


def _process_batch(
    batch_id: str,
    ledger: Ledger,
    client: OCClient | None,  # None only on the offline dry-run path
    governor: QueueGovernor | _NullGovernor,
    corpus_id: str,
    make_public: bool,
    max_attempts: int,
    dry_run: bool,
) -> tuple[str, bool, str]:
    """Build + submit one batch. Returns (batch_id, ok, detail). ``client`` is
    only ``None`` for ``dry_run`` (the early returns below run before any call)."""
    # Safety net for a lowered --max-attempts between runs: park (terminal) so
    # the batch is not re-listed every run. Normal exhaustion is parked in the
    # except handler below.
    if ledger.attempts(batch_id) >= max_attempts:
        ledger.mark_parked(batch_id)
        return batch_id, False, "parked (retries exhausted)"

    members = ledger.load_members(batch_id)
    kind = ledger.batch_kind(batch_id)
    governor.wait()
    try:
        if kind == KIND_OVERSIZE:
            member = members[0]
            if dry_run:
                return batch_id, True, "dry-run (oversize)"
            # Preserve the file's folder: its POSIX parent becomes the nested
            # corpus folder (matching what the ZIP path does for non-oversize
            # files); the leaf name is the document title.
            rel = PurePosixPath(member.rel_path)
            parent = str(rel.parent)
            folder_path = None if parent == "." else parent
            client.submit_single_document(
                corpus_id,
                member.abs_path,
                rel.name,
                make_public,
                folder_path=folder_path,
            )
            ledger.mark_submitted(batch_id, None)
            return batch_id, True, "single doc submitted"

        if dry_run:
            build_zip_stream(members)  # validate construction, then discard
            return batch_id, True, f"dry-run ({len(members)} files)"
        zip_stream = build_zip_stream(members)
        job_id = client.submit_zip_to_corpus(
            corpus_id, zip_stream, f"{batch_id}.zip", make_public
        )
        ledger.mark_submitted(batch_id, job_id)
        return batch_id, True, f"{len(members)} files (job {job_id[:8]})"
    except APIError as exc:
        parked = ledger.mark_failed(batch_id, str(exc), max_attempts)
        prefix = "parked (retries exhausted): " if parked else ""
        return batch_id, False, f"{prefix}{exc}"


def cmd_run(args: argparse.Namespace, ledger: Ledger) -> int:
    if ledger.total_member_count() == 0:
        logger.info("Ledger empty; planning first.")
        rc = cmd_plan(args, ledger)
        if rc != 0:
            return rc

    _warn_if_root_moved(args, ledger)

    if args.dry_run:
        # Offline: build every ZIP to validate batching/construction, never
        # touching the network (no auth, baseline, or backpressure).
        client = None
        governor = _NullGovernor()
        logger.info("Dry run: building ZIPs without submitting.")
    else:
        client = _make_client(args)
        _check_corpus_consistency(args, ledger)
        # Capture a baseline so verification compares the delta, in case the
        # corpus was not empty when the import began.
        baseline = int(
            ledger.set_meta_default(
                "baseline_total_docs",
                str(client.document_stats(args.corpus_id).get("totalDocs", 0)),
            )
        )
        logger.info("Corpus baseline: %d existing document(s)", baseline)
        # Backpressure reads documentStats over GraphQL, which a WorkerKey
        # cannot authenticate. Without a bearer token a PRIVATE corpus reports
        # processingCount=0 to the governor, so pacing silently never engages.
        if _worker_token(args) and not _bearer_token(args):
            logger.warning(
                "Worker-token mode without a bearer token: documentStats is "
                "queried unauthenticated, so backpressure only works for a "
                "PUBLIC corpus. For a private corpus, also pass --token / "
                "OC_TOKEN (a JWT with READ on the corpus) to enable pacing."
            )
        governor = QueueGovernor(
            client, args.corpus_id, args.queue_high, args.queue_low
        )

    pending = ledger.batch_ids_to_submit()
    if not pending:
        logger.info("Nothing to submit; all batches already SUBMITTED/VERIFIED.")
        return 0
    logger.info(
        "Submitting %d batch(es) with %d in flight", len(pending), args.max_inflight
    )

    ok_count = fail_count = 0
    with ThreadPoolExecutor(max_workers=args.max_inflight) as pool:
        futures = {
            pool.submit(
                _process_batch,
                bid,
                ledger,
                client,
                governor,
                args.corpus_id,
                args.make_public,
                args.max_attempts,
                args.dry_run,
            ): bid
            for bid in pending
        }
        for fut in as_completed(futures):
            bid, ok, detail = fut.result()
            if ok:
                ok_count += 1
                logger.info("OK   %s  %s", bid[:12], detail)
            else:
                fail_count += 1
                logger.error("FAIL %s  %s", bid[:12], detail)

    logger.info("Run complete: %d submitted, %d failed", ok_count, fail_count)
    parked = ledger.status_counts().get("PARKED", 0)
    if parked:
        logger.warning(
            "%d batch(es) PARKED after exhausting --max-attempts; they will NOT "
            "be retried. Inspect with `status`, then re-run with a higher "
            "--max-attempts or import their files individually.",
            parked,
        )
    logger.info("Next: monitor parsing, then run `verify`.")
    return 0 if fail_count == 0 else 2


def cmd_verify(args: argparse.Namespace, ledger: Ledger) -> int:
    client = _make_client(args)
    _check_corpus_consistency(args, ledger)
    raw_baseline = ledger.get_meta("baseline_total_docs")
    baseline = int(raw_baseline or "0")
    expected = ledger.submitted_member_count()
    stats = client.document_stats(args.corpus_id)
    # The baseline (corpus doc count before the import) is recorded by `run`.
    # If it's missing while we expect docs to have landed, `landed` would be
    # inflated by any pre-existing documents — warn rather than false-VERIFY.
    if raw_baseline is None and expected and int(stats.get("totalDocs", 0)) > 0:
        logger.warning(
            "No baseline recorded (was `run` executed against this ledger?). "
            "Assuming the corpus started empty; verify counts manually if it "
            "already contained documents."
        )
    landed = int(stats.get("totalDocs", 0)) - baseline
    processing = int(stats.get("processingCount", 0))

    logger.info(
        "Expected %d doc(s); corpus shows %d landed (%d still processing)",
        expected,
        landed,
        processing,
    )
    if processing > 0:
        logger.info("Still parsing — re-run `verify` once processingCount hits 0.")
        return 1
    if landed >= expected:
        n = ledger.mark_verified_all_submitted()
        logger.info("Reconciled: marked %d batch(es) VERIFIED. Import complete.", n)
        return 0
    shortfall = expected - landed
    logger.warning(
        "Shortfall of %d doc(s). Some files were skipped (unsupported type) or a "
        "batch failed. Re-run `run` to re-submit unfinished batches (idempotent — "
        "same path upversions, no duplicates).",
        shortfall,
    )
    return 2


def cmd_status(args: argparse.Namespace, ledger: Ledger) -> int:
    counts = ledger.status_counts()
    logger.info("Ledger batches: %s", json.dumps(counts) if counts else "(none)")
    logger.info(
        "Expected documents (submitted/verified): %d", ledger.submitted_member_count()
    )
    # documentStats needs no auth, so live stats work in any mode (including a
    # worker-token run, whose GraphQL calls go unauthenticated).
    if args.corpus_id:
        try:
            client = _make_client(args, require_auth=False)
            stats = client.document_stats(args.corpus_id)
            logger.info(
                "Corpus: totalDocs=%s processing=%s processed=%s",
                stats.get("totalDocs"),
                stats.get("processingCount"),
                stats.get("processedCount"),
            )
        except (APIError, SystemExit) as exc:
            logger.warning("Could not fetch live corpus stats: %s", exc)
    return 0


def cmd_create_corpus(args: argparse.Namespace, ledger: Ledger) -> int:
    if _worker_token(args) and not (_bearer_token(args) or _credentials(args)[0]):
        raise SystemExit(
            "create-corpus needs a user credential (OC_TOKEN or "
            "OC_USERNAME / OC_PASSWORD). A worker token is scoped to one "
            "existing corpus and cannot create a corpus — create it in the "
            "UI/GraphQL first, then mint a CorpusAccessToken for it."
        )
    client = _make_client(args)
    corpus_id = client.create_corpus(args.title, args.description or "")
    logger.info("Created corpus: %s", corpus_id)
    print(corpus_id)
    return 0


def _warn_if_root_moved(args: argparse.Namespace, ledger: Ledger) -> None:
    stored = ledger.get_meta("root_dir")
    current = os.path.abspath(args.root_dir)
    if stored and stored != current:
        logger.warning(
            "Ledger was planned for root %s but --root-dir is %s. Member "
            "abs_paths come from the ledger; ensure files are still reachable.",
            stored,
            current,
        )


def _check_corpus_consistency(args: argparse.Namespace, ledger: Ledger) -> None:
    """Bind the ledger to one corpus on first use and warn on any later mismatch,
    so `verify` (or a second `run`) can't silently target the wrong corpus."""
    stored = ledger.set_meta_default("corpus_id", args.corpus_id)
    if stored != args.corpus_id:
        logger.warning(
            "This ledger was created for corpus %s but --corpus-id is %s. "
            "Counts and verification will not line up — double-check the target.",
            stored,
            args.corpus_id,
        )


# --- CLI -------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    # Global options live on a shared parent so they are accepted *after* the
    # subcommand (the natural position, e.g. ``plan --root-dir X --ledger Y``).
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--api-base",
        default=os.environ.get("OC_API_BASE", "http://localhost:8000"),
        help="OpenContracts base URL (default: env OC_API_BASE "
        "or http://localhost:8000).",
    )
    common.add_argument(
        "--ledger",
        default="./oc_ingest.db",
        help="SQLite ledger path (default: ./oc_ingest.db).",
    )
    common.add_argument(
        "--corpus-id",
        default=os.environ.get("OC_CORPUS_ID"),
        help="Target corpus id (PK or global id). Env: OC_CORPUS_ID.",
    )
    common.add_argument("--username", help="Login username (or env OC_USERNAME).")
    common.add_argument(
        "--password",
        help="Login password. PREFER env OC_PASSWORD: a value passed here is "
        "visible to other users on the host via `ps` / /proc/<pid>/cmdline.",
    )
    common.add_argument(
        "--worker-token",
        help="CorpusAccessToken for WorkerKey auth — the recommended mode for "
        "Auth0 / production (the corpus must already exist; mint a token for "
        "it). PREFER env OC_WORKER_TOKEN: a value passed here is visible to "
        "other users on the host via `ps` / /proc/<pid>/cmdline.",
    )
    common.add_argument(
        "--token",
        help="Raw JWT bearer token used for REST and GraphQL. PREFER env "
        "OC_TOKEN (same process-table exposure caveat as --worker-token).",
    )
    common.add_argument(
        "--timeout",
        type=int,
        default=600,
        help="Per-request timeout in seconds (default: 600).",
    )
    common.add_argument("-v", "--verbose", action="store_true")

    p = argparse.ArgumentParser(
        prog="oc_bulk_import",
        description="Resumable bulk import of a local PDF tree into OpenContracts.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    def add_scan_args(sp: argparse.ArgumentParser) -> None:
        sp.add_argument(
            "--root-dir", required=True, help="Local directory tree of PDFs to import."
        )
        sp.add_argument(
            "--ext",
            default=DEFAULT_EXTENSIONS,
            help="Comma-separated extensions to include "
            f"(default: {DEFAULT_EXTENSIONS}).",
        )
        sp.add_argument(
            "--all-files",
            action="store_true",
            help="Include every file regardless of extension.",
        )
        sp.add_argument(
            "--hash",
            action="store_true",
            help="Compute SHA-256 per file (slower; for integrity).",
        )
        sp.add_argument(
            "--single-file-cap",
            type=int,
            default=DEFAULT_SINGLE_FILE_CAP,
            help="Bytes; files >= this go to the single-doc endpoint.",
        )
        sp.add_argument("--target-files", type=int, default=DEFAULT_TARGET_FILES)
        sp.add_argument("--target-bytes", type=int, default=DEFAULT_TARGET_BYTES)
        sp.add_argument("--target-folders", type=int, default=DEFAULT_TARGET_FOLDERS)

    sp_plan = sub.add_parser(
        "plan", parents=[common], help="Scan and compute the batch plan."
    )
    add_scan_args(sp_plan)

    sp_run = sub.add_parser(
        "run", parents=[common], help="Submit pending/failed batches."
    )
    add_scan_args(sp_run)
    sp_run.add_argument("--max-inflight", type=int, default=DEFAULT_MAX_INFLIGHT)
    sp_run.add_argument(
        "--queue-high",
        type=int,
        default=DEFAULT_QUEUE_HIGH,
        help="Pause submitting above this many processing docs "
        "(0 disables backpressure).",
    )
    sp_run.add_argument("--queue-low", type=int, default=DEFAULT_QUEUE_LOW)
    sp_run.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS)
    sp_run.add_argument("--make-public", action="store_true")
    sp_run.add_argument(
        "--dry-run", action="store_true", help="Build ZIPs but do not submit."
    )

    # `verify` and `status` take only the shared options.
    sub.add_parser("verify", parents=[common], help="Reconcile landed docs vs ledger.")
    sub.add_parser("status", parents=[common], help="Print ledger + corpus counts.")

    sp_cc = sub.add_parser(
        "create-corpus", parents=[common], help="Create a corpus, print its id."
    )
    sp_cc.add_argument("--title", required=True)
    sp_cc.add_argument("--description", default="")

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    needs_corpus = args.command in {"run", "verify"} and not getattr(
        args, "dry_run", False
    )
    if needs_corpus and not args.corpus_id:
        raise SystemExit("--corpus-id (or OC_CORPUS_ID) is required for this command.")

    ledger = Ledger(args.ledger)
    handlers = {
        "plan": cmd_plan,
        "run": cmd_run,
        "verify": cmd_verify,
        "status": cmd_status,
        "create-corpus": cmd_create_corpus,
    }
    return handlers[args.command](args, ledger)


if __name__ == "__main__":
    sys.exit(main())
