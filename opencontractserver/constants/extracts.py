"""
Extract-related constants.

Centralises pagination and display limits used by the extract grid embed
feature and its GraphQL resolvers.

The frontend mirrors ``MAX_FULL_DATACELL_LIST_LIMIT`` as
``EXTRACT_GRID_EMBED_CELL_LIMIT`` in
``frontend/src/assets/configurations/constants.ts``. Keep the two values
in sync when adjusting.
"""

# Server-enforced upper bound on the `limit` argument accepted by
# ``ExtractType.resolve_full_datacell_list``. Prevents authenticated
# callers from bypassing the intended payload cap by passing an
# arbitrarily large limit via the GraphQL API.
#
# Must match the frontend constant ``EXTRACT_GRID_EMBED_CELL_LIMIT``
# in ``frontend/src/assets/configurations/constants.ts``.
MAX_FULL_DATACELL_LIST_LIMIT = 500
