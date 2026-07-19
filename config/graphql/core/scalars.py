"""Custom scalars matching the graphene schema's wire behaviour.

``GenericScalar`` passes Python values straight through (graphene's
``graphene.types.generic.GenericScalar``); ``JSONString`` serialises via
``json.dumps`` / parses via ``json.loads`` (graphene's ``JSONString``);
``BigInt`` is graphene's arbitrary-precision integer scalar that falls
outside the GraphQL Int 32-bit range.
"""

from __future__ import annotations

import json
from typing import Any, NewType

import strawberry
from graphql import IntValueNode, StringValueNode

_GENERIC_DESCRIPTION = (
    "The `GenericScalar` scalar type represents a generic GraphQL "
    "scalar value that could be: List or Object."
)


def _identity(value: Any) -> Any:
    return value


def _parse_generic_literal(ast: Any, variables: Any = None) -> Any:
    """Literal parsing for GenericScalar, mirroring graphene's implementation."""
    from graphql import (
        BooleanValueNode,
        EnumValueNode,
        FloatValueNode,
        ListValueNode,
        NullValueNode,
        ObjectValueNode,
        VariableNode,
    )

    if isinstance(ast, (StringValueNode, BooleanValueNode)):
        return ast.value
    if isinstance(ast, IntValueNode):
        return int(ast.value)
    if isinstance(ast, FloatValueNode):
        return float(ast.value)
    if isinstance(ast, ListValueNode):
        return [_parse_generic_literal(value, variables) for value in ast.values]
    if isinstance(ast, ObjectValueNode):
        return {
            field.name.value: _parse_generic_literal(field.value, variables)
            for field in ast.fields
        }
    if isinstance(ast, EnumValueNode):
        return ast.value
    if isinstance(ast, VariableNode):
        return (variables or {}).get(ast.name.value)
    if isinstance(ast, NullValueNode):
        return None
    return None


GenericScalar = strawberry.scalar(
    NewType("GenericScalar", object),
    name="GenericScalar",
    description=_GENERIC_DESCRIPTION,
    serialize=_identity,
    parse_value=_identity,
    parse_literal=_parse_generic_literal,
)

_JSON_STRING_DESCRIPTION = (
    "Allows use of a JSON String for input / output from the GraphQL schema.\n"
    "\n"
    "Use of this type is *not recommended* as you lose the benefits of "
    "having a defined, static\n"
    "schema (one of the key benefits of GraphQL)."
)


def _serialize_json_string(value: Any) -> str:
    return json.dumps(value)


def _parse_json_string(value: Any) -> Any:
    return json.loads(value)


def _parse_json_string_literal(ast: Any, variables: Any = None) -> Any:
    if isinstance(ast, StringValueNode):
        return json.loads(ast.value)
    return None


JSONString = strawberry.scalar(
    NewType("JSONString", object),
    name="JSONString",
    description=_JSON_STRING_DESCRIPTION,
    serialize=_serialize_json_string,
    parse_value=_parse_json_string,
    parse_literal=_parse_json_string_literal,
)

_BIG_INT_DESCRIPTION = (
    "The `BigInt` scalar type represents non-fractional whole numeric values.\n"
    "`BigInt` is not constrained to 32-bit like the `Int` type and thus is a less\n"
    "compatible type."
)


def _coerce_big_int(value: Any) -> int:
    num = value
    if isinstance(value, str):
        num = int(float(value)) if "." in value else int(value)
    elif isinstance(value, float):
        num = int(value)
    if not isinstance(num, int) or isinstance(num, bool):
        raise ValueError(f"BigInt cannot represent value: {value!r}")
    return num


def _parse_big_int_literal(ast: Any, variables: Any = None) -> int | None:
    if isinstance(ast, IntValueNode):
        return int(ast.value)
    return None


BigInt = strawberry.scalar(
    NewType("BigInt", int),
    name="BigInt",
    description=_BIG_INT_DESCRIPTION,
    serialize=_coerce_big_int,
    parse_value=_coerce_big_int,
    parse_literal=_parse_big_int_literal,
)
