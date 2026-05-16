"""Tests for the privacy-filter HTTP client (no live container required)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from django.test import TestCase, override_settings

from opencontractserver.constants.document_processing import (
    PRIVACY_FILTER_CHUNK_OVERLAP,
    PRIVACY_FILTER_CHUNK_SIZE,
)
from opencontractserver.llms.tools.core_tools._privacy_filter_client import (
    adetect_pii,
)


def _mock_response(payload: dict, status_code: int = 200) -> MagicMock:
    """Build a MagicMock that emulates an httpx.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json = MagicMock(return_value=payload)
    resp.text = "" if status_code == 200 else "boom"
    return resp


@override_settings(
    PRIVACY_FILTER_URL="http://privacy_filter:8000",
    PRIVACY_FILTER_API_KEY="dev-only-not-secret",
    PRIVACY_FILTER_TIMEOUT_SECONDS=5,
)
class PrivacyFilterClientSingleChunkTests(TestCase):
    async def test_single_chunk_returns_remapped_detections(self) -> None:
        text = "Email me at alice@example.com tomorrow."
        # Privacy-filter detection coords are relative to the chunk it sees.
        # Single chunk == identical to whole input.
        payload = {
            "detections": [
                {
                    "entity_group": "private_email",
                    "score": 0.99,
                    "word": "alice@example.com",
                    "start": 12,
                    "end": 29,
                }
            ],
            "model": "openai/privacy-filter",
            "model_revision": "deadbeef",
        }

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=_mock_response(payload))

        with patch(
            "opencontractserver.llms.tools.core_tools._privacy_filter_client.httpx.AsyncClient",
            return_value=mock_client,
        ):
            detections = await adetect_pii(text)

        assert len(detections) == 1
        d = detections[0]
        assert d["entity_group"] == "private_email"
        assert d["score"] == pytest.approx(0.99)
        assert d["start"] == 12
        assert d["end"] == 29
        # The client re-derives `text` from input — should equal slice.
        assert d["text"] == "alice@example.com"

        # Verify HTTP wiring.
        mock_client.post.assert_awaited_once()
        call = mock_client.post.await_args
        # URL should be the configured endpoint.
        assert call.args[0].endswith("/v1/detect")
        # Headers carry the API key (always passed as a kwarg in the client).
        headers = call.kwargs.get("headers", {})
        assert headers["X-API-Key"] == "dev-only-not-secret"
        # Body has full text (single chunk).
        assert call.kwargs["json"] == {"text": text}


@override_settings(
    PRIVACY_FILTER_URL="http://privacy_filter:8000",
    PRIVACY_FILTER_API_KEY="key",
    PRIVACY_FILTER_TIMEOUT_SECONDS=5,
)
class PrivacyFilterClientMultiChunkTests(TestCase):
    async def test_multi_chunk_remaps_offsets_correctly(self) -> None:
        # Build a text > PRIVACY_FILTER_CHUNK_SIZE so the client has to split.
        # Place the target string at exactly that index in the full text so it
        # lands entirely in chunk #2 (which starts at
        # PRIVACY_FILTER_CHUNK_SIZE - PRIVACY_FILTER_CHUNK_OVERLAP).
        target = "alice@example.com"
        prefix = "x" * PRIVACY_FILTER_CHUNK_SIZE  # length == PRIVACY_FILTER_CHUNK_SIZE
        text = prefix + target + "y" * 100
        assert len(text) > PRIVACY_FILTER_CHUNK_SIZE

        # Mock returns nothing for chunk 1, returns the target for chunk 2.
        def _payload_for_call(call_idx: int) -> dict:
            if call_idx == 0:
                return {"detections": [], "model": "m", "model_revision": "r"}
            chunk_start_global = (
                PRIVACY_FILTER_CHUNK_SIZE - PRIVACY_FILTER_CHUNK_OVERLAP
            )
            local_start = len(prefix) - chunk_start_global
            return {
                "detections": [
                    {
                        "entity_group": "private_email",
                        "score": 0.95,
                        "word": target,
                        "start": local_start,
                        "end": local_start + len(target),
                    }
                ],
                "model": "m",
                "model_revision": "r",
            }

        call_counter = {"n": 0}

        async def _post(*_args, **_kwargs):
            payload = _payload_for_call(call_counter["n"])
            call_counter["n"] += 1
            return _mock_response(payload)

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=_post)

        with patch(
            "opencontractserver.llms.tools.core_tools._privacy_filter_client.httpx.AsyncClient",
            return_value=mock_client,
        ):
            detections = await adetect_pii(text)

        assert call_counter["n"] >= 2  # at least 2 chunks issued
        assert len(detections) == 1
        d = detections[0]
        assert d["start"] == len(prefix)
        assert d["end"] == len(prefix) + len(target)
        assert d["text"] == target

    async def test_dedup_when_overlap_returns_same_detection(self) -> None:
        # Force two chunks to both report the same global detection.
        target = "alice@example.com"
        # Position target inside the overlap region (last
        # PRIVACY_FILTER_CHUNK_OVERLAP chars of chunk 1 == first
        # PRIVACY_FILTER_CHUNK_OVERLAP chars of chunk 2).
        target_start_global = (
            PRIVACY_FILTER_CHUNK_SIZE - PRIVACY_FILTER_CHUNK_OVERLAP + 50
        )
        prefix = "x" * target_start_global
        text = prefix + target + "y" * 1000

        global_start = target_start_global
        global_end = global_start + len(target)

        def _payload_for_call(call_idx: int) -> dict:
            if call_idx == 0:
                # chunk 1 starts at 0 — local offsets == global offsets
                return {
                    "detections": [
                        {
                            "entity_group": "private_email",
                            "score": 0.99,
                            "word": target,
                            "start": global_start,
                            "end": global_end,
                        }
                    ],
                    "model": "m",
                    "model_revision": "r",
                }
            # chunk 2 starts at PRIVACY_FILTER_CHUNK_SIZE - PRIVACY_FILTER_CHUNK_OVERLAP
            chunk_start_global = (
                PRIVACY_FILTER_CHUNK_SIZE - PRIVACY_FILTER_CHUNK_OVERLAP
            )
            return {
                "detections": [
                    {
                        "entity_group": "private_email",
                        "score": 0.99,
                        "word": target,
                        "start": global_start - chunk_start_global,
                        "end": global_end - chunk_start_global,
                    }
                ],
                "model": "m",
                "model_revision": "r",
            }

        call_counter = {"n": 0}

        async def _post(*_args, **_kwargs):
            payload = _payload_for_call(call_counter["n"])
            call_counter["n"] += 1
            return _mock_response(payload)

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=_post)

        with patch(
            "opencontractserver.llms.tools.core_tools._privacy_filter_client.httpx.AsyncClient",
            return_value=mock_client,
        ):
            detections = await adetect_pii(text)

        assert call_counter["n"] >= 2
        assert len(detections) == 1
        assert detections[0]["start"] == global_start
        assert detections[0]["end"] == global_end

    async def test_transport_failure_is_converted_to_runtime_error(self) -> None:
        """httpx.TimeoutException / ConnectError must surface as RuntimeError
        so the agent tool fault-tolerance layer can convert them into an
        error string the LLM can react to (raw httpx exceptions would
        bypass that contract).
        """
        import httpx

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(
            side_effect=httpx.ConnectError("simulated connection refused")
        )

        with patch(
            "opencontractserver.llms.tools.core_tools._privacy_filter_client.httpx.AsyncClient",
            return_value=mock_client,
        ):
            with pytest.raises(RuntimeError) as exc:
                await adetect_pii("hello world")
        assert "privacy-filter request failed" in str(exc.value)
        assert "ConnectError" in str(exc.value)

    async def test_non_2xx_raises_runtime_error(self) -> None:
        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=_mock_response({}, status_code=503))

        with patch(
            "opencontractserver.llms.tools.core_tools._privacy_filter_client.httpx.AsyncClient",
            return_value=mock_client,
        ):
            with pytest.raises(RuntimeError) as exc:
                await adetect_pii("hello world")

        assert "503" in str(exc.value)

    async def test_empty_url_raises(self) -> None:
        with override_settings(PRIVACY_FILTER_URL=""):
            with pytest.raises(RuntimeError) as exc:
                await adetect_pii("hello world")
        assert "not configured" in str(exc.value).lower()

    async def test_empty_input_returns_empty_list(self) -> None:
        detections = await adetect_pii("")
        assert detections == []

    async def test_empty_api_key_logs_warning_once(self) -> None:
        """When ``PRIVACY_FILTER_URL`` is set but ``PRIVACY_FILTER_API_KEY``
        is empty, the client must:

        1. Continue to issue the request (deployment is opt-in, see
           ``_privacy_filter_client.py`` for the rationale).
        2. Emit a single ``logger.warning`` so the misconfiguration shows
           up in logs instead of silently shipping with no auth.
        3. Suppress the warning on subsequent calls so log volume doesn't
           grow with PII-scan call volume.

        We reset the module-level guard before *and* after so this test
        is order-independent — without the explicit reset another test
        could flip the flag first and we'd never observe the warning.
        """
        from opencontractserver.llms.tools.core_tools import (
            _privacy_filter_client as pf,
        )

        original = pf._warned_about_missing_api_key
        pf._warned_about_missing_api_key = False
        try:
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(
                return_value=_mock_response({"detections": []})
            )

            with override_settings(
                PRIVACY_FILTER_URL="http://privacy_filter:8000",
                PRIVACY_FILTER_API_KEY="",
            ):
                with patch(
                    "opencontractserver.llms.tools.core_tools._privacy_filter_client.httpx.AsyncClient",
                    return_value=mock_client,
                ):
                    with self.assertLogs(pf.logger, level="WARNING") as first_logs:
                        detections1 = await adetect_pii("hello world")
                    # Second call must NOT re-emit the warning.
                    with self.assertNoLogs(pf.logger, level="WARNING"):
                        detections2 = await adetect_pii("hello again")

            assert detections1 == []
            assert detections2 == []
            assert any(
                "PRIVACY_FILTER_API_KEY is empty" in msg for msg in first_logs.output
            )
            # Confirm the request actually went out unauthenticated.
            assert mock_client.post.await_count == 2
            sent_headers = mock_client.post.await_args_list[0].kwargs["headers"]
            assert sent_headers.get("X-API-Key") == ""
        finally:
            pf._warned_about_missing_api_key = original
