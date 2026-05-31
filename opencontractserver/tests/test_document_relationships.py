from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase
from graphene.test import Client
from graphql_relay import to_global_id

from config.graphql.schema import schema
from opencontractserver.annotations.models import AnnotationLabel
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import (
    Document,
    DocumentPath,
    DocumentRelationship,
)
from opencontractserver.tests.fixtures import SAMPLE_PDF_FILE_TWO_PATH

User = get_user_model()


class TestContext:
    def __init__(self, user):
        self.user = user


class DocumentRelationshipsQueryTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpassword"
        )
        self.graphene_client = Client(schema, context_value=TestContext(self.user))

        # Create test corpus
        self.corpus = Corpus.objects.create(
            title="TestCorpus",
            creator=self.user,
        )

        # Create test documents
        pdf_file = ContentFile(
            SAMPLE_PDF_FILE_TWO_PATH.open("rb").read(), name="test.pdf"
        )

        self.source_doc = Document.objects.create(
            creator=self.user,
            title="Source Doc",
            description="Source document",
            custom_meta={},
            pdf_file=pdf_file,
            backend_lock=True,
        )

        self.target_doc = Document.objects.create(
            creator=self.user,
            title="Target Doc",
            description="Target document",
            custom_meta={},
            pdf_file=pdf_file,
            backend_lock=True,
        )

        # Create test annotation label
        self.annotation_label = AnnotationLabel.objects.create(
            text="Test Relationship",
            label_type="DOC_RELATIONSHIP_LABEL",
            creator=self.user,
        )

        # Add documents to corpus via DocumentPath (required for DocumentRelationship)
        DocumentPath.objects.create(
            document=self.source_doc,
            corpus=self.corpus,
            creator=self.user,
            path="/source_doc",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )
        DocumentPath.objects.create(
            document=self.target_doc,
            corpus=self.corpus,
            creator=self.user,
            path="/target_doc",
            version_number=1,
            is_current=True,
            is_deleted=False,
        )

        # Create test relationships
        self.relationship = DocumentRelationship.objects.create(
            source_document=self.source_doc,
            target_document=self.target_doc,
            relationship_type="RELATIONSHIP",
            annotation_label=self.annotation_label,
            creator=self.user,
            corpus=self.corpus,
        )

        self.note = DocumentRelationship.objects.create(
            source_document=self.source_doc,
            target_document=self.target_doc,
            relationship_type="NOTES",
            data={"note": "Test note content"},
            creator=self.user,
            corpus=self.corpus,
        )

    def test_document_relationship_query(self):
        query = """
            query {
                documentRelationship(id: "%s") {
                    id
                    relationshipType
                    sourceDocument {
                        id
                        title
                    }
                    targetDocument {
                        id
                        title
                    }
                    annotationLabel {
                        id
                        text
                    }
                    corpus {
                        id
                        title
                    }
                }
            }
        """ % to_global_id("DocumentRelationshipType", self.relationship.id)

        result = self.graphene_client.execute(query)
        self.assertIsNone(result.get("errors"))
        data = result["data"]["documentRelationship"]

        self.assertEqual(
            data["id"],
            to_global_id("DocumentRelationshipType", self.relationship.id),
        )
        self.assertEqual(data["relationshipType"], "RELATIONSHIP")
        self.assertEqual(
            data["sourceDocument"]["id"],
            to_global_id("DocumentType", self.source_doc.id),
        )
        self.assertEqual(
            data["targetDocument"]["id"],
            to_global_id("DocumentType", self.target_doc.id),
        )
        self.assertEqual(
            data["annotationLabel"]["id"],
            to_global_id("AnnotationLabelType", self.annotation_label.id),
        )

    def test_document_note_query(self):
        query = """
            query {
                documentRelationship(id: "%s") {
                    id
                    relationshipType
                    sourceDocument {
                        id
                        title
                    }
                    targetDocument {
                        id
                        title
                    }
                    data
                }
            }
        """ % to_global_id("DocumentRelationshipType", self.note.id)

        result = self.graphene_client.execute(query)
        self.assertIsNone(result.get("errors"))
        data = result["data"]["documentRelationship"]

        self.assertEqual(
            data["id"],
            to_global_id("DocumentRelationshipType", self.note.id),
        )
        self.assertEqual(data["relationshipType"], "NOTES")
        self.assertEqual(data["data"], {"note": "Test note content"})

    def test_document_all_relationships_query(self):
        query = """
            query {{
                document(id: "{}") {{
                    id
                    allDocRelationships(corpusId: "{}") {{
                        id
                        relationshipType
                        sourceDocument {{
                            id
                            title
                        }}
                        targetDocument {{
                            id
                            title
                        }}
                    }}
                }}
            }}
        """.format(
            to_global_id("DocumentType", self.source_doc.id),
            to_global_id("CorpusType", self.corpus.id),
        )

        result = self.graphene_client.execute(query)
        self.assertIsNone(result.get("errors"))
        relationships = result["data"]["document"]["allDocRelationships"]

        self.assertEqual(
            len(relationships), 2
        )  # Should have both relationship and note
        relationship_types = {r["relationshipType"] for r in relationships}
        self.assertEqual(relationship_types, {"RELATIONSHIP", "NOTES"})

    def test_document_relationships_annotation_label_text_filter(self):
        """
        The corpus Table of Contents query relies on a server-side
        `annotationLabelText` filter (defined as `annotation_label_text`
        with `iexact` lookup on `DocumentRelationshipFilter`) to restrict
        edges to only the parent-labeled hierarchy rows. Pin the behavior
        so a future refactor cannot silently drop the filter and revert
        the TOC to fetching every relationship row.
        """
        # Build a second relationship whose label is "parent" so we can
        # prove the filter narrows on label text (case-insensitively).
        parent_label = AnnotationLabel.objects.create(
            text="parent",
            label_type="DOC_RELATIONSHIP_LABEL",
            creator=self.user,
        )
        parent_relationship = DocumentRelationship.objects.create(
            source_document=self.source_doc,
            target_document=self.target_doc,
            relationship_type="RELATIONSHIP",
            annotation_label=parent_label,
            creator=self.user,
            corpus=self.corpus,
        )

        # Sanity check: the corpus has 3 relationships total (the two from
        # `setUp` plus the parent-labeled one we just made). The filter
        # must return exactly 1 edge — only the parent-labeled relationship.
        corpus_gid = to_global_id("CorpusType", self.corpus.id)
        query = """
            query($corpusId: ID, $labelText: String) {
                documentRelationships(
                    corpusId: $corpusId
                    annotationLabelText: $labelText
                ) {
                    edges {
                        node {
                            id
                            relationshipType
                            annotationLabel { text }
                        }
                    }
                    totalCount
                }
            }
        """
        # Mixed case input — the filter uses `iexact` so "PARENT" must match.
        result = self.graphene_client.execute(
            query, variables={"corpusId": corpus_gid, "labelText": "PARENT"}
        )
        self.assertIsNone(result.get("errors"))
        rels = result["data"]["documentRelationships"]
        self.assertEqual(rels["totalCount"], 1)
        self.assertEqual(len(rels["edges"]), 1)
        self.assertEqual(
            rels["edges"][0]["node"]["id"],
            to_global_id("DocumentRelationshipType", parent_relationship.id),
        )
        self.assertEqual(rels["edges"][0]["node"]["annotationLabel"]["text"], "parent")

    def test_document_relationships_combined_type_and_label_filter(self):
        """
        The corpus TOC query passes ``relationshipType="RELATIONSHIP"`` and
        ``annotationLabelText="parent"`` together. Pin the combined-filter
        interaction so a future refactor that drops or reorders the filters
        is caught here rather than as a TOC regression.
        """
        # A parent-labeled RELATIONSHIP — the only row the TOC should return.
        parent_label = AnnotationLabel.objects.create(
            text="parent",
            label_type="DOC_RELATIONSHIP_LABEL",
            creator=self.user,
        )
        parent_relationship = DocumentRelationship.objects.create(
            source_document=self.source_doc,
            target_document=self.target_doc,
            relationship_type="RELATIONSHIP",
            annotation_label=parent_label,
            creator=self.user,
            corpus=self.corpus,
        )
        # A parent-labeled row with a non-RELATIONSHIP type — must be excluded
        # by ``relationshipType``.
        DocumentRelationship.objects.create(
            source_document=self.source_doc,
            target_document=self.target_doc,
            relationship_type="NOTES",
            annotation_label=parent_label,
            creator=self.user,
            corpus=self.corpus,
        )

        corpus_gid = to_global_id("CorpusType", self.corpus.id)
        query = """
            query(
                $corpusId: ID,
                $relType: DocumentsDocumentRelationshipRelationshipTypeChoices,
                $labelText: String,
            ) {
                documentRelationships(
                    corpusId: $corpusId
                    relationshipType: $relType
                    annotationLabelText: $labelText
                ) {
                    edges { node { id relationshipType } }
                    totalCount
                }
            }
        """
        result = self.graphene_client.execute(
            query,
            variables={
                "corpusId": corpus_gid,
                "relType": "RELATIONSHIP",
                "labelText": "parent",
            },
        )
        self.assertIsNone(result.get("errors"))
        rels = result["data"]["documentRelationships"]
        # Exactly one row matches BOTH filters: the parent-labeled RELATIONSHIP.
        self.assertEqual(rels["totalCount"], 1)
        self.assertEqual(
            rels["edges"][0]["node"]["id"],
            to_global_id("DocumentRelationshipType", parent_relationship.id),
        )
        self.assertEqual(rels["edges"][0]["node"]["relationshipType"], "RELATIONSHIP")
