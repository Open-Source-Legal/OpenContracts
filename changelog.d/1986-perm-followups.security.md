- Permissioning audit follow-ups from issue #1986 (filter/check parity + safe
  error handling):
  - **Anonymous chat-message visibility now follows the conversation
    bifurcation (item 2).** `ChatMessageQuerySet.visible_to_user`
    (`opencontractserver/conversations/models.py`) previously filtered the
    anonymous branch on `conversation__is_public=True` alone, which exposed a
    public **CHAT**'s messages even though `ConversationQuerySet.visible_to_user`
    keeps the conversation itself hidden from anonymous users (anonymous can
    only see THREADs). The branch now delegates to
    `Conversation.objects.visible_to_user`, so message visibility inherits the
    single-source-of-truth CHAT/THREAD rules — no public-CHAT message leak, and
    messages in context-inherited public-resource threads are correctly visible.
  - **Conversation and chat-message querysets now honour group-level READ
    grants (item 3).** `ConversationQuerySet` / `ChatMessageQuerySet`
    `visible_to_user` consulted only the USER object-permission tables. Because
    `ConversationManager.user_can(READ)` / `ChatMessageManager.user_can(READ)`
    route back through `visible_to_user`, a group-only READ grant was both
    invisible in lists AND denied by `user_can(READ)` — even though non-READ
    writes (via `_default_user_can`) honoured the same group grant. Both
    querysets now join the `*groupobjectpermission` tables (mirroring
    `BaseVisibilityManager`), closing the same group-grant gap PR #1985 fixed for
    annotations / relationships / extracts.
  - **`BaseVisibilityManager.visible_to_user` no longer swallows unexpected
    errors (item 4).** The guardian-lookup fallback caught
    `(ImportError, Exception)` — equivalent to a bare `except Exception` — so any
    error silently degraded the queryset to creator/public filtering,
    under-disclosing guardian-granted rows while hiding the defect
    (`opencontractserver/shared/Managers.py`). The catch is narrowed to
    `(ImportError, LookupError)` so a genuinely-absent permission table still
    falls back gracefully, but programming/database errors now propagate.
