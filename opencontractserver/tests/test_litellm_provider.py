"""Tests for LiteLLM provider integration in SimpleLLMClient."""

import sys
import types
from unittest import mock

from django.test import TestCase, override_settings

from opencontractserver.llms.client import (
    ChatMessage,
    ChatResponse,
    Provider,
    SimpleLLMClient,
    create_client,
)


def _install_litellm_stub():
    """Install a fake litellm module so tests run without the real package."""
    fake = types.ModuleType("litellm")
    fake.completion = mock.MagicMock(name="litellm.completion")  # type: ignore[attr-defined]
    sys.modules["litellm"] = fake
    return fake


class TestLiteLLMProviderEnum(TestCase):
    def test_litellm_in_provider_enum(self):
        self.assertEqual(Provider.LITELLM.value, "litellm")

    def test_provider_from_string(self):
        provider = Provider("litellm")
        self.assertEqual(provider, Provider.LITELLM)


class TestLiteLLMClientInit(TestCase):
    def setUp(self):
        self.fake_litellm = _install_litellm_stub()

    def tearDown(self):
        sys.modules.pop("litellm", None)

    def test_init_with_api_key(self):
        client = SimpleLLMClient(
            provider="litellm",
            api_key="sk-test",
            model="anthropic/claude-sonnet-4-6",
        )
        self.assertEqual(client.provider, Provider.LITELLM)
        self.assertEqual(client.model, "anthropic/claude-sonnet-4-6")
        self.assertEqual(client._litellm_api_key, "sk-test")

    @override_settings(LITELLM_API_KEY="sk-from-settings")
    def test_init_uses_settings_api_key(self):
        client = SimpleLLMClient(provider="litellm")
        self.assertEqual(client._litellm_api_key, "sk-from-settings")

    def test_init_without_api_key(self):
        client = SimpleLLMClient(provider="litellm")
        self.assertIsNone(client._litellm_api_key)


class TestLiteLLMChat(TestCase):
    def setUp(self):
        self.fake_litellm = _install_litellm_stub()

    def tearDown(self):
        sys.modules.pop("litellm", None)

    def test_chat_calls_litellm_completion(self):
        mock_usage = mock.MagicMock()
        mock_usage.prompt_tokens = 10
        mock_usage.completion_tokens = 5
        mock_usage.total_tokens = 15

        mock_response = mock.MagicMock()
        mock_response.choices = [mock.MagicMock(message=mock.MagicMock(content="4"))]
        mock_response.model = "anthropic/claude-sonnet-4-6"
        mock_response.usage = mock_usage
        self.fake_litellm.completion.return_value = mock_response

        client = SimpleLLMClient(
            provider="litellm",
            api_key="sk-test",
            model="anthropic/claude-sonnet-4-6",
        )
        messages = [ChatMessage(role="user", content="What is 2+2?")]
        response = client.chat(messages)

        self.assertIsInstance(response, ChatResponse)
        self.assertEqual(response.content, "4")
        self.assertEqual(response.model, "anthropic/claude-sonnet-4-6")
        assert response.usage is not None
        self.assertEqual(response.usage["total_tokens"], 15)

        call_kwargs = self.fake_litellm.completion.call_args[1]
        self.assertEqual(call_kwargs["model"], "anthropic/claude-sonnet-4-6")
        self.assertTrue(call_kwargs["drop_params"])
        self.assertEqual(call_kwargs["api_key"], "sk-test")

    def test_chat_omits_api_key_when_none(self):
        mock_response = mock.MagicMock()
        mock_response.choices = [mock.MagicMock(message=mock.MagicMock(content="ok"))]
        mock_response.model = "gpt-4o-mini"
        mock_response.usage = None
        self.fake_litellm.completion.return_value = mock_response

        client = SimpleLLMClient(provider="litellm")
        messages = [ChatMessage(role="user", content="test")]
        client.chat(messages)

        call_kwargs = self.fake_litellm.completion.call_args[1]
        self.assertNotIn("api_key", call_kwargs)


class TestLiteLLMFactory(TestCase):
    def setUp(self):
        self.fake_litellm = _install_litellm_stub()

    def tearDown(self):
        sys.modules.pop("litellm", None)

    @override_settings(LLM_CLIENT_PROVIDER="litellm")
    def test_create_client_with_litellm_setting(self):
        client = create_client()
        self.assertEqual(client.provider, Provider.LITELLM)
