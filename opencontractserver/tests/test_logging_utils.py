"""
Tests for opencontractserver/utils/logging.py
"""

from dataclasses import dataclass

from django.test import TestCase

from opencontractserver.utils.logging import redact_sensitive_kwargs


class TestRedactSensitiveKwargs(TestCase):
    """Tests for the redact_sensitive_kwargs utility function."""

    def test_redacts_api_key(self):
        """Test that api_key is redacted."""
        result = redact_sensitive_kwargs({"api_key": "sk-123", "verbose": True})
        self.assertEqual(result, {"api_key": "***", "verbose": True})

    def test_redacts_apikey_no_underscore(self):
        """Test that apikey (no underscore) is redacted."""
        result = redact_sensitive_kwargs({"apikey": "sk-123"})
        self.assertEqual(result, {"apikey": "***"})

    def test_case_insensitive_matching(self):
        """Test that matching is case-insensitive."""
        result = redact_sensitive_kwargs({"API_KEY": "sk-123", "ApiKey": "sk-456"})
        self.assertEqual(result, {"API_KEY": "***", "ApiKey": "***"})

    def test_multiple_sensitive_patterns(self):
        """Test that multiple sensitive patterns are all redacted."""
        result = redact_sensitive_kwargs(
            {
                "password": "pass123",
                "access_token": "token456",
                "client_secret": "secret789",
                "safe_value": "not_sensitive",
            }
        )
        self.assertEqual(
            result,
            {
                "password": "***",
                "access_token": "***",
                "client_secret": "***",
                "safe_value": "not_sensitive",
            },
        )

    def test_empty_dict(self):
        """Test that empty dict returns empty dict."""
        result = redact_sensitive_kwargs({})
        self.assertEqual(result, {})

    def test_no_false_positives_keyboard(self):
        """Test that 'keyboard' is NOT redacted (no false positive on 'key')."""
        result = redact_sensitive_kwargs(
            {"keyboard": "qwerty", "keyboard_layout": "us"}
        )
        self.assertEqual(result, {"keyboard": "qwerty", "keyboard_layout": "us"})

    def test_no_false_positives_monkey(self):
        """Test that 'monkey' is NOT redacted (no false positive on 'key')."""
        result = redact_sensitive_kwargs({"monkey": "banana"})
        self.assertEqual(result, {"monkey": "banana"})

    def test_nested_dict_redaction(self):
        """Test that nested dictionaries are recursively redacted."""
        result = redact_sensitive_kwargs(
            {
                "provider_config": {
                    "api_key": "secret123",
                    "endpoint": "https://api.example.com",
                },
                "verbose": True,
            }
        )
        self.assertEqual(
            result,
            {
                "provider_config": {
                    "api_key": "***",
                    "endpoint": "https://api.example.com",
                },
                "verbose": True,
            },
        )

    def test_deeply_nested_dict_redaction(self):
        """Test that deeply nested dictionaries are recursively redacted."""
        result = redact_sensitive_kwargs(
            {
                "level1": {
                    "level2": {
                        "level3": {
                            "api_key": "deep_secret",
                        }
                    }
                }
            }
        )
        self.assertEqual(
            result,
            {"level1": {"level2": {"level3": {"api_key": "***"}}}},
        )

    def test_list_of_dicts_redaction(self):
        """Test that lists of dictionaries are redacted."""
        result = redact_sensitive_kwargs(
            {
                "providers": [
                    {"name": "openai", "api_key": "sk-123"},
                    {"name": "anthropic", "api_key": "sk-456"},
                ]
            }
        )
        self.assertEqual(
            result,
            {
                "providers": [
                    {"name": "openai", "api_key": "***"},
                    {"name": "anthropic", "api_key": "***"},
                ]
            },
        )

    def test_list_of_non_dicts_unchanged(self):
        """Test that lists of non-dict values are unchanged."""
        result = redact_sensitive_kwargs(
            {"items": [1, 2, 3], "names": ["alice", "bob"]}
        )
        self.assertEqual(result, {"items": [1, 2, 3], "names": ["alice", "bob"]})

    def test_mixed_list_redaction(self):
        """Test that mixed lists (dicts and non-dicts) are handled correctly."""
        result = redact_sensitive_kwargs(
            {"mixed": [{"api_key": "secret"}, "string", 123, {"safe": "value"}]}
        )
        self.assertEqual(
            result,
            {"mixed": [{"api_key": "***"}, "string", 123, {"safe": "value"}]},
        )

    def test_authorization_header_redacted(self):
        """Test that authorization-related keys are redacted."""
        result = redact_sensitive_kwargs(
            {"authorization": "Bearer xyz", "authorization_header": "token"}
        )
        self.assertEqual(
            result, {"authorization": "***", "authorization_header": "***"}
        )

    def test_bearer_token_redacted(self):
        """Test that bearer-related keys are redacted."""
        result = redact_sensitive_kwargs({"bearer_token": "xyz123"})
        self.assertEqual(result, {"bearer_token": "***"})

    def test_credential_redacted(self):
        """Test that credential-related keys are redacted."""
        result = redact_sensitive_kwargs(
            {"credential": "abc", "user_credential": "def", "credentials_file": "/path"}
        )
        self.assertEqual(
            result,
            {"credential": "***", "user_credential": "***", "credentials_file": "***"},
        )

    def test_redacts_dataclass_instance(self):
        """A Settings dataclass is accepted and rendered as a redacted dict."""

        @dataclass
        class Settings:
            api_key: str
            timeout: int

        result = redact_sensitive_kwargs(Settings(api_key="sk-1", timeout=3))
        self.assertEqual(result, {"api_key": "***", "timeout": 3})

    def test_redacts_nested_dataclass_values(self):
        """Dataclasses nested in dicts and lists are redacted like dicts."""

        @dataclass
        class Inner:
            client_secret: str

        result = redact_sensitive_kwargs({"inner": Inner("s"), "items": [Inner("t")]})
        self.assertEqual(
            result,
            {"inner": {"client_secret": "***"}, "items": [{"client_secret": "***"}]},
        )
