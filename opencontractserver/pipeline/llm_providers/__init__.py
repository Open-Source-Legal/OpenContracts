"""Concrete LLM provider pipeline components.

Each module declares a ``BaseLLMProvider`` subclass describing one
``pydantic-ai``-supported provider (OpenAI, Anthropic, Google, Ollama,
…). The :class:`PipelineComponentRegistry` walks this package on first
access and registers every concrete subclass — adding a new provider
is a matter of dropping a new module in this directory.
"""
