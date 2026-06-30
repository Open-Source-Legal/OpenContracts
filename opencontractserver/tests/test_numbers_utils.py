"""Unit tests for opencontractserver.utils.numbers."""

from django.test import TestCase

from opencontractserver.utils.numbers import clamp_int


class ClampIntTests(TestCase):
    def test_in_range_value_passes_through(self):
        self.assertEqual(clamp_int(5, lower=0, upper=10), 5)

    def test_below_lower_clamps_to_lower(self):
        self.assertEqual(clamp_int(-3, lower=0, upper=10), 0)

    def test_above_upper_clamps_to_upper(self):
        self.assertEqual(clamp_int(99, lower=0, upper=10), 10)

    def test_boundaries_are_inclusive(self):
        self.assertEqual(clamp_int(0, lower=0, upper=10), 0)
        self.assertEqual(clamp_int(10, lower=0, upper=10), 10)

    def test_non_integer_value_falls_back_to_lower(self):
        # None / non-numeric strings exercise the coercion fallback; the
        # suppressions below mark the deliberate off-type inputs.
        self.assertEqual(clamp_int(None, lower=3, upper=10), 3)  # type: ignore[arg-type]
        self.assertEqual(
            clamp_int("not-a-number", lower=5, upper=20), 5  # type: ignore[arg-type]
        )

    def test_numeric_string_is_coerced(self):
        self.assertEqual(clamp_int("7", lower=0, upper=10), 7)  # type: ignore[arg-type]
