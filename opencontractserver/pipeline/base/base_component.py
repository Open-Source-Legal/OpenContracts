import dataclasses
import logging
from abc import ABC
from collections.abc import Mapping
from typing import Any, ClassVar, Optional

from django.conf import settings

# Re-exported so callers can annotate against the duck-typing contract that
# the pipeline registry checks for, without importing the concrete base
# class.  The protocol is the canonical surface; this class is one
# implementation of it.
from opencontractserver.types.protocols import (  # noqa: F401
    PipelineComponentProtocol,
)

logger = logging.getLogger(__name__)


class PipelineComponentBase(ABC):
    """
    Base class for pipeline components, providing automatic settings injection.

    Pipeline components inheriting from this class will have settings
    automatically loaded from the PipelineSettings database singleton.

    Components should declare a nested `Settings` dataclass to define their
    configuration schema:

        from dataclasses import dataclass, field
        from opencontractserver.pipeline.base.settings_schema import (
            PipelineSetting,
            SettingType,
        )

        class MyParser(BaseParser):
            @dataclass
            class Settings:
                api_key: str = field(
                    default="",
                    metadata={"pipeline_setting": PipelineSetting(
                        setting_type=SettingType.SECRET,
                        required=True,
                        description="API key",
                        env_var="MY_PARSER_API_KEY",
                    )}
                )

    Settings are loaded once during __init__ and cached. Use reload_settings()
    to refresh settings from the database if needed.

    For backwards compatibility, components without a Settings dataclass can
    still use get_component_settings() to get a raw dictionary of settings.
    """

    # Subclasses should override this with their Settings dataclass
    Settings: ClassVar[Optional[type[Any]]] = None

    # Component metadata declared at the class level. Concrete subclasses
    # (BaseParser, BaseEmbedder, BaseThumbnailGenerator, BasePostProcessor,
    # BaseReranker) override the defaults; declaring them here gives mypy
    # a single source of truth for ``type[PipelineComponentBase]`` lookups.
    title: str = ""
    description: str = ""
    author: str = ""
    dependencies: ClassVar[list[str]] = []
    input_schema: ClassVar[Mapping] = (
        {}
    )  # If you want user to provide inputs, define a jsonschema here

    def __init__(self, **kwargs):
        """
        Initialize the PipelineComponentBase.

        Loads and validates settings from PipelineSettings database if the
        component has a Settings dataclass defined.

        Args:
            **kwargs: Passed to superclass constructors in MRO.
        """
        super().__init__()  # Ensures MRO is handled correctly
        # Cache the class path for efficient lookups
        self._full_class_path = f"{self.__class__.__module__}.{self.__class__.__name__}"
        # Load settings (will be None if no Settings dataclass)
        self._settings: Optional[Any] = self._load_settings()

    @property
    def settings(self) -> Optional[Any]:
        """
        Access the validated settings dataclass instance.

        Returns:
            An instance of the component's Settings dataclass, or None if
            the component has no Settings dataclass defined.
        """
        return self._settings

    def _load_settings(self, strict: bool = False) -> Optional[Any]:
        """
        Load and validate settings from PipelineSettings database.

        If the component has a Settings dataclass defined, this method:
        1. Fetches stored settings from PipelineSettings database
        2. Merges with defaults from the Settings dataclass
        3. Validates required fields if strict=True
        4. Returns a populated Settings dataclass instance

        Args:
            strict: If True, raise ConfigurationError for missing required settings.
                    Default is False during __init__ to allow graceful degradation.

        Returns:
            An instance of self.Settings dataclass populated with values,
            or None if the component has no Settings dataclass.

        Raises:
            ConfigurationError: If strict=True and required settings are missing.
        """
        if self.Settings is None or not dataclasses.is_dataclass(self.Settings):
            return None

        # Import here to avoid circular imports
        from opencontractserver.pipeline.base.settings_schema import (
            ConfigurationError,
            create_settings_instance,
        )

        # Get settings from database
        settings_dict = self.get_component_settings()

        try:
            return create_settings_instance(
                self.__class__,
                settings_dict,
                strict=strict,
            )
        except ConfigurationError:
            if strict:
                raise
            # Non-strict mode: log warning and return instance with defaults
            logger.warning(
                f"Component '{self._full_class_path}' has missing required settings. "
                "Using defaults where available."
            )
            return create_settings_instance(
                self.__class__,
                settings_dict,
                strict=False,
            )
        except ValueError as e:
            # No Settings dataclass (shouldn't happen since we check above)
            logger.debug(f"Could not load settings: {e}")
            return None

    def reload_settings(self, strict: bool = False) -> Optional[Any]:
        """
        Reload settings from the database.

        Call this method to refresh settings after they've been modified
        in the PipelineSettings database.

        Args:
            strict: If True, raise ConfigurationError for missing required settings.

        Returns:
            The reloaded Settings dataclass instance.
        """
        self._settings = self._load_settings(strict=strict)
        return self._settings

    def validate_settings(self) -> tuple[bool, list[str]]:
        """
        Validate this component's current settings.

        Returns:
            Tuple of (is_valid, list_of_error_messages)
        """
        if self.Settings is None:
            return True, []

        from opencontractserver.pipeline.base.settings_schema import validate_settings

        settings_dict = self.get_component_settings()
        return validate_settings(self.__class__, settings_dict)

    @classmethod
    def get_settings_schema(cls) -> dict[str, dict[str, Any]]:
        """
        Get the settings schema for this component class.

        Returns:
            Dict mapping setting names to their schema information.
            Empty dict if the component has no Settings dataclass.
        """
        from opencontractserver.pipeline.base.settings_schema import (
            get_settings_schema as extract_schema,
        )

        return extract_schema(cls)

    def get_component_settings(self) -> dict:
        """
        Get settings for this component from PipelineSettings database.

        This method fetches settings fresh on each call to support runtime
        configuration changes. Settings are retrieved from the PipelineSettings
        database model which includes encrypted secrets.

        Note: For components with a Settings dataclass, prefer using the
        `settings` property which returns a validated dataclass instance.

        Returns:
            Dict of settings for this component, including decrypted secrets.
        """
        # Ensure Django settings are configured
        if not settings.configured:
            logger.warning(
                "Django settings not configured. Component settings unavailable."
            )
            return {}

        # Get settings from PipelineSettings DB model (includes secrets)
        try:
            from opencontractserver.documents.models import PipelineSettings

            pipeline_settings = PipelineSettings.get_instance()
            # get_full_component_settings merges component_settings with secrets
            db_settings = pipeline_settings.get_full_component_settings(
                self._full_class_path
            )
            if db_settings:
                logger.debug(f"Loaded settings from DB for '{self._full_class_path}'")
                return db_settings
        except Exception as e:
            # DB not available (e.g., during migrations or early startup)
            logger.debug(f"Could not load settings from PipelineSettings DB: {e}.")

        return {}
