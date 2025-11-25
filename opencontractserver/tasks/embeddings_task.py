import logging
from typing import Union

from celery import shared_task
from celery.utils.log import get_task_logger
from django.conf import settings
from django.contrib.auth import get_user_model

# from config import celery_app
from opencontractserver.annotations.models import Annotation, Note
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.pipeline.utils import get_default_embedder
from opencontractserver.utils.embeddings import generate_embeddings_from_text

User = get_user_model()

logger = get_task_logger(__name__)
logger.setLevel(logging.DEBUG)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60},
)
def calculate_embedding_for_doc_text(
    self, doc_id: Union[str, int], corpus_id: Union[str, int]
) -> None:
    """
    Calculate embeddings for the text extracted from a document, using its associated corpus.
    Retries automatically if any exception occurs, up to 3 times with a 60-second delay.

    Args:
        self: (Celery task instance, passed automatically when bind=True)
        doc_id (str | int): ID of the document.
        corpus_id (str | int): ID of the corpus to use for embedding.
    """
    try:
        doc = Document.objects.get(id=doc_id)

        if doc.txt_extract_file.name:
            with doc.txt_extract_file.open("r") as txt_file:
                text = txt_file.read()
        else:
            text = ""

        corpus = Corpus.objects.get(id=corpus_id)
        embedder_path, embeddings = corpus.embed_text(text)
        doc.add_embedding(embedder_path, embeddings)

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
    self, annotation_id: Union[str, int], embedder_path: str = None
) -> None:
    """
    Calculate embeddings for an annotation's text.

    Args:
        self: (Celery task instance, passed automatically when bind=True)
        annotation_id (str | int): ID of the annotation
        embedder_path (str, optional): Optional explicit embedder path to use (highest precedence)
    """
    try:
        logger.info(f"Retrieving annotation with ID {annotation_id}")
        annotation = Annotation.objects.get(pk=annotation_id)
    except Annotation.DoesNotExist:
        logger.warning(f"Annotation {annotation_id} not found.")
        return

    corpus_id = annotation.corpus_id  # if your annotation references a corpus
    logger.info(f"Processing annotation {annotation_id} with corpus_id {corpus_id}")

    text = annotation.raw_text or ""
    if not text.strip():
        logger.info(f"Annotation {annotation_id} has no raw_text to embed.")
        return

    logger.info(
        f"Generating embeddings for annotation {annotation_id} with text length {len(text)}"
    )
    # If we want to override the embedder path, do so. If not, generate_embeddings_from_text
    # will figure out from the corpus or fallback to default microservice or embedder.
    returned_path, vector = generate_embeddings_from_text(
        text, corpus_id=corpus_id, embedder_path=embedder_path
    )
    logger.info(
        f"Generated embeddings for annotation {annotation_id} using {returned_path}"
    )

    if vector is None:
        logger.error(
            f"Embedding could not be generated for annotation {annotation_id}."
        )
        return

    # If user explicitly requested an embedder path override, replace
    # the path from the function's defaults:
    final_path = embedder_path if embedder_path else returned_path

    # Now store the embedding
    embedding = annotation.add_embedding(final_path or "unknown-embedder", vector)

    # Set the reverse FK so annotation.embeddings points to the embedding
    if embedding:
        annotation.embeddings = embedding
        annotation.save(update_fields=["embeddings"])

    logger.info(
        f"Embedding for Annotation {annotation_id} stored using path: {final_path}, dimension={len(vector)}."
    )


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 60},
)
def calculate_embedding_for_note_text(self, note_id: Union[str, int]) -> None:
    """
    Calculate embeddings for the text in a Note object, possibly falling back to a default embedder.
    Retries automatically if any exception occurs, up to 3 times with a 60-second delay.

    Args:
        self: (Celery task instance, passed automatically when bind=True)
        note_id (str | int): ID of the note.
    """
    try:
        note = Note.objects.get(id=note_id)
        text = note.content

        if not isinstance(text, str) or len(text) == 0:
            logger.warning(f"Note with ID {note_id} has no content or is not a string")
            return

        try:
            embedder_path, embeddings = note.corpus.embed_text(text)
        except Exception as e:
            logger.warning(
                f"Failed to use corpus embedder: {e}. Falling back to default embedder."
            )
            embedder_path = settings.DEFAULT_EMBEDDER
            embedder_class = get_default_embedder()
            embedder = embedder_class()  # Create an instance
            embeddings = embedder.embed_text(text)

        note.add_embedding(embedder_path, embeddings)

    except Exception as e:
        logger.error(
            f"calculate_embedding_for_note_text() - failed to generate embeddings due to error: {e}"
        )
        raise
