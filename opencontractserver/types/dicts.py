from typing import Optional, Union

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

    text_labels: dict[str | int, AnnotationLabelPythonType]
    doc_labels: dict[str | int, AnnotationLabelPythonType]


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
    This is what an actual PAWLS token looks like.
    """

    x: float
    y: float
    width: float
    height: float
    text: str


class PawlsPagePythonType(TypedDict):
    """
    Pawls files are comprised of lists of jsons that correspond to the
    necessary tokens and page information for a given page. This describes
    the data shape for each of those page objs.
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
    These are how tokens are referenced in annotation jsons.
    """

    pageIndex: int
    tokenIndex: int


class OpenContractsSinglePageAnnotationType(TypedDict):
    """
    This is the data shapee for our actual annotations on a given page of a pdf.
    In practice, annotations are always assumed to be multi-page, and this means
    our annotation jsons are stored as a dict map of page #s to the annotation data:

    Dict[int, OpenContractsSinglePageAnnotationType]

    """

    bounds: BoundingBoxPythonType
    tokensJsons: list[TokenIdPythonType]
    rawText: str


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
    """

    id: Optional[Union[str, int]]  # noqa  # fmt: off
    annotationLabel: str
    rawText: str
    page: int
    annotation_json: Union[
        dict[Union[int, str], OpenContractsSinglePageAnnotationType], TextSpanData
    ]
    parent_id: Optional[Union[str, int]]
    annotation_type: Optional[str]
    structural: bool


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
