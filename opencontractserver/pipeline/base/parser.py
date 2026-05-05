import json
import logging
from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any, Optional, cast

from django.conf import settings
from django.core.files.base import ContentFile
from plasmapdf.models.PdfDataLayer import build_translation_layer

from opencontractserver.annotations.models import (
    RELATIONSHIP_LABEL,
    Annotation,
    Relationship,
    StructuralAnnotationSet,
)
from opencontractserver.documents.models import Document
from opencontractserver.pipeline.base.exceptions import DocumentParsingError
from opencontractserver.pipeline.base.file_types import FileTypeEnum
from opencontractserver.types.dicts import OpenContractDocExport
from opencontractserver.utils.compact_pawls import compact_pawls_pages
from opencontractserver.utils.importing import (
    import_annotations,
    import_relationships,
    load_or_create_labels,
)

from .base_component import PipelineComponentBase

logger = logging.getLogger(__name__)


class BaseParser(PipelineComponentBase, ABC):
    """
    Abstract base parser class. Parsers should inherit from this class.
    Handles automatic loading of settings from Django settings.PIPELINE_SETTINGS.
    """

    title: str = ""
    description: str = ""
    author: str = ""
    dependencies: list[str] = []
    supported_file_types: list[FileTypeEnum] = []
    input_schema: Mapping = (
        {}
    )  # If you want user to provide inputs, define a jsonschema here

    def __init__(self, **kwargs):
        """
        Initializes the Parser.
        Kwargs are passed to the superclass constructor (PipelineComponentBase).
        """
        super().__init__(**kwargs)

    @abstractmethod
    def _parse_document_impl(
        self, user_id: int, doc_id: int, **all_kwargs
    ) -> Optional[OpenContractDocExport]:
        """
        Abstract internal method to parse a document.
        Concrete subclasses must implement this method.

        Args:
            user_id (int): ID of the user.
            doc_id (int): ID of the document to parse.
            **all_kwargs: All keyword arguments, including those from
                          PIPELINE_SETTINGS and direct call-time arguments.

        Returns:
            Optional[OpenContractDocExport]: The parsed document data, or None if parsing failed.
        """
        pass

    def parse_document(
        self, user_id: int, doc_id: int, **direct_kwargs
    ) -> Optional[OpenContractDocExport]:
        """
        Parses a document, automatically injecting settings from PIPELINE_SETTINGS.

        Args:
            user_id (int): ID of the user.
            doc_id (int): ID of the document to parse.
            **direct_kwargs: Arbitrary keyword arguments that may be provided
                             for specific parser functionalities at call time.
                             These will override settings from PIPELINE_SETTINGS.

        Returns:
            Optional[OpenContractDocExport]: The parsed document data, or None if parsing failed.
        """
        # Merge component settings with direct kwargs, direct_kwargs take precedence
        merged_kwargs = {**self.get_component_settings(), **direct_kwargs}
        logger.info(
            f"Calling _parse_document_impl for doc_id {doc_id} with merged kwargs: {merged_kwargs}"
        )
        return self._parse_document_impl(user_id, doc_id, **merged_kwargs)

    def save_parsed_data(
        self,
        user_id: int,
        doc_id: int,
        open_contracts_data: OpenContractDocExport,
        corpus_id: Optional[int] = None,
        annotation_type: Optional[str] = None,
    ) -> None:
        """
        Saves the parsed data (both annotations and relationships) to the Document model.

        Args:
            user_id (int): ID of the user.
            doc_id (int): ID of the document.
            open_contracts_data (OpenContractDocExport): The parsed document data, including:
                - labelled_text (List[OpenContractsAnnotationPythonType]):
                  Annotation list to be imported.
                - relationships (Optional[List[OpenContractsRelationshipPythonType]]):
                  Relationship list to be imported.
                - page_count, pawls_file_content, content, etc.
            corpus_id (Optional[int]): ID of the corpus, if the document should be associated with one.
            annotation_type (Optional[str]): The fallback annotation_type (e.g., SPAN_LABEL or TOKEN_LABEL).
                If the annotation data doesn't specify an annotation_type, this one is used.
        """
        logger = logging.getLogger(__name__)
        logger.info(f"Saving parsed data for doc {doc_id}")

        document = Document.objects.get(pk=doc_id)

        # Get user for corpus operations
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user = User.objects.get(pk=user_id)

        # Associate with corpus if provided
        if corpus_id:
            # Use Django's lazy-loading with string reference to avoid circular import
            from django.apps import apps

            Corpus = apps.get_model("corpuses", "Corpus")
            DocumentPath = apps.get_model("documents", "DocumentPath")
            corpus_obj = Corpus.objects.get(id=corpus_id)

            # Check if document is ALREADY in this corpus via DocumentPath
            # (e.g., created by import_content in process_documents_zip)
            existing_path = DocumentPath.objects.filter(
                document=document,
                corpus=corpus_obj,
                is_current=True,
                is_deleted=False,
            ).first()

            if existing_path:
                # Document already in corpus - don't create another copy
                logger.info(
                    f"Document {doc_id} already in corpus {corpus_obj.title} "
                    f"via DocumentPath {existing_path.id}, skipping add_document"
                )
            else:
                # Document not yet in corpus - use add_document for corpus isolation
                document, status, _ = corpus_obj.add_document(
                    document=document, user=user
                )
                logger.info(
                    f"Associated document with corpus: {corpus_obj.title} (status: {status})"
                )
        else:
            corpus_obj = None

        # Save content to txt_extract_file
        txt_content = open_contracts_data.get("content", "")
        txt_file = ContentFile(txt_content.encode("utf-8"))
        document.txt_extract_file.save(f"doc_{doc_id}.txt", txt_file)

        # Handle PAWLS content if any
        pawls_file_content = open_contracts_data.get("pawls_file_content")
        if pawls_file_content:
            compact_data = compact_pawls_pages(pawls_file_content)
            pawls_string = json.dumps(compact_data)
            pawls_file = ContentFile(pawls_string.encode("utf-8"))
            document.pawls_parse_file.save(f"doc_{doc_id}.pawls", pawls_file)

            # Create text layer from PAWLS tokens (use original v1 data)
            span_translation_layer = build_translation_layer(pawls_file_content)
            # Optionally overwrite txt_extract_file with text from PAWLS
            txt_file = ContentFile(span_translation_layer.doc_text.encode("utf-8"))
            document.txt_extract_file.save(f"doc_{doc_id}.txt", txt_file)
            document.page_count = len(pawls_file_content)
        else:
            # Handle cases without PAWLS content
            document.page_count = open_contracts_data.get("page_count", 1)

        document.save()

        # Determine fallback label type (for annotations) if annotation types aren't specified in data
        logger.info(
            f"Loading or creating labels for document {doc_id} with file type {document.file_type}"
        )

        if annotation_type is not None:
            target_label_type = annotation_type
        else:
            target_label_type = settings.ANNOTATION_LABELS.get(
                document.file_type, "SPAN_LABEL"
            )

        logger.info(f"Target label type for textual annotations: {target_label_type}")

        # 1) Build a data dict for text annotation labels
        text_labels_data_dict = {
            label_data["annotationLabel"]: {
                "label_type": target_label_type,
                "color": "grey",
                "description": "Parser Structural Label",
                "icon": "expand",
                "text": label_data["annotationLabel"],
                "creator_id": user_id,
                "read_only": True,
            }
            for label_data in open_contracts_data.get("labelled_text", [])
        }

        logger.info(f"Text label data dict: {text_labels_data_dict}")

        # 2) Create or load text labels
        existing_text_labels = load_or_create_labels(
            user_id=user_id,
            labelset_obj=None,  # No labelset in this context
            label_data_dict=text_labels_data_dict,
            existing_labels={},
        )

        logger.info(f"Existing text label lookup: {existing_text_labels}")

        # 3) Import annotations & store mapping of old annotation IDs to new DB IDs
        # Pass PAWLs data for pre-extracting image content (faster embeddings).
        # Cast PawlsPagePythonType list to dict-list since import_annotations'
        # signature predates the typed-dict surface.
        annotation_id_map = import_annotations(
            user_id=user_id,
            doc_obj=document,
            corpus_obj=corpus_obj,
            annotations_data=open_contracts_data.get("labelled_text", []),
            label_lookup=existing_text_labels,
            label_type=target_label_type,
            pawls_data=cast("list[dict[Any, Any]]", pawls_file_content),
        )

        # 4) If there are relationships, load/create relationship labels and then import
        relationship_data = open_contracts_data.get("relationships", [])
        if relationship_data:
            # Build label data dict for relationship labels
            relationship_label_texts = {
                rel["relationshipLabel"] for rel in relationship_data
            }
            relationship_label_data_dict = {
                label_text: {
                    "label_type": RELATIONSHIP_LABEL,  # Distinct from text annotation type
                    "color": "gray",
                    "description": "Parser Relationship Label",
                    "icon": "share-alt",
                    "text": label_text,
                    "creator_id": user_id,
                    "read_only": True,
                }
                for label_text in relationship_label_texts
            }

            existing_relationship_labels = load_or_create_labels(
                user_id=user_id,
                labelset_obj=None,  # No labelset in this context
                label_data_dict=relationship_label_data_dict,
                existing_labels={},
            )

            # Now import relationships
            import_relationships(
                user_id=user_id,
                doc_obj=document,
                corpus_obj=corpus_obj,
                relationships_data=relationship_data,
                label_lookup=existing_relationship_labels,
                annotation_id_map=annotation_id_map,
            )

        # 5) Create StructuralAnnotationSet and migrate structural annotations to it
        self._create_structural_annotation_set(document, user)

        logger.info(
            f"Document {doc_id} parsed (with annotations & relationships) and saved successfully."
        )

    def _create_structural_annotation_set(self, document: Document, user) -> None:
        """
        Create a StructuralAnnotationSet for the document and migrate structural
        annotations and relationships to it.

        This ensures structural annotations are properly isolated per document and
        can be embedded using corpus-specific embedders.

        Args:
            document: The Document object
            user: The user creating the set
        """
        # Check if document already has a structural annotation set
        if document.structural_annotation_set:
            logger.info(
                f"Document {document.pk} already has StructuralAnnotationSet "
                f"{document.structural_annotation_set.pk}"
            )
            return

        # Find structural annotations on this document
        structural_annotations = Annotation.objects.filter(
            document=document, structural=True, structural_set__isnull=True
        )

        if not structural_annotations.exists():
            logger.info(
                f"Document {document.pk} has no structural annotations to migrate"
            )
            return

        # Generate content hash for the set
        content_hash = document.pdf_file_hash or f"doc_{document.pk}"

        # Use get_or_create to handle retry scenarios where the set was created
        # but the document link wasn't saved (e.g., task failed after line 298
        # but before document.save() at line 337)
        struct_set, created = StructuralAnnotationSet.objects.get_or_create(
            content_hash=content_hash,
            defaults={
                "creator": user,
                "parser_name": self.title or self.__class__.__name__,
                "parser_version": "1.0",
                "page_count": document.page_count,
                "pawls_parse_file": document.pawls_parse_file,
                "txt_extract_file": document.txt_extract_file,
            },
        )

        if created:
            logger.info(
                f"Created StructuralAnnotationSet {struct_set.pk} for document {document.pk}"
            )
        else:
            logger.info(
                f"Reusing existing StructuralAnnotationSet {struct_set.pk} "
                f"for document {document.pk} (retry scenario)"
            )

        # Migrate structural annotations to the set
        structural_annotation_ids = set(
            structural_annotations.values_list("id", flat=True)
        )

        for annot in structural_annotations:
            annot.structural_set = struct_set
            annot.document = None  # XOR constraint: either document or structural_set
            annot.save()

        # Migrate structural relationships to the set
        structural_relationships = Relationship.objects.filter(
            document=document, structural=True, structural_set__isnull=True
        ).filter(
            source_annotations__id__in=structural_annotation_ids,
            target_annotations__id__in=structural_annotation_ids,
        )

        for rel in structural_relationships:
            rel.structural_set = struct_set
            rel.document = None  # XOR constraint
            rel.save()

        # Link document to the structural set
        document.structural_annotation_set = struct_set
        document.save()

        logger.info(
            f"Migrated {structural_annotations.count()} annotations and "
            f"{structural_relationships.count()} relationships to StructuralAnnotationSet "
            f"{struct_set.pk}"
        )

    def process_document(
        self, user_id: int, doc_id: int, **kwargs
    ) -> OpenContractDocExport:
        """
        Process a document by parsing it and then saving the parsed data.
        This method calls parse_document(...) and then save_parsed_data(...).

        Args:
            user_id (int): ID of the user.
            doc_id (int): ID of the document to process.
            **kwargs: Arbitrary keyword arguments that may be provided
                      for specific parser functionalities. Notably:
                      - corpus_id (Optional[int]): ID of corpus for corpus-specific embeddings

        Returns:
            OpenContractDocExport: The parsed document data.

        Raises:
            DocumentParsingError: If parsing fails. The exception's is_transient
                attribute indicates whether the error might succeed on retry.
        """
        # Extract corpus_id for save_parsed_data (not needed by parse_document)
        corpus_id = kwargs.pop("corpus_id", None)

        logger.info(
            f"Processing document {doc_id} with possible parser kwargs: {kwargs}"
            + (f" (corpus_id={corpus_id})" if corpus_id else "")
        )

        parsed_data = self.parse_document(user_id, doc_id, **kwargs)
        if parsed_data is None:
            raise DocumentParsingError(
                f"Parser {self.__class__.__name__} returned None for document {doc_id}",
                is_transient=True,  # Assume transient by default; subclasses override
            )

        self.save_parsed_data(user_id, doc_id, parsed_data, corpus_id=corpus_id)
        logger.info(f"Document {doc_id} processed successfully.")

        return parsed_data
