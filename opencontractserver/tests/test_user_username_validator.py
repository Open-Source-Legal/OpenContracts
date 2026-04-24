r"""
Regression tests for issue #1358.

Before the fix, ``User.__init__`` mutated the shared
``User._meta.get_field("username").validators`` list on every instantiation.
That was fragile: if any third-party code prepended its own validator, the
``validators[0]`` assignment silently replaced the wrong slot and OpenContracts'
permissive username rules (which allow ``\``, ``|``, ``*``) could flip back to
Django's stricter default.

The fix declares the ``UserUnicodeUsernameValidator`` on the ``User.username``
field at class-body time, so there is no runtime mutation.
"""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from opencontractserver.users.validators import UserUnicodeUsernameValidator

User = get_user_model()


class UsernameValidatorRegressionTests(TestCase):
    """Guardrails against regressing issue #1358."""

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
        # full_clean() runs every validator on the field.
        try:
            user.full_clean(exclude=["password"])
        except ValidationError as exc:
            self.assertNotIn(
                "username",
                exc.message_dict,
                f"Permissive username rejected: {exc.message_dict}",
            )

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
        """
        Simulate a third-party package prepending its own validator. Before the
        fix, ``validators[0] = UserUnicodeUsernameValidator()`` in ``__init__``
        would clobber the third-party validator and silently fall back to
        Django's default validator for the OpenContracts slot.
        """
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
