import functools
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Optional, TypeVar, Union, cast

import requests
from celery import shared_task
from celery.utils.log import get_task_logger
from django.contrib.auth import get_user_model

from opencontractserver.annotations.models import Annotation, Note, Relationship
from opencontractserver.constants.document_processing import EMBEDDING_API_BATCH_SIZE
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.pipeline.base.embedder import BaseEmbedder
from opencontractserver.pipeline.base.exceptions import (
    EmbeddingClientError,
    EmbeddingServerError,
)
from opencontractserver.pipeline.utils import (
    get_component_by_name,
    get_default_embedder,
    get_default_embedder_path,
)
from opencontractserver.shared.mixins import HasEmbeddingMixin
from opencontractserver.types.enums import ContentModality
from opencontractserver.utils.embeddings import (
    synthesize_relationship_block_text,
)

User = get_user_model()

logger = get_task_logger(__name__)
logger.setLevel(logging.DEBUG)


def _create_text_embedding(
    obj: HasEmbeddingMixin,
    embedder: BaseEmbedder,
    embedder_path: str,
    text: str,
    obj_type: str,
    obj_id: int,
) -> bool:
    """
    Helper to create a text embedding for any object with HasEmbeddingMixin.

    Args:
        obj: The object to embed (Document, Note, etc.)
        embedder: The embedder instance to use
        embedder_path: Path identifier for the embedder
        text: The text to embed
        obj_type: Type name for logging (e.g., "document", "note")
        obj_id: Object ID for logging

    Returns:
        True if embedding was created successfully, False otherwise
    """
    if not text.strip():
        logger.info(f"{obj_type.capitalize()} {obj_id} has no text to embed.")
        return False

    logger.info(
        f"Generating text embedding for {obj_type} {obj_id} "
        f"with embedder {embedder_path} (text length={len(text)})"
    )

    vector = embedder.embed_text(text)

    if vector is None:
        logger.error(
            f"Embedding could not be generated for {obj_type} {obj_id} "
            f"using embedder {embedder_path}."
        )
        return False

    # Store the embedding - add_embedding handles duplicates via store_embedding
    embedding = obj.add_embedding(embedder_path, vector)

    if embedding:
        logger.info(
            f"Embedding for {obj_type} {obj_id} stored using path: {embedder_path} "
            f"(dimension={len(vector)})"
        )
        return True

    return False


def _create_embedding_for_annotation(
    annotation: Annotation,
    embedder: BaseEmbedder,
    embedder_path: str,
) -> bool:
    """
    Helper to create a single embedding for an annotation.

    Handles both text-only and multimodal embeddings based on annotation
    content and embedder capabilities.

    Args:
        annotation: The annotation to embed
        embedder: The embedder instance to use
        embedder_path: Path identifier for the embedder

    Returns:
        True if embedding was created successfully, False otherwise
    """
    modalities = annotation.content_modalities or [ContentModality.TEXT.value]
    has_images = ContentModality.IMAGE.value in modalities
    can_embed_images = embedder.is_multimodal and embedder.supports_images

    if can_embed_images and has_images:
        # Use multimodal embedding for annotations with images
        from opencontractserver.utils.multimodal_embeddings import (
            generate_multimodal_embedding,
        )

        logger.info(
            f"Using multimodal embedding for annotation {annotation.id} "
            f"with embedder {embedder_path} (modalities={modalities})"
        )
        try:
            vector = generate_multimodal_embedding(annotation, embedder)

            if vector is None:
                logger.error(
                    f"Embedding could not be generated for annotation {annotation.id} "
                    f"using embedder {embedder_path}."
                )
                return False

            logger.info(
                f"Generated multimodal embedding for annotation {annotation.id} "
                f"using {embedder_path} (dimension={len(vector)}, modalities={modalities})"
            )

            # Store the embedding - add_embedding handles duplicates via store_embedding
            embedding = annotation.add_embedding(embedder_path, vector)

            if embedding:
                logger.info(
                    f"Embedding for annotation {annotation.id} stored "
                    f"using path: {embedder_path}"
                )
                return True

            return False

        except Exception as e:
            # Graceful degradation: fall back to text-only if multimodal fails
            logger.warning(
                f"Multimodal embedding failed for annotation {annotation.id}: {e}. "
                f"Falling back to text-only embedding."
            )
            return _create_text_embedding(
                annotation,
                embedder,
                embedder_path,
                annotation.raw_text or "",
                "annotation",
                annotation.id,
            )
    # Standard text-only embedding (annotation is either text-only, or
    # contains images that the embedder cannot handle and will drop).
    if has_images and not can_embed_images:
        logger.debug(
            f"Annotation {annotation.id} has image content "
            f"(modalities={modalities}) but embedder {embedder_path} "
            f"does not support images; image content will be dropped."
        )

    return _create_text_embedding(
        annotation,
        embedder,
        embedder_path,
        annotation.raw_text or "",
        "annotation",
        annotation.id,
    )


class EmbeddingGenerationError(Exception):
    """Raised when embedding generation fails and should be retried."""

    pass


_EmbeddableT = TypeVar("_EmbeddableT", bound=HasEmbeddingMixin)


def _apply_dual_embedding_strategy(
    obj: _EmbeddableT,
    text: str,
    corpus_id: Optional[int],
    obj_type: str,
    obj_id: int,
    embed_func: Callable[[_EmbeddableT, BaseEmbedder, str], bool],
) -> None:
    """
    Apply the dual embedding strategy to any embeddable object.

    DUAL EMBEDDING STRATEGY:
    - ALWAYS creates a DEFAULT_EMBEDDER embedding (for global search)
    - ADDITIONALLY creates corpus-specific embedding if corpus uses different embedder

    Args:
        obj: The object to embed (must have HasEmbeddingMixin)
        text: The text to embed (used for early return check)
        corpus_id: Optional corpus ID for corpus-specific embedding
        obj_type: Type name for logging (e.g., "document", "annotation")
        obj_id: Object ID for logging
        embed_func: Function to call for creating embeddings (handles modality specifics)

    Raises:
        EmbeddingGenerationError: If the default embedding fails (triggers Celery retry).
            Corpus-specific embedding failures are logged but don't raise.
    """
    if not text.strip():
        logger.info(f"{obj_type.capitalize()} {obj_id} has no text to embed.")
        return

    # 1. Always create DEFAULT_EMBEDDER embedding (for global search)
    default_embedder_path = get_default_embedder_path()
    logger.info(
        f"Creating default embedding for {obj_type} {obj_id} "
        f"using {default_embedder_path} (for global search)"
    )

    default_embedding_succeeded = False
    default_embedding_error = None

    try:
        default_embedder_class = get_default_embedder()
        if default_embedder_class:
            default_embedder = default_embedder_class()
            default_embedding_succeeded = embed_func(
                obj, default_embedder, default_embedder_path
            )
            if not default_embedding_succeeded:
                default_embedding_error = "Embedder returned None or failed to store"
        else:
            default_embedding_error = "Could not get default embedder class"
            logger.error(f"Could not get default embedder for {obj_type} {obj_id}")
    except Exception as e:
        default_embedding_error = str(e)
        logger.error(f"Failed to create default embedding for {obj_type} {obj_id}: {e}")

    # 2. If corpus has different preferred_embedder, also create corpus-specific embedding
    # (This is optional - failures here don't fail the task)
    if corpus_id:
        try:
            corpus = Corpus.objects.get(id=corpus_id)
            corpus_embedder_path = corpus.preferred_embedder

            if corpus_embedder_path and corpus_embedder_path != default_embedder_path:
                logger.info(
                    f"Creating corpus-specific embedding for {obj_type} {obj_id} "
                    f"using {corpus_embedder_path} (corpus {corpus.id})"
                )
                try:
                    corpus_embedder_class = cast(
                        type[BaseEmbedder],
                        get_component_by_name(corpus_embedder_path),
                    )
                    corpus_embedder = corpus_embedder_class()
                    corpus_succeeded = embed_func(
                        obj, corpus_embedder, corpus_embedder_path
                    )
                    if not corpus_succeeded:
                        logger.warning(
                            f"Corpus embedding failed for {obj_type} {obj_id} "
                            f"with embedder {corpus_embedder_path} (non-fatal)"
                        )
                except Exception as e:
                    logger.error(
                        f"Failed to create corpus embedding for {obj_type} {obj_id} "
                        f"with embedder {corpus_embedder_path}: {e}"
                    )
            else:
                logger.debug(
                    f"Corpus {corpus.id} uses default embedder or has no preference, "
                    f"skipping duplicate corpus-specific embedding"
                )
        except Corpus.DoesNotExist:
            logger.warning(f"Corpus {corpus_id} not found")
        except Exception as e:
            logger.error(
                f"Error processing corpus-specific embedding for {obj_type} {obj_id}: {e}"
            )

    # 3. Raise if default embedding failed (triggers Celery retry)
    if not default_embedding_succeeded:
        raise EmbeddingGenerationError(
            f"Default embedding failed for {obj_type} {obj_id} "
            f"using {default_embedder_path}: {default_embedding_error}"
        )

    logger.info(f"Completed embedding generation for {obj_type} {obj_id}")


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60},
)
def calculate_embedding_for_doc_text(
    self, doc_id: Union[str, int], corpus_id: Optional[Union[str, int]] = None
) -> None:
    """
    Calculate embeddings for the text extracted from a document.

    DUAL EMBEDDING STRATEGY:
    - ALWAYS creates a DEFAULT_EMBEDDER embedding (for global search)
    - ADDITIONALLY creates corpus-specific embedding if corpus uses different embedder

    Retries automatically if any exception occurs, up to 3 times with a 60-second delay.

    Args:
        self: (Celery task instance, passed automatically when bind=True)
        doc_id (str | int): ID of the document.
        corpus_id (str | int, optional): ID of the corpus for corpus-specific embedding.
    """
    try:
        doc = Document.objects.get(id=doc_id)

        if doc.txt_extract_file.name:
            with doc.txt_extract_file.open("r") as txt_file:
                text = txt_file.read()
                # Workaround: Some django-storages backends (e.g., S3Boto3Storage with
                # certain configurations, or custom storage backends) may return bytes
                # even when files are opened in text mode ("r"). This can happen when:
                # - The storage backend doesn't properly handle the mode parameter
                # - Binary mode is forced by the underlying implementation
                # - File content-type metadata is missing or incorrect
                # See: https://github.com/jschneier/django-storages/issues/382
                if isinstance(text, bytes):
                    text = text.decode("utf-8")
        else:
            text = ""

        # Create embed function for documents (text-only)
        def doc_embed_func(obj, embedder, embedder_path):
            return _create_text_embedding(
                obj, embedder, embedder_path, text, "document", doc.id
            )

        _apply_dual_embedding_strategy(
            obj=doc,
            text=text,
            corpus_id=int(corpus_id) if corpus_id else None,
            obj_type="document",
            obj_id=doc.id,
            embed_func=doc_embed_func,
        )

    except Exception as e:
        logger.error(
            f"calculate_embedding_for_doc_text() - failed to generate embeddings due to error: {e}"
        )
        raise


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60},
)
def calculate_embedding_for_annotation_text(
    self,
    annotation_id: Union[str, int],
    corpus_id: Optional[Union[str, int]] = None,
    embedder_path: Optional[str] = None,
) -> None:
    """
    Calculate embeddings for an annotation's content (text, images, or both).

    DUAL EMBEDDING STRATEGY:
    - ALWAYS creates a DEFAULT_EMBEDDER embedding (for global search)
    - ADDITIONALLY creates corpus-specific embedding if corpus uses different embedder

    For multimodal embedders (e.g., CLIP ViT-L-14), this will:
    - Embed text content via embed_text()
    - Embed images via embed_image()
    - Combine mixed-modality content via weighted average

    All embeddings are stored in the same vector space, enabling cross-modal
    similarity search.

    Args:
        self: (Celery task instance, passed automatically when bind=True)
        annotation_id (str | int): ID of the annotation
        corpus_id (str | int, optional): ID of the corpus for corpus-specific embedding
        embedder_path (str, optional): Optional explicit embedder path to use (overrides all)
    """
    try:
        logger.info(f"Retrieving annotation with ID {annotation_id}")
        # Use select_related to avoid N+1 queries when accessing document/structural_set
        # for multimodal embeddings (structural annotations load PAWLs from structural_set)
        annotation = Annotation.objects.select_related(
            "document", "structural_set"
        ).get(pk=annotation_id)
    except Annotation.DoesNotExist:
        logger.warning(f"Annotation {annotation_id} not found.")
        return

    # If explicit embedder_path is provided, use only that (bypass dual embedding)
    if embedder_path:
        logger.info(
            f"Using explicit embedder_path {embedder_path} for annotation {annotation_id}"
        )
        try:
            embedder_class = cast(
                type[BaseEmbedder], get_component_by_name(embedder_path)
            )
            embedder = embedder_class()
            succeeded = _create_embedding_for_annotation(
                annotation, embedder, embedder_path
            )
            if not succeeded:
                raise EmbeddingGenerationError(
                    f"Embedding failed for annotation {annotation_id} "
                    f"using explicit embedder {embedder_path}"
                )
        except EmbeddingGenerationError:
            raise
        except Exception as e:
            logger.error(
                f"Failed to create embedding with explicit path {embedder_path}: {e}"
            )
            raise
        return

    # Use provided corpus_id or fall back to annotation's corpus_id
    effective_corpus_id = corpus_id or annotation.corpus_id

    # Apply dual embedding strategy using annotation-specific embed function
    # that handles multimodal content
    _apply_dual_embedding_strategy(
        obj=annotation,
        text=annotation.raw_text or "",
        corpus_id=int(effective_corpus_id) if effective_corpus_id else None,
        obj_type="annotation",
        obj_id=annotation.id,
        embed_func=cast(
            "Callable[[HasEmbeddingMixin, BaseEmbedder, str], bool]",
            _create_embedding_for_annotation,
        ),
    )


def _batch_embed_text_annotations(
    annotations: list[Annotation],
    embedder: BaseEmbedder,
    embedder_path: str,
    api_batch_size: int,
    result: dict,
) -> None:
    """
    Embed a list of text-only annotations using batched API calls.

    Groups annotation texts into sub-batches of ``api_batch_size``, calls
    ``embedder.embed_texts_batch()`` for each sub-batch, and stores the
    resulting vectors via ``add_embedding()``.

    Annotations whose text is empty or whitespace-only are skipped.
    Multimodal annotations should NOT be passed here — they require
    per-annotation handling via ``_create_embedding_for_annotation()``.

    Exception handling:
        - ``ValueError``: Re-raised immediately (programming/contract error).
        - ``requests.exceptions.Timeout``, ``requests.exceptions.ConnectionError``,
          ``EmbeddingServerError``: Re-raised so Celery task-level retry fires.
        - ``EmbeddingClientError``: Recorded as a permanent per-annotation
          failure for the chunk. Not re-raised so Celery retries are not burned
          on invalid input.
        - All other exceptions: Recorded as permanent per-annotation failures.

    Args:
        annotations: Ordered list of text-only Annotation objects.
        embedder: The embedder instance (must support ``embed_texts_batch``).
        embedder_path: Embedder path string stored alongside the vector.
        api_batch_size: Max texts per ``embed_texts_batch`` call.
        result: Mutable summary dict (keys: succeeded, failed, skipped, errors).
    """
    # Build (annotation, text) tuples, filtering out empties
    items: list[tuple[Annotation, str]] = []
    for annot in annotations:
        text = annot.raw_text or ""
        if not text.strip():
            logger.debug(f"Annotation {annot.id} has no text to embed, skipping.")
            result["skipped"] += 1
            continue
        items.append((annot, text))

    if not items:
        return

    # Carve into sub-batches up front so we can fan them out concurrently.
    chunks: list[list[tuple[Annotation, str]]] = [
        items[i : i + api_batch_size] for i in range(0, len(items), api_batch_size)
    ]

    # ------------------------------------------------------------------ #
    # Concurrency model
    # ------------------------------------------------------------------ #
    #
    # ``embedder.embed_max_concurrent_sub_batches`` controls how many
    # sub-batches the task is allowed to fly in parallel against the
    # provider. For local microservice embedders the default is 1
    # (single in-flight request); hosted embedders that comfortably
    # tolerate parallel requests (OpenAI) override it to 4-8.
    #
    # We deliberately keep the *DB writes* in the main thread:
    # ``add_embedding`` chains into Django ORM calls, and Django
    # connection management is per-thread — pinning writes to the
    # caller dodges that bookkeeping. The futures only own the HTTP
    # call, then return ``(chunk, vectors_or_exc)`` for the main
    # thread to drain.
    #
    # On a transient exception in any future we want celery's autoretry
    # to fire as soon as possible. Letting the exception propagate out of
    # the ``with`` block triggers ``ThreadPoolExecutor.__exit__`` which
    # calls ``shutdown(wait=True, cancel_futures=False)`` by default —
    # that blocks until every in-flight peer round-trip finishes,
    # delaying the retry by up to ~max_workers× the sub-batch latency.
    # Instead we capture the first transient exception, break out of the
    # ``as_completed`` loop, drop queued futures with
    # ``shutdown(wait=False, cancel_futures=True)``, then re-raise. Already
    # in-flight HTTP calls cannot be torn down from Python, but at least
    # we no longer wait for them. (issue #1410)
    max_workers = max(1, getattr(embedder, "embed_max_concurrent_sub_batches", 1))
    log_prefix = (
        f"embed_texts_batch (sub-batches={len(chunks)}, parallel={max_workers}, "
        f"embedder={embedder_path})"
    )
    logger.info(log_prefix)

    def _embed_one(chunk):
        texts_only = [text for _, text in chunk]
        return chunk, embedder.embed_texts_batch(texts_only)

    # Map future -> chunk index for logging/sub-batch numbering.
    #
    # Transient-error handling: instead of raising directly inside the
    # ``with`` block (which would call ``shutdown(wait=True)`` and block
    # until in-flight peers complete), we capture the first transient
    # exception, break out of the loop, and explicitly call
    # ``shutdown(wait=False, cancel_futures=True)`` before re-raising
    # outside the block. This unblocks Celery autoretry as fast as
    # possible. (issue #1410)
    transient_exc: Optional[BaseException] = None
    executor = ThreadPoolExecutor(max_workers=max_workers)
    try:
        future_to_idx = {
            executor.submit(_embed_one, chunk): idx for idx, chunk in enumerate(chunks)
        }
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                chunk, vectors = future.result()
            except ValueError:
                # ValueError indicates a caller contract violation (e.g., batch size
                # exceeds embedder maximum). Re-raise rather than silently recording
                # as an annotation failure so the programming error surfaces loudly.
                # The `finally` block below shuts down the executor with
                # cancel_futures=True; no need to repeat it here.
                raise
            except (
                requests.exceptions.Timeout,
                requests.exceptions.ConnectionError,
                EmbeddingServerError,
            ) as e:
                # Transient HTTP errors: re-raise so the task-level Celery
                # autoretry_for=(Exception,) decorator can fire a retry.
                # Defer the raise so we can drop queued futures first
                # without blocking on in-flight peers.
                transient_exc = e
                break
            except EmbeddingClientError as e:
                # Client errors (4xx): non-retriable, record as permanent
                # per-annotation failures. We explicitly swallow the exception
                # here (instead of letting it propagate) so the task's
                # autoretry_for=(Exception,) decorator does NOT burn retries
                # on invalid input that will never succeed.
                logger.error(f"sub-batch {idx + 1} client error (4xx): {e}")
                for annot, _ in chunks[idx]:
                    result["failed"] += 1
                    result["errors"].append(
                        f"Annotation {annot.id}: client error (4xx): {e}"
                    )
                continue
            except Exception as e:
                # Non-retriable errors (malformed response, unexpected data, etc.)
                # are recorded as permanent per-annotation failures.
                logger.error(f"sub-batch {idx + 1} failed: {e}")
                for annot, _ in chunks[idx]:
                    result["failed"] += 1
                    result["errors"].append(
                        f"Annotation {annot.id}: batch embed call failed: {e}"
                    )
                continue

            if vectors is None:
                logger.error(
                    f"sub-batch {idx + 1}: embed_texts_batch returned None for entire sub-batch"
                )
                for annot, _ in chunk:
                    result["failed"] += 1
                    result["errors"].append(
                        f"Annotation {annot.id}: batch embed returned None"
                    )
                continue

            if len(vectors) != len(chunk):
                logger.error(
                    f"sub-batch {idx + 1}: vector count mismatch — sent {len(chunk)} texts, "
                    f"received {len(vectors)} vectors. Failing entire chunk."
                )
                for annot, _ in chunk:
                    result["failed"] += 1
                    result["errors"].append(
                        f"Annotation {annot.id}: vector count mismatch "
                        f"({len(vectors)} vectors for {len(chunk)} texts)"
                    )
                continue

            # Store each vector in the main thread.
            # add_embedding() is idempotent (upserts via store_embedding), so
            # Celery retries of the whole task won't create duplicate records for
            # annotations that already succeeded in a previous attempt.
            for (annot, _), vector in zip(chunk, vectors):
                if vector is None:
                    result["failed"] += 1
                    result["errors"].append(
                        f"Annotation {annot.id}: individual vector was None in batch"
                    )
                    continue
                try:
                    embedding = annot.add_embedding(embedder_path, vector)
                    if embedding:
                        result["succeeded"] += 1
                    else:
                        result["failed"] += 1
                        result["errors"].append(
                            f"Annotation {annot.id}: add_embedding returned None"
                        )
                except Exception as e:
                    logger.error(
                        f"Failed to store embedding for annotation {annot.id}: {e}"
                    )
                    result["failed"] += 1
                    result["errors"].append(f"Annotation {annot.id}: store failed: {e}")
    finally:
        # On the transient-error fast path we want queued futures dropped
        # and the executor shut down without waiting on in-flight peers.
        # On the happy path ``shutdown(wait=False)`` is still safe — every
        # future has already been drained by ``as_completed``.
        executor.shutdown(wait=False, cancel_futures=True)

    if transient_exc is not None:
        # Re-raise the captured transient exception now that queued
        # futures have been cancelled. Celery's task-level
        # ``autoretry_for=(Exception,)`` decorator will fire.
        raise transient_exc


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60},
)
def calculate_embeddings_for_annotation_batch(
    self,
    annotation_ids: list[int],
    corpus_id: Optional[Union[str, int]] = None,
    embedder_path: Optional[str] = None,
) -> dict:
    """
    Calculate embeddings for a batch of annotations.

    This task processes multiple annotations in a single Celery task to prevent
    queue flooding when adding documents with many annotations to a corpus.

    When an explicit ``embedder_path`` is provided, text-only annotations are
    grouped and embedded via ``embed_texts_batch()`` for significantly better
    throughput (one HTTP request per sub-batch instead of one per annotation).
    Multimodal annotations (those with image content) are still processed
    individually since they require special handling (image extraction,
    weighted combination of text+image vectors).

    Without an explicit ``embedder_path``, the dual embedding strategy is
    applied per annotation (default + corpus-specific embedders).

    Retry semantics:
        - Transient HTTP errors (``requests.exceptions.Timeout``,
          ``requests.exceptions.ConnectionError``, ``EmbeddingServerError``
          from 5xx responses) propagate up and trigger the Celery
          ``autoretry_for=(Exception,)`` decorator for automatic retry.
        - ``EmbeddingClientError`` (4xx responses) is caught inside
          ``_batch_embed_text_annotations`` and recorded as a permanent
          per-annotation failure so retries are not burned on invalid input.
        - Non-retriable operational errors (malformed response, NaN
          values, count mismatch) are caught internally and recorded
          in ``result["errors"]`` without re-raising.
        - ``ValueError`` from contract violations (e.g., batch size
          exceeds embedder maximum) is caught at the task level and
          returned as an immediate failure without burning retries.

    Note on retry result counts:
        On Celery retry, the returned ``result`` dict is re-initialised
        to zero counts at the start of each attempt. Because
        ``add_embedding()`` is idempotent (upserts via ``store_embedding``),
        annotations that succeeded in a previous attempt are re-processed
        safely, but the final counts reflect only the last attempt — not
        the cumulative work across all retries. This is intentional; any
        monitoring that needs per-attempt vs cumulative distinction should
        read from Celery task state rather than ``result``.

    Args:
        self: Celery task instance (passed automatically when bind=True)
        annotation_ids: List of annotation IDs to embed
        corpus_id: Optional corpus ID for corpus-specific embeddings
        embedder_path: Optional explicit embedder path (bypasses dual embedding)

    Returns:
        dict: Summary with counts of succeeded, failed, and skipped annotations
    """
    result: dict[str, Any] = {
        "total": len(annotation_ids),
        "succeeded": 0,
        "failed": 0,
        "skipped": 0,
        "errors": [],
    }

    if not annotation_ids:
        return result

    logger.info(
        f"Processing batch of {len(annotation_ids)} annotations "
        f"(corpus_id={corpus_id}, embedder_path={embedder_path})"
    )

    # Get embedder instance once for the batch
    embedder: BaseEmbedder | None = None
    if embedder_path:
        try:
            embedder_class = cast(
                type[BaseEmbedder], get_component_by_name(embedder_path)
            )
            embedder = embedder_class()
        except Exception as e:
            logger.error(f"Failed to load embedder {embedder_path}: {e}")
            result["errors"].append(f"Failed to load embedder: {e}")
            result["failed"] = len(annotation_ids)
            return result

    # Fetch all annotations in batch to avoid N+1 queries
    annotations = Annotation.objects.select_related(
        "document", "structural_set"
    ).filter(pk__in=annotation_ids)

    annotation_map = {a.pk: a for a in annotations}

    # --- Explicit embedder path: use batch embedding for text-only annotations ---
    if embedder_path and embedder:
        can_embed_images = embedder.is_multimodal and embedder.supports_images

        # Partition annotations into text-only vs multimodal
        text_only_annots: list[Annotation] = []
        multimodal_annots: list[Annotation] = []

        for annotation_id in annotation_ids:
            annot = annotation_map.get(annotation_id)
            if not annot:
                logger.warning(f"Annotation {annotation_id} not found, skipping")
                result["skipped"] += 1
                continue

            modalities = annot.content_modalities or [ContentModality.TEXT.value]
            has_images = ContentModality.IMAGE.value in modalities

            if can_embed_images and has_images:
                multimodal_annots.append(annot)
            else:
                text_only_annots.append(annot)

        # Batch-embed text-only annotations.
        # Per-embedder ``api_batch_size`` falls back to the global default
        # for embedders that haven't overridden it (and for legacy paths
        # that pass an embedder instance without the attribute).
        api_batch_size = getattr(embedder, "api_batch_size", EMBEDDING_API_BATCH_SIZE)
        if text_only_annots:
            logger.info(
                f"Batch-embedding {len(text_only_annots)} text-only annotations "
                f"with {embedder_path} (api_batch_size={api_batch_size})"
            )
            # Snapshot all three outcome counters before the batch call so we
            # can compute how many text-only annotations were already accounted
            # for if a ValueError interrupts _batch_embed_text_annotations
            # mid-way. We need all three (skipped, failed, succeeded) because
            # the helper mutates result in-place as it processes sub-batches:
            # some annotations may have been skipped (empty text), some may
            # have succeeded, and some may have failed before the ValueError.
            # Without these baselines we'd double-count already-recorded outcomes.
            skipped_before_batch = result["skipped"]
            failed_before_batch = result["failed"]
            succeeded_before_batch = result["succeeded"]
            try:
                _batch_embed_text_annotations(
                    text_only_annots,
                    embedder,
                    embedder_path,
                    api_batch_size,
                    result,
                )
            except ValueError as e:
                # Programming error (e.g., batch size misconfiguration).
                # Fail fast without burning Celery retries.
                logger.error(f"Contract violation in batch embedding: {e}")
                result["errors"].append(f"Contract violation: {e}")
                # Count how many text-only annotations were already accounted for
                # by _batch_embed_text_annotations before it raised.
                batch_skipped = result["skipped"] - skipped_before_batch
                batch_failed = result["failed"] - failed_before_batch
                batch_succeeded = result["succeeded"] - succeeded_before_batch
                already_accounted = batch_skipped + batch_failed + batch_succeeded
                result["failed"] += len(text_only_annots) - already_accounted
                # Multimodal annotations were never processed; count as failed.
                result["failed"] += len(multimodal_annots)
                return result

        # Process multimodal annotations individually (need image extraction).
        # NOTE: The single-text path (_embed_text_impl) returns None on 5xx
        # rather than raising, so transient server errors for multimodal
        # annotations are recorded as permanent failures instead of triggering
        # Celery retry. This asymmetry with the batch path (which raises
        # EmbeddingServerError on 5xx) predates this PR and is accepted
        # because multimodal embedding involves image extraction that makes
        # blanket retry less straightforward.
        for annot in multimodal_annots:
            try:
                succeeded = _create_embedding_for_annotation(
                    annot, embedder, embedder_path
                )
                if succeeded:
                    result["succeeded"] += 1
                else:
                    result["failed"] += 1
                    result["errors"].append(
                        f"Annotation {annot.id}: multimodal embedding returned False"
                    )
            except Exception as e:
                logger.error(f"Failed to embed multimodal annotation {annot.id}: {e}")
                result["failed"] += 1
                result["errors"].append(f"Annotation {annot.id}: {str(e)}")

    # --- No explicit embedder: dual embedding strategy (per-annotation) ---
    else:
        for annotation_id in annotation_ids:
            annotation = annotation_map.get(annotation_id)

            if not annotation:
                logger.warning(f"Annotation {annotation_id} not found, skipping")
                result["skipped"] += 1
                continue

            try:
                effective_corpus_id = corpus_id or annotation.corpus_id
                _apply_dual_embedding_strategy(
                    obj=annotation,
                    text=annotation.raw_text or "",
                    corpus_id=(
                        int(effective_corpus_id) if effective_corpus_id else None
                    ),
                    obj_type="annotation",
                    obj_id=annotation.id,
                    embed_func=cast(
                        "Callable[[HasEmbeddingMixin, BaseEmbedder, str], bool]",
                        _create_embedding_for_annotation,
                    ),
                )
                result["succeeded"] += 1
            except Exception as e:
                logger.error(f"Failed to embed annotation {annotation_id}: {e}")
                result["failed"] += 1
                result["errors"].append(f"Annotation {annotation_id}: {str(e)}")

    logger.info(
        f"Batch embedding complete: {result['succeeded']} succeeded, "
        f"{result['failed']} failed, {result['skipped']} skipped"
    )

    return result


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60},
)
def calculate_embedding_for_note_text(
    self, note_id: Union[str, int], corpus_id: Optional[Union[str, int]] = None
) -> None:
    """
    Calculate embeddings for the text in a Note object.

    DUAL EMBEDDING STRATEGY:
    - ALWAYS creates a DEFAULT_EMBEDDER embedding (for global search)
    - ADDITIONALLY creates corpus-specific embedding if corpus uses different embedder

    Retries automatically if any exception occurs, up to 3 times with a 60-second delay.

    Args:
        self: (Celery task instance, passed automatically when bind=True)
        note_id (str | int): ID of the note.
        corpus_id (str | int, optional): ID of the corpus for corpus-specific embedding.
    """
    try:
        note = Note.objects.get(id=note_id)
        text = note.content

        if not isinstance(text, str) or len(text) == 0:
            logger.warning(f"Note with ID {note_id} has no content or is not a string")
            return

        # Use provided corpus_id or fall back to note's corpus_id
        effective_corpus_id = corpus_id or (note.corpus_id if note.corpus else None)

        # Create embed function for notes (text-only)
        def note_embed_func(obj, embedder, embedder_path):
            return _create_text_embedding(
                obj, embedder, embedder_path, text, "note", note.id
            )

        _apply_dual_embedding_strategy(
            obj=note,
            text=text,
            corpus_id=int(effective_corpus_id) if effective_corpus_id else None,
            obj_type="note",
            obj_id=note.id,
            embed_func=note_embed_func,
        )

    except Exception as e:
        logger.error(
            f"calculate_embedding_for_note_text() - failed to generate embeddings due to error: {e}"
        )
        raise


# --------------------------------------------------------------------------- #
# Relationship embeddings (issue #1645)
# --------------------------------------------------------------------------- #


def _embed_relationship(
    relationship: Relationship,
    embedder: BaseEmbedder,
    embedder_path: str,
    *,
    precomputed_text: str | None = None,
) -> bool:
    """Embed a single Relationship using ``synthesize_relationship_block_text``.

    Returns ``True`` on success, ``False`` on any failure. Mirrors the
    contract of ``_create_text_embedding`` for annotations so the dual-
    embedding helper can reuse the same call pattern.

    ``precomputed_text`` lets callers thread a single text synthesis
    through the dual-embedding strategy — without it the function
    would re-synthesize the block text on every embedder pass
    (default + corpus-preferred), which is wasted work when batches
    grow.
    """
    text = (
        precomputed_text
        if precomputed_text is not None
        else synthesize_relationship_block_text(relationship)
    )
    if not text.strip():
        logger.info(
            "Relationship %s has no text to embed (no non-empty source/target "
            "raw_text); skipping.",
            relationship.id,
        )
        return False

    logger.info(
        "Embedding relationship %s with %s (text length=%s)",
        relationship.id,
        embedder_path,
        len(text),
    )
    vector = embedder.embed_text(text)
    if vector is None:
        logger.error(
            "Embedder %s returned None for relationship %s",
            embedder_path,
            relationship.id,
        )
        return False

    embedding = relationship.add_embedding(embedder_path, vector)
    if embedding is None:
        logger.error(
            "store_embedding returned None for relationship %s using %s",
            relationship.id,
            embedder_path,
        )
        return False

    logger.info(
        "Stored relationship embedding %s for relationship %s (dim=%s, embedder=%s)",
        embedding.pk,
        relationship.id,
        len(vector),
        embedder_path,
    )
    return True


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60},
)
def calculate_embeddings_for_relationship_batch(
    self,
    relationship_ids: list[int],
    corpus_id: Optional[Union[str, int]] = None,
    embedder_path: Optional[str] = None,
) -> dict:
    """Embed a batch of relationships using the dual-embedding strategy.

    Mirrors ``calculate_embeddings_for_annotation_batch`` for relationships:
    when no ``embedder_path`` is supplied, each relationship is embedded
    with the default embedder AND (when distinct) the corpus's preferred
    embedder, so global-default search and corpus-scoped search both work.

    Unlike the annotation task we do NOT batch the wire calls
    via ``embed_texts_batch`` here — the volume of structural subtree
    groups is small relative to annotations (one per non-leaf node), so
    the simpler per-relationship dual-embedding loop is plenty. If subtree
    cardinality ever justifies batching, mirror
    ``_batch_embed_text_annotations`` and key on
    ``synthesize_relationship_block_text``.

    Args:
        self: Celery task instance (passed automatically when bind=True).
        relationship_ids: Relationships to embed.
        corpus_id: Optional corpus ID for corpus-specific embedding.
        embedder_path: Optional explicit embedder path that overrides the
            dual-embedding strategy entirely.

    Returns:
        Summary dict with ``succeeded``/``failed``/``skipped`` counts.

    Note:
        ``_dispatch_relationship_embeddings`` always supplies an explicit
        ``embedder_path``, dispatching two separate tasks to achieve dual
        embedding. The ``embedder_path=None`` branch below therefore exists
        for **direct callers** (tests, ad-hoc backfills, future schedulers
        that want a single task per relationship) — not for the materialiser
        path. Keep the branch wired even if it appears unused from the
        dispatcher: removing it would amputate the public single-call dual-
        embedding contract.
    """
    result: dict[str, Any] = {
        "total": len(relationship_ids),
        "succeeded": 0,
        "failed": 0,
        "skipped": 0,
        "errors": [],
    }

    if not relationship_ids:
        return result

    logger.info(
        "Embedding batch of %s relationships (corpus_id=%s, embedder_path=%s)",
        len(relationship_ids),
        corpus_id,
        embedder_path,
    )

    # ``synthesize_relationship_block_text`` uses ``values_list()`` on the
    # M2M managers, which bypasses Django's prefetch cache (it stores model
    # instances, not raw column tuples). Prefetching here would be dead
    # weight — issue 2N extra wire round-trips for nothing. We accept the
    # 2-queries-per-relationship cost; subtree-group cardinality is small
    # (one row per non-leaf node) so the extra round-trips per batch stay
    # bounded. If batches ever grow large enough to matter, the cleaner
    # fix is to teach the helper to accept a pre-fetched list of raw_text
    # strings, not to add prefetches that do nothing.
    relationships = list(Relationship.objects.filter(pk__in=relationship_ids))
    rel_map = {r.pk: r for r in relationships}

    if embedder_path:
        try:
            embedder_class = cast(
                type[BaseEmbedder], get_component_by_name(embedder_path)
            )
            explicit_embedder = embedder_class()
        except Exception as e:
            logger.error(f"Failed to load embedder {embedder_path}: {e}")
            result["errors"].append(f"Failed to load embedder: {e}")
            result["failed"] = len(relationship_ids)
            return result

        for rid in relationship_ids:
            rel = rel_map.get(rid)
            if rel is None:
                result["skipped"] += 1
                continue
            try:
                if _embed_relationship(rel, explicit_embedder, embedder_path):
                    result["succeeded"] += 1
                else:
                    result["failed"] += 1
                    result["errors"].append(
                        f"Relationship {rid}: embedding returned None or empty"
                    )
            except Exception as e:
                logger.error(f"Failed to embed relationship {rid}: {e}")
                result["failed"] += 1
                result["errors"].append(f"Relationship {rid}: {e}")
        return result

    # Dual-embedding strategy: default embedder is mandatory; the corpus's
    # preferred embedder is best-effort. Delegates to
    # ``_apply_dual_embedding_strategy`` — Relationship satisfies the same
    # ``HasEmbeddingMixin``-with-``creator`` shape that the annotation path
    # uses, so the existing store_embedding plumbing works without
    # reimplementation. ``precomputed_text`` keeps text synthesis to one
    # call per relationship across both embedder passes.
    for rid in relationship_ids:
        rel = rel_map.get(rid)
        if rel is None:
            result["skipped"] += 1
            continue
        try:
            # Synthesize once per relationship and thread the result
            # through both embedder passes (default + corpus-preferred)
            # via a partial. Avoids re-running the source/target
            # text assembly inside ``_embed_relationship`` for every
            # embedder.
            rel_text = synthesize_relationship_block_text(rel)
            _apply_dual_embedding_strategy(
                obj=rel,
                text=rel_text,
                corpus_id=int(corpus_id) if corpus_id else None,
                obj_type="relationship",
                obj_id=rel.id,
                embed_func=functools.partial(
                    _embed_relationship, precomputed_text=rel_text
                ),
            )
            result["succeeded"] += 1
        except Exception as e:
            logger.error(f"Failed to embed relationship {rid}: {e}")
            result["failed"] += 1
            result["errors"].append(f"Relationship {rid}: {e}")

    logger.info(
        "Relationship batch embedding complete: %s succeeded, %s failed, %s skipped",
        result["succeeded"],
        result["failed"],
        result["skipped"],
    )
    return result
