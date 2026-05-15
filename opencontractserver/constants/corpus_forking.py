"""
Constants for corpus forking.

Centralizes string literals used by the fork pipeline so that prefix
semantics (e.g. ``[FORK] `` title stacking across generations) live in
one place. Tests assert on this constant rather than the raw literal.
"""

# Prepended to corpus/document/labelset/fieldset titles created by a fork.
# Always added unconditionally — stacking across generations (``[FORK] [FORK] X``)
# is the historical contract used by snapshot comparisons.
FORK_TITLE_PREFIX = "[FORK] "
