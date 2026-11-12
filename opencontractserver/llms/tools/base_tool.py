"""
Base class for configurable agent tools.

Provides a formal settings/secrets pattern for agent tools, mirroring the
``PipelineComponentBase`` pattern used by pipeline parsers and embedders.

Tools declare a nested ``Settings`` dataclass using ``PipelineSetting``
metadata for schema extraction, validation, and encrypted secret storage.
Settings and secrets are persisted in the ``PipelineSettings`` singleton
under a ``tool:<tool_key>`` namespace. ``SECRET`` fields are dropped from the
Settings repr when the subclass is defined (see
``settings_schema.hide_secret_settings_from_repr``).

Example::

    from dataclasses import dataclass, field
    from opencontractserver.llms.tools.base_tool import BaseTool
    from opencontractserver.pipeline.base.settings_schema import (
        PipelineSetting, SettingType,
    )

    class MySearchTool(BaseTool):
        tool_key = "my_search"

        @dataclass
        class Settings:
            api_key: str = field(
                default="",
                metadata={"pipeline_setting": PipelineSetting(
                    setting_type=SettingType.SECRET,
                    required=True,
                    description="API key for the search service",
                    env_var="MY_SEARCH_API_KEY",
                )}
            )
            provider: str = field(
                default="default_provider",
                metadata={"pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="Search provider to use",
                )}
            )
"""

from __future__ import annotations

import dataclasses
import logging
from typing import Any, ClassVar

from opencontractserver.constants.tools import TOOL_SETTINGS_PREFIX
from opencontractserver.pipeline.base.settings_schema import (
    get_required_settings,
    get_secret_settings,
    get_settings_schema,
    hide_secret_settings_from_repr,
    validate_settings_detailed,
)

logger = logging.getLogger(__name__)


class BaseTool:
    """Base class for agent tools with database-backed settings and secrets.

    Subclasses must define:
      - ``tool_key``: short identifier (stored as ``tool:<tool_key>`` in DB)
      - ``Settings``: nested dataclass with ``PipelineSetting`` metadata

    Class methods allow checking configuration state *without* instantiation,
    enabling the tool registry to skip unconfigured tools at resolution time.
    """

    #: Short key used as suffix in PipelineSettings, e.g. ``"web_search"``
    #: yields the full key ``"tool:web_search"``.
    tool_key: ClassVar[str] = ""

    #: Nested Settings dataclass — subclasses override this.
    Settings: ClassVar[type[Any] | None] = None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        hide_secret_settings_from_repr(cls.__dict__.get("Settings"))

    # ------------------------------------------------------------------
    # Full key
    # ------------------------------------------------------------------

    @classmethod
    def full_settings_key(cls) -> str:
        """Return the namespaced key used in PipelineSettings.

        E.g. ``"tool:web_search"``
        """
        if not cls.tool_key:
            raise ValueError(
                f"{cls.__name__} must define a non-empty 'tool_key' class variable."
            )
        return f"{TOOL_SETTINGS_PREFIX}{cls.tool_key}"

    # ------------------------------------------------------------------
    # Settings retrieval
    # ------------------------------------------------------------------

    @classmethod
    def get_settings(cls) -> dict[str, Any]:
        """Fetch merged settings + secrets from PipelineSettings DB.

        **Sync-only**: This method performs synchronous ORM access via
        ``PipelineSettings.get_instance()``.  It must only be called from
        synchronous contexts (e.g. ``is_configured()`` during tool
        resolution, or wrapped in ``sync_to_async`` for use inside async
        tool functions).  Calling it directly from an async context will
        raise ``SynchronousOnlyOperation``.

        Returns:
            Dict of all settings (non-sensitive merged with decrypted secrets).
            Empty dict if DB is unavailable or nothing is configured.
        """
        try:
            from opencontractserver.documents.models import PipelineSettings

            ps = PipelineSettings.get_instance()
            return ps.get_tool_settings(cls.full_settings_key())
        except Exception:
            # Log only the tool key — exception details may contain
            # connection strings or other sensitive information.
            logger.debug(
                "Could not load tool settings for '%s' (exception suppressed)",
                cls.tool_key,
            )
            return {}

    # ------------------------------------------------------------------
    # Configuration / enablement checks
    # ------------------------------------------------------------------

    @classmethod
    def is_configured(cls) -> bool:
        """Check whether all required settings (including secrets) are present.

        This is the gate used by ``_resolve_tools()`` to decide whether a
        tool backed by ``BaseTool`` should be available to agents.

        **Sync-only**: delegates to :meth:`get_settings` which performs
        synchronous ORM access.  Must not be called from an async context
        without wrapping in ``sync_to_async``.

        Returns:
            True if every setting marked ``required=True`` has a non-empty
            value in PipelineSettings; False otherwise.
        """
        if cls.Settings is None or not dataclasses.is_dataclass(cls.Settings):
            # No formal schema → always considered configured
            return True

        settings_dict = cls.get_settings()

        # Check required non-secret settings
        required = get_required_settings(cls)
        for name in required:
            val = settings_dict.get(name)
            if val is None or (isinstance(val, str) and not val.strip()):
                logger.debug(
                    "Tool '%s' not configured: missing required setting '%s'",
                    cls.tool_key,
                    name,
                )
                return False

        # Check required secret settings — values are never logged to
        # avoid leaking sensitive information.
        secret_names = get_secret_settings(cls)
        schema = get_settings_schema(cls)
        for secret_field in secret_names:
            info = schema.get(secret_field, {})
            if info.get("required", False):
                raw = settings_dict.get(secret_field)
                is_empty = raw is None or (isinstance(raw, str) and not raw.strip())
                if is_empty:
                    logger.debug(
                        "Tool '%s' not configured: a required secret is missing.",
                        cls.tool_key,
                    )
                    return False

        return True

    @classmethod
    def validate(cls) -> tuple[bool, list[str]]:
        """Validate current settings against the schema.

        Returns:
            Tuple of ``(is_valid, error_messages)``.
        """
        if cls.Settings is None or not dataclasses.is_dataclass(cls.Settings):
            return True, []

        settings_dict = cls.get_settings()
        result = validate_settings_detailed(cls, settings_dict)
        return result.is_valid, result.errors

    @classmethod
    def get_schema(cls) -> dict[str, dict[str, Any]]:
        """Return the settings schema for admin UI / introspection.

        Returns:
            Dict mapping setting names to their schema information.
        """
        return get_settings_schema(cls)
