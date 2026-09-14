# Register your models here.
from django.contrib import admin

from opencontractserver.conversations.models import ChatMessage, Conversation
from opencontractserver.shared.admin import GuardedModelAdmin


@admin.register(Conversation)
class ConversationAdmin(GuardedModelAdmin):
    list_display_links = ["id", "title"]
    list_display = [
        "id",
        "title",
        "created_at",
    ]
    search_fields = ["id", "title", "creator__username"]
    list_filter = ("is_public", "created", "modified")
    raw_id_fields = ("creator", "chat_with_document", "chat_with_corpus")
    date_hierarchy = "created_at"


@admin.register(ChatMessage)
class ChatMessageAdmin(GuardedModelAdmin):
    list_display_links = ["id"]
    list_display = [
        "id",
        "msg_type",
        "content",
        "created_at",
        "source_document",
    ]
    search_fields = ["id", "content", "creator__username"]
    list_filter = ("msg_type",)
    raw_id_fields = (
        "creator",
        "created_annotations",
        "source_annotations",
        "source_document",
    )
    date_hierarchy = "created_at"
