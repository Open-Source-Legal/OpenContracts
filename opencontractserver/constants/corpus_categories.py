"""
Constants for corpus category (tag) management.

Corpus categories are the runtime-configurable tag set ("Case Law",
"Contracts", "Legislation", ...) shown on the Discover page and in corpus
settings. These bounds and default-appearance values are shared by the
service layer (``opencontractserver/corpuses/services/corpus_category_service.py``)
and the GraphQL mutations (``config/graphql/corpus_category_mutations.py``).

Kept in sync with the field definitions on ``CorpusCategory``
(``opencontractserver/corpuses/models.py``). The matching frontend defaults
live in ``frontend/src/assets/configurations/constants.ts`` per the
"Keep in sync" convention used for other cross-stack constants.
"""

# Maximum length of a category name — matches the ``name`` field width.
MAX_CATEGORY_NAME_LENGTH = 255

# Maximum length of a Lucide icon name — matches the ``icon`` field width.
MAX_CATEGORY_ICON_LENGTH = 100

# Soft cap on the description. The model field is an unbounded ``TextField``,
# so this is a service-layer guard against absurdly large payloads rather than
# a DB constraint — consistent with the name/icon length checks.
MAX_CATEGORY_DESCRIPTION_LENGTH = 2000

# Default appearance values, mirroring the model field defaults so a create
# that omits ``icon`` / ``color`` lands on the same look as a direct ORM create.
DEFAULT_CATEGORY_ICON = "folder"
DEFAULT_CATEGORY_COLOR = "#3B82F6"
