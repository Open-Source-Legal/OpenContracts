from __future__ import annotations

import logging

import django.db.models
import requests
from django.conf import settings
from django.core.handlers.wsgi import WSGIRequest
from django.db import transaction
from django.utils import timezone

from opencontractserver.analyzer.models import Analysis, Analyzer, GremlinEngine
from opencontractserver.annotations.models import Annotation, AnnotationLabel, LabelSet
from opencontractserver.documents.models import Document
from opencontractserver.types.dicts import (
    AnalyzerManifest,
    AnnotationLabelPythonType,
    OpenContractsGeneratedCorpusPythonType,
    OpenContractsLabelSetType,
)
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.packaging import (
    turn_base64_encoded_file_to_django_content_file,
)
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

logger = logging.getLogger(__name__)


def get_django_file_field_url(
    field_name: str,
    obj: type[django.db.models.Model],
    context: type[WSGIRequest] | None = None,
):

    if settings.STORAGE_BACKEND in ["AWS", "GCP"]:
        return getattr(obj, field_name).url
    else:
        if context is None:
            return (
                settings.CALLBACK_ROOT_URL_FOR_ANALYZER + getattr(obj, field_name).url
            )
        else:
            return context.build_absolute_uri(getattr(obj, field_name).url)


def install_labels_for_analyzer(
    analyzer_id: int | str,
    creating_user_id: str,
    doc_labels: list[AnnotationLabelPythonType],
    text_labels: list[AnnotationLabelPythonType],
    label_set: OpenContractsLabelSetType,
    install_label_set: bool | None = None,
) -> dict[str | int, str | int]:
    """
    When an analysis is run, we need to have labels in the local OpenContracts database to link to
    the annotations. This utility will, given a Gremlin analyzers label metadata, check to see if they exist,
    and, if they don't create them.

    Returns a map of the label ids Gremlin is using to the ids created (or retrieved) for label objs in the OC system
    """

    logger.info("install_labels_for_analyzer() - start...")
    label_set_obj = None

    if install_label_set is not None and install_label_set is True:

        logger.info(
            f"install_labels_for_analyzer() - install labelset for analyzer {analyzer_id}"
        )

        # First, check to see if there's a labelset with this title for given analyzer
        with transaction.atomic():
            try:
                label_set_obj = LabelSet.objects.get(
                    title=label_set["title"], analyzer_id=analyzer_id
                )
                logger.info(
                    f"install_labels_for_analyzer() - retrieved existing label_set: {label_set_obj}"
                )

            except LabelSet.DoesNotExist:

                label_set_obj = LabelSet.objects.create(
                    title=label_set["title"],
                    analyzer_id=analyzer_id,
                    description=label_set["description"],
                    creator_id=creating_user_id,
                )

                # Give proper permission to our user
                set_permissions_for_obj_to_user(
                    creating_user_id, label_set_obj, [PermissionTypes.CRUD]
                )

        # If there's icon data, we need to unpack it and create a ContentFile
        if label_set["icon_data"] is not None:
            icon_content_file = turn_base64_encoded_file_to_django_content_file(
                base64_string=label_set["icon_data"], filename=label_set["icon_name"]
            )

            with transaction.atomic():
                label_set_obj.icon.save(label_set["icon_name"], icon_content_file)

    # Combine all the received labels into a list we can iterate over
    combined_labels: list[AnnotationLabelPythonType] = [*doc_labels, *text_labels]

    # We need to be able to map the local label ids to the ids in the analyzer
    label_id_map = {}

    for label_data in combined_labels:

        try:
            label = AnnotationLabel.objects.get(
                analyzer_id=analyzer_id, text=label_data["text"]
            )

            label_id_map[label_data["id"]] = label.id

        except AnnotationLabel.DoesNotExist:

            with transaction.atomic():
                label = AnnotationLabel.objects.create(
                    analyzer_id=analyzer_id,
                    text=label_data["text"],
                    label_type=label_data["label_type"],
                    color=label_data["color"],
                    description=label_data["description"],
                    creator_id=creating_user_id,
                )

                # Give proper permission to our user
                set_permissions_for_obj_to_user(
                    creating_user_id, label, [PermissionTypes.CRUD]
                )

            label_id_map[label_data["id"]] = label.id

        if label_set_obj is not None:
            label_set_obj.annotation_labels.add(label)

    return label_id_map


def install_analyzers(
    gremlin_id: int, analyzer_manifests: list[AnalyzerManifest]
) -> list[int]:
    """
    When setting up a new Gremlin Engine, this task will be used to ping the engine
    for a manifest of its installed analyzers and then create database entries for these
    analyzers in the DB of this instance of Open Contracts.
    """

    resulting_ids = []

    gremlin_obj = GremlinEngine.objects.get(id=gremlin_id)

    for manifest in analyzer_manifests:
        # First, set up the analyzer
        with transaction.atomic():
            analyzer = Analyzer.objects.create(
                id=manifest["metadata"]["id"],
                manifest=manifest,
                description=manifest["metadata"]["description"],
                host_gremlin=gremlin_obj,
                creator=gremlin_obj.creator,
            )
            icon_content_file = turn_base64_encoded_file_to_django_content_file(
                base64_string=manifest["metadata"]["icon_base_64_data"],
                filename=manifest["metadata"]["icon_name"],
            )
            analyzer.icon.save(manifest["metadata"]["icon_name"], icon_content_file)

            resulting_ids.append(analyzer.id)

        # Then, set up the labels and labelsets
        install_labels_for_analyzer(
            creating_user_id=gremlin_obj.creator.id,
            analyzer_id=analyzer.id,
            doc_labels=manifest["doc_labels"],
            text_labels=manifest["text_labels"],
            label_set=manifest["label_set"],
            install_label_set=True,
        )

    return resulting_ids


# TODO - delete candidate?
def run_analysis(
    analysis_id: str,
    doc_ids: list[int | str] | None = None,
) -> int:
    """
    Given an analysis id, package up the data required to transfer
    the task to a Gremlin Engine and then submit it to the target analyzer on the target
    Gremlin engine. Doc_ids is optional, if you only want to analyzer certain documents
    in a given corpus, it overrides the corpus data.
    """

    # Not the most efficient set of calls, I know. Holdover from a slight change in how
    # this utility was constructed
    analysis = Analysis.objects.get(id=analysis_id)
    analyzer = analysis.analyzer
    gremlin = analyzer.host_gremlin

    # If we're analyzing an entire corpus and we didn't override docs
    if analysis.analyzed_corpus and (
        not isinstance(doc_ids, list) or len(doc_ids) == 0
    ):
        corpus = analysis.analyzed_corpus
        docs = corpus.get_documents()
        logger.info(f"Analyze corpus {corpus.id} with {docs.count()} docs")

    # Otherwise we need a list of valid doc_ids to apply to analysis
    elif isinstance(doc_ids, list) and len(doc_ids) > 0:
        docs = Document.objects.filter(id__in=doc_ids)
        if docs.count() != len(doc_ids):
            raise ValueError(f"Failed retrieving all documents in doc list {doc_ids}")
        logger.info(f"Analyze document list with d {doc_ids}")

    # OR we have to throw an error
    else:
        raise ValueError(
            f"create_analysis_with_analyzer() - called and analysis {analysis_id} has no corpus property "
            f"AND no doc_id list provided as alternate doc source"
        )

    analysis.analyzed_documents.add(*[doc.id for doc in docs])
    document_exchange_data = []
    for doc in docs:

        doc_data = {
            "original_id": doc.id,
            "pdf_file_url": get_django_file_field_url("pdf_file", doc),
        }

        if doc.txt_extract_file and getattr(doc.txt_extract_file, "url"):
            doc_data["txt_extract_file_url"] = get_django_file_field_url(
                "txt_extract_file", doc
            )

        if doc.pawls_parse_file and getattr(doc.pawls_parse_file, "url"):
            doc_data["pawls_parse_file_url"] = get_django_file_field_url(
                "pawls_parse_file", doc
            )

        document_exchange_data.append(doc_data)

    # We need to build the url of THIS actual instance of OpenContracts
    # This should be set in the settings (though we could grab it from the site,
    # setting in env lets us do things like have localhost callbacks)
    # ... this site FYI if you want to change back: from django.contrib.sites.models import Site
    gremlin_submission = {
        "analyzer_id": analyzer.id,
        "callback_url": settings.CALLBACK_ROOT_URL_FOR_ANALYZER
        + f"/analysis/{analysis.id}/complete",
        "callback_token": analysis.callback_token.__str__(),
        "documents": document_exchange_data,
    }

    logger.info(
        f"submit_corpus_documents_to_analyzer() - submit data to gremlin: {gremlin_submission}"
    )

    try:
        submission_response = requests.post(
            f"{gremlin.url}/api/jobs/submit", json=gremlin_submission
        )

        logger.info(f"Post job to: {gremlin.url}/api/jobs/submit")
        logger.info(
            f"submit_corpus_documents_to_analyzer() - submission response {submission_response} "
            f"{submission_response.content}"
        )

        with transaction.atomic():
            analysis.analysis_started = timezone.now()

        logger.info(
            f"submit_corpus_documents_to_analyzer() - analysis {analysis.id} submitted to gremlin "
            f"{gremlin.url}"
        )

        return analysis.id

    except Exception as e:
        logger.error(
            f"submit_corpus_documents_to_analyzer() - failed to submit analysis {analysis.id} due to error "
            f"{e}"
        )
        return -1


def import_annotations_from_analysis(
    analysis_id: str | int,
    creator_id: str | int,
    analysis_results: OpenContractsGeneratedCorpusPythonType,
) -> bool:
    """
    Import the actual annotations and link them to proper analyzers, analysis, labels, etc.
    """
    logger.info(
        f"import_annotations_from_analysis - start(analysis_id: {analysis_id}, creator_id: {creator_id})..."
    )
    analysis = Analysis.objects.get(id=analysis_id)
    logger.info(f"import_annotations_from_analysis - analysis: {analysis}")

    try:
        label_id_map = install_labels_for_analyzer(
            creating_user_id=creator_id,
            analyzer_id=analysis.analyzer.id,
            doc_labels=list(analysis_results["doc_labels"].values()),
            text_labels=list(analysis_results["text_labels"].values()),
            label_set=analysis_results["label_set"],
            install_label_set=True,
        )
    except Exception as e:

        message = (
            f"import_annotations_from_analysis() - failed to import annotation labels / labelset due to error:"
            f" {e}"
        )
        logger.error(message)

        with transaction.atomic():
            analysis.import_log = (
                analysis.import_log + "\n" + message
                if (analysis and len(analysis.import_log) > 0)
                else message
            )
            analysis.save()

        return False

    for doc_id, doc_annotation_data in list(analysis_results["annotated_docs"].items()):

        # Create doc labels for the doc
        for doc_label_data in doc_annotation_data["doc_labels"]:

            try:
                # logger.info(f"import_annotations_from_analysis() - create doc label {doc_label_data} for doc {
                # doc_id}")

                with transaction.atomic():
                    annotation = Annotation.objects.create(
                        annotation_label_id=label_id_map[doc_label_data],
                        document_id=doc_id,
                        analysis_id=analysis_id,
                        created_by_analysis_id=analysis_id,  # Mark as created by this analysis
                        creator_id=creator_id,
                        corpus=analysis.analyzed_corpus,
                    )
                    set_permissions_for_obj_to_user(
                        creator_id, annotation, [PermissionTypes.CRUD]
                    )

                    # logger.info(f"import_annotations_from_analysis() - Successfully created doc label {annotation}")
            except Exception as e:
                message = (
                    f"import_annotations_from_analysis() - for doc {doc_id} failed to import doc annotation "
                    f"{doc_label_data} due to error: {e}"
                )
                logger.error(message)
                with transaction.atomic():
                    analysis.import_log = (
                        analysis.import_log + "\n" + message
                        if len(analysis.import_log) > 0
                        else message
                    )
                    analysis.save()

        # Create span labels for the doc
        for span_label_data in doc_annotation_data["labelled_text"]:

            try:
                # logger.info(f"import_annotations_from_analysis() - create span label {span_label_data} for doc
                # {doc_id}")
                with transaction.atomic():
                    annotation = Annotation.objects.create(
                        annotation_label_id=label_id_map[
                            span_label_data["annotationLabel"]
                        ],
                        document_id=doc_id,
                        analysis_id=analysis_id,
                        created_by_analysis_id=analysis_id,  # Mark as created by this analysis
                        creator_id=creator_id,
                        raw_text=span_label_data["rawText"],
                        page=span_label_data["page"],
                        json=span_label_data["annotation_json"],
                        corpus=analysis.analyzed_corpus,
                    )
                    set_permissions_for_obj_to_user(
                        creator_id, annotation, [PermissionTypes.CRUD]
                    )
                    # logger.info(f"import_annotations_from_analysis() - Successfully created span label {annotation}")

            except Exception as e:
                message = (
                    f"import_annotations_from_analysis() - for doc {doc_id} failed to import span annotation "
                    f"{span_label_data} due to error: {e}"
                )
                logger.error(message)
                with transaction.atomic():
                    analysis.import_log = (
                        analysis.import_log + "\n" + message
                        if (analysis.import_log and len(analysis.import_log) > 0)
                        else message
                    )
                    analysis.save()

    return True
