"""Base class for LLM provider pipeline components.

LLM providers describe a model family supported by ``pydantic-ai`` —
OpenAI, Anthropic, Google, Ollama, and so on — together with the
suggested models that ship with the provider's SDK. Concrete providers
carry no behaviour of their own: actual client instantiation happens
inside ``pydantic-ai`` when an ``Agent(model="provider:model")`` is
built. The classes exist so the rest of the system has something to
enumerate (UI dropdowns, validation, future credential routing).

Discovery follows the same pattern as :class:`BaseEmbedder` and the
other ``BaseXxx`` pipeline components — the
:class:`PipelineComponentRegistry` walks the
``opencontractserver.pipeline.llm_providers`` package on first access
and registers every concrete subclass.
"""

from __future__ import annotations

from abc import ABC
from typing import ClassVar

from opencontractserver.pipeline.base.base_component import PipelineComponentBase


class BaseLLMProvider(PipelineComponentBase, ABC):
    """Abstract base class for LLM provider pipeline components.

    Subclasses declare:

    * ``provider_key`` — pydantic-ai's provider prefix (e.g. ``"openai"``,
      ``"anthropic"``, ``"google-gla"``, ``"ollama"``). Used to build
      the full ``"{provider_key}:{model_name}"`` spec accepted by
      ``pydantic_ai.Agent(model=...)`` and to key future credential
      lookups.
    * ``supported_models`` — suggested bare model names exposed to the
      UI (e.g. ``("claude-opus-4-6", "claude-haiku-4-5")``). Not
      strictly enforced at runtime so newer models can be used without
      a code change.
    * ``requires_api_key`` — whether the provider needs a credential.
      Most do; ``ollama`` (local) does not.

    The class is intentionally abstract — we never instantiate concrete
    providers, we only read their class attributes through the
    registry.
    """

    # Identity used to build pydantic-ai model strings and to key
    # credential lookups. Override in every concrete subclass.
    provider_key: ClassVar[str] = ""

    # Suggested model names exposed to the UI. Not strictly enforced at
    # runtime so users can pass newer models without waiting on a code
    # change.
    supported_models: ClassVar[tuple[str, ...]] = ()

    # Whether the provider needs an API credential (Ollama does not).
    requires_api_key: ClassVar[bool] = True
