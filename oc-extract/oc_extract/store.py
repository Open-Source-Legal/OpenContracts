"""SQLite persistence layer.

Schema mirrors the OpenContracts extract data model
(``opencontractserver/extracts/models.py``) minus accounts/permissions:

* ``documents``   — ingested text + optional page offsets (Document)
* ``fieldsets``   — named schema of fields (Fieldset)
* ``fields``      — prompt + output-type config (Column)
* ``extracts``    — a run of a fieldset over documents (Extract)
* ``extract_documents`` — the run's document set (Extract.documents M2M)
* ``cells``       — one result per document x field (Datacell), including
  ``sources`` (citations), lifecycle timestamps, ``failure_mode`` and the
  captured ``llm_log``.

Plain ``sqlite3`` + a process lock keeps the service dependency-free; WAL
mode keeps readers unblocked during runs.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .constants import DEFAULT_DB_PATH
from .schema import FieldSet, FieldSpec

_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    text TEXT NOT NULL,
    sha256 TEXT NOT NULL UNIQUE,
    page_offsets TEXT,
    meta TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fieldsets (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fields (
    id INTEGER PRIMARY KEY,
    fieldset_id INTEGER NOT NULL REFERENCES fieldsets(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    query TEXT,
    match_text TEXT,
    must_contain_text TEXT,
    instructions TEXT,
    output_type TEXT NOT NULL,
    extract_is_list INTEGER NOT NULL DEFAULT 0,
    display_order INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS extracts (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    fieldset_id INTEGER NOT NULL REFERENCES fieldsets(id),
    model TEXT,
    created_at TEXT NOT NULL,
    started TEXT,
    finished TEXT,
    error TEXT
);
CREATE TABLE IF NOT EXISTS extract_documents (
    extract_id INTEGER NOT NULL REFERENCES extracts(id) ON DELETE CASCADE,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    PRIMARY KEY (extract_id, document_id)
);
CREATE TABLE IF NOT EXISTS cells (
    id INTEGER PRIMARY KEY,
    extract_id INTEGER NOT NULL REFERENCES extracts(id) ON DELETE CASCADE,
    field_id INTEGER NOT NULL REFERENCES fields(id),
    document_id INTEGER NOT NULL REFERENCES documents(id),
    data TEXT,
    data_definition TEXT NOT NULL,
    sources TEXT NOT NULL DEFAULT '[]',
    failure_mode TEXT,
    started TEXT,
    completed TEXT,
    failed TEXT,
    stacktrace TEXT,
    llm_log TEXT,
    UNIQUE (extract_id, field_id, document_id)
);
CREATE INDEX IF NOT EXISTS idx_cells_extract ON cells(extract_id);
CREATE INDEX IF NOT EXISTS idx_cells_document ON cells(document_id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _loads(value: str | None) -> Any:
    return None if value is None else json.loads(value)


class Store:
    """Thread-safe SQLite store for documents, fieldsets, extracts, cells."""

    def __init__(self, path: str | Path = DEFAULT_DB_PATH):
        self.path = str(path)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # -- documents ---------------------------------------------------------

    def add_document(
        self,
        title: str,
        text: str,
        *,
        page_offsets: list[int] | None = None,
        meta: dict[str, Any] | None = None,
    ) -> int:
        """Insert a document; re-ingesting identical text returns the
        existing row's id (idempotent by content hash)."""
        sha = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()
        with self._lock:
            row = self._conn.execute(
                "SELECT id FROM documents WHERE sha256 = ?", (sha,)
            ).fetchone()
            if row:
                return int(row["id"])
            cur = self._conn.execute(
                "INSERT INTO documents (title, text, sha256, page_offsets, meta, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    title,
                    text,
                    sha,
                    json.dumps(page_offsets) if page_offsets else None,
                    json.dumps(meta or {}),
                    _now(),
                ),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def get_document(self, document_id: int, *, include_text: bool = True) -> dict:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM documents WHERE id = ?", (document_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"document {document_id} not found")
        return self._document_dict(row, include_text=include_text)

    def list_documents(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM documents ORDER BY id").fetchall()
        return [self._document_dict(row, include_text=False) for row in rows]

    @staticmethod
    def _document_dict(row: sqlite3.Row, *, include_text: bool) -> dict:
        doc = {
            "id": row["id"],
            "title": row["title"],
            "sha256": row["sha256"],
            "text_length": len(row["text"]),
            "page_offsets": _loads(row["page_offsets"]),
            "meta": _loads(row["meta"]) or {},
            "created_at": row["created_at"],
        }
        if include_text:
            doc["text"] = row["text"]
        return doc

    # -- fieldsets -----------------------------------------------------------

    def create_fieldset(self, fieldset: FieldSet) -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO fieldsets (name, description, created_at) VALUES (?, ?, ?)",
                (fieldset.name, fieldset.description, _now()),
            )
            fieldset_id = int(cur.lastrowid)
            for order, spec in enumerate(fieldset.fields):
                self._conn.execute(
                    "INSERT INTO fields (fieldset_id, name, query, match_text,"
                    " must_contain_text, instructions, output_type,"
                    " extract_is_list, display_order)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        fieldset_id,
                        spec.name,
                        spec.query,
                        spec.match_text,
                        spec.must_contain_text,
                        spec.instructions,
                        spec.output_type,
                        int(spec.extract_is_list),
                        order,
                    ),
                )
            self._conn.commit()
            return fieldset_id

    def get_fieldset(self, fieldset_id: int) -> dict:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM fieldsets WHERE id = ?", (fieldset_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"fieldset {fieldset_id} not found")
            field_rows = self._conn.execute(
                "SELECT * FROM fields WHERE fieldset_id = ? ORDER BY display_order",
                (fieldset_id,),
            ).fetchall()
        return {
            "id": row["id"],
            "name": row["name"],
            "description": row["description"],
            "created_at": row["created_at"],
            "fields": [self._field_dict(f) for f in field_rows],
        }

    def list_fieldsets(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT f.*, (SELECT COUNT(*) FROM fields WHERE fieldset_id = f.id)"
                " AS field_count FROM fieldsets f ORDER BY f.id"
            ).fetchall()
        return [
            {
                "id": row["id"],
                "name": row["name"],
                "description": row["description"],
                "created_at": row["created_at"],
                "field_count": row["field_count"],
            }
            for row in rows
        ]

    @staticmethod
    def _field_dict(row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "name": row["name"],
            "query": row["query"],
            "match_text": row["match_text"],
            "must_contain_text": row["must_contain_text"],
            "instructions": row["instructions"],
            "output_type": row["output_type"],
            "extract_is_list": bool(row["extract_is_list"]),
            "display_order": row["display_order"],
        }

    @staticmethod
    def field_spec(field_row: dict) -> FieldSpec:
        """Rehydrate a stored field row into a :class:`FieldSpec`."""
        return FieldSpec(
            name=field_row["name"],
            query=field_row["query"],
            match_text=field_row["match_text"],
            must_contain_text=field_row["must_contain_text"],
            instructions=field_row["instructions"],
            output_type=field_row["output_type"],
            extract_is_list=field_row["extract_is_list"],
        )

    # -- extracts -------------------------------------------------------------

    def create_extract(
        self,
        name: str,
        fieldset_id: int,
        document_ids: list[int],
        *,
        model: str | None = None,
    ) -> int:
        self.get_fieldset(fieldset_id)  # existence check
        for doc_id in document_ids:
            self.get_document(doc_id, include_text=False)
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO extracts (name, fieldset_id, model, created_at)"
                " VALUES (?, ?, ?, ?)",
                (name, fieldset_id, model, _now()),
            )
            extract_id = int(cur.lastrowid)
            self._conn.executemany(
                "INSERT OR IGNORE INTO extract_documents (extract_id, document_id)"
                " VALUES (?, ?)",
                [(extract_id, doc_id) for doc_id in document_ids],
            )
            self._conn.commit()
            return extract_id

    def get_extract(self, extract_id: int) -> dict:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM extracts WHERE id = ?", (extract_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"extract {extract_id} not found")
            doc_ids = [
                r["document_id"]
                for r in self._conn.execute(
                    "SELECT document_id FROM extract_documents"
                    " WHERE extract_id = ? ORDER BY document_id",
                    (extract_id,),
                ).fetchall()
            ]
            counts = self._conn.execute(
                "SELECT COUNT(*) AS total,"
                " SUM(completed IS NOT NULL) AS completed,"
                " SUM(failed IS NOT NULL) AS failed"
                " FROM cells WHERE extract_id = ?",
                (extract_id,),
            ).fetchone()
        return {
            "id": row["id"],
            "name": row["name"],
            "fieldset_id": row["fieldset_id"],
            "model": row["model"],
            "created_at": row["created_at"],
            "started": row["started"],
            "finished": row["finished"],
            "error": row["error"],
            "document_ids": doc_ids,
            "cell_counts": {
                "total": counts["total"] or 0,
                "completed": counts["completed"] or 0,
                "failed": counts["failed"] or 0,
            },
        }

    def list_extracts(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute("SELECT id FROM extracts ORDER BY id").fetchall()
        return [self.get_extract(row["id"]) for row in rows]

    def mark_extract_started(self, extract_id: int) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE extracts SET started = ?, finished = NULL, error = NULL"
                " WHERE id = ?",
                (_now(), extract_id),
            )
            self._conn.commit()

    def mark_extract_finished(self, extract_id: int, error: str | None = None) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE extracts SET finished = ?, error = ? WHERE id = ?",
                (_now(), error, extract_id),
            )
            self._conn.commit()

    # -- cells ------------------------------------------------------------------

    def create_cell(
        self, extract_id: int, field_id: int, document_id: int, data_definition: str
    ) -> int:
        with self._lock:
            # RETURNING (SQLite >= 3.35) yields the correct row id on BOTH the
            # insert and the conflict/UPDATE path. Do NOT infer it from
            # ``cursor.lastrowid``: when the upsert resolves via DO UPDATE,
            # lastrowid keeps the connection's last *real* insert, so a re-run
            # over multiple cells would attribute every cell to one stale id.
            row = self._conn.execute(
                "INSERT INTO cells (extract_id, field_id, document_id, data_definition)"
                " VALUES (?, ?, ?, ?)"
                " ON CONFLICT (extract_id, field_id, document_id) DO UPDATE SET"
                " data = NULL, sources = '[]', failure_mode = NULL, started = NULL,"
                " completed = NULL, failed = NULL, stacktrace = NULL, llm_log = NULL"
                " RETURNING id",
                (extract_id, field_id, document_id, data_definition),
            ).fetchone()
            self._conn.commit()
            return int(row["id"])

    def mark_cell_started(self, cell_id: int) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE cells SET started = ? WHERE id = ?", (_now(), cell_id)
            )
            self._conn.commit()

    def mark_cell_completed(
        self,
        cell_id: int,
        data: Any,
        sources: list[dict],
        *,
        failure_mode: str | None = None,
        llm_log: str | None = None,
    ) -> None:
        """Persist a completed cell. ``data`` is stored as ``{"data": value}``
        (the OpenContracts Datacell convention)."""
        with self._lock:
            self._conn.execute(
                "UPDATE cells SET data = ?, sources = ?, failure_mode = ?,"
                " completed = ?, llm_log = ? WHERE id = ?",
                (
                    json.dumps({"data": data}),
                    json.dumps(sources),
                    failure_mode,
                    _now(),
                    llm_log,
                    cell_id,
                ),
            )
            self._conn.commit()

    def mark_cell_failed(
        self,
        cell_id: int,
        *,
        failure_mode: str,
        stacktrace: str,
        llm_log: str | None = None,
    ) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE cells SET failure_mode = ?, stacktrace = ?, failed = ?,"
                " llm_log = ? WHERE id = ?",
                (failure_mode, stacktrace, _now(), llm_log, cell_id),
            )
            self._conn.commit()

    def get_cell(self, cell_id: int, *, include_llm_log: bool = False) -> dict:
        with self._lock:
            row = self._conn.execute(
                "SELECT c.*, f.name AS field_name, d.title AS document_title"
                " FROM cells c"
                " JOIN fields f ON f.id = c.field_id"
                " JOIN documents d ON d.id = c.document_id"
                " WHERE c.id = ?",
                (cell_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"cell {cell_id} not found")
        return self._cell_dict(row, include_llm_log=include_llm_log)

    def get_cells(
        self, extract_id: int, *, include_llm_log: bool = False
    ) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT c.*, f.name AS field_name, d.title AS document_title"
                " FROM cells c"
                " JOIN fields f ON f.id = c.field_id"
                " JOIN documents d ON d.id = c.document_id"
                " WHERE c.extract_id = ? ORDER BY c.document_id, f.display_order",
                (extract_id,),
            ).fetchall()
        return [self._cell_dict(row, include_llm_log=include_llm_log) for row in rows]

    @staticmethod
    def _cell_dict(row: sqlite3.Row, *, include_llm_log: bool) -> dict:
        data = _loads(row["data"])
        cell = {
            "id": row["id"],
            "extract_id": row["extract_id"],
            "field_id": row["field_id"],
            "field_name": row["field_name"],
            "document_id": row["document_id"],
            "document_title": row["document_title"],
            "data": data,
            "value": data.get("data") if isinstance(data, dict) else None,
            "data_definition": row["data_definition"],
            "sources": _loads(row["sources"]) or [],
            "failure_mode": row["failure_mode"],
            "started": row["started"],
            "completed": row["completed"],
            "failed": row["failed"],
            "stacktrace": row["stacktrace"],
        }
        if include_llm_log:
            cell["llm_log"] = row["llm_log"]
        return cell

    def extract_table(self, extract_id: int) -> list[dict]:
        """Grid view: one row per document, one key per field name."""
        cells = self.get_cells(extract_id)
        rows: dict[int, dict] = {}
        for cell in cells:
            row = rows.setdefault(
                cell["document_id"],
                {
                    "document_id": cell["document_id"],
                    "document_title": cell["document_title"],
                    "values": {},
                },
            )
            row["values"][cell["field_name"]] = {
                "value": cell["value"],
                "status": (
                    "completed"
                    if cell["completed"]
                    else "failed" if cell["failed"] else "pending"
                ),
                "failure_mode": cell["failure_mode"],
                "cell_id": cell["id"],
                "source_count": len(cell["sources"]),
            }
        return list(rows.values())
