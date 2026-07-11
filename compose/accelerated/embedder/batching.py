"""Small request coalescer for accelerator-backed embedding inference."""

from __future__ import annotations

import math
import queue
import threading
import time
from concurrent.futures import Future
from dataclasses import dataclass
from typing import Callable, Generic, TypeVar

InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")


@dataclass
class _Request(Generic[InputT, OutputT]):
    items: list[InputT]
    result: Future[list[OutputT]]


class DynamicBatcher(Generic[InputT, OutputT]):
    """Combine simultaneous HTTP requests into fuller accelerator batches.

    A single worker owns the model, so inference remains serialized and safe.
    Request threads wait on futures while the worker briefly collects peers and
    performs one larger model call. Results are sliced back in request order.
    """

    def __init__(
        self,
        process: Callable[[list[InputT]], list[OutputT]],
        *,
        max_items: int,
        wait_ms: float,
    ) -> None:
        if max_items < 1:
            raise ValueError("max_items must be at least 1")
        if not math.isfinite(wait_ms) or wait_ms < 0:
            raise ValueError("wait_ms must be a finite, non-negative number")

        self._process = process
        self._max_items = max_items
        self._wait_seconds = wait_ms / 1000
        self._queue: queue.Queue[_Request[InputT, OutputT] | None] = queue.Queue()
        # Worker-thread-only slot for a request that arrived during collection
        # but did not fit under ``max_items``. Holding it here (instead of
        # re-queueing at the back) preserves FIFO order for the next batch.
        self._pending: _Request[InputT, OutputT] | None = None
        self._closed = False
        self._close_lock = threading.Lock()
        self._thread = threading.Thread(
            target=self._run,
            name="embedding-dynamic-batcher",
            daemon=True,
        )
        self._thread.start()

    @property
    def queue_depth(self) -> int:
        return self._queue.qsize()

    def submit(self, items: list[InputT]) -> list[OutputT]:
        if not items:
            return []
        if len(items) > self._max_items:
            raise ValueError(
                f"Request has {len(items)} items; dynamic batch cap is "
                f"{self._max_items}"
            )

        future: Future[list[OutputT]] = Future()
        # Guarded by ``_close_lock`` so a request can never be queued after
        # ``close()`` has already put its sentinel -- without this a caller
        # racing close() would block on ``future.result()`` forever, since
        # nothing would ever service a request enqueued after the worker
        # thread has exited.
        with self._close_lock:
            if self._closed:
                raise RuntimeError(
                    "submit() called after close(); DynamicBatcher no longer "
                    "accepts requests"
                )
            self._queue.put(_Request(items=list(items), result=future))
        return future.result()

    def close(self) -> None:
        with self._close_lock:
            self._closed = True
            self._queue.put(None)
        self._thread.join(timeout=5)

    def _collect(self) -> list[_Request[InputT, OutputT]] | None:
        if self._pending is not None:
            first: _Request[InputT, OutputT] | None = self._pending
            self._pending = None
        else:
            first = self._queue.get()
        if first is None:
            return None

        requests = [first]
        item_count = len(first.items)
        deadline = time.monotonic() + self._wait_seconds

        while item_count < self._max_items:
            timeout = deadline - time.monotonic()
            if timeout <= 0:
                break
            try:
                candidate = self._queue.get(timeout=timeout)
            except queue.Empty:
                break

            if candidate is None:
                self._queue.put(None)
                break
            if item_count + len(candidate.items) > self._max_items:
                self._pending = candidate
                break
            requests.append(candidate)
            item_count += len(candidate.items)

        return requests

    def _run(self) -> None:
        while True:
            requests = self._collect()
            if requests is None:
                return

            try:
                combined = [item for request in requests for item in request.items]
                outputs = self._process(combined)
                if len(outputs) != len(combined):
                    raise RuntimeError(
                        "Embedding backend returned "
                        f"{len(outputs)} results for {len(combined)} inputs"
                    )

                offset = 0
                for request in requests:
                    end = offset + len(request.items)
                    request.result.set_result(outputs[offset:end])
                    offset = end
            except BaseException as exc:
                for request in requests:
                    request.result.set_exception(exc)
