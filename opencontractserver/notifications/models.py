"""
Notification models for the OpenContracts notification system.

This module implements Epic #562: Notification System
"""

import re

from django.contrib.auth import get_user_model
from django.db import models

from opencontractserver.shared.defaults import jsonfield_default_value
from opencontractserver.shared.fields import NullableJSONField

User = get_user_model()


class NotificationTypeChoices(models.TextChoices):
    """Types of notifications that can be sent to users."""

    REPLY = "REPLY", "Reply to Message"
    VOTE = "VOTE", "Vote on Message"
    BADGE = "BADGE", "Badge Awarded"
    MENTION = "MENTION", "Mentioned in Message"
    ACCEPTED = "ACCEPTED", "Answer Accepted"
    THREAD_LOCKED = "THREAD_LOCKED", "Thread Locked"
    THREAD_UNLOCKED = "THREAD_UNLOCKED", "Thread Unlocked"
    THREAD_PINNED = "THREAD_PINNED", "Thread Pinned"
    THREAD_UNPINNED = "THREAD_UNPINNED", "Thread Unpinned"
    MESSAGE_DELETED = "MESSAGE_DELETED", "Message Deleted"
    THREAD_DELETED = "THREAD_DELETED", "Thread Deleted"
    MESSAGE_RESTORED = "MESSAGE_RESTORED", "Message Restored"
    THREAD_RESTORED = "THREAD_RESTORED", "Thread Restored"
    THREAD_REPLY = "THREAD_REPLY", "Reply in Thread You're Participating In"


class Notification(models.Model):
    """
    Represents a notification to a user about an event in the system.

    Notifications are created automatically via signals when certain events occur:
    - User receives a reply to their message
    - User's message receives a vote
    - User is awarded a badge
    - User is mentioned in a message
    - User's thread/message is moderated
    - Someone replies in a thread the user is participating in
    """

    recipient = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="notifications",
        help_text="User receiving this notification",
        db_index=True,
    )

    notification_type = models.CharField(
        max_length=20,
        choices=NotificationTypeChoices.choices,
        help_text="Type of notification",
    )

    message = models.ForeignKey(
        "conversations.ChatMessage",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="notifications",
        help_text="Related message if applicable",
    )

    conversation = models.ForeignKey(
        "conversations.Conversation",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="notifications",
        help_text="Related conversation/thread if applicable",
    )

    actor = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="notifications_triggered",
        help_text="User who triggered this notification (if applicable)",
    )

    is_read = models.BooleanField(
        default=False,
        help_text="Whether the notification has been read",
        db_index=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the notification was created",
        db_index=True,
    )

    modified = models.DateTimeField(
        auto_now=True,
        help_text="When the notification was last modified",
    )

    data = NullableJSONField(
        default=jsonfield_default_value,
        blank=True,
        null=True,
        help_text="Additional context data for the notification (e.g., vote type, badge info)",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient", "-created_at"]),
            models.Index(fields=["recipient", "is_read"]),
            models.Index(fields=["notification_type"]),
            models.Index(fields=["conversation"]),
            models.Index(fields=["message"]),
        ]

    def __str__(self):
        return (
            f"{self.get_notification_type_display()} "
            f"for {self.recipient.username} "
            f"({'read' if self.is_read else 'unread'})"
        )

    def mark_as_read(self):
        """Mark this notification as read."""
        if not self.is_read:
            self.is_read = True
            self.save(update_fields=["is_read", "modified"])

    def mark_as_unread(self):
        """Mark this notification as unread."""
        if self.is_read:
            self.is_read = False
            self.save(update_fields=["is_read", "modified"])

    @staticmethod
    def extract_mentions(text: str) -> list[str]:
        """
        Extract @username mentions from text.

        Args:
            text: The text to search for mentions

        Returns:
            List of mentioned usernames (without the @ symbol)
        """
        if not text:
            return []

        # Match @username - alphanumeric, underscores, and hyphens
        # Must be preceded by whitespace or start of string
        # Must be followed by whitespace, punctuation, or end of string
        pattern = r"(?:^|(?<=\s))@([\w-]+)(?=\s|[.,!?;:]|$)"
        matches = re.findall(pattern, text)

        # Return unique usernames (case-insensitive deduplication)
        seen = set()
        unique_matches = []
        for match in matches:
            lower_match = match.lower()
            if lower_match not in seen:
                seen.add(lower_match)
                unique_matches.append(match)

        return unique_matches
