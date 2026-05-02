"""LLM/agent helper utilities."""

from typing import Optional


def is_anthropic_model(model_name: Optional[str]) -> bool:
    """Return True if ``model_name`` looks like an Anthropic / Claude model.

    Accepts pydantic-ai-style ``"anthropic:..."`` prefixes and bare model
    names containing ``"claude"``. Used to decide whether to apply the
    Anthropic temperature guard in structured extraction (issue #1381).
    """
    if not model_name:
        return False
    name = model_name.lower()
    return name.startswith("anthropic:") or "claude" in name
