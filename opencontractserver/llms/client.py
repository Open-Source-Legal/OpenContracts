"""
Lightweight LLM client abstraction for simple chat completions.

This module provides a minimal abstraction over LLM providers (currently OpenAI)
for basic chat completion tasks without the overhead of full agent frameworks.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional, Union

from django.conf import settings

logger = logging.getLogger(__name__)


class Provider(Enum):
    """Supported LLM providers."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"  # Future support
    GOOGLE = "google"  # Future support


@dataclass
class ChatMessage:
    """Simple chat message representation."""

    role: str  # "system", "user", "assistant"
    content: str


@dataclass
class ChatResponse:
    """Response from a chat completion."""

    content: str
    model: str
    usage: Optional[dict[str, int]] = None
    raw_response: Optional[Any] = None


class SimpleLLMClient:
    """
    Lightweight LLM client for basic chat completions.

    This class provides a simple interface for chat completions without
    the overhead of full agent frameworks like llama_index.
    """

    def __init__(
        self,
        provider: Union[Provider, str] = Provider.OPENAI,
        api_key: Optional[str] = None,
        model: str = "gpt-4o-mini",
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ):
        """
        Initialize the LLM client.

        Args:
            provider: LLM provider to use
            api_key: API key for the provider (uses settings if not provided)
            model: Model name to use
            temperature: Temperature for response generation
            max_tokens: Maximum tokens in response
        """
        if isinstance(provider, str):
            provider = Provider(provider)

        self.provider = provider
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

        # Initialize provider-specific client
        if provider == Provider.OPENAI:
            self._init_openai(api_key)
        else:
            raise ValueError(f"Provider {provider} not yet supported")

    def _init_openai(self, api_key: Optional[str] = None) -> None:
        """Initialize OpenAI client."""
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("OpenAI library not installed. Run: pip install openai")

        api_key = api_key or getattr(settings, "OPENAI_API_KEY", None)
        if not api_key:
            raise ValueError("OpenAI API key not found in settings")

        self.client = OpenAI(api_key=api_key)

    def chat(
        self,
        messages: list[ChatMessage],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> ChatResponse:
        """
        Send a chat completion request.

        Args:
            messages: List of chat messages
            model: Override default model
            temperature: Override default temperature
            max_tokens: Override default max_tokens

        Returns:
            ChatResponse with the completion result

        Example:
            client = SimpleLLMClient()
            messages = [
                ChatMessage(role="system", content="You are helpful"),
                ChatMessage(role="user", content="Hello!")
            ]
            response = client.chat(messages)
            print(response.content)
        """
        model = model or self.model
        temperature = temperature if temperature is not None else self.temperature
        max_tokens = max_tokens or self.max_tokens

        if self.provider == Provider.OPENAI:
            return self._chat_openai(messages, model, temperature, max_tokens)
        else:
            raise ValueError(f"Provider {self.provider} not yet supported")

    def _chat_openai(
        self,
        messages: list[ChatMessage],
        model: str,
        temperature: float,
        max_tokens: Optional[int],
    ) -> ChatResponse:
        """Execute OpenAI chat completion."""
        try:
            # Convert our messages to OpenAI format
            openai_messages = [
                {"role": msg.role, "content": msg.content} for msg in messages
            ]

            # Build request parameters
            params = {
                "model": model,
                "messages": openai_messages,
                "temperature": temperature,
            }
            if max_tokens:
                params["max_tokens"] = max_tokens

            # Make the API call
            response = self.client.chat.completions.create(**params)

            # Extract the response
            message = response.choices[0].message
            usage = (
                {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                }
                if response.usage
                else None
            )

            return ChatResponse(
                content=message.content,
                model=response.model,
                usage=usage,
                raw_response=response,
            )

        except Exception as e:
            logger.error(f"OpenAI chat completion failed: {e}")
            raise

    async def achat(
        self,
        messages: list[ChatMessage],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> ChatResponse:
        """
        Async version of chat (currently wraps sync version).

        Future versions will use native async clients.
        """
        # NOTE(deferred): Replace with native async OpenAI/Anthropic clients
        # once provider-specific async support is stabilized. The executor
        # approach works but adds one thread per call.
        import asyncio

        return await asyncio.get_event_loop().run_in_executor(
            None, self.chat, messages, model, temperature, max_tokens
        )


def create_client(
    provider: Optional[Union[Provider, str]] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    **kwargs,
) -> SimpleLLMClient:
    """
    Factory function to create an LLM client.

    Args:
        provider: LLM provider to use (defaults to settings.LLM_CLIENT_PROVIDER)
        model: Model to use (defaults to settings.LLM_CLIENT_MODEL)
        temperature: Temperature setting (defaults to settings.LLM_CLIENT_TEMPERATURE)
        max_tokens: Max tokens setting (defaults to settings.LLM_CLIENT_MAX_TOKENS)
        **kwargs: Additional arguments passed to SimpleLLMClient

    Returns:
        Configured SimpleLLMClient instance

    Example:
        client = create_client()  # Uses settings defaults
        response = client.chat([
            ChatMessage(role="user", content="Hello!")
        ])
    """
    # Import here to avoid circular dependency
    from django.conf import settings

    # Use settings defaults if not provided
    if provider is None:
        provider = getattr(settings, "LLM_CLIENT_PROVIDER", "openai")
    if model is None:
        model = getattr(settings, "LLM_CLIENT_MODEL", "gpt-4o-mini")
    if temperature is None:
        temperature = getattr(settings, "LLM_CLIENT_TEMPERATURE", 0.7)
    if max_tokens is None:
        max_tokens = getattr(settings, "LLM_CLIENT_MAX_TOKENS", None)

    return SimpleLLMClient(
        provider=provider,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        **kwargs,
    )
