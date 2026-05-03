"""
Authentication-related constants.
"""

# Cache TTL for admin claims sync (in seconds)
# Admin claims are synced from Auth0 tokens periodically to balance security
# and performance. This TTL controls how often claims are re-synced.
# 5 minutes = 300 seconds
ADMIN_CLAIMS_CACHE_TTL = 300
