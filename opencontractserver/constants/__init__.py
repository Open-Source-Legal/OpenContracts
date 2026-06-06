"""
Constants used throughout the OpenContracts application.

This package contains centralized constant definitions to avoid magic numbers
and hardcoded values scattered throughout the codebase.
"""

from opencontractserver.constants.annotations import *  # noqa: F401, F403
from opencontractserver.constants.auth import *  # noqa: F401, F403
from opencontractserver.constants.benchmarks import *  # noqa: F401, F403
from opencontractserver.constants.community_stats import *  # noqa: F401, F403
from opencontractserver.constants.context_guardrails import *  # noqa: F401, F403
from opencontractserver.constants.corpus_actions import *  # noqa: F401, F403
from opencontractserver.constants.discovery import *  # noqa: F401, F403
from opencontractserver.constants.document_processing import *  # noqa: F401, F403
from opencontractserver.constants.extracts import *  # noqa: F401, F403
from opencontractserver.constants.moderation import *  # noqa: F401, F403
from opencontractserver.constants.truncation import *  # noqa: F401, F403

# NOTE: ``zip_import`` and ``zip_export`` are deliberately NOT barrel-imported
# here. ``config/settings/base.py`` imports from this package at the top of the
# settings module, so anything pulled in by this ``__init__`` runs *while
# settings is still building*. Both modules expose settings-derived limits; an
# eager import here previously froze ``zip_import``'s limits to their defaults
# (the env/ConfigMap overrides became permanently inert). Import their ``get_*``
# accessors from the submodule (``opencontractserver.constants.zip_import``) at
# call sites instead.
