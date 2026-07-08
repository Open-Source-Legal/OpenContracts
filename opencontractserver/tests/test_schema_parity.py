"""Schema-shape parity: strawberry schema vs the graphene golden SDL.

``config/graphql/schema.graphql`` is the SDL captured from the graphene
schema at migration time (the wire contract every frontend document was
written against). This test structurally compares the served strawberry
schema against it: every named type (kind, fields, argument names/types/
printed defaults, interfaces, enum members) must match exactly — field
*ordering* and descriptions are not part of the contract.

If you intentionally change the API surface, regenerate the golden file:

    python manage.py shell -c "from config.graphql.schema import schema; \
        from graphql import print_schema; \
        open('config/graphql/schema.graphql','w').write(print_schema(schema._schema))"
"""

from pathlib import Path
from typing import cast

from django.test import SimpleTestCase
from graphql import (
    GraphQLEnumType,
    GraphQLInputObjectType,
    GraphQLInterfaceType,
    GraphQLObjectType,
    GraphQLScalarType,
    GraphQLUnionType,
    Undefined,
    build_schema,
    print_ast,
)
from graphql.utilities import ast_from_value

GOLDEN_PATH = Path(__file__).resolve().parents[2] / "config/graphql/schema.graphql"


def _kind(t) -> str:
    for klass, label in (
        (GraphQLObjectType, "object"),
        (GraphQLInterfaceType, "interface"),
        (GraphQLEnumType, "enum"),
        (GraphQLInputObjectType, "input"),
        (GraphQLScalarType, "scalar"),
        (GraphQLUnionType, "union"),
    ):
        if isinstance(t, klass):
            return label
    return "?"


def _printed_default(arg) -> str | None:
    if arg.default_value is Undefined:
        return None
    node = ast_from_value(arg.default_value, arg.type)
    return print_ast(node) if node else repr(arg.default_value)


class SchemaParityTestCase(SimpleTestCase):
    """The served schema must be shape-identical to the golden SDL."""

    maxDiff = None

    def test_schema_matches_golden_sdl(self) -> None:
        golden = build_schema(GOLDEN_PATH.read_text())

        from config.graphql.schema import schema

        served = schema._schema

        problems: list[str] = []

        gnames = {n for n in golden.type_map if not n.startswith("__")}
        snames = {n for n in served.type_map if not n.startswith("__")}
        for n in sorted(gnames - snames):
            problems.append(f"missing type: {n}")
        for n in sorted(snames - gnames):
            problems.append(f"extra type: {n}")

        for n in sorted(gnames & snames):
            gt, st = golden.type_map[n], served.type_map[n]
            if _kind(gt) != _kind(st):
                problems.append(f"kind mismatch {n}: {_kind(gt)} vs {_kind(st)}")
                continue

            # ``_kind(gt) == _kind(st)`` above guarantees the parallel ``st``
            # is the same GraphQL kind as ``gt``; cast so mypy sees the
            # kind-specific attributes (``values`` / ``fields`` / ``interfaces``)
            # it can only narrow on ``gt`` via ``isinstance``.
            if isinstance(gt, GraphQLEnumType):
                st_enum = cast(GraphQLEnumType, st)
                if set(gt.values) != set(st_enum.values):
                    problems.append(
                        f"enum {n}: members differ "
                        f"{sorted(set(gt.values) ^ set(st_enum.values))}"
                    )
                continue

            if isinstance(
                gt, (GraphQLObjectType, GraphQLInterfaceType, GraphQLInputObjectType)
            ):
                st_fielded = cast(
                    "GraphQLObjectType | GraphQLInterfaceType | GraphQLInputObjectType",
                    st,
                )
                gf, sf = gt.fields, st_fielded.fields
                for fn in sorted(set(gf) - set(sf)):
                    problems.append(f"{n}: missing field {fn}")
                for fn in sorted(set(sf) - set(gf)):
                    problems.append(f"{n}: extra field {fn}")
                for fn in sorted(set(gf) & set(sf)):
                    g, s = gf[fn], sf[fn]
                    if str(g.type) != str(s.type):
                        problems.append(f"{n}.{fn}: type {g.type} vs {s.type}")
                    ga = getattr(g, "args", {}) or {}
                    sa = getattr(s, "args", {}) or {}
                    for an in sorted(set(ga) - set(sa)):
                        problems.append(f"{n}.{fn}: missing arg {an}")
                    for an in sorted(set(sa) - set(ga)):
                        problems.append(f"{n}.{fn}: extra arg {an}")
                    for an in sorted(set(ga) & set(sa)):
                        if str(ga[an].type) != str(sa[an].type):
                            problems.append(
                                f"{n}.{fn}({an}): {ga[an].type} vs {sa[an].type}"
                            )
                        if _printed_default(ga[an]) != _printed_default(sa[an]):
                            problems.append(
                                f"{n}.{fn}({an}) default: "
                                f"{_printed_default(ga[an])!r} vs {_printed_default(sa[an])!r}"
                            )

                if isinstance(gt, GraphQLObjectType):
                    gi = {i.name for i in gt.interfaces}
                    si = {i.name for i in cast(GraphQLObjectType, st).interfaces}
                    if gi != si:
                        problems.append(f"{n}: interfaces {gi} vs {si}")

        self.assertEqual(
            problems, [], "\n".join(["schema diverges from golden SDL:"] + problems)
        )
