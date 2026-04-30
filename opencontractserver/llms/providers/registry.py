"""Auto-discovering registry of :class:`BaseLLMProvider` subclasses.

Mirrors the pattern in :mod:`opencontractserver.pipeline.registry`: walks the
:mod:`opencontractserver.llms.providers` package once at first access and
caches a class-path → provider-class map. Module-level :func:`get_provider_registry`
is wrapped in :func:`functools.lru_cache` so subsequent lookups are O(1) with
no re-scan.
"""

from __future__ import annotations

import importlib
import inspect
import logging
import pkgutil
from functools import lru_cache
from typing import Optional

from opencontractserver.llms.providers.base import BaseLLMProvider

logger = logging.getLogger(__name__)


_PROVIDERS_PACKAGE = "opencontractserver.llms.providers"


class LLMProviderRegistry:
    """Lazy-discovered registry of provider classes.

    Discovery is triggered exactly once per process at construction time.
    Use the module-level :func:`get_provider_registry` rather than
    constructing this class directly so the lru_cache memoizes the
    instance.
    """

    def __init__(self) -> None:
        self._by_class_path: dict[str, type[BaseLLMProvider]] = {}
        self._discover()

    # ------------------------------------------------------------------ #
    # Discovery
    # ------------------------------------------------------------------ #

    def _discover(self) -> None:
        """Walk the providers package and register every concrete subclass.

        Mirrors ``PipelineComponentRegistry._discover_subclasses`` —
        deduplicates by class identity, skips abstract classes, and
        catches per-module import errors so one broken provider doesn't
        break discovery for the rest.
        """
        seen: set[type[BaseLLMProvider]] = set()
        try:
            package = importlib.import_module(_PROVIDERS_PACKAGE)
        except Exception as e:
            logger.error(f"Failed to import providers package: {e}")
            return

        prefix = package.__name__ + "."

        for _, modname, ispkg in pkgutil.iter_modules(package.__path__, prefix):
            if ispkg:
                continue
            # Skip the base module — it only defines the abstract class.
            if modname == f"{_PROVIDERS_PACKAGE}.base":
                continue
            try:
                module = importlib.import_module(modname)
            except Exception as e:
                logger.warning(f"Failed to import provider module {modname}: {e}")
                continue

            for _, obj in inspect.getmembers(module, inspect.isclass):
                if (
                    issubclass(obj, BaseLLMProvider)
                    and obj is not BaseLLMProvider
                    and obj not in seen
                    and not inspect.isabstract(obj)
                ):
                    seen.add(obj)
                    class_path = obj.class_path()
                    if class_path in self._by_class_path:
                        # Two classes claim the same path — surface the
                        # collision loudly rather than silently overwriting.
                        existing = self._by_class_path[class_path]
                        logger.warning(
                            "LLM provider class path collision: %s (existing %r, "
                            "new %r). Keeping existing.",
                            class_path,
                            existing,
                            obj,
                        )
                        continue
                    self._by_class_path[class_path] = obj

    # ------------------------------------------------------------------ #
    # Lookups
    # ------------------------------------------------------------------ #

    def get(self, class_path: str) -> Optional[type[BaseLLMProvider]]:
        """Return the provider class for ``class_path``, or ``None`` if
        unregistered."""
        return self._by_class_path.get(class_path)

    def all(self) -> tuple[type[BaseLLMProvider], ...]:
        """All discovered provider classes."""
        return tuple(self._by_class_path.values())

    def class_paths(self) -> tuple[str, ...]:
        """All registered provider class paths."""
        return tuple(self._by_class_path.keys())


@lru_cache(maxsize=1)
def get_provider_registry() -> LLMProviderRegistry:
    """Get the process-wide provider registry (instantiated on first call)."""
    return LLMProviderRegistry()


def reset_provider_registry_cache() -> None:
    """Clear the lru_cache; tests use this to force re-discovery."""
    get_provider_registry.cache_clear()
