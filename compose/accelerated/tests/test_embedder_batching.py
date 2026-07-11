from __future__ import annotations

import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "embedder"))

from batching import DynamicBatcher  # noqa: E402


def test_coalesces_concurrent_requests_and_preserves_order() -> None:
    calls: list[list[int]] = []
    calls_lock = threading.Lock()

    def process(items: list[int]) -> list[int]:
        with calls_lock:
            calls.append(items)
        return [item * 10 for item in items]

    batcher = DynamicBatcher(process, max_items=20, wait_ms=50)
    gate = threading.Barrier(3)

    def submit(items: list[int]) -> list[int]:
        gate.wait(timeout=2)
        return batcher.submit(items)

    try:
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                executor.submit(submit, [1, 2]),
                executor.submit(submit, [3]),
                executor.submit(submit, [4, 5, 6]),
            ]
            results = [future.result(timeout=2) for future in futures]
    finally:
        batcher.close()

    assert results == [[10, 20], [30], [40, 50, 60]]
    assert len(calls) == 1
    assert sorted(calls[0]) == [1, 2, 3, 4, 5, 6]


def test_displaced_over_cap_request_keeps_fifo_order() -> None:
    calls: list[list[int]] = []
    first_batch_gate = threading.Event()

    def process(items: list[int]) -> list[int]:
        calls.append(items)
        if len(calls) == 1:
            assert first_batch_gate.wait(timeout=2)
        return items

    def wait_for(condition, timeout: float = 2.0) -> None:
        deadline = time.perf_counter() + timeout
        while not condition():
            assert time.perf_counter() < deadline, "condition never became true"
            time.sleep(0.001)

    batcher = DynamicBatcher(process, max_items=2, wait_ms=500)
    try:
        with ThreadPoolExecutor(max_workers=4) as executor:
            # A fills max_items exactly, so the worker skips the collection
            # window, enters process(), and parks on the gate. Everything
            # submitted while it is parked lands in the queue in a known order.
            blocker = executor.submit(batcher.submit, [0, 1])
            wait_for(lambda: len(calls) == 1)
            leading = executor.submit(batcher.submit, [2])
            wait_for(lambda: batcher.queue_depth == 1)
            # [3, 4] cannot join [2] under max_items=2, so the worker must
            # displace it — and [5], submitted strictly later, must not
            # overtake it.
            displaced = executor.submit(batcher.submit, [3, 4])
            wait_for(lambda: batcher.queue_depth == 2)
            trailing = executor.submit(batcher.submit, [5])
            wait_for(lambda: batcher.queue_depth == 3)
            first_batch_gate.set()

            assert blocker.result(timeout=2) == [0, 1]
            assert leading.result(timeout=2) == [2]
            assert displaced.result(timeout=2) == [3, 4]
            assert trailing.result(timeout=2) == [5]
    finally:
        batcher.close()

    assert calls == [[0, 1], [2], [3, 4], [5]]


def test_does_not_delay_a_request_beyond_collection_window() -> None:
    batcher = DynamicBatcher(lambda items: items, max_items=10, wait_ms=10)
    started = time.perf_counter()
    try:
        assert batcher.submit([1]) == [1]
    finally:
        batcher.close()

    assert time.perf_counter() - started < 0.5


def test_propagates_backend_failure_to_every_coalesced_request() -> None:
    entered = threading.Barrier(2)

    def submit(batcher: DynamicBatcher[int, int], value: int) -> list[int]:
        entered.wait(timeout=2)
        return batcher.submit([value])

    def fail(_items: list[int]) -> list[int]:
        raise RuntimeError("backend failed")

    batcher = DynamicBatcher(fail, max_items=10, wait_ms=50)
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(submit, batcher, 1),
                executor.submit(submit, batcher, 2),
            ]
            for future in futures:
                with pytest.raises(RuntimeError, match="backend failed"):
                    future.result(timeout=2)
    finally:
        batcher.close()


def test_submit_after_close_raises_instead_of_hanging() -> None:
    batcher = DynamicBatcher(lambda items: items, max_items=10, wait_ms=10)
    batcher.close()

    with pytest.raises(RuntimeError, match="submit\\(\\) called after close\\(\\)"):
        batcher.submit([1])


def test_validates_limits() -> None:
    with pytest.raises(ValueError, match="max_items"):
        DynamicBatcher(lambda items: items, max_items=0, wait_ms=1)
    with pytest.raises(ValueError, match="wait_ms"):
        DynamicBatcher(lambda items: items, max_items=1, wait_ms=-1)
    with pytest.raises(ValueError, match="wait_ms"):
        DynamicBatcher(lambda items: items, max_items=1, wait_ms=float("nan"))
    with pytest.raises(ValueError, match="wait_ms"):
        DynamicBatcher(lambda items: items, max_items=1, wait_ms=float("inf"))

    batcher = DynamicBatcher(lambda items: items, max_items=2, wait_ms=0)
    try:
        with pytest.raises(ValueError, match="dynamic batch cap"):
            batcher.submit([1, 2, 3])
    finally:
        batcher.close()
