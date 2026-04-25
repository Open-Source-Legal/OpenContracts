"""Regression tests for shared-state mutation in ``User.username`` validators."""

from django.contrib.auth import get_user_model
from django.test import TestCase

from opencontractserver.users.validators import UserUnicodeUsernameValidator

User = get_user_model()


class UsernameValidatorRegressionTests(TestCase):
    """Guardrails against shared-state mutation of ``User.username`` validators."""

    def test_username_field_has_opencontracts_validator(self):
        """The custom validator must be declared on the field, not patched in."""
        field = User._meta.get_field("username")
        self.assertTrue(
            any(isinstance(v, UserUnicodeUsernameValidator) for v in field.validators),
            "Expected UserUnicodeUsernameValidator to be declared on User.username",
        )

    def test_permissive_characters_accepted(self):
        """Usernames containing ``\\``, ``|``, and ``*`` must pass validation."""
        permissive_username = r"name\with|pipes*and-slash"
        user = User(username=permissive_username, email="perm@example.com")
        # full_clean() runs every validator on the field; should not raise.
        user.full_clean(exclude=["password"])

    def test_validators_list_stable_across_instantiations(self):
        """Creating many ``User`` instances must not grow/shrink the validators list."""
        field = User._meta.get_field("username")
        baseline = list(field.validators)
        baseline_len = len(baseline)

        for i in range(100):
            User(username=f"stable_user_{i}", email=f"stable{i}@example.com")

        self.assertEqual(
            len(field.validators),
            baseline_len,
            "User instantiation mutated the shared Field.validators list.",
        )
        # Identity of each validator should also be preserved — we should not be
        # rebinding ``validators[0]`` on every ``User(...)`` call.
        for before, after in zip(baseline, field.validators):
            self.assertIs(
                before,
                after,
                "A validator on User.username was replaced during instantiation.",
            )

    def test_third_party_prepend_does_not_corrupt_username_validator(self):
        """A third-party validator prepended to ``Field.validators`` must survive ``User`` instantiation."""
        from django.core.validators import RegexValidator

        field = User._meta.get_field("username")
        sentinel = RegexValidator(regex=r".*", message="sentinel")
        field.validators.insert(0, sentinel)
        try:
            # Instantiate a few users — previously this would reassign
            # ``validators[0]`` and overwrite the sentinel.
            for i in range(5):
                User(username=f"corrupt_check_{i}")

            self.assertIs(
                field.validators[0],
                sentinel,
                "User.__init__ should not mutate Field.validators",
            )
            self.assertTrue(
                any(
                    isinstance(v, UserUnicodeUsernameValidator)
                    for v in field.validators
                ),
                "UserUnicodeUsernameValidator must remain in the validators list",
            )
        finally:
            field.validators.remove(sentinel)
