#  Copyright (C) 2022  John Scrudato

import logging

from django.db import transaction

from opencontractserver.analyzer.models import Analysis

logger = logging.getLogger(__name__)


def delete_analysis_and_annotations(analysis_pk: str | int = -1) -> bool:
    """
    When we delete an analysis, just deleting the analysis doesn't actually delete the
    annotations due to the way relationships are constructed between annotations and
    analyses.
    """

    logger.error(
        f"delete_analysis_and_annotations() - start for analysis {analysis_pk}"
    )

    try:
        analysis = Analysis.objects.get(id=analysis_pk)

        # Lock the analysis (no need to unlock later as we're deleting it)
        with transaction.atomic():
            analysis.backend_lock = True
            analysis.save()

        with transaction.atomic():

            # Bulk update actual annotations
            analysis.annotations.all().delete()
            analysis.delete()

    except Exception as e:
        logger.error(
            f"delete_analysis_and_annotations() - failed for analysis {analysis_pk} due to error: {e}"
        )
        return False

    logger.error("delete_analysis_and_annotations() - done...")

    return True
