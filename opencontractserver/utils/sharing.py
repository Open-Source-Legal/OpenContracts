from __future__ import annotations

import logging
from typing import TypedDict

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q

from opencontractserver.analyzer.models import Analysis, Analyzer
from opencontractserver.annotations.models import (
    Annotation,
    AnnotationLabel,
    Relationship,
)
from opencontractserver.corpuses.models import Corpus, CorpusQuery
from opencontractserver.documents.models import Document, DocumentAnalysisRow
from opencontractserver.extracts.models import Datacell, Extract, Fieldset

User = get_user_model()
logger = logging.getLogger(__name__)


class MakePublicReturnType(TypedDict):
    message: str
    ok: bool


def make_analysis_public(analysis_id: int | str) -> MakePublicReturnType:
    """
    Given an analysis ID, make it and its annotations public. If you do this on a
    Corpus that is not itself public, the underlying docs and corpus (and thus
    the analysis itself) can only be seen by those who have at least read permission to the
    Corpus. In current iteration of OC (Sept 22), that basically means only admins
    and the person who created it will see the annotations. Long story short, MAKE
    THE CORPUS PUBLIC TOO USING A SEPARATE CALL.
    """

    ok = False

    try:

        analysis = Analysis.objects.get(id=analysis_id)

        # Lock the analysis as this can take a long time depending on the number of
        # documents and annotations to change permissions for.
        with transaction.atomic():
            analysis.is_public = True
            analysis.backend_lock = True
            analysis.save()

        corpus = analysis.analyzed_corpus

        # Bulk update the analyzers labels
        labels = AnnotationLabel.objects.filter(analyzer=analysis.analyzer)
        for label in labels:
            label.is_public = True
        AnnotationLabel.objects.bulk_update(labels, ["is_public"], batch_size=100)

        # Bulk update actual annotations
        analyzer_annotations = corpus.annotations.filter(analysis_id=analysis_id)
        for annotation in analyzer_annotations:
            # logger.info(f"Make annotation public: {annotation}")
            annotation.is_public = True
        Annotation.objects.bulk_update(
            analyzer_annotations, ["is_public"], batch_size=100
        )

        with transaction.atomic():
            analysis.backend_lock = False
            analysis.save()

        analysis.refresh_from_db()

        message = "SUCCESS - Analysis is Public"
        ok = True

    except Exception as e:
        message = f"ERROR - Could not make analysis public due to unexpected error: {e}"

    return {"message": message, "ok": ok}


def make_corpus_public(corpus_id: int | str) -> MakePublicReturnType:
    """
    Given a corpus ID, make it, its labelset, its docs, human annotations, extracts,
    analyses, datacells, fieldsets, analyzers and related objects public.
    """
    ok = False

    try:
        corpus = Corpus.objects.get(id=corpus_id)
        logger.info(f"Retrieved corpus with id {corpus_id}")

        # Lock the corpus while we re-permission
        with transaction.atomic():
            corpus.backend_lock = True
            corpus.is_public = True
            corpus.save()
            logger.info(f"Locked and set corpus {corpus_id} as public")

        # Make documents public
        docs = corpus.get_documents()
        updated_docs = Document.objects.filter(id__in=docs).update(is_public=True)
        logger.info(f"Made {updated_docs} documents public")

        # !!DANGER!! - Make ALL labels for this corpus public
        if corpus.label_set:
            corpus.label_set.is_public = True
            corpus.label_set.save()
            logger.info(f"Set label_set {corpus.label_set.id} as public")

            # Make labels public
            updated_labels = AnnotationLabel.objects.filter(
                included_in_labelset=corpus.label_set
            ).update(is_public=True)
            logger.info(f"Made {updated_labels} annotation labels public")

        # Make human annotations public
        updated_annotations = Annotation.objects.filter(corpus=corpus).update(
            is_public=True
        )
        logger.info(f"Made {updated_annotations} human annotations public")

        # Make extracts public
        updated_extracts = Extract.objects.filter(corpus=corpus).update(is_public=True)
        logger.info(f"Made {updated_extracts} extracts public")

        # Make analyses public
        analyses = Analysis.objects.filter(analyzed_corpus=corpus)
        updated_analyses = Analysis.objects.filter(id__in=analyses).update(
            is_public=True
        )
        logger.info(f"Made {updated_analyses} analyses public")

        # Make datacells public
        updated_datacells = Datacell.objects.filter(extract__corpus=corpus).update(
            is_public=True
        )
        logger.info(f"Made {updated_datacells} datacells public")

        # Make fieldsets public
        fieldsets = Fieldset.objects.filter(extracts__corpus=corpus).distinct()
        updated_fieldsets = Fieldset.objects.filter(id__in=fieldsets).update(
            is_public=True
        )
        logger.info(f"Made {updated_fieldsets} fieldsets public")

        # Make analyzers public
        analyzers = Analyzer.objects.filter(
            Q(analysis__analyzed_corpus=corpus) | Q(corpusaction__corpus=corpus)
        ).distinct()
        updated_analyzers = Analyzer.objects.filter(id__in=analyzers).update(
            is_public=True
        )
        logger.info(f"Made {updated_analyzers} analyzers public")

        # Make related objects public
        # Relationships
        updated_relationships = Relationship.objects.filter(corpus=corpus).update(
            is_public=True
        )
        logger.info(f"Made {updated_relationships} relationships public")

        # CorpusQueries
        updated_queries = CorpusQuery.objects.filter(corpus=corpus).update(
            is_public=True
        )
        logger.info(f"Made {updated_queries} corpus queries public")

        # DocumentAnalysisRows
        updated_rows = DocumentAnalysisRow.objects.filter(
            Q(analysis__analyzed_corpus=corpus) | Q(extract__corpus=corpus)
        ).update(is_public=True)
        logger.info(f"Made {updated_rows} document analysis rows public")

        # Unlock the corpus
        with transaction.atomic():
            corpus.backend_lock = False
            corpus.save()
            logger.info(f"Unlocked corpus {corpus_id}")

        corpus.refresh_from_db()
        logger.info(f"Refreshed corpus {corpus_id} from database")

        message = "SUCCESS - Corpus and related objects are now public"
        ok = True

    except Exception as e:
        message = f"ERROR - Could not make public due to unexpected error: {e}"
        logger.error(message, exc_info=True)

    return {"message": message, "ok": ok}
