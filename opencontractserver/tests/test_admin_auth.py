"""
Tests for Auth0 Django admin authentication.

This module tests:
- Admin claims sync from Auth0 tokens
- Auth0AdminBackend authentication
- Auth0AdminLoginView and Auth0AdminLogoutView
- Rate limiting on admin login endpoints
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase, override_settings

User = get_user_model()


class TestAdminClaimsSync(TestCase):
    """Tests for syncing admin claims from Auth0 tokens."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="auth0|test_user",
            email="test@example.com",
            is_staff=False,
            is_superuser=False,
        )

    def setUp(self):
        # Refresh user from DB before each test
        self.user.refresh_from_db()
        self.user.is_staff = False
        self.user.is_superuser = False
        self.user.save()

    @override_settings(
        USE_AUTH0=True, AUTH0_ADMIN_CLAIM_NAMESPACE="https://test.example.com/"
    )
    def test_sync_is_staff_true_from_claims(self):
        """is_staff should be synced to True from token claims."""
        from config.graphql_auth0_auth.utils import sync_admin_claims_from_payload

        payload = {
            "sub": "auth0|test_user",
            "https://test.example.com/is_staff": True,
        }

        result = sync_admin_claims_from_payload(self.user, payload)

        self.user.refresh_from_db()
        self.assertTrue(result)
        self.assertTrue(self.user.is_staff)

    @override_settings(
        USE_AUTH0=True, AUTH0_ADMIN_CLAIM_NAMESPACE="https://test.example.com/"
    )
    def test_sync_is_staff_false_from_claims(self):
        """is_staff should be synced to False from token claims."""
        from config.graphql_auth0_auth.utils import sync_admin_claims_from_payload

        # First set user to staff
        self.user.is_staff = True
        self.user.save()

        payload = {
            "sub": "auth0|test_user",
            "https://test.example.com/is_staff": False,
        }

        result = sync_admin_claims_from_payload(self.user, payload)

        self.user.refresh_from_db()
        self.assertTrue(result)
        self.assertFalse(self.user.is_staff)

    @override_settings(
        USE_AUTH0=True,
        AUTH0_ADMIN_CLAIM_NAMESPACE="https://test.example.com/",
        AUTH0_SUPERUSER_SUB_ALLOWLIST=["auth0|test_user"],
    )
    def test_sync_is_superuser_true_from_claims(self):
        """is_superuser should be synced to True from token claims."""
        from config.graphql_auth0_auth.utils import sync_admin_claims_from_payload

        payload = {
            "sub": "auth0|test_user",
            "https://test.example.com/is_superuser": True,
        }

        result = sync_admin_claims_from_payload(self.user, payload)

        self.user.refresh_from_db()
        self.assertTrue(result)
        self.assertTrue(self.user.is_superuser)

    @override_settings(
        USE_AUTH0=True, AUTH0_ADMIN_CLAIM_NAMESPACE="https://test.example.com/"
    )
    def test_sync_is_superuser_false_from_claims(self):
        """is_superuser should be synced to False from token claims."""
        from config.graphql_auth0_auth.utils import sync_admin_claims_from_payload

        # First set user to superuser
        self.user.is_superuser = True
        self.user.save()

        payload = {
            "sub": "auth0|test_user",
            "https://test.example.com/is_superuser": False,
        }

        result = sync_admin_claims_from_payload(self.user, payload)

        self.user.refresh_from_db()
        self.assertTrue(result)
        self.assertFalse(self.user.is_superuser)

    @override_settings(
        USE_AUTH0=True,
        AUTH0_ADMIN_CLAIM_NAMESPACE="https://test.example.com/",
        AUTH0_SUPERUSER_SUB_ALLOWLIST=["auth0|test_user"],
    )
    def test_sync_both_claims(self):
        """Both is_staff and is_superuser should be synced together."""
        from config.graphql_auth0_auth.utils import sync_admin_claims_from_payload

        payload = {
            "sub": "auth0|test_user",
            "https://test.example.com/is_staff": True,
            "https://test.example.com/is_superuser": True,
        }

        result = sync_admin_claims_from_payload(self.user, payload)

        self.user.refresh_from_db()
        self.assertTrue(result)
        self.assertTrue(self.user.is_staff)
        self.assertTrue(self.user.is_superuser)

    @override_settings(
        USE_AUTH0=True, AUTH0_ADMIN_CLAIM_NAMESPACE="https://test.example.com/"
    )
    def test_missing_claims_demotes(self):
        """Missing claims should demote admin privileges."""
        from config.graphql_auth0_auth.utils import sync_admin_claims_from_payload

        # Set user to staff first
        self.user.is_staff = True
        self.user.save()

        payload = {"sub": "auth0|test_user"}  # No admin claims

        result = sync_admin_claims_from_payload(self.user, payload)

        self.user.refresh_from_db()
        self.assertTrue(result)
        self.assertFalse(self.user.is_staff)

    @override_settings(
        USE_AUTH0=True, AUTH0_ADMIN_CLAIM_NAMESPACE="https://test.example.com/"
    )
    def test_no_change_when_already_matches(self):
        """No database update should occur when claims match current values."""
        from config.graphql_auth0_auth.utils import sync_admin_claims_from_payload

        # Set user to match claims
        self.user.is_staff = True
        self.user.is_superuser = False
        self.user.save()

        payload = {
            "sub": "auth0|test_user",
            "https://test.example.com/is_staff": True,
            "https://test.example.com/is_superuser": False,
        }

        result = sync_admin_claims_from_payload(self.user, payload)

        self.assertTrue(result)  # Success (no changes needed)

    @override_settings(USE_AUTH0=True)
    def test_uses_default_namespace(self):
        """Should use default namespace when AUTH0_ADMIN_CLAIM_NAMESPACE not set."""
        from config.graphql_auth0_auth.utils import sync_admin_claims_from_payload

        payload = {
            "sub": "auth0|test_user",
            "https://contracts.opensource.legal/is_staff": True,
        }

        result = sync_admin_claims_from_payload(self.user, payload)

        self.user.refresh_from_db()
        self.assertTrue(result)
        self.assertTrue(self.user.is_staff)

    @override_settings(
        USE_AUTH0=True, AUTH0_ADMIN_CLAIM_NAMESPACE="https://test.example.com/"
    )
    def test_sync_string_true_claim(self):
        """String 'true' should be parsed as boolean True."""
        from config.graphql_auth0_auth.utils import sync_admin_claims_from_payload

        payload = {
            "sub": "auth0|test_user",
            "https://test.example.com/is_staff": "true",
        }

        result = sync_admin_claims_from_payload(self.user, payload)

        self.user.refresh_from_db()
        self.assertTrue(result)
        self.assertTrue(self.user.is_staff)

    @override_settings(
        USE_AUTH0=True, AUTH0_ADMIN_CLAIM_NAMESPACE="https://test.example.com/"
    )
    def test_sync_string_false_claim(self):
        """String 'false' should be parsed as boolean False."""
        from config.graphql_auth0_auth.utils import sync_admin_claims_from_payload

        self.user.is_staff = True
        self.user.save()

        payload = {
            "sub": "auth0|test_user",
            "https://test.example.com/is_staff": "false",
        }

        result = sync_admin_claims_from_payload(self.user, payload)

        self.user.refresh_from_db()
        self.assertTrue(result)
        self.assertFalse(self.user.is_staff)

    @override_settings(
        USE_AUTH0=True, AUTH0_ADMIN_CLAIM_NAMESPACE="https://test.example.com/"
    )
    def test_sync_string_True_uppercase(self):
        """String 'True' (uppercase) should be parsed as boolean True."""
        from config.graphql_auth0_auth.utils import sync_admin_claims_from_payload

        payload = {
            "sub": "auth0|test_user",
            "https://test.example.com/is_staff": "True",
        }

        result = sync_admin_claims_from_payload(self.user, payload)

        self.user.refresh_from_db()
        self.assertTrue(result)
        self.assertTrue(self.user.is_staff)

    @override_settings(
        USE_AUTH0=True, AUTH0_ADMIN_CLAIM_NAMESPACE="https://test.example.com/"
    )
    def test_sync_numeric_1_claim(self):
        """Numeric 1 should be parsed as boolean True."""
        from config.graphql_auth0_auth.utils import sync_admin_claims_from_payload

        payload = {
            "sub": "auth0|test_user",
            "https://test.example.com/is_staff": 1,
        }

        result = sync_admin_claims_from_payload(self.user, payload)

        self.user.refresh_from_db()
        self.assertTrue(result)
        self.assertTrue(self.user.is_staff)

    @override_settings(
        USE_AUTH0=True, AUTH0_ADMIN_CLAIM_NAMESPACE="https://test.example.com/"
    )
    def test_sync_numeric_0_claim(self):
        """Numeric 0 should be parsed as boolean False."""
        from config.graphql_auth0_auth.utils import sync_admin_claims_from_payload

        self.user.is_staff = True
        self.user.save()

        payload = {
            "sub": "auth0|test_user",
            "https://test.example.com/is_staff": 0,
        }

        result = sync_admin_claims_from_payload(self.user, payload)

        self.user.refresh_from_db()
        self.assertTrue(result)
        self.assertFalse(self.user.is_staff)

    @override_settings(
        USE_AUTH0=True, AUTH0_ADMIN_CLAIM_NAMESPACE="https://test.example.com/"
    )
    def test_sync_invalid_string_claim_demotes(self):
        """Invalid string claim should demote staff."""
        from config.graphql_auth0_auth.utils import sync_admin_claims_from_payload

        self.user.is_staff = True
        self.user.save()

        payload = {
            "sub": "auth0|test_user",
            "https://test.example.com/is_staff": "invalid",
        }

        result = sync_admin_claims_from_payload(self.user, payload)

        self.user.refresh_from_db()
        self.assertTrue(result)
        self.assertFalse(self.user.is_staff)

    @override_settings(
        USE_AUTH0=True, AUTH0_ADMIN_CLAIM_NAMESPACE="https://test.example.com/"
    )
    @patch.object(User, "save")
    def test_sync_returns_false_on_save_exception(self, mock_save):
        """sync_admin_claims_from_payload should return False when save() fails."""
        from config.graphql_auth0_auth.utils import sync_admin_claims_from_payload

        mock_save.side_effect = Exception("Database error")

        payload = {
            "sub": "auth0|test_user",
            "https://test.example.com/is_staff": True,
        }

        result = sync_admin_claims_from_payload(self.user, payload)

        self.assertFalse(result)
        mock_save.assert_called_once()


class TestAuth0SuperuserAllowlist(TestCase):
    """Tests for the AUTH0_SUPERUSER_SUB_ALLOWLIST defense-in-depth check."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="auth0|allowlist_target",
            email="allowlist@example.com",
            is_staff=False,
            is_superuser=False,
        )

    def setUp(self):
        self.user.refresh_from_db()
        self.user.is_staff = False
        self.user.is_superuser = False
        self.user.save()

    @override_settings(
        USE_AUTH0=True,
        AUTH0_ADMIN_CLAIM_NAMESPACE="https://test.example.com/",
        AUTH0_SUPERUSER_SUB_ALLOWLIST=[],
    )
    def test_blocks_superuser_when_allowlist_empty(self):
        """An empty allowlist must refuse every is_superuser=True claim."""
        from config.graphql_auth0_auth.utils import sync_admin_claims_from_payload

        payload = {
            "sub": "auth0|allowlist_target",
            "https://test.example.com/is_superuser": True,
        }
        result = sync_admin_claims_from_payload(self.user, payload)
        self.user.refresh_from_db()
        self.assertTrue(result)
        # Allowlist override forces is_superuser back to False.
        self.assertFalse(self.user.is_superuser)

    @override_settings(
        USE_AUTH0=True,
        AUTH0_ADMIN_CLAIM_NAMESPACE="https://test.example.com/",
        AUTH0_SUPERUSER_SUB_ALLOWLIST=["auth0|someone_else"],
    )
    def test_blocks_superuser_for_user_not_in_allowlist(self):
        """A populated allowlist that excludes this sub still blocks."""
        from config.graphql_auth0_auth.utils import sync_admin_claims_from_payload

        payload = {
            "sub": "auth0|allowlist_target",
            "https://test.example.com/is_superuser": True,
        }
        result = sync_admin_claims_from_payload(self.user, payload)
        self.user.refresh_from_db()
        self.assertTrue(result)
        self.assertFalse(self.user.is_superuser)

    @override_settings(
        USE_AUTH0=True,
        AUTH0_ADMIN_CLAIM_NAMESPACE="https://test.example.com/",
        AUTH0_SUPERUSER_SUB_ALLOWLIST=["auth0|allowlist_target"],
    )
    def test_demote_path_does_not_require_allowlist(self):
        """Demotion to is_superuser=False bypasses the allowlist gate."""
        from config.graphql_auth0_auth.utils import sync_admin_claims_from_payload

        # Start as superuser.
        self.user.is_superuser = True
        self.user.save()

        payload = {
            "sub": "auth0|allowlist_target",
            "https://test.example.com/is_superuser": False,
        }
        result = sync_admin_claims_from_payload(self.user, payload)
        self.user.refresh_from_db()
        self.assertTrue(result)
        self.assertFalse(self.user.is_superuser)


class TestAuth0SuperuserAllowlistSystemCheck(TestCase):
    """Tests for ``users.checks.check_auth0_superuser_allowlist``."""

    def setUp(self):
        # The initial-superuser migration leaves at least one is_superuser
        # row in the test DB. Demote them so the tests below can pin the
        # W001 (no existing superuser) vs E001 (existing superuser) branches
        # deterministically.
        User.objects.filter(is_superuser=True).update(is_superuser=False)

    @override_settings(USE_AUTH0=False)
    def test_check_silent_when_auth0_disabled(self):
        """Check returns no warnings if Auth0 is not in use."""
        from opencontractserver.users.checks import check_auth0_superuser_allowlist

        self.assertEqual(check_auth0_superuser_allowlist(None), [])

    @override_settings(USE_AUTH0=True, AUTH0_SUPERUSER_SUB_ALLOWLIST=[])
    def test_check_warns_when_allowlist_empty_and_no_superuser(self):
        """Empty allowlist with no existing superuser yields W001 (Warning)."""
        from opencontractserver.users.checks import check_auth0_superuser_allowlist

        # No is_superuser rows exist after setUp.
        warnings = check_auth0_superuser_allowlist(None)
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0].id, "users.W001")

    @override_settings(USE_AUTH0=True, AUTH0_SUPERUSER_SUB_ALLOWLIST=["auth0|allowed"])
    def test_check_silent_when_allowlist_populated(self):
        """Check emits no warning when the allowlist contains at least one sub."""
        from opencontractserver.users.checks import check_auth0_superuser_allowlist

        self.assertEqual(check_auth0_superuser_allowlist(None), [])

    @override_settings(USE_AUTH0=True, AUTH0_SUPERUSER_SUB_ALLOWLIST=[])
    def test_check_escalates_to_critical_with_existing_superuser(self):
        """Empty allowlist + existing superuser escalates to E001 (Critical)
        so ``manage.py check --deploy`` blocks the deploy that would lock
        out the only admin account."""
        from opencontractserver.users.checks import check_auth0_superuser_allowlist

        super_user = User.objects.create_user(
            username="auth0|test_super",
            email="super@example.com",
            is_superuser=True,
            is_staff=True,
        )
        issues = check_auth0_superuser_allowlist(None)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].id, "users.E001")
        # The eligible-superusers list must surface enough identity to
        # let an operator populate AUTH0_SUPERUSER_SUB_ALLOWLIST without
        # guessing — pk, username (Auth0 sub), and email if set.
        self.assertIn("auth0|test_super", issues[0].msg)
        self.assertIn(f"#{super_user.pk}", issues[0].msg)
        self.assertIn("super@example.com", issues[0].msg)


class TestBooleanClaimParsing(TestCase):
    """Tests for the _parse_boolean_claim helper function."""

    def test_parse_boolean_true(self):
        """Boolean True should be parsed correctly."""
        from config.graphql_auth0_auth.utils import _parse_boolean_claim

        value, valid = _parse_boolean_claim(True)
        self.assertTrue(valid)
        self.assertTrue(value)

    def test_parse_boolean_false(self):
        """Boolean False should be parsed correctly."""
        from config.graphql_auth0_auth.utils import _parse_boolean_claim

        value, valid = _parse_boolean_claim(False)
        self.assertTrue(valid)
        self.assertFalse(value)

    def test_parse_string_true_lowercase(self):
        """String 'true' should be parsed as True."""
        from config.graphql_auth0_auth.utils import _parse_boolean_claim

        value, valid = _parse_boolean_claim("true")
        self.assertTrue(valid)
        self.assertTrue(value)

    def test_parse_string_false_lowercase(self):
        """String 'false' should be parsed as False."""
        from config.graphql_auth0_auth.utils import _parse_boolean_claim

        value, valid = _parse_boolean_claim("false")
        self.assertTrue(valid)
        self.assertFalse(value)

    def test_parse_string_yes(self):
        """String 'yes' should be parsed as True."""
        from config.graphql_auth0_auth.utils import _parse_boolean_claim

        value, valid = _parse_boolean_claim("yes")
        self.assertTrue(valid)
        self.assertTrue(value)

    def test_parse_string_no(self):
        """String 'no' should be parsed as False."""
        from config.graphql_auth0_auth.utils import _parse_boolean_claim

        value, valid = _parse_boolean_claim("no")
        self.assertTrue(valid)
        self.assertFalse(value)

    def test_parse_string_1(self):
        """String '1' should be parsed as True."""
        from config.graphql_auth0_auth.utils import _parse_boolean_claim

        value, valid = _parse_boolean_claim("1")
        self.assertTrue(valid)
        self.assertTrue(value)

    def test_parse_string_0(self):
        """String '0' should be parsed as False."""
        from config.graphql_auth0_auth.utils import _parse_boolean_claim

        value, valid = _parse_boolean_claim("0")
        self.assertTrue(valid)
        self.assertFalse(value)

    def test_parse_int_1(self):
        """Integer 1 should be parsed as True."""
        from config.graphql_auth0_auth.utils import _parse_boolean_claim

        value, valid = _parse_boolean_claim(1)
        self.assertTrue(valid)
        self.assertTrue(value)

    def test_parse_int_0(self):
        """Integer 0 should be parsed as False."""
        from config.graphql_auth0_auth.utils import _parse_boolean_claim

        value, valid = _parse_boolean_claim(0)
        self.assertTrue(valid)
        self.assertFalse(value)

    def test_parse_none(self):
        """None should return (False, False)."""
        from config.graphql_auth0_auth.utils import _parse_boolean_claim

        value, valid = _parse_boolean_claim(None)
        self.assertFalse(valid)
        self.assertFalse(value)

    def test_parse_invalid_string(self):
        """Invalid string should return (False, False)."""
        from config.graphql_auth0_auth.utils import _parse_boolean_claim

        value, valid = _parse_boolean_claim("invalid")
        self.assertFalse(valid)
        self.assertFalse(value)


class TestAuth0AdminBackend(TestCase):
    """Tests for the Auth0 admin authentication backend."""

    @classmethod
    def setUpTestData(cls):
        cls.staff_user = User.objects.create_user(
            username="auth0|staff_user",
            email="staff@example.com",
            is_staff=True,
            is_active=True,
        )
        cls.non_staff_user = User.objects.create_user(
            username="auth0|regular_user",
            email="regular@example.com",
            is_staff=False,
            is_active=True,
        )
        cls.inactive_staff = User.objects.create_user(
            username="auth0|inactive_staff",
            email="inactive@example.com",
            is_staff=True,
            is_active=False,
        )
        cls.superuser = User.objects.create_superuser(
            username="auth0|superuser",
            email="super@example.com",
        )

    @override_settings(USE_AUTH0=True)
    def test_authenticate_staff_user(self):
        """Staff user should authenticate successfully."""
        from config.admin_auth.backends import Auth0AdminBackend

        backend = Auth0AdminBackend()
        user = backend.authenticate(None, auth0_user_id="auth0|staff_user")

        self.assertEqual(user, self.staff_user)

    @override_settings(USE_AUTH0=True)
    def test_authenticate_superuser(self):
        """Superuser should authenticate successfully."""
        from config.admin_auth.backends import Auth0AdminBackend

        backend = Auth0AdminBackend()
        user = backend.authenticate(None, auth0_user_id="auth0|superuser")

        self.assertEqual(user, self.superuser)

    @override_settings(USE_AUTH0=True)
    def test_non_staff_user_denied(self):
        """Non-staff user should be denied."""
        from config.admin_auth.backends import Auth0AdminBackend

        backend = Auth0AdminBackend()
        user = backend.authenticate(None, auth0_user_id="auth0|regular_user")

        self.assertIsNone(user)

    @override_settings(USE_AUTH0=True)
    def test_inactive_staff_denied(self):
        """Inactive staff user should be denied."""
        from config.admin_auth.backends import Auth0AdminBackend

        backend = Auth0AdminBackend()
        user = backend.authenticate(None, auth0_user_id="auth0|inactive_staff")

        self.assertIsNone(user)

    @override_settings(USE_AUTH0=True)
    def test_nonexistent_user_denied(self):
        """Non-existent user should be denied."""
        from config.admin_auth.backends import Auth0AdminBackend

        backend = Auth0AdminBackend()
        user = backend.authenticate(None, auth0_user_id="auth0|does_not_exist")

        self.assertIsNone(user)

    @override_settings(USE_AUTH0=True)
    def test_no_auth0_user_id_denied(self):
        """Missing auth0_user_id should return None."""
        from config.admin_auth.backends import Auth0AdminBackend

        backend = Auth0AdminBackend()
        user = backend.authenticate(None, auth0_user_id=None)

        self.assertIsNone(user)

    @override_settings(USE_AUTH0=False)
    def test_auth0_disabled_returns_none(self):
        """Backend should return None when Auth0 is disabled."""
        from config.admin_auth.backends import Auth0AdminBackend

        backend = Auth0AdminBackend()
        user = backend.authenticate(None, auth0_user_id="auth0|staff_user")

        self.assertIsNone(user)

    @override_settings(USE_AUTH0=True)
    def test_get_user_success(self):
        """get_user should return user by primary key."""
        from config.admin_auth.backends import Auth0AdminBackend

        backend = Auth0AdminBackend()
        user = backend.get_user(self.staff_user.pk)

        self.assertEqual(user, self.staff_user)

    @override_settings(USE_AUTH0=True)
    def test_get_user_not_found(self):
        """get_user should return None for non-existent user."""
        from config.admin_auth.backends import Auth0AdminBackend

        backend = Auth0AdminBackend()
        user = backend.get_user(99999)

        self.assertIsNone(user)


class TestAdminLoginView(TestCase):
    """Tests for the custom admin login view."""

    @classmethod
    def setUpTestData(cls):
        cls.staff_user = User.objects.create_user(
            username="admin_test",
            email="admin@example.com",
            password="testpass123",
            is_staff=True,
        )
        cls.regular_user = User.objects.create_user(
            username="regular_test",
            email="regular@example.com",
            password="testpass123",
            is_staff=False,
        )

    def setUp(self):
        self.client = Client()
        # Clear the rate-limit cache so each test starts with a fresh budget
        cache.clear()

    def test_get_login_page(self):
        """GET request should return login page."""
        response = self.client.get("/admin/login/")

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "admin/auth0_login.html")

    def test_password_login_success(self):
        """Staff user should be able to log in with password."""
        response = self.client.post(
            "/admin/login/",
            {
                "username": "admin_test",
                "password": "testpass123",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        # User should be authenticated
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_password_login_wrong_password(self):
        """Wrong password should fail."""
        response = self.client.post(
            "/admin/login/",
            {
                "username": "admin_test",
                "password": "wrongpassword",
            },
        )

        self.assertEqual(response.status_code, 302)  # Redirect back to login
        # Should have error message in session

    def test_password_login_non_staff(self):
        """Non-staff user should be denied even with correct password."""
        response = self.client.post(
            "/admin/login/",
            {
                "username": "regular_test",
                "password": "testpass123",
            },
        )

        self.assertEqual(response.status_code, 302)  # Redirect back to login

    def test_already_authenticated_redirects(self):
        """Already authenticated staff user should be redirected to admin."""
        self.client.force_login(self.staff_user)

        response = self.client.get("/admin/login/")

        self.assertEqual(response.status_code, 302)
        self.assertIn("admin", response.url)

    @patch("config.jwt_utils.get_user_from_jwt_token")
    def test_token_login_success(self, mock_get_user):
        """Valid token should authenticate staff user."""
        mock_get_user.return_value = self.staff_user

        response = self.client.post(
            "/admin/login/",
            {
                "token": "valid_test_token",
            },
        )

        self.assertEqual(response.status_code, 302)  # Redirect to admin
        mock_get_user.assert_called_once_with("valid_test_token")

    @patch("config.jwt_utils.get_user_from_jwt_token")
    def test_token_login_non_staff_denied(self, mock_get_user):
        """Valid token for non-staff user should be denied."""
        mock_get_user.return_value = self.regular_user

        response = self.client.post(
            "/admin/login/",
            {
                "token": "valid_test_token",
            },
        )

        self.assertEqual(response.status_code, 302)  # Redirect back to login

    @patch("config.jwt_utils.get_user_from_jwt_token")
    def test_token_login_invalid_token(self, mock_get_user):
        """Invalid token should show error."""
        mock_get_user.side_effect = Exception("Invalid token")

        response = self.client.post(
            "/admin/login/",
            {
                "token": "invalid_token",
            },
        )

        self.assertEqual(response.status_code, 302)  # Redirect back to login

    @patch("config.jwt_utils.get_user_from_jwt_token")
    @patch.object(
        __import__(
            "config.admin_auth.views", fromlist=["Auth0AdminLoginView"]
        ).Auth0AdminLoginView,
        "_sync_admin_claims",
        return_value=False,
    )
    def test_token_login_fails_on_claim_sync_error(self, mock_sync, mock_get_user):
        """Login should fail if claim sync fails to prevent stale permissions."""
        mock_get_user.return_value = self.staff_user

        response = self.client.post(
            "/admin/login/",
            {
                "token": "valid_test_token",
            },
        )

        # Login should fail when claim sync returns False
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)
        mock_get_user.assert_called_once_with("valid_test_token")
        mock_sync.assert_called_once()

    @override_settings(
        USE_AUTH0=True, AUTH0_ADMIN_CLAIM_NAMESPACE="https://test.example.com/"
    )
    @patch("config.graphql_auth0_auth.utils.get_payload")
    @patch("config.jwt_utils.get_user_from_jwt_token")
    def test_admin_login_revokes_staff_when_claim_false(
        self, mock_get_user, mock_get_payload
    ):
        """Admin login with is_staff=False claim should revoke staff access and deny login."""
        # User is currently staff
        self.staff_user.is_staff = True
        self.staff_user.save()

        mock_get_user.return_value = self.staff_user
        mock_get_payload.return_value = {
            "sub": self.staff_user.username,
            "https://test.example.com/is_staff": False,
        }

        response = self.client.post(
            "/admin/login/",
            {
                "token": "valid_test_token",
            },
        )

        # Should be denied (no longer staff)
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

        # Verify is_staff was actually revoked
        self.staff_user.refresh_from_db()
        self.assertFalse(self.staff_user.is_staff)

    @override_settings(USE_AUTH0=True)
    def test_login_page_shows_auth0_button(self):
        """Login page should show Auth0 button when USE_AUTH0=True."""
        response = self.client.get("/admin/login/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sign in with Auth0")

    @override_settings(USE_AUTH0=False)
    def test_login_page_hides_auth0_button(self):
        """Login page should hide Auth0 button when USE_AUTH0=False."""
        response = self.client.get("/admin/login/")

        self.assertEqual(response.status_code, 200)
        # Auth0 button should not be in content

    def test_open_redirect_blocked_external_url(self):
        """External URL in next parameter should be blocked."""
        response = self.client.post(
            "/admin/login/",
            {
                "username": "admin_test",
                "password": "testpass123",
                "next": "https://evil.com/steal-cookies",
            },
            follow=False,
        )

        self.assertEqual(response.status_code, 302)
        # Should redirect to admin, not evil.com
        self.assertNotIn("evil.com", response.url)
        self.assertIn("admin", response.url)

    def test_open_redirect_blocked_protocol_relative(self):
        """Protocol-relative URL in next parameter should be blocked."""
        response = self.client.post(
            "/admin/login/",
            {
                "username": "admin_test",
                "password": "testpass123",
                "next": "//evil.com/steal-cookies",
            },
            follow=False,
        )

        self.assertEqual(response.status_code, 302)
        # Should redirect to admin, not evil.com
        self.assertNotIn("evil.com", response.url)
        self.assertIn("admin", response.url)

    def test_open_redirect_blocked_backslash(self):
        """Backslash-prefixed URL in next parameter should be blocked.

        Browsers normalize ``\\evil.com`` to ``//evil.com``, which can bypass
        protocol-relative URL checks.
        """
        response = self.client.post(
            "/admin/login/",
            {
                "username": "admin_test",
                "password": "testpass123",
                "next": "\\evil.com/steal-cookies",
            },
            follow=False,
        )

        self.assertEqual(response.status_code, 302)
        # Should redirect to admin, not evil.com
        self.assertNotIn("evil.com", response.url)
        self.assertIn("admin", response.url)

    def test_valid_internal_redirect_allowed(self):
        """Valid internal URL in next parameter should be allowed."""
        response = self.client.post(
            "/admin/login/",
            {
                "username": "admin_test",
                "password": "testpass123",
                "next": "/admin/users/",
            },
            follow=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/admin/users/")

    def test_open_redirect_blocked_in_get_next_param(self):
        """External URL in GET next parameter should be sanitized in context."""
        response = self.client.get("/admin/login/?next=https://evil.com/")

        self.assertEqual(response.status_code, 200)
        # The next value in context should be safe
        self.assertNotIn("evil.com", response.content.decode())


class TestAdminLogoutView(TestCase):
    """Tests for the custom admin logout view."""

    @classmethod
    def setUpTestData(cls):
        cls.staff_user = User.objects.create_user(
            username="logout_test",
            email="logout@example.com",
            password="testpass123",
            is_staff=True,
        )

    def setUp(self):
        self.client = Client()

    def test_logout_clears_session(self):
        """Logout via POST should clear user session."""
        self.client.force_login(self.staff_user)

        response = self.client.post("/admin/logout/")

        # Session should be cleared after logout
        self.assertEqual(response.status_code, 302)

    def test_logout_get_returns_405_for_authenticated_user(self):
        """Logout via GET should return 405 Method Not Allowed for authenticated users."""
        self.client.force_login(self.staff_user)

        response = self.client.get("/admin/logout/")

        self.assertEqual(response.status_code, 405)

    def test_logout_get_redirects_for_unauthenticated_user(self):
        """Logout via GET should redirect unauthenticated users to admin."""
        response = self.client.get("/admin/logout/")

        self.assertEqual(response.status_code, 302)
        self.assertIn("admin", response.url)

    @override_settings(USE_AUTH0=False)
    def test_logout_redirects_to_admin_when_auth0_disabled(self):
        """Logout should redirect to admin when Auth0 is disabled."""
        self.client.force_login(self.staff_user)

        response = self.client.post("/admin/logout/")

        self.assertEqual(response.status_code, 302)
        self.assertIn("admin", response.url)

    @override_settings(
        USE_AUTH0=True,
        AUTH0_DOMAIN="test.auth0.com",
        AUTH0_CLIENT_ID="test_client_id",
    )
    def test_logout_redirects_to_auth0_when_enabled(self):
        """Logout should redirect to Auth0 logout URL when Auth0 is enabled."""
        self.client.force_login(self.staff_user)

        response = self.client.post("/admin/logout/")

        self.assertEqual(response.status_code, 302)
        self.assertIn("test.auth0.com", response.url)
        self.assertIn("logout", response.url)

    @override_settings(
        USE_AUTH0=True,
        AUTH0_DOMAIN="test.auth0.com",
        AUTH0_CLIENT_ID="test_client_id",
        ALLOWED_HOSTS=["example.com", "localhost", "testserver"],
    )
    def test_logout_uses_safe_return_url(self):
        """Logout should use a safe return URL from ALLOWED_HOSTS."""
        self.client.force_login(self.staff_user)

        response = self.client.post("/admin/logout/")

        self.assertEqual(response.status_code, 302)
        # returnTo should be URL-encoded and use a safe host
        self.assertIn("returnTo=", response.url)
        # Should prefer the request host when it is allowed
        self.assertIn("testserver", response.url)
        # Should redirect to admin login page, not root
        self.assertIn("admin%2Flogin", response.url)

    @override_settings(ALLOWED_HOSTS=[])
    def test_get_safe_logout_return_url_raises_without_valid_hosts(self):
        """_get_safe_logout_return_url should raise ImproperlyConfigured without valid hosts."""
        from unittest.mock import MagicMock

        from django.core.exceptions import ImproperlyConfigured

        from config.admin_auth.views import _get_safe_logout_return_url

        # Create a mock request
        mock_request = MagicMock()
        mock_request.get_host.return_value = "evil.com"
        mock_request.is_secure.return_value = False

        with self.assertRaises(ImproperlyConfigured) as context:
            _get_safe_logout_return_url(mock_request)

        self.assertIn("ALLOWED_HOSTS", str(context.exception))
        self.assertIn("non-wildcard", str(context.exception))


class TestGetUserByPayloadWithClaimSync(TestCase):
    """Integration tests for get_user_by_payload with claim syncing."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="auth0|integration_test",
            email="integration@example.com",
            is_staff=False,
            is_superuser=False,
            is_active=True,
        )

    def setUp(self):
        self.user.refresh_from_db()
        self.user.is_staff = False
        self.user.is_superuser = False
        self.user.save()

    @override_settings(
        USE_AUTH0=True,
        AUTH0_ADMIN_CLAIM_NAMESPACE="https://test.example.com/",
        AUTH0_SUPERUSER_SUB_ALLOWLIST=["auth0|integration_test"],
    )
    @patch("django.core.cache.cache")
    def test_sync_claims_cached_handles_cache_failure(self, mock_cache):
        """_sync_admin_claims_cached should sync claims even when cache fails."""
        from config.graphql_auth0_auth.utils import _sync_admin_claims_cached

        # Simulate cache failure
        mock_cache.get.side_effect = Exception("Cache unavailable")
        mock_cache.set.side_effect = Exception("Cache unavailable")

        payload = {
            "sub": self.user.username,
            "https://test.example.com/is_staff": True,
            "https://test.example.com/is_superuser": True,
        }

        # Should not raise, and should still sync claims
        _sync_admin_claims_cached(self.user, payload)

        # Verify claims were synced despite cache failure
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_staff)
        self.assertTrue(self.user.is_superuser)

    @override_settings(
        USE_AUTH0=True,
        AUTH0_ADMIN_CLAIM_NAMESPACE="https://test.example.com/",
        AUTH0_SUPERUSER_SUB_ALLOWLIST=["auth0|integration_test"],
        AUTH0_ADMIN_CLAIMS_CACHE_TTL=7,
    )
    def test_admin_claims_cache_ttl_env_override(self):
        """The ``AUTH0_ADMIN_CLAIMS_CACHE_TTL`` setting overrides the default TTL.

        We patch the cache so the sync path always runs, then assert that
        ``cache.set`` is invoked with the overridden timeout instead of the
        module-level constant.
        """
        from unittest.mock import MagicMock
        from unittest.mock import patch as _patch

        from config.graphql_auth0_auth.utils import _sync_admin_claims_cached

        payload = {
            "sub": self.user.username,
            "https://test.example.com/is_staff": True,
            "https://test.example.com/is_superuser": True,
        }

        fake_cache = MagicMock()
        fake_cache.get.return_value = None
        with _patch("django.core.cache.cache", fake_cache):
            _sync_admin_claims_cached(self.user, payload)

        fake_cache.set.assert_called_once()
        kwargs = fake_cache.set.call_args.kwargs
        args = fake_cache.set.call_args.args
        timeout = kwargs.get("timeout", args[2] if len(args) > 2 else None)
        self.assertEqual(timeout, 7)

    @override_settings(USE_AUTH0=False)
    def test_admin_claims_cached_noop_when_auth0_disabled(self):
        """``_sync_admin_claims_cached`` is a no-op when Auth0 is disabled."""
        from config.graphql_auth0_auth.utils import _sync_admin_claims_cached

        self.user.is_staff = False
        self.user.is_superuser = False
        self.user.save()

        payload = {
            "sub": self.user.username,
            "https://test.example.com/is_staff": True,
            "https://test.example.com/is_superuser": True,
        }
        _sync_admin_claims_cached(self.user, payload)

        self.user.refresh_from_db()
        self.assertFalse(self.user.is_staff)
        self.assertFalse(self.user.is_superuser)


@override_settings(
    RATELIMIT_DISABLE=False,
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "admin-login-ratelimit-test",
        }
    },
)
class TestAdminLoginRateLimit(TestCase):
    """Tests for rate limiting on the admin login endpoint."""

    @classmethod
    def setUpTestData(cls):
        cls.staff_user = User.objects.create_user(
            username="ratelimit_test",
            email="ratelimit@example.com",
            password="testpass123",
            is_staff=True,
        )

    def setUp(self):
        self.client = Client()
        # Clear the rate-limit cache before each test to ensure isolation
        cache.clear()

    @patch("config.ratelimit.engine.time")
    def test_post_rate_limit_returns_429(self, mock_time):
        """Login POST should return 429 after exceeding the rate limit."""
        # Pin time so all requests land in the same rate-limit window.
        mock_time.time.return_value = 12345.0
        # Default rate is 5/m. Send 5 requests to exhaust the limit.
        for _ in range(5):
            self.client.post(
                "/admin/login/",
                {"username": "wrong", "password": "wrong"},
            )

        # The 6th request should be rate-limited
        response = self.client.post(
            "/admin/login/",
            {"username": "wrong", "password": "wrong"},
        )

        self.assertEqual(response.status_code, 429)
        data = response.json()
        self.assertIn("error", data)
        self.assertIn("Too many login attempts", data["error"])

    @patch("config.ratelimit.engine.time")
    def test_post_rate_limit_json_content_type(self, mock_time):
        """Rate-limited POST should return application/json."""
        mock_time.time.return_value = 12345.0
        for _ in range(5):
            self.client.post(
                "/admin/login/",
                {"username": "wrong", "password": "wrong"},
            )

        response = self.client.post(
            "/admin/login/",
            {"username": "wrong", "password": "wrong"},
        )

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response["Content-Type"], "application/json")

    def test_successful_login_still_works_within_limit(self):
        """Valid credentials should still succeed within the rate limit."""
        response = self.client.post(
            "/admin/login/",
            {"username": "ratelimit_test", "password": "testpass123"},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    @patch("config.ratelimit.engine.time")
    def test_get_rate_limit_returns_429(self, mock_time):
        """Login page GET should return 429 after exceeding the rate limit."""
        mock_time.time.return_value = 12345.0
        # Default GET rate is 20/m. Send 20 requests to exhaust.
        for _ in range(20):
            self.client.get("/admin/login/")

        response = self.client.get("/admin/login/")

        self.assertEqual(response.status_code, 429)
        self.assertIn(
            "Too many requests",
            response.content.decode(),
        )

    @patch("config.ratelimit.engine.time")
    def test_get_rate_limit_plain_text(self, mock_time):
        """Rate-limited GET should return text/plain."""
        mock_time.time.return_value = 12345.0
        for _ in range(20):
            self.client.get("/admin/login/")

        response = self.client.get("/admin/login/")

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response["Content-Type"], "text/plain")
