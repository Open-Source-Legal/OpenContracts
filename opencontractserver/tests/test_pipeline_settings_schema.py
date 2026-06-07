"""
Tests for the pipeline settings schema system.

This module tests the Settings dataclass-based configuration schema for
pipeline components, including:
- Schema extraction from component classes
- Settings validation
- Settings instance creation
- Integration with PipelineComponentBase
"""

from dataclasses import dataclass, field
from typing import Optional
from unittest.mock import patch

from django.test import TestCase

from opencontractserver.pipeline.base.base_component import PipelineComponentBase
from opencontractserver.pipeline.base.settings_schema import (
    ConfigurationError,
    PipelineSetting,
    SettingType,
    ValidationResult,
    _coerce_value,
    _get_type_name,
    create_settings_instance,
    get_all_env_vars,
    get_pipeline_setting,
    get_required_settings,
    get_secret_settings,
    get_settings_schema,
    validate_settings,
    validate_settings_detailed,
)


class ComponentWithSettings(PipelineComponentBase):
    """Test component with a Settings dataclass."""

    @dataclass
    class Settings:
        """Test settings schema."""

        api_key: str = field(
            default="",
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.SECRET,
                    required=True,
                    description="API key for the service",
                    env_var="TEST_API_KEY",
                )
            },
        )
        timeout: int = field(
            default=30,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="Request timeout in seconds",
                )
            },
        )
        debug_mode: bool = field(
            default=False,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="Enable debug mode",
                    env_var="TEST_DEBUG_MODE",
                )
            },
        )
        service_url: str = field(
            default="http://localhost:8000",
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.REQUIRED,
                    required=True,
                    description="Service URL",
                    env_var="TEST_SERVICE_URL",
                )
            },
        )


class ComponentWithoutSettings(PipelineComponentBase):
    """Test component without a Settings dataclass."""

    pass


class TestSettingType(TestCase):
    """Test the SettingType enum."""

    def test_setting_type_values(self):
        """Test that SettingType enum has expected values."""
        self.assertEqual(SettingType.REQUIRED.value, "required")
        self.assertEqual(SettingType.OPTIONAL.value, "optional")
        self.assertEqual(SettingType.SECRET.value, "secret")


class TestPipelineSetting(TestCase):
    """Test the PipelineSetting dataclass."""

    def test_pipeline_setting_defaults(self):
        """Test PipelineSetting default values."""
        setting = PipelineSetting(setting_type=SettingType.OPTIONAL)
        self.assertEqual(setting.setting_type, SettingType.OPTIONAL)
        self.assertFalse(setting.required)
        self.assertEqual(setting.description, "")
        self.assertIsNone(setting.env_var)
        self.assertIsNone(setting.validation)

    def test_pipeline_setting_with_all_values(self):
        """Test PipelineSetting with all values specified."""
        validator = lambda x: len(x) > 0  # noqa: E731
        setting = PipelineSetting(
            setting_type=SettingType.SECRET,
            required=True,
            description="Test description",
            env_var="TEST_ENV_VAR",
            validation=validator,
        )
        self.assertEqual(setting.setting_type, SettingType.SECRET)
        self.assertTrue(setting.required)
        self.assertEqual(setting.description, "Test description")
        self.assertEqual(setting.env_var, "TEST_ENV_VAR")
        self.assertIs(setting.validation, validator)


class TestGetSettingsSchema(TestCase):
    """Test the get_settings_schema function."""

    def test_get_schema_from_component_with_settings(self):
        """Test extracting schema from a component with Settings dataclass."""
        schema = get_settings_schema(ComponentWithSettings)

        self.assertIn("api_key", schema)
        self.assertIn("timeout", schema)
        self.assertIn("debug_mode", schema)
        self.assertIn("service_url", schema)

        # Check api_key schema
        api_key_info = schema["api_key"]
        self.assertEqual(api_key_info["type"], "secret")
        self.assertTrue(api_key_info["required"])
        self.assertEqual(api_key_info["description"], "API key for the service")
        self.assertEqual(api_key_info["env_var"], "TEST_API_KEY")
        self.assertEqual(api_key_info["python_type"], "str")

        # Check timeout schema
        timeout_info = schema["timeout"]
        self.assertEqual(timeout_info["type"], "optional")
        self.assertFalse(timeout_info["required"])
        self.assertEqual(timeout_info["default"], 30)
        self.assertEqual(timeout_info["python_type"], "int")

    def test_get_schema_from_component_without_settings(self):
        """Test extracting schema from a component without Settings dataclass."""
        schema = get_settings_schema(ComponentWithoutSettings)
        self.assertEqual(schema, {})

    def test_get_schema_returns_default_values(self):
        """Test that schema includes default values."""
        schema = get_settings_schema(ComponentWithSettings)

        self.assertEqual(schema["api_key"]["default"], "")
        self.assertEqual(schema["timeout"]["default"], 30)
        self.assertEqual(schema["debug_mode"]["default"], False)
        self.assertEqual(schema["service_url"]["default"], "http://localhost:8000")


class TestSchemaUtilities(TestCase):
    """Test schema utility functions."""

    def test_get_all_env_vars(self):
        """Test getting all env_var mappings."""
        env_vars = get_all_env_vars(ComponentWithSettings)

        self.assertEqual(env_vars["api_key"], "TEST_API_KEY")
        self.assertEqual(env_vars["debug_mode"], "TEST_DEBUG_MODE")
        self.assertEqual(env_vars["service_url"], "TEST_SERVICE_URL")
        self.assertNotIn("timeout", env_vars)  # timeout has no env_var

    def test_get_required_settings(self):
        """Test getting list of required settings."""
        required = get_required_settings(ComponentWithSettings)

        self.assertIn("api_key", required)
        self.assertIn("service_url", required)
        self.assertNotIn("timeout", required)
        self.assertNotIn("debug_mode", required)

    def test_get_secret_settings(self):
        """Test getting list of secret settings."""
        secrets = get_secret_settings(ComponentWithSettings)

        self.assertIn("api_key", secrets)
        self.assertNotIn("timeout", secrets)
        self.assertNotIn("debug_mode", secrets)
        self.assertNotIn("service_url", secrets)


class TestValidateSettings(TestCase):
    """Test the validate_settings function."""

    def test_validate_complete_settings(self):
        """Test validation passes with all required settings."""
        settings_dict = {
            "api_key": "test-key-123",
            "service_url": "https://api.example.com",
            "timeout": 60,
        }
        is_valid, errors = validate_settings(ComponentWithSettings, settings_dict)
        self.assertTrue(is_valid)
        self.assertEqual(errors, [])

    def test_validate_missing_required_settings(self):
        """Test validation fails when required non-secret settings are missing.

        Secret settings (like api_key) are validated separately and skipped here.
        """
        settings_dict = {
            "timeout": 60,
        }
        is_valid, errors = validate_settings(ComponentWithSettings, settings_dict)
        self.assertFalse(is_valid)
        # api_key is SECRET so it's skipped by validate_settings
        self.assertFalse(any("api_key" in err for err in errors))
        self.assertTrue(any("service_url" in err for err in errors))

    def test_validate_empty_required_string(self):
        """Test validation fails when required non-secret string is empty."""
        settings_dict = {
            "service_url": "",  # Empty string for a required non-secret field
        }
        is_valid, errors = validate_settings(ComponentWithSettings, settings_dict)
        self.assertFalse(is_valid)
        self.assertTrue(any("service_url" in err for err in errors))

    def test_validate_component_without_settings(self):
        """Test validation of component without Settings dataclass."""
        is_valid, errors = validate_settings(ComponentWithoutSettings, {})
        self.assertTrue(is_valid)
        self.assertEqual(errors, [])


class TestCreateSettingsInstance(TestCase):
    """Test the create_settings_instance function."""

    def test_create_instance_with_complete_settings(self):
        """Test creating settings instance with all values."""
        settings_dict = {
            "api_key": "test-key-123",
            "service_url": "https://api.example.com",
            "timeout": 60,
            "debug_mode": True,
        }
        instance = create_settings_instance(
            ComponentWithSettings, settings_dict, strict=False
        )

        self.assertEqual(instance.api_key, "test-key-123")
        self.assertEqual(instance.service_url, "https://api.example.com")
        self.assertEqual(instance.timeout, 60)
        self.assertTrue(instance.debug_mode)

    def test_create_instance_uses_defaults(self):
        """Test that missing values use defaults."""
        settings_dict = {
            "api_key": "test-key-123",
            "service_url": "https://api.example.com",
        }
        instance = create_settings_instance(
            ComponentWithSettings, settings_dict, strict=False
        )

        self.assertEqual(instance.timeout, 30)  # Default
        self.assertFalse(instance.debug_mode)  # Default

    def test_create_instance_strict_mode_raises_error(self):
        """Test that strict mode raises ConfigurationError for missing required.

        Secret fields (api_key) are skipped; only non-secret required fields
        (service_url) trigger the error.
        """
        settings_dict = {
            "timeout": 60,
        }
        with self.assertRaises(ConfigurationError) as context:
            create_settings_instance(ComponentWithSettings, settings_dict, strict=True)

        self.assertIn(
            "service_url",
            str(context.exception.missing_settings) or str(context.exception),
        )

    def test_create_instance_for_component_without_settings_raises(self):
        """Test that creating instance for component without Settings raises."""
        with self.assertRaises(ValueError) as context:
            create_settings_instance(ComponentWithoutSettings, {}, strict=False)

        self.assertIn("no Settings dataclass", str(context.exception))


class TestPipelineComponentBaseWithSettingsSchema(TestCase):
    """Test PipelineComponentBase integration with Settings schema."""

    def test_component_has_settings_property(self):
        """Test that components with Settings dataclass have settings property."""
        # Need to mock PipelineSettings to avoid DB access
        with patch(
            "opencontractserver.pipeline.base.base_component.PipelineComponentBase.get_component_settings"
        ) as mock_get_settings:
            mock_get_settings.return_value = {
                "api_key": "test-key",
                "service_url": "https://test.com",
            }
            component = ComponentWithSettings()

            self.assertIsNotNone(component.settings)
            assert component.settings is not None
            self.assertEqual(component.settings.api_key, "test-key")
            self.assertEqual(component.settings.service_url, "https://test.com")

    def test_component_without_settings_has_none(self):
        """Test that components without Settings dataclass have None settings."""
        with patch(
            "opencontractserver.pipeline.base.base_component.PipelineComponentBase.get_component_settings"
        ) as mock_get_settings:
            mock_get_settings.return_value = {}
            component = ComponentWithoutSettings()

            self.assertIsNone(component.settings)

    def test_get_settings_schema_class_method(self):
        """Test the get_settings_schema class method."""
        schema = ComponentWithSettings.get_settings_schema()

        self.assertIn("api_key", schema)
        self.assertIn("timeout", schema)

    def test_validate_settings_method(self):
        """Test the validate_settings instance method."""
        with patch(
            "opencontractserver.pipeline.base.base_component.PipelineComponentBase.get_component_settings"
        ) as mock_get_settings:
            mock_get_settings.return_value = {
                "api_key": "test-key",
                "service_url": "https://test.com",
            }
            component = ComponentWithSettings()
            is_valid, errors = component.validate_settings()

            self.assertTrue(is_valid)
            self.assertEqual(errors, [])


class TestConfigurationError(TestCase):
    """Test the ConfigurationError exception."""

    def test_configuration_error_attributes(self):
        """Test ConfigurationError has expected attributes."""
        error = ConfigurationError(
            component_path="test.module.TestComponent",
            missing_settings=["api_key", "service_url"],
        )

        self.assertEqual(error.component_path, "test.module.TestComponent")
        self.assertEqual(error.missing_settings, ["api_key", "service_url"])
        self.assertIn("api_key", str(error))
        self.assertIn("service_url", str(error))

    def test_configuration_error_custom_message(self):
        """Test ConfigurationError with custom message."""
        error = ConfigurationError(
            component_path="test.Component",
            missing_settings=["key"],
            message="Custom error message",
        )

        self.assertEqual(str(error), "Custom error message")


class ComponentWithValidation(PipelineComponentBase):
    """Component with custom validation functions for testing."""

    @dataclass
    class Settings:
        port: int = field(
            default=8080,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="Port number",
                    validation=lambda x: 1 <= x <= 65535,
                )
            },
        )
        host: str = field(
            default="localhost",
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="Hostname",
                    validation=lambda x: len(x) > 0,
                )
            },
        )


class ComponentWithDefaultFactory(PipelineComponentBase):
    """Component with a default_factory field for testing."""

    @dataclass
    class Settings:
        tags: list = field(
            default_factory=list,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="Tags list",
                )
            },
        )


class ComponentWithOptionalType(PipelineComponentBase):
    """Component using Optional type hints for testing _get_type_name."""

    @dataclass
    class Settings:
        name: Optional[str] = field(
            default=None,
            metadata={
                "pipeline_setting": PipelineSetting(
                    setting_type=SettingType.OPTIONAL,
                    description="Optional name",
                )
            },
        )


class ComponentWithBareField(PipelineComponentBase):
    """Component with a field that has no pipeline_setting metadata."""

    @dataclass
    class Settings:
        plain_field: str = "default_value"


class TestCoerceValue(TestCase):
    """Test the _coerce_value function for type coercion."""

    def test_coerce_none_returns_none(self):
        self.assertIsNone(_coerce_value(None, "str"))

    def test_coerce_string_to_int(self):
        self.assertEqual(_coerce_value("42", "int"), 42)

    def test_coerce_float_to_int(self):
        self.assertEqual(_coerce_value(3.7, "int"), 3)

    def test_coerce_bool_to_int(self):
        self.assertEqual(_coerce_value(True, "int"), 1)

    def test_coerce_int_to_int(self):
        self.assertEqual(_coerce_value(5, "int"), 5)

    def test_coerce_string_to_float(self):
        self.assertAlmostEqual(_coerce_value("3.14", "float"), 3.14)

    def test_coerce_int_to_float(self):
        self.assertAlmostEqual(_coerce_value(5, "float"), 5.0)

    def test_coerce_string_to_bool_true(self):
        self.assertTrue(_coerce_value("true", "bool"))
        self.assertTrue(_coerce_value("1", "bool"))
        self.assertTrue(_coerce_value("yes", "bool"))
        self.assertTrue(_coerce_value("on", "bool"))

    def test_coerce_string_to_bool_false(self):
        self.assertFalse(_coerce_value("false", "bool"))
        self.assertFalse(_coerce_value("0", "bool"))

    def test_coerce_bool_to_bool(self):
        self.assertTrue(_coerce_value(True, "bool"))
        self.assertFalse(_coerce_value(False, "bool"))

    def test_coerce_int_to_bool(self):
        self.assertTrue(_coerce_value(1, "bool"))
        self.assertFalse(_coerce_value(0, "bool"))

    def test_coerce_non_string_to_str(self):
        self.assertEqual(_coerce_value(42, "str"), "42")

    def test_coerce_string_to_str_noop(self):
        self.assertEqual(_coerce_value("hello", "str"), "hello")

    def test_coerce_empty_string_to_int_returns_original(self):
        # Empty string can't be converted to int, returns original
        self.assertEqual(_coerce_value("", "int"), "")

    def test_coerce_invalid_string_to_int(self):
        # Invalid string, should log warning and return original
        self.assertEqual(_coerce_value("not_a_number", "int"), "not_a_number")

    def test_coerce_unknown_type_returns_original(self):
        self.assertEqual(_coerce_value("value", "unknown"), "value")

    def test_coerce_empty_string_to_float_returns_original(self):
        self.assertEqual(_coerce_value("", "float"), "")


class TestGetTypeName(TestCase):
    """Test the _get_type_name function."""

    def test_basic_types(self):
        self.assertEqual(_get_type_name(str), "str")
        self.assertEqual(_get_type_name(int), "int")
        self.assertEqual(_get_type_name(bool), "bool")
        self.assertEqual(_get_type_name(float), "float")

    def test_any_type(self):
        from typing import Any

        self.assertEqual(_get_type_name(Any), "any")

    def test_optional_type(self):
        result = _get_type_name(Optional[str])
        # Optional[str] is Union[str, None]; may be "Optional" or "str | None"
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)

    def test_list_type(self):
        result = _get_type_name(list[int])
        self.assertIn("list", result)

    def test_plain_string_fallback(self):
        # Non-type objects fall through to str()
        self.assertIsInstance(_get_type_name("not_a_type"), str)


class TestGetPipelineSetting(TestCase):
    """Test the get_pipeline_setting function."""

    def test_returns_setting_from_metadata(self):
        from dataclasses import fields as dc_fields

        for f in dc_fields(ComponentWithSettings.Settings):
            if f.name == "api_key":
                result = get_pipeline_setting(f)
                self.assertIsNotNone(result)
                assert result is not None
                self.assertEqual(result.setting_type, SettingType.SECRET)

    def test_returns_none_for_no_metadata(self):
        from dataclasses import fields as dc_fields

        for f in dc_fields(ComponentWithBareField.Settings):
            if f.name == "plain_field":
                result = get_pipeline_setting(f)
                self.assertIsNone(result)


class TestValidateSettingsDetailed(TestCase):
    """Test validate_settings_detailed with custom validation."""

    def test_custom_validation_passes(self):
        settings_dict = {"port": 8080, "host": "example.com"}
        result = validate_settings_detailed(ComponentWithValidation, settings_dict)
        self.assertTrue(result.is_valid)
        self.assertEqual(result.errors, [])

    def test_custom_validation_fails(self):
        settings_dict = {"port": 99999, "host": "example.com"}
        result = validate_settings_detailed(ComponentWithValidation, settings_dict)
        self.assertFalse(result.is_valid)
        self.assertIn("port", result.validation_failures)

    def test_custom_validation_exception(self):
        """Validation function that raises should be caught."""

        @dataclass
        class BadSettings:
            value: str = field(
                default="",
                metadata={
                    "pipeline_setting": PipelineSetting(
                        setting_type=SettingType.OPTIONAL,
                        validation=lambda x: x.no_such_method(),
                    )
                },
            )

        class BadComponent(PipelineComponentBase):
            Settings = BadSettings

        result = validate_settings_detailed(BadComponent, {"value": "test"})
        self.assertFalse(result.is_valid)
        self.assertIn("value", result.validation_failures)

    def test_validation_result_structure(self):
        result = ValidationResult(
            is_valid=False,
            errors=["err1"],
            missing_required=["field1"],
            validation_failures=["field2"],
        )
        self.assertFalse(result.is_valid)
        self.assertEqual(result.missing_required, ["field1"])
        self.assertEqual(result.validation_failures, ["field2"])


class TestDefaultFactory(TestCase):
    """Test settings with default_factory fields."""

    def test_schema_includes_default_factory_value(self):
        schema = get_settings_schema(ComponentWithDefaultFactory)
        self.assertIn("tags", schema)
        self.assertEqual(schema["tags"]["default"], [])

    def test_create_instance_with_default_factory(self):
        instance = create_settings_instance(
            ComponentWithDefaultFactory, {}, strict=False
        )
        self.assertEqual(instance.tags, [])


class TestBareFieldSchema(TestCase):
    """Test schema extraction for fields without PipelineSetting metadata."""

    def test_bare_field_gets_optional_defaults(self):
        schema = get_settings_schema(ComponentWithBareField)
        self.assertIn("plain_field", schema)
        self.assertEqual(schema["plain_field"]["type"], "optional")
        self.assertFalse(schema["plain_field"]["required"])

    def test_schema_has_validation_flag(self):
        schema = get_settings_schema(ComponentWithSettings)
        self.assertIn("has_validation", schema["api_key"])
        self.assertFalse(schema["api_key"]["has_validation"])

    def test_schema_with_validation_has_flag(self):
        schema = get_settings_schema(ComponentWithValidation)
        self.assertTrue(schema["port"]["has_validation"])


class TestCreateSettingsInstanceCoercion(TestCase):
    """Test type coercion in create_settings_instance."""

    def test_string_values_coerced_to_int(self):
        """Settings from JSON/DB may come as strings, should be coerced."""
        instance = create_settings_instance(
            ComponentWithSettings,
            {
                "api_key": "key",
                "service_url": "http://test",
                "timeout": "120",
                "debug_mode": "true",
            },
            strict=False,
        )
        self.assertEqual(instance.timeout, 120)
        self.assertTrue(instance.debug_mode)
