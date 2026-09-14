from django.contrib import admin

from opencontractserver.feedback.models import UserFeedback
from opencontractserver.shared.admin import GuardedModelAdmin


@admin.register(UserFeedback)
class AnnotationAdmin(GuardedModelAdmin):
    list_display = ["id", "approved", "rejected", "comment", "creator"]
    list_filter = ("approved", "rejected")
