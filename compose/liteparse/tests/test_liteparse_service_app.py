"""HTTP tests for the LiteParse service app.

Needs ``fastapi`` and ``liteparse`` (the service image's deps), so it skips in
the OpenContracts CI image; run it locally against a venv with both installed.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

pytest.importorskip("fastapi")
liteparse = pytest.importorskip("liteparse")

sys.path.insert(0, str(Path(__file__).parents[1]))

from fastapi.testclient import TestClient  # noqa: E402
from liteparse_service.app import create_app  # noqa: E402
from liteparse_service.projection import SCHEMA_VERSION  # noqa: E402
from liteparse_service.runtime import ServiceConfig  # noqa: E402

PDF_BYTES = b"%PDF-1.7\n1 0 obj\n<</Type/Catalog>>\nendobj\n%%EOF\n"


def _config(**overrides) -> ServiceConfig:
    values = dict(
        api_key="secret",
        pool_size=1,
        parse_timeout=10.0,
        ocr_workers=1,
        max_pages=50,
        max_upload_mb=5,
        model_version="1.0.0",
    )
    values.update(overrides)
    return ServiceConfig(**values)


def _result(*, pages=1, total_pages=None):
    page = NS(page_num=1, width=612.0, height=792.0, text_items=[], blocks=None)
    return NS(
        pages=[page] * pages,
        total_pages=pages if total_pages is None else total_pages,
        page_errors=[],
    )


class FakeParser:
    def __init__(self, *, result=None, error=None):
        self.result = result if result is not None else _result()
        self.error = error
        self.calls: list[bytes] = []

    def parse(self, file_data: bytes):
        self.calls.append(file_data)
        if self.error is not None:
            raise self.error
        return self.result


def _client(parser=None, **config) -> TestClient:
    app = create_app(
        config=_config(**config),
        parser=parser or FakeParser(),
        liteparse_version="2.21.3",
    )
    return TestClient(app)


def _post(client, body=PDF_BYTES, key="secret"):
    headers = {} if key is None else {"X-API-Key": key}
    return client.post(
        "/parse", files={"file": ("a.pdf", body, "application/pdf")}, headers=headers
    )


def test_health_reports_versions():
    response = _client().get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "liteparse_version": "2.21.3",
        "model_version": "1.0.0",
        "schema_version": SCHEMA_VERSION,
    }


def test_parse_requires_api_key():
    parser = FakeParser()
    client = _client(parser)
    assert _post(client, key=None).status_code == 401
    assert _post(client, key="wrong").status_code == 401
    assert parser.calls == []


def test_parse_rejects_non_pdf_with_415():
    parser = FakeParser()
    response = _post(_client(parser), body=b"PK\x03\x04 not a pdf")
    assert response.status_code == 415
    assert parser.calls == []


def test_parse_rejects_oversize_with_413():
    parser = FakeParser()
    response = _post(_client(parser, max_upload_mb=0))
    assert response.status_code == 413
    assert parser.calls == []


def test_parse_error_maps_to_422():
    parser = FakeParser(error=liteparse.ParseError("encrypted document"))
    response = _post(_client(parser))
    assert response.status_code == 422
    assert "encrypted document" in response.json()["detail"]


def test_parse_timeout_maps_to_504():
    error = liteparse.ParseTimeoutError("too slow", source="<10 bytes>", timeout=10.0)
    response = _post(_client(FakeParser(error=error)))
    assert response.status_code == 504


def test_parse_rejects_truncated_result_with_413():
    parser = FakeParser(result=_result(pages=2, total_pages=9))
    response = _post(_client(parser, max_pages=2))
    assert response.status_code == 413
    detail = response.json()["detail"]
    assert "9" in detail and "2" in detail


def test_parse_success_returns_projection():
    parser = FakeParser()
    response = _post(_client(parser))
    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == SCHEMA_VERSION
    assert body["liteparse_version"] == "2.21.3"
    assert body["model_version"] == "1.0.0"
    assert body["pages"][0]["blocks"] == []
    assert parser.calls == [PDF_BYTES]
