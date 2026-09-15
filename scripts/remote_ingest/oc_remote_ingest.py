#!/usr/bin/env python3
"""Parse PDF, DOCX and TXT files remotely and upload prepared artifacts.

Reuses the application's parser implementations with worker-local settings and
no target database access. PDF text is reconstructed from PAWLS; DOCX/TXT retain
parser character spans. Local enrichers run before embedding and worker-upload.

Commands: plan scans extensions into a SQLite ledger; run prepares/uploads
pending or failed documents; verify polls receipts; status prints ledger counts.
Only run boots Django. See README.md for parser configuration and service setup.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import os
import random
import sqlite3
import sys
import threading
import time
from collections import Counter
from collections.abc import Generator, Mapping
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from contextlib import closing
from dataclasses import asdict, dataclass
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

import requests

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from opencontractserver.utils.embedding_validation import (  # noqa: E402
    embedding_batch,
    embedding_values,
    normalize_embedding_vector,
    validate_embedding_vector,
)
from scripts.remote_ingest.admission import (  # noqa: E402
    AdmissionGovernor,
    StatusPollError,
    retry_after_seconds,
    validate_watermarks,
)

if TYPE_CHECKING:  # avoid importing enrichers (needs Django path) at module load
    from enrichers import MetadataOverlay

    from scripts.remote_ingest.parsers import LocalParsers

logger = logging.getLogger("oc_remote_ingest")

# --- Defaults --------------------------------------------------------------
DEFAULT_EXTENSIONS = ".pdf"
DEFAULT_MAX_WORKERS = 4
DEFAULT_LEDGER_PAGE_SIZE = 256
FUTURES_PER_WORKER = 2
VERIFY_COMPLETE = 0
VERIFY_OUTSTANDING = 1
VERIFY_FAILED = 2
VERIFY_UNAVAILABLE = 3
VERIFY_SCHEMA_VERSION = 1
DEFAULT_EMBED_BATCH = 100
DEFAULT_MAX_ATTEMPTS = 5
# Token-scoped outstanding uploads: pause above HIGH, resume at/below LOW.
DEFAULT_QUEUE_HIGH = 2000
DEFAULT_QUEUE_LOW = 500
_HTTP_MAX_RETRIES = 6
_JITTER_MIN = 0.5
_HTTP_UPLOAD_TIMEOUT_SECONDS = 300
_HTTP_STATUS_TIMEOUT_SECONDS = 60
_HTTP_BACKLOG_TIMEOUT_SECONDS = 30
_HTTP_EMBED_SINGLE_TIMEOUT_SECONDS = 30
_HTTP_EMBED_BATCH_TIMEOUT_SECONDS = 120
_HTTP_INITIAL_BACKOFF_SECONDS = 2
_HTTP_MAX_BACKOFF_SECONDS = 60
_HTTP_DEFAULT_RETRY_AFTER_SECONDS = 60
_HTTP_MAX_RETRY_AFTER_SECONDS = 300

_CLAIMABLE_WHERE = "status IN ('PENDING', 'FAILED')"
_UNCONFIRMED_WHERE = "status='UPLOADED' AND upload_id IS NOT NULL"

# Ledger statuses
PENDING = "PENDING"
UPLOADED = "UPLOADED"  # staged on the server (202 accepted), not yet confirmed
COMPLETED = "COMPLETED"  # server confirmed terminal success
FAILED = "FAILED"  # retry-eligible
PARKED = "PARKED"  # retries exhausted (terminal)
AMBIGUOUS = "AMBIGUOUS"  # POST started; acceptance/receipt cannot be established
CONFLICT = "CONFLICT"  # changed source with an accepted or ambiguous prior version


# ======================================================================
# Ledger
# ======================================================================


class Ledger:
    """Crash-resumable SQLite ledger of per-document ingest state."""

    def __init__(self, path: str):
        self.path = path
        self._local = threading.local()
        # Create privately before SQLite can write; also harden legacy ledgers
        # and any existing recovery files before opening/recovering the database.
        fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            os.fchmod(fd, 0o600)
        finally:
            os.close(fd)
        for suffix in ("-wal", "-shm", "-journal"):
            try:
                os.chmod(path + suffix, 0o600)
            except FileNotFoundError:
                pass
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS docs (
                    rel_path   TEXT PRIMARY KEY,
                    abs_path   TEXT NOT NULL,
                    size       INTEGER,
                    sha256     TEXT,
                    status     TEXT NOT NULL DEFAULT 'PENDING',
                    upload_id  TEXT,
                    attempts   INTEGER NOT NULL DEFAULT 0,
                    page_count INTEGER,
                    last_error TEXT,
                    created_at REAL,
                    uploaded_at REAL,
                    completed_at REAL
                );
                CREATE INDEX IF NOT EXISTS idx_docs_status ON docs(status);
                CREATE INDEX IF NOT EXISTS idx_docs_claimable_path
                    ON docs(rel_path) WHERE status IN ('PENDING', 'FAILED');
                CREATE INDEX IF NOT EXISTS idx_docs_unconfirmed_path
                    ON docs(rel_path) WHERE status='UPLOADED' AND upload_id IS NOT NULL;
                CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
                PRAGMA journal_mode=WAL;
                PRAGMA synchronous=FULL;
                """)
            columns = {r["name"] for r in conn.execute("PRAGMA table_info(docs)")}
            for name in (
                "prior_status",
                "conflict_sha256",
                "client_key",
                "upload_digest",
            ):
                if name not in columns:
                    conn.execute(f"ALTER TABLE docs ADD COLUMN {name} TEXT")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_docs_ambiguous_path ON docs(rel_path) WHERE status='AMBIGUOUS'"
            )

    def _conn(self) -> sqlite3.Connection:
        # One connection per thread (sqlite connections are not thread-safe).
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.path, timeout=60, isolation_level=None)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA busy_timeout=60000;")
            # In particular, the pre-POST AMBIGUOUS marker must survive power loss.
            conn.execute("PRAGMA synchronous=FULL;")
            self._local.conn = conn
        return conn

    def set_meta(self, key: str, value: str) -> None:
        self._conn().execute(
            "INSERT INTO meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )

    def get_meta(self, key: str) -> str | None:
        row = (
            self._conn()
            .execute("SELECT value FROM meta WHERE key=?", (key,))
            .fetchone()
        )
        return row["value"] if row else None

    def upsert_doc(
        self, rel_path: str, abs_path: str, size: int, sha256: str, now: float
    ) -> bool:
        """Reconcile source versions. Return True only for a newly planned path.

        Accepted/unknown uploads retain their source hash and receipt on conflict.
        A server-rejected version (FAILED/PARKED) may be replaced safely.
        """
        cur = self._conn().execute(
            "INSERT INTO docs(rel_path, abs_path, size, sha256, status, created_at) "
            "VALUES(?, ?, ?, ?, 'PENDING', ?) "
            "ON CONFLICT(rel_path) DO NOTHING",
            (rel_path, abs_path, size, sha256, now),
        )
        if cur.rowcount > 0:
            return True
        row = self.get_doc(rel_path)
        if row["sha256"] == sha256:
            self._conn().execute(
                "UPDATE docs SET abs_path=?, size=?, "
                "status=COALESCE(prior_status, status), prior_status=NULL, "
                "conflict_sha256=NULL WHERE rel_path=?",
                (abs_path, size, rel_path),
            )
        elif (
            row["upload_id"]
            or row["upload_digest"]
            or row["status"]
            in (
                UPLOADED,
                COMPLETED,
                AMBIGUOUS,
                CONFLICT,
            )
        ):
            self._conn().execute(
                "UPDATE docs SET prior_status=COALESCE(prior_status, status), "
                "status='CONFLICT', conflict_sha256=?, abs_path=? WHERE rel_path=?",
                (sha256, abs_path, rel_path),
            )
            logger.error(
                "%s: source changed after upload; prior receipt retained. "
                "Resolve an explicit replace/new-document policy before continuing.",
                rel_path,
            )
        else:
            self._conn().execute(
                "UPDATE docs SET abs_path=?, size=?, sha256=?, status='PENDING', "
                "upload_id=NULL, attempts=0, page_count=NULL, last_error=NULL, "
                "uploaded_at=NULL, completed_at=NULL, prior_status=NULL, "
                "conflict_sha256=NULL, client_key=NULL, upload_digest=NULL WHERE rel_path=?",
                (abs_path, size, sha256, rel_path),
            )
        return False

    def get_doc(self, rel_path: str) -> sqlite3.Row:
        return (
            self._conn()
            .execute("SELECT * FROM docs WHERE rel_path=?", (rel_path,))
            .fetchone()
        )

    def mark_upload_started(
        self,
        rel_path: str,
        payload_digest: str | None = None,
        page_count: int | None = None,
    ) -> str | None:
        from uuid import uuid4

        row = self.get_doc(rel_path)
        if row["upload_digest"] and row["upload_digest"] != payload_digest:
            self._conn().execute(
                "UPDATE docs SET status='CONFLICT', "
                "last_error='Prepared payload changed after submission' WHERE rel_path=?",
                (rel_path,),
            )
            raise ValueError(
                "Prepared payload changed after submission; resolve the existing receipt"
            )
        client_key = (row["client_key"] or str(uuid4())) if payload_digest else None
        self._conn().execute(
            "UPDATE docs SET status='AMBIGUOUS', upload_id=NULL, "
            "uploaded_at=NULL, completed_at=NULL, client_key=?, upload_digest=?, "
            "page_count=COALESCE(?, page_count), "
            "last_error='Upload started; outcome unknown. Reconcile with the server before replay.' "
            "WHERE rel_path=?",
            (client_key, payload_digest, page_count, rel_path),
        )
        return client_key

    def mark_rejected(self, rel_path: str) -> None:
        self._conn().execute(
            "UPDATE docs SET status='FAILED', client_key=NULL, upload_digest=NULL "
            "WHERE rel_path=? AND status='AMBIGUOUS'",
            (rel_path,),
        )

    def mark_absent(self, rel_path: str) -> None:
        self._conn().execute(
            "UPDATE docs SET status='PENDING', last_error=NULL "
            "WHERE rel_path=? AND status='AMBIGUOUS'",
            (rel_path,),
        )

    def blocked_count(self) -> int:
        return self._count("status IN ('CONFLICT', 'AMBIGUOUS')")

    def _iter_rows(
        self, where: str, index: str, page_size: int
    ) -> Generator[sqlite3.Row]:
        """One pass in immutable path order; visited failures wait for the next run.

        Pages release their read cursor before yielding so worker writes neither
        shift an OFFSET nor keep a long-lived SQLite read snapshot/WAL open.
        One CLI invocation owns the ledger; concurrent plan/run/verify is unsupported.
        ``where``/``index`` are internal SQL constants, never operator input.
        """
        if page_size <= 0:
            raise ValueError("ledger page size must be positive")
        after = None
        while True:
            keyset = "" if after is None else " AND rel_path > ?"
            params = (page_size,) if after is None else (after, page_size)
            with closing(
                self._conn().execute(
                    # Force the matching path index: SQLite can otherwise choose the
                    # status index and re-sort the remaining ledger on every page.
                    f"SELECT * FROM docs INDEXED BY {index} "
                    f"WHERE {where}{keyset} ORDER BY rel_path LIMIT ?",
                    params,
                )
            ) as cursor:
                rows = cursor.fetchmany(page_size)
            if not rows:
                return
            after = rows[-1]["rel_path"]
            yield from rows
            if len(rows) < page_size:
                return
            del rows

    def _count(self, where: str) -> int:
        return (
            self._conn()
            .execute(f"SELECT COUNT(*) FROM docs WHERE {where}")
            .fetchone()[0]
        )

    def claimable_count(self) -> int:
        return self._count(_CLAIMABLE_WHERE)

    def ambiguous(
        self, page_size: int = DEFAULT_LEDGER_PAGE_SIZE
    ) -> Generator[sqlite3.Row]:
        where = "status='AMBIGUOUS' AND client_key IS NOT NULL"
        if self._count(where):
            yield from self._iter_rows(where, "idx_docs_ambiguous_path", page_size)

    def claimable(
        self, page_size: int = DEFAULT_LEDGER_PAGE_SIZE
    ) -> Generator[sqlite3.Row]:
        return self._iter_rows(_CLAIMABLE_WHERE, "idx_docs_claimable_path", page_size)

    def all_docs(
        self, page_size: int = DEFAULT_LEDGER_PAGE_SIZE
    ) -> Generator[sqlite3.Row]:
        return self._iter_rows("1=1", "sqlite_autoindex_docs_1", page_size)

    def uploaded_unconfirmed_count(self) -> int:
        return self._count(_UNCONFIRMED_WHERE)

    def uploaded_unconfirmed(
        self, page_size: int = DEFAULT_LEDGER_PAGE_SIZE
    ) -> Generator[sqlite3.Row]:
        return self._iter_rows(
            _UNCONFIRMED_WHERE, "idx_docs_unconfirmed_path", page_size
        )

    def mark_uploaded(
        self, rel_path: str, upload_id: str, page_count: int, now: float
    ) -> None:
        self._conn().execute(
            "UPDATE docs SET status='UPLOADED', upload_id=?, page_count=?, "
            "uploaded_at=?, last_error=NULL WHERE rel_path=?",
            (upload_id, page_count, now, rel_path),
        )

    def mark_completed(self, rel_path: str, now: float) -> None:
        self._conn().execute(
            "UPDATE docs SET status='COMPLETED', completed_at=? WHERE rel_path=?",
            (now, rel_path),
        )

    def mark_failed(self, rel_path: str, error: str, max_attempts: int) -> None:
        conn = self._conn()
        row = conn.execute(
            "SELECT attempts, status FROM docs WHERE rel_path=?", (rel_path,)
        ).fetchone()
        if row and row["status"] == AMBIGUOUS:
            conn.execute(
                "UPDATE docs SET last_error=? WHERE rel_path=?",
                (
                    f"Ambiguous upload; reconcile before replay: {error}"[:1000],
                    rel_path,
                ),
            )
            return  # Preparation retries must never authorize an uncertain POST replay.
        if row and row["status"] == CONFLICT:
            return
        attempts = (row["attempts"] if row else 0) + 1
        status = PARKED if attempts >= max_attempts else FAILED
        conn.execute(
            "UPDATE docs SET status=?, attempts=?, last_error=? WHERE rel_path=?",
            (status, attempts, error[:1000], rel_path),
        )

    def status_counts(self) -> dict[str, int]:
        rows = (
            self._conn()
            .execute("SELECT status, COUNT(*) AS n FROM docs GROUP BY status")
            .fetchall()
        )
        return {r["status"]: r["n"] for r in rows}


# ======================================================================
# Target client (worker-upload REST)
# ======================================================================


@dataclass
class Config:
    target_url: str
    worker_token: str
    corpus_id: str | None
    root_dir: str
    ledger_path: str
    extensions: tuple[str, ...]
    max_workers: int
    max_attempts: int
    queue_high: int
    queue_low: int
    embeddings: bool
    target_folder_from_tree: bool
    verify_tls: bool
    limit: int
    enrichers: list[str]
    parser_config: str | None = None
    ledger_page_size: int = DEFAULT_LEDGER_PAGE_SIZE
    enricher_identity: str | None = None
    embedding_identity: str | None = None
    embedding_dimension: int = 384
    parser_identity: str | None = None
    json_output: bool = False
    readiness: bool = False


class TargetClient:
    """HTTP client for the target's worker-upload endpoints with retry/backoff."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.base = cfg.target_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"WorkerKey {cfg.worker_token}"
        self._verify = cfg.verify_tls

    @staticmethod
    def _backoff(attempt: int) -> float:
        return min(
            _HTTP_INITIAL_BACKOFF_SECONDS * (2 ** (attempt - 1)),
            _HTTP_MAX_BACKOFF_SECONDS,
        ) * random.uniform(_JITTER_MIN, 1.0)

    def upload(
        self,
        source_bytes: bytes,
        metadata: dict,
        *,
        filename: str,
        idempotency_key: str | None = None,
    ) -> str:
        """Send the immutable preparation snapshot; never replay an uncertain POST.

        Only explicit 429 rejections are retried. A transport error, 5xx, redirect
        or unusable success receipt can follow acceptance and is ambiguous.
        """
        url = f"{self.base}/api/worker-uploads/documents/"
        meta_json = json.dumps(metadata, allow_nan=False)
        for attempt in range(1, _HTTP_MAX_RETRIES + 1):
            try:
                with BytesIO(source_bytes) as fh:
                    resp = self.session.post(
                        url,
                        files={"file": (filename, fh, metadata["file_type"])},
                        data={"metadata": meta_json},
                        headers=(
                            {"Idempotency-Key": idempotency_key}
                            if idempotency_key
                            else {}
                        ),
                        timeout=_HTTP_UPLOAD_TIMEOUT_SECONDS,
                        verify=self._verify,
                        allow_redirects=False,
                    )
            except requests.RequestException:
                raise AmbiguousUploadError(
                    "Upload response lost; reconcile server acceptance before replay"
                ) from None
            if resp.status_code == 202:
                try:
                    receipt = resp.json()["upload_id"]
                    if not isinstance(receipt, str) or not receipt.strip():
                        raise ValueError
                    return receipt
                except (ValueError, KeyError, TypeError):
                    raise AmbiguousUploadError(
                        "Upload accepted without a usable receipt; reconcile with server"
                    ) from None
            if resp.status_code == 429:
                if attempt < _HTTP_MAX_RETRIES:
                    try:
                        delay = float(
                            resp.headers.get(
                                "Retry-After", str(_HTTP_DEFAULT_RETRY_AFTER_SECONDS)
                            )
                        )
                        if not math.isfinite(delay) or delay < 0:
                            raise ValueError
                    except (ValueError, TypeError):
                        delay = self._backoff(attempt)
                    time.sleep(min(delay, _HTTP_MAX_RETRY_AFTER_SECONDS))
                continue
            if resp.status_code == 409:
                raise AmbiguousUploadError(
                    "Idempotency conflict; reconcile the existing key before changing the payload"
                )
            if 400 <= resp.status_code < 500:
                raise PermanentUploadError(f"Upload rejected: HTTP {resp.status_code}")
            raise AmbiguousUploadError(
                f"Upload outcome unknown: HTTP {resp.status_code}; reconcile before replay"
            )
        raise TransientUploadError("Upload rejected: rate limit retries exhausted")

    def _status_json(self, url: str, timeout: int) -> dict:
        """Shared safe HTTP classification; admission and verify choose policy."""
        try:
            resp = self.session.get(
                url, timeout=timeout, verify=self._verify, allow_redirects=False
            )
        except (
            requests.exceptions.InvalidURL,
            requests.exceptions.InvalidSchema,
            requests.exceptions.MissingSchema,
            requests.exceptions.InvalidHeader,
        ):
            raise StatusPollError(
                "Invalid status request; check --target-url and --worker-token configuration",
                permanent=True,
                reason="invalid_request",
            ) from None
        except requests.RequestException:
            raise StatusPollError(
                "Status network error or timeout", reason="network_error"
            ) from None
        code = resp.status_code
        if code != 200:
            if code == 429 or 500 <= code < 600:
                raise StatusPollError(
                    f"Status unavailable: HTTP {code}",
                    reason="rate_limited" if code == 429 else "server_unavailable",
                    http_status=code,
                    retry_after=retry_after_seconds(resp.headers.get("Retry-After")),
                )
            hint = (
                "check --worker-token / OC_WORKER_TOKEN and worker/token permissions"
                if code in (401, 403)
                else "check --target-url and worker-upload API configuration"
            )
            raise StatusPollError(
                f"Status HTTP {code}; {hint}",
                permanent=True,
                reason={401: "unauthorized", 403: "forbidden", 404: "not_found"}.get(
                    code, "http_error"
                ),
                http_status=code,
            )
        try:
            body = resp.json()
        except ValueError:
            raise StatusPollError("Invalid status response: malformed JSON") from None
        if not isinstance(body, dict):
            raise StatusPollError("Invalid status response: expected a JSON object")
        return body

    def upload_status(self, upload_id: str) -> dict:
        url = f"{self.base}/api/worker-uploads/documents/{upload_id}/"
        try:
            body = self._status_json(url, _HTTP_STATUS_TIMEOUT_SECONDS)
        except StatusPollError as exc:
            if exc.http_status == 404:
                raise StatusPollError(
                    "Receipt missing or inaccessible under the current worker token (HTTP 404)",
                    reason="not_found",
                    http_status=404,
                    permanent=True,
                ) from None
            raise
        if (
            body.get("upload_id") != upload_id
            or body.get("status")
            not in ("PENDING", "PROCESSING", "COMPLETED", "FAILED")
            or not isinstance(body.get("error_message", ""), str)
        ):
            raise StatusPollError("Invalid status response: receipt identity or state")
        return body

    def lookup_upload(self, client_key: str) -> dict | None:
        from urllib.parse import quote

        body = self._status_json(
            f"{self.base}/api/worker-uploads/documents/by-key/{quote(client_key, safe='')}/",
            _HTTP_STATUS_TIMEOUT_SECONDS,
        )
        if (
            body.get("schema_version") != 1
            or body.get("client_key") != client_key
            or type(body.get("found")) is not bool
        ):
            raise StatusPollError("Invalid upload lookup response")
        if not body["found"]:
            return None  # Only this explicit, authenticated envelope proves absence.
        if (
            not isinstance(body.get("upload_id"), str)
            or not body["upload_id"]
            or body.get("status") not in (PENDING, "PROCESSING", COMPLETED, FAILED)
        ):
            raise StatusPollError("Invalid upload lookup receipt")
        return body

    def retry_upload(self, upload_id: str) -> str:
        try:
            response = self.session.post(
                f"{self.base}/api/worker-uploads/documents/{upload_id}/retry/",
                timeout=_HTTP_STATUS_TIMEOUT_SECONDS,
                verify=self._verify,
                allow_redirects=False,
            )
            if response.status_code != 202:
                raise StatusPollError(
                    f"Receipt retry unavailable (HTTP {response.status_code})"
                )
            body = response.json()
        except (requests.RequestException, ValueError):
            raise StatusPollError(
                "Receipt retry response unavailable; retained original receipt"
            ) from None
        if not isinstance(body, dict) or body.get("upload_id") != upload_id:
            raise StatusPollError("Invalid retry receipt")
        return upload_id

    def readiness_status(self, upload_id: str) -> dict:
        body = self._status_json(
            f"{self.base}/api/readiness/worker/{upload_id}/",
            _HTTP_STATUS_TIMEOUT_SECONDS,
        )
        if (
            body.get("schema_version") != 1
            or body.get("upload_id") != upload_id
            or body.get("state")
            not in ("ready", "outstanding", "failed", "unavailable")
            or (body.get("state") == "ready" and not body.get("generation"))
        ):
            raise StatusPollError(
                "Invalid readiness response: identity, generation or state"
            )
        return body

    def backlog_count(self) -> int:
        """Worker/corpus PENDING + PROCESSING count, or StatusPollError.

        The two requests are not an atomic snapshot or a server-wide queue metric.
        Neither a partial aggregate nor an unavailable count is usable capacity.
        """
        total = 0
        for st in ("PENDING", "PROCESSING"):
            url = f"{self.base}/api/worker-uploads/documents/list/?status={st}&page_size=1"
            body = self._status_json(url, _HTTP_BACKLOG_TIMEOUT_SECONDS)
            count = body.get("count")
            if type(count) is not int or count < 0:
                raise StatusPollError(
                    "Invalid status response: expected a nonnegative integer count"
                )
            total += count
        return total


class PermanentUploadError(Exception):
    pass


class TransientUploadError(Exception):
    pass


class AmbiguousUploadError(Exception):
    pass


# ======================================================================
# Embedder client (vector-embedder microservice)
# ======================================================================


class EmbedderClient:
    """Thin HTTP client for the vector-embedder microservice."""

    def __init__(
        self,
        service_url: str,
        api_key: str | None,
        batch_size: int,
        *,
        dimension: int = 384,
        identity: str | None = None,
    ):
        self.base = service_url.rstrip("/")
        self.session = requests.Session()
        if api_key:
            self.session.headers["X-API-Key"] = api_key
        self.batch_size = batch_size
        self.dimension = dimension
        self.identity = identity

    def embed_text(self, text: str) -> list[float] | None:
        if not text or not text.strip():
            return None
        resp = self.session.post(
            f"{self.base}/embeddings",
            json={"text": text},
            timeout=_HTTP_EMBED_SINGLE_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        return self._coerce_vector(embedding_values(resp.json()))

    def _coerce_vector(self, vec) -> list[float]:
        return normalize_embedding_vector(vec, self.dimension)

    def embed_batch(self, texts: list[str]) -> list[list[float] | None]:
        """Embed a list of texts (sub-batched). Empty texts map to None."""
        out: list[list[float] | None] = [None] * len(texts)
        # indices with non-empty text
        idxs = [i for i, t in enumerate(texts) if t and t.strip()]
        for start in range(0, len(idxs), self.batch_size):
            chunk_idxs = idxs[start : start + self.batch_size]
            chunk_texts = [texts[i] for i in chunk_idxs]
            resp = self.session.post(
                f"{self.base}/embeddings/batch",
                json={"texts": chunk_texts},
                timeout=_HTTP_EMBED_BATCH_TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
            vecs = embedding_batch(resp.json(), len(chunk_idxs))
            for local_i, vec in enumerate(vecs):
                # The batch endpoint wraps each row one level deeper than the
                # single endpoint (per-item shape is ``[[...floats...]]``), so
                # coerce each row down to a flat numeric vector.
                coerced = self._coerce_vector(vec)
                out[chunk_idxs[local_i]] = coerced
        return out


# ======================================================================
# Parser wrapper (Django imports + worker-local configuration)
# ======================================================================


class _Parser:
    """Bootstrap Django imports, then use explicitly configured local parsers."""

    def __init__(
        self, config_path: str | None = None, identity: str | None = None
    ) -> None:
        self.config_path = config_path
        self.operator_identity = identity
        self._parsers: LocalParsers | None = None

    def ensure_ready(self) -> LocalParsers:
        if self._parsers is not None:
            return self._parsers
        repo_root = str(Path(__file__).resolve().parents[2])
        if repo_root not in sys.path:
            sys.path.insert(0, repo_root)
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.remote_worker")
        import django

        django.setup()
        from scripts.remote_ingest.parsers import LocalParsers

        parsers = LocalParsers(self.config_path, identity=self.operator_identity)
        parsers.require_checkpoint_identities()
        self._parsers = parsers
        return self._parsers

    @property
    def default_embedder_path(self) -> str:
        return self.ensure_ready().default_embedder_path

    def parse(self, source_bytes: bytes, *, filename: str) -> dict:
        return self.ensure_ready().parse(source_bytes, filename=filename)

    def identity(self, mime: str) -> dict:
        return self.ensure_ready().identity(mime)

    def source_mime(self, source_bytes: bytes, *, filename: str) -> str:
        return self.ensure_ready().source_mime(source_bytes, filename=filename)


# ======================================================================
# Payload construction
# ======================================================================

# Mirror save_parsed_data's structural-label definitions so the target
# auto-creates any labels the parser emitted with identical presentation.
_RELATIONSHIP_LABEL = "RELATIONSHIP_LABEL"
_DOC_TYPE_LABEL = "DOC_TYPE_LABEL"


def _build_metadata(
    *,
    title: str,
    export: dict,
    content: str,
    embedder_path: str,
    embeddings: dict | None,
    target_folder_path: str | None,
    parser_name: str,
    parser_version: str = "1.0",
    overlay: MetadataOverlay | None = None,
) -> dict:
    from django.conf import settings

    from scripts.remote_ingest.parsers import canonical_mime

    file_type = canonical_mime(export.get("file_type"))
    fallback = settings.ANNOTATION_LABELS.get(file_type, "SPAN_LABEL")
    labelled_text = export.get("labelled_text", []) or []
    relationships = export.get("relationships", []) or []
    doc_label_names = list(export.get("doc_labels", []) or [])

    # text_labels: token-annotation labels + relationship labels. _prepare_labels
    # on the server merges these into one lookup used by BOTH import_annotations
    # and import_relationships, so relationship labels must live here too.
    text_labels: dict[str, dict] = {}
    for ann in labelled_text:
        name = ann.get("annotationLabel")
        if name and name not in text_labels:
            text_labels[name] = {
                "label_type": ann.get("annotation_type") or fallback,
                "color": "grey",
                "description": "Parser Structural Label",
                "icon": "expand",
                "text": name,
                "read_only": True,
            }
    for rel in relationships:
        name = rel.get("relationshipLabel")
        if name and name not in text_labels:
            text_labels[name] = {
                "label_type": _RELATIONSHIP_LABEL,
                "color": "grey",
                "description": "Parser Relationship Label",
                "icon": "share-alt",
                "text": name,
                "read_only": True,
            }

    doc_labels_definitions: dict[str, dict] = {
        name: {
            "label_type": _DOC_TYPE_LABEL,
            "color": "grey",
            "description": "Parser Document Label",
            "icon": "tag",
            "text": name,
            "read_only": True,
        }
        for name in doc_label_names
    }

    custom_meta: dict = {}
    description = export.get("description", "") or ""
    if overlay is not None:
        # Enricher-supplied label definitions WIN over the generic parser
        # defaults so injected annotations/labels carry their intended
        # presentation (color/icon/description).
        text_labels.update(overlay.text_label_defs)
        doc_labels_definitions.update(overlay.doc_label_defs)
        if overlay.title:
            title = overlay.title
        if overlay.description:
            description = overlay.description
        custom_meta = overlay.custom_meta or {}

    metadata: dict = {
        "title": title,
        "description": description,
        "content": content,
        "page_count": export.get("page_count")
        or len(export.get("pawls_file_content", [])),
        "file_type": file_type,
        "pawls_file_content": export.get("pawls_file_content", []),
        "labelled_text": labelled_text,
        "relationships": relationships,
        "doc_labels": doc_label_names,
        "text_labels": text_labels,
        "doc_labels_definitions": doc_labels_definitions,
        "parser_name": parser_name,
        "parser_version": parser_version,
    }
    if target_folder_path:
        metadata["target_folder_path"] = target_folder_path
    if embeddings:
        metadata["embeddings"] = embeddings
    if custom_meta:
        metadata["custom_meta"] = custom_meta
    if overlay is not None and overlay.metadata:
        metadata["metadata"] = overlay.metadata
    return metadata


def _compute_embeddings(
    *,
    embedder: EmbedderClient,
    embedder_path: str,
    content: str,
    labelled_text: list,
) -> dict:
    """Compute the doc-level + per-annotation embeddings the server would store."""
    ann_ids = _embedding_ids(labelled_text)
    try:
        doc_vec = embedder.embed_text(content)
        _validate_vector(doc_vec, embedder.dimension)
    except ValueError as exc:
        raise ValueError(f"Document embedding: {exc}") from exc
    vecs = embedder.embed_batch(
        [ann["rawText"] for ann in labelled_text if ann["rawText"].strip()]
    )
    if not isinstance(vecs, list) or len(vecs) != len(ann_ids):
        raise ValueError(
            "Embedding batch cardinality does not match eligible annotations"
        )
    payload = {
        "embedder_path": embedder_path,
        "model_identity": embedder.identity,
        "document_embedding": doc_vec,
        "annotation_embeddings": dict(zip(ann_ids, vecs)),
    }
    _validate_embeddings(payload, labelled_text, embedder.dimension, embedder_path)
    return payload


def _embedding_ids(annotations: list) -> list[str]:
    ids = set()
    eligible = []
    for ann in annotations:
        aid = ann.get("id")
        if type(aid) not in (str, int) or aid == "" or str(aid) in ids:
            raise ValueError(
                "Embeddings require unique string/integer annotation IDs (including JSON keys)"
            )
        ids.add(str(aid))
        if ann["rawText"].strip():
            eligible.append(str(aid))
    return eligible


def _validate_vector(vector, dimension: int) -> None:
    validate_embedding_vector(vector, dimension)


def _validate_embeddings(payload, annotations, dimension, embedder_path) -> None:
    if not isinstance(payload, dict) or payload.get("embedder_path") != embedder_path:
        raise ValueError("Embedding payload is missing or has an incompatible embedder")
    _validate_vector(payload.get("document_embedding"), dimension)
    vectors = payload.get("annotation_embeddings", {})
    if not isinstance(vectors, dict) or set(vectors) != set(
        _embedding_ids(annotations)
    ):
        raise ValueError("Embedding coverage does not match eligible annotation IDs")
    for annotation_id, vector in vectors.items():
        try:
            _validate_vector(vector, dimension)
        except ValueError as exc:
            raise ValueError(f"Annotation {annotation_id!r} embedding: {exc}") from exc


# ======================================================================
# Scanning
# ======================================================================


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _scan(root: str, extensions: tuple[str, ...]):
    """Stream depth-first in filesystem order, without following directory links.

    Retain only one scandir iterator per depth, even for a very wide directory.
    Closing the generator (e.g. at --limit) closes every open directory handle.
    """
    root_path = Path(root).resolve()
    stack = [os.scandir(root_path)]
    try:
        while stack:
            entry = next(stack[-1], None)
            if entry is None:
                stack.pop().close()
            elif entry.is_dir(follow_symlinks=False):
                stack.append(os.scandir(entry.path))
            elif entry.is_file():
                path = Path(entry.path)
                if path.suffix.lower() in extensions:
                    yield path.relative_to(root_path).as_posix(), str(path)
    finally:
        for entries in stack:
            entries.close()


# ======================================================================
# Subcommands
# ======================================================================


def cmd_plan(cfg: Config) -> int:
    ledger = Ledger(cfg.ledger_path)
    ledger.set_meta("root_dir", str(Path(cfg.root_dir).resolve()))
    if cfg.corpus_id:
        ledger.set_meta("corpus_id", cfg.corpus_id)
    now = time.time()
    added = scanned = 0
    with closing(_scan(cfg.root_dir, cfg.extensions)) as paths:
        for rel, abs_path in paths:
            scanned += 1
            size = os.path.getsize(abs_path)
            # sha256 is recorded for provenance/dedup; cheap enough at plan time.
            if ledger.upsert_doc(rel, abs_path, size, _sha256(abs_path), now):
                added += 1
            if cfg.limit and added >= cfg.limit:
                logger.info(f"reached --limit {cfg.limit}; stopping scan")
                break
            if scanned % 500 == 0:
                logger.info(f"planned {scanned} files ({added} new)…")
    logger.info(f"plan complete: scanned={scanned}, new={added}")
    _print_status(ledger, None)
    return 1 if ledger.blocked_count() else 0


def _process_one(
    cfg: Config,
    parser: _Parser,
    embedder: EmbedderClient | None,
    client: TargetClient,
    row: sqlite3.Row | Mapping[str, Any],
    enrichers: list | None = None,
    ledger: Ledger | None = None,
) -> tuple[str, bool, str]:
    """Prepare/upload and persist the receipt. Return (path, ok, receipt or error)."""
    from scripts.remote_ingest.checkpoints import (
        Checkpoints,
        digest,
        implementation_digest,
    )
    from scripts.remote_ingest.parsers import normalize_and_validate_export

    rel_path = row["rel_path"]
    owns_ledger = ledger is None
    ledger = ledger or Ledger(cfg.ledger_path)
    try:
        current = ledger.get_doc(rel_path)
        if current["upload_id"] and current["status"] == FAILED:
            upload_id = client.retry_upload(current["upload_id"])
            ledger.mark_uploaded(
                rel_path, upload_id, current["page_count"], time.time()
            )
            return (rel_path, True, upload_id)
        abs_path = current["abs_path"]
        # Immutable snapshot: neither parser nor uploader reopens the mutable path.
        source_bytes = Path(abs_path).read_bytes()
        source_digest = digest(source_bytes)
        ledger.upsert_doc(
            rel_path, abs_path, len(source_bytes), source_digest, time.time()
        )
        current = ledger.get_doc(rel_path)
        if current["status"] not in (PENDING, FAILED):
            return (
                rel_path,
                False,
                f"{current['status']}: source/receipt requires reconciliation",
            )

        filename = PurePosixPath(rel_path).name
        mime = parser.source_mime(source_bytes, filename=filename)
        identity = parser.identity(mime)
        cache = Checkpoints(cfg.ledger_path, rel_path)
        export, parsed_digest = cache.stage(
            "parse",
            [source_digest, filename, identity],
            lambda: parser.parse(source_bytes, filename=filename),
            normalize_and_validate_export,
        )

        from enrichers import (
            EnricherContext,
            MetadataOverlay,
            apply_enrichment,
            run_enrichers,
            validate_enrichment,
        )

        def enrich():
            overlay = MetadataOverlay()
            if enrichers:
                ctx = EnricherContext(
                    rel_path=rel_path,
                    abs_path=abs_path,
                    export=export,
                    content=export["content"],
                )
                enrichment = run_enrichers(enrichers, ctx)
                errors = validate_enrichment(export, enrichment)
                if errors:
                    raise ValueError("enrichment invalid: " + "; ".join(errors[:5]))
                overlay = apply_enrichment(export, enrichment)
            return {"export": export, "overlay": asdict(overlay)}

        def validate_enriched(value):
            normalize_and_validate_export(value["export"])
            overlay = MetadataOverlay(**value["overlay"])
            if not all(
                isinstance(v, dict)
                for v in (
                    overlay.custom_meta,
                    overlay.text_label_defs,
                    overlay.doc_label_defs,
                )
            ) or not isinstance(overlay.metadata, list):
                raise ValueError("Invalid cached enrichment overlay")

        if enrichers and not cfg.enricher_identity:
            raise ValueError(
                "--enricher-identity must describe the effective enricher configuration"
            )
        enriched, enriched_digest = cache.stage(
            "enrich",
            [
                parsed_digest,
                rel_path,
                abs_path,
                cfg.enricher_identity,
                [(name, implementation_digest(fn)) for name, fn in (enrichers or [])],
                implementation_digest(apply_enrichment),
            ],
            enrich,
            validate_enriched,
        )
        export = enriched["export"]
        overlay = MetadataOverlay(**enriched["overlay"])
        embeddings = None
        if cfg.embeddings:
            if embedder is None:
                raise ValueError("Remote embeddings enabled without an embedder")
            embeddings, _ = cache.stage(
                "embed",
                [
                    enriched_digest,
                    parser.default_embedder_path,
                    embedder.base,
                    embedder.identity,
                    embedder.dimension,
                    implementation_digest(type(embedder).__init__),
                ],
                lambda: _compute_embeddings(
                    embedder=embedder,
                    embedder_path=parser.default_embedder_path,
                    content=export["content"],
                    labelled_text=export.get("labelled_text", []),
                ),
                lambda value: _validate_embeddings(
                    value,
                    export.get("labelled_text", []),
                    embedder.dimension,
                    parser.default_embedder_path,
                ),
            )

        parent = PurePosixPath(rel_path).parent.as_posix()
        metadata = _build_metadata(
            title=filename,
            export=export,
            content=export["content"],
            embedder_path=parser.default_embedder_path,
            embeddings=embeddings,
            target_folder_path=(
                parent
                if cfg.target_folder_from_tree and parent not in (".", "")
                else None
            ),
            overlay=overlay,
            parser_name=identity["parser_name"],
            parser_version=identity["parser_version"],
        )
        # Bind the receipt to source, semantic output, and effective preparation
        # settings. Only hashes cross the network; settings can contain secrets.
        from opencontractserver.utils.upload_identity import upload_payload_digest
        from scripts.remote_ingest.checkpoints import fingerprint

        metadata["preparation_identity"] = fingerprint(
            [
                identity,
                cfg.enricher_identity,
                cfg.embedding_identity,
                embedder.base if embedder else None,
                embedder.dimension if embedder else None,
            ]
        )
        payload_digest = upload_payload_digest(source_digest, metadata)
        client_key = ledger.mark_upload_started(
            rel_path, payload_digest, metadata["page_count"]
        )
        upload_id = client.upload(
            source_bytes, metadata, filename=filename, idempotency_key=client_key
        )
        page_count = metadata["page_count"]
        ledger.mark_uploaded(rel_path, upload_id, page_count, time.time())
        return (rel_path, True, upload_id)
    except (PermanentUploadError, TransientUploadError) as e:
        # Rejecting a replay says nothing about an earlier POST still in flight.
        if not current["client_key"]:
            ledger.mark_rejected(rel_path)
        return (rel_path, False, str(e))
    except Exception as e:  # noqa: BLE001 — ambiguous rows stay unclaimable
        return (rel_path, False, str(e))
    finally:
        if owns_ledger:
            ledger._conn().close()


def _reconcile_ambiguous(
    ledger: Ledger,
    client: TargetClient,
    row,
    *,
    replay_absent: bool = False,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> None:
    if row["status"] != AMBIGUOUS or not row["client_key"]:
        return
    receipt = client.lookup_upload(row["client_key"])
    if receipt is None:
        if replay_absent:
            ledger.mark_absent(row["rel_path"])
        return
    if receipt.get("payload_digest") != row["upload_digest"]:
        raise StatusPollError(
            "Upload lookup payload does not match the durable local digest"
        )
    ledger.mark_uploaded(
        row["rel_path"], receipt["upload_id"], row["page_count"], time.time()
    )
    if receipt["status"] == COMPLETED:
        ledger.mark_completed(row["rel_path"], time.time())
    elif receipt["status"] == FAILED:
        ledger.mark_failed(
            row["rel_path"],
            f"server: {receipt.get('error_message') or 'failed'}",
            max_attempts,
        )


def cmd_run(cfg: Config) -> int:
    try:
        validate_watermarks(cfg.queue_high, cfg.queue_low)
    except ValueError as watermark_error:
        logger.error("%s", watermark_error)
        return 2
    ledger = Ledger(cfg.ledger_path)
    client = TargetClient(cfg)
    for ambiguous_row in ledger.ambiguous(cfg.ledger_page_size):
        try:
            _reconcile_ambiguous(
                ledger,
                client,
                ambiguous_row,
                replay_absent=True,
                max_attempts=cfg.max_attempts,
            )
        except StatusPollError as lookup_error:
            logger.error(
                "%s: %s; upload remains ambiguous",
                ambiguous_row["rel_path"],
                lookup_error,
            )
    if not ledger.claimable_count():
        if _print_status(ledger, client if cfg.queue_high > 0 else None) == 2:
            return 2
        return 1 if ledger.blocked_count() else 0
    parser = _Parser(cfg.parser_config, cfg.parser_identity)
    # Set up Django + the parser eagerly so config errors (missing service URL,
    # broken enricher import) surface before we start churning documents.
    parser.ensure_ready()

    enrichers: list = []
    if cfg.enrichers:
        if not cfg.enricher_identity:
            raise ValueError(
                "--enricher-identity is required with --enricher; include configuration/data versions"
            )
        from enrichers import load_enrichers

        enrichers = load_enrichers(cfg.enrichers)
        logger.info(
            f"loaded {len(enrichers)} enricher(s): "
            + ", ".join(name for name, _ in enrichers)
        )

    embedder = None
    if cfg.embeddings:
        if not cfg.embedding_identity:
            raise ValueError(
                "--embedding-identity is required: identify the deployed model/service revision"
            )
        from opencontractserver.annotations.models import EMBEDDING_DIMENSIONS

        if cfg.embedding_dimension not in {dim for dim, _ in EMBEDDING_DIMENSIONS}:
            raise ValueError("--embedding-dimension is not supported by server storage")
        embedder = EmbedderClient(
            os.environ.get(
                "EMBEDDINGS_MICROSERVICE_URL", "http://vector-embedder:8000"
            ),
            os.environ.get("VECTOR_EMBEDDER_API_KEY") or None,
            DEFAULT_EMBED_BATCH,
            dimension=cfg.embedding_dimension,
            identity=cfg.embedding_identity,
        )
    total = ledger.claimable_count()
    if not total:
        logger.info("nothing to do — run `plan` first or everything is done.")
        if _print_status(ledger, client if cfg.queue_high > 0 else None) == 2:
            return 2
        return 1 if ledger.blocked_count() else 0

    window = FUTURES_PER_WORKER * cfg.max_workers
    logger.info(
        f"run: {total} docs to process with {cfg.max_workers} workers "
        f"(future window={window}, ledger page size={cfg.ledger_page_size}) "
        f"(embeddings={'on' if cfg.embeddings else 'off'}, "
        f"enrichers={len(enrichers)})"
    )

    governor = AdmissionGovernor(client.backlog_count, cfg.queue_high, cfg.queue_low)
    stop_event = governor.stopped

    done = {"ok": 0, "fail": 0}
    done_lock = threading.Lock()

    def worker(row: sqlite3.Row) -> None:
        # A grant is atomic with polling/pausing; only admitted work uses attempts.
        if not governor.admit() or stop_event.is_set():
            return
        rel, ok, msg = _process_one(
            cfg, parser, embedder, client, row, enrichers, ledger
        )
        if ok:
            with done_lock:
                done["ok"] += 1
                n = done["ok"] + done["fail"]
            logger.info(f"[{n}/{total}] uploaded {rel} -> {msg}")
        else:
            ledger.mark_failed(rel, msg, cfg.max_attempts)
            with done_lock:
                done["fail"] += 1
                n = done["ok"] + done["fail"]
            logger.warning(f"[{n}/{total}] FAILED {rel}: {msg}")

    todo = ledger.claimable(cfg.ledger_page_size)
    pool = ThreadPoolExecutor(max_workers=cfg.max_workers)
    pending: set[Future[None]] = set()
    exhausted = interrupted = False
    try:
        while not stop_event.is_set() and (pending or not exhausted):
            while not stop_event.is_set() and not exhausted and len(pending) < window:
                row = next(todo, None)
                if row is None:
                    exhausted = True
                    break
                if stop_event.is_set():
                    break
                pending.add(pool.submit(worker, row))
            if stop_event.is_set() or not pending:
                break
            finished, pending = wait(pending, return_when=FIRST_COMPLETED)
            for future in finished:
                exc = future.exception()
                if exc is not None:
                    logger.error("worker crashed: %s", governor.fatal_error or exc)
                    with done_lock:
                        done["fail"] += 1
            finished.clear()
            del future
    except KeyboardInterrupt:
        interrupted = True
    finally:
        governor.stop()
        for future in pending:
            future.cancel()
        todo.close()
        if interrupted:
            logger.info(
                "interrupted: cancelling queued work; waiting for at most "
                f"{cfg.max_workers} already-running document/status calls"
            )
        # Avoid the context manager's unconditional wait on governor-paused work.
        # In-flight preparation/uploads finish and persist their ledger transitions.
        pool.shutdown(wait=True, cancel_futures=True)

    if interrupted:
        _print_status(ledger, None)
        return 130

    if governor.fatal_error is not None:
        logger.error("Admission stopped: %s", governor.fatal_error)
        _print_status(ledger, None)
        return 2

    logger.info(f"run complete: uploaded={done['ok']}, failed={done['fail']}")
    if _print_status(ledger, client if cfg.queue_high > 0 else None) == 2:
        return 2
    return 0 if done["fail"] == 0 and not ledger.blocked_count() else 1


def _verification_state(status: str) -> tuple[int, str]:
    return {
        COMPLETED: (VERIFY_COMPLETE, "completed"),
        PENDING: (VERIFY_OUTSTANDING, "not_uploaded"),
        UPLOADED: (VERIFY_OUTSTANDING, "receipt_outstanding"),
        FAILED: (VERIFY_FAILED, "failed"),
        PARKED: (VERIFY_FAILED, "parked"),
        AMBIGUOUS: (VERIFY_FAILED, "ambiguous_upload"),
        CONFLICT: (VERIFY_FAILED, "source_conflict"),
    }.get(status, (VERIFY_UNAVAILABLE, "unknown_ledger_state"))


def cmd_verify(cfg: Config) -> int:
    """Verify the whole ledger, streaming bounded document results before a summary.

    Receipt unavailability is observational: never change state, attempts, receipt,
    timestamps or last_error without a valid response. Final ledger state governs
    success, including failures moved out of UPLOADED on an earlier invocation.
    """
    ledger = Ledger(cfg.ledger_path)
    client = TargetClient(cfg)
    reasons: Counter[str] = Counter()
    unavailable = 0
    readiness_code = VERIFY_COMPLETE
    for row in ledger.all_docs(cfg.ledger_page_size):
        receipt_status = None
        poll_error = None
        try:
            _reconcile_ambiguous(ledger, client, row, max_attempts=cfg.max_attempts)
            row = ledger.get_doc(row["rel_path"])
        except StatusPollError as exc:
            poll_error = exc
        if row["status"] == UPLOADED:
            try:
                if not row["upload_id"]:
                    raise StatusPollError(
                        "Uploaded row has no receipt; reconcile with the server",
                        reason="missing_receipt",
                    )
                receipt = client.upload_status(row["upload_id"])
                receipt_status = receipt["status"]
                if receipt_status == COMPLETED:
                    ledger.mark_completed(row["rel_path"], time.time())
                elif receipt_status == FAILED:
                    ledger.mark_failed(
                        row["rel_path"],
                        f"server: {receipt.get('error_message') or 'failed'}",
                        cfg.max_attempts,
                    )
                if receipt_status in (COMPLETED, FAILED):
                    row = ledger.get_doc(row["rel_path"])
            except StatusPollError as exc:
                poll_error = exc
        code, reason = _verification_state(row["status"])
        detail = row["last_error"]
        if poll_error is not None:
            code, reason = VERIFY_UNAVAILABLE, poll_error.reason
            detail = str(poll_error)
        elif receipt_status in ("PENDING", "PROCESSING"):
            reason = f"receipt_{receipt_status.lower()}"
        readiness = None
        if cfg.readiness and code == VERIFY_COMPLETE:
            try:
                if not row["upload_id"]:
                    raise StatusPollError(
                        "Completed row has no receipt", reason="missing_receipt"
                    )
                readiness = client.readiness_status(row["upload_id"])
                code = {
                    "ready": VERIFY_COMPLETE,
                    "outstanding": VERIFY_OUTSTANDING,
                    "failed": VERIFY_FAILED,
                    "unavailable": VERIFY_UNAVAILABLE,
                }[readiness["state"]]
                reason = f"readiness_{readiness['state']}"
                detail = readiness.get("reasons", [])
            except StatusPollError as exc:
                poll_error = exc
                code, reason, detail = VERIFY_UNAVAILABLE, exc.reason, str(exc)
            readiness_code = max(readiness_code, code)
        unavailable += int(code == VERIFY_UNAVAILABLE)
        reasons[reason] += 1
        record = {
            "type": "document",
            "schema_version": VERIFY_SCHEMA_VERSION,
            "rel_path": row["rel_path"],
            "status": row["status"],
            "upload_id": row["upload_id"],
            "receipt_status": receipt_status,
            "reason": reason,
            "detail": detail,
            "http_status": poll_error.http_status if poll_error else None,
        }
        if cfg.readiness:
            record["readiness"] = readiness
        if cfg.json_output:
            print(json.dumps(record, ensure_ascii=True))
        elif code != VERIFY_COMPLETE:
            print(f"{row['rel_path']!r}: {reason}" + (f" ({detail})" if detail else ""))

    # Status counts are bounded by ledger states, not document count. A failed
    # receipt remains a failure on the next pass even though it is no longer polled.
    counts = ledger.status_counts()
    code = max(
        (_verification_state(status)[0] for status in counts),
        default=VERIFY_COMPLETE,
    )
    code = max(code, readiness_code)
    if unavailable:
        code = VERIFY_UNAVAILABLE
    total = sum(counts.values())
    outcome = {
        VERIFY_COMPLETE: "complete" if total else "empty",
        VERIFY_OUTSTANDING: "outstanding",
        VERIFY_FAILED: "failed",
        VERIFY_UNAVAILABLE: "unable_to_verify",
    }[code]
    summary = {
        "type": "summary",
        "schema_version": VERIFY_SCHEMA_VERSION,
        "scope": "whole_ledger",
        "completion_boundary": (
            "search_readiness" if cfg.readiness else "worker_upload_transaction"
        ),
        "outcome": outcome,
        "exit_code": code,
        "total": total,
        "counts": counts,
        "reason_counts": dict(reasons),
        "unavailable": unavailable,
    }
    if cfg.json_output:
        print(json.dumps(summary, sort_keys=True))
    else:
        print(
            f"verify: {outcome}; {counts.get(COMPLETED, 0)}/{total} worker uploads "
            f"completed; unavailable={unavailable}; exit={code}"
        )
    return code


def cmd_cleanup(cfg: Config) -> int:
    from scripts.remote_ingest.checkpoints import Checkpoints

    ledger = Ledger(cfg.ledger_path)
    removed = 0
    for row in ledger.all_docs(cfg.ledger_page_size):
        removed += Checkpoints(cfg.ledger_path, row["rel_path"], create=False).prune()
    logger.info(
        "cleanup: removed %s unreferenced artifacts older than 24 hours", removed
    )
    return 0


def cmd_status(cfg: Config) -> int:
    ledger = Ledger(cfg.ledger_path)
    client = None
    if cfg.target_url and cfg.worker_token:
        client = TargetClient(cfg)
    return _print_status(ledger, client)


def _print_status(ledger: Ledger, client: TargetClient | None) -> int:
    """Print an informational snapshot; return 2 for fatal status configuration."""
    result = 0
    counts = ledger.status_counts()
    total = sum(counts.values())
    print("\n── Ledger ──")
    print(f"  root_dir : {ledger.get_meta('root_dir')}")
    print(f"  corpus   : {ledger.get_meta('corpus_id')}")
    print(f"  total    : {total}")
    for st in (PENDING, UPLOADED, COMPLETED, FAILED, PARKED, AMBIGUOUS, CONFLICT):
        if counts.get(st):
            print(f"  {st:<9}: {counts[st]}")
    if client is not None:
        try:
            print("\n── Token-scoped outstanding uploads ──")
            print(f"  PENDING+PROCESSING : {client.backlog_count()}")
        except StatusPollError as exc:
            result = 2 if exc.permanent else 0
            print(f"  PENDING+PROCESSING : unknown ({exc})")
    print("")
    return result


# ======================================================================
# CLI
# ======================================================================


def _build_config(args: argparse.Namespace) -> Config:
    target_url = args.target_url or os.environ.get("OC_TARGET_URL", "")
    worker_token = args.worker_token or os.environ.get("OC_WORKER_TOKEN", "")
    corpus_id = args.corpus_id or os.environ.get("OC_CORPUS_ID")
    extensions = tuple(
        e if e.startswith(".") else f".{e}"
        for e in (args.extensions or DEFAULT_EXTENSIONS).lower().split(",")
    )
    # Enrichers: --enricher (repeatable) plus comma-separated OC_ENRICHERS env.
    enrichers = list(args.enricher or [])
    enrichers += [s for s in os.environ.get("OC_ENRICHERS", "").split(",") if s.strip()]
    return Config(
        target_url=target_url,
        worker_token=worker_token,
        corpus_id=corpus_id,
        root_dir=args.root_dir or "",
        ledger_path=args.ledger,
        extensions=extensions,
        max_workers=args.max_workers,
        max_attempts=args.max_attempts,
        queue_high=args.queue_high,
        queue_low=args.queue_low,
        embeddings=not args.no_embeddings,
        target_folder_from_tree=not args.flat,
        verify_tls=not args.insecure,
        limit=args.limit,
        enrichers=enrichers,
        parser_config=args.parser_config or os.environ.get("OC_PARSER_CONFIG"),
        ledger_page_size=args.ledger_page_size,
        enricher_identity=args.enricher_identity
        or os.environ.get("OC_ENRICHER_IDENTITY"),
        embedding_identity=args.embedding_identity
        or os.environ.get("OC_EMBEDDING_IDENTITY"),
        embedding_dimension=args.embedding_dimension,
        parser_identity=args.parser_identity or os.environ.get("OC_PARSER_IDENTITY"),
        json_output=args.json,
        readiness=args.readiness,
    )


def _positive_int(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="oc_remote_ingest",
        description="Remote parse + worker-upload driver for OpenContracts.",
    )
    p.add_argument(
        "--ledger", default="oc_remote_ingest.sqlite3", help="SQLite ledger path"
    )
    p.add_argument("--target-url", help="Target OC base URL (env OC_TARGET_URL)")
    p.add_argument("--worker-token", help="WorkerKey token (env OC_WORKER_TOKEN)")
    p.add_argument("--corpus-id", help="Corpus id (informational; env OC_CORPUS_ID)")
    p.add_argument(
        "--root-dir", help="Root directory of source documents (for plan/run)"
    )
    p.add_argument("--extensions", help="Comma-separated extensions (default .pdf)")
    p.add_argument(
        "--parser-config",
        help="Local parser mapping/settings JSON file (env OC_PARSER_CONFIG)",
    )
    p.add_argument(
        "--parser-identity",
        help="Parser deployment revision (env OC_PARSER_IDENTITY); per-parser JSON identities override this",
    )
    p.add_argument(
        "--max-workers",
        type=_positive_int,
        default=DEFAULT_MAX_WORKERS,
        help="Active workers; submitted unfinished work is capped at twice this value",
    )
    p.add_argument(
        "--ledger-page-size",
        type=_positive_int,
        default=DEFAULT_LEDGER_PAGE_SIZE,
        help="Maximum ledger rows fetched per page for run/verify (default 256)",
    )
    p.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS)
    p.add_argument(
        "--queue-high",
        type=int,
        default=DEFAULT_QUEUE_HIGH,
        help="Pause run admission above this token-scoped outstanding upload count; <= 0 disables polling",
    )
    p.add_argument(
        "--queue-low",
        type=int,
        default=DEFAULT_QUEUE_LOW,
        help="Resume paused admission at/below this token-scoped count (0 <= low <= high when enabled)",
    )
    p.add_argument(
        "--no-embeddings",
        action="store_true",
        help="Skip remote embedding; let the server embed",
    )
    p.add_argument(
        "--flat",
        action="store_true",
        help="Do not mirror the directory tree into corpus folders",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Cap the number of docs recorded at plan time (0 = no cap)",
    )
    p.add_argument(
        "--insecure",
        action="store_true",
        help="Disable TLS verification (testing only)",
    )
    p.add_argument(
        "--enricher",
        action="append",
        metavar="MODULE:CALLABLE",
        help=(
            "Pre-processing enricher to calc + inject metadata/annotations "
            "(repeatable; also OC_ENRICHERS, comma-separated). "
            "E.g. example_enrichers:effective_date_annotations"
        ),
    )
    p.add_argument(
        "--enricher-identity",
        help=(
            "Stable identity of effective enricher configuration/data "
            "(required with enrichers; env OC_ENRICHER_IDENTITY)"
        ),
    )
    p.add_argument(
        "--embedding-identity",
        help="Operator model/service revision (env OC_EMBEDDING_IDENTITY); bump when the model changes",
    )
    p.add_argument(
        "--embedding-dimension",
        type=_positive_int,
        default=os.environ.get("OC_EMBEDDING_DIMENSION", "384"),
        help="Expected document/annotation vector dimension (default 384)",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Stream verify document results and a final summary as JSON Lines",
    )
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument(
        "--readiness",
        action="store_true",
        help="Verify current server search readiness in addition to upload receipts",
    )
    p.add_argument("command", choices=["plan", "run", "verify", "status", "cleanup"])
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.readiness and args.command != "verify":
        p.error("--readiness is supported only by verify")
    if args.json and args.command != "verify":
        p.error("--json is supported only by verify")
    cfg = _build_config(args)

    if args.command == "run":
        try:
            validate_watermarks(cfg.queue_high, cfg.queue_low)
        except ValueError as exc:
            p.error(str(exc))

    if args.command in ("run", "verify") and (
        not cfg.target_url or not cfg.worker_token
    ):
        p.error(
            "run/verify require --target-url and --worker-token (or OC_TARGET_URL/OC_WORKER_TOKEN)"
        )
    if args.command in ("plan", "run") and not cfg.root_dir:
        p.error("plan/run require --root-dir")

    return {
        "plan": cmd_plan,
        "run": cmd_run,
        "verify": cmd_verify,
        "status": cmd_status,
        "cleanup": cmd_cleanup,
    }[args.command](cfg)


if __name__ == "__main__":
    sys.exit(main())
