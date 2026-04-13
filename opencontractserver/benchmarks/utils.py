"""Shared utilities for the benchmark harness."""

from __future__ import annotations

from contextlib import contextmanager


@contextmanager
def null_context():
    """No-op context manager used when eager-mode wrapping is not needed."""
    yield
