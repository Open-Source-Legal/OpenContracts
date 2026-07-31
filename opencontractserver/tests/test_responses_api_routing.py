"""GPT-5.6 models must be driven through the Responses API.

OpenAI answers a tool-carrying ``/v1/chat/completions`` request for this family
with a 400: *"Function tools with reasoning_effort are not supported for
gpt-5.6-luna in /v1/chat/completions. To use function tools, use /v1/responses
or set reasoning_effort to 'none'."* Every OpenContracts agent carries function
tools, and turning reasoning off to keep the old endpoint would discard the
capability these models are picked for — so the endpoint moves.

Routed automatically because the names are selectable in the System Settings
LLM picker: without it, choosing one would 400 every agent in the install with
an explanation visible only in a worker log.
"""

from __future__ import annotations

from django.test import TestCase

from opencontractserver.llms.model_factory import (
    build_agent_model,
    requires_responses_api,
)


class ResponsesApiRoutingTests(TestCase):
    def test_the_gpt_56_family_requires_the_responses_api(self):
        for name in ("gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol"):
            self.assertTrue(requires_responses_api("openai", name), name)

    def test_earlier_openai_models_are_left_on_chat_completions(self):
        for name in ("gpt-4.1", "gpt-4o", "o3-mini"):
            self.assertFalse(requires_responses_api("openai", name), name)

    def test_another_provider_is_never_redirected(self):
        # The constraint is OpenAI's endpoint split, not a property of the
        # model name, so a same-named model elsewhere must not be rewritten.
        self.assertFalse(requires_responses_api("anthropic", "gpt-5.6-luna"))

    def test_the_spec_string_is_rewritten_on_the_env_credential_path(self):
        # With no DB credentials the factory hands the spec back for
        # pydantic-ai to resolve, so the redirect has to live in the string —
        # covering this path is the difference between a working picker and a
        # 400 on every agent call.
        self.assertEqual(
            build_agent_model("openai:gpt-5.6-luna"),
            "openai-responses:gpt-5.6-luna",
        )

    def test_an_unaffected_spec_is_returned_untouched(self):
        self.assertEqual(build_agent_model("openai:gpt-4.1"), "openai:gpt-4.1")

    def test_pydantic_ai_resolves_the_rewritten_spec_to_a_responses_model(self):
        # Pins the contract with the framework: if the prefix is ever renamed,
        # the rewrite would silently produce an unresolvable spec.
        from pydantic_ai.models import infer_model

        model = infer_model(build_agent_model("openai:gpt-5.6-luna"))
        self.assertEqual(type(model).__name__, "OpenAIResponsesModel")
        self.assertEqual(model.model_name, "gpt-5.6-luna")
