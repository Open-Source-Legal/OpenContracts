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

import hashlib
import importlib
import importlib.machinery
import importlib.util
import inspect
import logging
import pkgutil
import sys
import threading
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional, TypedDict

from opencontractserver.pipeline.base.base_authority_discovery_provider import (
    BaseAuthorityDiscoveryProvider,
)
from opencontractserver.pipeline.base.base_authority_source_provider import (
    BaseAuthoritySourceProvider,
)
from opencontractserver.pipeline.base.embedder import BaseEmbedder
from opencontractserver.pipeline.base.enricher import BaseEnricher
from opencontractserver.pipeline.base.file_converter import BaseFileConverter
from opencontractserver.pipeline.base.file_types import (
    FILE_TYPE_LABELS,
    FILE_TYPE_TO_MIME,
    LEGACY_MIME_ALIASES,
    MIME_TO_FILE_TYPE,
    FileTypeEnum,
)
from opencontractserver.pipeline.base.llm_provider import BaseLLMProvider
from opencontractserver.pipeline.base.parser import BaseParser
from opencontractserver.pipeline.base.post_processor import BasePostProcessor
from opencontractserver.pipeline.base.reranker import BaseReranker
from opencontractserver.pipeline.base.thumbnailer import BaseThumbnailGenerator
from opencontractserver.types.enums import ContentModality

logger = logging.getLogger(__name__)


# The in-tree authority-pack root; each immediate subdirectory is a
# self-contained pack (``pack.yaml`` + optional ``providers/``). It ships the
# worked *example* pack only — a real body of regulation is deployment data, not
# product code, and is sideloaded. Out-of-tree packs come in two shapes:
# ``AUTHORITY_PACK_PATHS`` (individual pack directories) and
# ``AUTHORITY_PACK_ROOTS`` (directories *of* packs, for mounting a whole pack
# repository with one variable). Either way a pack brings its provider module(s)
# with it — the provider lives WITH its authority instead of in the shared
# ``pipeline/authority_source_providers/`` package.
_AUTHORITY_PACKS_ROOT = (
    Path(__file__).resolve().parents[1] / "enrichment" / "data" / "authority_packs"
)


# Root of the synthetic module namespace in-pack component modules are imported
# under. Shared across component families so a pack's own helper module is ONE
# module object however many families import it.
_PACK_MODULE_ROOT = "_authority_pack"


def _pack_namespaces(pack_dirs: list[Path]) -> dict[Path, str]:
    """Map each pack directory to a collision-free synthetic module namespace.

    The namespace is normally just the pack directory's basename, which keeps
    generated module names readable and stable. But ``authority_pack_dirs()``
    unions three independent sources (the in-tree root, every
    ``AUTHORITY_PACK_ROOTS`` bundle, every ``AUTHORITY_PACK_PATHS`` entry) and
    de-duplicates by RESOLVED PATH only — so two genuinely different packs from
    different roots may share a basename.

    Left alone they land on one namespace and ``_ensure_synthetic_package``
    re-points the first pack's package at the second pack's directory, purging
    the first pack's cached submodules. Its provider names then silently
    resolve to the OTHER pack's code, which also moves the ``__module__``-based
    host-ownership checks in ``authority_source_hosts`` onto the wrong pack.
    ``AuthorityPackService.catalog``'s duplicate check keys on the manifest
    ``name`` field, not the directory, so it does not catch this.

    Colliding directories get a short digest of their resolved path appended.
    The digest depends on the path alone, so a pack keeps the same namespace
    across ``reset_registry()`` re-discovery, and a non-colliding pack keeps
    the plain basename it has always had.
    """
    basename_counts = Counter(p.name for p in pack_dirs)
    namespaces: dict[Path, str] = {}
    for pack_dir in pack_dirs:
        if basename_counts[pack_dir.name] == 1:
            namespaces[pack_dir] = pack_dir.name
            continue
        digest = hashlib.sha256(str(pack_dir.resolve()).encode()).hexdigest()[:8]
        namespaces[pack_dir] = f"{pack_dir.name}-{digest}"
        logger.warning(
            "Authority pack directory basename %r is used by more than one pack "
            "root; importing %s under the disambiguated namespace %r. Rename one "
            "of the pack directories to silence this.",
            pack_dir.name,
            pack_dir,
            namespaces[pack_dir],
        )
    return namespaces


def _ensure_synthetic_package(name: str, paths: list[str]) -> None:
    """Register (or re-point) a synthetic package rooted at ``paths``.

    In-pack component modules are imported by file path, so without this their
    parent packages do not exist and a pack module cannot import a sibling —
    ``from ..publisher_identity import ...`` has nothing to resolve against.
    Packs that lived in-tree hid this by being importable as real packages;
    the moment one is sideloaded, that absolute path stops resolving. Creating
    the parents makes ordinary relative imports work identically in-tree and
    out, which is what "a pack is copy-to-port" requires.

    ``__path__`` is re-pointed on every call rather than skipped when the module
    already exists: ``reset_registry()`` re-runs discovery, and a test (or an
    operator) may have swapped which directory a given pack name resolves to.
    Re-pointing alone is not enough — an import resolves against
    ``sys.modules[<pkg>.<sub>]`` before it ever consults the parent's
    ``__path__``, so a helper cached from the previous directory would be handed
    back and the new pack would silently run the old pack's code. Cached
    submodules are therefore dropped whenever the path actually changes.
    """
    module = sys.modules.get(name)
    if module is None:
        spec = importlib.machinery.ModuleSpec(name, None, is_package=True)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
    elif list(getattr(module, "__path__", [])) != paths:
        prefix = name + "."
        for cached in [n for n in sys.modules if n.startswith(prefix)]:
            del sys.modules[cached]
    module.__path__ = paths


def _packs_under(root: Path) -> list[Path]:
    """Immediate subdirectories of a pack root that are packs, sorted.

    A root is scanned, not enumerated by an operator, so a subdirectory with no
    ``pack.yaml`` is an artifact of scanning rather than something anyone named
    — most often a root pointed one level too deep, at a pack, whose own
    ``charters/``/``specs/``/``personas/`` would otherwise each surface as a
    broken pack in the Authority Console.

    This applies to the in-tree root as well. The trade-off there is that a
    committed pack with a missing or unreadable ``pack.yaml`` disappears from
    the catalog instead of appearing as repairable — acceptable because an
    in-tree pack is a reviewed commit in this repository, where a malformed
    manifest is caught by the test suite rather than by an operator reading the
    Console.

    Explicit ``AUTHORITY_PACK_PATHS`` entries are deliberately NOT filtered this
    way: the operator named that directory, so a missing manifest must surface
    as an invalid pack they can repair, not vanish.
    """
    return [
        p for p in sorted(root.iterdir()) if p.is_dir() and (p / "pack.yaml").is_file()
    ]


def authority_pack_dirs() -> list[Path]:
    """Return every authority-pack directory to scan for in-pack providers.

    Union of (a) every immediate subdirectory of the in-tree
    ``enrichment/data/authority_packs/`` root, (b) every immediate subdirectory
    of each ``AUTHORITY_PACK_ROOTS`` entry (a mounted pack *bundle*), and (c)
    each path in ``AUTHORITY_PACK_PATHS`` (an individual out-of-tree pack).

    Order is deterministic (in-tree first, then roots, then explicit paths, each
    sorted) so duplicate-prefix warnings are reproducible, and the result is
    de-duplicated by resolved path: a pack reachable both through a root and
    through an explicit path would otherwise register its providers twice under
    the same generated module name. Never raises — a misconfigured setting is
    logged and skipped.
    """
    dirs: list[Path] = []
    if _AUTHORITY_PACKS_ROOT.is_dir():
        dirs.extend(_packs_under(_AUTHORITY_PACKS_ROOT))
    try:
        from django.conf import settings

        for raw in getattr(settings, "AUTHORITY_PACK_ROOTS", []) or []:
            root = Path(raw).expanduser()
            if root.is_dir():
                dirs.extend(p.resolve() for p in _packs_under(root))
            else:
                logger.warning("AUTHORITY_PACK_ROOTS entry is not a directory: %s", raw)
        for raw in getattr(settings, "AUTHORITY_PACK_PATHS", []) or []:
            p = Path(raw).expanduser()
            if p.is_dir():
                dirs.append(p.resolve())
            else:
                logger.warning("AUTHORITY_PACK_PATHS entry is not a directory: %s", raw)
    except Exception as e:  # pragma: no cover - settings always importable in app
        logger.warning("Could not read authority-pack settings: %s", e)

    seen: set[Path] = set()
    unique: list[Path] = []
    for path in dirs:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(path)
    return unique


class ComponentType(str, Enum):
    """Types of pipeline components."""

    PARSER = "parser"
    EMBEDDER = "embedder"
    THUMBNAILER = "thumbnailer"
    POST_PROCESSOR = "post_processor"
    ENRICHER = "enricher"
    RERANKER = "reranker"
    LLM_PROVIDER = "llm_provider"
    FILE_CONVERTER = "file_converter"
    AUTHORITY_SOURCE_PROVIDER = "authority_source_provider"
    AUTHORITY_DISCOVERY_PROVIDER = "authority_discovery_provider"


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
    # File converters are keyed by source-file EXTENSION (not FileTypeEnum /
    # MIME type) because they exist precisely for formats the pipeline has no
    # native support for. Empty for every other component type.
    supported_extensions: tuple[str, ...] = ()
    input_schema: dict = field(default_factory=dict)
    settings_schema: tuple[dict, ...] = field(default_factory=tuple)  # Settings schema
    vector_size: Optional[int] = None  # Only for embedders
    # Modality support (only for embedders) - stored as tuple of strings for serializability
    supported_modalities: tuple[str, ...] = ("TEXT",)
    # LLM-provider metadata (only set for ComponentType.LLM_PROVIDER entries).
    # ``provider_key`` is pydantic-ai's prefix (e.g. ``"anthropic"``).
    provider_key: Optional[str] = None
    supported_models: tuple[str, ...] = ()
    requires_api_key: bool = True
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
        # Include provider routing info for LLM providers
        if self.component_type == ComponentType.LLM_PROVIDER:
            result["provider_key"] = self.provider_key
            result["supported_models"] = list(self.supported_models)
            result["requires_api_key"] = self.requires_api_key
        # Include extension coverage for file converters
        if self.component_type == ComponentType.FILE_CONVERTER:
            result["supported_extensions"] = list(self.supported_extensions)
        return result


class PipelineComponentRegistry:
    """
    Singleton registry for all pipeline components.

    Uses lazy initialization - components are discovered on first access
    and cached for all subsequent accesses.
    """

    _instance: Optional["PipelineComponentRegistry"] = None
    _initialized: bool = False
    # Serialises construction across threads. Discovery walks the filesystem and
    # ``exec_module``s every in-pack provider, and ``_ensure_synthetic_package``
    # mutates the process-global ``sys.modules`` while it does — none of which is
    # safe to run twice concurrently. Without the lock, a second thread arriving
    # during discovery (plausible under threaded WSGI/ASGI, where ``get_registry``
    # is first touched by whichever request lands first) sails past the
    # ``_initialized`` check below and reads a registry whose component tuples
    # are still empty or not yet assigned.
    #
    # Re-entrant by design: it is an RLock, and ``_initialized`` is still set
    # BEFORE discovery, so a pack module that reaches back into ``get_registry()``
    # at import time behaves exactly as it did before (returns early rather than
    # recursing). Only cross-thread callers block.
    _lock = threading.RLock()

    def __new__(cls) -> "PipelineComponentRegistry":
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
            return cls._instance

    def __init__(self):
        with PipelineComponentRegistry._lock:
            # Only initialize once (singleton pattern)
            if PipelineComponentRegistry._initialized:
                return
            PipelineComponentRegistry._initialized = True
            self._initialize()

    def _initialize(self) -> None:
        """Build every lookup table. Called once, under ``_lock``."""

        # Initialize storage
        self._parsers: tuple[PipelineComponentDefinition, ...] = ()
        self._embedders: tuple[PipelineComponentDefinition, ...] = ()
        self._thumbnailers: tuple[PipelineComponentDefinition, ...] = ()
        self._post_processors: tuple[PipelineComponentDefinition, ...] = ()
        self._enrichers: tuple[PipelineComponentDefinition, ...] = ()
        self._rerankers: tuple[PipelineComponentDefinition, ...] = ()
        self._llm_providers: tuple[PipelineComponentDefinition, ...] = ()
        self._file_converters: tuple[PipelineComponentDefinition, ...] = ()
        self._authority_source_providers: tuple[PipelineComponentDefinition, ...] = ()
        self._authority_discovery_providers: tuple[PipelineComponentDefinition, ...] = (
            ()
        )

        # Name -> Definition lookup for fast access
        self._by_name: dict[str, PipelineComponentDefinition] = {}
        self._by_class_name: dict[str, PipelineComponentDefinition] = {}
        # Provider-key -> Definition for LLM provider routing
        self._llm_providers_by_key: dict[str, PipelineComponentDefinition] = {}

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

    def _discover_pack_component_classes(
        self, subdir_name: str, base_class: type
    ) -> list[type]:
        """Discover ``base_class`` subclasses shipped INSIDE authority packs
        (``<pack>/<subdir_name>/*.py``).

        Generalizes the "self-contained pack" discovery mechanism across every
        component family that follows the pack-directory convention — today
        ``BaseAuthoritySourceProvider`` under ``<pack>/providers/`` and
        ``BaseAuthorityDiscoveryProvider`` under ``<pack>/discovery_providers/`` —
        so a pack ships either (or both) kind of component the same way:
        discovered by the registry, no registration call, no core edit. This is
        what makes a pack self-contained: its scraper(s) live in the pack
        directory rather than in a shared core package, so copying the pack to
        another install brings them with it. The subdirectory name is part of
        the synthetic module path, so a pack shipping BOTH kinds of component
        cannot collide on the same module name.

        Each module is imported by file path under a synthetic, collision-free
        module name; an import failure is logged and skipped so a bad pack never
        crashes registry build (matching ``_discover_subclasses``' isolation).
        Only classes DEFINED in the pack module are registered — base/imported
        classes that merely happen to be in scope are ignored via the
        ``__module__`` check.
        """
        seen: set[type] = set()
        found: list[type] = []
        pack_dirs = authority_pack_dirs()
        namespaces = _pack_namespaces(pack_dirs)
        for pack_dir in pack_dirs:
            component_dir = pack_dir / subdir_name
            if not component_dir.is_dir():
                continue
            # Parents first, so a component module can import its own pack's
            # sibling modules relatively (``from ..helper import x``).
            pack_ns = f"{_PACK_MODULE_ROOT}.{namespaces[pack_dir]}"
            sub_ns = f"{pack_ns}.{subdir_name}"
            _ensure_synthetic_package(_PACK_MODULE_ROOT, [])
            _ensure_synthetic_package(pack_ns, [str(pack_dir)])
            _ensure_synthetic_package(sub_ns, [str(component_dir)])
            for py in sorted(component_dir.glob("*.py")):
                if py.name.startswith("_"):
                    continue
                mod_name = f"{sub_ns}.{py.stem}"
                try:
                    spec = importlib.util.spec_from_file_location(mod_name, py)
                    if spec is None or spec.loader is None:
                        continue
                    module = importlib.util.module_from_spec(spec)
                    # Register before exec so intra-module relative references and
                    # re-discovery (reset_registry) resolve to one module object.
                    sys.modules[mod_name] = module
                    spec.loader.exec_module(module)
                    for _, obj in inspect.getmembers(module, inspect.isclass):
                        if (
                            issubclass(obj, base_class)
                            and obj is not base_class
                            and obj not in seen
                            and not inspect.isabstract(obj)
                            and obj.__module__ == mod_name
                        ):
                            seen.add(obj)
                            found.append(obj)
                except Exception as e:
                    logger.warning("Failed to import pack provider %s: %s", py, e)
        return found

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

        # Get supported extensions (file converters only — plain strings, not
        # FileTypeEnum members, since converters target non-native formats)
        supported_extensions = tuple(
            str(ext) for ext in getattr(component_class, "supported_extensions", ())
        )

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

        # LLM-provider-specific metadata. Pulled unconditionally so the
        # dataclass receives sensible defaults for non-LLM components.
        provider_key = getattr(component_class, "provider_key", None) or None
        supported_models = tuple(getattr(component_class, "supported_models", ()) or ())
        requires_api_key = bool(getattr(component_class, "requires_api_key", True))

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
            supported_extensions=supported_extensions,
            input_schema=dict(getattr(component_class, "input_schema", {})),
            settings_schema=settings_schema,
            vector_size=vector_size,
            supported_modalities=supported_modalities,
            provider_key=provider_key,
            supported_models=supported_models,
            requires_api_key=requires_api_key,
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

        # Discover LLM providers
        llm_provider_classes = self._discover_subclasses(
            "opencontractserver.pipeline.llm_providers", BaseLLMProvider
        )
        llm_providers = []
        for cls in llm_provider_classes:
            defn = self._create_definition(cls, ComponentType.LLM_PROVIDER)
            llm_providers.append(defn)
            self._by_name[defn.name] = defn
            self._by_class_name[defn.class_name] = defn
            # Provider-key collisions would silently shadow earlier
            # registrations; warn loudly so a bad install is obvious.
            if defn.provider_key:
                if defn.provider_key in self._llm_providers_by_key:
                    existing = self._llm_providers_by_key[defn.provider_key]
                    logger.warning(
                        "Duplicate LLM provider_key %r: %s shadows %s",
                        defn.provider_key,
                        defn.class_name,
                        existing.class_name,
                    )
                self._llm_providers_by_key[defn.provider_key] = defn
            else:
                # A subclass that forgot ``provider_key`` would otherwise
                # land in the catalog but be unreachable from the
                # resolver (which keys lookups by provider prefix).  The
                # registry only logs once at startup so a louder warning
                # is justified — otherwise the failure mode is "model
                # spec X is unroutable" with no obvious cause.
                logger.warning(
                    "LLM provider %s has no provider_key — "
                    "key-based lookups will not find it; the resolver "
                    "cannot route to this provider.",
                    defn.class_name,
                )
        self._llm_providers = tuple(llm_providers)

        # Discover file converters
        file_converter_classes = self._discover_subclasses(
            "opencontractserver.pipeline.file_converters", BaseFileConverter
        )
        file_converters = []
        for cls in file_converter_classes:
            defn = self._create_definition(cls, ComponentType.FILE_CONVERTER)
            file_converters.append(defn)
            self._by_name[defn.name] = defn
            self._by_class_name[defn.class_name] = defn
        self._file_converters = tuple(file_converters)

        # Discover authority source providers: core package + in-pack providers.
        # In-pack discovery lets a self-contained pack ship its own scraper under
        # <pack>/providers/, so the provider travels with the authority.
        authority_source_provider_classes = self._discover_subclasses(
            "opencontractserver.pipeline.authority_source_providers",
            BaseAuthoritySourceProvider,
        )
        seen_classes = set(authority_source_provider_classes)
        for cls in self._discover_pack_component_classes(
            "providers", BaseAuthoritySourceProvider
        ):
            if cls not in seen_classes:
                seen_classes.add(cls)
                authority_source_provider_classes.append(cls)

        authority_source_providers = []
        prefix_owner: dict[str, str] = {}
        for cls in authority_source_provider_classes:
            defn = self._create_definition(cls, ComponentType.AUTHORITY_SOURCE_PROVIDER)
            authority_source_providers.append(defn)
            self._by_name[defn.name] = defn
            self._by_class_name[defn.class_name] = defn
            # Warn on supported_prefix collisions: AuthorityDiscoveryService.
            # _provider_for returns the FIRST can_handle match in priority order,
            # so two providers claiming the same prefix family resolve
            # non-deterministically (by priority, then discovery order) with no
            # other signal — make a shadowing install loud, mirroring the LLM
            # provider_key collision warning above.
            for pfx in getattr(cls, "supported_prefixes", ()) or ():
                if pfx in prefix_owner:
                    logger.warning(
                        "Duplicate authority-source-provider prefix %r: %s also "
                        "claims it (already owned by %s); _provider_for routing is "
                        "priority-then-discovery-order.",
                        pfx,
                        defn.class_name,
                        prefix_owner[pfx],
                    )
                else:
                    prefix_owner[pfx] = defn.class_name
        self._authority_source_providers = tuple(authority_source_providers)

        # Discover authority DISCOVERY providers: core package + in-pack providers
        # (Phase 2, issue #2054). Same mechanism as authority source providers
        # above, just a different base class + pack subdirectory
        # (<pack>/discovery_providers/) — a discovery provider lists UNCITED
        # candidates from a publisher's index page rather than resolving a known
        # canonical_key, so it is not keyed by supported_prefixes and has no
        # analogous prefix-collision warning.
        authority_discovery_provider_classes = self._discover_subclasses(
            "opencontractserver.pipeline.authority_discovery_providers",
            BaseAuthorityDiscoveryProvider,
        )
        seen_discovery_classes = set(authority_discovery_provider_classes)
        for cls in self._discover_pack_component_classes(
            "discovery_providers", BaseAuthorityDiscoveryProvider
        ):
            if cls not in seen_discovery_classes:
                seen_discovery_classes.add(cls)
                authority_discovery_provider_classes.append(cls)

        authority_discovery_providers = []
        for cls in authority_discovery_provider_classes:
            defn = self._create_definition(
                cls, ComponentType.AUTHORITY_DISCOVERY_PROVIDER
            )
            authority_discovery_providers.append(defn)
            self._by_name[defn.name] = defn
            self._by_class_name[defn.class_name] = defn
        self._authority_discovery_providers = tuple(authority_discovery_providers)

        logger.info(
            f"Pipeline registry initialized: "
            f"{len(self._parsers)} parsers, "
            f"{len(self._embedders)} embedders, "
            f"{len(self._thumbnailers)} thumbnailers, "
            f"{len(self._post_processors)} post-processors, "
            f"{len(self._enrichers)} enrichers, "
            f"{len(self._rerankers)} rerankers, "
            f"{len(self._llm_providers)} llm-providers, "
            f"{len(self._file_converters)} file-converters, "
            f"{len(self._authority_source_providers)} authority-source-providers, "
            f"{len(self._authority_discovery_providers)} authority-discovery-providers"
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

    @property
    def llm_providers(self) -> tuple[PipelineComponentDefinition, ...]:
        """Get all registered LLM providers."""
        return self._llm_providers

    @property
    def file_converters(self) -> tuple[PipelineComponentDefinition, ...]:
        """Get all registered file converters."""
        return self._file_converters

    @property
    def authority_source_providers(self) -> tuple[PipelineComponentDefinition, ...]:
        """Get all registered authority source providers."""
        return self._authority_source_providers

    @property
    def authority_discovery_providers(self) -> tuple[PipelineComponentDefinition, ...]:
        """Get all registered authority discovery providers."""
        return self._authority_discovery_providers

    def get_llm_provider_by_key(
        self, provider_key: str
    ) -> Optional[PipelineComponentDefinition]:
        """Get an LLM provider definition by its pydantic-ai prefix.

        Example: ``"anthropic"`` → the AnthropicProvider definition.
        """
        return self._llm_providers_by_key.get(provider_key)

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


def get_all_llm_providers_cached() -> tuple[PipelineComponentDefinition, ...]:
    """Get all registered LLM providers (cached)."""
    return get_registry().llm_providers


def get_all_file_converters_cached() -> tuple[PipelineComponentDefinition, ...]:
    """Get all registered file converters (cached)."""
    return get_registry().file_converters


def get_all_authority_source_providers_cached() -> (
    tuple[PipelineComponentDefinition, ...]
):
    """Get all registered authority source providers (cached)."""
    return get_registry().authority_source_providers


def get_all_authority_discovery_providers_cached() -> (
    tuple[PipelineComponentDefinition, ...]
):
    """Get all registered authority discovery providers (cached)."""
    return get_registry().authority_discovery_providers


def get_llm_provider_by_key_cached(
    provider_key: str,
) -> Optional[PipelineComponentDefinition]:
    """Get an LLM provider by its pydantic-ai prefix (cached)."""
    return get_registry().get_llm_provider_by_key(provider_key)


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
        "llm_providers": registry.llm_providers,
        "file_converters": registry.file_converters,
        "authority_source_providers": registry.authority_source_providers,
        "authority_discovery_providers": registry.authority_discovery_providers,
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
    # Same lock construction takes: tearing the singleton down while another
    # thread is mid-discovery would leave that thread publishing a registry the
    # reset was meant to discard.
    with PipelineComponentRegistry._lock:
        PipelineComponentRegistry._instance = None
        PipelineComponentRegistry._initialized = False
        get_registry.cache_clear()
        get_supported_mime_types.cache_clear()
        get_allowed_mime_types.cache_clear()
    # Installed pack paths determine both component discovery and each in-pack
    # provider's narrow manifest host ownership.
    from opencontractserver.enrichment.services.authority_source_hosts import (
        reset_source_hosts_cache,
    )

    reset_source_hosts_cache()
