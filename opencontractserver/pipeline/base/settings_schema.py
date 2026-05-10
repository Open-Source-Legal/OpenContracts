"""
Settings schema types and utilities for pipeline components.

This module provides a formal schema system for declaring component configuration
requirements. Components declare a nested `Settings` dataclass that specifies
all configuration options with their types, defaults, descriptions, and whether
they are required/optional/secret.

Example usage in a component:

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
                    description="API key for the service",
                    env_var="MY_PARSER_API_KEY",
                )}
            )
            timeout: int = field(
                default=30,
                metadata={"pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="Request timeout in seconds",
                )}
            )
"""

import dataclasses
import logging
from dataclasses import dataclass, fields
from enum import Enum
from typing import Any, Callable, Optional, get_type_hints

logger = logging.getLogger(__name__)


class SettingType(str, Enum):
    """Type classification for pipeline component settings."""

    REQUIRED = "required"  # Must have value, no usable default
    OPTIONAL = "optional"  # Has default, can be overridden
    SECRET = "secret"  # Encrypted storage, marked sensitive (API keys, tokens)


@dataclass(frozen=True)
class PipelineSetting:
    """
    Metadata for a component setting field.

    This is attached to dataclass fields via the `metadata` parameter to
    provide additional information about the setting for schema extraction,
    validation, and migration.

    Attributes:
        setting_type: Classification (required, optional, or secret)
        required: Whether a non-empty value is required for the component to function
        description: Human-readable description for admin UI
        env_var: Django setting name used to seed initial value during migration
        validation: Optional callable to validate the setting value
    """

    setting_type: SettingType
    required: bool = False
    description: str = ""
    env_var: Optional[str] = None
    validation: Optional[Callable[[Any], bool]] = None

    def __post_init__(self) -> None:
        """Auto-set required=True for SECRET type if not explicitly set."""
        # Note: Can't modify frozen dataclass in __post_init__
        # The required logic is handled in the extraction instead
        pass


class ConfigurationError(Exception):
    """Raised when a component has invalid or missing configuration."""

    def __init__(
        self, component_path: str, missing_settings: list[str], message: str = ""
    ):
        self.component_path = component_path
        self.missing_settings = missing_settings
        if not message:
            message = (
                f"Component '{component_path}' is missing required settings: "
                f"{', '.join(missing_settings)}"
            )
        super().__init__(message)


def get_pipeline_setting(field_obj: dataclasses.Field) -> Optional[PipelineSetting]:
    """
    Extract PipelineSetting metadata from a dataclass field.

    Args:
        field_obj: A dataclass Field object

    Returns:
        PipelineSetting if present in metadata, None otherwise
    """
    if not field_obj.metadata:
        return None
    return field_obj.metadata.get("pipeline_setting")


def get_settings_schema(component_class: type) -> dict[str, dict[str, Any]]:
    """
    Extract settings schema from a component's Settings dataclass.

    Scans the component class for a nested `Settings` dataclass and extracts
    all fields with their PipelineSetting metadata.

    Args:
        component_class: A pipeline component class (parser, embedder, etc.)

    Returns:
        Dict mapping setting names to their schema:
        {
            "api_key": {
                "type": "secret",
                "required": True,
                "default": "",
                "description": "API key for the service",
                "env_var": "MY_PARSER_API_KEY",
                "python_type": "str",
            },
            ...
        }

    Returns empty dict if the component has no Settings dataclass.
    """
    settings_class = getattr(component_class, "Settings", None)
    if not isinstance(settings_class, type) or not dataclasses.is_dataclass(
        settings_class
    ):
        return {}

    schema: dict[str, dict[str, Any]] = {}

    # Get type hints for proper type representation
    try:
        type_hints = get_type_hints(settings_class)
    except Exception:
        type_hints = {}

    for field_obj in fields(settings_class):
        setting_info = get_pipeline_setting(field_obj)

        # Build schema entry even if no PipelineSetting metadata
        # (treat as optional with just the default)
        entry: dict[str, Any] = {
            "name": field_obj.name,
            "python_type": _get_type_name(type_hints.get(field_obj.name, Any)),
        }

        # Add default value if present
        if field_obj.default is not dataclasses.MISSING:
            entry["default"] = field_obj.default
        elif field_obj.default_factory is not dataclasses.MISSING:
            try:
                entry["default"] = field_obj.default_factory()
            except Exception:
                entry["default"] = None

        if setting_info:
            entry["type"] = setting_info.setting_type.value
            entry["required"] = setting_info.required
            entry["description"] = setting_info.description
            if setting_info.env_var:
                entry["env_var"] = setting_info.env_var
            entry["has_validation"] = setting_info.validation is not None
        else:
            # Default to optional if no metadata
            entry["type"] = SettingType.OPTIONAL.value
            entry["required"] = False
            entry["description"] = ""

        schema[field_obj.name] = entry

    return schema


def get_all_env_vars(component_class: type) -> dict[str, str]:
    """
    Get all env_var mappings from a component's Settings schema.

    Args:
        component_class: A pipeline component class

    Returns:
        Dict mapping setting names to their env_var names:
        {"api_key": "MY_PARSER_API_KEY", ...}
    """
    schema = get_settings_schema(component_class)
    return {
        name: info["env_var"] for name, info in schema.items() if info.get("env_var")
    }


def get_required_settings(component_class: type) -> list[str]:
    """
    Get list of required setting names for a component.

    Args:
        component_class: A pipeline component class

    Returns:
        List of setting names that are marked as required
    """
    schema = get_settings_schema(component_class)
    return [name for name, info in schema.items() if info.get("required")]


def get_secret_settings(component_class: type) -> list[str]:
    """
    Get list of secret setting names for a component.

    Args:
        component_class: A pipeline component class

    Returns:
        List of setting names that are marked as secret
    """
    schema = get_settings_schema(component_class)
    return [
        name
        for name, info in schema.items()
        if info.get("type") == SettingType.SECRET.value
    ]


@dataclass
class ValidationResult:
    """Result of settings validation with structured error information."""

    is_valid: bool
    errors: list[str]
    missing_required: list[str]
    validation_failures: list[str]


def validate_settings(
    component_class: type,
    settings_dict: dict[str, Any],
) -> tuple[bool, list[str]]:
    """
    Validate a settings dictionary against a component's schema.

    Args:
        component_class: A pipeline component class
        settings_dict: Dict of setting name -> value

    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    result = validate_settings_detailed(component_class, settings_dict)
    return result.is_valid, result.errors


def validate_settings_detailed(
    component_class: type,
    settings_dict: dict[str, Any],
) -> ValidationResult:
    """
    Validate a settings dictionary against a component's schema with detailed results.

    Args:
        component_class: A pipeline component class
        settings_dict: Dict of setting name -> value

    Returns:
        ValidationResult with structured error information
    """
    schema = get_settings_schema(component_class)
    errors: list[str] = []
    missing_required: list[str] = []
    validation_failures: list[str] = []

    for name, info in schema.items():
        # Skip secret fields — they are stored/validated separately
        if info.get("type") == SettingType.SECRET.value:
            continue

        value = settings_dict.get(name)

        # Check required settings
        if info.get("required"):
            if value is None or (isinstance(value, str) and not value.strip()):
                missing_required.append(name)
                errors.append(f"Required setting '{name}' is missing or empty")
                continue

        # Run custom validation if present and value exists
        settings_class = getattr(component_class, "Settings", None)
        if settings_class and value is not None:
            for field_obj in fields(settings_class):
                if field_obj.name == name:
                    setting_info = get_pipeline_setting(field_obj)
                    if setting_info and setting_info.validation:
                        try:
                            if not setting_info.validation(value):
                                validation_failures.append(name)
                                errors.append(f"Setting '{name}' failed validation")
                        except Exception as e:
                            validation_failures.append(name)
                            errors.append(f"Setting '{name}' validation error: {e}")
                    break

    return ValidationResult(
        is_valid=len(errors) == 0,
        errors=errors,
        missing_required=missing_required,
        validation_failures=validation_failures,
    )


def create_settings_instance(
    component_class: type,
    settings_dict: dict[str, Any],
    strict: bool = True,
) -> Any:
    """
    Create a Settings dataclass instance from a dictionary.

    Args:
        component_class: A pipeline component class with Settings dataclass
        settings_dict: Dict of setting name -> value (from PipelineSettings database)
        strict: If True, raise ConfigurationError for missing required settings

    Returns:
        An instance of the component's Settings dataclass

    Raises:
        ConfigurationError: If strict=True and required settings are missing
        ValueError: If component has no Settings dataclass
    """
    settings_class = getattr(component_class, "Settings", None)
    if not isinstance(settings_class, type) or not dataclasses.is_dataclass(
        settings_class
    ):
        raise ValueError(
            f"Component {component_class.__name__} has no Settings dataclass"
        )

    if strict:
        result = validate_settings_detailed(component_class, settings_dict)
        if not result.is_valid:
            component_path = f"{component_class.__module__}.{component_class.__name__}"
            raise ConfigurationError(
                component_path=component_path,
                missing_settings=(
                    result.missing_required
                    if result.missing_required
                    else result.validation_failures
                ),
                message="; ".join(result.errors),
            )

    # Build kwargs for dataclass instantiation
    # Use defaults for any missing values and apply type coercion
    schema = get_settings_schema(component_class)
    kwargs: dict[str, Any] = {}

    for name, info in schema.items():
        if name in settings_dict:
            value = settings_dict[name]
            # Apply type coercion for primitive types
            python_type = info.get("python_type", "")
            kwargs[name] = _coerce_value(value, python_type)
        elif "default" in info:
            kwargs[name] = info["default"]
        # else: let dataclass use its own default

    return settings_class(**kwargs)


def _coerce_value(value: Any, python_type: str) -> Any:
    """
    Coerce a value to the expected Python type.

    Args:
        value: The value to coerce
        python_type: The target type name ('str', 'int', 'float', 'bool')

    Returns:
        The coerced value, or original value if coercion not needed/possible
    """
    if value is None:
        return value

    try:
        if python_type == "int":
            if isinstance(value, bool):
                return int(value)
            if isinstance(value, (int, float)):
                return int(value)
            if isinstance(value, str) and value.strip():
                return int(value)
        elif python_type == "float":
            if isinstance(value, (int, float)):
                return float(value)
            if isinstance(value, str) and value.strip():
                return float(value)
        elif python_type == "bool":
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                return value.lower() in ("true", "1", "yes", "on")
            if isinstance(value, (int, float)):
                return bool(value)
        elif python_type == "str":
            if not isinstance(value, str):
                return str(value)
    except (ValueError, TypeError) as e:
        logger.warning(
            "Failed to coerce value %r to type '%s': %s", value, python_type, e
        )

    return value


def _get_type_name(type_hint: Any) -> str:
    """Get a human-readable type name from a type hint."""
    if type_hint is Any:
        return "any"
    if hasattr(type_hint, "__name__"):
        return type_hint.__name__
    if hasattr(type_hint, "__origin__"):
        # Handle generic types like Optional[str], List[int], etc.
        origin = type_hint.__origin__
        args = getattr(type_hint, "__args__", ())
        if origin is type(None):
            return "None"
        origin_name = getattr(origin, "__name__", str(origin))
        if args:
            arg_names = [_get_type_name(arg) for arg in args]
            return f"{origin_name}[{', '.join(arg_names)}]"
        return origin_name
    return str(type_hint)
