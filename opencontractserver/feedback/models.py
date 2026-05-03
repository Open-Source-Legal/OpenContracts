from django.core.exceptions import ValidationError
from django.db import models
from guardian.models import GroupObjectPermissionBase, UserObjectPermissionBase

from opencontractserver.annotations.models import Annotation
from opencontractserver.shared.defaults import jsonfield_default_value
from opencontractserver.shared.fields import NullableJSONField
from opencontractserver.shared.Managers import UserFeedbackManager
from opencontractserver.shared.Models import BaseOCModel


class UserFeedback(BaseOCModel):
    # django-stubs flags re-declaring ``objects`` as overriding a class
    # variable with an instance variable; intentional manager override.
    objects = UserFeedbackManager()  # type: ignore[misc]

    approved = models.BooleanField(default=False)
    rejected = models.BooleanField(default=False)
    comment = models.TextField(blank=True, default="", null=False)
    markdown = models.TextField(blank=True, default="", null=False)
    metadata = NullableJSONField(default=jsonfield_default_value, null=True, blank=True)
    commented_annotation = models.ForeignKey(
        Annotation,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="user_feedback",
    )

    class Meta:
        permissions = (
            ("permission_userfeedback", "permission UserFeedback"),
            ("publish_userfeedback", "publish UserFeedback"),
            ("create_userfeedback", "create UserFeedback"),
            ("read_userfeedback", "read UserFeedback"),
            ("update_userfeedback", "update UserFeedback"),
            ("remove_userfeedback", "delete UserFeedback"),
            ("comment_userfeedback", "comment UserFeedback"),
        )

    def clean(self):
        if self.approved and self.rejected:
            if self._state.adding:
                raise ValidationError("Both approved and rejected cannot be True.")
            else:
                # If updating, set the original value to False
                original = UserFeedback.objects.get(pk=self.pk)
                if original.approved != self.approved:
                    self.rejected = False
                else:
                    self.approved = False

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)


# Model for Django Guardian permissions... trying to improve performance...
class UserFeedbackUserObjectPermission(UserObjectPermissionBase):
    content_object = models.ForeignKey("UserFeedback", on_delete=models.CASCADE)
    # enabled = False


# Model for Django Guardian permissions... trying to improve performance...
class UserFeedbackGroupObjectPermission(GroupObjectPermissionBase):
    content_object = models.ForeignKey("UserFeedback", on_delete=models.CASCADE)
    # enabled = False
