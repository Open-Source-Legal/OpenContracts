"""Unit tests for the CLI's auth modes, GraphQL-contract fixes, corpus-id
normalization, and chunked-transport helpers (PR #2038 fix). Pure Python — no
Docker, no network."""

import base64
import importlib.util
import io
import os
import sys

_spec = importlib.util.spec_from_file_location(
    "ocbi",
    os.path.join(os.path.dirname(__file__), "..", "oc_bulk_import.py"),
)
ocbi = importlib.util.module_from_spec(_spec)
sys.modules["ocbi"] = ocbi
_spec.loader.exec_module(ocbi)


# --- auth modes ------------------------------------------------------------
def test_worker_token_rest_header_only():
    c = ocbi.OCClient("http://x", worker_token="wk_abc")
    assert c.rest_headers() == {"Authorization": "WorkerKey wk_abc"}
    # WorkerKey is meaningless to GraphQL, so it must not be sent there.
    assert c.graphql_headers() == {}


def test_bearer_token_both_surfaces():
    c = ocbi.OCClient("http://x", bearer_token="jwt123")
    assert c.rest_headers() == {"Authorization": "Bearer jwt123"}
    assert c.graphql_headers() == {"Authorization": "Bearer jwt123"}


def test_unauthenticated_sends_no_headers():
    c = ocbi.OCClient("http://x")
    assert c.rest_headers() == {}
    assert c.graphql_headers() == {}


def test_can_reauth_only_with_password_and_not_worker_token():
    c = ocbi.OCClient("http://x")
    assert c._can_reauth is False
    c.set_password_credentials("u", "p")
    assert c._can_reauth is True
    w = ocbi.OCClient("http://x", worker_token="wk")
    w.set_password_credentials("u", "p")
    assert w._can_reauth is False  # worker-token mode never re-exchanges


# --- GraphQL contract fixes ------------------------------------------------
def test_tokenauth_query_selects_token_only():
    assert "refreshToken" not in ocbi.OCClient._TOKEN_AUTH_QUERY
    assert "token" in ocbi.OCClient._TOKEN_AUTH_QUERY


def test_create_corpus_query_uses_objid():
    q = ocbi.OCClient._CREATE_CORPUS_QUERY
    assert "objId" in q
    assert "obj{" not in q.replace(" ", "")


# --- corpus-id normalization ----------------------------------------------
def test_to_global_corpus_id_encodes_bare_int():
    gid = ocbi._to_global_corpus_id("32")
    assert base64.b64decode(gid).decode() == "CorpusType:32"


def test_to_global_corpus_id_passthrough_for_global_id():
    existing = base64.b64encode(b"CorpusType:32").decode()
    assert ocbi._to_global_corpus_id(existing) == existing


# --- chunked transport helpers ---------------------------------------------
def test_should_chunk_threshold():
    assert ocbi._should_chunk(ocbi.CHUNK_THRESHOLD_BYTES + 1) is True
    assert ocbi._should_chunk(ocbi.CHUNK_THRESHOLD_BYTES) is False


def test_iter_chunks_splits_and_rewinds():
    stream = io.BytesIO(b"0123456789")
    stream.read(3)  # move position; _iter_chunks must rewind first
    chunks = [bytes(c) for c in ocbi._iter_chunks(stream, 4)]
    assert chunks == [b"0123", b"4567", b"89"]


def test_chunk_size_under_backend_part_cap():
    # Backend CHUNKED_UPLOAD_PART_MAX_BYTES default is 90 MB; stay below it.
    assert ocbi.CHUNK_SIZE_BYTES <= 90 * 1024 * 1024
