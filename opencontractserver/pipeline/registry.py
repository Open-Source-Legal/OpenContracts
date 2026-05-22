"""
Central registry of all pipeline components with lazy initialization.

This module provides an efficient, cached registry of pipeline components
(parsers, embedders, thumbnailers, post-processors) that:
1. Auto-discovers components on first access (no manual registration needed)
2. Caches the registry at module level for zero-overhead subsequent access
3. Exposes fast lookup functions similar to the tool_registry pattern

Performance:
- First access: ~50-100ms (module scanning)
- Subsequent accesses: ~0ms (cached dict lookup)
"""

import importlib
import inspect
import logging
import pkgutil
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from typing import Any, Optional, TypedDict

from opencontractserver.pipeline.base.embedder import BaseEmbedder
from opencontractserver.pipeline.base.enricher import BaseEnricher
from opencontractserver.pipeline.base.file_types import (
    FILE_TYPE_LABELS,
    FILE_TYPE_TO_MIME,
    LEGACY_MIME_ALIASES,
    MIME_TO_FILE_TYPE,
    FileTypeEnum,
)
from opencontractserver.pipeline.base.parser import BaseParser
from opencontractserver.pipeline.base.post_processor import BasePostProcessor
from opencontractserver.pipeline.base.reranker import BaseReranker
from opencontractserver.pipeline.base.thumbnailer import BaseThumbnailGenerator
from opencontractserver.types.enums import ContentModality

logger = logging.getLogger(__name__)


class ComponentType(str, Enum):
    """Types of pipeline components."""

    PARSER = "parser"
    EMBEDDER = "embedder"
    THUMBNAILER = "thumbnailer"
    POST_PROCESSOR = "post_processor"
    ENRICHER = "enricher"
    RERANKER = "reranker"


@dataclass(frozen=True)
class PipelineComponentDefinition:
    """
    Immutable definition of a pipeline component for fast registry access.

    This captures the component's metadata at registration time, avoiding
    repeated attribute lookups on the class.
    """

    name: str
    class_name: str  # Full module.ClassName path
    component_type: ComponentType
    title: str
    module_name: str
    description: str
    author: str
    dependencies: tuple[str, ...]
    supported_file_types: tuple[str, ...]  # FileTypeEnum values as strings
    input_schema: dict = field(default_factory=dict)
    settings_schema: tuple[dict, ...] = field(default_factory=tuple)  # Settings schema
    vector_size: Optional[int] = None  # Only for embedders
    # Modality support (only for embedders) - stored as tuple of strings for serializability
    supported_modalities: tuple[str, ...] = ("TEXT",)
    component_class: Optional[type] = field(
        default=None, compare=False, hash=False
    )  # Reference to actual class

    # Convenience properties derived from supported_modalities
    @property
    def is_multimodal(self) -> bool:
        """Whether this embedder supports multiple modalities."""
        return len(self.supported_modalities) > 1

    @property
    def supports_text(self) -> bool:
        """Whether this embedder supports text input."""
        return "TEXT" in self.supported_modalities

    @property
    def supports_images(self) -> bool:
        """Whether this embedder supports image input."""
        return "IMAGE" in self.supported_modalities

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for GraphQL response."""
        result: dict[str, Any] = {
            "name": self.name,
            "class_name": self.class_name,
            "component_type": self.component_type.value,
            "title": self.title,
            "module_name": self.module_name,
            "description": self.description,
            "author": self.author,
            "dependencies": list(self.dependencies),
            "supported_file_types": list(self.supported_file_types),
            "input_schema": self.input_schema,
            "settings_schema": list(self.settings_schema),
        }
        if self.vector_size is not None:
            result["vector_size"] = self.vector_size
        # Include modality info for embedders
        if self.component_type == ComponentType.EMBEDDER:
            result["supported_modalities"] = list(self.supported_modalities)
            # Convenience fields derived from supported_modalities
            result["is_multimodal"] = self.is_multimodal
            result["supports_text"] = self.supports_text
            result["supports_images"] = self.supports_images
        return result


class PipelineComponentRegistry:
    """
    Singleton registry for all pipeline components.

    Uses lazy initialization - components are discovered on first access
    and cached for all subsequent accesses.
    """

    _instance: Optional["PipelineComponentRegistry"] = None
    _initialized: bool = False

    def __new__(cls) -> "PipelineComponentRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        # Only initialize once (singleton pattern)
        if PipelineComponentRegistry._initialized:
            return
        PipelineComponentRegistry._initialized = True

        # Initialize storage
        self._parsers: tuple[PipelineComponentDefinition, ...] = ()
        self._embedders: tuple[PipelineComponentDefinition, ...] = ()
        self._thumbnailers: tuple[PipelineComponentDefinition, ...] = ()
        self._post_processors: tuple[PipelineComponentDefinition, ...] = ()
        self._enrichers: tuple[PipelineComponentDefinition, ...] = ()
        self._rerankers: tuple[PipelineComponentDefinition, ...] = ()

        # Name -> Definition lookup for fast access
        self._by_name: dict[str, PipelineComponentDefinition] = {}
        self._by_class_name: dict[str, PipelineComponentDefinition] = {}

        # File type -> Components lookup for filtering
        self._parsers_by_filetype: dict[str, list[PipelineComponentDefinition]] = {}
        self._thumbnailers_by_filetype: dict[str, list[PipelineComponentDefinition]] = (
            {}
        )
        self._post_processors_by_filetype: dict[
            str, list[PipelineComponentDefinition]
        ] = {}
        self._enrichers_by_filetype: dict[str, list[PipelineComponentDefinition]] = {}

        # Perform discovery
        self._discover_all_components()

    def _discover_subclasses(self, module_name: str, base_class: type) -> list[type]:
        """
        Discover all concrete subclasses of base_class in the given module package.

        This is called ONCE during initialization. Deduplicates by class identity
        so that module-level aliases (e.g. ``Alias = RealClass``) don't cause
        the same class to appear twice.  Abstract intermediate base classes are
        also skipped — only concrete (instantiable) components are registered.

        Note: inspect.isabstract() returns True only when a class has unimplemented
        abstract methods.  An intermediate base class that accidentally implements
        all parent abstract methods (while intending to remain abstract) will pass
        through this filter.  If you add intermediate bases, mark them with ABC and
        leave at least one @abstractmethod unimplemented, or add a dedicated
        ``_is_abstract = True`` sentinel checked here.
        """
        seen: set[type] = set()
        subclasses: list[type] = []
        try:
            package = importlib.import_module(module_name)
            prefix = package.__name__ + "."

            for _, modname, ispkg in pkgutil.iter_modules(package.__path__, prefix):
                if not ispkg:
                    try:
                        module = importlib.import_module(modname)
                        for name, obj in inspect.getmembers(module, inspect.isclass):
                            if (
                                issubclass(obj, base_class)
                                and obj is not base_class
                                and obj not in seen
                                and not inspect.isabstract(obj)
                            ):
                                seen.add(obj)
                                subclasses.append(obj)
                    except Exception as e:
                        logger.warning(f"Failed to import {modname}: {e}")
        except Exception as e:
            logger.error(f"Failed to discover components in {module_name}: {e}")

        return subclasses

    def _get_class_or_instance_attr(
        self, component_class: type, attr_name: str, default: Any = None
    ) -> Any:
        """
        Get an attribute from a class, handling @property correctly.

        When an attribute is defined as a @property, getattr on the class
        returns the property descriptor, not the value. This method detects
        properties and instantiates the class to get the actual value.

        Args:
            component_class: The class to get the attribute from.
            attr_name: Name of the attribute.
            default: Default value if attribute doesn't exist.

        Returns:
            The attribute value (from class or instance if property).
        """
        attr = getattr(component_class, attr_name, default)

        # Check if it's a property descriptor - if so, instantiate to get value
        if isinstance(attr, property):
            try:
                instance = component_class()
                return getattr(instance, attr_name, default)
            except Exception as e:
                logger.warning(
                    f"Failed to instantiate {component_class.__name__} "
                    f"to get property '{attr_name}': {e}"
                )
                return default

        return attr

    def _create_definition(
        self, component_class: type, component_type: ComponentType
    ) -> PipelineComponentDefinition:
        """Create a PipelineComponentDefinition from a component class."""
        module_name = component_class.__module__.split(".")[-1]

        # Get supported file types, filtering to valid FileTypeEnum members
        # Store as the enum value (e.g., "pdf") for consistency
        supported_file_types = []
        if hasattr(component_class, "supported_file_types"):
            for ft in component_class.supported_file_types:
                if isinstance(ft, FileTypeEnum):
                    supported_file_types.append(ft.value)

        # Get supported modalities (for embedders)
        # Convert from set of ContentModality enums to tuple of strings
        raw_modalities = getattr(
            component_class, "supported_modalities", {ContentModality.TEXT}
        )
        if isinstance(raw_modalities, set):
            # New format: set of ContentModality enums
            supported_modalities = tuple(m.value for m in raw_modalities)
        else:
            # Fallback for any unexpected format
            supported_modalities = ("TEXT",)

        # Get vector_size - handles both class attributes and @property
        vector_size = self._get_class_or_instance_attr(
            component_class, "vector_size", None
        )

        # Extract settings schema if the component has a Settings dataclass
        settings_schema: tuple[dict, ...] = ()
        try:
            from opencontractserver.pipeline.base.settings_schema import (
                get_settings_schema,
            )

            schema_dict = get_settings_schema(component_class)
            if schema_dict:
                # Convert schema dict to list of dicts for GraphQL
                settings_schema = tuple(
                    {"name": name, **info} for name, info in schema_dict.items()
                )
        except Exception as e:
            logger.debug(
                f"Could not extract settings schema for {component_class}: {e}"
            )

        # Build definition
        definition = PipelineComponentDefinition(
            name=component_class.__name__,
            class_name=f"{component_class.__module__}.{component_class.__name__}",
            component_type=component_type,
            title=getattr(component_class, "title", ""),
            module_name=module_name,
            description=getattr(component_class, "description", ""),
            author=getattr(component_class, "author", ""),
            dependencies=tuple(getattr(component_class, "dependencies", [])),
            supported_file_types=tuple(supported_file_types),
            input_schema=dict(getattr(component_class, "input_schema", {})),
            settings_schema=settings_schema,
            vector_size=vector_size,
            supported_modalities=supported_modalities,
            component_class=component_class,
        )

        return definition

    def _discover_all_components(self) -> None:
        """
        Discover and register all pipeline components.

        Called once during singleton initialization.
        """
        logger.info("Initializing pipeline component registry...")

        # Discover parsers
        parser_classes = self._discover_subclasses(
            "opencontractserver.pipeline.parsers", BaseParser
        )
        parsers = []
        for cls in parser_classes:
            defn = self._create_definition(cls, ComponentType.PARSER)
            parsers.append(defn)
            self._by_name[defn.name] = defn
            self._by_class_name[defn.class_name] = defn
            for ft in defn.supported_file_types:
                self._parsers_by_filetype.setdefault(ft, []).append(defn)
        self._parsers = tuple(parsers)

        # Discover embedders
        embedder_classes = self._discover_subclasses(
            "opencontractserver.pipeline.embedders", BaseEmbedder
        )
        embedders = []
        for cls in embedder_classes:
            defn = self._create_definition(cls, ComponentType.EMBEDDER)
            embedders.append(defn)
            self._by_name[defn.name] = defn
            self._by_class_name[defn.class_name] = defn
        self._embedders = tuple(embedders)

        # Discover thumbnailers
        thumbnailer_classes = self._discover_subclasses(
            "opencontractserver.pipeline.thumbnailers", BaseThumbnailGenerator
        )
        thumbnailers = []
        for cls in thumbnailer_classes:
            defn = self._create_definition(cls, ComponentType.THUMBNAILER)
            thumbnailers.append(defn)
            self._by_name[defn.name] = defn
            self._by_class_name[defn.class_name] = defn
            for ft in defn.supported_file_types:
                self._thumbnailers_by_filetype.setdefault(ft, []).append(defn)
        self._thumbnailers = tuple(thumbnailers)

        # Discover post-processors
        post_processor_classes = self._discover_subclasses(
            "opencontractserver.pipeline.post_processors", BasePostProcessor
        )
        post_processors = []
        for cls in post_processor_classes:
            defn = self._create_definition(cls, ComponentType.POST_PROCESSOR)
            post_processors.append(defn)
            self._by_name[defn.name] = defn
            self._by_class_name[defn.class_name] = defn
            for ft in defn.supported_file_types:
                self._post_processors_by_filetype.setdefault(ft, []).append(defn)
        self._post_processors = tuple(post_processors)

        # Discover enrichers
        enricher_classes = self._discover_subclasses(
            "opencontractserver.pipeline.enrichers", BaseEnricher
        )
        enrichers = []
        for cls in enricher_classes:
            defn = self._create_definition(cls, ComponentType.ENRICHER)
            enrichers.append(defn)
            self._by_name[defn.name] = defn
            self._by_class_name[defn.class_name] = defn
            for ft in defn.supported_file_types:
                self._enrichers_by_filetype.setdefault(ft, []).append(defn)
        self._enrichers = tuple(enrichers)

        # Discover rerankers
        reranker_classes = self._discover_subclasses(
            "opencontractserver.pipeline.rerankers", BaseReranker
        )
        rerankers = []
        for cls in reranker_classes:
            defn = self._create_definition(cls, ComponentType.RERANKER)
            rerankers.append(defn)
            self._by_name[defn.name] = defn
            self._by_class_name[defn.class_name] = defn
        self._rerankers = tuple(rerankers)

        logger.info(
            f"Pipeline registry initialized: "
            f"{len(self._parsers)} parsers, "
            f"{len(self._embedders)} embedders, "
            f"{len(self._thumbnailers)} thumbnailers, "
            f"{len(self._post_processors)} post-processors, "
            f"{len(self._enrichers)} enrichers, "
            f"{len(self._rerankers)} rerankers"
        )

    # -------------------------------------------------------------------------
    # PUBLIC API - Fast cached access
    # -------------------------------------------------------------------------

    @property
    def parsers(self) -> tuple[PipelineComponentDefinition, ...]:
        """Get all registered parsers."""
        return self._parsers

    @property
    def embedders(self) -> tuple[PipelineComponentDefinition, ...]:
        """Get all registered embedders."""
        return self._embedders

    @property
    def thumbnailers(self) -> tuple[PipelineComponentDefinition, ...]:
        """Get all registered thumbnailers."""
        return self._thumbnailers

    @property
    def post_processors(self) -> tuple[PipelineComponentDefinition, ...]:
        """Get all registered post-processors."""
        return self._post_processors

    @property
    def enrichers(self) -> tuple[PipelineComponentDefinition, ...]:
        """Get all registered enrichers."""
        return self._enrichers

    @property
    def rerankers(self) -> tuple[PipelineComponentDefinition, ...]:
        """Get all registered rerankers."""
        return self._rerankers

    def get_by_name(self, name: str) -> Optional[PipelineComponentDefinition]:
        """Get a component definition by class name (e.g., 'DoclingParser')."""
        return self._by_name.get(name)

    def get_by_class_name(
        self, class_name: str
    ) -> Optional[PipelineComponentDefinition]:
        """
        Get a component by full class path.

        E.g., 'opencontractserver.pipeline.parsers.docling_parser_rest.DoclingParser'
        """
        return self._by_class_name.get(class_name)

    def get_parsers_for_filetype(
        self, file_type: str
    ) -> list[PipelineComponentDefinition]:
        """Get parsers compatible with a file type (e.g., 'application/pdf')."""
        return self._parsers_by_filetype.get(file_type, [])

    def get_thumbnailers_for_filetype(
        self, file_type: str
    ) -> list[PipelineComponentDefinition]:
        """Get thumbnailers compatible with a file type."""
        return self._thumbnailers_by_filetype.get(file_type, [])

    def get_post_processors_for_filetype(
        self, file_type: str
    ) -> list[PipelineComponentDefinition]:
        """Get post-processors compatible with a file type."""
        return self._post_processors_by_filetype.get(file_type, [])

    def get_enrichers_for_filetype(
        self, file_type: str
    ) -> list[PipelineComponentDefinition]:
        """Get enrichers compatible with a file type."""
        return self._enrichers_by_filetype.get(file_type, [])


# =============================================================================
# MODULE-LEVEL CONVENIENCE FUNCTIONS
# =============================================================================


# Lazy singleton access
@lru_cache(maxsize=1)
def get_registry() -> PipelineComponentRegistry:
    """
    Get the singleton pipeline component registry.

    The registry is initialized on first access and cached permanently.
    """
    return PipelineComponentRegistry()


def get_all_parsers_cached() -> tuple[PipelineComponentDefinition, ...]:
    """Get all registered parsers (cached)."""
    return get_registry().parsers


def get_all_embedders_cached() -> tuple[PipelineComponentDefinition, ...]:
    """Get all registered embedders (cached)."""
    return get_registry().embedders


def get_all_thumbnailers_cached() -> tuple[PipelineComponentDefinition, ...]:
    """Get all registered thumbnailers (cached)."""
    return get_registry().thumbnailers


def get_all_post_processors_cached() -> tuple[PipelineComponentDefinition, ...]:
    """Get all registered post-processors (cached)."""
    return get_registry().post_processors


def get_all_enrichers_cached() -> tuple[PipelineComponentDefinition, ...]:
    """Get all registered enrichers (cached)."""
    return get_registry().enrichers


def get_all_rerankers_cached() -> tuple[PipelineComponentDefinition, ...]:
    """Get all registered rerankers (cached)."""
    return get_registry().rerankers


def get_component_by_name_cached(name: str) -> Optional[PipelineComponentDefinition]:
    """Get a component definition by name (cached)."""
    return get_registry().get_by_name(name)


def get_components_by_mimetype_cached(
    mimetype: str,
) -> dict[str, list[PipelineComponentDefinition]]:
    """
    Get all components compatible with a MIME type (cached).

    Args:
        mimetype: MIME type string (e.g., "application/pdf")

    Returns dict with keys: parsers, embedders, thumbnailers, post_processors,
    enrichers, rerankers
    """
    registry = get_registry()

    # Convert MIME type to FileTypeEnum value for lookup
    file_type_value = MIME_TO_FILE_TYPE.get(mimetype)
    if file_type_value is None:
        logger.warning("Unknown MIME type %r — no FileTypeEnum mapping", mimetype)
        return {
            "parsers": [],
            "embedders": [],
            "thumbnailers": [],
            "post_processors": [],
            "enrichers": [],
        }

    return {
        "parsers": registry.get_parsers_for_filetype(file_type_value),
        "embedders": list(registry.embedders),  # Embedders work on all text
        "thumbnailers": registry.get_thumbnailers_for_filetype(file_type_value),
        "post_processors": registry.get_post_processors_for_filetype(file_type_value),
        "enrichers": registry.get_enrichers_for_filetype(file_type_value),
        "rerankers": list(registry.rerankers),  # Rerankers work on all text
    }


def get_all_components_cached() -> dict[str, tuple[PipelineComponentDefinition, ...]]:
    """
    Get all components grouped by type (cached).

    Returns dict with keys: parsers, embedders, thumbnailers, post_processors,
    enrichers, rerankers
    """
    registry = get_registry()
    return {
        "parsers": registry.parsers,
        "embedders": registry.embedders,
        "thumbnailers": registry.thumbnailers,
        "post_processors": registry.post_processors,
        "enrichers": registry.enrichers,
        "rerankers": registry.rerankers,
    }


class StageCoverage(TypedDict):
    parser: bool
    embedder: bool
    thumbnailer: bool


class SupportedMimeTypeEntry(TypedDict):
    mimetype: str
    file_type: str
    label: str
    fully_supported: bool
    stage_coverage: StageCoverage


@lru_cache(maxsize=None)
def get_supported_mime_types() -> tuple[SupportedMimeTypeEntry, ...]:
    """
    Derive supported MIME types dynamically from registered pipeline components.

    A file type is "fully supported" if at least one registered component exists
    for each required pipeline stage: parser and embedder. Thumbnailer coverage
    is informational but not required for upload acceptance.

    Thread-safe via @lru_cache. Cleared by reset_registry().

    Returns a tuple of dicts, each containing:
        - mimetype: canonical MIME type string
        - file_type: short label (e.g. "pdf")
        - label: human-readable label (e.g. "PDF")
        - fully_supported: True if all required stages have at least one component
        - stage_coverage: dict of stage -> bool indicating availability
    """
    registry = get_registry()
    result: list[SupportedMimeTypeEntry] = []

    for ft_enum in FileTypeEnum:
        ft_value = ft_enum.value
        mime = FILE_TYPE_TO_MIME.get(ft_value)
        if not mime:
            logger.warning("No MIME mapping for FileTypeEnum member %r", ft_value)
            continue

        has_parser = len(registry.get_parsers_for_filetype(ft_value)) > 0
        # TODO: Embedders currently work on all text types (not filtered
        # by file type). If a file-type-specific embedder is added, update this
        # check to query per-file-type coverage. Until then, has_embedder is
        # True whenever *any* embedder is registered.
        has_any_embedder = len(registry.embedders) > 0
        has_thumbnailer = len(registry.get_thumbnailers_for_filetype(ft_value)) > 0

        stage_coverage: StageCoverage = {
            "parser": has_parser,
            "embedder": has_any_embedder,
            "thumbnailer": has_thumbnailer,
        }

        result.append(
            {
                "mimetype": mime,
                "file_type": ft_value,
                "label": FILE_TYPE_LABELS.get(ft_value, ft_value.upper()),
                "fully_supported": has_parser and has_any_embedder,
                "stage_coverage": stage_coverage,
            }
        )

    return tuple(result)


@lru_cache(maxsize=None)
def get_allowed_mime_types() -> tuple[str, ...]:
    """
    Return the MIME types that are fully supported by the pipeline.

    This replaces the static settings.ALLOWED_DOCUMENT_MIMETYPES with a
    dynamically-derived list based on registered pipeline components.
    Includes legacy MIME type aliases for backward compatibility.

    Falls back to settings.ALLOWED_DOCUMENT_MIMETYPES when no components are
    registered (fresh install, import-time failures, certain test configs).

    Thread-safe via @lru_cache. Cleared by reset_registry().
    """
    from django.conf import settings

    supported = get_supported_mime_types()
    allowed = [entry["mimetype"] for entry in supported if entry["fully_supported"]]

    # Add legacy aliases that map to supported types
    for legacy, canonical in LEGACY_MIME_ALIASES.items():
        if canonical in allowed and legacy not in allowed:
            allowed.append(legacy)

    if not allowed:
        fallback = getattr(settings, "ALLOWED_DOCUMENT_MIMETYPES", [])
        if fallback:
            logger.warning(
                "No pipeline components registered — falling back to "
                "settings.ALLOWED_DOCUMENT_MIMETYPES (%d types). This may "
                "indicate a component import failure or misconfiguration.",
                len(fallback),
            )
            return tuple(fallback)
        logger.warning(
            "No pipeline components registered and no "
            "settings.ALLOWED_DOCUMENT_MIMETYPES fallback — all uploads "
            "will be rejected."
        )

    return tuple(allowed)


def reset_registry() -> None:
    """
    Reset the registry singleton.

    Useful for testing or if components are dynamically added.
    """
    PipelineComponentRegistry._instance = None
    PipelineComponentRegistry._initialized = False
    get_registry.cache_clear()
    get_supported_mime_types.cache_clear()
    get_allowed_mime_types.cache_clear()
