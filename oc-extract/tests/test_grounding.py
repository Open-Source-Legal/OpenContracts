from __future__ import annotations

from oc_extract.grounding import (
    align_string,
    collect_groundable_strings,
    ground_value,
)

from .conftest import SAMPLE_CONTRACT


def test_exact_alignment():
    span = align_string(SAMPLE_CONTRACT, "ACME Corporation")
    assert span is not None
    assert span.method == "exact"
    assert SAMPLE_CONTRACT[span.start : span.end] == "ACME Corporation"


def test_case_insensitive_alignment():
    span = align_string(SAMPLE_CONTRACT, "acme corporation")
    assert span is not None
    assert span.method == "case_insensitive"
    assert SAMPLE_CONTRACT[span.start : span.end] == "ACME Corporation"


def test_whitespace_normalized_alignment():
    # The document wraps this phrase across a newline.
    span = align_string(SAMPLE_CONTRACT, "continue for a period of three (3) years")
    assert span is not None
    assert span.method in ("normalized", "exact")


def test_fuzzy_alignment():
    span = align_string(
        SAMPLE_CONTRACT, "Widgets Incorporated, a New Jersey corporation"
    )
    assert span is not None
    assert span.method == "fuzzy"
    assert span.score >= 0.75


def test_no_alignment_for_absent_text():
    assert align_string(SAMPLE_CONTRACT, "flux capacitor warranty") is None


def test_collect_groundable_strings_walks_and_caps():
    value = {
        "a": "ACME Corporation",
        "b": ["Yes", "Widgets Incorporated"],  # "Yes" too short
        "c": {"d": "ACME Corporation"},  # duplicate skipped
        "e": 42,
    }
    strings = collect_groundable_strings(value)
    assert strings == ["ACME Corporation", "Widgets Incorporated"]


def test_ground_value_end_to_end():
    spans = ground_value(
        SAMPLE_CONTRACT, {"provider": "ACME Corporation", "fee": "$12,500"}
    )
    methods = {s.method for s in spans}
    assert len(spans) == 2
    assert "exact" in methods
