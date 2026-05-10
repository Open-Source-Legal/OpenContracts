from typing import Literal, Optional, Union

from typing_extensions import NotRequired, TypedDict

from opencontractserver.types.enums import LabelType


class AnnotationLabelPythonType(TypedDict):
    id: str
    color: str
    description: str
    icon: str
    text: str
    label_type: LabelType


class LabelLookupPythonType(TypedDict):
    """
    We need to inject these objs into our pipeline so tha tasks can
    look up text or doc label pks by their *name* without needing to
    hit the database across some unknown number N tasks later in the
    pipeline. We preload the lookups as this lets us look them up only
    once with only a very small memory cost.
    """

    text_labels: dict[str, AnnotationLabelPythonType]
    doc_labels: dict[str, AnnotationLabelPythonType]


class PawlsPageBoundaryPythonType(TypedDict):
    """
    This is what a PAWLS Page Boundary obj looks like
    """

    width: float
    height: float
    index: int


class FunsdTokenType(TypedDict):
    # From Funsd paper: box = [xlef t, ytop, xright, ybottom]
    box: tuple[
        float, float, float, float
    ]  # This will be serialized to list when exported as JSON, but we want more
    # control over length than list typing allows
    text: str


class FunsdAnnotationType(TypedDict):
    box: tuple[float, float, float, float]
    text: str
    label: str
    words: list[FunsdTokenType]
    linking: list[int]
    id: str | int
    parent_id: Optional[str | int]


class FunsdAnnotationLoaderOutputType(TypedDict):
    id: str
    tokens: list[str]
    bboxes: list[tuple[float, float, float, float]]
    ner_tags: list[str]
    image: tuple[int, str, str]  # (doc_id, image_data, image_format)


class FunsdAnnotationLoaderMapType(TypedDict):
    page: list[FunsdAnnotationLoaderOutputType]


class PageFundsAnnotationsExportType(TypedDict):
    form: list[FunsdAnnotationType]


class PawlsTokenPythonType(TypedDict):
    """
    Unified token type for PAWLs data. Represents either a text token or an
    image token within a PDF page.

    Text tokens have:
    - x, y, width, height: Position and dimensions in PDF points
    - text: The text content

    Image tokens have:
    - x, y, width, height: Position and dimensions in PDF points
    - text: Empty string for images
    - is_image: True to indicate this is an image token
    - image_path: Storage path reference to the image file
    - format: Image format ("jpeg" or "png")
    - content_hash: SHA-256 hash for deduplication
    - original_width, original_height: Original pixel dimensions
    - image_type: "embedded" (extracted from PDF) or "cropped" (region crop)

    This unified approach allows images to be referenced using the same
    TokenIdPythonType as text tokens, simplifying annotation handling.
    """

    # Position and dimensions (in PDF points)
    x: float
    y: float
    width: float
    height: float
    text: str

    # Image-specific fields (only present when is_image=True)
    is_image: NotRequired[bool]  # True for image tokens
    image_path: NotRequired[str]  # Storage path to image file
    base64_data: NotRequired[
        str
    ]  # Base64-encoded image data (fallback if storage fails)
    format: NotRequired[str]  # Image format: "jpeg" or "png"
    content_hash: NotRequired[str]  # SHA-256 hash for deduplication
    original_width: NotRequired[int]  # Original image width in pixels
    original_height: NotRequired[int]  # Original image height in pixels
    image_type: NotRequired[str]  # "embedded" or "cropped"


class PawlsPagePythonType(TypedDict):
    """
    Pawls files are comprised of lists of jsons that correspond to the
    necessary tokens and page information for a given page. This describes
    the data shape for each of those page objs.

    The tokens array contains both text tokens and image tokens. Image tokens
    are identified by having is_image=True and can be referenced using the
    same TokenIdPythonType as text tokens.
    """

    page: PawlsPageBoundaryPythonType
    tokens: list[PawlsTokenPythonType]


class BoundingBoxPythonType(TypedDict):
    """
    Bounding box for pdf box on a pdf page
    """

    top: int | float
    bottom: int | float
    left: int | float
    right: int | float


class TokenIdPythonType(TypedDict):
    """
    Reference to a token (text or image) within the PAWLs data structure.
    Used in annotations to reference specific tokens on a page.

    Since images are now stored as tokens with is_image=True in the unified
    tokens[] array, both text and image tokens are referenced using this
    same type.
    """

    pageIndex: int
    tokenIndex: int


class OpenContractsSinglePageAnnotationType(TypedDict):
    """
    This is the data shape for our actual annotations on a given page of a pdf.
    In practice, annotations are always assumed to be multi-page, and this means
    our annotation jsons are stored as a dict map of page #s to the annotation data:

    Dict[int, OpenContractsSinglePageAnnotationType]

    The tokensJsons array can reference both text tokens and image tokens,
    as images are now stored in the unified tokens[] array with is_image=True.
    """

    bounds: BoundingBoxPythonType
    tokensJsons: list[TokenIdPythonType]
    rawText: str


class CompactPageAnnotationType(TypedDict):
    """
    Compact v2 per-page annotation data. Replaces
    :class:`OpenContractsSinglePageAnnotationType` in the v2 format.

    - ``b``: Bounds as ``[top, left, right, bottom]`` array.
    - ``t``: Token indices as range-encoded string (e.g. ``"35-37,40"``).
    """

    b: list[float | int]
    t: str


class CompactAnnotationJsonType(TypedDict):
    """
    Compact v2 multipage annotation JSON.

    Stored in ``Annotation.json`` when the compact format is used.
    Detected by ``"v": 2`` marker.
    """

    v: Literal[2]
    p: dict[str, CompactPageAnnotationType]


class TextSpanData(TypedDict):
    """
    Stores start and end indices of a span
    """

    start: int
    end: int
    text: str


class TextSpan(TextSpanData):
    """
    Stores start and end indices of a span
    """

    id: str


class OpenContractsAnnotationPythonType(TypedDict):
    """
    Data type for individual Open Contract annotation data type converted
    into JSON. Note the models have a number of additional fields that are not
    relevant for import/export purposes.

    The content_modalities field indicates what types of content are referenced
    by this annotation's tokens. Possible values: "TEXT", "IMAGE".
    """

    id: Optional[Union[str, int]]  # noqa  # fmt: off
    annotationLabel: str
    rawText: str
    page: int
    annotation_json: Union[
        dict[Union[int, str], OpenContractsSinglePageAnnotationType],
        CompactAnnotationJsonType,
        TextSpanData,
    ]
    parent_id: Optional[Union[str, int]]
    annotation_type: Optional[str]
    structural: bool
    content_modalities: NotRequired[
        list[str]
    ]  # ["TEXT"], ["IMAGE"], or ["TEXT", "IMAGE"]
    long_description: NotRequired[Optional[str]]


class SpanAnnotation(TypedDict):
    span: TextSpan
    annotation_label: str


class AnnotationGroup(TypedDict):
    labelled_spans: list[SpanAnnotation]
    doc_labels: list[str]


class AnnotatedDocumentData(AnnotationGroup):
    doc_id: int
    # labelled_spans and doc_labels incorporated via AnnotationGroup


class PageAwareTextSpan(TypedDict):
    """
    Given an arbitrary start and end index in a doc, want to be able to split it
    across pages, and we'll need page index information in additional to just
    start and end indices.
    """

    original_span_id: NotRequired[str | None]
    page: int
    start: int
    end: int
    text: str


class OpenContractCorpusTemplateType(TypedDict):
    title: str
    description: str
    icon_data: Optional[str]
    icon_name: Optional[str]
    creator: str


class OpenContractCorpusType(OpenContractCorpusTemplateType):
    id: int
    label_set: str


class OpenContractCorpusV2Type(OpenContractCorpusType):
    """
    Extended corpus type for V2 exports that includes additional configuration.
    Backward compatible with V1 by inheriting from OpenContractCorpusType.
    """

    slug: NotRequired[Optional[str]]
    post_processors: NotRequired[list[str]]
    preferred_embedder: NotRequired[Optional[str]]
    corpus_agent_instructions: NotRequired[Optional[str]]
    document_agent_instructions: NotRequired[Optional[str]]
    allow_comments: NotRequired[bool]


class OpenContractsLabelSetType(TypedDict):
    id: int | str
    title: str
    description: str
    icon_data: Optional[str]
    icon_name: str
    creator: str


class AnalyzerMetaDataType(TypedDict):
    id: str
    description: str
    title: str
    dependencies: list[str]
    author_name: str
    author_email: str
    more_details_url: str
    icon_base_64_data: str
    icon_name: str


class AnalyzerManifest(TypedDict):
    metadata: AnalyzerMetaDataType
    doc_labels: list[AnnotationLabelPythonType]
    text_labels: list[AnnotationLabelPythonType]
    label_set: OpenContractsLabelSetType


class OpenContractsRelationshipPythonType(TypedDict):
    """
    Data type for individual Open Contract relationship data type converted
    into JSON for import/export.

    Note that typically any 'old' ID is not the actual DB ID, so you'll need a map
    from these old ids to the new database IDs for any related objects (i.e. Annotations).
    """

    id: Optional[Union[str, int]]
    relationshipLabel: str
    source_annotation_ids: list[Union[str, int]]
    target_annotation_ids: list[Union[str, int]]
    structural: bool


class OpenContractsDocAnnotations(TypedDict):
    # Can have multiple doc labels. Want array of doc label ids, which will be
    # mapped to proper objects after import.
    doc_labels: list[str]

    # The annotations are stored in a list of JSONS matching OpenContractsAnnotationPythonType
    labelled_text: list[OpenContractsAnnotationPythonType]

    # Relationships are stored in a list of JSONS matching OpenContractsRelationshipPythonType.
    # These in the OpenContractsDocAnnotations should only be for the annotations that are
    # contained WITHIN document. Plan to add a separate attr at corpus level for cross-doc
    # relationships.
    relationships: NotRequired[list[OpenContractsRelationshipPythonType]]


class OpenContractDocExport(OpenContractsDocAnnotations):
    """
    Eech individual documents annotations are exported and imported into
    and out of jsons with this form. Inherits doc_labels and labelled_text
    from OpenContractsDocAnnotations
    """

    # Document title
    title: str

    # Document text
    content: str

    # Document description
    description: Optional[str]

    # Documents PAWLS parse file contents (serialized)
    pawls_file_content: list[PawlsPagePythonType]

    # We need to have a page count for certain analyses
    page_count: int

    # V2: MIME type of original file (e.g., "application/pdf", "text/plain")
    file_type: NotRequired[Optional[str]]

    # V2: Reference to structural annotation set (if any)
    structural_set_hash: NotRequired[Optional[str]]


class OpenContractsExportDataJsonPythonType(TypedDict):
    """
    This is the type of the data.json that goes into our export zips and
    carries the annotations and annotation information
    """

    # Lookup of pdf filename to the corresponding Annotation data
    annotated_docs: dict[str, OpenContractDocExport]

    # Requisite labels, mapped from label name to label data
    doc_labels: dict[str, AnnotationLabelPythonType]

    # Requisite text labels, mapped from label name to label data
    text_labels: dict[str, AnnotationLabelPythonType]

    # Stores the corpus (todo - make sure the icon gets stored as base64)
    corpus: OpenContractCorpusType

    # Stores the label set (todo - make sure the icon gets stored as base64)
    label_set: OpenContractsLabelSetType


class OpenContractsAnnotatedDocumentImportType(TypedDict):
    """
    This is the type of the data.json that goes into our import for a single
    document with its annotations and labels.
    """

    # Document title
    doc_data: OpenContractDocExport

    # Document pdf as base64 string
    pdf_base64: str

    # Document name
    pdf_name: str

    # Lookup of pdf filename to the corresponding Annotation data
    doc_labels: dict[str, AnnotationLabelPythonType]

    # Requisite text labels, mapped from label name to label data
    text_labels: dict[str, AnnotationLabelPythonType]


class OpenContractsAnalysisTaskResult(TypedDict):
    doc_id: int
    annotations: OpenContractsDocAnnotations


class OpenContractsGeneratedCorpusPythonType(TypedDict):
    """
    Meant to be the output of a backend job annotating docs. This can be imported
    using a slightly tweaked packaging script similar to what was done for the
    export importing pipeline, but it's actually simpler and faster as we're
    not recreating the documents.
    """

    annotated_docs: dict[Union[str, int], OpenContractsDocAnnotations]

    # Requisite labels, mapped from label name to label data
    doc_labels: dict[Union[str, int], AnnotationLabelPythonType]

    # Requisite text labels, mapped from label name to label data
    text_labels: dict[Union[str, int], AnnotationLabelPythonType]

    # Stores the label set (todo - make sure the icon gets stored as base64)
    label_set: OpenContractsLabelSetType


# ============================================================================
# Export Format V2.0 - Added for comprehensive corpus export/import
# ============================================================================


class StructuralAnnotationSetExport(TypedDict):
    """
    Export format for StructuralAnnotationSet - shared structural annotations
    across document copies.
    """

    content_hash: str
    parser_name: Optional[str]
    parser_version: Optional[str]
    page_count: Optional[int]
    token_count: Optional[int]
    pawls_file_content: list[PawlsPagePythonType]
    txt_content: str
    structural_annotations: list[OpenContractsAnnotationPythonType]
    structural_relationships: list[OpenContractsRelationshipPythonType]


class CorpusFolderExport(TypedDict):
    """
    Export format for CorpusFolder - hierarchical folder structure.
    Stores full path for easier reconstruction.
    """

    id: str  # Temporary export ID
    name: str
    description: str
    color: str
    icon: str
    tags: list[str]
    is_public: bool
    parent_id: Optional[str]  # Reference to parent folder export ID
    path: str  # Full path from root for easier reconstruction


class DocumentPathExport(TypedDict):
    """
    Export format for DocumentPath - version tree for document paths.
    Preserves full version history within corpus.
    """

    document_ref: str  # Reference to document in export (filename or hash)
    folder_path: Optional[str]  # Full folder path if assigned to folder
    path: str
    version_number: int
    parent_version_number: Optional[int]  # Reference to parent version
    is_current: bool
    is_deleted: bool
    created: str  # ISO format timestamp

    # Ingestion lineage (optional - not present in older exports)
    ingestion_source_name: NotRequired[Optional[str]]  # IngestionSource.name reference
    external_id: NotRequired[str]
    ingestion_metadata: NotRequired[Optional[dict]]


class IngestionSourceExport(TypedDict):
    """
    Export format for IngestionSource - a named integration that produces documents.

    Note: config is always exported as an empty dict ``{}`` because it may
    contain credentials. Importers should reconfigure sources after import.
    """

    name: str
    source_type: str
    config: dict
    active: bool


class AgentConfigExport(TypedDict):
    """
    Export format for corpus and document agent configurations.
    """

    corpus_agent_instructions: Optional[str]
    document_agent_instructions: Optional[str]


class DescriptionRevisionExport(TypedDict):
    """
    Export format for CorpusDescriptionRevision.
    """

    version: int
    diff: str
    snapshot: Optional[str]
    checksum_base: str
    checksum_full: str
    created: str  # ISO format timestamp
    author_email: str


class ConversationExport(TypedDict):
    """
    Export format for Conversation (discussion threads).
    Optional - only included if include_conversations=True.
    """

    id: str  # Temporary export ID
    title: str
    conversation_type: str  # 'chat' or 'thread'
    agent_type: Optional[str]
    is_public: bool
    creator_email: str
    created: str
    modified: str


class ChatMessageExport(TypedDict):
    """
    Export format for ChatMessage.
    Optional - only included if include_conversations=True.
    """

    id: str  # Temporary export ID
    conversation_id: str  # Reference to ConversationExport id
    content: str
    message_type: str
    state: str
    role: str
    tool_name: Optional[str]
    approved_by_email: Optional[str]
    creator_email: str
    created: str


class MessageVoteExport(TypedDict):
    """
    Export format for MessageVote.
    Optional - only included if include_conversations=True.
    """

    message_id: str  # Reference to ChatMessageExport id
    vote_type: str
    creator_email: str
    created: str


# ============================================================================
# Action Trail Export Types
# ============================================================================


class CorpusActionExecutionExport(TypedDict):
    """Export format for a single action execution."""

    id: str
    action_name: str
    action_type: str  # fieldset, analyzer, agent
    document_id: str
    status: str
    trigger: str
    queued_at: Optional[str]  # ISO format
    started_at: Optional[str]
    completed_at: Optional[str]
    duration_seconds: Optional[float]
    affected_objects: list[dict]
    error_message: str
    execution_metadata: dict


class CorpusActionExport(TypedDict):
    """Export format for a corpus action configuration."""

    id: str
    name: str
    action_type: str
    trigger: str
    disabled: bool
    # Type-specific config
    fieldset_id: Optional[str]
    analyzer_id: Optional[str]
    agent_config_id: Optional[str]
    task_instructions: str
    pre_authorized_tools: list[str]


class ActionTrailStatsExport(TypedDict):
    """Statistics for action trail export."""

    total_executions: int
    completed: int
    failed: int
    exported_count: int


class ActionTrailExport(TypedDict):
    """Complete action trail for export."""

    actions: list[CorpusActionExport]
    executions: list[CorpusActionExecutionExport]
    stats: ActionTrailStatsExport


class OpenContractsExportDataJsonV2Type(TypedDict):
    """
    Export format V2.0 - Comprehensive corpus export including all new features
    added since original export design.

    Backward compatible: Old importers will ignore new fields.
    New importers check 'version' field to determine format.
    """

    # Version marker for format detection
    version: str  # "2.0"

    # ===== EXISTING V1 FIELDS (maintained for backward compatibility) =====
    annotated_docs: dict[str, OpenContractDocExport]
    doc_labels: dict[str, AnnotationLabelPythonType]
    text_labels: dict[str, AnnotationLabelPythonType]
    corpus: OpenContractCorpusV2Type  # Enhanced with V2 fields
    label_set: OpenContractsLabelSetType

    # ===== NEW V2 FIELDS =====

    # Structural annotations (shared across document copies)
    structural_annotation_sets: dict[
        str, StructuralAnnotationSetExport
    ]  # Keyed by content_hash

    # Corpus folder hierarchy
    folders: list[CorpusFolderExport]

    # Document version trees (DocumentPath history)
    document_paths: list[DocumentPathExport]

    # Cross-document relationships
    relationships: list[OpenContractsRelationshipPythonType]

    # Agent configuration
    agent_config: AgentConfigExport

    # Markdown description and revision history
    md_description: Optional[str]
    md_description_revisions: list[DescriptionRevisionExport]

    # Post-processors configuration
    post_processors: list[str]

    # Ingestion sources (lineage tracking)
    ingestion_sources: NotRequired[list[IngestionSourceExport]]

    # ===== OPTIONAL V2 FIELDS (based on export flags) =====

    # Conversations/messages (only if include_conversations=True)
    conversations: NotRequired[list[ConversationExport]]
    messages: NotRequired[list[ChatMessageExport]]
    message_votes: NotRequired[list[MessageVoteExport]]

    # Action trail (only if include_action_trail=True)
    action_trail: NotRequired[ActionTrailExport]


# ============================================================================
# Worker Document Upload Format
# ============================================================================


class WorkerEmbeddingsType(TypedDict):
    """
    Embedding data included in a worker document upload.

    External workers pre-compute embeddings and include them so that the server
    can store them directly without re-running an embedder. The embedder_path
    must match one of the supported embedding dimensions (384–4096).
    """

    # Identifies the model/pipeline that produced these embeddings
    embedder_path: str  # e.g. "sentence-transformers/all-MiniLM-L6-v2"

    # Document-level embedding (optional)
    document_embedding: NotRequired[Optional[list[float]]]

    # Annotation embeddings keyed by the annotation's local ID from labelled_text
    annotation_embeddings: NotRequired[dict[str, list[float]]]


class WorkerDocumentUploadMetadataType(TypedDict):
    """
    JSON metadata payload for a single-document worker upload.

    Extends the V2 document export format with:
    - Pre-computed embeddings
    - Target path / folder placement
    - Label definitions (so missing labels can be auto-created)

    The document file itself is sent as a separate multipart field.
    """

    # Document metadata
    title: str
    description: NotRequired[Optional[str]]
    content: str  # Full extracted text
    page_count: int
    file_type: NotRequired[Optional[str]]  # MIME type

    # PAWLs token data (required for PDF annotations)
    pawls_file_content: list[PawlsPagePythonType]

    # Target placement within the corpus
    target_path: NotRequired[Optional[str]]  # e.g. "contracts/2024/nda.pdf"
    target_folder_path: NotRequired[Optional[str]]  # e.g. "contracts/2024"

    # Document-level labels (list of label names)
    doc_labels: NotRequired[list[str]]

    # Text / token-level annotations
    labelled_text: NotRequired[list[OpenContractsAnnotationPythonType]]

    # Intra-document relationships
    relationships: NotRequired[list[OpenContractsRelationshipPythonType]]

    # Label definitions — allows the server to auto-create any that don't exist
    text_labels: NotRequired[dict[str, AnnotationLabelPythonType]]
    doc_labels_definitions: NotRequired[dict[str, AnnotationLabelPythonType]]

    # Pre-computed embeddings from the external worker
    embeddings: NotRequired[WorkerEmbeddingsType]
