#!/usr/bin/env python3
"""
oc_remote_ingest.py — run the OpenContracts ingestion pipeline on a remote host
and stream FAITHFUL, fully-processed documents into a target OpenContracts
corpus via the worker-upload REST API.

WHY THIS EXISTS
---------------
``scripts/bulk_import/oc_bulk_import.py`` ships *raw* PDFs to the server and lets
the SERVER parse them (Docling + embeddings). That offloads nothing — the
expensive work still runs in-cluster. This driver instead does the heavy lifting
(Docling parse + embedding) on a beefy *remote* worker and ships the finished
artifacts — PAWLs token layer, text layer, structural annotations, relationships
and pre-computed embeddings — to the target via ``POST /api/worker-uploads/
documents/``, which bypasses the server parser entirely. The result is a faithful
mirror: because the worker runs the SAME Docling microservice and the SAME
``DoclingParser`` code the server would run, the PAWLs and structural layer are
identical to an in-cluster ingestion (no tokenizer drift).

FAITHFUL-BY-CONSTRUCTION
------------------------
* PAWLs / structural annotations / relationships: produced by the real
  ``DoclingParser.parse_pdf_bytes`` (same parser, same docling service).
* Text layer (``content``): rebuilt from the shipped PAWLs with the same
  ``plasmapdf.build_translation_layer`` the server's ``save_parsed_data`` uses,
  so the stored text layer matches byte-for-byte.
* Embeddings: computed against the same vector-embedder microservice the server
  uses, over the same inputs (full text for the doc, ``rawText`` per annotation).
* Structural set + thumbnail: materialised server-side by the worker-upload
  ingestion path (see opencontractserver/worker_uploads/tasks.py).

DESIGN
------
* Resumable: a SQLite ledger records every document's state (PENDING / UPLOADED /
  COMPLETED / FAILED / PARKED). Re-running ``run`` skips finished work. Each doc
  is keyed by its path relative to ``--root-dir`` (its corpus folder path).
* Per-document streaming (NO archive): scales to 100k–1M docs without ever
  building a ZIP. The slow step is the remote Docling parse, so the driver runs
  a thread pool of workers and paces itself against the server's worker-upload
  backlog (the ``documents/list/`` counts) instead of detonating the queue.
* Secure: auth is a corpus-scoped ``CorpusAccessToken`` sent as
  ``Authorization: WorkerKey <token>`` over TLS. The corpus is fixed by the
  token binding — the remote host cannot target another corpus. NO database
  access to the target is required or possible.

SUBCOMMANDS
-----------
    plan     Scan ``--root-dir`` and record every PDF in the ledger (no network,
             no parsing).
    run      Parse + embed + upload PENDING/FAILED docs (resumable, paced,
             concurrent).
    verify   Poll the target for each uploaded doc's terminal status and update
             the ledger (UPLOADED -> COMPLETED / FAILED).
    status   Print ledger counts + the target's live worker-upload backlog.

ENVIRONMENT / FLAGS (flags override env)
----------------------------------------
    OC_TARGET_URL     Base URL of the target OC instance (e.g. https://oc.example.com)
    OC_WORKER_TOKEN   CorpusAccessToken plaintext (WorkerKey auth)
    OC_CORPUS_ID      Informational; the bound corpus is enforced by the token
    DOCLING_PARSER_SERVICE_URL    Docling microservice (default from Django settings)
    EMBEDDINGS_MICROSERVICE_URL   Vector embedder microservice

This script runs INSIDE the OpenContracts image (it imports the real parser),
so Django must be importable. Only the ``run`` subcommand needs Django/Docling;
``plan`` / ``status`` / ``verify`` are pure HTTP + SQLite.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import random
import sqlite3
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

import requests

if TYPE_CHECKING:  # avoid importing enrichers (needs Django path) at module load
    from enrichers import MetadataOverlay

logger = logging.getLogger("oc_remote_ingest")

# --- Defaults --------------------------------------------------------------
DEFAULT_EXTENSIONS = ".pdf"
DEFAULT_MAX_WORKERS = 4
DEFAULT_EMBED_BATCH = 100
DEFAULT_MAX_ATTEMPTS = 5
# Backpressure: pause submitting when the target has more than HIGH worker
# uploads still PENDING+PROCESSING, resume once it drains below LOW.
DEFAULT_QUEUE_HIGH = 2000
DEFAULT_QUEUE_LOW = 500
_HTTP_MAX_RETRIES = 6
_JITTER_MIN = 0.5

# Ledger statuses
PENDING = "PENDING"
UPLOADED = "UPLOADED"  # staged on the server (202 accepted), not yet confirmed
COMPLETED = "COMPLETED"  # server confirmed terminal success
FAILED = "FAILED"  # retry-eligible
PARKED = "PARKED"  # retries exhausted (terminal)


# ======================================================================
# Ledger
# ======================================================================


class Ledger:
    """Crash-resumable SQLite ledger of per-document ingest state."""

    def __init__(self, path: str):
        self.path = path
        self._local = threading.local()
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
                CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
                PRAGMA journal_mode=WAL;
                PRAGMA synchronous=NORMAL;
                """)

    def _conn(self) -> sqlite3.Connection:
        # One connection per thread (sqlite connections are not thread-safe).
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.path, timeout=60, isolation_level=None)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA busy_timeout=60000;")
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
        """Insert a doc if new. Returns True if inserted, False if it already existed."""
        cur = self._conn().execute(
            "INSERT INTO docs(rel_path, abs_path, size, sha256, status, created_at) "
            "VALUES(?, ?, ?, ?, 'PENDING', ?) "
            "ON CONFLICT(rel_path) DO NOTHING",
            (rel_path, abs_path, size, sha256, now),
        )
        return cur.rowcount > 0

    def claimable(self) -> list[sqlite3.Row]:
        return list(
            self._conn()
            .execute(
                "SELECT * FROM docs WHERE status IN ('PENDING', 'FAILED') "
                "ORDER BY rel_path"
            )
            .fetchall()
        )

    def uploaded_unconfirmed(self) -> list[sqlite3.Row]:
        return list(
            self._conn()
            .execute(
                "SELECT * FROM docs WHERE status='UPLOADED' AND upload_id IS NOT NULL"
            )
            .fetchall()
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
            "SELECT attempts FROM docs WHERE rel_path=?", (rel_path,)
        ).fetchone()
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
        return min(2.0 * (2 ** (attempt - 1)), 60.0) * random.uniform(_JITTER_MIN, 1.0)

    def upload(self, pdf_path: str, metadata: dict) -> str:
        """POST a document. Returns the server upload_id. Raises on permanent failure."""
        url = f"{self.base}/api/worker-uploads/documents/"
        meta_json = json.dumps(metadata)
        last_error = "unknown"
        for attempt in range(1, _HTTP_MAX_RETRIES + 1):
            try:
                with open(pdf_path, "rb") as fh:
                    resp = self.session.post(
                        url,
                        files={
                            "file": (
                                PurePosixPath(pdf_path).name,
                                fh,
                                "application/pdf",
                            )
                        },
                        data={"metadata": meta_json},
                        timeout=300,
                        verify=self._verify,
                    )
                if resp.status_code == 202:
                    return resp.json()["upload_id"]
                if resp.status_code == 429:
                    wait = float(resp.headers.get("Retry-After", "60"))
                    logger.warning(f"429 rate-limited; sleeping {wait}s")
                    time.sleep(wait)
                    continue
                if 400 <= resp.status_code < 500:
                    # Permanent (bad payload / auth / too large) — do not retry.
                    raise PermanentUploadError(
                        f"HTTP {resp.status_code}: {resp.text[:500]}"
                    )
                last_error = f"HTTP {resp.status_code}: {resp.text[:300]}"
            except PermanentUploadError:
                raise
            except requests.RequestException as e:
                last_error = f"network: {e}"
            if attempt < _HTTP_MAX_RETRIES:
                time.sleep(self._backoff(attempt))
        raise TransientUploadError(
            f"upload failed after {_HTTP_MAX_RETRIES} attempts: {last_error}"
        )

    def upload_status(self, upload_id: str) -> dict | None:
        url = f"{self.base}/api/worker-uploads/documents/{upload_id}/"
        resp = self.session.get(url, timeout=60, verify=self._verify)
        if resp.status_code == 200:
            return resp.json()
        return None

    def backlog_count(self) -> int:
        """PENDING + PROCESSING uploads for this token (drives backpressure)."""
        total = 0
        for st in ("PENDING", "PROCESSING"):
            url = f"{self.base}/api/worker-uploads/documents/list/?status={st}&page_size=1"
            try:
                resp = self.session.get(url, timeout=30, verify=self._verify)
                if resp.status_code == 200:
                    total += int(resp.json().get("count", 0))
            except requests.RequestException:
                # Treat polling failure as "no backpressure signal" — better to
                # keep moving than to stall the whole run on a flaky status call.
                return 0
        return total


class PermanentUploadError(Exception):
    pass


class TransientUploadError(Exception):
    pass


# ======================================================================
# Embedder client (vector-embedder microservice)
# ======================================================================


class EmbedderClient:
    """Thin HTTP client for the vector-embedder microservice."""

    def __init__(self, service_url: str, api_key: str | None, batch_size: int):
        self.base = service_url.rstrip("/")
        self.session = requests.Session()
        if api_key:
            self.session.headers["X-API-Key"] = api_key
        self.batch_size = batch_size

    def embed_text(self, text: str) -> list[float] | None:
        if not text or not text.strip():
            return None
        resp = self.session.post(
            f"{self.base}/embeddings", json={"text": text}, timeout=30
        )
        resp.raise_for_status()
        return self._coerce_vector(resp.json().get("embeddings"))

    @staticmethod
    def _coerce_vector(vec) -> list[float] | None:
        """Accept either a 1-D vector or a 2-D ``[[...]]`` single-row response."""
        if not isinstance(vec, list) or not vec:
            return None
        if isinstance(vec[0], list):  # 2-D (batch-shaped) single response
            inner = vec[0]
            return inner if inner else None
        return vec

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
                timeout=120,
            )
            resp.raise_for_status()
            vecs = resp.json().get("embeddings")
            if not isinstance(vecs, list):
                continue
            for local_i, vec in enumerate(vecs):
                # The batch endpoint wraps each row one level deeper than the
                # single endpoint (per-item shape is ``[[...floats...]]``), so
                # coerce each row down to a flat numeric vector.
                coerced = self._coerce_vector(vec)
                if coerced is not None:
                    out[chunk_idxs[local_i]] = coerced
        return out


# ======================================================================
# Parser wrapper (lazy Django + DoclingParser singleton)
# ======================================================================


class _Parser:
    """Lazily-initialised, thread-safe singleton wrapper around DoclingParser."""

    def __init__(self) -> None:
        self._parser = None
        self._build_translation_layer = None
        self._default_embedder_path = None
        self._lock = threading.Lock()

    def _ensure(self) -> None:
        if self._parser is not None:
            return
        with self._lock:
            if self._parser is not None:
                return
            # Ensure the OpenContracts repo root is importable. When this file is
            # run directly (``python .../oc_remote_ingest.py``) sys.path[0] is the
            # script's own directory, so ``config`` / ``opencontractserver`` are
            # not importable until we add the repo root (this file lives at
            # ``<root>/scripts/remote_ingest/oc_remote_ingest.py``).
            repo_root = str(Path(__file__).resolve().parents[2])
            if repo_root not in sys.path:
                sys.path.insert(0, repo_root)

            os.environ.setdefault(
                "DJANGO_SETTINGS_MODULE", "config.settings.remote_worker"
            )
            import django

            django.setup()
            from plasmapdf.models.PdfDataLayer import build_translation_layer

            from opencontractserver.pipeline.parsers.docling_parser_rest import (
                DoclingParser,
            )

            try:
                from opencontractserver.pipeline.utils import get_default_embedder_path

                self._default_embedder_path = get_default_embedder_path()
            except Exception:
                self._default_embedder_path = (
                    "opencontractserver.pipeline.embedders."
                    "sent_transformer_microservice.MicroserviceEmbedder"
                )

            self._build_translation_layer = build_translation_layer
            self._parser = DoclingParser()

            # Pipeline component settings (incl. the Docling service URL) are
            # normally sourced from the PipelineSettings DB table — the
            # ``env_var`` declared on each setting only SEEDS that table via
            # ``migrate_pipeline_settings``, it is not read at runtime. The
            # remote worker runs WITHOUT that DB, so the parser comes up with
            # dataclass defaults (service_url=""). Backfill the Docling knobs
            # from the environment so the worker is configured purely via env,
            # mirroring how the in-cluster parser is seeded from the same vars.
            self._backfill_parser_settings_from_env()

            if not self._parser.service_url:
                raise RuntimeError(
                    "DOCLING_PARSER_SERVICE_URL must be set so the remote worker "
                    "can reach the Docling microservice."
                )
            logger.info(
                f"DoclingParser ready (service={self._parser.service_url!r}, "
                f"extract_images={self._parser.extract_images}, "
                f"embedder_path={self._default_embedder_path})"
            )

    def _backfill_parser_settings_from_env(self) -> None:
        """Override DoclingParser instance settings from DOCLING_* env vars.

        Only applied when the value is present in the environment, so a worker
        that sets nothing inherits the same defaults the in-cluster parser uses.
        """

        def _set(attr: str, env_var: str, cast) -> None:
            raw = os.environ.get(env_var)
            if raw is None or raw == "":
                return
            try:
                setattr(self._parser, attr, cast(raw))
            except (ValueError, TypeError):
                logger.warning(f"Ignoring invalid {env_var}={raw!r}")

        def _as_bool(v: str) -> bool:
            return v.strip().lower() in ("1", "true", "yes", "on")

        _set("service_url", "DOCLING_PARSER_SERVICE_URL", str)
        _set("request_timeout", "DOCLING_PARSER_TIMEOUT", int)
        _set("extract_images", "DOCLING_EXTRACT_IMAGES", _as_bool)
        _set("image_format", "DOCLING_IMAGE_FORMAT", str)
        _set("image_quality", "DOCLING_IMAGE_QUALITY", int)
        _set("image_dpi", "DOCLING_IMAGE_DPI", int)
        _set("min_image_width", "DOCLING_MIN_IMAGE_WIDTH", int)
        _set("min_image_height", "DOCLING_MIN_IMAGE_HEIGHT", int)
        _set("max_pages_per_chunk", "DOCLING_MAX_PAGES_PER_CHUNK", int)
        _set("min_pages_for_chunking", "DOCLING_MIN_PAGES_FOR_CHUNKING", int)
        _set("max_concurrent_chunks", "DOCLING_MAX_CONCURRENT_CHUNKS", int)
        _set("chunk_overlap", "DOCLING_CHUNK_OVERLAP", int)

    def ensure_ready(self) -> None:
        """Eagerly set up Django + the parser (used to fail fast on config errors
        and to make ``config`` / ``opencontractserver`` importable before
        enrichers are loaded)."""
        self._ensure()

    @property
    def default_embedder_path(self) -> str:
        self._ensure()
        return self._default_embedder_path

    def parse(self, pdf_bytes: bytes) -> dict:
        self._ensure()
        result = self._parser.parse_pdf_bytes(pdf_bytes, user_id=0, doc_id=0)
        if result is None:
            raise RuntimeError("parser returned no result")
        return result

    def text_from_pawls(self, pawls_pages: list) -> str:
        self._ensure()
        if not pawls_pages:
            return ""
        return self._build_translation_layer(pawls_pages).doc_text


# ======================================================================
# Payload construction
# ======================================================================

# Mirror save_parsed_data's structural-label definitions so the target
# auto-creates any labels the parser emitted with identical presentation.
_TOKEN_LABEL = "TOKEN_LABEL"
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
    overlay: MetadataOverlay | None = None,
) -> dict:
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
                "label_type": ann.get("annotation_type") or _TOKEN_LABEL,
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
        "file_type": export.get("file_type", "application/pdf") or "application/pdf",
        "pawls_file_content": export.get("pawls_file_content", []),
        "labelled_text": labelled_text,
        "relationships": relationships,
        "doc_labels": doc_label_names,
        "text_labels": text_labels,
        "doc_labels_definitions": doc_labels_definitions,
        "parser_name": "Docling Parser (REST)",
        "parser_version": "1.0",
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
) -> dict | None:
    """Compute the doc-level + per-annotation embeddings the server would store."""
    doc_vec = embedder.embed_text(content)

    # Annotation embeddings keyed by the annotation's stable export ``id``
    # (the same id the worker-upload path maps to the new DB pk).
    ann_ids: list = []
    ann_texts: list[str] = []
    for ann in labelled_text:
        ann_id = ann.get("id")
        raw = ann.get("rawText") or ""
        if ann_id is not None and raw.strip():
            ann_ids.append(ann_id)
            ann_texts.append(raw)

    annotation_embeddings: dict[str, list[float]] = {}
    if ann_texts:
        vecs = embedder.embed_batch(ann_texts)
        for ann_id, vec in zip(ann_ids, vecs):
            if vec is not None:
                annotation_embeddings[str(ann_id)] = vec

    if doc_vec is None and not annotation_embeddings:
        return None

    payload: dict = {"embedder_path": embedder_path}
    if doc_vec is not None:
        payload["document_embedding"] = doc_vec
    if annotation_embeddings:
        payload["annotation_embeddings"] = annotation_embeddings
    return payload


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
    root_path = Path(root).resolve()
    for path in sorted(root_path.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in extensions:
            continue
        rel = path.relative_to(root_path).as_posix()
        yield rel, str(path)


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
    for rel, abs_path in _scan(cfg.root_dir, cfg.extensions):
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
    return 0


def _process_one(
    cfg: Config,
    parser: _Parser,
    embedder: EmbedderClient | None,
    client: TargetClient,
    row: sqlite3.Row,
    enrichers: list | None = None,
) -> tuple[str, bool, str]:
    """Parse + (enrich) + embed + upload one document. Returns (rel_path, ok, message)."""
    rel_path = row["rel_path"]
    abs_path = row["abs_path"]
    try:
        with open(abs_path, "rb") as fh:
            pdf_bytes = fh.read()

        export = parser.parse(pdf_bytes)
        pawls = export.get("pawls_file_content", []) or []

        # Rebuild the text layer the same way the server's save_parsed_data does
        # (PAWLs translation), falling back to the parser-reported content.
        content = parser.text_from_pawls(pawls) or (export.get("content") or "")
        if not content.strip():
            return (rel_path, False, "empty content/text layer (would be unsearchable)")

        # Pre-processing / enrichment stage: calculate + inject extra metadata
        # and annotations BEFORE embedding (so injected annotations get embedded)
        # and BEFORE building the payload. A validation failure fails the doc.
        overlay = None
        if enrichers:
            from enrichers import (  # local import: needs Django path set up
                EnricherContext,
                apply_enrichment,
                run_enrichers,
                validate_enrichment,
            )

            ctx = EnricherContext(
                rel_path=rel_path, abs_path=abs_path, export=export, content=content
            )
            enrichment = run_enrichers(enrichers, ctx)
            if not enrichment.is_empty():
                errors = validate_enrichment(export, enrichment)
                if errors:
                    return (
                        rel_path,
                        False,
                        "enrichment invalid: " + "; ".join(errors[:5]),
                    )
                overlay = apply_enrichment(export, enrichment)

        embeddings = None
        if cfg.embeddings and embedder is not None:
            # Compute over the (possibly enriched) labelled_text so injected
            # annotations are embedded too.
            embeddings = _compute_embeddings(
                embedder=embedder,
                embedder_path=parser.default_embedder_path,
                content=content,
                labelled_text=export.get("labelled_text", []) or [],
            )

        target_folder_path = None
        if cfg.target_folder_from_tree:
            parent = PurePosixPath(rel_path).parent.as_posix()
            target_folder_path = None if parent in (".", "") else parent

        title = PurePosixPath(rel_path).name
        metadata = _build_metadata(
            title=title,
            export=export,
            content=content,
            embedder_path=parser.default_embedder_path,
            embeddings=embeddings,
            target_folder_path=target_folder_path,
            overlay=overlay,
        )

        upload_id = client.upload(abs_path, metadata)
        page_count = metadata["page_count"]
        return (rel_path, True, f"{upload_id}|{page_count}")
    except PermanentUploadError as e:
        return (rel_path, False, f"permanent: {e}")
    except Exception as e:  # noqa: BLE001 — surface any parse/embed/upload failure
        return (rel_path, False, str(e))


def cmd_run(cfg: Config) -> int:
    ledger = Ledger(cfg.ledger_path)
    parser = _Parser()
    # Set up Django + the parser eagerly so config errors (missing service URL,
    # broken enricher import) surface before we start churning documents.
    parser.ensure_ready()

    enrichers: list = []
    if cfg.enrichers:
        from enrichers import load_enrichers

        enrichers = load_enrichers(cfg.enrichers)
        logger.info(
            f"loaded {len(enrichers)} enricher(s): "
            + ", ".join(name for name, _ in enrichers)
        )

    embedder = None
    if cfg.embeddings:
        embedder = EmbedderClient(
            os.environ.get(
                "EMBEDDINGS_MICROSERVICE_URL", "http://vector-embedder:8000"
            ),
            os.environ.get("VECTOR_EMBEDDER_API_KEY") or None,
            DEFAULT_EMBED_BATCH,
        )
    client = TargetClient(cfg)

    todo = ledger.claimable()
    if not todo:
        logger.info("nothing to do — run `plan` first or everything is done.")
        _print_status(ledger, client)
        return 0

    logger.info(
        f"run: {len(todo)} docs to process with {cfg.max_workers} workers "
        f"(embeddings={'on' if cfg.embeddings else 'off'}, "
        f"enrichers={len(enrichers)})"
    )

    # Backpressure gate shared by all workers.
    pause_event = threading.Event()
    pause_event.set()  # set == "go"
    governor_state = {"last_poll": 0.0, "stop": False}
    gov_lock = threading.Lock()

    def maybe_poll_backpressure() -> None:
        if cfg.queue_high <= 0:
            return
        with gov_lock:
            now = time.time()
            if now - governor_state["last_poll"] < 15:
                return
            governor_state["last_poll"] = now
        backlog = client.backlog_count()
        if backlog > cfg.queue_high and pause_event.is_set():
            logger.info(f"backpressure: backlog={backlog} > {cfg.queue_high}; pausing")
            pause_event.clear()
        elif backlog <= cfg.queue_low and not pause_event.is_set():
            logger.info(f"backpressure: backlog={backlog} <= {cfg.queue_low}; resuming")
            pause_event.set()

    done = {"ok": 0, "fail": 0}
    done_lock = threading.Lock()

    def worker(row: sqlite3.Row) -> None:
        # Wait while paused (re-poll periodically to unblock).
        while not pause_event.wait(timeout=10):
            maybe_poll_backpressure()
        maybe_poll_backpressure()
        rel, ok, msg = _process_one(cfg, parser, embedder, client, row, enrichers)
        now = time.time()
        if ok:
            upload_id, _, page_count = msg.partition("|")
            ledger.mark_uploaded(rel, upload_id, int(page_count or 0), now)
            with done_lock:
                done["ok"] += 1
                n = done["ok"] + done["fail"]
            logger.info(f"[{n}/{len(todo)}] uploaded {rel} -> {upload_id}")
        else:
            ledger.mark_failed(rel, msg, cfg.max_attempts)
            with done_lock:
                done["fail"] += 1
                n = done["ok"] + done["fail"]
            logger.warning(f"[{n}/{len(todo)}] FAILED {rel}: {msg}")

    with ThreadPoolExecutor(max_workers=cfg.max_workers) as pool:
        futures = [pool.submit(worker, row) for row in todo]
        for fut in as_completed(futures):
            exc = fut.exception()
            if exc is not None:
                logger.error(f"worker crashed: {exc}")

    logger.info(f"run complete: uploaded={done['ok']}, failed={done['fail']}")
    _print_status(ledger, client)
    return 0 if done["fail"] == 0 else 1


def cmd_verify(cfg: Config) -> int:
    ledger = Ledger(cfg.ledger_path)
    client = TargetClient(cfg)
    pending = ledger.uploaded_unconfirmed()
    logger.info(f"verify: polling {len(pending)} uploaded docs for terminal status")
    confirmed = failed = still = 0
    now = time.time()
    for row in pending:
        status = client.upload_status(row["upload_id"])
        if status is None:
            still += 1
            continue
        st = status.get("status")
        if st == "COMPLETED":
            ledger.mark_completed(row["rel_path"], now)
            confirmed += 1
        elif st == "FAILED":
            ledger.mark_failed(
                row["rel_path"],
                f"server: {status.get('error_message', 'failed')}",
                cfg.max_attempts,
            )
            failed += 1
        else:
            still += 1
    logger.info(
        f"verify complete: confirmed={confirmed}, failed={failed}, still-processing={still}"
    )
    _print_status(ledger, client)
    return 0


def cmd_status(cfg: Config) -> int:
    ledger = Ledger(cfg.ledger_path)
    client = None
    if cfg.target_url and cfg.worker_token:
        client = TargetClient(cfg)
    _print_status(ledger, client)
    return 0


def _print_status(ledger: Ledger, client: TargetClient | None) -> None:
    counts = ledger.status_counts()
    total = sum(counts.values())
    print("\n── Ledger ──")
    print(f"  root_dir : {ledger.get_meta('root_dir')}")
    print(f"  corpus   : {ledger.get_meta('corpus_id')}")
    print(f"  total    : {total}")
    for st in (PENDING, UPLOADED, COMPLETED, FAILED, PARKED):
        if counts.get(st):
            print(f"  {st:<9}: {counts[st]}")
    if client is not None:
        try:
            print("\n── Target worker-upload backlog ──")
            print(f"  PENDING+PROCESSING : {client.backlog_count()}")
        except Exception as e:  # noqa: BLE001
            print(f"  (could not reach target: {e})")
    print("")


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
    )


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
    p.add_argument("--root-dir", help="Root directory of PDFs (for plan/run)")
    p.add_argument("--extensions", help="Comma-separated extensions (default .pdf)")
    p.add_argument("--max-workers", type=int, default=DEFAULT_MAX_WORKERS)
    p.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS)
    p.add_argument("--queue-high", type=int, default=DEFAULT_QUEUE_HIGH)
    p.add_argument("--queue-low", type=int, default=DEFAULT_QUEUE_LOW)
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
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("command", choices=["plan", "run", "verify", "status"])
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    cfg = _build_config(args)

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
    }[args.command](cfg)


if __name__ == "__main__":
    sys.exit(main())
