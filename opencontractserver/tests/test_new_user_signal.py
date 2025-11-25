from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

User = get_user_model()


class UserSignalsTestCase(TestCase):
    def setUp(self):
        # Set up arbitrary_function mock
        self.arbitrary_function_patcher = patch(
            "opencontractserver.users.signals.record_event"
        )
        self.mock_arbitrary_function = self.arbitrary_function_patcher.start()

        # Record initial user count for assertions
        self.initial_user_count = User.objects.count()

    def tearDown(self):
        self.arbitrary_function_patcher.stop()

    def test_user_created_signal_on_create(self):
        """Test that arbitrary_function is called when a new user is created"""
        User.objects.create(
            username="testuser_signal_create",
            email="testsigcreate@example.com",
            password="testpass123",
        )

        # Verify the signal was called with the correct event and the new user count
        expected_user_count = self.initial_user_count + 1
        self.mock_arbitrary_function.assert_called_once_with(
            "user_created", {"user_count": expected_user_count}
        )

    def test_user_created_signal_on_update(self):
        """Test that arbitrary_function is not called when a user is updated"""
        # First create the user
        user = User.objects.create(
            username="testuser_signal_update",
            email="testsigupdate@example.com",
            password="testpass123",
        )

        # Reset the mock to clear the creation call
        self.mock_arbitrary_function.reset_mock()

        # Update the user
        user.email = "newemail@example.com"
        user.save()

        # Verify arbitrary_function was not called
        self.mock_arbitrary_function.assert_not_called()

    def test_user_created_signal_with_multiple_users(self):
        """Test that arbitrary_function is called for each new user created"""
        # Clear the mock to ensure we only check calls from this test
        self.mock_arbitrary_function.reset_mock()

        num_users_to_create = 3
        [
            User.objects.create(
                username=f"testuser_multi_{i}",
                email=f"testmulti{i}@example.com",
                password="testpass123",
            )
            for i in range(num_users_to_create)
        ]

        # Verify arbitrary_function was called for each user
        self.assertEqual(self.mock_arbitrary_function.call_count, num_users_to_create)

        # Get all the calls made to the mock
        actual_calls = self.mock_arbitrary_function.call_args_list

        # Verify all calls used the correct event name and incrementing user counts
        for idx, call in enumerate(actual_calls):
            self.assertEqual(call[0][0], "user_created")
            expected_count = self.initial_user_count + idx + 1
            self.assertEqual(call[0][1]["user_count"], expected_count)
