import importlib
import inspect
import logging
import pkgutil
import threading
from typing import Any, Optional, Union

from opencontractserver.pipeline.base.base_component import PipelineComponentBase
from opencontractserver.pipeline.base.embedder import BaseEmbedder
from opencontractserver.pipeline.base.enricher import BaseEnricher
from opencontractserver.pipeline.base.file_types import FILE_TYPE_TO_MIME, FileTypeEnum
from opencontractserver.pipeline.base.parser import BaseParser
from opencontractserver.pipeline.base.post_processor import BasePostProcessor
from opencontractserver.pipeline.base.reranker import BaseReranker
from opencontractserver.pipeline.base.thumbnailer import BaseThumbnailGenerator
from opencontractserver.types.dicts import (
    OpenContractDocExport,
    OpenContractsExportDataJsonPythonType,
)

logger = logging.getLogger(__name__)


def get_all_subclasses(module_name: str, base_class: type) -> list[type]:
    """
    Get all subclasses of a base class within a given module.

    Args:
        module_name (str): The module to search in.
        base_class (Type): The base class to find subclasses of.

    Returns:
        List[Type]: List of subclass types.
    """
    subclasses = []
    package = importlib.import_module(module_name)
    prefix = package.__name__ + "."

    for _, modname, ispkg in pkgutil.iter_modules(package.__path__, prefix):
        if not ispkg:
            module = importlib.import_module(modname)
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if issubclass(obj, base_class) and obj != base_class:
                    subclasses.append(obj)
    return subclasses


def get_all_parsers() -> list[type[BaseParser]]:
    """
    Get all parser classes.

    Returns:
        List[Type[BaseParser]]: List of parser classes.
    """
    return get_all_subclasses("opencontractserver.pipeline.parsers", BaseParser)


def get_all_embedders() -> list[type[BaseEmbedder]]:
    """
    Get all embedder classes.

    Returns:
        List[Type[BaseEmbedder]]: List of embedder classes.
    """
    return get_all_subclasses("opencontractserver.pipeline.embedders", BaseEmbedder)


def get_all_thumbnailers() -> list[type[BaseThumbnailGenerator]]:
    """
    Get all thumbnail generator classes.

    Returns:
        List[Type[BaseThumbnailGenerator]]: List of thumbnail generator classes.
    """
    return get_all_subclasses(
        "opencontractserver.pipeline.thumbnailers", BaseThumbnailGenerator
    )


def get_all_post_processors() -> list[type[BasePostProcessor]]:
    """
    Get all post-processor classes.

    Returns:
        List[Type[BasePostProcessor]]: List of post-processor classes.
    """
    return get_all_subclasses(
        "opencontractserver.pipeline.post_processors", BasePostProcessor
    )


def get_all_rerankers() -> list[type[BaseReranker]]:
    """
    Get all reranker classes.

    Returns:
        List[Type[BaseReranker]]: List of reranker classes.
    """
    return get_all_subclasses("opencontractserver.pipeline.rerankers", BaseReranker)


def get_components_by_mimetype(
    file_type: Optional[Union[str, FileTypeEnum]] = None, detailed: bool = False
) -> dict[str, list[Any]]:
    """
    Given a mimetype string or FileTypeEnum, fetch lists of compatible parsers,
    embedders, and thumbnailers.

    Args:
        file_type (Optional[Union[str, FileTypeEnum]]): The file type enum or
            mimetype string (converted via FileTypeEnum.from_mimetype)
        detailed (bool): If True, include title, description, and author details

    Returns:
        Dict[str, List[Any]]: Dictionary with lists of compatible components
    """
    # Initialize component lists
    parsers: list[Any] = []
    embedders: list[Any] = []
    thumbnailers: list[Any] = []
    post_processors: list[Any] = []

    # Handle mimetype string case for backward compatibility
    if isinstance(file_type, str):
        file_type = FileTypeEnum.from_mimetype(file_type)

    # If file_type is None or not supported, return empty lists
    if file_type is None:
        logger.warning(f"Unsupported file type: {file_type}")
        return {
            "parsers": parsers,
            "embedders": embedders,
            "thumbnailers": thumbnailers,
            "post_processors": post_processors,
        }

    # Get compatible parsers
    for parser_class in get_all_parsers():
        if file_type in parser_class.supported_file_types:
            module_name = parser_class.__module__.split(".")[-1]
            if detailed:
                parsers.append(
                    {
                        "class": parser_class,
                        "module_name": module_name,
                        "title": parser_class.title,
                        "description": parser_class.description,
                        "author": parser_class.author,
                        "input_schema": parser_class.input_schema,
                    }
                )
            else:
                parsers.append(parser_class)

    # Get compatible embedders (assuming embedders work on text output)
    for embedder_class in get_all_embedders():
        module_name = embedder_class.__module__.split(".")[-1]
        if detailed:
            embedders.append(
                {
                    "class": embedder_class,
                    "title": embedder_class.title,
                    "module_name": module_name,
                    "description": embedder_class.description,
                    "author": embedder_class.author,
                    "vector_size": embedder_class.vector_size,
                    "input_schema": embedder_class.input_schema,
                }
            )
        else:
            embedders.append(embedder_class)

    # Get compatible thumbnailers
    for thumbnailer_class in get_all_thumbnailers():
        if file_type in thumbnailer_class.supported_file_types:
            module_name = thumbnailer_class.__module__.split(".")[-1]
            if detailed:
                thumbnailers.append(
                    {
                        "class": thumbnailer_class,
                        "module_name": module_name,
                        "title": thumbnailer_class.title,
                        "description": thumbnailer_class.description,
                        "author": thumbnailer_class.author,
                        "input_schema": thumbnailer_class.input_schema,
                    }
                )
            else:
                thumbnailers.append(thumbnailer_class)

    # Get compatible post-processors
    for post_processor_class in get_all_post_processors():
        if file_type in post_processor_class.supported_file_types:
            logger.info(post_processor_class)
            logger.info(dir(post_processor_class))
            module_name = post_processor_class.__module__.split(".")[-1]
            post_processors.append(
                {
                    "class": post_processor_class,
                    "title": post_processor_class.title,
                    "module_name": module_name,
                    "description": post_processor_class.description,
                    "author": post_processor_class.author,
                    "input_schema": post_processor_class.input_schema,
                }
            )

    return {
        "parsers": parsers,
        "embedders": embedders,
        "thumbnailers": thumbnailers,
        "post_processors": post_processors,
    }


def get_metadata_for_component(
    component_class: type[PipelineComponentBase],
) -> dict[str, Any]:
    """
    Given a component class, return its metadata.

    Args:
        component_class (Type): The component class.

    Returns:
        Dict[str, Any]: Dictionary of metadata.
    """

    module_name = component_class.__module__.split(".")[-1]
    metadata: dict[str, Any] = {
        "title": component_class.title,
        "module_name": module_name,
        "description": component_class.description,
        "author": component_class.author,
        "dependencies": component_class.dependencies,
        "input_schema": component_class.input_schema,
    }

    if hasattr(component_class, "vector_size"):
        metadata["vector_size"] = component_class.vector_size

    if hasattr(component_class, "supported_file_types"):
        # Filter out any file types that are no longer supported (like HTML)
        supported_types = []
        for file_type in component_class.supported_file_types:
            # Only include file types that are still defined in FileTypeEnum
            if file_type in [FileTypeEnum.PDF, FileTypeEnum.TXT, FileTypeEnum.DOCX]:
                supported_types.append(file_type)
        metadata["supported_file_types"] = supported_types

    return metadata


def get_metadata_by_component_name(component_name: str) -> dict[str, Any]:
    """
    Given the script name of a pipeline component, fetch all metadata.

    Args:
        component_name (str): The name of the component script.

    Returns:
        Dict[str, Any]: Dictionary of metadata.
    """
    component_class = get_component_by_name(component_name)
    return get_metadata_for_component(component_class)


def get_component_by_name(component_name: str) -> type[PipelineComponentBase]:
    """
    Given the script name or full path of a pipeline component, return the class itself.

    Args:
        component_name (str): The name or full path of the component script.

    Returns:
        Type: The component class.
    """
    # Handle full path case by extracting the module and class names
    if "." in component_name:
        try:
            module_path, class_name = component_name.rsplit(".", 1)
            module = importlib.import_module(module_path)
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if name == class_name and (
                    issubclass(obj, BaseParser)
                    or issubclass(obj, BaseEmbedder)
                    or issubclass(obj, BaseThumbnailGenerator)
                    or issubclass(obj, BasePostProcessor)
                    or issubclass(obj, BaseEnricher)
                    or issubclass(obj, BaseReranker)
                ):
                    return obj
        except (ModuleNotFoundError, AttributeError):
            pass

    # Original implementation for script name only
    base_paths = [
        "opencontractserver.pipeline.parsers",
        "opencontractserver.pipeline.embedders",
        "opencontractserver.pipeline.thumbnailers",
        "opencontractserver.pipeline.post_processors",
        "opencontractserver.pipeline.enrichers",
        "opencontractserver.pipeline.rerankers",
    ]

    for base_path in base_paths:
        try:
            module = importlib.import_module(f"{base_path}.{component_name}")
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if (
                    (issubclass(obj, BaseParser) and obj != BaseParser)
                    or (issubclass(obj, BaseEmbedder) and obj != BaseEmbedder)
                    or (
                        issubclass(obj, BaseThumbnailGenerator)
                        and obj != BaseThumbnailGenerator
                    )
                    or (issubclass(obj, BasePostProcessor) and obj != BasePostProcessor)
                    or (issubclass(obj, BaseEnricher) and obj != BaseEnricher)
                    or (issubclass(obj, BaseReranker) and obj != BaseReranker)
                ):
                    return obj
        except ModuleNotFoundError:
            continue

    raise ValueError(f"Component '{component_name}' not found.")


def get_preferred_embedder(mimetype: str) -> Optional[type[BaseEmbedder]]:
    """
    Get the preferred embedder class for a given mimetype.

    Reads from the database PipelineSettings singleton.

    Args:
        mimetype (str): The mimetype of the file.

    Returns:
        Optional[Type[BaseEmbedder]]: The preferred embedder class, or None if not found.
    """
    # Import here to avoid circular imports
    from opencontractserver.documents.models import PipelineSettings

    pipeline_settings = PipelineSettings.get_instance()
    embedder_path = pipeline_settings.get_preferred_embedder(mimetype)

    if embedder_path:
        try:
            module_path, class_name = embedder_path.rsplit(".", 1)
            module = importlib.import_module(module_path)
            embedder_class = getattr(module, class_name)
            return embedder_class
        except (ModuleNotFoundError, AttributeError) as e:
            logger.error(f"Error loading embedder '{embedder_path}': {e}")
            return None
    else:
        logger.warning(f"No preferred embedder set for mimetype: {mimetype}")
        return None


def get_default_embedder_path() -> str:
    """
    Get the default embedder class path from the database PipelineSettings singleton.

    Returns:
        str: The default embedder class path, or empty string if not configured.
    """
    # Import here to avoid circular imports
    from opencontractserver.documents.models import PipelineSettings

    return PipelineSettings.get_instance().get_default_embedder()


def get_default_llm_spec() -> str:
    """Get the install-wide default LLM model spec from PipelineSettings.

    Returns the runtime-configurable ``PipelineSettings.default_llm`` (set by
    superusers in the admin System Settings UI). An empty string means "no
    runtime override is configured" — callers should pass this through to
    :func:`opencontractserver.llms.llm_registry.resolve_model_spec` as
    ``settings_default`` so the documented priority chain falls back to the
    Django settings default.

    **Sync-only**: performs synchronous ORM access via
    ``PipelineSettings.get_instance()``. Call from synchronous contexts or
    wrap in ``sync_to_async`` when invoking from async code.

    Returns:
        str: The default LLM model spec (e.g. "anthropic:claude-opus-4-6"),
        or empty string if not configured.
    """
    # Import here to avoid circular imports
    from opencontractserver.documents.models import PipelineSettings

    return PipelineSettings.get_instance().get_default_llm()


def get_default_embedder() -> Optional[type[BaseEmbedder]]:
    """
    Get the default embedder class.

    Reads from the database PipelineSettings singleton.

    Returns:
        Optional[Type[BaseEmbedder]]: The default embedder class, or None if not found.
    """
    embedder_path = get_default_embedder_path()

    if embedder_path:
        try:
            module_path, class_name = embedder_path.rsplit(".", 1)
            module = importlib.import_module(module_path)
            embedder_class = getattr(module, class_name)
            return embedder_class
        except (ModuleNotFoundError, AttributeError) as e:
            logger.error(f"Error loading default embedder '{embedder_path}': {e}")
            return None
    else:
        logger.error("No default embedder configured in PipelineSettings")
        return None


def get_default_embedder_for_filetype(mimetype: str) -> Optional[type[BaseEmbedder]]:
    """
    Get the default embedder for a specific filetype.

    Reads from the database PipelineSettings singleton's preferred_embedders,
    falling back to the global default embedder if no MIME-specific embedder
    is configured.

    Args:
        mimetype: The MIME type of the file

    Returns:
        Optional[Type[BaseEmbedder]]: The default embedder for the specified filetype,
        or None if not found
    """
    embedder = get_preferred_embedder(mimetype)
    if embedder is not None:
        return embedder
    return get_default_embedder()


def get_dimension_from_embedder(
    embedder_class_or_path: Union[type[BaseEmbedder], str],
) -> int:
    """
    Get the dimension from an embedder class or path.

    Args:
        embedder_class_or_path: Either an embedder class or a path to an embedder class

    Returns:
        int: The dimension of the embedder, or the default dimension if not found
    """
    from django.conf import settings

    default_dim = getattr(settings, "DEFAULT_EMBEDDING_DIMENSION", 768)

    if isinstance(embedder_class_or_path, str):
        try:
            embedder_class = get_component_by_name(embedder_class_or_path)
        except ValueError:
            logger.error(f"Could not find embedder class: {embedder_class_or_path}")
            return default_dim
    else:
        embedder_class = embedder_class_or_path

    if embedder_class and hasattr(embedder_class, "vector_size"):
        return embedder_class.vector_size

    return default_dim


def find_embedder_for_filetype(
    mimetype_or_enum: Union[str, FileTypeEnum],
) -> Optional[type[BaseEmbedder]]:
    """
    Find an appropriate embedder for a specific file type and dimension.

    Args:
        mimetype_or_enum: The MIME type of the file or a FileTypeEnum
        dimension: The desired embedding dimension (optional)

    Returns:
        Optional[Type[BaseEmbedder]]: An appropriate embedder class, or None if not found
    """
    # Ensure we're working with a mimetype string, not a FileTypeEnum
    if isinstance(mimetype_or_enum, FileTypeEnum):
        mimetype = FILE_TYPE_TO_MIME.get(mimetype_or_enum.value)
        if not mimetype:
            logger.warning(
                f"Could not convert FileTypeEnum {mimetype_or_enum} to mimetype"
            )
            return get_default_embedder()
    else:
        mimetype = mimetype_or_enum

    embedder = get_preferred_embedder(mimetype)
    if embedder is not None:
        return embedder
    return get_default_embedder()


def run_post_processors(
    processor_paths: list[str],
    zip_bytes: bytes,
    export_data: OpenContractsExportDataJsonPythonType,
    input_kwargs: dict[str, Any] = {},
) -> tuple[bytes, OpenContractsExportDataJsonPythonType]:
    """
    Load and run post-processors in sequence.

    Args:
        processor_paths: List of fully qualified Python paths to post-processor classes
        zip_bytes: The raw bytes of the zip file being created
        export_data: The export data dictionary that will be serialized to data.json

    Returns:
        Tuple containing:
            - Modified zip bytes
            - Modified export data dictionary
    """
    current_zip_bytes = zip_bytes
    current_export_data = export_data

    for path in processor_paths:
        try:
            logger.info(f"Loading post-processor: {path}")
            processor_class = get_component_by_name(path)
            if not issubclass(processor_class, BasePostProcessor):
                raise TypeError(
                    f"Component '{path}' is not a BasePostProcessor subclass"
                )
            logger.debug(f"Initializing post-processor {processor_class.__name__}")
            processor = processor_class()
            logger.info(f"Running post-processor: {processor.title}")
            current_zip_bytes, current_export_data = processor.process_export(
                current_zip_bytes, current_export_data, **input_kwargs
            )
            logger.debug(f"Completed post-processor: {processor.title}")
        except Exception as e:
            logger.error(f"Error running post-processor {path}: {str(e)}")
            raise

    return current_zip_bytes, current_export_data


def run_enrichers(
    enricher_paths: list[str],
    user_id: int,
    doc_id: int,
    export_data: OpenContractDocExport,
    input_kwargs: Optional[dict[str, Any]] = None,
) -> OpenContractDocExport:
    """
    Run a configured, ordered chain of enrichers over a parsed document's
    export data.

    Each enricher receives the output of the previous one
    (``OpenContractDocExport -> OpenContractDocExport``), so enrichers compose.
    This is the ingest-time analogue of :func:`run_post_processors`.

    Enrichment is additive and OPTIONAL: any failure — a class path that will
    not load, a component that is not a ``BaseEnricher`` subclass, or an
    exception raised inside the enricher — is logged at WARNING level and that
    enricher is skipped. The chain continues with the last good ``export_data``
    so a misbehaving enricher can never fail document ingestion.

    Args:
        enricher_paths: Ordered list of fully-qualified enricher class paths.
        user_id: ID of the user the document is being ingested for.
        doc_id: ID of the document being ingested.
        export_data: The parsed document data produced by the parser.
        input_kwargs: Optional kwargs forwarded to every enricher's
            ``enrich_document`` call (these override PipelineSettings component
            settings).

    Returns:
        OpenContractDocExport: The final, possibly-enriched document data.
    """
    current_export_data = export_data
    kwargs = input_kwargs or {}

    for path in enricher_paths:
        try:
            logger.info(f"Loading enricher: {path}")
            enricher_class = get_component_by_name(path)
            if not issubclass(enricher_class, BaseEnricher):
                logger.warning(
                    f"Skipping enricher '{path}': not a BaseEnricher subclass"
                )
                continue
            enricher = enricher_class()
            logger.info(f"Running enricher: {enricher.title or path}")
            result = enricher.enrich_document(
                user_id, doc_id, current_export_data, **kwargs
            )
            if result is not None:
                current_export_data = result
        except Exception as e:
            # Enrichment is non-fatal: log and continue so a misbehaving
            # enricher never blocks document ingestion.
            logger.warning(
                f"Enricher '{path}' failed for doc {doc_id}; skipping "
                f"(ingestion continues): {e}",
                exc_info=True,
            )

    return current_export_data


# --------------------------------------------------------------------------- #
# Reranker helpers
# --------------------------------------------------------------------------- #
# Process-local cache of reranker *instances* keyed by (class path,
# PipelineSettings.modified). Rerankers (especially cross-encoder backends)
# can be expensive to instantiate because ``__init__`` loads component
# settings from the database and cross-encoder model weights are large.
#
# Cross-worker coherence: the cache key includes PipelineSettings.modified.
# Every config change bumps that timestamp, which propagates to all workers
# via PipelineSettings' Django cache (shared Redis). The next lookup in each
# worker misses on the new key and re-loads, so all workers converge to the
# new reranker within Django's PipelineSettings cache TTL (5 minutes).
#
# Failure handling: we deliberately do NOT cache failures. A transient
# instantiation error in one worker (e.g. network blip reaching a remote
# reranker) must not pin that worker to "no reranking" while sibling workers
# continue to rerank -- that would produce unpredictable per-query behaviour
# depending on which worker served the request. Each call retries. The
# cost is bounded: import errors are cheap, and genuine service outages are
# rare relative to query volume. The caller treats ``None`` as "skip
# reranking this call" so correctness is preserved either way.
_RERANKER_INSTANCE_CACHE: dict[tuple[str, Any], BaseReranker] = {}
# Guards against two concurrent retrievals paying the reranker-construction
# cost twice. Instance lookups after warm-up are read-only so no lock is
# needed on the hot path.
_RERANKER_CACHE_LOCK = threading.Lock()


def _get_pipeline_cache_key(class_path: str) -> tuple[str, Any]:
    """Cache key that changes whenever PipelineSettings is written.

    Shared by the process-local reranker and embedder instance caches.
    Using ``modified`` (auto_now DateTime) means every edit — even one
    that doesn't touch the relevant component path — invalidates the local
    cache across all workers on their next lookup. That's conservative but
    cheap; component construction dominates over a cache miss.
    """
    from opencontractserver.documents.models import PipelineSettings

    modified = PipelineSettings.get_instance().modified
    return (class_path, modified)


def get_default_reranker_path() -> str:
    """
    Get the default reranker class path from the database PipelineSettings
    singleton. Returns empty string when no reranker is configured.
    """
    from opencontractserver.documents.models import PipelineSettings

    return PipelineSettings.get_instance().get_default_reranker()


def get_default_reranker_class() -> Optional[type[BaseReranker]]:
    """
    Resolve the configured default reranker class path to an actual class.

    Returns ``None`` when no reranker is configured, or when the configured
    class path cannot be imported (missing optional dependency, typo, etc.).
    The caller is responsible for treating ``None`` as "reranking disabled".
    """
    class_path = get_default_reranker_path()
    if not class_path:
        return None
    try:
        module_path, class_name = class_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        reranker_class = getattr(module, class_name)
    except (ModuleNotFoundError, AttributeError, ValueError) as e:
        logger.warning(f"Error loading reranker '{class_path}': {e}")
        return None

    if not isinstance(reranker_class, type) or not issubclass(
        reranker_class, BaseReranker
    ):
        logger.warning(
            f"Configured default reranker '{class_path}' is not a BaseReranker subclass"
        )
        return None
    return reranker_class


def get_default_reranker_instance(
    *, require: Optional[bool] = None
) -> Optional[BaseReranker]:
    """
    Return a process-cached instance of the configured default reranker.

    Args:
        require: When True, raise :class:`RerankerUnavailableError` instead
            of returning ``None`` if the reranker is unconfigured or fails
            to instantiate. Defaults to the ``STRICT_RERANKER`` Django
            setting (which itself defaults to False). Set this for
            benchmark runs and anywhere silent fallback would poison
            results.

    Returns:
        A reranker instance, or ``None`` when unconfigured / unavailable
        and ``require`` is False.

    Raises:
        RerankerUnavailableError: When ``require`` is True and the
        reranker cannot be provided.

    Instantiation failures are intentionally NOT cached: a transient error
    in one worker must not pin that worker to degraded behaviour while
    siblings continue reranking successfully. See the module-level comment
    for the rationale.

    Cache invalidation: the cache key includes ``PipelineSettings.modified``,
    so DB writes bust it process-wide. Tests that patch settings purely
    in-memory will hit stale instances — set ``STRICT_RERANKER`` (which
    bypasses the cache fast-path) or call :func:`invalidate_reranker_cache`
    explicitly if you need a fresh instance from a fixture.

    Caveat (issue #1410): ``modified`` is an ``auto_now`` field that only
    ticks on ``save()`` / ``Model.save()``-equivalent code paths. Any code
    that bypasses ``save()`` — e.g., ``QuerySet.update``, ``bulk_update``,
    or a data migration that writes ``default_reranker`` directly — will
    *not* bump ``modified``, so workers can stay pinned on the stale cached
    instance until their process restarts. If you must mutate the singleton
    from a migration or bulk-update path, also call
    :func:`invalidate_reranker_cache` (or touch ``modified`` explicitly) so
    every worker picks up the new config on its next lookup.
    """
    from django.conf import settings as django_settings

    from opencontractserver.pipeline.base.reranker import RerankerUnavailableError

    if require is None:
        require = bool(getattr(django_settings, "STRICT_RERANKER", False))

    class_path = get_default_reranker_path()
    if not class_path:
        if require:
            raise RerankerUnavailableError(
                "STRICT_RERANKER=True but no default reranker is configured"
            )
        return None

    cache_key = _get_pipeline_cache_key(class_path)
    cached = _RERANKER_INSTANCE_CACHE.get(cache_key)
    if cached is not None:
        return cached

    with _RERANKER_CACHE_LOCK:
        # Double-check after acquiring the lock -- another thread may have
        # populated the cache while we waited.
        cached = _RERANKER_INSTANCE_CACHE.get(cache_key)
        if cached is not None:
            return cached

        reranker_class = get_default_reranker_class()
        if reranker_class is None:
            if require:
                raise RerankerUnavailableError(
                    f"Reranker '{class_path}' could not be loaded "
                    "(missing dependency, bad class path, or not a "
                    "BaseReranker subclass)"
                )
            return None

        try:
            instance = reranker_class()
        except Exception as e:
            if require:
                raise RerankerUnavailableError(
                    f"Failed to instantiate reranker '{class_path}': {e}"
                ) from e
            logger.warning(
                f"Failed to instantiate reranker '{class_path}': {e}. "
                "Skipping reranking for this call; will retry on the next."
            )
            return None

        _RERANKER_INSTANCE_CACHE[cache_key] = instance
        return instance


def invalidate_reranker_cache() -> None:
    """Drop cached reranker instances.

    In normal operation this is unnecessary — the cache key includes
    ``PipelineSettings.modified`` so any settings write naturally
    invalidates the cache on the next lookup across all workers. Kept
    for test isolation and for callers that want an immediate purge.
    """
    with _RERANKER_CACHE_LOCK:
        _RERANKER_INSTANCE_CACHE.clear()


# --------------------------------------------------------------------------- #
# Embedder helpers
# --------------------------------------------------------------------------- #
# Process-local cache of embedder *instances* keyed by (class path,
# PipelineSettings.modified). Embedder ``__init__`` (via
# ``PipelineComponentBase``) loads component settings from the database and,
# whenever any secret is configured, decrypts them with a deliberately
# expensive PBKDF2 KDF (hundreds of thousands of HMAC iterations — see
# ``PipelineSettings._derive_key``). Re-instantiating on every embed call —
# which is exactly what query-time endpoints did (``Corpus.embed_text`` behind
# the public search API, the MCP ``search_corpus`` tool, global vector search)
# — paid that KDF + DB round-trip on every single request, which made loading
# the configured embedder "super duper slow". Caching the instance amortises
# both costs across calls. Per-call overrides still work: the cached instance's
# ``embed_text``/``embed_texts_batch`` accept ``**kwargs`` that override
# settings at call time, so the instance only pins the resolved-from-DB
# defaults, not the per-request inputs.
#
# Cross-worker coherence / invalidation: mirrors the reranker cache exactly.
# The key includes ``PipelineSettings.modified`` (auto_now), so every settings
# write through the GraphQL mutations — which all call ``save()`` — bumps the
# timestamp and busts this cache process-wide on the next lookup. The same
# issue #1410 caveat applies: code paths that bypass ``save()`` (``update``,
# ``bulk_update``, raw migrations) won't bump ``modified``; call
# :func:`invalidate_embedder_cache` explicitly in those cases.
#
# Failure handling: instantiation errors are NOT cached (the construction
# happens inside ``get_embedder_instance`` and any exception propagates without
# populating the cache), so a transient construction failure in one worker
# never pins it to a broken state while siblings succeed. Unlike the reranker
# cache, construction errors propagate rather than degrading to ``None``:
# embedding is mandatory for vector search (a ``None`` embedder would only move
# the failure to a ``NoneType.embed_text`` crash or, worse, silently skip the
# query vector), whereas reranking is an optional refinement that can be skipped.
#
# Thread-safety requirement: because one instance is shared across all threads
# in the worker, embedder implementations eligible for this cache MUST be
# thread-safe for read — ``embed_text``/``embed_texts_batch`` must not mutate
# shared instance state per call (the base merges call-time kwargs into a local
# dict, which is safe; subclasses holding mutable model/connection state must
# guard it themselves).
_EMBEDDER_INSTANCE_CACHE: dict[tuple[str, Any], BaseEmbedder] = {}
# Guards against two concurrent retrievals paying the embedder-construction
# (and PBKDF2 decryption) cost twice. Lookups after warm-up are read-only so
# no lock is needed on the hot path.
_EMBEDDER_CACHE_LOCK = threading.Lock()


def get_embedder_instance(
    embedder_class: type[BaseEmbedder],
    embedder_path: Optional[str] = None,
) -> BaseEmbedder:
    """Return a process-cached instance of ``embedder_class``.

    Construction is expensive (DB read + PBKDF2 secret decryption in
    ``PipelineComponentBase.__init__``) and was previously repeated on every
    embed call. This caches the instance keyed by ``(class_path,
    PipelineSettings.modified)`` so the cost is paid once per configuration
    per process. See the module-level comment for the invalidation contract.

    .. warning::
        The returned instance is shared across every thread in the worker.
        Embedder implementations eligible for this cache MUST be thread-safe
        for read — ``embed_text``/``embed_texts_batch`` must not mutate shared
        instance state per call. The base merges call-time kwargs into a local
        dict (safe); subclasses holding mutable model/connection state must
        guard it themselves.

    Construction failures are intentionally NOT cached: the call to
    ``embedder_class()`` happens inside the lock and any exception propagates
    to the caller without populating the cache, so a transient failure in one
    worker never pins it to a broken state. This deliberately diverges from
    the reranker cache (which degrades to ``None``) because embedding is
    mandatory for vector search — see the module-level comment.

    Args:
        embedder_class: The resolved embedder class to instantiate.
        embedder_path: The fully-qualified class path used as the cache key.
            Defaults to ``f"{embedder_class.__module__}.{embedder_class.__name__}"``.

            Caller contract: when supplied, ``embedder_path`` MUST identify
            the same class as ``embedder_class``. The cache is keyed on the
            path but stores an instance of the class, so passing a mismatched
            pair (e.g. ``get_embedder_instance(ClassA, "pkg.ClassB")``) would
            poison the cache — a later lookup for ``"pkg.ClassB"`` would get a
            ``ClassA`` instance. Both current call sites derive the path from
            the same resolution that produced the class, so they are safe; do
            not pass a synthetic / alias path.

    Returns:
        A cached (or freshly constructed) embedder instance.

    Raises:
        Exception: Propagates any exception raised by ``embedder_class()``
            construction (the failure is not cached).
    """
    class_path = (
        embedder_path or f"{embedder_class.__module__}.{embedder_class.__name__}"
    )

    cache_key = _get_pipeline_cache_key(class_path)
    cached = _EMBEDDER_INSTANCE_CACHE.get(cache_key)
    if cached is not None:
        return cached

    with _EMBEDDER_CACHE_LOCK:
        # Double-check after acquiring the lock -- another thread may have
        # populated the cache while we waited.
        cached = _EMBEDDER_INSTANCE_CACHE.get(cache_key)
        if cached is not None:
            return cached

        instance = embedder_class()
        _EMBEDDER_INSTANCE_CACHE[cache_key] = instance
        return instance


def invalidate_embedder_cache() -> None:
    """Drop cached embedder instances.

    In normal operation this is unnecessary — the cache key includes
    ``PipelineSettings.modified`` so any settings write through ``save()``
    naturally invalidates the cache on the next lookup across all workers.
    Kept for test isolation and for callers that mutate the singleton via a
    ``save()``-bypassing path (``update``/``bulk_update``/migrations).
    """
    with _EMBEDDER_CACHE_LOCK:
        _EMBEDDER_INSTANCE_CACHE.clear()
