import logging
from typing import TYPE_CHECKING, Optional, Union, cast

from channels.db import database_sync_to_async

from opencontractserver.constants.annotations import (
    SUBTREE_GROUP_BLOCK_TEXT_MAX_CHARS,
)
from opencontractserver.pipeline.base.embedder import BaseEmbedder
from opencontractserver.pipeline.base.file_types import FileTypeEnum

if TYPE_CHECKING:
    from opencontractserver.annotations.models import Relationship

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def join_block_text_parts(
    chunks: list[str],
    *,
    max_chars: int = SUBTREE_GROUP_BLOCK_TEXT_MAX_CHARS,
) -> str:
    """Newline-join non-empty strings, truncated at ``max_chars``."""
    # Shared by embedder + vector store + block-context attach so the
    # cap/truncation logic never diverges. Empty strings are skipped so
    # a partially-parsed annotation doesn't inject stray newlines.
    parts: list[str] = []
    running = 0
    for chunk in chunks:
        if not chunk:
            continue
        if running == 0:
            if len(chunk) >= max_chars:
                parts.append(chunk[:max_chars])
                running = max_chars
                break
            parts.append(chunk)
            running = len(chunk)
            continue
        # ``+1`` accounts for the newline separator the join below will
        # insert between successive non-empty parts.
        if running + 1 + len(chunk) > max_chars:
            remaining = max_chars - running - 1
            if remaining > 0:
                parts.append(chunk[:remaining])
            break
        parts.append(chunk)
        running += 1 + len(chunk)

    return "\n".join(parts)


def synthesize_relationship_block_text(
    relationship: "Relationship",
    *,
    max_chars: int = SUBTREE_GROUP_BLOCK_TEXT_MAX_CHARS,
) -> str:
    """Build the embedder-facing string for a ``Relationship``."""
    # Order by ID (not document position) so re-embedding produces a
    # stable input string and ``add_embedding``'s upsert short-circuits
    # unchanged inputs. Document-position ordering would be more
    # semantically meaningful for the embedder but isn't available
    # cheaply today — IDs are dense and roughly insertion-ordered, so
    # the resulting text is usually close to document order anyway.
    # values_list keeps the helper resilient to whether the caller
    # prefetched these M2Ms — couples to a public API, not the private
    # ``_prefetched_objects_cache`` whose shape has shifted across
    # Django versions.
    sources = [
        (text or "")
        for text in relationship.source_annotations.order_by("id").values_list(
            "raw_text", flat=True
        )
    ]
    targets = [
        (text or "")
        for text in relationship.target_annotations.order_by("id").values_list(
            "raw_text", flat=True
        )
    ]
    return join_block_text_parts([*sources, *targets], max_chars=max_chars)


def get_embedder(
    corpus_id: Optional[Union[int, str]] = None,
    mimetype_or_enum: Optional[Union[str, FileTypeEnum]] = None,
    embedder_path: Optional[str] = None,
) -> tuple[Optional[type[BaseEmbedder]], Optional[str]]:
    """
    Get the appropriate embedder for a corpus.

    Args:
        corpus_id: The ID of the corpus
        mimetype_or_enum: The MIME type of the document or a FileTypeEnum (used as fallback)
        embedder_path: The path to the embedder class to use (OVERRIDES ALL OTHER ARGUMENTS)

    Returns:
        A tuple of (embedder_class, embedder_path)
    """

    logger.debug(
        f"get_embedders - arguments: {corpus_id}, {mimetype_or_enum}, {embedder_path}  "
    )

    from opencontractserver.corpuses.models import Corpus
    from opencontractserver.pipeline.utils import (
        find_embedder_for_filetype,
        get_component_by_name,
        get_default_embedder,
    )

    embedder_class: Optional[type[BaseEmbedder]] = None

    # Try to get the corpus's preferred embedder
    if embedder_path:
        logger.debug(f"Explicit embedder_path provided: {embedder_path}")
        try:
            logger.debug(
                f"Attempting to load embedder class from path: {embedder_path}"
            )
            embedder_class = cast(
                type[BaseEmbedder], get_component_by_name(embedder_path)
            )
            logger.debug(
                f"Successfully loaded embedder class: {embedder_class.__name__}"
            )
        except Exception as e:
            logger.warning(
                f"Failed to load embedder class from path {embedder_path}: {str(e)}"
            )
            logger.debug(f"Exception details: {repr(e)}")

    elif corpus_id:
        logger.debug(
            f"No explicit embedder_path, trying to get embedder from corpus_id: {corpus_id}"
        )
        try:
            logger.debug(f"Querying database for corpus with id: {corpus_id}")
            corpus = Corpus.objects.get(id=corpus_id)
            logger.debug(f"Found corpus: {corpus.id}")

            if corpus.preferred_embedder:
                logger.debug(
                    f"Corpus has preferred_embedder: {corpus.preferred_embedder}"
                )
                try:
                    logger.debug(
                        f"Attempting to load corpus preferred embedder: {corpus.preferred_embedder}"
                    )
                    embedder_class = cast(
                        type[BaseEmbedder],
                        get_component_by_name(corpus.preferred_embedder),
                    )
                    embedder_path = corpus.preferred_embedder
                    logger.debug(
                        f"Successfully loaded corpus preferred embedder: {embedder_class.__name__}"
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to load corpus preferred embedder {corpus.preferred_embedder}: {str(e)}"
                    )
                    logger.debug(f"Exception details: {repr(e)}")
                    logger.debug("Will fall back to mimetype-based embedder selection")
            else:
                logger.debug(f"Corpus {corpus_id} has no preferred_embedder configured")
        except Exception as e:
            logger.warning(f"Failed to retrieve corpus with id {corpus_id}: {str(e)}")
            logger.debug(f"Exception details: {repr(e)}")
            logger.debug("Will fall back to mimetype-based embedder selection")

    # If no explicit or corpus-specific embedder was found and a mimetype is provided,
    # try to find an appropriate embedder for the mimetype
    if embedder_class is None and mimetype_or_enum:
        logger.debug(
            f"No embedder found yet, trying mimetype-based selection with: {mimetype_or_enum}"
        )

        # Find an embedder for the mimetype and dimension
        logger.debug(f"Calling find_embedder_for_filetype with: {mimetype_or_enum}")
        embedder_class = find_embedder_for_filetype(mimetype_or_enum)
        if embedder_class:
            embedder_path = f"{embedder_class.__module__}.{embedder_class.__name__}"
            logger.debug(f"Found mimetype-specific embedder: {embedder_path}")
        else:
            logger.debug(f"No mimetype-specific embedder found for: {mimetype_or_enum}")

    # Fall back to default embedder if no specific embedder is found
    if embedder_class is None:
        logger.debug(
            "No embedder found through specific methods, falling back to default embedder"
        )
        embedder_class = get_default_embedder()
        if embedder_class:
            embedder_path = f"{embedder_class.__module__}.{embedder_class.__name__}"
            logger.debug(f"Using default embedder: {embedder_path}")
        else:
            logger.warning("Failed to get default embedder")

    logger.debug(
        f"Return embedder class: {embedder_class}, embedder path: {embedder_path}"
    )

    return embedder_class, embedder_path


def generate_embeddings_from_text(
    text: str,
    corpus_id: Optional[int] = None,
    mimetype: Optional[Union[str, "FileTypeEnum"]] = None,
    embedder_path: Optional[str] = None,
) -> tuple[Optional[str], Optional[list[float]]]:
    """
    Unified function to generate embeddings for a given text, optionally using
    the corpus's configured embedder class if available, otherwise falling
    back to an external embeddings microservice (or default embedder) as needed.

    Args:
        text (str): The text to embed.
        corpus_id (Optional[int]): ID of the corpus to retrieve embedder configuration from.
        mimetype (Optional[Union[str, FileTypeEnum]]): MIME type or file type for specialized embedding logic.

    Returns:
        Tuple[Optional[str], Optional[List[float]]]:
            - The embedder_path that was used (or None if not found).
            - The list of floats representing the embedding vector (or None on error).
    """
    if not text.strip():
        logger.warning(
            f"generate_embeddings_from_text() - text is empty or whitespace for corpus_id {corpus_id}"
        )
        return None, None

    embedder_class, embedder_path = get_embedder(
        corpus_id, mimetype_or_enum=mimetype, embedder_path=embedder_path
    )
    logger.debug(
        f"Selected embedder: class={embedder_class.__name__ if embedder_class else None}, path={embedder_path}"
    )

    # If we found a valid Python embedder class with an embed_text method, use it.
    if embedder_class:
        try:
            # Use the process-cached instance: constructing an embedder loads
            # settings from the DB and decrypts secrets with an expensive
            # PBKDF2 KDF, which we must not pay on every embed call. See
            # ``get_embedder_instance`` for the caching/invalidation contract.
            from opencontractserver.pipeline.utils import get_embedder_instance

            logger.debug(f"Resolving embedder instance of {embedder_class.__name__}")
            embedder_instance = get_embedder_instance(embedder_class, embedder_path)

            logger.debug(f"Embedding text with {embedder_class.__name__}")
            vector = embedder_instance.embed_text(text)
            return embedder_path, vector
        except Exception as e:
            logger.error(
                f"Failed to generate embeddings via embedder class {embedder_class.__name__}: {e}"
            )
            logger.exception("Detailed embedding generation error:")

    logger.warning(
        f"No suitable embedder found or embedding generation failed for corpus_id={corpus_id}"
    )
    return None, None


def calculate_embedding_for_text(
    text: str,
    corpus_id: Optional[int] = None,
    mimetype: Optional[Union[str, "FileTypeEnum"]] = None,
) -> Optional[list[float]]:
    """
    DEPRECATED (but kept for backward compatibility):
    Please use generate_embeddings_from_text(...) directly.
    This function calls generate_embeddings_from_text and returns only the vector.
    """
    _, embeddings = generate_embeddings_from_text(text, corpus_id, mimetype)
    return embeddings


async def aget_embedder(
    corpus_id: Optional[Union[int, str]] = None,
    mimetype_or_enum: Optional[Union[str, FileTypeEnum]] = None,
    embedder_path: Optional[str] = None,
) -> tuple[Optional[type[BaseEmbedder]], Optional[str]]:
    """
    Async version of `get_embedder`.

    All database access is executed with `database_sync_to_async` so that it
    never blocks the event-loop thread.  The public signature mirrors the
    synchronous helper for drop-in replacement.
    """
    # Wrap the synchronous implementation to keep the code DRY.
    return await database_sync_to_async(get_embedder, thread_sensitive=False)(
        corpus_id, mimetype_or_enum, embedder_path
    )


async def agenerate_embeddings_from_text(
    text: str,
    corpus_id: Optional[int] = None,
    mimetype: Optional[Union[str, "FileTypeEnum"]] = None,
    embedder_path: Optional[str] = None,
) -> tuple[Optional[str], Optional[list[float]]]:
    """
    Async wrapper around ``generate_embeddings_from_text``.

    The synchronous implementation performs blocking I/O (DB look-ups,
    model loading).  Running it in the event-loop thread would trigger
    ``SynchronousOnlyOperation`` and stall other coroutines.  We therefore
    delegate the entire call via ``database_sync_to_async``.

    Returns
    -------
    (embedder_path, vector)      – identical to the synchronous helper.
    """
    return await database_sync_to_async(
        generate_embeddings_from_text, thread_sensitive=False
    )(
        text,
        corpus_id,
        mimetype,
        embedder_path,
    )
