"""
Authentication-related constants.
"""

# Number of characters to show when logging token prefixes for debugging
TOKEN_LOG_PREFIX_LENGTH = 10

# Cache TTL for admin claims sync (in seconds).
# Admin claims are re-synced from each verified Auth0 token at most once per
# this window per user. The window bounds the privilege-retention gap when
# Auth0 demotes a user: at worst, the Django ``is_staff``/``is_superuser``
# flags remain stale until the next sync after the cache expires. 30 seconds
# trades a small write-rate increase for a tight revocation SLA. Admin login
# bypasses this cache and always re-syncs.
ADMIN_CLAIMS_CACHE_TTL = 30

# Default grace window for server-nudged WebSocket auth refresh.
# When a consumer calls AuthHandshakeMixin.request_token_refresh() it sends
# AUTH_REFRESH_REQUIRED to the client and starts a timer; if the client
# does not reply with a fresh token within this window the socket is closed
# 4001 (TOKEN_EXPIRED). Sized to comfortably cover Auth0 silent renewal
# (a few seconds in practice) plus retry headroom.
WS_AUTH_REFRESH_GRACE_SECONDS = 30.0

# Length of the OAuth ``sub`` suffix surfaced as the redacted display name
# fallback (``user_<last N chars>``). Long enough to stay reasonably unique
# across users in the same UI context, short enough that the redacted form
# does not effectively expose the full sub. See ``UserType.resolve_display_name``
# (issue #1557).
#
# Mirrored in
# ``frontend/src/assets/configurations/constants.ts::REDACTED_HANDLE_PK_SUFFIX_LENGTH``
# so both ends of the privacy contract render the same fallback. If you change
# this number, change the frontend constant in the same commit.
OAUTH_SUB_DISPLAY_SUFFIX_LENGTH = 6
