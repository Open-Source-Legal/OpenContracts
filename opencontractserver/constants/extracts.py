"""
Extract-related constants.

Centralises pagination and display limits used by the extract grid embed
feature and its GraphQL resolvers.

The frontend mirrors ``MAX_FULL_DATACELL_LIST_LIMIT`` as
``EXTRACT_GRID_EMBED_CELL_LIMIT`` in
``frontend/src/assets/configurations/constants.ts``. Keep the two values
in sync when adjusting.
"""

# Server-enforced upper bound on the number of datacells returned by
# ``ExtractType.resolve_full_datacell_list``. Prevents authenticated
# callers from bypassing the intended payload cap by passing an
# arbitrarily large limit (or no limit at all) via the GraphQL API —
# all code paths (no-args, offset-only, limit+offset) are bounded by
# this value.
#
# IMPORTANT: If you change this value, update the frontend constant
# ``EXTRACT_GRID_EMBED_CELL_LIMIT`` in
# ``frontend/src/assets/configurations/constants.ts`` at the same time.
# An automated CI sync-check is tracked in issue #1256.
MAX_FULL_DATACELL_LIST_LIMIT = 500

# Server cap on the ``extracts`` Relay connection page size. Must be >=
# the frontend ``EXTRACT_PAGINATION.PAGE_SIZE`` in
# ``frontend/src/assets/configurations/constants.ts``; otherwise Graphene
# silently clamps every request and the slim list query is back to the
# pre-#1602 broken-pagination shape.
EXTRACT_LIST_MAX_PAGE_SIZE = 20
