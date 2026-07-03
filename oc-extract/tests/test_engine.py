"""Engine tests run fully offline via pydantic-ai's FunctionModel."""

from __future__ import annotations

from typing import Any

from oc_extract.constants import (
    NONE_RESULT_AGENT_COMMITTED,
    NONE_RESULT_USAGE_LIMIT,
)
from oc_extract.engine import ExtractionEngine, build_prompt
from oc_extract.schema import FieldSpec
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from .conftest import SAMPLE_CONTRACT

DOCUMENT = {"id": 1, "title": "MSA", "text": SAMPLE_CONTRACT, "page_offsets": None}


def _final_result_args(info: AgentInfo, value: Any) -> dict:
    """Build final_result args matching the output tool's schema shape."""
    schema = info.output_tools[0].parameters_json_schema
    properties = schema.get("properties", {})
    if set(properties) == {"response"}:
        return {"response": value}
    return value


def _scripted_model(
    tool_calls: list[tuple[str, dict]], final_value: Any
) -> FunctionModel:
    """A model that issues ``tool_calls`` one per turn, then commits
    ``final_value`` via the final_result output tool."""
    state = {"turn": 0}

    def fn(messages, info: AgentInfo) -> ModelResponse:
        turn = state["turn"]
        state["turn"] += 1
        if turn < len(tool_calls):
            name, args = tool_calls[turn]
            return ModelResponse(parts=[ToolCallPart(tool_name=name, args=args)])
        out_tool = info.output_tools[0]
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name=out_tool.name,
                    args=_final_result_args(info, final_value),
                )
            ]
        )

    return FunctionModel(fn)


async def test_successful_extraction_with_citations():
    model = _scripted_model([("search_document", {"query": "monthly fee"})], 12500.0)
    engine = ExtractionEngine(model=model)
    field = FieldSpec(
        name="monthly_fee", query="What is the monthly fee?", output_type="float"
    )
    outcome = await engine.extract_cell(DOCUMENT, field)
    assert outcome.status == "completed"
    assert outcome.value == 12500.0
    # The search hit was captured as a retrieval citation.
    retrieval = [s for s in outcome.sources if s["kind"] == "retrieval"]
    assert retrieval
    span_text = SAMPLE_CONTRACT[retrieval[0]["start"] : retrieval[0]["end"]]
    assert "12,500" in span_text
    assert outcome.llm_log  # message history captured


async def test_string_extraction_gets_grounded():
    model = _scripted_model([], "ACME Corporation")
    engine = ExtractionEngine(model=model)
    field = FieldSpec(name="provider", query="Who is the provider?")
    outcome = await engine.extract_cell(DOCUMENT, field)
    assert outcome.status == "completed"
    grounded = [s for s in outcome.sources if s["kind"] == "grounding"]
    assert grounded
    span = grounded[0]
    assert SAMPLE_CONTRACT[span["start"] : span["end"]] == "ACME Corporation"
    assert span["method"] == "exact"


async def test_agent_committed_none_is_completed_null():
    model = _scripted_model([("search_document", {"query": "arbitration"})], None)
    engine = ExtractionEngine(model=model)
    field = FieldSpec(name="arbitration", query="What is the arbitration venue?")
    outcome = await engine.extract_cell(DOCUMENT, field)
    assert outcome.status == "completed"
    assert outcome.value is None
    assert outcome.failure_mode == NONE_RESULT_AGENT_COMMITTED


async def test_usage_limit_exhaustion_is_failed():
    # Model never commits — searches forever.
    def fn(messages, info: AgentInfo) -> ModelResponse:
        return ModelResponse(
            parts=[ToolCallPart(tool_name="search_document", args={"query": "fee"})]
        )

    engine = ExtractionEngine(model=FunctionModel(fn), request_limit=3)
    field = FieldSpec(name="fee", query="What is the fee?", output_type="float")
    outcome = await engine.extract_cell(DOCUMENT, field)
    assert outcome.status == "failed"
    assert outcome.failure_mode == NONE_RESULT_USAGE_LIMIT
    assert "request budget" in (outcome.error or "")


async def test_model_output_type_extraction():
    model = _scripted_model([], {"party_name": "ACME Corporation", "role": "Provider"})
    engine = ExtractionEngine(model=model)
    field = FieldSpec(
        name="party",
        query="Extract the first party.",
        output_type="party_name: str\nrole: str",
    )
    outcome = await engine.extract_cell(DOCUMENT, field)
    assert outcome.status == "completed"
    assert outcome.value == {"party_name": "ACME Corporation", "role": "Provider"}


async def test_list_extraction():
    model = _scripted_model([], ["ACME Corporation", "Widgets Incorporated"])
    engine = ExtractionEngine(model=model)
    field = FieldSpec(name="parties", query="List the parties.", extract_is_list=True)
    outcome = await engine.extract_cell(DOCUMENT, field)
    assert outcome.status == "completed"
    assert outcome.value == ["ACME Corporation", "Widgets Incorporated"]
    # Both list items grounded.
    grounded = [s for s in outcome.sources if s["kind"] == "grounding"]
    assert len(grounded) == 2


def test_prompt_full_text_injection_and_few_shot():
    field = FieldSpec(
        name="date",
        query="What is the effective date?",
        match_text="January 15, 2024 ||| March 1, 2023",
        instructions="Prefer ISO format.",
        must_contain_text="Effective Date",
    )
    prompt = build_prompt(field, SAMPLE_CONTRACT, full_text_limit=100_000)
    assert "example values" in prompt
    assert "March 1, 2023" in prompt
    assert "field instructions" in prompt
    assert "must contain text" in prompt
    assert "MASTER SERVICES AGREEMENT" in prompt  # full text injected

    short_prompt = build_prompt(field, SAMPLE_CONTRACT, full_text_limit=10)
    assert "MASTER SERVICES AGREEMENT" not in short_prompt  # falls back to retrieval
