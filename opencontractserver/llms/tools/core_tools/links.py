"""Tools for generating markdown deep-links to OpenContracts entities."""

from opencontractserver.constants.truncation import MAX_LINK_TITLE_LENGTH
from opencontractserver.utils.text import truncate


def create_markdown_link(
    entity_type: str,
    entity_id: int,
) -> str:
    """
    Create a markdown link for a given entity (annotation, corpus, document, or conversation/thread).

    This tool generates markdown-formatted links following OpenContracts URL routing patterns.
    The generated links can be used in notes, summaries, or agent responses to reference
    specific entities within the system.

    Args:
        entity_type: Type of entity - one of: "annotation", "corpus", "document", "conversation"
        entity_id: The primary key (ID) of the entity

    Returns:
        A markdown-formatted link string: [Entity Title](URL)

        Examples:
            - Annotation: [Annotation 123](/d/john/my-corpus/my-doc?ann=123)
            - Corpus: [Legal Contracts](/c/john-doe/legal-contracts)
            - Document: [Contract.pdf](/d/john-doe/my-corpus/contract-pdf)
            - Conversation: [Discussion about X](/c/john/corpus/discussions/thread-123)

    Raises:
        ValueError: If entity_type is invalid, entity doesn't exist, or required slugs are missing

    Note:
        - Documents can be standalone or belong to a corpus (link includes corpus if available)
        - Annotations always include their parent document context in the link
        - Conversations/threads must be associated with a corpus for proper URL generation
        - All URLs use slugs for human-readable links (e.g., /c/john/my-corpus)
    """
    from opencontractserver.annotations.models import Annotation
    from opencontractserver.conversations.models import Conversation
    from opencontractserver.corpuses.models import Corpus
    from opencontractserver.documents.models import Document

    # Validate entity_type
    valid_types = {"annotation", "corpus", "document", "conversation"}
    if entity_type not in valid_types:
        raise ValueError(
            f"Invalid entity_type '{entity_type}'. Must be one of: {valid_types}"
        )

    try:
        if entity_type == "annotation":
            # Annotation link: /d/{userSlug}/{corpusSlug}/{docSlug}?ann={annotationId}
            # or /d/{userSlug}/{docSlug}?ann={annotationId} for standalone docs
            annotation = Annotation.objects.select_related(
                "document", "document__creator", "corpus", "corpus__creator"
            ).get(pk=entity_id)

            if not annotation.document:
                raise ValueError(
                    f"Annotation {entity_id} has no associated document and cannot be linked."
                )

            doc = annotation.document
            corpus = annotation.corpus

            # Get user slug from document creator
            if not doc.creator or not doc.creator.username:
                raise ValueError(
                    f"Document {doc.id} has no creator and cannot generate a link."
                )
            user_slug = doc.creator.username

            # Build document path
            if corpus and corpus.slug:
                # Document within corpus: /d/{userSlug}/{corpusSlug}/{docSlug}?ann={annotationId}
                if not doc.slug:
                    raise ValueError(
                        f"Document {doc.id} has no slug and cannot generate a link."
                    )
                url = f"/d/{user_slug}/{corpus.slug}/{doc.slug}?ann={entity_id}"
            else:
                # Standalone document: /d/{userSlug}/{docSlug}?ann={annotationId}
                if not doc.slug:
                    raise ValueError(
                        f"Document {doc.id} has no slug and cannot generate a link."
                    )
                url = f"/d/{user_slug}/{doc.slug}?ann={entity_id}"

            # Create title from annotation's raw_text or generic label
            title = (
                annotation.raw_text
                if annotation.raw_text
                else f"Annotation {entity_id}"
            )
            title = truncate(title, MAX_LINK_TITLE_LENGTH, suffix="...")

            return f"[{title}]({url})"

        elif entity_type == "corpus":
            # Corpus link: /c/{userSlug}/{corpusSlug}
            corpus = Corpus.objects.select_related("creator").get(pk=entity_id)

            if not corpus.creator or not corpus.creator.username:
                raise ValueError(
                    f"Corpus {entity_id} has no creator and cannot generate a link."
                )
            if not corpus.slug:
                raise ValueError(
                    f"Corpus {entity_id} has no slug and cannot generate a link."
                )

            user_slug = corpus.creator.username
            url = f"/c/{user_slug}/{corpus.slug}"
            title = corpus.title if corpus.title else f"Corpus {entity_id}"

            return f"[{title}]({url})"

        elif entity_type == "document":
            # Document link: /d/{userSlug}/{corpusSlug}/{docSlug} (if in corpus)
            # or /d/{userSlug}/{docSlug} (standalone)
            doc = Document.objects.select_related("creator").get(pk=entity_id)

            if not doc.creator or not doc.creator.username:
                raise ValueError(
                    f"Document {entity_id} has no creator and cannot generate a link."
                )
            if not doc.slug:
                raise ValueError(
                    f"Document {entity_id} has no slug and cannot generate a link."
                )

            user_slug = doc.creator.username

            # Check if document belongs to a corpus (via annotations)
            # Documents don't have direct corpus FK, but annotations do
            corpus = None
            first_annotation = (
                Annotation.objects.filter(document=doc)
                .exclude(corpus__isnull=True)
                .select_related("corpus")
                .first()
            )
            if first_annotation and first_annotation.corpus:
                corpus = first_annotation.corpus

            if corpus and corpus.slug:
                url = f"/d/{user_slug}/{corpus.slug}/{doc.slug}"
            else:
                url = f"/d/{user_slug}/{doc.slug}"

            title = doc.title if doc.title else f"Document {entity_id}"

            return f"[{title}]({url})"

        elif entity_type == "conversation":
            # Conversation/thread link: /c/{userSlug}/{corpusSlug}/discussions/{conversationId}
            conversation = Conversation.objects.select_related(
                "chat_with_corpus", "chat_with_corpus__creator"
            ).get(pk=entity_id)

            # Conversations require a corpus context for URL generation
            if not conversation.chat_with_corpus:
                raise ValueError(
                    f"Conversation {entity_id} has no associated corpus and cannot generate a discussion link. "
                    "Only corpus-scoped conversations can be linked."
                )

            corpus = conversation.chat_with_corpus
            if not corpus.creator or not corpus.creator.username:
                raise ValueError(
                    f"Corpus {corpus.id} has no creator and cannot generate a link."
                )
            if not corpus.slug:
                raise ValueError(
                    f"Corpus {corpus.id} has no slug and cannot generate a link."
                )

            user_slug = corpus.creator.username
            url = f"/c/{user_slug}/{corpus.slug}/discussions/{entity_id}"
            title = (
                conversation.title if conversation.title else f"Discussion {entity_id}"
            )

            return f"[{title}]({url})"

    except Annotation.DoesNotExist:
        raise ValueError(f"Annotation with id={entity_id} does not exist.")
    except Corpus.DoesNotExist:
        raise ValueError(f"Corpus with id={entity_id} does not exist.")
    except Document.DoesNotExist:
        raise ValueError(f"Document with id={entity_id} does not exist.")
    except Conversation.DoesNotExist:
        raise ValueError(f"Conversation with id={entity_id} does not exist.")


async def acreate_markdown_link(
    entity_type: str,
    entity_id: int,
) -> str:
    """
    Async version: Create a markdown link for a given entity.

    See :func:`create_markdown_link` for detailed documentation.

    Args:
        entity_type: Type of entity - one of: "annotation", "corpus", "document", "conversation"
        entity_id: The primary key (ID) of the entity

    Returns:
        A markdown-formatted link string: [Entity Title](URL)

    Raises:
        ValueError: If entity_type is invalid, entity doesn't exist, or required slugs are missing
    """
    from opencontractserver.annotations.models import Annotation
    from opencontractserver.conversations.models import Conversation
    from opencontractserver.corpuses.models import Corpus
    from opencontractserver.documents.models import Document

    # Validate entity_type
    valid_types = {"annotation", "corpus", "document", "conversation"}
    if entity_type not in valid_types:
        raise ValueError(
            f"Invalid entity_type '{entity_type}'. Must be one of: {valid_types}"
        )

    try:
        if entity_type == "annotation":
            annotation = await Annotation.objects.select_related(
                "document", "document__creator", "corpus", "corpus__creator"
            ).aget(pk=entity_id)

            if not annotation.document:
                raise ValueError(
                    f"Annotation {entity_id} has no associated document and cannot be linked."
                )

            doc = annotation.document
            corpus = annotation.corpus

            if not doc.creator or not doc.creator.username:
                raise ValueError(
                    f"Document {doc.id} has no creator and cannot generate a link."
                )
            user_slug = doc.creator.username

            if corpus and corpus.slug:
                if not doc.slug:
                    raise ValueError(
                        f"Document {doc.id} has no slug and cannot generate a link."
                    )
                url = f"/d/{user_slug}/{corpus.slug}/{doc.slug}?ann={entity_id}"
            else:
                if not doc.slug:
                    raise ValueError(
                        f"Document {doc.id} has no slug and cannot generate a link."
                    )
                url = f"/d/{user_slug}/{doc.slug}?ann={entity_id}"

            title = (
                annotation.raw_text
                if annotation.raw_text
                else f"Annotation {entity_id}"
            )
            title = truncate(title, MAX_LINK_TITLE_LENGTH, suffix="...")

            return f"[{title}]({url})"

        elif entity_type == "corpus":
            corpus = await Corpus.objects.select_related("creator").aget(pk=entity_id)

            if not corpus.creator or not corpus.creator.username:
                raise ValueError(
                    f"Corpus {entity_id} has no creator and cannot generate a link."
                )
            if not corpus.slug:
                raise ValueError(
                    f"Corpus {entity_id} has no slug and cannot generate a link."
                )

            user_slug = corpus.creator.username
            url = f"/c/{user_slug}/{corpus.slug}"
            title = corpus.title if corpus.title else f"Corpus {entity_id}"

            return f"[{title}]({url})"

        elif entity_type == "document":
            doc = await Document.objects.select_related("creator").aget(pk=entity_id)

            if not doc.creator or not doc.creator.username:
                raise ValueError(
                    f"Document {entity_id} has no creator and cannot generate a link."
                )
            if not doc.slug:
                raise ValueError(
                    f"Document {entity_id} has no slug and cannot generate a link."
                )

            user_slug = doc.creator.username

            corpus = None
            first_annotation = await (
                Annotation.objects.filter(document=doc)
                .exclude(corpus__isnull=True)
                .select_related("corpus")
                .afirst()
            )
            if first_annotation and first_annotation.corpus:
                corpus = first_annotation.corpus

            if corpus and corpus.slug:
                url = f"/d/{user_slug}/{corpus.slug}/{doc.slug}"
            else:
                url = f"/d/{user_slug}/{doc.slug}"

            title = doc.title if doc.title else f"Document {entity_id}"

            return f"[{title}]({url})"

        elif entity_type == "conversation":
            conversation = await Conversation.objects.select_related(
                "chat_with_corpus", "chat_with_corpus__creator"
            ).aget(pk=entity_id)

            if not conversation.chat_with_corpus:
                raise ValueError(
                    f"Conversation {entity_id} has no associated corpus and cannot generate a discussion link. "
                    "Only corpus-scoped conversations can be linked."
                )

            corpus = conversation.chat_with_corpus
            if not corpus.creator or not corpus.creator.username:
                raise ValueError(
                    f"Corpus {corpus.id} has no creator and cannot generate a link."
                )
            if not corpus.slug:
                raise ValueError(
                    f"Corpus {corpus.id} has no slug and cannot generate a link."
                )

            user_slug = corpus.creator.username
            url = f"/c/{user_slug}/{corpus.slug}/discussions/{entity_id}"
            title = (
                conversation.title if conversation.title else f"Discussion {entity_id}"
            )

            return f"[{title}]({url})"

    except Annotation.DoesNotExist:
        raise ValueError(f"Annotation with id={entity_id} does not exist.")
    except Corpus.DoesNotExist:
        raise ValueError(f"Corpus with id={entity_id} does not exist.")
    except Document.DoesNotExist:
        raise ValueError(f"Document with id={entity_id} does not exist.")
    except Conversation.DoesNotExist:
        raise ValueError(f"Conversation with id={entity_id} does not exist.")
