"""Coverage-focused tests for ``config.graphql.core.scalars``.

These are plain-function unit tests — no GraphQL execution — for the
literal-parsing and value-coercion helpers behind ``GenericScalar``,
``JSONString``, and ``BigInt``. String/Boolean/Object literal parsing for
``GenericScalar`` is already exercised elsewhere (schema-level tests); this
module fills in the branches the strawberry port left uncovered: numeric,
list, enum, variable and null AST literals, the unrecognised-node fallback,
``JSONString``'s value/literal parsing, and every ``BigInt`` coercion path.
"""

from __future__ import annotations

from django.test import SimpleTestCase
from graphql import (
    EnumValueNode,
    FloatValueNode,
    IntValueNode,
    ListValueNode,
    NameNode,
    NullValueNode,
    StringValueNode,
    VariableNode,
)

from config.graphql.core.scalars import (
    _coerce_big_int,
    _parse_big_int_literal,
    _parse_generic_literal,
    _parse_json_string,
    _parse_json_string_literal,
)


class ParseGenericLiteralTests(SimpleTestCase):
    """``_parse_generic_literal`` — graphene's ``GenericScalar`` AST parser."""

    def test_int_value_node_parses_to_a_python_int(self) -> None:
        self.assertEqual(_parse_generic_literal(IntValueNode(value="42")), 42)

    def test_float_value_node_parses_to_a_python_float(self) -> None:
        self.assertEqual(_parse_generic_literal(FloatValueNode(value="3.14")), 3.14)

    def test_list_value_node_parses_each_element_recursively(self) -> None:
        ast = ListValueNode(values=[IntValueNode(value="1"), IntValueNode(value="2")])
        self.assertEqual(_parse_generic_literal(ast), [1, 2])

    def test_enum_value_node_returns_the_raw_enum_name(self) -> None:
        self.assertEqual(
            _parse_generic_literal(EnumValueNode(value="ACTIVE")), "ACTIVE"
        )

    def test_variable_node_resolves_from_the_variables_mapping(self) -> None:
        ast = VariableNode(name=NameNode(value="myVar"))
        self.assertEqual(
            _parse_generic_literal(ast, variables={"myVar": "resolved"}), "resolved"
        )

    def test_variable_node_missing_from_variables_returns_none(self) -> None:
        ast = VariableNode(name=NameNode(value="missingVar"))
        self.assertIsNone(_parse_generic_literal(ast, variables={}))

    def test_null_value_node_returns_none(self) -> None:
        self.assertIsNone(_parse_generic_literal(NullValueNode()))

    def test_unrecognised_ast_node_falls_back_to_none(self) -> None:
        """Every real GraphQL value-node type is already handled; this pins
        the defensive fallback for anything graphql-core might add later
        (or any object reaching the parser that isn't a value node at
        all) so it degrades to ``None`` instead of raising."""
        self.assertIsNone(_parse_generic_literal(object()))


class ParseJsonStringTests(SimpleTestCase):
    """``JSONString`` value/literal parsing (``json.loads`` ports)."""

    def test_parse_value_decodes_a_json_object_payload(self) -> None:
        self.assertEqual(
            _parse_json_string('{"a": 1, "b": [2, 3]}'), {"a": 1, "b": [2, 3]}
        )

    def test_parse_literal_decodes_a_string_value_node(self) -> None:
        ast = StringValueNode(value='{"nested": true}')
        self.assertEqual(_parse_json_string_literal(ast), {"nested": True})

    def test_parse_literal_returns_none_for_a_non_string_ast_node(self) -> None:
        self.assertIsNone(_parse_json_string_literal(IntValueNode(value="1")))


class CoerceBigIntTests(SimpleTestCase):
    """``_coerce_big_int`` — serialize/parse_value for the ``BigInt`` scalar."""

    def test_plain_int_passes_through_unchanged(self) -> None:
        value = 9_007_199_254_740_993  # beyond JS's MAX_SAFE_INTEGER
        self.assertEqual(_coerce_big_int(value), value)

    def test_integer_string_converts_to_int(self) -> None:
        self.assertEqual(_coerce_big_int("123456789012345"), 123456789012345)

    def test_decimal_string_truncates_through_float_to_int(self) -> None:
        self.assertEqual(_coerce_big_int("123.0"), 123)

    def test_float_value_truncates_to_int(self) -> None:
        self.assertEqual(_coerce_big_int(42.9), 42)

    def test_boolean_value_is_rejected(self) -> None:
        """``bool`` is an ``int`` subclass in Python — without the explicit
        ``isinstance(num, bool)`` guard a stray ``True``/``False`` would
        silently coerce to ``1``/``0`` instead of being rejected."""
        with self.assertRaises(ValueError):
            _coerce_big_int(True)

    def test_non_numeric_value_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            _coerce_big_int([1, 2, 3])


class ParseBigIntLiteralTests(SimpleTestCase):
    """``_parse_big_int_literal`` — literal parsing for the ``BigInt`` scalar."""

    def test_int_value_node_parses_to_int(self) -> None:
        self.assertEqual(
            _parse_big_int_literal(IntValueNode(value="9007199254740993")),
            9007199254740993,
        )

    def test_non_int_ast_node_returns_none(self) -> None:
        self.assertIsNone(_parse_big_int_literal(StringValueNode(value="123")))
