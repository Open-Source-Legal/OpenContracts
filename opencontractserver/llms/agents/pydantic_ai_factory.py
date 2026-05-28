"""Single construction path for ``pydantic_ai.Agent`` (a.k.a. ``PydanticAIAgent``).

Background — issue #1451 / CLAUDE.md pitfall #14
-------------------------------------------------
``pydantic_ai.Agent`` accepts both ``system_prompt=`` and ``instructions=``,
and on the ``Agent.run()`` path the ``system_prompt`` value is *only*
materialised into the model request when ``message_history`` is ``None``.
OpenContracts' ``chat()`` flow always persists the user's HUMAN message
*before* calling ``run()``, which means ``message_history`` is never empty
in practice — so a ``system_prompt=`` argument is silently dropped and the
LLM runs without any system instruction.

The fix in production code is to pass ``instructions=`` everywhere, but
that lesson is fragile against:

* Future pydantic-ai version bumps changing precedence rules.
* New call sites that copy from external pydantic-ai examples.

This factory is the single chokepoint for ``Agent`` construction in this
codebase. It refuses ``system_prompt=`` outright (raising ``TypeError``)
so the regression cannot reappear silently. Use ``instructions=`` instead.

In addition, the factory unconditionally installs the in-run history
compaction processor (``shrink_old_artifacts_processor``) as a
``ProcessHistory`` capability, so every constructed agent benefits from
the same threshold-gated shrink behaviour. Callers may pass extra
capabilities via ``capabilities=`` or legacy history processors via
``history_processors=`` (each is wrapped in ``ProcessHistory``); both
run after ours so the in-run shrink is applied first.

Tests that need to intercept agent construction should patch
``opencontractserver.llms.agents.pydantic_ai_factory.PydanticAIAgent`` —
the symbol the factory uses to build the agent. See
``opencontractserver/tests/test_pydantic_ai_factory.py`` for the
regression test that pins the precedence behaviour against the currently
pinned pydantic-ai version.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic_ai.agent import Agent as PydanticAIAgent
from pydantic_ai.capabilities import ProcessHistory

from opencontractserver.llms.history_processors import (
    shrink_old_artifacts_processor,
)

logger = logging.getLogger(__name__)

# Sentinel distinct from ``None`` so callers can't pass ``system_prompt=None``
# and bypass the guard — any *presence* of the argument is rejected.
_SYSTEM_PROMPT_FORBIDDEN = object()


def make_pydantic_ai_agent(
    model: Any,
    *,
    system_prompt: Any = _SYSTEM_PROMPT_FORBIDDEN,
    **kwargs: Any,
) -> PydanticAIAgent[Any]:
    """Construct a ``pydantic_ai.Agent`` with the system_prompt foot-gun blocked
    and the in-run history compaction processor installed as a capability.

    ``model`` is required and keyword-only-after-positional, matching every
    existing call site. ``system_prompt`` is forbidden — pass the system
    instruction via ``instructions=`` instead, which is the only form that
    survives the ``message_history``-non-empty path used by OpenContracts'
    chat flow. Other kwargs are forwarded verbatim to ``pydantic_ai.Agent``.

    The in-run compaction processor is wrapped in a ``ProcessHistory``
    capability and prepended to the resulting ``capabilities=`` list, so
    it runs before any caller-supplied processor/capability.

    Caller-supplied ``history_processors=[...]`` (legacy form) and
    ``capabilities=[...]`` (modern form) are both accepted; legacy
    processors are each wrapped in ``ProcessHistory(...)`` and both lists
    run after ours.

    Legacy processor signatures: pydantic-ai's ``ProcessHistory`` accepts
    both ``(messages)`` and ``(ctx: RunContext, messages)`` forms, sync or
    async. Dispatch is decided by inspecting the *type annotation* of the
    first parameter — only an annotation that is (or originates in)
    ``RunContext`` selects the two-argument call path. Untyped parameters
    therefore always fall through to the single-argument path, so an
    untyped two-argument processor (``def fn(ctx, messages):``) will be
    invoked with a single positional argument and raise ``TypeError`` at
    runtime. If a caller wants the ``RunContext`` form they MUST annotate
    the first parameter as ``RunContext`` (or a parameterised
    ``RunContext[...]``).

    Raises:
        TypeError: If ``system_prompt`` is supplied at all (even ``None``).
    """
    if system_prompt is not _SYSTEM_PROMPT_FORBIDDEN:
        raise TypeError(
            "make_pydantic_ai_agent() does not accept system_prompt=. "
            "pydantic-ai silently drops system_prompt when message_history "
            "is non-empty, which is always the case in OpenContracts' "
            "chat() flow because the user message is persisted before "
            "Agent.run() is invoked. Pass instructions= instead. "
            "See issue #1451 and CLAUDE.md pitfall #14."
        )

    legacy_processors = list(kwargs.pop("history_processors", None) or [])
    wrapped_legacy = [ProcessHistory(fn) for fn in legacy_processors]

    caller_capabilities = list(kwargs.pop("capabilities", None) or [])

    kwargs["capabilities"] = [
        ProcessHistory(shrink_old_artifacts_processor),
        *wrapped_legacy,
        *caller_capabilities,
    ]

    # Forward ``model`` as a keyword so call sites and tests that asserted
    # against ``kwargs["model"]`` (the canonical form pydantic-ai documents)
    # keep working.
    return PydanticAIAgent(model=model, **kwargs)
