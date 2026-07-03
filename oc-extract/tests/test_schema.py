from __future__ import annotations

from typing import get_args, get_origin

import pytest
from oc_extract.schema import (
    FieldSpec,
    parse_output_type,
    resolve_target_type,
)
from pydantic import BaseModel, ValidationError


def test_primitives():
    assert parse_output_type("str") is str
    assert parse_output_type("int") is int
    assert parse_output_type("float") is float
    assert parse_output_type("bool") is bool


def test_model_definition():
    model = parse_output_type("party_name: str\nrole: str\nownership_pct: float")
    assert issubclass(model, BaseModel)
    instance = model(party_name="ACME", role="Provider", ownership_pct=50.0)
    assert instance.party_name == "ACME"
    # All fields required.
    with pytest.raises(ValidationError):
        model(party_name="ACME")


def test_model_definition_with_list_and_noise():
    model = parse_output_type(
        "class Terms(BaseModel):\n  names: list[str]\n  count: int = 3\n\n"
    )
    instance = model(names=["a", "b"], count=2)
    assert instance.names == ["a", "b"]


def test_invalid_output_type():
    with pytest.raises(ValueError):
        parse_output_type("banana")
    with pytest.raises(ValueError):
        parse_output_type("x: banana")


def test_resolve_target_type_list_and_optional():
    spec = FieldSpec(
        name="parties", query="who?", output_type="str", extract_is_list=True
    )
    target = resolve_target_type(spec)
    # Optional[list[str]]
    assert type(None) in get_args(target)
    inner = [a for a in get_args(target) if a is not type(None)][0]
    assert get_origin(inner) is list


def test_field_requires_query_or_match_text():
    with pytest.raises(ValidationError):
        FieldSpec(name="x", output_type="str")
    FieldSpec(name="x", match_text="Effective Date ||| Commencement Date")


def test_field_rejects_bad_output_type_eagerly():
    with pytest.raises(ValidationError):
        FieldSpec(name="x", query="q", output_type="not_a_type")
