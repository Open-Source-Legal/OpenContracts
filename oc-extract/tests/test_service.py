"""Service tests: full HTTP flow with a stub engine (no LLM calls)."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient
from oc_extract.engine import CellOutcome
from oc_extract.schema import FieldSpec
from oc_extract.service import create_app

from .conftest import SAMPLE_CONTRACT

CANNED = {
    "parties": ["ACME Corporation", "Widgets Incorporated"],
    "monthly_fee": 12500.0,
}


class StubEngine:
    """Returns canned values keyed by field name; grounds nothing."""

    async def extract_cell(self, document: dict, field: FieldSpec) -> CellOutcome:
        if field.name not in CANNED:
            return CellOutcome(status="failed", failure_mode="error", error="no data")
        return CellOutcome(
            status="completed",
            value=CANNED[field.name],
            sources=[
                {
                    "kind": "retrieval",
                    "chunk_id": 0,
                    "start": 0,
                    "end": 20,
                    "page": None,
                    "snippet": "MASTER SERVICES AGRE",
                }
            ],
            llm_log="[]",
        )


@pytest.fixture
def client(tmp_path):
    app = create_app(
        db_path=str(tmp_path / "svc.db"), engine_factory=lambda extract: StubEngine()
    )
    with TestClient(app) as test_client:
        yield test_client


FIELDSET = {
    "name": "Key terms",
    "description": "",
    "fields": [
        {"name": "parties", "query": "Who are the parties?", "extract_is_list": True},
        {"name": "monthly_fee", "query": "Monthly fee?", "output_type": "float"},
    ],
}


def _wait_finished(client: TestClient, extract_id: int, timeout: float = 10.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        extract = client.get(f"/extracts/{extract_id}").json()
        if extract["finished"]:
            return extract
        time.sleep(0.05)
    raise AssertionError("extract did not finish in time")


def test_health(client: TestClient):
    assert client.get("/health").json()["status"] == "ok"


def test_full_extraction_flow(client: TestClient):
    # 1. Ingest documents (multiple in one call).
    resp = client.post(
        "/documents",
        json={"documents": [{"title": "MSA", "text": SAMPLE_CONTRACT}]},
    )
    assert resp.status_code == 201
    doc_id = resp.json()["document_ids"][0]

    # 2. Register a fieldset.
    resp = client.post("/fieldsets", json=FIELDSET)
    assert resp.status_code == 201
    fieldset_id = resp.json()["id"]
    assert len(resp.json()["fields"]) == 2

    # 3. Start an extract (runs in the background).
    resp = client.post(
        "/extracts",
        json={"name": "run 1", "fieldset_id": fieldset_id, "document_ids": [doc_id]},
    )
    assert resp.status_code == 202
    extract_id = resp.json()["id"]

    # 4. Poll to completion.
    extract = _wait_finished(client, extract_id)
    assert extract["cell_counts"] == {"total": 2, "completed": 2, "failed": 0}

    # 5. Results grid.
    rows = client.get(f"/extracts/{extract_id}/table").json()["rows"]
    assert len(rows) == 1
    assert rows[0]["values"]["parties"]["value"] == CANNED["parties"]
    assert rows[0]["values"]["monthly_fee"]["value"] == 12500.0

    # 6. Cells carry citations; llm_log only on request.
    cells = client.get(f"/extracts/{extract_id}/cells").json()["cells"]
    assert all(cell["sources"] for cell in cells)
    assert "llm_log" not in cells[0]
    cell = client.get(
        f"/cells/{cells[0]['id']}", params={"include_llm_log": True}
    ).json()
    assert cell["llm_log"] == "[]"


def test_upload_endpoint(client: TestClient):
    resp = client.post(
        "/documents/upload",
        files=[("files", ("note.txt", b"Hello extraction world", "text/plain"))],
    )
    assert resp.status_code == 201
    doc_id = resp.json()["document_ids"][0]
    doc = client.get(f"/documents/{doc_id}", params={"include_text": True}).json()
    assert doc["text"] == "Hello extraction world"


def test_upload_size_cap(client: TestClient, monkeypatch):
    from oc_extract import constants

    monkeypatch.setattr(constants, "MAX_UPLOAD_BYTES", 10)
    resp = client.post(
        "/documents/upload",
        files=[("files", ("big.txt", b"x" * 11, "text/plain"))],
    )
    assert resp.status_code == 413


def test_unsupported_upload_type(client: TestClient):
    resp = client.post(
        "/documents/upload",
        files=[("files", ("img.png", b"\x89PNG", "image/png"))],
    )
    assert resp.status_code == 415


def test_404s(client: TestClient):
    assert client.get("/documents/999").status_code == 404
    assert client.get("/fieldsets/999").status_code == 404
    assert client.get("/extracts/999").status_code == 404
    assert client.get("/cells/999").status_code == 404
    resp = client.post("/extracts", json={"fieldset_id": 999, "document_ids": [1]})
    assert resp.status_code == 404


def test_deferred_run(client: TestClient):
    doc_id = client.post(
        "/documents", json={"documents": [{"title": "d", "text": SAMPLE_CONTRACT}]}
    ).json()["document_ids"][0]
    fieldset_id = client.post("/fieldsets", json=FIELDSET).json()["id"]
    extract = client.post(
        "/extracts",
        json={
            "name": "later",
            "fieldset_id": fieldset_id,
            "document_ids": [doc_id],
            "run": False,
        },
    ).json()
    assert extract["started"] is None
    resp = client.post(f"/extracts/{extract['id']}/run")
    assert resp.status_code == 202
    finished = _wait_finished(client, extract["id"])
    assert finished["cell_counts"]["completed"] == 2
