"""
Integration tests that exercise the live Django GraphQL API over HTTP.

These tests are designed to run *inside* the Django container against
the running dev server (localhost:8000). They use ``requests`` to send
real HTTP traffic, authenticate via JWT, and verify end-to-end flows.

Run with:
    python manage.py test opencontractserver.tests.integration --keepdb

Or standalone:
    python -m pytest opencontractserver/tests/integration/test_api_flows.py -v
"""

import base64
import os
import time

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

API_BASE = os.environ.get("INTEGRATION_API_BASE", "http://localhost:8000")
GRAPHQL_URL = f"{API_BASE}/graphql/"
HEALTH_URL = f"{API_BASE}/api/health/"

SUPERUSER_USERNAME = os.environ.get("DJANGO_SUPERUSER_USERNAME", "admin")
SUPERUSER_PASSWORD = os.environ.get(
    "DJANGO_SUPERUSER_PASSWORD", "Openc0ntracts_def@ult"
)

# Path to a small PDF we can upload.  Reuses the existing test fixture.
FIXTURE_DIR = os.path.join(os.path.dirname(__file__), os.pardir, "fixtures")
SAMPLE_PDF = os.path.join(FIXTURE_DIR, "sample.pdf")

# Maximum seconds to wait for the server to become healthy.
STARTUP_TIMEOUT = int(os.environ.get("INTEGRATION_STARTUP_TIMEOUT", "120"))

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _wait_for_server() -> None:
    """Block until the health endpoint responds 200 or timeout is reached."""
    deadline = time.time() + STARTUP_TIMEOUT
    while time.time() < deadline:
        try:
            resp = requests.get(HEALTH_URL, timeout=5)
            if resp.status_code == 200:
                return
        except requests.ConnectionError:
            pass
        time.sleep(2)
    raise RuntimeError(
        f"Server at {API_BASE} did not become healthy within {STARTUP_TIMEOUT}s"
    )


def _graphql(
    query: str, variables: dict | None = None, token: str | None = None
) -> dict:
    """Execute a GraphQL request and return the parsed JSON body."""
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    payload: dict = {"query": query}
    if variables:
        payload["variables"] = variables
    resp = requests.post(GRAPHQL_URL, json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    body = resp.json()
    return body


def _get_token(username: str, password: str) -> str:
    """Obtain a JWT via the ``tokenAuth`` mutation."""
    query = """
        mutation TokenAuth($username: String!, $password: String!) {
            tokenAuth(username: $username, password: $password) {
                token
            }
        }
    """
    body = _graphql(query, {"username": username, "password": password})
    assert "errors" not in body, f"tokenAuth failed: {body.get('errors')}"
    token = body["data"]["tokenAuth"]["token"]
    assert token, "Received empty token"
    return token


def _read_fixture_pdf_b64() -> str:
    """Return the sample.pdf fixture as a base64-encoded string."""
    with open(SAMPLE_PDF, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestHealthCheck:
    """Smoke test: the health endpoint is reachable."""

    def test_health_returns_ok(self) -> None:
        _wait_for_server()
        resp = requests.get(HEALTH_URL, timeout=5)
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestTokenAuth:
    """Verify that the local JWT login flow works."""

    def test_valid_credentials_return_token(self) -> None:
        _wait_for_server()
        token = _get_token(SUPERUSER_USERNAME, SUPERUSER_PASSWORD)
        assert len(token) > 20, "Token looks too short"

    def test_invalid_credentials_return_error(self) -> None:
        _wait_for_server()
        body = _graphql(
            """
            mutation {
                tokenAuth(username: "nonexistent", password: "wrong") {
                    token
                }
            }
            """
        )
        assert "errors" in body, "Expected an error for bad credentials"


class TestCorpusLifecycle:
    """Create, query, and delete a corpus via GraphQL over HTTP."""

    def test_create_and_query_corpus(self) -> None:
        _wait_for_server()
        token = _get_token(SUPERUSER_USERNAME, SUPERUSER_PASSWORD)

        # 1. Create a corpus
        create_result = _graphql(
            """
            mutation CreateCorpus($title: String!, $description: String!) {
                createCorpus(title: $title, description: $description) {
                    ok
                    message
                    obj {
                        id
                        title
                        description
                    }
                }
            }
            """,
            {
                "title": "Integration Test Corpus",
                "description": "Created by integration test",
            },
            token=token,
        )
        assert (
            "errors" not in create_result
        ), f"createCorpus errors: {create_result.get('errors')}"
        data = create_result["data"]["createCorpus"]
        assert data["ok"] is True, f"createCorpus not ok: {data['message']}"
        corpus_id = data["obj"]["id"]
        assert corpus_id, "No corpus ID returned"
        assert data["obj"]["title"] == "Integration Test Corpus"

        # 2. Query corpuses and find the one we just created
        query_result = _graphql(
            """
            query {
                corpuses {
                    edges {
                        node {
                            id
                            title
                        }
                    }
                }
            }
            """,
            token=token,
        )
        assert (
            "errors" not in query_result
        ), f"corpuses query errors: {query_result.get('errors')}"
        nodes = [edge["node"] for edge in query_result["data"]["corpuses"]["edges"]]
        matching = [n for n in nodes if n["id"] == corpus_id]
        assert len(matching) == 1, f"Expected to find corpus {corpus_id} in list"

        # 3. Delete the corpus (cleanup)
        delete_result = _graphql(
            """
            mutation DeleteCorpus($id: String!) {
                deleteCorpus(id: $id) {
                    ok
                    message
                }
            }
            """,
            {"id": corpus_id},
            token=token,
        )
        assert (
            "errors" not in delete_result
        ), f"deleteCorpus errors: {delete_result.get('errors')}"
        assert delete_result["data"]["deleteCorpus"]["ok"] is True


class TestDocumentUpload:
    """Upload a document, query it, then clean up."""

    def test_upload_standalone_document(self) -> None:
        _wait_for_server()
        token = _get_token(SUPERUSER_USERNAME, SUPERUSER_PASSWORD)
        pdf_b64 = _read_fixture_pdf_b64()

        # 1. Upload
        upload_result = _graphql(
            """
            mutation UploadDoc(
                $base64FileString: String!,
                $filename: String!,
                $title: String!,
                $description: String!,
                $makePublic: Boolean!
            ) {
                uploadDocument(
                    base64FileString: $base64FileString,
                    filename: $filename,
                    title: $title,
                    description: $description,
                    makePublic: $makePublic
                ) {
                    ok
                    message
                    document {
                        id
                        title
                        description
                    }
                }
            }
            """,
            {
                "base64FileString": pdf_b64,
                "filename": "integration_test.pdf",
                "title": "Integration Test Document",
                "description": "Uploaded by integration test",
                "makePublic": False,
            },
            token=token,
        )
        assert (
            "errors" not in upload_result
        ), f"uploadDocument errors: {upload_result.get('errors')}"
        data = upload_result["data"]["uploadDocument"]
        assert data["ok"] is True, f"uploadDocument not ok: {data['message']}"
        doc_id = data["document"]["id"]
        assert doc_id, "No document ID returned"

        # 2. Query to verify
        query_result = _graphql(
            """
            query {
                documents {
                    edges {
                        node {
                            id
                            title
                        }
                    }
                }
            }
            """,
            token=token,
        )
        assert (
            "errors" not in query_result
        ), f"documents query errors: {query_result.get('errors')}"
        nodes = [edge["node"] for edge in query_result["data"]["documents"]["edges"]]
        matching = [n for n in nodes if n["id"] == doc_id]
        assert len(matching) == 1, f"Expected to find document {doc_id} in list"

        # 3. Delete document (cleanup)
        delete_result = _graphql(
            """
            mutation DeleteDoc($id: String!) {
                deleteDocument(id: $id) {
                    ok
                    message
                }
            }
            """,
            {"id": doc_id},
            token=token,
        )
        assert (
            "errors" not in delete_result
        ), f"deleteDocument errors: {delete_result.get('errors')}"
        assert delete_result["data"]["deleteDocument"]["ok"] is True

    def test_upload_document_to_corpus(self) -> None:
        _wait_for_server()
        token = _get_token(SUPERUSER_USERNAME, SUPERUSER_PASSWORD)
        pdf_b64 = _read_fixture_pdf_b64()

        # 1. Create a corpus first
        corpus_result = _graphql(
            """
            mutation CreateCorpus($title: String!, $description: String!) {
                createCorpus(title: $title, description: $description) {
                    ok
                    obj {
                        id
                    }
                }
            }
            """,
            {
                "title": "Doc Upload Test Corpus",
                "description": "For document upload test",
            },
            token=token,
        )
        assert (
            "errors" not in corpus_result
        ), f"createCorpus errors: {corpus_result.get('errors')}"
        corpus_id = corpus_result["data"]["createCorpus"]["obj"]["id"]

        # 2. Upload document into the corpus
        upload_result = _graphql(
            """
            mutation UploadDoc(
                $base64FileString: String!,
                $filename: String!,
                $title: String!,
                $description: String!,
                $makePublic: Boolean!,
                $addToCorpusId: ID
            ) {
                uploadDocument(
                    base64FileString: $base64FileString,
                    filename: $filename,
                    title: $title,
                    description: $description,
                    makePublic: $makePublic,
                    addToCorpusId: $addToCorpusId
                ) {
                    ok
                    message
                    document {
                        id
                        title
                    }
                }
            }
            """,
            {
                "base64FileString": pdf_b64,
                "filename": "corpus_doc.pdf",
                "title": "Corpus Test Document",
                "description": "Uploaded into corpus by integration test",
                "makePublic": False,
                "addToCorpusId": corpus_id,
            },
            token=token,
        )
        assert (
            "errors" not in upload_result
        ), f"uploadDocument errors: {upload_result.get('errors')}"
        data = upload_result["data"]["uploadDocument"]
        assert data["ok"] is True, f"uploadDocument not ok: {data['message']}"
        doc_id = data["document"]["id"]

        # 3. Query the corpus and verify the document is linked
        corpus_query = _graphql(
            """
            query GetCorpus($id: ID!) {
                corpus(id: $id) {
                    id
                    title
                    documents {
                        edges {
                            node {
                                id
                                title
                            }
                        }
                    }
                }
            }
            """,
            {"id": corpus_id},
            token=token,
        )
        assert (
            "errors" not in corpus_query
        ), f"corpus query errors: {corpus_query.get('errors')}"
        corpus_docs = [
            edge["node"]
            for edge in corpus_query["data"]["corpus"]["documents"]["edges"]
        ]
        doc_ids = [d["id"] for d in corpus_docs]
        assert (
            doc_id in doc_ids
        ), f"Document {doc_id} not found in corpus documents: {doc_ids}"

        # 4. Cleanup: delete document then corpus
        _graphql(
            """
            mutation DeleteDoc($id: String!) {
                deleteDocument(id: $id) { ok }
            }
            """,
            {"id": doc_id},
            token=token,
        )
        _graphql(
            """
            mutation DeleteCorpus($id: String!) {
                deleteCorpus(id: $id) { ok }
            }
            """,
            {"id": corpus_id},
            token=token,
        )


class TestUnauthenticatedAccess:
    """Verify that unauthenticated requests are properly rejected."""

    def test_create_corpus_without_token_fails(self) -> None:
        _wait_for_server()
        result = _graphql(
            """
            mutation {
                createCorpus(title: "Should Fail", description: "No auth") {
                    ok
                    message
                }
            }
            """
        )
        # Should either have errors or ok=False
        has_errors = "errors" in result
        not_ok = (
            result.get("data", {}).get("createCorpus", {}).get("ok") is False
            if not has_errors
            else False
        )
        assert has_errors or not_ok, "Expected unauthenticated createCorpus to fail"

    def test_upload_document_without_token_fails(self) -> None:
        _wait_for_server()
        result = _graphql(
            """
            mutation {
                uploadDocument(
                    base64FileString: "dGVzdA==",
                    filename: "test.pdf",
                    title: "Should Fail",
                    description: "No auth",
                    makePublic: false
                ) {
                    ok
                    message
                }
            }
            """
        )
        has_errors = "errors" in result
        not_ok = (
            result.get("data", {}).get("uploadDocument", {}).get("ok") is False
            if not has_errors
            else False
        )
        assert has_errors or not_ok, "Expected unauthenticated uploadDocument to fail"
