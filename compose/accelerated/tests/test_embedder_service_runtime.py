from __future__ import annotations

import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "embedder"))

from batching import DynamicBatcher  # noqa: E402
from service_runtime import (  # noqa: E402
    SerializedModelOwner,
    all_non_empty_strings,
    api_key_is_valid,
    non_empty_string_field,
    public_fallback_reason,
)


def test_api_key_is_valid_matches_and_rejects() -> None:
    assert api_key_is_valid("correct-key", "correct-key") is True
    assert api_key_is_valid("wrong-key", "correct-key") is False
    assert api_key_is_valid(None, "correct-key") is False
    assert api_key_is_valid("", "correct-key") is False


def test_api_key_is_valid_handles_non_ascii_without_raising() -> None:
    # hmac.compare_digest raises TypeError on non-ASCII str input; a malformed
    # header must be rejected (401), not crash the request (500).
    assert api_key_is_valid("café-key", "correct-key") is False
    assert api_key_is_valid("café-key", "café-key") is True


def test_invalid_single_text_never_enters_shared_batch() -> None:
    calls: list[list[str]] = []

    def process(texts: list[str]) -> list[str]:
        calls.append(texts)
        return texts

    batcher = DynamicBatcher(process, max_items=10, wait_ms=0)
    try:
        invalid = non_empty_string_field({"text": 42}, "text")
        valid = non_empty_string_field({"text": "valid contract text"}, "text")
        assert invalid is None
        assert valid is not None
        assert batcher.submit([valid]) == ["valid contract text"]
    finally:
        batcher.close()

    assert calls == [["valid contract text"]]


def test_batch_fields_reject_blank_and_non_string_items() -> None:
    assert all_non_empty_strings(["first", " second "]) is True
    assert all_non_empty_strings(["first", "   "]) is False
    assert all_non_empty_strings(["first", 42]) is False
    assert all_non_empty_strings(["first", None]) is False


def test_text_and_image_inference_share_one_model_owner() -> None:
    state_lock = threading.Lock()
    text_entered = threading.Event()
    active = 0
    max_active = 0

    def enter_inference() -> None:
        nonlocal active, max_active
        with state_lock:
            active += 1
            max_active = max(max_active, active)

    def leave_inference() -> None:
        nonlocal active
        with state_lock:
            active -= 1

    def process_text(texts: list[str]) -> list[str]:
        enter_inference()
        text_entered.set()
        try:
            time.sleep(0.1)
            return texts
        finally:
            leave_inference()

    def process_image(image: str) -> str:
        enter_inference()
        try:
            time.sleep(0.02)
            return image
        finally:
            leave_inference()

    owner = SerializedModelOwner(process_text, process_image, lambda images: images)
    with ThreadPoolExecutor(max_workers=2) as executor:
        text_future = executor.submit(owner.embed_texts, ["serialized text"])
        assert text_entered.wait(timeout=2)
        image_future = executor.submit(owner.embed_image, "encoded-image")
        assert text_future.result(timeout=2) == ["serialized text"]
        assert image_future.result(timeout=2) == "encoded-image"

    assert max_active == 1


def test_public_fallback_reason_hides_raw_backend_exception() -> None:
    raw_reason = "/private/model/path: GPU driver initialization failed"

    assert public_fallback_reason(None) is None
    assert public_fallback_reason(raw_reason) == "accelerator_initialization_failed"
