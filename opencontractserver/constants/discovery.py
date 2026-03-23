"""Constants for the discovery module (robots.txt, llms.txt, sitemap, etc.)."""

# Cache discovery responses for 5 minutes to avoid repeated DB hits
DISCOVERY_CACHE_SECONDS = 300

# Upper bound on the number of public corpuses returned by discovery endpoints
# to prevent memory issues with very large public corpus sets.
MAX_PUBLIC_CORPUSES = 500

# Maximum number of results the public search API will return per request.
MAX_SEARCH_RESULTS = 50
