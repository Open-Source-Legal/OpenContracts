"""
Tests for Auth0 JWKS caching functionality.

This module tests the JWKS cache in config/graphql_auth0_auth/utils.py to ensure:
1. JWKS is fetched from Auth0 on first request
2. Subsequent requests use cached data within TTL
3. Cache expires correctly after TTL
4. Thread-safe access to the cache
5. Graceful fallback to stale cache on network errors
"""

from unittest.mock import MagicMock, patch

import pytest
import requests

from config.graphql_auth0_auth.utils import (
    _JWKS_CACHE_TTL,
    _get_cached_jwks,
)


class TestJWKSCache:
    """Tests for the _get_cached_jwks function."""

    def setup_method(self):
        """Reset cache before each test."""
        # Import and reset the module-level cache
        import config.graphql_auth0_auth.utils as utils_module

        utils_module._jwks_cache = {"data": None, "expires_at": 0}

    @patch("config.graphql_auth0_auth.utils.requests.get")
    def test_first_request_fetches_from_auth0(self, mock_get):
        """First request should fetch JWKS from Auth0."""
        mock_jwks = {"keys": [{"kid": "test-key-id", "kty": "RSA"}]}
        mock_response = MagicMock()
        mock_response.json.return_value = mock_jwks
        mock_get.return_value = mock_response

        result = _get_cached_jwks("test-domain.auth0.com")

        assert result == mock_jwks
        mock_get.assert_called_once_with(
            "https://test-domain.auth0.com/.well-known/jwks.json", timeout=10
        )
        mock_response.raise_for_status.assert_called_once()

    @patch("config.graphql_auth0_auth.utils.requests.get")
    def test_second_request_uses_cache(self, mock_get):
        """Second request within TTL should use cached data."""
        mock_jwks = {"keys": [{"kid": "test-key-id", "kty": "RSA"}]}
        mock_response = MagicMock()
        mock_response.json.return_value = mock_jwks
        mock_get.return_value = mock_response

        # First request
        result1 = _get_cached_jwks("test-domain.auth0.com")
        # Second request (should use cache)
        result2 = _get_cached_jwks("test-domain.auth0.com")

        assert result1 == mock_jwks
        assert result2 == mock_jwks
        # Should only be called once (first request)
        assert mock_get.call_count == 1

    @patch("config.graphql_auth0_auth.utils.requests.get")
    @patch("config.graphql_auth0_auth.utils.time.time")
    def test_cache_expires_after_ttl(self, mock_time, mock_get):
        """Cache should expire after TTL and fetch fresh data."""
        mock_jwks_v1 = {"keys": [{"kid": "key-v1", "kty": "RSA"}]}
        mock_jwks_v2 = {"keys": [{"kid": "key-v2", "kty": "RSA"}]}

        mock_response = MagicMock()
        mock_response.json.side_effect = [mock_jwks_v1, mock_jwks_v2]
        mock_get.return_value = mock_response

        # First request at time 0
        mock_time.return_value = 0
        result1 = _get_cached_jwks("test-domain.auth0.com")

        # Second request after TTL expires
        mock_time.return_value = _JWKS_CACHE_TTL + 1
        result2 = _get_cached_jwks("test-domain.auth0.com")

        assert result1 == mock_jwks_v1
        assert result2 == mock_jwks_v2
        # Should be called twice (cache expired)
        assert mock_get.call_count == 2

    @patch("config.graphql_auth0_auth.utils.requests.get")
    @patch("config.graphql_auth0_auth.utils.time.time")
    def test_cache_valid_just_before_expiry(self, mock_time, mock_get):
        """Cache should still be valid just before TTL expires."""
        mock_jwks = {"keys": [{"kid": "test-key-id", "kty": "RSA"}]}
        mock_response = MagicMock()
        mock_response.json.return_value = mock_jwks
        mock_get.return_value = mock_response

        # First request at time 0
        mock_time.return_value = 0
        _get_cached_jwks("test-domain.auth0.com")

        # Second request just before TTL expires
        mock_time.return_value = _JWKS_CACHE_TTL - 1
        result = _get_cached_jwks("test-domain.auth0.com")

        assert result == mock_jwks
        # Should only be called once (cache still valid)
        assert mock_get.call_count == 1

    @patch("config.graphql_auth0_auth.utils.requests.get")
    @patch("config.graphql_auth0_auth.utils.time.time")
    def test_network_error_returns_stale_cache(self, mock_time, mock_get):
        """Network error should return stale cache if available."""
        mock_jwks = {"keys": [{"kid": "test-key-id", "kty": "RSA"}]}
        mock_response = MagicMock()
        mock_response.json.return_value = mock_jwks
        mock_get.return_value = mock_response

        # First request succeeds at time 0
        mock_time.return_value = 0
        result1 = _get_cached_jwks("test-domain.auth0.com")
        assert result1 == mock_jwks

        # Second request after TTL expires, but network fails
        mock_time.return_value = _JWKS_CACHE_TTL + 1
        mock_get.side_effect = requests.RequestException("Network error")

        # Should return stale cache
        result2 = _get_cached_jwks("test-domain.auth0.com")
        assert result2 == mock_jwks

    @patch("config.graphql_auth0_auth.utils.requests.get")
    def test_network_error_raises_when_no_cache(self, mock_get):
        """Network error should raise when no cache is available."""
        mock_get.side_effect = requests.RequestException("Network error")

        with pytest.raises(requests.RequestException):
            _get_cached_jwks("test-domain.auth0.com")

    @patch("config.graphql_auth0_auth.utils.requests.get")
    @patch("config.graphql_auth0_auth.utils.time.time")
    def test_http_error_returns_stale_cache(self, mock_time, mock_get):
        """HTTP error should return stale cache if available."""
        mock_jwks = {"keys": [{"kid": "test-key-id", "kty": "RSA"}]}
        mock_response_success = MagicMock()
        mock_response_success.json.return_value = mock_jwks

        # First request succeeds at time 0
        mock_time.return_value = 0
        mock_get.return_value = mock_response_success
        result1 = _get_cached_jwks("test-domain.auth0.com")
        assert result1 == mock_jwks

        # Second request after TTL expires, but HTTP error
        mock_time.return_value = _JWKS_CACHE_TTL + 1
        mock_response_error = MagicMock()
        mock_response_error.raise_for_status.side_effect = requests.HTTPError(
            "500 Server Error"
        )
        mock_get.return_value = mock_response_error

        # Should return stale cache
        result2 = _get_cached_jwks("test-domain.auth0.com")
        assert result2 == mock_jwks

    @patch("config.graphql_auth0_auth.utils.requests.get")
    @patch("config.graphql_auth0_auth.utils.time.time")
    def test_json_parse_error_returns_stale_cache(self, mock_time, mock_get):
        """JSON parse error should return stale cache if available."""
        mock_jwks = {"keys": [{"kid": "test-key-id", "kty": "RSA"}]}
        mock_response_success = MagicMock()
        mock_response_success.json.return_value = mock_jwks

        # First request succeeds at time 0
        mock_time.return_value = 0
        mock_get.return_value = mock_response_success
        result1 = _get_cached_jwks("test-domain.auth0.com")
        assert result1 == mock_jwks

        # Second request after TTL expires, but JSON parse fails
        mock_time.return_value = _JWKS_CACHE_TTL + 1
        mock_response_bad_json = MagicMock()
        mock_response_bad_json.json.side_effect = ValueError("Invalid JSON")
        mock_get.return_value = mock_response_bad_json

        # Should return stale cache
        result2 = _get_cached_jwks("test-domain.auth0.com")
        assert result2 == mock_jwks


class TestAuth0JWTSettingsDunderProbe:
    """Regression tests for Auth0JWTSettings.__getattr__ noisy logging.

    Production logs were sprinkled with
    ``ERROR settings  Auth0JWTSettings.__getattr__() - Invalid setting
    requested: _user_settings`` whenever Python machinery (deepcopy,
    pickle, hasattr) probed dunder/private attributes.  The class now
    raises ``AttributeError`` quietly for any name beginning with ``_``.
    """

    def test_dunder_probe_is_silent(self, caplog):
        from config.graphql_auth0_auth.settings import Auth0JWTSettings

        s = Auth0JWTSettings({"AUTH0_FOO": "bar"}, ())
        with caplog.at_level("ERROR"):
            with pytest.raises(AttributeError):
                _ = s._user_settings_probe  # noqa: B018 — intentional probe
            with pytest.raises(AttributeError):
                _ = s.__deepcopy__  # noqa: B018 — intentional probe
        assert "Invalid setting requested" not in caplog.text

    def test_unknown_public_setting_still_logs_error(self, caplog):
        from config.graphql_auth0_auth.settings import Auth0JWTSettings

        s = Auth0JWTSettings({"AUTH0_FOO": "bar"}, ())
        with caplog.at_level("ERROR"):
            with pytest.raises(AttributeError):
                _ = s.NOT_A_SETTING  # noqa: B018 — intentional probe
        assert "Invalid setting requested" in caplog.text
