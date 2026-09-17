"""A citation preserves its evidence; current views follow the active corpus paths."""

from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.test import TestCase
from graphql_relay import to_global_id

from config.graphql.testing import Client
from opencontractserver.annotations.models import (
    RELATIONSHIP_LABEL,
    SPAN_LABEL,
    Annotation,
    CorpusReference,
)
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import DocumentRelationship
from opencontractserver.documents.services import DocumentRelationshipService
from opencontractserver.documents.versioning import delete_document, import_document
from opencontractserver.enrichment import constants as C
from opencontractserver.enrichment.services import (
    CorpusReferenceService,
    EnrichmentService,
)
from opencontractserver.enrichment.services.governance_graph_service import (
    GovernanceGraphService,
)
from opencontractserver.enrichment.writer import EnrichmentWriter


class ReferenceVersioningTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="reviewer")
        self.corpus = Corpus.objects.create(title="Filings", creator=self.user)
        self.authorities = Corpus.objects.create(title="Law", creator=self.user)
        self.source = self.import_text(
            self.corpus,
            "/filing.txt",
            "Section 145 of the Delaware General Corporation Law applies.",
        )

    def import_text(self, corpus, path, text, **kwargs):
        document, _, _ = import_document(
            corpus=corpus,
            path=path,
            content=text.encode(),
            user=self.user,
            file_type="text/plain",
            title=path.rsplit("/", 1)[-1],
            **kwargs,
        )
        return document

    def query(self, query, **variables):
        from config.graphql.schema import schema

        result = Client(schema).execute(
            query,
            variable_values=variables,
            context_value=SimpleNamespace(user=self.user),
        )
        self.assertNotIn("errors", result, result)
        return result["data"]

    def test_citation_keeps_as_cited_version_and_exposes_visible_current_text(self):
        law_v1 = self.import_text(
            self.authorities,
            "/145.txt",
            "Original law.",
            custom_meta={"canonical_key": "dgcl:145"},
        )
        service = EnrichmentService()
        service.apply(corpus_id=self.corpus.pk, creator_id=self.user.pk)
        ref = CorpusReference.objects.get(corpus=self.corpus, canonical_key="dgcl:145")
        original_url = ref.source_annotation.link_url
        assert original_url is not None
        self.assertTrue(original_url.endswith("?v=1"), original_url)

        law_v2 = self.import_text(
            self.authorities,
            "/145.txt",
            "Amended law.",
            custom_meta={"canonical_key": "dgcl:145"},
        )
        service.link_external_references(
            corpus_id=self.corpus.pk, creator_id=self.user.pk
        )
        ref.refresh_from_db()
        self.assertEqual(ref.target_document_id, law_v1.pk)
        self.assertEqual(ref.source_annotation.link_url, original_url)

        query = """query($corpus: ID!) {
          corpusReferences(corpusId: $corpus) { edges { node {
            targetDocument { id } currentTargetDocument { id } targetIsSuperseded
          } } }
        }"""
        row = self.query(query, corpus=to_global_id("CorpusType", self.corpus.pk))[
            "corpusReferences"
        ]["edges"][0]["node"]
        self.assertEqual(
            row,
            {
                "targetDocument": {"id": to_global_id("DocumentType", law_v1.pk)},
                "currentTargetDocument": {
                    "id": to_global_id("DocumentType", law_v2.pk)
                },
                "targetIsSuperseded": True,
            },
        )
        resolved = self.query(
            """query($user: String!, $corpus: String!, $doc: String!) {
          documentInCorpusBySlugs(userSlug: $user, corpusSlug: $corpus,
            documentSlug: $doc, versionNumber: 1) { id }
        }""",
            user=self.user.slug,
            corpus=self.authorities.slug,
            doc=law_v1.slug,
        )
        self.assertEqual(
            resolved["documentInCorpusBySlugs"]["id"],
            to_global_id("DocumentType", law_v1.pk),
        )

        # A different tree replaces the pin, including any annotation in the old tree.
        target_annotation = Annotation.objects.create(
            document=law_v1,
            corpus=self.authorities,
            creator=self.user,
            annotation_type=SPAN_LABEL,
            raw_text="Original",
            json={"start": 0, "end": 8},
        )
        ref.target_annotation = target_annotation
        ref.save()
        delete_document(self.authorities, "/145.txt", self.user)
        replacement = self.import_text(
            self.authorities,
            "/replacement.txt",
            "Rebuilt authority.",
            custom_meta={"canonical_key": "dgcl:145"},
        )
        service.link_external_references(
            corpus_id=self.corpus.pk, creator_id=self.user.pk
        )
        ref.refresh_from_db()
        self.assertEqual(ref.target_document_id, replacement.pk)
        self.assertIsNone(ref.target_annotation_id)
        delete_document(self.authorities, "/replacement.txt", self.user)
        service.link_external_references(
            corpus_id=self.corpus.pk, creator_id=self.user.pk
        )
        ref.refresh_from_db()
        self.assertEqual(ref.resolution_status, C.STATUS_EXTERNAL)
        self.assertIsNone(ref.target_document_id)
        self.assertIsNone(ref.target_annotation_id)
        self.assertIsNone(ref.source_annotation.link_url)

    def test_current_and_historical_reference_views_after_reupload_and_delete(self):
        service = EnrichmentService()
        service.apply(corpus_id=self.corpus.pk, creator_id=self.user.pk)
        old_ref = CorpusReference.objects.get(corpus=self.corpus)
        source_v2 = self.import_text(
            self.corpus,
            "/filing.txt",
            "Section 145 of the Delaware General Corporation Law still applies.",
        )
        service.apply(corpus_id=self.corpus.pk, creator_id=self.user.pk)
        new_ref = CorpusReference.objects.get(source_annotation__document=source_v2)
        self.assertQuerySetEqual(
            CorpusReferenceService.for_corpus(self.user, self.corpus.pk),
            [new_ref],
            ordered=False,
        )
        self.assertQuerySetEqual(
            CorpusReferenceService.for_corpus(
                self.user, self.corpus.pk, include_historical=True
            ),
            [old_ref, new_ref],
            ordered=False,
        )
        views = self.query(
            """query($corpus: ID!) {
          corpus(id: $corpus) { references { edges { node { id } } } }
          corpusReferences(corpusId: $corpus, includeHistorical: true) {
            edges { node { id } }
          }
        }""",
            corpus=to_global_id("CorpusType", self.corpus.pk),
        )
        self.assertEqual(
            views["corpus"]["references"]["edges"],
            [{"node": {"id": to_global_id("CorpusReferenceType", new_ref.pk)}}],
        )
        self.assertEqual(len(views["corpusReferences"]["edges"]), 2)
        delete_document(self.corpus, "/filing.txt", self.user)
        self.assertFalse(
            CorpusReferenceService.for_corpus(self.user, self.corpus.pk).exists()
        )

    def test_existing_unversioned_mentions_are_repaired_by_the_migration(self):
        from importlib import import_module

        from django.apps import apps
        from django.db import connection

        self.import_text(
            self.authorities,
            "/145.txt",
            "Original law.",
            custom_meta={"canonical_key": "dgcl:145"},
        )
        EnrichmentService().apply(corpus_id=self.corpus.pk, creator_id=self.user.pk)
        ref = CorpusReference.objects.get(corpus=self.corpus)
        original_url = ref.source_annotation.link_url
        assert original_url is not None
        Annotation.objects.filter(pk=ref.source_annotation_id).update(
            link_url=original_url.split("?")[0]
        )
        self.import_text(
            self.authorities,
            "/145.txt",
            "Amended law.",
            custom_meta={"canonical_key": "dgcl:145"},
        )
        migration = import_module(
            "opencontractserver.annotations.migrations.0106_annotation_version_decision"
        )
        migration.pin_existing_mention_links(
            apps, SimpleNamespace(connection=connection)
        )
        ref.source_annotation.refresh_from_db()
        self.assertEqual(ref.source_annotation.link_url, original_url)

    def test_current_target_does_not_leak_a_private_new_version(self):
        for corpus in (self.corpus, self.authorities):
            corpus.is_public = True
            corpus.save()
        self.source.is_public = True
        self.source.save()
        law_v1 = self.import_text(
            self.authorities,
            "/145.txt",
            "Original law.",
            custom_meta={"canonical_key": "dgcl:145"},
        )
        EnrichmentService().apply(corpus_id=self.corpus.pk, creator_id=self.user.pk)
        ref = CorpusReference.objects.select_related("target_document").get(
            corpus=self.corpus
        )
        law_v2 = self.import_text(
            self.authorities,
            "/145.txt",
            "Private amendment.",
            custom_meta={"canonical_key": "dgcl:145"},
        )
        law_v2.is_public = False
        law_v2.save()
        reader = get_user_model().objects.create_user(username="public-reader")
        self.assertEqual(ref.target_document_id, law_v1.pk)
        self.assertIsNone(
            CorpusReferenceService.current_target(
                ref, reader, request=SimpleNamespace()
            )
        )
        request = SimpleNamespace()
        self.assertEqual(
            CorpusReferenceService.current_target(ref, self.user, request=request),
            law_v2,
        )
        with self.assertNumQueries(0):
            self.assertEqual(
                CorpusReferenceService.current_target(ref, self.user, request=request),
                law_v2,
            )

    def test_handwritten_document_links_follow_both_endpoints_without_copying_derived_links(
        self,
    ):
        other = self.import_text(self.corpus, "/other.txt", "Another document.")
        label = self.corpus.ensure_label_and_labelset(
            label_text="Supports",
            label_type=RELATIONSHIP_LABEL,
            creator_id=self.user.pk,
        )
        original = DocumentRelationship.objects.create(
            source_document=self.source,
            target_document=other,
            corpus=self.corpus,
            creator=self.user,
            annotation_label=label,
            data={"explanation": "These belong together"},
        )
        note = DocumentRelationship.objects.create(
            source_document=other,
            target_document=self.source,
            corpus=self.corpus,
            creator=self.user,
            relationship_type="NOTES",
            data={"text": "Read alongside the filing"},
        )
        DocumentRelationship.objects.create(
            source_document=other,
            target_document=self.source,
            corpus=self.corpus,
            creator=self.user,
            annotation_label=label,
            data={"analysis_id": None},
        )
        source_v2 = self.import_text(self.corpus, "/filing.txt", "Revised filing.")
        current = DocumentRelationshipService.get_visible_relationships(
            self.user, corpus_id=self.corpus.pk
        )
        self.assertEqual(
            set(
                current.values_list(
                    "source_document_id", "target_document_id", "relationship_type"
                )
            ),
            {
                (source_v2.pk, other.pk, "RELATIONSHIP"),
                (other.pk, source_v2.pk, "NOTES"),
            },
        )
        original.refresh_from_db()
        note.refresh_from_db()
        self.assertEqual(original.source_document_id, self.source.pk)
        self.assertEqual(note.target_document_id, self.source.pk)

        other_v2 = self.import_text(
            self.corpus, "/other.txt", "Revised other document."
        )
        source_v3 = self.import_text(self.corpus, "/filing.txt", "Third filing.")
        current = DocumentRelationshipService.get_visible_relationships(
            self.user, corpus_id=self.corpus.pk
        )
        self.assertEqual(
            set(
                current.values_list(
                    "source_document_id", "target_document_id", "relationship_type"
                )
            ),
            {
                (source_v3.pk, other_v2.pk, "RELATIONSHIP"),
                (other_v2.pk, source_v3.pk, "NOTES"),
            },
        )
        self.assertEqual(
            current.get(relationship_type="RELATIONSHIP").data, original.data
        )

    def test_document_graph_reconciles_only_active_source_versions(self):
        target = self.import_text(self.corpus, "/exhibit.txt", "The exhibit.")
        mention = Annotation.objects.create(
            document=self.source,
            corpus=self.corpus,
            creator=self.user,
            annotation_type=SPAN_LABEL,
            raw_text="Exhibit",
            json={"start": 0, "end": 7},
        )
        CorpusReference.objects.create(
            corpus=self.corpus,
            source_annotation=mention,
            creator=self.user,
            target_document=target,
            reference_type=C.REF_DOCUMENT,
            resolution_status=C.STATUS_RESOLVED,
        )
        writer = EnrichmentWriter(corpus=self.corpus, creator_id=self.user.pk)
        writer.reconcile_document_graph()
        self.assertEqual(
            DocumentRelationship.objects.filter(corpus=self.corpus).count(), 1
        )
        self.import_text(self.corpus, "/filing.txt", "A version without that citation.")
        writer.reconcile_document_graph()
        self.assertFalse(
            DocumentRelationship.objects.filter(corpus=self.corpus).exists()
        )
        graph = GovernanceGraphService.build(self.user, self.corpus.pk, node_cap=100)
        assert graph is not None
        self.assertEqual(graph["edge_count"], 0)
        self.assertEqual(CorpusReference.objects.filter(corpus=self.corpus).count(), 1)
