"""Field-set schema: field specs and output-type parsing.

A :class:`FieldSpec` is the standalone analogue of an OpenContracts
``Column`` (query + output type + guidance); a :class:`FieldSet` is the
analogue of a ``Fieldset``. ``parse_output_type`` ports
``opencontractserver/utils/etl.py::parse_model_or_primitive``: an
``output_type`` string is either a primitive name (``"str"``, ``"int"``,
``"float"``, ``"bool"``) or a newline-separated ``name: type`` model
definition that is compiled into a dynamic Pydantic model.
"""

from __future__ import annotations

import uuid
from typing import Union, get_origin

from pydantic import BaseModel, Field, create_model, model_validator

PRIMITIVES: dict[str, type] = {
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
}


class FieldSpec(BaseModel):
    """One extractable field (OpenContracts ``Column`` analogue)."""

    name: str = Field(min_length=1)
    #: Natural-language question to answer from the document.
    query: str | None = None
    #: Alternate prompt seed; ``|||``-separated values become few-shot examples.
    match_text: str | None = None
    #: Advisory + retrieval filter: only sections containing this text.
    must_contain_text: str | None = None
    #: Extra guidance folded into the prompt (fenced — treated as data).
    instructions: str | None = None
    #: ``"str"`` / ``"int"`` / ``"float"`` / ``"bool"`` or ``name: type`` lines.
    output_type: str = "str"
    #: Wrap the output type in ``list[...]``.
    extract_is_list: bool = False

    @model_validator(mode="after")
    def _require_prompt(self) -> FieldSpec:
        if not (self.query or self.match_text):
            raise ValueError("field requires query or match_text")
        # Fail fast on an unparseable output_type at definition time rather
        # than at extraction time.
        parse_output_type(self.output_type)
        return self


class FieldSet(BaseModel):
    """A named collection of fields (OpenContracts ``Fieldset`` analogue)."""

    name: str = Field(min_length=1)
    description: str = ""
    fields: list[FieldSpec] = Field(min_length=1)


def parse_output_type(value: str) -> type:
    """Parse an ``output_type`` string into a Python type.

    Primitive names map to builtins. A string containing ``:`` is treated as
    a model definition — one ``field_name: type`` per line — and compiled to
    a dynamic Pydantic model (all fields required, types restricted to the
    primitives table).
    """
    value = value.strip()
    if value in PRIMITIVES:
        return PRIMITIVES[value]

    if ":" in value:
        props: dict = {}
        for line in value.split("\n"):
            line = line.strip()
            if not line:
                continue
            # Skip class headers / decorators pasted in from real code.
            if line.startswith("class") or "(" in line or ")" in line:
                continue
            if line.startswith("#"):
                continue
            # Drop inline defaults — dynamic fields are always required.
            if "=" in line:
                line = line.split("=", 1)[0].strip()
            if ":" not in line:
                raise ValueError(f"invalid model field line: {line!r}")
            field_name, type_name = (part.strip() for part in line.split(":", 1))
            if not field_name.isidentifier():
                raise ValueError(f"invalid field name: {field_name!r}")
            is_list = False
            if type_name.startswith("list[") and type_name.endswith("]"):
                is_list = True
                type_name = type_name[5:-1].strip()
            if type_name not in PRIMITIVES:
                raise ValueError(
                    f"unsupported type {type_name!r} for field {field_name!r}; "
                    f"allowed: {sorted(PRIMITIVES)} (optionally list-wrapped)"
                )
            annotation: type = PRIMITIVES[type_name]
            if is_list:
                annotation = list[annotation]  # type: ignore[valid-type]
            props[field_name] = (annotation, ...)
        if not props:
            raise ValueError(f"no fields found in model definition: {value!r}")
        return create_model(f"DynamicModel_{uuid.uuid4().hex[:8]}", **props)

    raise ValueError(
        f"output_type {value!r} is neither a primitive ({sorted(PRIMITIVES)}) "
        "nor a 'name: type' model definition"
    )


def resolve_target_type(field: FieldSpec) -> type:
    """Resolve a field's full extraction target type.

    Applies ``extract_is_list`` wrapping, then wraps in ``Optional`` so the
    agent can legitimately commit to "the value is absent" (the
    ``agent_committed_none`` outcome) instead of being forced to invent one.
    """
    target: type = parse_output_type(field.output_type)
    if field.extract_is_list and get_origin(target) is not list:
        target = list[target]  # type: ignore[valid-type]
    return Union[target, None]  # type: ignore[return-value]
