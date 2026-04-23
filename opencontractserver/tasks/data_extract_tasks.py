# opencontractserver/tasks/data_extract_tasks.py
import json
import logging
import os

from asgiref.sync import sync_to_async

from opencontractserver.annotations.compact_json import iter_page_annotations
from opencontractserver.constants.extraction import DEFAULT_EXTRACT_MODEL
from opencontractserver.extracts.models import Datacell
from opencontractserver.shared.decorators import celery_task_with_async_to_sync
from opencontractserver.utils.compact_pawls import expand_pawls_pages
from opencontractserver.utils.extraction_grounding import (
    ground_extraction_to_annotations,
)

logger = logging.getLogger(__name__)


@sync_to_async
def get_annotation_label_text(annotation):
    """
    Safely get the annotation label text from an annotation object.

    Args:
        annotation: The annotation object to get the label text from.

    Returns:
        str: The label text or 'Unlabeled' if no label exists.
    """
    return (
        annotation.annotation_label.text if annotation.annotation_label else "Unlabeled"
    )


@sync_to_async
def get_column_search_params(datacell):
    """
    Safely get the search text and query from a datacell's column.

    Args:
        datacell: The datacell object to get search parameters from.

    Returns:
        tuple: A tuple containing (match_text, query).
    """
    return datacell.column.match_text, datacell.column.query


@sync_to_async
def get_relationship_label_text(relationship):
    """
    Safely get the relationship label text from a relationship object.

    Args:
        relationship: The relationship object to get the label text from.

    Returns:
        str: The label text or 'relates_to' if no label exists.
    """
    return (
        relationship.relationship_label.text
        if relationship.relationship_label
        else "relates_to"
    )


@sync_to_async
def get_column_extraction_params(datacell):
    """
    Safely get the output_type, instructions, and extract_is_list from a datacell's column.

    Args:
        datacell: The datacell object to get extraction parameters from.

    Returns:
        tuple: A tuple containing (output_type, instructions, extract_is_list).
    """
    return (
        datacell.column.output_type,
        datacell.column.instructions,
        datacell.column.extract_is_list,
    )


@celery_task_with_async_to_sync()
async def doc_extract_query_task(
    cell_id: int,
    similarity_top_k: int = 10,
    max_token_length: int = 64000,
    model_override: str | None = None,
) -> None:
    """
    OpenContracts' BLAZING FAST agent-based data extraction pipeline.
    Powered by our battle-tested structured extraction API.
    No more marvin. No more flakiness. Just pure extraction power! 🚀

    Args:
        cell_id: Primary key of the Datacell to populate.
        similarity_top_k: Top-k neighbours to retrieve when calling the agent.
        max_token_length: Soft cap on prompt tokens (reserved for future use).
        model_override: Optional model identifier (e.g. ``"openai:gpt-4o"``,
            ``"anthropic:claude-opus-4-6"``). When provided it overrides the
            default extraction model. Used by the benchmark runner to sweep
            models without touching production defaults.
    """
    import traceback
    from typing import get_origin

    from django.utils import timezone
    from pydantic import BaseModel
    from pydantic_ai import capture_run_messages
    from pydantic_ai.messages import ModelMessagesTypeAdapter

    from opencontractserver.llms import agents
    from opencontractserver.llms.types import AgentFramework
    from opencontractserver.utils.etl import parse_model_or_primitive

    logger = logging.getLogger(__name__)

    # -------------------------------------------------------------------------
    # Helper functions
    # -------------------------------------------------------------------------
    @sync_to_async
    def sync_get_datacell(pk: int):
        """Get datacell with all related objects."""
        return Datacell.objects.select_related(
            "extract", "column", "document", "creator"
        ).get(pk=pk)

    @sync_to_async
    def sync_mark_started(dc):
        """Mark datacell as started."""
        dc.started = timezone.now()
        dc.save()

    @sync_to_async
    def sync_mark_completed(dc, data_dict, llm_log=None):
        """Mark datacell as completed with data and optional LLM log."""
        dc.data = data_dict
        dc.completed = timezone.now()
        if llm_log:
            dc.llm_call_log = llm_log
        dc.save()

    @sync_to_async
    def sync_mark_failed(dc, exc, tb, llm_log=None):
        """Mark datacell as failed with error and optional LLM log."""
        dc.stacktrace = f"Error: {exc}\n\nTraceback:\n{tb}"
        dc.failed = timezone.now()
        if llm_log:
            dc.llm_call_log = llm_log
        dc.save()

    @sync_to_async
    def sync_get_corpus_id(document):
        """Get corpus ID for document via DocumentPath."""
        from opencontractserver.documents.models import DocumentPath

        doc_path = DocumentPath.objects.filter(document=document).first()
        if doc_path:
            return doc_path.corpus_id
        return None

    @sync_to_async
    def sync_add_sources(datacell, sources):
        """Add source annotations to datacell."""
        if sources:
            # Extract annotation IDs from SourceNode objects
            annotation_ids = [s.annotation_id for s in sources if s.annotation_id > 0]
            if annotation_ids:
                datacell.sources.add(*annotation_ids)

    @sync_to_async
    def _link_retrieval_citations(datacell, annotation_ids):
        """Link raw Annotation PKs retrieved by the agent to ``datacell.sources``.

        Filters defensively: only positive ints that correspond to real
        Annotation rows are persisted.  Duplicates are deduped by the M2M
        unique constraint, so ``add(*ids)`` with repeats is safe.
        """
        from opencontractserver.annotations.models import Annotation

        valid_ids = [int(a) for a in annotation_ids if isinstance(a, int) and a > 0]
        if not valid_ids:
            return
        # Guard against IDs that don't exist (e.g. race with deletion).
        existing = set(
            Annotation.objects.filter(id__in=valid_ids).values_list("id", flat=True)
        )
        existing_ids = [aid for aid in valid_ids if aid in existing]
        if existing_ids:
            datacell.sources.add(*existing_ids)

    # Initialize datacell to None to avoid UnboundLocalError
    datacell = None

    logger.info("=" * 60)
    logger.info(f"doc_extract_query_task STARTED for cell_id: {cell_id}")
    logger.info(f"  similarity_top_k: {similarity_top_k}")
    logger.info(f"  max_token_length: {max_token_length}")

    try:
        # 1. Setup
        datacell = await sync_get_datacell(cell_id)
        logger.info(f"Retrieved datacell {cell_id}")
        await sync_mark_started(datacell)
        logger.info(f"Marked datacell {cell_id} as started")

        document = datacell.document
        column = datacell.column
        logger.info(f"Document: {document.id}, Column: {column.name}")

        # Get corpus ID (None if document isn't in a corpus - that's OK now!)
        corpus_id = await sync_get_corpus_id(document)
        logger.info(f"Corpus ID: {corpus_id}")

        # 2. Parse the output type
        output_type = parse_model_or_primitive(column.output_type)

        # Handle list types
        if column.extract_is_list:
            # If it's not already a List type, wrap it
            if get_origin(output_type) is not list:
                output_type = list[output_type]

        # 3. Build the prompt
        prompt = column.query if column.query else column.match_text
        if not prompt:
            raise ValueError("Column must have either query or match_text!")

        # 4. Build system prompt with constraints
        # system_prompt_parts = [
        #     "You are a precise data extraction agent.",
        #     "Extract ONLY the requested information from the document.",
        #     "If the information is not present, return None rather than guessing.",
        # ]

        # Add must_contain_text constraint
        # if column.must_contain_text:
        #     system_prompt_parts.append(
        #         f"\nIMPORTANT: Only extract data from sections that contain the text: '{column.must_contain_text}'"
        #     )
        #     logger.info(f"Added must_contain_text constraint: {column.must_contain_text}")

        # Add limit_to_label constraint
        # if column.limit_to_label:
        #     system_prompt_parts.append(
        #         f"\nIMPORTANT: Only extract data from annotations labeled as: '{column.limit_to_label}'"
        #     )
        #     logger.info(f"Added limit_to_label constraint: {column.limit_to_label}")

        # system_prompt = "\n".join(system_prompt_parts)
        # logger.info(f"System prompt: {system_prompt[:200]}...")

        # 5. Build extra context from instructions and match_text
        # extra_context_parts = []

        # if column.instructions:
        #     extra_context_parts.append(
        #         f"Additional instructions: {column.instructions}"
        #     )
        #     logger.info(f"Added instructions: {column.instructions[:100]}...")

        # Handle special match_text with ||| separator (few-shot examples)
        if column.match_text and "|||" in column.match_text:
            examples = [
                ex.strip() for ex in column.match_text.split("|||") if ex.strip()
            ]
            if examples:
                prompt += (
                    "Here are example values to guide your extraction:\n"
                    + "\n".join(f"- {ex}" for ex in examples)
                )
                logger.info(f"Added {len(examples)} few-shot examples from match_text")

        # extra_context = (
        #     "\n\n".join(extra_context_parts) if extra_context_parts else None
        # )

        # if extra_context:
        #     logger.info(f"Extra context: {extra_context[:200]}...")

        # 6. EXTRACT! 🚀
        logger.info(f"Starting extraction for datacell {cell_id}:")
        logger.info(f"  - Document ID: {document.id}")
        logger.info(
            f"  - Document title: {document.title if hasattr(document, 'title') else 'N/A'}"
        )
        logger.info(f"  - Column: {column.name}")
        logger.info(f"  - Query/Prompt: {prompt}")
        logger.info(f"  - Output type: {output_type}")
        logger.info(f"  - Is list: {column.extract_is_list}")
        logger.info(f"  - Corpus ID: {corpus_id}")

        # Capture LLM messages for debugging
        llm_log = None

        try:
            # Wrap the agent call in the context manager to capture messages
            with capture_run_messages() as messages:
                # Create a temporary agent and extract.  The ``_and_sources``
                # variant also returns the real Annotation PKs that the
                # agent's retrieval tools (similarity_search, ...) returned
                # during this run, so we can link them to ``datacell.sources``
                # without relying on the post-hoc fuzzy-match grounder.
                (
                    result,
                    retrieved_annotation_ids,
                ) = await agents.get_structured_response_and_sources_from_document(
                    document=document.id,
                    corpus=corpus_id,
                    prompt=prompt,
                    target_type=output_type,
                    framework=AgentFramework.PYDANTIC_AI,
                    temperature=0.3,  # Low temperature for consistent extraction
                    similarity_top_k=similarity_top_k,
                    model=model_override or DEFAULT_EXTRACT_MODEL,
                    user_id=datacell.creator.id,
                )

            # Capture the message history regardless of success/failure
            llm_log = ModelMessagesTypeAdapter.dump_json(messages, indent=2).decode()
            logger.info(f"LLM message history captured for cell {cell_id}")
            logger.debug(f"Full LLM conversation:\n{llm_log}")

        except Exception as e:
            # If we have messages, capture them before re-raising
            if "messages" in locals():
                llm_log = ModelMessagesTypeAdapter.dump_json(
                    messages, indent=2
                ).decode()
                logger.error(
                    f"Failed extraction with error {e} - LLM messages:\n{llm_log}"
                )
            raise

        # 7. Process and save results
        logger.info(f"Raw extraction result type: {type(result)}")
        logger.info(f"Raw extraction result: {result}")

        if result is not None:
            # Convert result to saveable format
            if isinstance(result, BaseModel):
                data = {"data": result.model_dump()}
                logger.info(f"Converted BaseModel to dict: {data}")
            elif (
                isinstance(result, list) and result and isinstance(result[0], BaseModel)
            ):
                data = {"data": [item.model_dump() for item in result]}
                logger.info(f"Converted list of BaseModels to dict: {data}")
            else:
                data = {"data": result}
                logger.info(f"Using raw result as data: {data}")

            await sync_mark_completed(datacell, data, llm_log)
            logger.info(f"✓ Successfully extracted and saved data for cell {cell_id}")
            logger.info(f"  Final saved data: {data}")
            logger.info(f"  LLM log saved: {len(llm_log) if llm_log else 0} characters")

            # Link the annotations the agent actually retrieved to
            # ``datacell.sources``.  This is the TRUE citation signal — what
            # the retrieval tools surfaced to the model — and it sidesteps
            # the fragile fuzzy-match grounder below for answers where the
            # retrieval already pinpointed the right spans.  The grounder
            # still runs as a complementary pass for extracted substrings
            # that weren't part of a retrieved annotation.
            if retrieved_annotation_ids:
                try:
                    await _link_retrieval_citations(
                        datacell, retrieved_annotation_ids
                    )
                    logger.info(
                        "Linked %d retrieval citations to datacell %s",
                        len(retrieved_annotation_ids),
                        cell_id,
                    )
                except Exception as link_err:
                    logger.warning(
                        "Failed to link retrieval citations for datacell %s: %s",
                        cell_id,
                        link_err,
                        exc_info=True,
                    )

            # Auto-ground: find extracted text values in the source document
            # and create linked source annotations with PDF/text coordinates.
            try:
                grounding_annotations = await ground_extraction_to_annotations(
                    datacell=datacell,
                    document=document,
                    corpus=corpus_id,
                    user_id=datacell.creator.id,
                )
                if grounding_annotations:
                    logger.info(
                        f"Auto-grounded {len(grounding_annotations)} source "
                        f"annotations for datacell {cell_id}"
                    )
            except Exception as grounding_err:
                # Grounding is best-effort — never fail the extraction
                logger.warning(
                    f"Auto-grounding failed for datacell {cell_id}: "
                    f"{grounding_err}",
                    exc_info=True,
                )

        else:
            # Extraction returned None
            logger.warning(f"✗ Extraction returned None for cell {cell_id}")
            logger.warning(
                "  This likely means the requested information is not present in the document"
            )
            await sync_mark_failed(
                datacell,
                "Failed to extract requested data from document",
                "The extraction returned None - the requested information may not be present in the document.",
                llm_log,
            )

    except Exception as e:
        logger.exception(f"Error during extraction for cell {cell_id}: {e}")
        tb = traceback.format_exc()
        # Only try to mark failed if we have a datacell
        if datacell:
            # Pass llm_log if we have it
            await sync_mark_failed(
                datacell, e, tb, llm_log if "llm_log" in locals() else None
            )
        else:
            logger.error(f"Failed to get datacell for cell_id {cell_id}: {e}\n{tb}")
        raise


def text_search(document_id: int, query_str: str) -> str:
    """
    Performs case-insensitive substring search in structural annotations.
    Returns the first 3 results that match.

    Args:
        document_id (int): The ID of the document to query structural Annotations from.
        query_str (str): The search text to look for in structural Annotations.

    Returns:
        str: A string describing up to 3 matched annotation segments.
    """
    from opencontractserver.annotations.models import Annotation

    matches = Annotation.objects.filter(
        document_id=document_id,
        structural=True,
        raw_text__icontains=query_str,
    ).order_by("id")[0:3]

    if not matches.exists():
        return "No structural annotations matched your text_search."

    results = []
    for ann in matches:
        snippet = f"Annotation ID: {ann.id}, Page: {ann.page}, Text: {ann.raw_text}"
        results.append(snippet)

    return "\n".join(results)


def annotation_window(document_id: int, annotation_id: str, window_size: str) -> str:
    """
    Retrieves contextual text around the specified Annotation. Returns up to
    'window_size' words (on each side) of the Annotation text, with a global
    maximum of 1000 words in total.

    Args:
        document_id (int): The ID of the document containing the annotation.
        annotation_id (str): The ID of the Annotation to retrieve context for.
        window_size (str): The number of words to expand on each side (passed as string).

    Returns:
        str: The textual window around the Annotation or an error message.
    """
    from opencontractserver.annotations.models import Annotation
    from opencontractserver.types.dicts import PawlsPagePythonType, TextSpanData

    # Step 1: Parse the window_size argument
    try:
        window_words = int(window_size)
        # Enforce a reasonable upper bound
        window_words = min(window_words, 500)  # 500 on each side => 1000 total
    except ValueError:
        return "Error: Could not parse window_size as an integer."

    # Step 2: Fetch the annotation and its document
    try:
        annotation = Annotation.objects.get(
            id=int(annotation_id), document_id=document_id
        )
    except (Annotation.DoesNotExist, ValueError):
        return f"Error: Annotation [{annotation_id}] not found."

    doc = annotation.document

    # Step 3: Distinguish text/* vs application/pdf
    file_type = doc.file_type
    if not file_type:
        return "Error: Document file_type not specified."

    # Utility for splitting text into words safely
    def split_words_preserve_idx(text_str: str) -> list[tuple[str, int]]:
        """
        Splits text_str into words. Returns a list of (word, starting_char_index)
        pairs so we can rebuild substrings by word count if needed.
        """
        words_and_idxs: list[tuple[str, int]] = []
        idx = 0
        for word in text_str.split():
            # find the occurrence of this word in text_str starting at idx
            pos = text_str.find(word, idx)
            if pos == -1:
                # fallback if something is off
                pos = idx
            words_and_idxs.append((word, pos))
            idx = pos + len(word)
        return words_and_idxs

    try:
        if file_type.startswith("text/"):
            # -------------------------
            # Handle text/* annotation
            # -------------------------
            if not doc.txt_extract_file or not os.path.exists(
                doc.txt_extract_file.path
            ):
                return "Error: Document has no txt_extract_file or path is invalid."

            # Read the entire doc text
            with open(doc.txt_extract_file.path, encoding="utf-8") as f:
                doc_text = f.read()

            # The Annotation.json is presumably a TextSpanData
            anno_json = annotation.json
            if not isinstance(anno_json, dict):
                return "Error: Annotation.json is not a dictionary for text/*."

            # Attempt to parse it as a TextSpanData
            try:
                span_data: TextSpanData = TextSpanData(**anno_json)
            except Exception:
                return "Error: Annotation.json could not be parsed as TextSpanData for text/* document."

            start_idx = span_data["start"]
            end_idx = span_data["end"]

            # Safeguard: clamp indices
            start_idx = max(start_idx, 0)
            end_idx = min(end_idx, len(doc_text))

            # If user wants a word-based window, we can find the nearest word boundaries
            words_with_idx = split_words_preserve_idx(doc_text)

            # Locate word that encloses start_idx, end_idx
            start_word_index = 0
            end_word_index = len(words_with_idx) - 1

            for i, (_, wstart) in enumerate(words_with_idx):
                if wstart <= start_idx:
                    start_word_index = i
                if wstart <= end_idx:
                    end_word_index = i

            # Expand by 'window_words' on each side, but total no more than 1000 words
            total_window = min(
                window_words * 2 + (end_word_index - start_word_index + 1), 1000
            )
            left_expand = min(window_words, start_word_index)
            right_expand = min(window_words, len(words_with_idx) - end_word_index - 1)

            # Recompute if the combined is too large (simple approach)
            def clamp_to_total_window(
                left: int, right: int, center_count: int, total_max: int
            ):
                current_count = left + right + center_count
                if current_count <= total_max:
                    return left, right
                overshoot = current_count - total_max
                left_reduced = min(left, overshoot)
                new_left = left - left_reduced
                overshoot -= left_reduced
                if overshoot > 0:
                    right_reduced = min(right, overshoot)
                    new_right = right - right_reduced
                else:
                    new_right = right
                return new_left, new_right

            center_chunk = end_word_index - start_word_index + 1
            left_expand, right_expand = clamp_to_total_window(
                left_expand, right_expand, center_chunk, 1000
            )

            final_start_word = start_word_index - left_expand
            final_end_word = end_word_index + right_expand

            final_text_start_char = words_with_idx[final_start_word][1]
            final_text_end_char = (
                len(doc_text)
                if final_end_word >= len(words_with_idx) - 1
                else words_with_idx[final_end_word + 1][1]
            )

            return doc_text[final_text_start_char:final_text_end_char].strip()

        elif file_type == "application/pdf":
            # -------------------------
            # Handle PDF annotation
            # -------------------------
            if not doc.pawls_parse_file or not os.path.exists(
                doc.pawls_parse_file.path
            ):
                return "Error: Document has no pawls_parse_file or path is invalid."

            with open(doc.pawls_parse_file.path, encoding="utf-8") as f:
                pawls_pages = expand_pawls_pages(json.load(f))

            if not isinstance(pawls_pages, list):
                return "Error: pawls_parse_file is not a list of PawlsPagePythonType."

            if not isinstance(annotation.json, dict):
                return "Error: Annotation.json is not a dictionary for PDF."

            from opencontractserver.annotations.compact_json import (
                PageAnnotationData,
            )

            pages: list[PageAnnotationData] = list(
                iter_page_annotations(
                    annotation.json, raw_text=annotation.raw_text or ""
                )
            )
            if not pages:
                return (
                    "Error: Annotation.json could not be parsed as single or multi-page "
                    "PDF annotation data."
                )

            result_texts: list[str] = []

            pawls_by_index: dict[int, PawlsPagePythonType] = {}

            for page_obj in pawls_pages:
                try:
                    pg_ind = page_obj["page"]["index"]
                    pawls_by_index[pg_ind] = PawlsPagePythonType(**page_obj)
                except Exception:
                    continue

            def tokens_as_words(page_index: int) -> list[str]:
                page_data = pawls_by_index.get(page_index)
                if not page_data:
                    return []
                tokens_list = page_data["tokens"]
                return [t["text"] for t in tokens_list]

            for page in pages:
                all_tokens = tokens_as_words(page.page_index)
                if not all_tokens:
                    continue

                raw_text = page.raw_text.strip() if page.raw_text else ""
                # We'll find a contiguous chunk in the token list that matches raw_text, or fallback to partial

                # Join tokens with spaces for searching. Then we find raw_text in there.
                joined_tokens_str = " ".join(all_tokens)

                if raw_text and raw_text in joined_tokens_str:
                    start_idx = joined_tokens_str.index(raw_text)
                    # we can reconstruct the word boundaries
                    # but let's do a simpler approach:
                    # skip words up to that position
                    prefix_part = joined_tokens_str[:start_idx]
                    prefix_count = len(prefix_part.strip().split())
                    anno_word_count = len(raw_text.strip().split())
                    start_word_index = prefix_count
                    end_word_index = prefix_count + anno_word_count - 1

                else:
                    # fallback: we will collect tokens from tokensJsons
                    # each "tokensJsons" entry might have an "id" if each token is identified
                    # or we rely on raw_text if we can't match
                    # we'll do a naive approach: assume the annotation covers some subset in tokens
                    # The user might store token indices in tokensJson.
                    # This is out of scope for a short example. We'll just expand all tokens as fallback.
                    start_word_index = 0
                    end_word_index = len(all_tokens) - 1

                left_expand = window_words
                right_expand = window_words
                total_possible = len(all_tokens)

                final_start_word = max(0, start_word_index - left_expand)
                final_end_word = min(total_possible - 1, end_word_index + right_expand)

                # then clamp total to 1000
                # total words = final_end_word - final_start_word + 1
                total_window = final_end_word - final_start_word + 1
                if total_window > 1000:
                    # reduce from both sides if needed (some naive approach)
                    overshoot = total_window - 1000
                    # reduce from left side first
                    reduce_left = min(overshoot, left_expand)
                    final_start_word += reduce_left
                    overshoot -= reduce_left
                    if overshoot > 0:
                        reduce_right = min(overshoot, right_expand)
                        final_end_word -= reduce_right

                snippet = " ".join(all_tokens[final_start_word : final_end_word + 1])
                if snippet.strip():
                    result_texts.append(f"Page {page.page_index} context:\n{snippet}")

            # Combine page-level context
            if not result_texts:
                return (
                    "No tokens found or no matching text for the specified annotation."
                )

            return "\n\n".join(result_texts)

        else:
            return f"Error: Unsupported document file_type: {file_type}"

    except Exception as e:
        return f"Error: Exception encountered while retrieving annotation window: {e}"


def sync_save_datacell(datacell: Datacell) -> None:
    logger.info(f"Entering sync_save_datacell for Datacell id={datacell.id}")
    try:
        datacell.save()
        logger.info(f"Datacell saved successfully: {datacell.id}")
    except Exception as e:
        logger.exception(
            f"Exception in sync_save_datacell for Datacell id={datacell.id}: {e}"
        )
        raise
