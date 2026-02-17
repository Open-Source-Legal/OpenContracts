"""Pydantic AI-specific tool implementations following latest syntax patterns."""

import inspect
import logging
from collections.abc import Awaitable
from typing import Any, Callable, Optional, get_type_hints

from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai.tools import RunContext

from opencontractserver.llms.exceptions import ToolConfirmationRequired
from opencontractserver.llms.tools.tool_factory import CoreTool
from opencontractserver.llms.vector_stores.core_vector_stores import (
    CoreAnnotationVectorStore,
)

logger = logging.getLogger(__name__)


async def _check_user_permissions(
    ctx: "RunContext[PydanticAIDependencies]",
) -> None:
    """
    Validate that the user in context has permission to access the resources.

    This is a defense-in-depth check that runs BEFORE any tool execution to
    ensure an agent cannot escalate beyond the calling user's permissions.
    Even if the consumer layer has a bug, tools won't leak data.

    Performance Note:
        This function intentionally does NOT cache permission results. Each tool
        call triggers fresh DB queries to ensure we catch permission revocations
        that occur mid-session (e.g., admin removes user's access while they're
        chatting). The security benefit of detecting revoked permissions in
        real-time outweighs the ~2-4 DB queries per tool call overhead.

        Tests verify this behavior:
        - test_pe4_4_permission_revoked_mid_session_blocks_next_call
        - test_pe4_5_document_made_private_mid_session

    Args:
        ctx: The RunContext containing PydanticAIDependencies with user/resource IDs

    Raises:
        PermissionError: If user lacks READ permission on document or corpus
    """
    from asgiref.sync import sync_to_async

    deps = ctx.deps
    if deps is None:
        return  # No context = no check (shouldn't happen in practice)

    user_id = deps.user_id
    document_id = deps.document_id
    corpus_id = deps.corpus_id

    # Import here to avoid circular imports and keep this check optional
    from django.contrib.auth import get_user_model

    from opencontractserver.corpuses.models import Corpus
    from opencontractserver.documents.models import Document

    User = get_user_model()

    if user_id is None:
        # Anonymous user - only allow if resources are public
        # (Should already be validated at consumer layer, but double-check)
        if document_id:
            try:
                doc = await Document.objects.aget(pk=document_id)
                if not doc.is_public:
                    logger.warning(
                        f"Anonymous tool access denied to private document {document_id}"
                    )
                    raise PermissionError("Anonymous access denied to private document")
            except Document.DoesNotExist:
                raise PermissionError(f"Document {document_id} not found")

        if corpus_id:
            try:
                corpus = await Corpus.objects.aget(pk=corpus_id)
                if not corpus.is_public:
                    logger.warning(
                        f"Anonymous tool access denied to private corpus {corpus_id}"
                    )
                    raise PermissionError("Anonymous access denied to private corpus")
            except Corpus.DoesNotExist:
                raise PermissionError(f"Corpus {corpus_id} not found")
        return

    # Authenticated user - check actual permissions
    try:
        user = await User.objects.aget(pk=user_id)
    except User.DoesNotExist:
        raise PermissionError(f"User {user_id} not found")

    if document_id:
        # Use visible_to_user() queryset which properly handles creator access,
        # public status, and guardian permissions — unlike user_has_permission_for_obj
        # which misses creator-based access (see its docstring warning).
        # Use Django's native aexists() to avoid thread-hopping via
        # database_sync_to_async, which breaks under TestCase transaction isolation.
        has_perm = await sync_to_async(
            lambda: Document.objects.visible_to_user(user)
            .filter(pk=document_id)
            .exists()
        )()
        if not has_perm:
            logger.warning(
                f"User {user_id} tool access denied - lacks READ on document {document_id}"
            )
            raise PermissionError(
                f"User {user_id} lacks READ permission on document {document_id}"
            )

    if corpus_id:
        has_perm = await sync_to_async(
            lambda: Corpus.objects.visible_to_user(user).filter(pk=corpus_id).exists()
        )()
        if not has_perm:
            logger.warning(
                f"User {user_id} tool access denied - lacks READ on corpus {corpus_id}"
            )
            raise PermissionError(
                f"User {user_id} lacks READ permission on corpus {corpus_id}"
            )


def _validate_resource_id_params(
    ctx: "RunContext[PydanticAIDependencies]",
    **kwargs,
) -> None:
    """
    Validate that any document_id or corpus_id parameters match the context.

    This is a defense-in-depth check that prevents tools from being called
    with different resource IDs than what the agent has permission for.
    The LLM could potentially be prompted to access a different document
    via prompt injection; this check prevents such escalation.

    Args:
        ctx: The RunContext containing PydanticAIDependencies
        **kwargs: Tool keyword arguments to validate

    Raises:
        PermissionError: If document_id or corpus_id params don't match context
    """
    deps = ctx.deps
    if deps is None:
        return

    # Check document_id parameter
    param_doc_id = kwargs.get("document_id")
    if param_doc_id is not None and deps.document_id is not None:
        if int(param_doc_id) != int(deps.document_id):
            logger.warning(
                f"Tool called with document_id={param_doc_id} but context has "
                f"document_id={deps.document_id} - potential permission bypass attempt"
            )
            raise PermissionError(
                f"document_id parameter ({param_doc_id}) does not match "
                f"context document ({deps.document_id})"
            )

    # Check corpus_id parameter
    param_corpus_id = kwargs.get("corpus_id")
    if param_corpus_id is not None and deps.corpus_id is not None:
        if int(param_corpus_id) != int(deps.corpus_id):
            logger.warning(
                f"Tool called with corpus_id={param_corpus_id} but context has "
                f"corpus_id={deps.corpus_id} - potential permission bypass attempt"
            )
            raise PermissionError(
                f"corpus_id parameter ({param_corpus_id}) does not match "
                f"context corpus ({deps.corpus_id})"
            )


class PydanticAIToolMetadata(BaseModel):
    """Pydantic model for tool metadata."""

    name: str = Field(..., description="The name of the tool")
    description: str = Field(..., description="Description of what the tool does")
    parameters: dict[str, Any] = Field(
        default_factory=dict, description="Tool parameter schema"
    )


class PydanticAIDependencies(BaseModel):
    """
    Default dependencies for PydanticAI tools and agents.
    This class is used as the `deps_type` for PydanticAI Agents
    and for typing the `RunContext` in tools.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    user_id: Optional[int] = Field(default=None, description="Current user ID")
    document_id: Optional[int] = Field(default=None, description="Current document ID")
    corpus_id: Optional[int] = Field(default=None, description="Current corpus ID")
    vector_store: CoreAnnotationVectorStore = Field(
        default=None, description="Vector store instance"
    )

    # Optional hook so tools can surface nested stream events to the
    # application layer (e.g. WebSocket) while a call is running.
    stream_observer: Optional[Callable[[Any], Awaitable[None]]] = Field(
        default=None,
        description="Side-channel callback that receives UnifiedStreamEvent objects",
    )

    # Flag to bypass tool approval gates for automated/pre-authorized execution
    # Used by agent-based corpus actions where tools are pre-authorized
    skip_approval_gate: bool = Field(
        default=False,
        description="If True, skip approval prompts for all tools in this agent",
    )


class PydanticAIToolWrapper:
    """Modern Pydantic AI tool wrapper following latest patterns."""

    def __init__(
        self,
        core_tool: CoreTool,
        inject_params: dict[str, Any] | None = None,
    ):
        """Initialize the wrapper.

        Args:
            core_tool: The CoreTool instance to wrap
            inject_params: Parameters to automatically inject at execution time,
                hiding them from the LLM's view of the tool schema. This is used
                for context-bound values like document_id or corpus_id that should
                be deterministic (set by the system) rather than chosen by the LLM.
                Maps parameter name -> value to inject.
                Example: {"document_id": 123, "corpus_id": 456}
        """
        self.core_tool = core_tool
        self.inject_params = inject_params or {}
        self._metadata = PydanticAIToolMetadata(
            name=core_tool.name,
            description=core_tool.description,
            parameters=core_tool.parameters,
        )

        # Create a properly typed wrapper function for PydanticAI
        self._wrapped_function = self._create_pydantic_ai_compatible_function()

    @property
    def callable_function(self) -> Callable:
        """The PydanticAI-compatible callable tool function."""
        return self._wrapped_function

    def to_dict(self) -> dict:
        return {
            "function": {
                "name": self.name,
                "description": self.description,
            },
            "name": self.name,
            "description": self.description,
        }

    def _create_pydantic_ai_compatible_function(self) -> Callable:
        """Create a PydanticAI-compatible async function with RunContext as first parameter."""
        original_func = self.core_tool.function
        func_name = self.core_tool.name

        # Get original function signature
        sig = inspect.signature(original_func)

        # Create new parameters list with RunContext as first parameter
        new_params = [
            inspect.Parameter(
                "ctx",
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                annotation=RunContext[PydanticAIDependencies],
            )
        ]

        # Add original parameters, EXCLUDING:
        # - 'self'/'cls' (method artifacts)
        # - Parameters in inject_params (hidden from LLM, auto-injected at runtime)
        for param_name, param in sig.parameters.items():
            if (
                param_name not in ["self", "cls"]
                and param_name not in self.inject_params
            ):
                new_params.append(param)

        # Create new signature (LLM will only see non-injected params)
        new_sig = sig.replace(parameters=new_params)

        # ------------------------------------------------------------------
        # Helper that raises veto-gate exception when required.
        # ------------------------------------------------------------------

        def _maybe_raise(ctx: RunContext[PydanticAIDependencies], *a, **kw):
            """Raise ToolConfirmationRequired if this CoreTool needs approval."""
            # Check if approval is bypassed via deps (for automated corpus actions)
            skip_approval = (
                getattr(ctx.deps, "skip_approval_gate", False) if ctx.deps else False
            )
            if self.core_tool.requires_approval and not skip_approval:
                bound = inspect.signature(original_func).bind(*a, **kw)
                bound.apply_defaults()

                # Make arguments JSON-serialisable to avoid DB/JSONField errors.
                def _serialise(obj):
                    """Return JSON-friendly version of *obj* for metadata storage."""
                    if isinstance(obj, (str, int, float, bool)) or obj is None:
                        return obj
                    if hasattr(obj, "model_dump"):
                        return obj.model_dump()
                    if isinstance(obj, list):
                        return [_serialise(o) for o in obj]
                    if isinstance(obj, tuple):
                        return tuple(_serialise(o) for o in obj)
                    if isinstance(obj, dict):
                        return {k: _serialise(v) for k, v in obj.items()}
                    # Fallback – string representation
                    return str(obj)

                serialised_args = {k: _serialise(v) for k, v in bound.arguments.items()}

                # pydantic-ai attaches a unique tool_call_id to the context
                tool_call_id = getattr(ctx, "tool_call_id", None)

                raise ToolConfirmationRequired(
                    tool_name=self.core_tool.name,
                    tool_args=serialised_args,
                    tool_call_id=tool_call_id,
                )

        # ------------------------------------------------------------------

        if inspect.iscoroutinefunction(original_func):

            async def async_wrapper(
                ctx: RunContext[PydanticAIDependencies], *args, **kwargs
            ):
                """Async wrapper for PydanticAI tools."""
                # Inject context-bound parameters before any other processing.
                # These params are hidden from the LLM and set deterministically.
                for param_name, value in self.inject_params.items():
                    kwargs[param_name] = value

                # Defense-in-depth: validate user permissions BEFORE any tool execution
                # This prevents permission escalation via agents
                await _check_user_permissions(ctx)

                # Defense-in-depth: validate resource ID params match context
                # This prevents prompt injection attacks that try to access other resources
                # (Also validates injected params match deps as additional safety check)
                _validate_resource_id_params(ctx, **kwargs)

                # Trigger approval gate *before* attempting execution.
                _maybe_raise(ctx, *args, **kwargs)

                try:
                    return await original_func(*args, **kwargs)
                except (PermissionError, ToolConfirmationRequired):
                    # Security and approval exceptions must propagate to the
                    # agent loop so they can be handled at the framework level.
                    raise
                except Exception as e:
                    # Operational errors (bad input, missing data, network
                    # failures, etc.) are caught and returned as a descriptive
                    # string so the LLM can inform the user gracefully instead
                    # of crashing the entire agent loop.  See issue #820.
                    logger.error(f"Error in tool {func_name}: {e}")
                    return (
                        f"[Tool error] {func_name} failed: {e}. "
                        "Please inform the user and suggest alternatives."
                    )

            # Set proper metadata
            async_wrapper.__name__ = func_name
            async_wrapper.__doc__ = original_func.__doc__ or self._metadata.description
            async_wrapper.__signature__ = new_sig
            # Ensure the injected ``ctx`` parameter has a proper annotation so
            # that Pydantic-AI's `_takes_ctx` helper can detect it.
            _anns = dict(getattr(original_func, "__annotations__", {}))
            _anns.setdefault("ctx", RunContext[PydanticAIDependencies])
            async_wrapper.__annotations__ = _anns
            # Attach reference to the wrapper for approval checking
            async_wrapper._pydantic_ai_wrapper = self
            async_wrapper.core_tool = self.core_tool
            # Attach requires_approval directly for easy access by _check_tool_requires_approval
            async_wrapper.requires_approval = self.core_tool.requires_approval
            return async_wrapper
        else:
            # Sync tools are called directly (no thread pool).  All
            # production tools are async; this path exists only for
            # lightweight helpers and tests.  If a sync tool touches
            # Django ORM it will raise SynchronousOnlyOperation — the
            # fix is to make the tool async, not to paper over it.

            async def sync_wrapper(
                ctx: RunContext[PydanticAIDependencies], *args, **kwargs
            ):
                """Wrapper that calls a sync tool from an async context."""
                for param_name, value in self.inject_params.items():
                    kwargs[param_name] = value

                await _check_user_permissions(ctx)
                _validate_resource_id_params(ctx, **kwargs)
                _maybe_raise(ctx, *args, **kwargs)

                try:
                    return original_func(*args, **kwargs)
                except (PermissionError, ToolConfirmationRequired):
                    raise
                except Exception as e:
                    logger.error(f"Error in tool {func_name}: {e}")
                    return (
                        f"[Tool error] {func_name} failed: {e}. "
                        "Please inform the user and suggest alternatives."
                    )

            sync_wrapper.__name__ = func_name
            sync_wrapper.__doc__ = original_func.__doc__ or self._metadata.description
            sync_wrapper.__signature__ = new_sig
            _anns_sync = dict(getattr(original_func, "__annotations__", {}))
            _anns_sync.setdefault("ctx", RunContext[PydanticAIDependencies])
            sync_wrapper.__annotations__ = _anns_sync
            sync_wrapper._pydantic_ai_wrapper = self
            sync_wrapper.core_tool = self.core_tool
            sync_wrapper.requires_approval = self.core_tool.requires_approval

            return sync_wrapper

    @property
    def name(self) -> str:
        """Get the tool name."""
        return self._metadata.name

    @property
    def description(self) -> str:
        """Get the tool description."""
        return self._metadata.description

    @property
    def metadata(self) -> PydanticAIToolMetadata:
        """Get the tool metadata."""
        return self._metadata

    def __call__(self, *args, **kwargs) -> Any:
        """Make the wrapper callable."""
        return self._wrapped_function(*args, **kwargs)

    def get_tool_definition(self) -> dict[str, Any]:
        """Get the tool definition for PydanticAI agent registration.

        Returns:
            Dictionary containing tool function and metadata
        """
        return {
            "function": self._wrapped_function,
            "name": self.name,
            "description": self.description,
        }

    def __repr__(self) -> str:
        """String representation."""
        return f"PydanticAIToolWrapper(name='{self.name}', description='{self.description[:50]}...')"


class PydanticAIToolFactory:
    """Modern factory for creating Pydantic AI compatible tools."""

    @staticmethod
    def create_tools(core_tools: list[CoreTool]) -> list[Callable]:
        """Convert a list of CoreTools to modern Pydantic AI callable tools.

        Args:
            core_tools: List of CoreTool instances

        Returns:
            List of PydanticAI-compatible callable functions
        """
        return [PydanticAIToolFactory.create_tool(tool) for tool in core_tools]

    @staticmethod
    def create_tool(
        core_tool: CoreTool,
        inject_params: dict[str, Any] | None = None,
    ) -> Callable:
        """Convert a single CoreTool to a modern Pydantic AI callable tool.

        Args:
            core_tool: CoreTool instance
            inject_params: Parameters to auto-inject at execution time, hiding them
                from the LLM. Used for context-bound values like document_id.
                Example: {"document_id": 123}

        Returns:
            PydanticAI-compatible callable function
        """
        return PydanticAIToolWrapper(
            core_tool, inject_params=inject_params
        ).callable_function

    @staticmethod
    def from_function(
        func: Callable,
        name: Optional[str] = None,
        description: Optional[str] = None,
        parameter_descriptions: Optional[dict[str, str]] = None,
        *,
        requires_approval: bool = False,
        requires_corpus: bool = False,
        requires_write_permission: bool = False,
        inject_params: dict[str, Any] | None = None,
    ) -> Callable:
        """Create a PydanticAI-compatible callable tool directly from a Python function.

        Args:
            func: Python function to wrap
            name: Optional custom name
            description: Optional custom description
            parameter_descriptions: Optional parameter descriptions
            requires_approval: Whether the tool requires approval
            requires_corpus: Whether the tool requires a corpus_id to function
            requires_write_permission: Whether the tool performs write operations
            inject_params: Parameters to auto-inject at execution time, hiding them
                from the LLM. Used for context-bound values like document_id that
                should be deterministic. Maps param name -> value to inject.
                Example: {"document_id": 123}

        Returns:
            PydanticAI-compatible callable function
        """
        core_tool = CoreTool.from_function(
            func=func,
            name=name,
            description=description,
            parameter_descriptions=parameter_descriptions,
            requires_approval=requires_approval,
            requires_corpus=requires_corpus,
            requires_write_permission=requires_write_permission,
        )
        return PydanticAIToolWrapper(
            core_tool, inject_params=inject_params
        ).callable_function

    @staticmethod
    def create_tool_registry(core_tools: list[CoreTool]) -> dict[str, Callable]:
        """Create a registry of PydanticAI-compatible callable tools by name.

        Args:
            core_tools: List of CoreTool instances

        Returns:
            Dictionary mapping tool names to PydanticAI-compatible callable functions
        """
        return {
            tool.name: PydanticAIToolFactory.create_tool(tool) for tool in core_tools
        }

    @staticmethod
    def create_typed_tool_from_function(
        func: Callable,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Callable:
        """Create a fully typed Pydantic AI callable tool using function annotations.

        This method leverages Python type hints to create better tool schemas.

        Args:
            func: Python function with proper type hints
            name: Optional custom name
            description: Optional custom description

        Returns:
            PydanticAI-compatible callable function with enhanced type information
        """
        # Extract type hints
        type_hints = get_type_hints(func)
        sig = inspect.signature(func)

        # Build parameter descriptions from type hints
        parameter_descriptions = {}
        for param_name, param in sig.parameters.items():
            if param_name in type_hints:
                type_hint = type_hints[param_name]
                parameter_descriptions[param_name] = f"Parameter of type {type_hint}"

        return PydanticAIToolFactory.from_function(
            func=func,
            name=name,
            description=description,
            parameter_descriptions=parameter_descriptions,
            requires_corpus=False,
        )


def pydantic_ai_tool(
    name: Optional[str] = None,
    description: Optional[str] = None,
    parameter_descriptions: Optional[dict[str, str]] = None,
) -> Callable[[Callable], Callable]:
    """Decorator to create Pydantic AI compatible callable tools.

    Args:
        name: Optional custom name for the tool
        description: Optional description of the tool
        parameter_descriptions: Optional parameter descriptions

    Returns:
        Decorator function that transforms a function into a PydanticAI-compatible callable tool

    Example:
        @pydantic_ai_tool(description="Extract dates from text")
        async def extract_dates(text: str) -> List[str]: # Note: ctx is added by the wrapper
            '''Extract all dates from the given text.'''
            # Implementation here
            return ["2024-01-01", "2024-12-31"]
    """

    def decorator(func: Callable) -> Callable:
        """Inner decorator that wraps the function."""
        return PydanticAIToolFactory.from_function(
            func=func,
            name=name,
            description=description,
            parameter_descriptions=parameter_descriptions,
            requires_corpus=False,
        )

    return decorator


def create_pydantic_ai_tool_from_func(
    func: Callable,
    name: Optional[str] = None,
    description: Optional[str] = None,
    parameter_descriptions: Optional[dict[str, str]] = None,
) -> Callable:
    """Create a PydanticAI-compatible callable tool from a function.

    Args:
        func: Python function to wrap
        name: Optional custom name
        description: Optional custom description
        parameter_descriptions: Optional parameter descriptions

    Returns:
        PydanticAI-compatible callable function
    """
    return PydanticAIToolFactory.from_function(
        func=func,
        name=name,
        description=description,
        parameter_descriptions=parameter_descriptions,
        requires_corpus=False,
    )


def create_typed_pydantic_ai_tool(func: Callable) -> Callable:
    """Create a fully typed Pydantic AI callable tool using function type hints.

    Args:
        func: Python function with proper type annotations

    Returns:
        PydanticAI-compatible callable function with enhanced type information
    """
    return PydanticAIToolFactory.create_typed_tool_from_function(func)
