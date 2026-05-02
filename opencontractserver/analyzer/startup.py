"""
Startup tasks for the analyzer app.
This module can be imported in settings or wsgi.py to ensure
doc analyzers are synced on application startup.
"""

import logging

logger = logging.getLogger(__name__)


def sync_analyzers_on_startup() -> None:
    """
    Automatically sync doc analyzer tasks on application startup.
    This ensures all decorated tasks are available without manual intervention.
    """
    try:
        from django.contrib.auth import get_user_model

        from opencontractserver.analyzer.models import Analyzer
        from opencontractserver.analyzer.utils import auto_create_doc_analyzers

        UserModel = get_user_model()

        auto_create_doc_analyzers(AnalyzerModel=Analyzer, UserModel=UserModel)

        logger.info("Successfully synchronized doc analyzer tasks on startup")
    except Exception as e:
        logger.warning(f"Could not sync analyzers on startup: {e}")
        # Don't fail startup if sync fails
        pass
