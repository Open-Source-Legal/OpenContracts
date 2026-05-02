"""Tools for reading and updating per-corpus agent memory documents."""

from ._helpers import _db_sync_to_async


async def aget_corpus_memory(
    corpus_id: int,
    user_id: int,
    section: str = "",
) -> str:
    """Read the corpus agent memory document.

    Returns the full memory content or, if ``section`` is specified, only the
    matching section (e.g. "Collection Patterns" or "Query Patterns").

    Args:
        corpus_id: The corpus ID.
        user_id: The requesting user (injected from context).
        section: Optional section header to filter to.

    Returns:
        The memory document content, or a message if no memory exists.
    """
    from django.contrib.auth import get_user_model

    from opencontractserver.agents.memory import (
        read_memory_content,
        split_memory_sections,
    )
    from opencontractserver.corpuses.models import Corpus

    User = get_user_model()

    try:
        user = await User.objects.aget(pk=user_id)
    except User.DoesNotExist as exc:
        raise ValueError(f"User with id={user_id} does not exist.") from exc

    try:
        corpus = await _db_sync_to_async(
            lambda: Corpus.objects.visible_to_user(user).get(pk=corpus_id)
        )()
    except Corpus.DoesNotExist as exc:
        raise ValueError(
            f"Corpus with id={corpus_id} does not exist or is not accessible."
        ) from exc

    if not corpus.memory_enabled:
        return "Memory is not enabled for this corpus."

    content = await read_memory_content(corpus)
    if not content:
        return "No memory document exists for this corpus yet."

    if not section:
        return content

    # Filter to the requested section
    sections = split_memory_sections(content)
    for s in sections:
        if s.lower().startswith(f"## {section.lower()}"):
            return s

    return f"Section '{section}' not found in memory document."


async def asuggest_memory_update(
    corpus_id: int,
    user_id: int,
    section: str,
    insight: str,
) -> str:
    """Suggest a new insight to add to the corpus memory document.

    The insight is appended to the specified section of the memory document.
    This allows agents to explicitly contribute learnings during a conversation.

    Note: There is currently no per-conversation rate limit on memory updates.
    An agent could call this tool many times in a single conversation.  The
    ``MEMORY_INSIGHT_MAX_LENGTH`` cap and write-permission check provide some
    guardrails, but per-session throttling may be warranted if abuse is observed.

    Args:
        corpus_id: The corpus ID.
        user_id: The user performing the update.
        section: Which section to add to ("collection_patterns" or "query_patterns").
        insight: The insight text (formatted as ``- **Title**: Description``).

    Returns:
        Confirmation message.
    """
    from django.contrib.auth import get_user_model

    from opencontractserver.agents.memory import (
        get_or_create_memory_document,
        merge_curation_into_memory,
        read_memory_content,
        update_memory_content,
    )
    from opencontractserver.constants.agent_memory import MEMORY_INSIGHT_MAX_LENGTH
    from opencontractserver.corpuses.models import Corpus

    User = get_user_model()

    # Content validation
    insight = insight.strip()
    if not insight:
        return "Insight text cannot be empty."
    if len(insight) > MEMORY_INSIGHT_MAX_LENGTH:
        return (
            f"Insight exceeds maximum length of {MEMORY_INSIGHT_MAX_LENGTH} "
            f"characters ({len(insight)} provided). Please shorten the insight."
        )

    try:
        user = await User.objects.aget(pk=user_id)
    except User.DoesNotExist as exc:
        raise ValueError(f"User with id={user_id} does not exist.") from exc

    try:
        corpus = await _db_sync_to_async(
            lambda: Corpus.objects.visible_to_user(user).get(pk=corpus_id)
        )()
    except Corpus.DoesNotExist as exc:
        raise ValueError(
            f"Corpus with id={corpus_id} does not exist or is not accessible."
        ) from exc

    # visible_to_user only checks read access; writing to memory requires CRUD.
    from opencontractserver.types.enums import PermissionTypes
    from opencontractserver.utils.permissioning import user_has_permission_for_obj

    has_write = await _db_sync_to_async(user_has_permission_for_obj)(
        user, corpus, PermissionTypes.CRUD
    )
    if not has_write:
        raise PermissionError(
            f"User does not have write permission on corpus {corpus_id}."
        )

    if not corpus.memory_enabled:
        return "Memory is not enabled for this corpus."

    # Ensure memory document exists
    await get_or_create_memory_document(corpus, user)

    current_content = await read_memory_content(corpus)

    # Route to the correct section (validate explicitly)
    normalized = section.lower().replace(" ", "_")
    valid_sections = {"collection_patterns", "query_patterns"}
    if normalized not in valid_sections:
        return (
            f"Invalid section '{section}'. "
            f"Must be one of: {', '.join(sorted(valid_sections))}"
        )

    collection = []
    query = []
    if normalized == "collection_patterns":
        collection = [insight]
    else:
        query = [insight]

    updated = merge_curation_into_memory(
        current_content=current_content,
        collection_patterns=collection,
        query_patterns=query,
        refinements=[],
    )
    await update_memory_content(corpus, updated, user)

    return f"Insight added to {section} section of corpus memory."
