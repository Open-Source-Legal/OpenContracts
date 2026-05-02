import asyncio
import functools
import json
import logging
import traceback
from functools import wraps
from typing import Any, Callable, Union

from asgiref.sync import async_to_sync, sync_to_async
from celery import shared_task
from celery.exceptions import Retry
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from plasmapdf.models.PdfDataLayer import build_translation_layer

from opencontractserver.analyzer.models import Analysis
from opencontractserver.annotations.models import Annotation, AnnotationLabel
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document, DocumentAnalysisRow
from opencontractserver.types.dicts import TextSpan
from opencontractserver.types.enums import LabelType
from opencontractserver.utils.compact_pawls import expand_pawls_pages
from opencontractserver.utils.etl import is_dict_instance_of_typed_dict

# Timing constants for retry and backoff durations
MAX_DELAY = 1800  # 30 minutes
INITIAL_DELAY = 30  # 30 seconds
DELAY_INCREMENT = 300  # 5 minutes

logger = logging.getLogger(__name__)


def doc_analyzer_task(
    max_retries: Union[int, None] = None,
    input_schema: dict[str, Any] | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Decorator for Celery tasks that analyze documents.

    The wrapped function is expected to return either:
        1) A 4-element tuple:
           (List[str], List[OpenContractsAnnotationPythonType], List[Dict[str, Any]], bool)
           If only four elements are returned, we will set the message to "No Return Message"
        2) A 5-element tuple:
           (List[str], List[OpenContractsAnnotationPythonType], List[Dict[str, Any]], bool, str)
           The final element is the message for inclusion in the Analysis.result_message or Analysis.error_message

    An optional input_schema parameter may be stored for later retrieval.

    :param max_retries: Optional maximum number of retries for the Celery task.
    :param input_schema: Optional dictionary defining input schema for the decorated task.
    :return: The decorator function.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @shared_task(bind=True, max_retries=max_retries)
        @wraps(func)
        def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            doc_id = kwargs.get("doc_id")
            corpus_id = kwargs.get("corpus_id")
            analysis_id = kwargs.get("analysis_id")

            logger.info(f"Doc analyzer task doc id: {doc_id}")

            if not doc_id:
                raise ValueError("doc_id is required for doc_analyzer_task")
            if not analysis_id:
                raise ValueError("analysis_id is required for doc_analyzer_task")

            # Attempt to retrieve Document
            try:
                doc = Document.objects.get(id=doc_id)
            except ObjectDoesNotExist:
                raise ValueError(f"Document with id {doc_id} does not exist")

            # Attempt to retrieve Corpus if corpus_id is present
            if corpus_id:
                try:
                    Corpus.objects.get(id=corpus_id)
                except ObjectDoesNotExist:
                    logger.warning(f"Corpus with id {corpus_id} does not exist")
                    raise ValueError(f"Corpus with id {corpus_id} does not exist")

            # Attempt to retrieve Analysis if analysis_id is present
            analysis = None
            if analysis_id:
                try:
                    analysis = Analysis.objects.get(id=analysis_id)
                    logger.info(f"Link to analysis: {analysis}")
                except ObjectDoesNotExist:
                    logger.warning(f"Analysis with id {analysis_id} does not exist")
                    raise ValueError(f"Analysis with id {analysis_id} does not exist")

            # If doc is locked, retry with back-off
            logger.info(f"Doc {doc_id} backend lock: {doc.backend_lock}")
            if doc.backend_lock:
                logger.info(f"Doc {doc_id} backend lock is True")
                retry_count = self.request.retries
                logger.info(f"\tRetry count: {retry_count}")
                delay = min(INITIAL_DELAY + (retry_count * DELAY_INCREMENT), MAX_DELAY)
                logger.info(f"\tNew delay: {delay}")

                if delay < MAX_DELAY:
                    logger.info("Starting retry...")
                    raise self.retry(countdown=delay)

            try:
                # Prepare text extracts
                pdf_text_extract = (
                    doc.txt_extract_file.read().decode("utf-8")
                    if doc.txt_extract_file
                    else None
                )
                pdf_pawls_extract = (
                    expand_pawls_pages(json.loads(doc.pawls_parse_file.read()))
                    if doc.pawls_parse_file
                    else None
                )
                pdf_data_layer = (
                    build_translation_layer(pdf_pawls_extract)
                    if pdf_pawls_extract
                    else []
                )

                # Call the wrapped function
                result = func(
                    pdf_text_extract=pdf_text_extract,
                    pdf_pawls_extract=pdf_pawls_extract,
                    *args,
                    **kwargs,
                )

                # Validate return structure: allow 4 or 5 elements
                if not isinstance(result, tuple):
                    raise ValueError(
                        "Wrapped function must return a tuple of either 4 or 5 elements."
                    )

                if len(result) == 4:
                    doc_annotations, span_label_pairs, metadata, task_pass = result
                    message = "No Return Message"
                elif len(result) == 5:
                    (
                        doc_annotations,
                        span_label_pairs,
                        metadata,
                        task_pass,
                        message,
                    ) = result
                else:
                    raise ValueError(
                        "Function must return a tuple of 4 (without message) or 5 elements (with message)."
                    )

                # Added type check for task_pass
                if not isinstance(task_pass, bool):
                    raise ValueError(
                        "Fourth element of the return value must be true/false"
                    )

                # Update Analysis with the returned message (and clear any previous error) if analysis is available
                if analysis:
                    if task_pass:
                        analysis.error_message = None
                        analysis.result_message = message
                    else:
                        # If the task did not pass, treat the message as an error
                        analysis.error_message = message
                        analysis.result_message = None
                    analysis.save()

                # If task is false, skip further processing
                if not task_pass:
                    # Return the final 5-tuple to match the updated spec
                    return (
                        doc_annotations,
                        span_label_pairs,
                        metadata,
                        task_pass,
                        message,
                    )

                # Process annotations if task passed and we have a valid analysis
                if analysis:
                    logger.info("Doc analyzer task passed... handle outputs.")
                    data_row, _ = DocumentAnalysisRow.objects.get_or_create(
                        document=doc, analysis=analysis, creator=analysis.creator
                    )
                    logger.info(f"Retrieved data row: {data_row}")
                    data_row.save()

                    # Validate doc_annotations
                    if not isinstance(doc_annotations, list) or (
                        len(doc_annotations) > 0
                        and not all(isinstance(a, str) for a in doc_annotations)
                    ):
                        raise ValueError(
                            "First element of the tuple must be a list of doc labels"
                        )

                    # Validate span_label_pairs
                    if not isinstance(span_label_pairs, list):
                        raise ValueError(
                            "Second element of the tuple must be a list of (TextSpan, str) tuples"
                        )

                    # Validate metadata
                    if not isinstance(metadata, list) or (
                        len(metadata) > 0
                        and not all(
                            isinstance(m, dict) and "data" in m for m in metadata
                        )
                    ):
                        raise ValueError(
                            "Third element of the tuple must be a list of dictionaries with 'data' key"
                        )

                    resulting_annotations = []
                    with transaction.atomic():
                        for span_label_pair in span_label_pairs:
                            logger.debug(f"Look at span_label_pair: {span_label_pair}")
                            if not (
                                isinstance(span_label_pair, tuple)
                                and len(span_label_pair) == 2
                                and is_dict_instance_of_typed_dict(
                                    span_label_pair[0], TextSpan
                                )
                                and isinstance(span_label_pair[1], str)
                            ):
                                raise ValueError(
                                    "Second element must be a list of (TextSpan, str) tuples"
                                )

                            # Convert to the appropriate form of annotation
                            if doc.file_type in ["application/pdf"]:
                                # PDF / token-based annotation
                                span, label_text = span_label_pair
                                annotation_data = pdf_data_layer.create_opencontract_annotation_from_span(
                                    {"span": span, "annotation_label": label_text}
                                )
                                label_obj, _ = AnnotationLabel.objects.get_or_create(
                                    text=annotation_data["annotationLabel"],
                                    label_type=LabelType.TOKEN_LABEL,
                                    creator=analysis.creator,
                                    analyzer=analysis.analyzer,
                                )
                                annot = Annotation(
                                    document=doc,
                                    analysis=analysis,
                                    annotation_label=label_obj,
                                    page=annotation_data["page"],
                                    raw_text=annotation_data["rawText"],
                                    json=annotation_data["annotation_json"],
                                    annotation_type=LabelType.TOKEN_LABEL,
                                    creator=analysis.creator,
                                    **({"corpus_id": corpus_id} if corpus_id else {}),
                                )
                                annot.save()
                                resulting_annotations.append(annot)

                            elif doc.file_type in ["application/txt", "text/plain"]:
                                # Plain text / span-based annotation
                                span, label_text = span_label_pair
                                label_obj, _ = AnnotationLabel.objects.get_or_create(
                                    text=label_text,
                                    label_type=LabelType.SPAN_LABEL,
                                    creator=analysis.creator,
                                    analyzer=analysis.analyzer,
                                )
                                annot = Annotation(
                                    document=doc,
                                    analysis=analysis,
                                    annotation_label=label_obj,
                                    page=1,
                                    raw_text=pdf_text_extract[
                                        span["start"] : span["end"]
                                    ],
                                    annotation_type=LabelType.SPAN_LABEL,
                                    json={"start": span["start"], "end": span["end"]},
                                    creator=analysis.creator,
                                    **({"corpus_id": corpus_id} if corpus_id else {}),
                                )
                                annot.save()
                                resulting_annotations.append(annot)
                            else:
                                raise ValueError(
                                    f"Unexpected file type: {doc.file_type}"
                                )

                        # Now handle doc-level labels
                        for doc_label in doc_annotations:
                            logger.info(f"Creating doc label annotation: {doc_label}")
                            label_obj, _ = AnnotationLabel.objects.get_or_create(
                                text=doc_label,
                                label_type=LabelType.DOC_TYPE_LABEL,
                                creator=analysis.creator,
                                analyzer=analysis.analyzer,
                            )
                            annot = Annotation(
                                document=doc,
                                analysis=analysis,
                                annotation_label=label_obj,
                                page=1,
                                raw_text="",
                                json={},
                                annotation_type=LabelType.DOC_TYPE_LABEL,
                                creator=analysis.creator,
                                **({"corpus_id": corpus_id} if corpus_id else {}),
                            )
                            annot.save()
                            resulting_annotations.append(annot)

                        transaction.on_commit(
                            lambda: data_row.annotations.add(*resulting_annotations)
                        )

                # Return the final 5-tuple to keep results uniform
                return (doc_annotations, span_label_pairs, metadata, task_pass, message)

            except Retry:
                logger.info(f"Retry in doc_analyzer_task for doc_id {doc_id}")
                raise

            except ValueError:
                # Re-raise ValueError as is, since they're raised intentionally for invalid return values
                raise

            except Exception as e:
                logger.info(f"Error in doc_analyzer_task for doc_id {doc_id}: {str(e)}")
                if analysis:
                    analysis.error_message = str(e)
                    analysis.result_message = None
                    analysis.save()

                # Return a 5-element tuple (with the error in the last position)
                return [], [], [{"data": {"error": str(e)}}], False, str(e)

        # Identify tasks decorated by this wrapper
        wrapper.is_doc_analyzer_task = True
        # Attach the input schema for runtime retrieval
        wrapper._oc_doc_analyzer_input_schema = input_schema

        return wrapper

    return decorator


def async_doc_analyzer_task(
    max_retries: Union[int, None] = None,
    input_schema: dict[str, Any] | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Decorator for Celery tasks that analyze documents in an async context,
    providing the same preflight checks as doc_analyzer_task, in the
    same order, and then calling the user-supplied async function.

    This version forces a complete drain of the newly created event loop,
    ensuring that any tasks or async generators spawned by user code are
    properly finalized (or canceled) before the loop is closed.
    """

    def decorator(async_func: Callable[..., Any]) -> Callable[..., Any]:
        @shared_task(bind=True, max_retries=max_retries)
        @functools.wraps(async_func)
        def wrapper(self, *args, **kwargs) -> Any:
            """
            Synchronously runs the async_wrapper by creating a dedicated event loop,
            running the async code, then forcibly draining or canceling any pending
            tasks before shutting down the loop.
            """
            loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(loop)
                result = loop.run_until_complete(async_wrapper(self, *args, **kwargs))
                return result
            finally:
                # Forcefully cancel *all* remaining tasks so none linger
                pending_tasks = asyncio.all_tasks(loop=loop)
                for task in pending_tasks:
                    task.cancel()
                if pending_tasks:
                    loop.run_until_complete(
                        asyncio.gather(*pending_tasks, return_exceptions=True)
                    )

                # Shutdown async generators
                loop.run_until_complete(loop.shutdown_asyncgens())

                # Finally close the loop
                loop.close()

        async def async_wrapper(self, *args, **kwargs) -> Any:
            """
            The core logic: preflight checks using async-safe ORM methods, then
            calling the user's async function. Any tasks or async generators
            spawned here will be cleaned up in the wrapper after this returns.
            """
            doc_id = kwargs.get("doc_id")
            corpus_id = kwargs.get("corpus_id")
            analysis_id = kwargs.get("analysis_id")
            logger.info(
                f"[ASYNC] Task parameters - doc_id: {doc_id}, corpus_id: {corpus_id}, analysis_id: {analysis_id}"
            )

            logger.info(f"[ASYNC] Starting task with doc_id: {doc_id}")

            # Log all documents in DB before we try to fetch
            all_docs = await Document.objects.all().acount()
            logger.info(f"[ASYNC] Number of documents in DB: {all_docs}")

            if doc_id:
                try:
                    exists = await Document.objects.filter(id=doc_id).aexists()
                    logger.info(f"[ASYNC] Document {doc_id} exists check: {exists}")
                except Exception as e:
                    logger.error(f"[ASYNC] Error checking document existence: {e}")

            if not doc_id:
                raise ValueError("doc_id is required for doc_analyzer_task")

            # 2) Check if analysis_id is missing
            if not analysis_id:
                raise ValueError("analysis_id is required for doc_analyzer_task")

            # 3) Fetch the Document
            try:
                doc = await Document.objects.aget(id=doc_id)
            except ObjectDoesNotExist:
                raise ValueError(f"Document with id {doc_id} does not exist")

            # 4) If a corpus_id is provided, fetch it
            if corpus_id:
                try:
                    await Corpus.objects.aget(id=corpus_id)
                except ObjectDoesNotExist:
                    logger.error(f"Corpus with id {corpus_id} does not exist")
                    raise ValueError(f"Corpus with id {corpus_id} does not exist")

            # 5) If an analysis_id is provided, fetch the Analysis
            try:
                analysis = await Analysis.objects.aget(id=analysis_id)
                logger.info(f"Link to analysis: {analysis}")
            except ObjectDoesNotExist:
                logger.warning(f"Analysis with id {analysis_id} does not exist")
                raise ValueError(f"Analysis with id {analysis_id} does not exist")

            # 6) Check doc.backend_lock and possibly retry
            logger.info(f"[ASYNC] Doc {doc_id} backend lock: {doc.backend_lock}")
            if doc.backend_lock:
                logger.info(f"[ASYNC] Doc {doc_id} backend lock is True")
                retry_count = self.request.retries
                logger.info(f"[ASYNC]\tRetry count: {retry_count}")
                delay = min(INITIAL_DELAY + (retry_count * DELAY_INCREMENT), MAX_DELAY)
                logger.info(f"[ASYNC]\tNew delay: {delay}")

                if delay < MAX_DELAY:
                    logger.info("[ASYNC] Starting retry...")
                    raise self.retry(countdown=delay)

            # 7) If we passed all preflight checks, proceed to gather data and call async func
            try:

                @sync_to_async
                def get_pdf_text(doc: Document) -> str:
                    return doc.txt_extract_file.read().decode("utf-8")

                @sync_to_async
                def get_pawls_extract(doc: Document) -> Any:
                    return expand_pawls_pages(json.loads(doc.pawls_parse_file.read()))

                @sync_to_async
                def has_txt_extract(doc: Document) -> bool:
                    """
                    Safely check if the txt_extract_file field of the document is truthy.
                    """
                    return bool(doc.txt_extract_file)

                @sync_to_async
                def has_pawls_parse(doc: Document) -> bool:
                    """
                    Safely check if the pawls_parse_file field of the document is truthy.
                    """
                    return bool(doc.pawls_parse_file)

                if await has_txt_extract(doc):
                    pdf_text_extract = await get_pdf_text(doc)
                else:
                    pdf_text_extract = None

                if await has_pawls_parse(doc):
                    pdf_pawls_extract = await get_pawls_extract(doc)
                else:
                    pdf_pawls_extract = None

                pdf_data_layer = (
                    build_translation_layer(pdf_pawls_extract)
                    if pdf_pawls_extract
                    else []
                )

                # Key change: Wrap access to analysis.creator with sync_to_async
                @sync_to_async
                def get_analysis_creator(analysis):
                    return analysis.creator

                # Use the wrapped function to get creator
                creator = await get_analysis_creator(analysis)

                # Use creator in subsequent operations
                data_row, _ = await DocumentAnalysisRow.objects.aget_or_create(
                    document=doc,
                    analysis=analysis,
                    creator=creator,  # Use the safely retrieved creator
                )

                @sync_to_async
                def get_analysis_analyzer(analysis):
                    return analysis.analyzer

                analyzer = await get_analysis_analyzer(analysis)

                # -- Call the user's async function --
                result = await async_func(
                    pdf_text_extract=pdf_text_extract,
                    pdf_pawls_extract=pdf_pawls_extract,
                    *args,
                    **kwargs,
                )

                # Now do the same post-processing as doc_analyzer_task...
                if not isinstance(result, tuple) or len(result) != 4:
                    raise ValueError(
                        "Function must return a tuple of (List[str], List[OpenContractsAnnotationPythonType], "
                        "List[Dict[str, Any]], bool)"
                    )

                doc_annotations, span_label_pairs, metadata, task_pass = result

                if not isinstance(task_pass, bool):
                    raise ValueError(
                        "Fourth element of the return value must be true/false. "
                        "(False indicates failure for tests)."
                    )

                if task_pass:
                    # Validate doc_annotations, label pairs, metadata
                    if not isinstance(doc_annotations, list) or (
                        len(doc_annotations) > 0
                        and not all(isinstance(a, str) for a in doc_annotations)
                    ):
                        raise ValueError(
                            "First element of the tuple must be a list of doc labels"
                        )

                    if not isinstance(span_label_pairs, list):
                        raise ValueError(
                            "Second element of the tuple must be a list of (TextSpan, str) tuples"
                        )

                    if not isinstance(metadata, list) or (
                        len(metadata) > 0
                        and not all(
                            isinstance(m, dict) and "data" in m for m in metadata
                        )
                    ):
                        raise ValueError(
                            "Third element of the tuple must be a list of dictionaries with 'data' key"
                        )

                    resulting_annotations = []
                    for span_label_pair in span_label_pairs:
                        if not (
                            isinstance(span_label_pair, tuple)
                            and len(span_label_pair) == 2
                            and is_dict_instance_of_typed_dict(
                                span_label_pair[0], TextSpan
                            )
                            and isinstance(span_label_pair[1], str)
                        ):
                            raise ValueError(
                                "Second element of the tuple must be a list of (TextSpan, str) tuples"
                            )

                        # Handle PDF vs TXT annotation creation
                        if doc.file_type in ["application/pdf"]:
                            span, label_text = span_label_pair
                            annotation_data = (
                                pdf_data_layer.create_opencontract_annotation_from_span(
                                    {"span": span, "annotation_label": label_text}
                                )
                            )
                            logger.info(
                                f"[ASYNC] PDF Annotation data: {annotation_data}"
                            )
                            label_obj, _ = await AnnotationLabel.objects.aget_or_create(
                                text=annotation_data["annotationLabel"],
                                label_type=LabelType.TOKEN_LABEL,
                                creator=creator,
                                analyzer=analyzer,
                            )
                            annot = Annotation(
                                document=doc,
                                analysis=analysis,
                                annotation_label=label_obj,
                                page=annotation_data["page"],
                                raw_text=annotation_data["rawText"],
                                json=annotation_data["annotation_json"],
                                annotation_type=LabelType.TOKEN_LABEL,
                                creator=creator,
                                **({"corpus_id": corpus_id} if corpus_id else {}),
                            )
                            await annot.asave()
                            resulting_annotations.append(annot)

                        elif doc.file_type in ["application/txt", "text/plain"]:
                            span, label_text = span_label_pair
                            logger.info(
                                f"[ASYNC] TXT Annotation data: {label_text} / {span}"
                            )
                            label_obj, _ = await AnnotationLabel.objects.aget_or_create(
                                text=label_text,
                                label_type=LabelType.SPAN_LABEL,
                                creator=creator,
                                analyzer=analyzer,
                            )
                            annot = Annotation(
                                document=doc,
                                analysis=analysis,
                                annotation_label=label_obj,
                                page=1,
                                raw_text=span["text"],
                                annotation_type=LabelType.SPAN_LABEL,
                                json={"start": span["start"], "end": span["end"]},
                                creator=creator,
                                **({"corpus_id": corpus_id} if corpus_id else {}),
                            )
                            await annot.asave()
                            resulting_annotations.append(annot)

                        else:
                            raise ValueError(f"Unexpected file type: {doc.file_type}")

                    for doc_label in doc_annotations:
                        label_obj, _ = await AnnotationLabel.objects.aget_or_create(
                            text=doc_label,
                            label_type=LabelType.DOC_TYPE_LABEL,
                            creator=creator,
                            analyzer=analyzer,
                        )
                        annot = Annotation(
                            document=doc,
                            analysis=analysis,
                            annotation_label=label_obj,
                            page=1,
                            raw_text="",
                            json={},
                            annotation_type=LabelType.DOC_TYPE_LABEL,
                            creator=creator,
                            **({"corpus_id": corpus_id} if corpus_id else {}),
                        )
                        await annot.asave()
                        resulting_annotations.append(annot)

                    await data_row.annotations.aadd(*resulting_annotations)

                return result

            except ValueError:
                # Re-raise ValueError so these are not masked by the generic except
                raise

            except Exception as e:
                tb = traceback.format_exc()
                logger.error(
                    f"[ASYNC] Error in async_doc_analyzer_task for doc_id {kwargs.get('doc_id')}: {str(e)}\n{tb}"
                )
                # Use the doc_analyzer_task fallback shape
                return [], [], [{"data": {"error": str(e), "stack_trace": tb}}], False

        # Mark this as a doc_analyzer_task for any reflection
        wrapper.is_doc_analyzer_task = True
        wrapper._oc_doc_analyzer_input_schema = input_schema

        return wrapper

    return decorator


def celery_task_with_async_to_sync(*task_args, **task_kwargs) -> Callable:
    """
    Simplified decorator for async Celery tasks using AsyncToSync.

    This decorator converts async functions to sync functions that can be
    registered as Celery tasks, without creating new event loops or
    closing database connections.
    """

    def decorator(async_func: Callable[..., Any]) -> Callable[..., Any]:
        # Convert async to sync using asgiref
        sync_func = async_to_sync(async_func)

        # Register as a Celery task
        @shared_task(*task_args, **task_kwargs)
        @functools.wraps(async_func)
        def wrapper(*args, **kwargs):
            return sync_func(*args, **kwargs)

        # Expose underlying async func for testing if needed
        wrapper._async_func = async_func
        return wrapper

    return decorator
