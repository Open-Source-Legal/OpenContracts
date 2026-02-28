import logging
from typing import Any

from opencontractserver.shared.decorators import doc_analyzer_task
from opencontractserver.types.dicts import TextSpan

logger = logging.getLogger(__name__)


# @doc_analyzer_task(
#     input_schema={
#         "$schema": "http://json-schema.org/draft-07/schema#",
#         "title": "InputSchema",
#         "type": "object",
#         "properties": {
#             "context": {
#                 "type": "string",
#                 "title": "Context",
#                 "description": "A description or context for the input.",
#             },
#             "labels": {
#                 "type": "array",
#                 "title": "Labels",
#                 "description": "An optional list of labels.",
#                 "items": {"type": "string"},
#                 "uniqueItems": True,
#             },
#         },
#         "required": ["context"],
#         "additionalProperties": False,
#     }
# )
# def legal_entity_tagger(*args, pdf_text_extract, **kawrgs):
#     """
#     # Legal Entity Tagger

#     Uses SALI tags, GLiNER, and spaCy sentence splitter to identify and tag legal entities in text.

#     ## Features
#     - Leverages pre-trained GLiNER model for entity recognition
#     - Supports custom label sets via input schema
#     - Default support for 39+ legal entity types including:
#       - Corporations (B, C, S Corps)
#       - Partnerships
#       - LLCs
#       - Government entities
#       - Committees
#       - And more

#     ## Process
#     1. Splits text into sentences using spaCy
#     2. Applies GLiNER model with confidence threshold of 0.7
#     3. Maps entities to text spans with precise character offsets

#     ## Parameters
#     - labels: Optional list of custom entity types to detect. If not provided, uses default legal entity types.

#     ## Returns
#     Tagged entities with:
#     - Entity text
#     - Entity type
#     - Character offsets
#     - Confidence score
#     """
#     import logging

#     import spacy
#     from gliner import GLiNER

#     logger = logging.getLogger(__name__)
#     logger.info("Starting legal entity tagger task")

#     logger.info(f"Task parameters: {kawrgs}")

#     logger.info("Loading spaCy model")
#     nlp = spacy.load("en_core_web_lg")
#     logger.info("Successfully loaded spaCy model")

#     logger.info("Loading GLiNER model")
#     model = GLiNER.from_pretrained("urchade/gliner_base")
#     model.set_sampling_params(
#         max_types=25,  # maximum number of entity types during training
#         shuffle_types=True,  # if shuffle or not entity types
#         random_drop=True,  # randomly drop entity types
#         max_neg_type_ratio=1,  # ratio of positive/negative types, 1 mean 50%/50%, 2 mean 33%/66%, 3 mean 25%/75% ...
#         max_len=2500,  # maximum sentence length
#     )
#     logger.info("Successfully loaded and configured GLiNER model")

#     # Use provided labels if available, otherwise fall back to defaults
#     default_labels = [
#         "Legal Entity",
#         "Entity",
#         "Business Trust",
#         "Cooperative",
#         "Corporation",
#         "B Corporation",
#         "C Corporation",
#         "S Corporation",
#         "Exempted Company",
#         "Governmental Entity",
#         "Limited Duration Company",
#         "Limited Liability Company",
#         "Municipal Corporation",
#         "Non-Governmental Organization",
#         "Non-Profit Organization",
#         "Partnership",
#         "Exempted Limited Partnership",
#         "General Partnership",
#         "Limited Liability Partnership",
#         "Limited Partnership",
#         "Political Party",
#         "Professional Limited Liability Company",
#         "Segregated Portfolio Company",
#         "Société Anonyme",
#         "Société en Commandite Simple",
#         "Société à Responsabilité Limitée",
#         "Sole Proprietorship",
#         "Sovereign State",
#         "Trade Union / Labor Union",
#         "Entity Groups",
#         "Board of Directors",
#         "Class",
#         "Committees",
#         "Ad Hoc/Unofficial Committee",
#         "Creditors' Committee",
#         "Independent Committee",
#         "Official Committee of Creditors",
#         "Official Committee of Unsecured Creditors",
#         "Joint Defense Group",
#         "Joint Defense Group Member",
#     ]

#     labels_to_use = kawrgs.get("labels", default_labels)
#     logger.info(f"Using label set with {len(labels_to_use)} labels")

#     logger.info("Splitting text into sentences")
#     sentences = [i for i in nlp(pdf_text_extract).sents]
#     logger.info(f"Split text into {len(sentences)} sentences")

#     results = []

#     for index, sent in enumerate(sentences):
#         logger.debug(f"Processing sentence {index + 1}/{len(sentences)}")
#         ents = model.predict_entities(sent.text, labels_to_use)
#         logger.debug(f"Found {len(ents)} potential entities in sentence {index + 1}")

#         for e in ents:
#             # Rough heuristic - drop anything with score of less than .7. Anecdotally, anything much lower is garbage.
#             if e["score"] > 0.7:
#                 logger.debug(
#                     f"Found high-confidence entity: {e['text']} ({e['label']}) - score: {e['score']}"
#                 )
#                 span = TextSpan(
#                     id=str(index),
#                     start=sent.start_char + e["start"],
#                     end=sent.start_char + e["end"],
#                     text=e["text"],
#                 )
#                 results.append(
#                     (
#                         span,
#                         str(e["label"]),
#                     )
#                 )
#             else:
#                 logger.debug(
#                     f"Skipping low-confidence entity: {e['text']} ({e['label']}) - score: {e['score']}"
#                 )

#     logger.info(f"Found {len(results)} total entities above confidence threshold")
#     logger.info("Completed legal entity tagger task")

#     return [], results, [], True


# @doc_analyzer_task()
# def proper_name_tagger(*args, pdf_text_extract, **kawrgs):
#     """
#     # Proper Name Entity Tagger

#     Uses spaCy to identify and tag named entities in text.

#     ## Entity Types
#     - Organizations (ORG)
#     - Geopolitical Entities (GPE)
#     - People (PERSON)
#     - Products (PRODUCT)

#     ## Process
#     1. Applies spaCy's small English model
#     2. Extracts entities of specified types
#     3. Maps to text spans with character offsets
#     4. Returns top 10 most relevant entities

#     ## Notes
#     Currently limited to 10 entities to manage
#     annotation density. Future improvements planned for page-aware annotations.
#     """

#     import spacy

#     nlp = spacy.load("en_core_web_sm")
#     doc = nlp(pdf_text_extract)

#     results = []

#     for index, ent in enumerate(
#         [ent for ent in doc.ents if ent.label_ in ["ORG", "GPE", "PERSON", "PRODUCT"]]
#     ):
#         results.append(
#             (
#                 TextSpan(
#                     id=str(index),
#                     start=ent.start_char,
#                     end=ent.end_char,
#                     text="First ten",
#                 ),
#                 str(ent.label_),
#             )
#         )
#         # print(ent.text, ent.start_char, ent.end_char, ent.label_)

#     # This generates a TON of labels... so artificially limiting to 10 for now... Ideal fix here is using page aware
#     # annotations, which I know I was using before for virtual loading. Think it ran into some issues with the jump
#     # to annotation functionality, but that should be largely solved with new functionality to render specified annots
#     # on annotator load.
#     return [], results[:10], [], True


@doc_analyzer_task(
    input_schema={
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": "AgenticHighlighterSchema",
        "type": "object",
        "properties": {
            "instructions": {
                "type": "string",
                "title": "Instructions",
                "description": "User's instructions describing what to highlight in the document.",
            },
        },
        "required": ["instructions"],
        "additionalProperties": False,
    }
)
def agentic_highlighter_claude(
    *args: Any,
    pdf_text_extract: str | None = None,
    pdf_pawls_extract: dict | None = None,
    **kwargs: Any,
) -> tuple[list[str], list[tuple[TextSpan, str]], list[dict], bool]:
    """
    # Agentic Document Highlighter (Claude)

    Uses Anthropic's Claude API to intelligently highlight document sections based on user instructions.

    ## Features
    - Processes large documents in chunks
    - Uses Claude's citation API for precise text location
    - Handles documents with or without explicit citations
    - Maintains character-level accuracy for highlights

    ## Parameters
    - pdf_text_extract: Full document text
    - pdf_pawls_extract: Optional PDF structure data
    - kwargs:
      - instructions: User highlighting instructions
      - doc_id: Document identifier

    ## Process
    1. Chunks document if needed
    2. Sends each chunk to Claude
    3. Processes citations or falls back to text matching
    4. Maps matches to precise character spans

    ## Returns
    Tuple containing:
    - List[str]: Empty list (reserved)
    - List[Tuple[TextSpan, str]]: Matched spans with labels
    - List[dict]: Error/debug information
    - bool: Success status
    """

    import logging
    import os

    import anthropic
    from django.conf import settings

    logger = logging.getLogger(__name__)

    logger.info("Starting agentic_highlighter_claude task")
    instructions = kwargs.get("instructions", "No instructions provided.")
    doc_id = kwargs.get("doc_id")
    logger.info(f"Task parameters - doc_id: {doc_id}, instructions: {instructions}")

    if not pdf_text_extract or not doc_id:
        logger.info("Missing required input - returning early")
        return [], [], [{"data": {"error": "Missing required input"}}], False

    # Setup Anthropic client
    # The API key is typically provided in settings or environment variable
    kwargs = getattr(settings, "ANALYZER_KWARGS", {})
    analyzer_kwargs = kwargs.get(
        "opencontractserver.tasks.doc_analysis_tasks.agentic_highlighter_claude", {}
    )
    ANTHROPIC_API_KEY = analyzer_kwargs.get(
        "ANTHROPIC_API_KEY", None
    ) or os.environ.get("ANTHROPIC_API_KEY", None)
    if not ANTHROPIC_API_KEY:
        logger.info("Anthropic API key not found in settings or environment")
        return [], [], [{"data": {"error": "Anthropic API key not found"}}], False

    logger.info("Successfully configured Anthropic API key")
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # Maximum chunk size in characters. You may adjust this if you know your model's context window
    # (approx 100k tokens for claude-3-5, but we use a smaller slice to be safe).
    MAX_CHARS_PER_CHUNK = 80000

    def chunk_text(text: str, chunk_size: int = MAX_CHARS_PER_CHUNK) -> list[str]:
        """
        # Text Chunker

        Splits text into sized chunks for processing.

        ## Parameters
        - text: Full text to chunk
        - chunk_size: Maximum characters per chunk

        ## Returns
        List of text chunks
        """
        if len(text) <= chunk_size:
            return [text]

        chunks = []
        current_index = 0
        while current_index < len(text):
            end_index = min(current_index + chunk_size, len(text))
            chunks.append(text[current_index:end_index])
            current_index = end_index

        return chunks

    # Create text chunks for big documents
    doc_chunks = chunk_text(pdf_text_extract, MAX_CHARS_PER_CHUNK)
    logger.info(f"Split document into {len(doc_chunks)} chunks")

    # We'll store all matched spans across all chunks here
    all_spans: list[tuple[TextSpan, str]] = []
    error_responses: list[dict] = []

    # Build the system prompt
    system_directive = (
        "You are a contract interpretation expert. "
        f'You have received the following user instructions:\n\n"{instructions}"\n\n'
        "Your goal: Identify relevant text from the contract. Review the full document text if possible, "
        "or use the largest available chunks of text to find relevant excerpts.\n\n"
        "Use citations so we can locate the relevant text within each chunk. "
        "If you cannot find any relevant excerpts, respond with empty text. "
        "No extra commentary. Return only the relevant text, or nothing."
    )
    logger.info("Created system directive for Claude")

    # We'll process each chunk in turn
    offset_so_far = 0
    for chunk_index, chunk_text_str in enumerate(doc_chunks):
        logger.info(f"Processing chunk {chunk_index + 1} of {len(doc_chunks)}")
        try:
            # Prepare single 'document' object with citations = True
            document_for_claude = {
                "type": "document",
                "source": {
                    "type": "text",
                    "media_type": "text/plain",
                    "data": chunk_text_str,
                },
                "title": f"Chunk-{chunk_index}",
                "citations": {"enabled": True},
            }

            # Create the request
            request_payload = [
                # The chunked doc
                document_for_claude,
                # The instructions / user message
                {
                    "type": "text",
                    "text": "Please extract the relevant text as specified.",
                },
            ]

            logger.info(f"Sending request to Claude for chunk {chunk_index + 1}")
            response = client.messages.create(
                model="claude-3-5-sonnet-latest",
                temperature=0.0,
                max_tokens=1024,
                system=system_directive,
                messages=[
                    {"role": "user", "content": request_payload},
                ],
            )

            # Parse the response from Claude
            if not response or not response.content:
                logger.info(f"No content in response for chunk {chunk_index + 1}")
                continue

            # For each block of the response:
            for content_msg in response.content:
                if content_msg.type == "text":
                    snippet_text = content_msg.text.strip()

                    # If there's no text or it's empty, skip
                    if not snippet_text:
                        logger.info(f"Empty text content in chunk {chunk_index + 1}")
                        continue

                    logger.info(f"Processing text content in chunk {chunk_index + 1}")
                    # If there's citation data, we'll parse them; if not, do naive substring
                    # match. Claude may produce partial citations, so we handle them:
                    # We'll match the entire snippet_text in the chunk.
                    # Then for each match, build a TextSpan.

                    # Potentially multiple citations in the block
                    # We'll also handle the case of no citations.
                    found_citations = getattr(content_msg, "citations", [])

                    # If no citations were provided, simply attempt to find the entire snippet in the chunk
                    if not found_citations:
                        logger.info(
                            f"No citations found in chunk {chunk_index + 1}, using full text matching"
                        )
                        start_search = 0
                        while True:
                            idx = chunk_text_str.find(snippet_text, start_search)
                            if idx == -1:
                                break
                            # Build the span
                            span = TextSpan(
                                id=f"chunk_{chunk_index}_match_{len(all_spans)}",
                                start=offset_so_far + idx,
                                end=offset_so_far + idx + len(snippet_text),
                                text=snippet_text,
                            )
                            all_spans.append((span, "AGENTIC_HIGHLIGHT"))
                            logger.info(
                                f"Added span from full text match in chunk {chunk_index + 1}"
                            )
                            start_search = idx + len(snippet_text)
                    else:
                        logger.info(
                            f"Found {len(found_citations)} citations in chunk {chunk_index + 1}"
                        )
                        # If citations exist, each citation can be smaller or bigger block of text
                        # We'll find them in the chunk.
                        for citation_obj in found_citations:
                            cited_substring = citation_obj.cited_text.strip()

                            # Find all occurrences of the cited_substring within the chunk
                            start_search = 0
                            while True:
                                idx = chunk_text_str.find(cited_substring, start_search)
                                if idx == -1:
                                    break
                                span = TextSpan(
                                    id=f"chunk_{chunk_index}_match_{len(all_spans)}",
                                    start=offset_so_far + idx,
                                    end=offset_so_far + idx + len(cited_substring),
                                    text=cited_substring,
                                )
                                all_spans.append((span, "AGENTIC_HIGHLIGHT"))
                                logger.info(
                                    f"Added span from citation in chunk {chunk_index + 1}"
                                )
                                start_search = idx + len(cited_substring)

        except Exception as exc:
            logger.exception(f"Error in Claude chunk {chunk_index}: {exc}")
            error_responses.append({"data": {"error": str(exc), "chunk": chunk_index}})

        # Move offset for the next chunk
        offset_so_far += len(chunk_text_str)
        logger.info(f"Completed processing chunk {chunk_index + 1}")

    logger.info(f"Total spans found: {len(all_spans)}")
    logger.info(f"Error responses: {error_responses}")

    # If anything went wrong in any chunk, success is still True if we found at least some spans
    # but we'll record all errors in error_responses
    # Return them so the caller can see them if needed.
    success = True
    logger.info("Completed agentic_highlighter_claude task")

    return [], all_spans, error_responses, success


@doc_analyzer_task()
def pii_highlighter_claude(
    *args: Any,
    pdf_text_extract: str | None = None,
    pdf_pawls_extract: dict | None = None,
    **kwargs: Any,
) -> tuple[
    list[str],  # doc-level labels
    list[tuple[TextSpan, str]],  # span-level annotations
    list[dict[str, Any]],  # metadata
    bool,  # success/failure
]:
    """
    # PII Highlighter (Claude)

    Analyzes the text of a contract, sends it to Claude for potential PII redactions,
    and returns a 4-element tuple consistent with doc_analyzer_task requirements:

      1. List of doc-level labels (usually empty for PII detection)
      2. List of (TextSpan, str) tuples describing each snippet to redact
      3. A list of metadata dictionaries (for additional debug info or errors)
      4. A boolean indicating success/failure

    We'll actually build and submit the prompt to Claude if the API key is provided in
    settings or environment. Each returned snippet is assumed to appear line-by-line
    in Claude's response with no additional commentary.

    Args:
        *args (Any): Additional positional arguments (not used here).
        pdf_text_extract (str | None, optional): Full document text to analyze.
        pdf_pawls_extract (dict | None, optional): Data for PDF annotation or layout (not used here).
        **kwargs (Any): Additional keyword arguments.

    Returns:
        (list[str], list[tuple[TextSpan, str]], list[dict[str, Any]], bool):
            - A tuple of:
                1) Doc-level labels (empty in this case).
                2) List of (TextSpan, label) for each snippet to redact.
                3) A list of metadata/error dictionaries.
                4) Success or failure as a boolean.
    """

    import logging
    import os

    import anthropic
    from django.conf import settings

    from opencontractserver.types.dicts import TextSpan

    logger = logging.getLogger(__name__)

    if not pdf_text_extract:
        return ([], [], [{"data": {"error": "No PDF text supplied"}}], False)

    # Retrieve Anthropic config from settings or environment
    analyzer_config = getattr(settings, "ANALYZER_KWARGS", {})
    pii_config = analyzer_config.get(
        "opencontractserver.tasks.doc_analysis_tasks.pii_highlighter_claude", {}
    )
    ANTHROPIC_API_KEY = pii_config.get("ANTHROPIC_API_KEY") or os.environ.get(
        "ANTHROPIC_API_KEY"
    )

    if not ANTHROPIC_API_KEY:
        logger.error("Anthropic API key not found in settings or environment.")
        return ([], [], [{"data": {"error": "Anthropic API key not found"}}], False)

    # Construct the prompt for Claude
    prompt_text = (
        "You are an expert at interpreting contracts and, more importantly, inferring "
        "confidential data from the text of the document. We are going to give you a "
        "contract related to a document and want you to carefully review "
        "the document, thinking step-by-step whether any given section of text could reveal "
        "confidential details of the transaction or the names of the parties, or could do "
        "so in combination with other text. For all such text, return the offending text "
        "EXACTLY as it appears in the source text, with a few preceding works and a few trailing words,"
        " each snippet on its own line. Add nothing "
        "to the text — no formatting changes, punctuation, capitalization changes, commas, "
        "quotes, or additional commentary. Don't explain your work. Don't add commentary. "
        "No chatter. If you see no relevant material, simply return empty string.\n\n"
        f"Now, here's the document text:\n=====\n{pdf_text_extract}\n====="
    )

    # Create an Anthropic client
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    try:
        # Create the messages request
        response = client.messages.create(
            model="claude-3-5-sonnet-latest",
            max_tokens=8192,
            temperature=0,
            messages=[
                {
                    "role": "user",
                    "content": prompt_text,
                }
            ],
        )
        claude_response = response.content or []
        logger.info(f"Claude response ({type(claude_response)}): {claude_response}")

        claude_response = [resp.text for resp in claude_response]
        logger.info(f"Claude response ({type(claude_response)}): {claude_response}")

        claude_response = "\n".join(claude_response)
        logger.info(f"Claude response ({type(claude_response)}): {claude_response}")

    except Exception as e:
        logger.error(f"Error calling Anthropic API: {e}")
        return ([], [], [{"data": {"error": str(e)}}], False)

    # If we got no response text, treat it as an error
    if not claude_response.strip():
        logger.warning("Received empty response from Claude.")
        return ([], [], [{"data": {"error": "Empty response from Claude"}}], False)

    # Split response by line to get each snippet
    logger.debug(  # pragma: no cover -- requires live Claude API
        "Claude response (%s): %s", type(claude_response), claude_response
    )
    lines_to_redact = []
    for line in claude_response.splitlines():
        if line.strip().lower() != "none" and line.strip():
            lines_to_redact.append(line.strip())

    # Prepare a list for annotation pairs (TextSpan, label)
    span_label_pairs: list[tuple[TextSpan, str]] = []

    # Search each snippet in the original text, building (TextSpan, "REDACTED")
    for snippet_idx, snippet in enumerate(lines_to_redact):
        search_start = 0
        while True:
            match_idx = pdf_text_extract.find(snippet, search_start)
            if match_idx == -1:
                break

            snippet_end = match_idx + len(snippet)
            span_label_pairs.append(
                (
                    TextSpan(
                        id=f"redaction_{snippet_idx}",
                        start=match_idx,
                        end=snippet_end,
                        text=snippet,
                    ),
                    "REDACTED",
                )
            )
            search_start = snippet_end

    # Return the list of doc labels (empty), our list of snippet tuples,
    # an empty metadata list, and success = True
    return ([], span_label_pairs, [], True)
