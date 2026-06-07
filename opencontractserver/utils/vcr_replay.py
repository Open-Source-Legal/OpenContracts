"""
Optional VCR.py wrapper for the LLM extraction pipeline.

When the env vars below are set, the agent's HTTP traffic to the LLM
provider (OpenAI / Anthropic) is recorded to or replayed from a cassette
file. The intended use case is CI / smoke tests for the extract pipeline
that need a real run end-to-end but cannot afford to call the LLM
provider on every CI run.

Env vars:
    OC_LLM_VCR_MODE
        ``record``       - capture all LLM calls to the cassette file
                           (overwrites existing cassette).
        ``once``         - record if the cassette is missing, replay if it
                           exists. Convenient for the first run.
        ``replay``       - replay only; raise if a request has no match.
        unset / empty    - bypass VCR entirely (production behavior).
    OC_LLM_VCR_CASSETTE
        Filesystem path to the cassette YAML file. Required when MODE is
        set; ignored otherwise.

The wrapper is intentionally narrow: it only wraps the LLM agent call in
``doc_extract_query_task``. We don't blanket-wrap the whole task because
unrelated HTTP traffic (LlamaParse, embedder microservice, S3) should
keep going to its real endpoints during E2E runs — those services run in
the local docker stack and don't cost money to call.

Implementation note: VCR matches by method + URI + body. Our extract
prompts contain RUN_ID timestamps from the E2E spec, which make bodies
differ across runs. We therefore strip volatile fields from the request
body before matching. See ``_match_llm_body`` below.
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Iterator
from contextlib import contextmanager

logger = logging.getLogger(__name__)


def ensure_aiohttp_vcr_compat() -> None:
    """Make vcrpy 8.1.1's aiohttp stub importable under aiohttp >= 3.14.

    vcrpy 8.1.1 (the latest release) defines
    ``class MockStream(asyncio.StreamReader, streams.AsyncStreamReaderMixin)``
    in ``vcr/stubs/aiohttp_stubs.py``. aiohttp 3.14 removed
    ``aiohttp.streams.AsyncStreamReaderMixin`` (its helpers were folded onto the
    stream classes). vcrpy imports that stub lazily — when a cassette is entered
    and ``vcr/patch.py`` builds its patchers — so under aiohttp >= 3.14 every VCR
    cassette entry raises ``AttributeError`` (issue #1920; upstream
    kevin1024/vcrpy#995, fix proposed in the unreleased PR #996).

    This codebase only records/replays *httpx* (LLM provider) cassettes — the
    aiohttp stub is pulled in incidentally because aiohttp is importable
    (transitive via llama-index-core). ``MockStream`` is therefore never
    instantiated here, so restoring the removed name as an empty mixin is enough
    to let the stub's class body evaluate; none of the mixin's (now-removed)
    helper methods are exercised.

    Idempotent, and a no-op under aiohttp < 3.14 (where the real mixin is still
    present — it is left untouched). Delete this shim, and bump ``vcrpy`` in
    requirements/local.txt, once vcrpy ships a release that supports the aiohttp
    3.14 stream API.
    """
    try:
        from aiohttp import streams
    except ModuleNotFoundError:
        # aiohttp isn't installed → vcrpy won't load its aiohttp stub anyway.
        return

    if hasattr(streams, "AsyncStreamReaderMixin"):
        return

    class AsyncStreamReaderMixin:
        """Empty stand-in for the base class aiohttp 3.14 removed.

        Only needs to exist so vcrpy's ``MockStream`` class statement can
        evaluate; its methods are never called (we never replay aiohttp
        cassettes).
        """

    # setattr (string name) rather than attribute assignment so mypy does not
    # flag a member aiohttp 3.14 removed from the ``streams`` module.
    setattr(streams, "AsyncStreamReaderMixin", AsyncStreamReaderMixin)


# These hostnames are the LLM provider endpoints VCR should intercept.
# Other hosts (LlamaParse, embedder microservice, S3) bypass VCR.
_LLM_HOSTS = {"api.openai.com", "api.anthropic.com"}

# Volatile values inside extract requests that change across runs and
# would otherwise prevent VCR from matching a recorded cassette entry.
#
#   - RUN_ID: millisecond timestamp the Playwright spec splices into
#     corpus / document / extract names.
#   - "(ID: 56)": Django auto-increment document primary key the
#     structured-extraction system prompt embeds — varies per fresh DB.
#   - "call_xxx": OpenAI tool-call IDs the assistant generates per turn.
#   - "<docling-..." / similar — defensive: parser-emitted UUIDs that
#     may surface in retrieval-result content.
_VOLATILE_PATTERNS = [
    re.compile(rb"\b1[789]\d{11,12}\b"),  # 13-digit ms timestamps in the 2026 era
    re.compile(rb"\(ID:\s*\d+\)"),  # Django document PK in the system prompt
    re.compile(rb'"id"\s*:\s*"call_[A-Za-z0-9]+"'),  # OpenAI tool-call IDs
    re.compile(rb'"tool_call_id"\s*:\s*"call_[A-Za-z0-9]+"'),
    # UUIDs that occasionally appear in tool returns (annotation IDs etc.)
    re.compile(rb"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"),
    # Tool-result payloads embed Django auto-increment PKs for
    # annotations, corpuses, documents, and labels. These vary across
    # runs (a fresh test DB hands out different IDs than the recording
    # DB) but VCR matches on full request body, including the tool
    # messages echoed back into the next assistant call. Strip them so
    # the matcher sees a stable shape.
    #
    # Tool messages are JSON-encoded strings *inside* the chat-completion
    # request JSON, so the inner quotes appear escaped (`\"annotation_id\":`).
    # The leading `\\?` makes both the bare-JSON and the escaped-string
    # forms match the same pattern.
    re.compile(rb'\\?"annotation_id\\?"\s*:\s*(?:null|\d+)'),
    re.compile(rb'\\?"corpus_id\\?"\s*:\s*(?:null|\d+)'),
    re.compile(rb'\\?"document_id\\?"\s*:\s*(?:null|\d+)'),
    re.compile(rb'\\?"label_id\\?"\s*:\s*(?:null|\d+)'),
    # Generic numeric `"id":N` fields in tool returns (annotation rows,
    # corpus references, etc.). Also handles the escaped-string variant.
    re.compile(rb'\\?"id\\?"\s*:\s*\d+'),
    # Float fields whose exact value drifts run-to-run because the
    # embedder microservice and the pgvector hybrid-search fusion
    # produce slightly different scores even for identical inputs (token
    # IDs differ when the doc/corpus title contains a fresh RUN_ID, the
    # vector index is a fresh build, etc.). The stable signal is the
    # ranking — the actual numeric score should not gate cassette match.
    re.compile(rb'\\?"similarity_score\\?"\s*:\s*[-\d.eE+]+'),
    re.compile(rb'\\?"score\\?"\s*:\s*[-\d.eE+]+'),
]


def _normalize_body(body) -> bytes:
    """Strip volatile fields so cassette matches survive run-to-run.

    VCR can hand us the body as ``bytes``, ``str``, ``None``, or
    occasionally a dict (already-parsed JSON). Coerce everything to bytes
    before running the volatility regexes; an empty / missing body is
    returned as an empty byte string so the matcher can short-circuit.
    """
    if body is None:
        return b""
    if isinstance(body, str):
        body = body.encode("utf-8")
    elif isinstance(body, dict):
        # vcr's stub for httpx may pre-parse JSON bodies; re-encode.
        import json

        body = json.dumps(body, sort_keys=True).encode("utf-8")
    elif not isinstance(body, (bytes, bytearray)):
        # Last-resort coercion — repr() so debug logging is still useful.
        body = repr(body).encode("utf-8")
    for pat in _VOLATILE_PATTERNS:
        body = pat.sub(b"<volatile>", body)
    return bytes(body)


def _match_llm_body(r1, r2) -> None:
    """Custom VCR matcher that compares LLM bodies after volatility strip."""
    a = _normalize_body(getattr(r1, "body", None))
    b = _normalize_body(getattr(r2, "body", None))
    if a != b:
        # Diagnostic: log the first byte difference + a window of context to
        # /tmp/vcr-mismatch-<pid>.log so the operator can see why a recorded
        # cassette failed to match. Only the FIRST mismatch is useful (the
        # cassette gets reloaded each run); we therefore append, not write,
        # so multiple runs leave a paper trail.
        if os.environ.get("OC_LLM_VCR_DEBUG"):
            try:
                import json

                debug_path = f"/tmp/vcr-mismatch-{os.getpid()}.log"
                first_diff = next(
                    (i for i, (x, y) in enumerate(zip(a, b)) if x != y),
                    min(len(a), len(b)),
                )
                with open(debug_path, "a") as fh:
                    fh.write(
                        json.dumps(
                            {
                                "len_a": len(a),
                                "len_b": len(b),
                                "first_diff": first_diff,
                                "ctx_a": a[
                                    max(0, first_diff - 200) : first_diff + 200
                                ].decode("utf-8", "replace"),
                                "ctx_b": b[
                                    max(0, first_diff - 200) : first_diff + 200
                                ].decode("utf-8", "replace"),
                            }
                        )
                        + "\n"
                    )
            except Exception:  # pragma: no cover — best-effort debug
                pass
        # VCR matchers raise AssertionError on mismatch; the actual exception
        # type doesn't matter as long as it's truthy-on-failure.
        raise AssertionError("normalized LLM body mismatch")


@contextmanager
def maybe_vcr_cassette() -> Iterator[object | None]:
    """
    Yield either an active VCR cassette context (when env says so) or
    None (the no-op path used in production).

    Usage::

        with maybe_vcr_cassette():
            await agent.run(...)
    """
    mode = os.environ.get("OC_LLM_VCR_MODE", "").strip().lower()
    if mode in ("", "off", "none-disabled"):
        # Special-case: empty or "off" means "don't use VCR at all".
        # We use "none-disabled" instead of "none" because VCR itself
        # treats "none" as a record_mode meaning "replay only".
        yield None
        return

    cassette_path = os.environ.get("OC_LLM_VCR_CASSETTE", "").strip()
    if not cassette_path:
        logger.warning(
            "OC_LLM_VCR_MODE=%s but OC_LLM_VCR_CASSETTE is unset; bypassing VCR",
            mode,
        )
        yield None
        return

    # Map our friendly mode names to vcrpy record_mode values.
    record_mode = {
        "record": "all",
        "once": "once",
        "replay": "none",
    }.get(mode)
    if record_mode is None:
        logger.warning(
            "Unknown OC_LLM_VCR_MODE=%s; expected record|once|replay. Bypassing VCR.",
            mode,
        )
        yield None
        return

    # vcrpy 8.1.1's aiohttp stub references a symbol aiohttp 3.14 removed;
    # restore it before importing vcr so the live E2E record/replay harness
    # (which runs outside pytest, where conftest isn't loaded) also works under
    # aiohttp >= 3.14. See ensure_aiohttp_vcr_compat above and issue #1920.
    ensure_aiohttp_vcr_compat()
    import vcr  # local import keeps prod paths free of vcr cost

    cassette_dir = os.path.dirname(os.path.abspath(cassette_path))
    if cassette_dir:
        os.makedirs(cassette_dir, exist_ok=True)

    # The cassette intentionally only covers LLM provider HTTP traffic
    # (api.openai.com / api.anthropic.com). Other hosts visited from the
    # extract task — LlamaParse, the embedder microservice, S3 — must
    # continue to hit their real endpoints. We use ``ignore_hosts`` for
    # that, configured by inverting ``_LLM_HOSTS``: anything that's not
    # an LLM provider is told to bypass VCR. This also has to work in
    # both record and replay modes, which ``before_record_request``
    # does not (it only affects recording).
    # Matchers:
    #
    #   * In ``record`` mode we want strict body matching so a re-record
    #     against the same fixtures still produces a deterministic
    #     cassette (and so partial re-records don't accidentally collide
    #     with stale entries in the same file).
    #
    #   * In ``replay`` mode we deliberately drop body matching. The
    #     pydantic-ai agent loop echoes every prior tool result back into
    #     the next request body, and tool results contain content that
    #     varies run-to-run for reasons the matcher cannot strip cleanly:
    #     the vector-embedder microservice (which is NOT cassette-wrapped
    #     because it is not an LLM provider) returns slightly different
    #     similarity orderings against a fresh corpus, and the order
    #     leaks the actual chunk content into subsequent requests.
    #     Strict body matching therefore breaks replay even when the
    #     conversation transcript is otherwise correct.
    #
    #     Falling back to URL+method matching makes VCR replay the
    #     interactions in cassette order. That is sufficient for our
    #     extract pipeline because the celery worker processes datacells
    #     sequentially, the model is effectively deterministic
    #     (temperature pinned), and the cassette captures the full
    #     successful conversation per document.
    match_on: tuple[str, ...]
    if record_mode == "none":
        match_on = ("method", "scheme", "host", "port", "path")
    else:
        match_on = ("method", "scheme", "host", "port", "path", "llm_body")
    my_vcr = vcr.VCR(
        cassette_library_dir=cassette_dir or ".",
        record_mode=record_mode,
        match_on=match_on,
        filter_headers=[
            "authorization",
            "x-api-key",
            "openai-organization",
            "openai-project",
        ],
        decode_compressed_response=True,
        ignore_hosts=("localhost", "127.0.0.1"),
    )
    my_vcr.register_matcher("llm_body", _match_llm_body)

    # Hosts to skip recording/replay for — everything except LLM
    # providers. Computed lazily because the host list is short.
    def _ignore_request(request) -> bool:
        return request.host not in _LLM_HOSTS

    my_vcr.before_record_request = lambda req: req if not _ignore_request(req) else None
    # ``record_mode=none`` (replay) plus our ignore filter means: for
    # non-LLM hosts the request passes through to the real network; for
    # LLM hosts a missing cassette entry raises
    # CannotOverwriteExistingCassetteException, which is what we want.

    cassette_filename = os.path.basename(cassette_path)
    logger.info(
        "VCR active: mode=%s record_mode=%s cassette=%s",
        mode,
        record_mode,
        cassette_path,
    )
    with my_vcr.use_cassette(cassette_filename) as cassette:
        yield cassette
