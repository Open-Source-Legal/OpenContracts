"""Singleton registry that auto-discovers ``BaseLLMProvider`` subclasses.

Mirrors ``opencontractserver.pipeline.registry.PipelineComponentRegistry``: lazy
initialisation, idempotent, ~50ms first access then dict-lookup speed.
"""

from __future__ import annotations

import importlib
import inspect
import logging
import pkgutil
from typing import Optional

from opencontractserver.llms.providers.base import (
    BaseLLMProvider,
    LLMProviderDefinition,
)

logger = logging.getLogger(__name__)


class LLMProviderRegistry:
    """Singleton holding all registered LLM providers."""

    _instance: Optional["LLMProviderRegistry"] = None
    _initialized: bool = False

    def __new__(cls) -> "LLMProviderRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if LLMProviderRegistry._initialized:
            return
        LLMProviderRegistry._initialized = True

        self._providers: tuple[LLMProviderDefinition, ...] = ()
        self._by_key: dict[str, LLMProviderDefinition] = {}
        self._instances: dict[str, BaseLLMProvider] = {}

        self._discover()

    # ------------------------------------------------------------------ #
    # Discovery
    # ------------------------------------------------------------------ #

    def _discover(self) -> None:
        package_name = "opencontractserver.llms.providers"
        seen: set[type] = set()
        defs: list[LLMProviderDefinition] = []

        try:
            package = importlib.import_module(package_name)
        except Exception as exc:  # noqa: BLE001
            logger.error("LLMProviderRegistry: failed to import %s: %s", package_name, exc)
            return

        for _, modname, ispkg in pkgutil.iter_modules(
            package.__path__, package.__name__ + "."
        ):
            if ispkg or modname.endswith((".base", ".registry")):
                continue
            try:
                module = importlib.import_module(modname)
            except Exception as exc:  # noqa: BLE001
                logger.warning("LLMProviderRegistry: failed to import %s: %s", modname, exc)
                continue

            for _, obj in inspect.getmembers(module, inspect.isclass):
                if (
                    issubclass(obj, BaseLLMProvider)
                    and obj is not BaseLLMProvider
                    and obj not in seen
                    and not inspect.isabstract(obj)
                    and obj.key  # require a non-empty key to be registered
                ):
                    seen.add(obj)
                    defn = obj.to_definition()
                    if defn.key in self._by_key:
                        logger.warning(
                            "LLMProviderRegistry: duplicate provider key '%s' "
                            "(class %s shadows %s)",
                            defn.key,
                            obj,
                            self._by_key[defn.key].provider_class,
                        )
                        continue
                    defs.append(defn)
                    self._by_key[defn.key] = defn
                    self._instances[defn.key] = obj()

        self._providers = tuple(defs)
        logger.info(
            "LLMProviderRegistry initialized: %d providers (%s)",
            len(self._providers),
            ", ".join(d.key for d in self._providers),
        )

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    @property
    def providers(self) -> tuple[LLMProviderDefinition, ...]:
        return self._providers

    def get(self, key: str) -> Optional[LLMProviderDefinition]:
        return self._by_key.get(key)

    def get_instance(self, key: str) -> Optional[BaseLLMProvider]:
        return self._instances.get(key)

    def keys(self) -> list[str]:
        return [d.key for d in self._providers]

    @classmethod
    def reset(cls) -> None:
        """Test-only: drop the cached singleton so re-imports are picked up."""
        cls._instance = None
        cls._initialized = False


def get_provider_registry() -> LLMProviderRegistry:
    return LLMProviderRegistry()


def get_provider(key: str) -> Optional[LLMProviderDefinition]:
    return get_provider_registry().get(key)
