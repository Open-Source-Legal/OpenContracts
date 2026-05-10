"""
Authentication-related constants.
"""

# Number of characters to show when logging token prefixes for debugging
TOKEN_LOG_PREFIX_LENGTH = 10

# Cache TTL for admin claims sync (in seconds)
# Admin claims are synced from Auth0 tokens periodically to balance security
# and performance. This TTL controls how often claims are re-synced.
# 5 minutes = 300 seconds
ADMIN_CLAIMS_CACHE_TTL = 300

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
