"""
Tests for OC_URL clickable hyperlink annotations.

Covers:
* ``Annotation.link_url`` validation (model-level): blocks ``javascript:``,
  ``data:`` and other unsafe schemes; accepts http(s):// and site-relative
  paths; empty/None is a no-op.
* GraphQL ``addUrlAnnotation`` mutation: creates an OC_URL label on first
  use, anchors highlighted text, persists ``link_url``, enforces visibility
  on parent corpus/document, and rejects unsafe URLs with a structured error.
* GraphQL ``addAnnotation`` mutation: optional ``linkUrl`` argument validates
  the scheme and is persisted on the resulting annotation.
* GraphQL ``updateAnnotation`` mutation: allows clearing ``link_url`` with an
  empty string and rejects unsafe schemes.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from graphene.test import Client
from graphql_relay import to_global_id

from config.graphql.schema import schema
from opencontractserver.annotations.models import (
    TOKEN_LABEL,
    Annotation,
    AnnotationLabel,
    validate_link_url,
)
from opencontractserver.constants.annotations import OC_URL_LABEL
from opencontractserver.corpuses.models import Corpus
from opencontractserver.documents.models import Document
from opencontractserver.types.enums import PermissionTypes
from opencontractserver.utils.permissioning import set_permissions_for_obj_to_user

User = get_user_model()


ADD_URL_ANNOTATION_MUTATION = """
    mutation AddUrlAnnotation(
        $corpusId: String!
        $documentId: String!
        $page: Int!
        $rawText: String!
        $json: GenericScalar!
        $annotationType: LabelType!
        $linkUrl: String!
    ) {
        addUrlAnnotation(
            corpusId: $corpusId
            documentId: $documentId
            page: $page
            rawText: $rawText
            json: $json
            annotationType: $annotationType
            linkUrl: $linkUrl
        ) {
            ok
            message
            annotation {
                id
                rawText
                linkUrl
                annotationLabel {
                    text
                }
            }
        }
    }
"""


ADD_ANNOTATION_WITH_LINK_URL_MUTATION = """
    mutation AddAnnotation(
        $corpusId: String!
        $documentId: String!
        $annotationLabelId: String!
        $page: Int!
        $rawText: String!
        $json: GenericScalar!
        $annotationType: LabelType!
        $linkUrl: String
    ) {
        addAnnotation(
            corpusId: $corpusId
            documentId: $documentId
            annotationLabelId: $annotationLabelId
            page: $page
            rawText: $rawText
            json: $json
            annotationType: $annotationType
            linkUrl: $linkUrl
        ) {
            ok
            message
            annotation {
                id
                linkUrl
            }
        }
    }
"""


UPDATE_ANNOTATION_MUTATION = """
    mutation UpdateAnnotation(
        $id: String!
        $linkUrl: String
    ) {
        updateAnnotation(
            id: $id
            linkUrl: $linkUrl
        ) {
            ok
            message
        }
    }
"""


class _MutationContext:
    """Minimal info.context stand-in for graphene.test.Client."""

    def __init__(self, user):
        self.user = user


class ValidateLinkUrlTests(TestCase):
    """Direct coverage of ``validate_link_url`` and ``Annotation.clean()``."""

    def test_empty_string_is_noop(self):
        # Empty / None must return cleanly so the column can stay NULL.
        # ``validate_link_url`` returns None on accept; the assertion below
        # exists purely to fail loudly if a future change makes it raise.
        validate_link_url("")

    def test_http_url_is_allowed(self):
        # Sanity: plain http URL must be accepted (no exception raised).
        validate_link_url("http://example.com")

    def test_https_url_is_allowed(self):
        # Sanity: plain https URL must be accepted (no exception raised).
        validate_link_url("https://example.com/path?x=1")

    def test_site_relative_path_is_allowed(self):
        # Site-relative URLs allow internal SPA navigation (e.g. /corpus/foo).
        validate_link_url("/corpus/foo")

    def test_javascript_scheme_is_rejected(self):
        with self.assertRaises(ValidationError) as cm:
            validate_link_url("javascript:alert(1)")
        # Error must mention the offending field for clean GraphQL surfacing.
        self.assertIn("link_url", cm.exception.message_dict)

    def test_data_scheme_is_rejected(self):
        with self.assertRaises(ValidationError):
            validate_link_url("data:text/html,<script>alert(1)</script>")

    def test_file_scheme_is_rejected(self):
        # file:// references would let an attacker probe local resources.
        with self.assertRaises(ValidationError):
            validate_link_url("file:///etc/passwd")

    def test_ftp_scheme_is_rejected(self):
        # Only http(s) + site-relative are in the allow-list — ftp is out.
        with self.assertRaises(ValidationError):
            validate_link_url("ftp://example.com/file")

    def test_case_insensitive_scheme(self):
        # Schemes are compared lowercased, so casing must not bypass the check.
        validate_link_url("HTTPS://example.com")
        with self.assertRaises(ValidationError):
            validate_link_url("JavaScript:alert(1)")

    def test_whitespace_prefix_does_not_bypass(self):
        # ``" javascript:..."`` could trick a naive startswith check if we
        # did not strip; the regex must still reject after normalisation.
        with self.assertRaises(ValidationError):
            validate_link_url("   javascript:alert(1)")

    def test_protocol_relative_url_is_rejected(self):
        # ``//evil.com`` starts with ``/`` but browsers resolve it as
        # ``https://evil.com``. The site-relative branch of the allow-list
        # must not let it through — otherwise we ship an open redirect.
        with self.assertRaises(ValidationError):
            validate_link_url("//evil.com")
        with self.assertRaises(ValidationError):
            validate_link_url("//evil.com/path?x=1")
        # Whitespace-prefixed protocol-relative also rejected (post-strip
        # the leading ``//`` is preserved, so the rejection still fires).
        with self.assertRaises(ValidationError):
            validate_link_url("  //evil.com")

    def test_annotation_clean_rejects_unsafe_link_url(self):
        # The model's ``clean()`` must invoke ``validate_link_url`` so
        # callers that go through full_clean() are protected.
        user = User.objects.create_user(username="u1", password="x")
        doc = Document.objects.create(
            title="doc", creator=user, is_public=False, backend_lock=False
        )
        label = AnnotationLabel.objects.create(
            text="L", label_type=TOKEN_LABEL, creator=user
        )
        ann = Annotation(
            page=0,
            raw_text="hello",
            document=doc,
            annotation_label=label,
            creator=user,
            annotation_type=TOKEN_LABEL,
            link_url="javascript:alert(1)",
            json={"0": {"bounds": {}, "rawText": "hello", "tokensJsons": []}},
        )
        with self.assertRaises(ValidationError):
            ann.clean()

    def test_annotation_save_rejects_unsafe_link_url(self):
        # The override on ``save()`` runs even when the JSON-validation flag
        # is disabled — this is the last line of defence before persistence.
        user = User.objects.create_user(username="u2", password="x")
        doc = Document.objects.create(
            title="doc", creator=user, is_public=False, backend_lock=False
        )
        label = AnnotationLabel.objects.create(
            text="L", label_type=TOKEN_LABEL, creator=user
        )
        ann = Annotation(
            page=0,
            raw_text="hello",
            document=doc,
            annotation_label=label,
            creator=user,
            annotation_type=TOKEN_LABEL,
            link_url="javascript:alert(1)",
            json={"0": {"bounds": {}, "rawText": "hello", "tokensJsons": []}},
        )
        with self.assertRaises(ValidationError):
            ann.save()

    def test_whitespace_only_link_url_collapses_to_none(self):
        # ``"   "`` is truthy as a string. Without explicit normalisation
        # ``save()`` would persist the whitespace verbatim, leaving the
        # column with garbage. Both ``clean()`` and ``save()`` collapse
        # whitespace-only to None so the column stays NULL.
        user = User.objects.create_user(username="u3", password="x")
        doc = Document.objects.create(
            title="doc", creator=user, is_public=False, backend_lock=False
        )
        label = AnnotationLabel.objects.create(
            text="L", label_type=TOKEN_LABEL, creator=user
        )
        ann = Annotation(
            page=0,
            raw_text="hello",
            document=doc,
            annotation_label=label,
            creator=user,
            annotation_type=TOKEN_LABEL,
            link_url="   ",
            json={"0": {"bounds": {}, "rawText": "hello", "tokensJsons": []}},
        )
        ann.save()
        ann.refresh_from_db()
        self.assertIsNone(ann.link_url)

    def test_save_validates_link_url_when_json_validation_disabled(self):
        # ``save()`` has an ``elif`` branch that runs when
        # ``VALIDATE_ANNOTATION_JSON`` is False: ``clean()`` was skipped
        # so the override must validate ``link_url`` itself, otherwise an
        # unsafe scheme would slip past the last line of defence whenever
        # JSON validation is disabled in production.
        from django.test import override_settings

        user = User.objects.create_user(username="u4", password="x")
        doc = Document.objects.create(
            title="doc", creator=user, is_public=False, backend_lock=False
        )
        label = AnnotationLabel.objects.create(
            text="L", label_type=TOKEN_LABEL, creator=user
        )
        ann = Annotation(
            page=0,
            raw_text="hello",
            document=doc,
            annotation_label=label,
            creator=user,
            annotation_type=TOKEN_LABEL,
            link_url="javascript:alert(1)",
            json={"0": {"bounds": {}, "rawText": "hello", "tokensJsons": []}},
        )
        # DEBUG=False + VALIDATE_ANNOTATION_JSON not set -> skips clean(),
        # forcing the save-side validation branch to fire.
        with override_settings(DEBUG=False, VALIDATE_ANNOTATION_JSON=False):
            with self.assertRaises(ValidationError):
                ann.save()

    def test_save_normalises_link_url_whitespace_when_json_validation_disabled(self):
        # Companion to the test above: the save-side ``elif`` branch must
        # also strip whitespace and collapse whitespace-only to ``None``
        # so the column stays canonical regardless of which path
        # persisted it.
        from django.test import override_settings

        user = User.objects.create_user(username="u5", password="x")
        doc = Document.objects.create(
            title="doc", creator=user, is_public=False, backend_lock=False
        )
        label = AnnotationLabel.objects.create(
            text="L", label_type=TOKEN_LABEL, creator=user
        )
        ann = Annotation(
            page=0,
            raw_text="hello",
            document=doc,
            annotation_label=label,
            creator=user,
            annotation_type=TOKEN_LABEL,
            link_url="   ",
            json={"0": {"bounds": {}, "rawText": "hello", "tokensJsons": []}},
        )
        with override_settings(DEBUG=False, VALIDATE_ANNOTATION_JSON=False):
            ann.save()
        ann.refresh_from_db()
        self.assertIsNone(ann.link_url)


class AddUrlAnnotationMutationTests(TestCase):
    """Coverage of the ``addUrlAnnotation`` GraphQL mutation."""

    def setUp(self):
        self.owner = User.objects.create_user(username="owner", password="x")
        self.outsider = User.objects.create_user(username="outsider", password="x")

        original_doc = Document.objects.create(
            title="Owner Doc",
            creator=self.owner,
            is_public=False,
            backend_lock=False,
        )
        self.corpus = Corpus.objects.create(
            title="Owner Corpus", creator=self.owner, is_public=False
        )
        # add_document returns the corpus-scoped copy that the frontend
        # actually annotates against.
        self.document, _, _ = self.corpus.add_document(
            document=original_doc, user=self.owner
        )

        set_permissions_for_obj_to_user(
            self.owner, self.document, [PermissionTypes.CRUD]
        )
        set_permissions_for_obj_to_user(self.owner, self.corpus, [PermissionTypes.CRUD])

        self.client = Client(schema)

    def _execute(self, *, user, link_url, raw_text="link text"):
        return self.client.execute(
            ADD_URL_ANNOTATION_MUTATION,
            variables={
                "corpusId": to_global_id("CorpusType", self.corpus.pk),
                "documentId": to_global_id("DocumentType", self.document.pk),
                "page": 0,
                "rawText": raw_text,
                "json": {
                    "0": {
                        "bounds": {},
                        "rawText": raw_text,
                        "tokensJsons": [],
                    }
                },
                "annotationType": "TOKEN_LABEL",
                "linkUrl": link_url,
            },
            context_value=_MutationContext(user),
        )

    def test_owner_creates_url_annotation_and_label(self):
        # Happy path: owner creates a URL annotation. The OC_URL label is
        # created on first use and the resulting annotation carries the
        # supplied link_url.
        before_labels = AnnotationLabel.objects.filter(text=OC_URL_LABEL).count()
        result = self._execute(user=self.owner, link_url="https://example.com/a")
        self.assertNotIn("errors", result, msg=result.get("errors"))

        payload = result["data"]["addUrlAnnotation"]
        self.assertTrue(payload["ok"], msg=payload.get("message"))
        self.assertIsNotNone(payload["annotation"])
        self.assertEqual(payload["annotation"]["linkUrl"], "https://example.com/a")
        self.assertEqual(payload["annotation"]["annotationLabel"]["text"], OC_URL_LABEL)

        # The OC_URL label exists exactly once — the mutation is idempotent
        # at the label level so repeated calls reuse the same label row.
        self.assertEqual(
            AnnotationLabel.objects.filter(text=OC_URL_LABEL).count(),
            before_labels + 1,
        )

    def test_second_url_annotation_reuses_oc_url_label(self):
        # Idempotency: creating a second URL annotation must NOT create a
        # second OC_URL label — ensure_label_and_labelset is idempotent.
        self._execute(user=self.owner, link_url="https://example.com/a")
        self._execute(user=self.owner, link_url="https://example.com/b")
        self.assertEqual(AnnotationLabel.objects.filter(text=OC_URL_LABEL).count(), 1)

    def test_rejects_javascript_scheme(self):
        # Defence in depth: the GraphQL layer must refuse unsafe schemes
        # before persistence (the model layer is the last line of defence).
        before = Annotation.objects.count()
        result = self._execute(user=self.owner, link_url="javascript:alert(1)")
        payload = result["data"]["addUrlAnnotation"]
        self.assertFalse(payload["ok"])
        self.assertIsNone(payload["annotation"])
        # No row written.
        self.assertEqual(Annotation.objects.count(), before)

    def test_rejects_data_scheme(self):
        result = self._execute(
            user=self.owner, link_url="data:text/html,<script>alert(1)</script>"
        )
        self.assertFalse(result["data"]["addUrlAnnotation"]["ok"])

    def test_outsider_cannot_create_url_annotation(self):
        # IDOR coverage: an authenticated user with no permissions on
        # the parent corpus/document gets the uniform permission error
        # and no annotation is written.
        before = Annotation.objects.count()
        result = self._execute(user=self.outsider, link_url="https://example.com")
        payload = result["data"]["addUrlAnnotation"]
        self.assertFalse(payload["ok"])
        self.assertIsNone(payload["annotation"])
        self.assertEqual(Annotation.objects.count(), before)

    def test_site_relative_url_accepted(self):
        # Confirms the allow-list lets through internal SPA links.
        result = self._execute(user=self.owner, link_url="/corpus/foo/doc/bar")
        payload = result["data"]["addUrlAnnotation"]
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["annotation"]["linkUrl"], "/corpus/foo/doc/bar")


class AddAnnotationLinkUrlTests(TestCase):
    """Coverage of the optional ``link_url`` argument on ``addAnnotation``."""

    def setUp(self):
        self.owner = User.objects.create_user(username="owner", password="x")
        original_doc = Document.objects.create(
            title="Owner Doc",
            creator=self.owner,
            is_public=False,
            backend_lock=False,
        )
        self.corpus = Corpus.objects.create(
            title="Owner Corpus", creator=self.owner, is_public=False
        )
        self.document, _, _ = self.corpus.add_document(
            document=original_doc, user=self.owner
        )
        self.label = AnnotationLabel.objects.create(
            text="Custom", label_type=TOKEN_LABEL, creator=self.owner
        )
        set_permissions_for_obj_to_user(
            self.owner, self.document, [PermissionTypes.CRUD]
        )
        set_permissions_for_obj_to_user(self.owner, self.corpus, [PermissionTypes.CRUD])
        self.client = Client(schema)

    def _execute(self, *, link_url, user=None):
        return self.client.execute(
            ADD_ANNOTATION_WITH_LINK_URL_MUTATION,
            variables={
                "corpusId": to_global_id("CorpusType", self.corpus.pk),
                "documentId": to_global_id("DocumentType", self.document.pk),
                "annotationLabelId": to_global_id("AnnotationLabelType", self.label.pk),
                "page": 0,
                "rawText": "anchor",
                "json": {"0": {"bounds": {}, "rawText": "anchor", "tokensJsons": []}},
                "annotationType": "TOKEN_LABEL",
                "linkUrl": link_url,
            },
            context_value=_MutationContext(user or self.owner),
        )

    def test_add_annotation_persists_link_url(self):
        result = self._execute(link_url="https://example.com")
        payload = result["data"]["addAnnotation"]
        self.assertTrue(payload["ok"], msg=payload.get("message"))
        self.assertEqual(payload["annotation"]["linkUrl"], "https://example.com")

    def test_add_annotation_rejects_unsafe_link_url(self):
        # Validation happens BEFORE the parents are resolved; no DB write.
        before = Annotation.objects.count()
        result = self._execute(link_url="javascript:alert(1)")
        payload = result["data"]["addAnnotation"]
        self.assertFalse(payload["ok"])
        self.assertIsNone(payload["annotation"])
        self.assertEqual(Annotation.objects.count(), before)

    def test_add_annotation_without_link_url_is_ok(self):
        # Backward compatibility: omitting link_url must still create an
        # annotation with link_url=NULL.
        result = self._execute(link_url=None)
        payload = result["data"]["addAnnotation"]
        self.assertTrue(payload["ok"], msg=payload.get("message"))
        self.assertIsNone(payload["annotation"]["linkUrl"])


class UpdateAnnotationLinkUrlTests(TestCase):
    """Coverage of ``link_url`` handling in ``updateAnnotation``."""

    def setUp(self):
        self.owner = User.objects.create_user(username="owner", password="x")
        original_doc = Document.objects.create(
            title="Owner Doc",
            creator=self.owner,
            is_public=False,
            backend_lock=False,
        )
        self.corpus = Corpus.objects.create(
            title="Owner Corpus", creator=self.owner, is_public=False
        )
        self.document, _, _ = self.corpus.add_document(
            document=original_doc, user=self.owner
        )
        self.label = AnnotationLabel.objects.create(
            text="Custom", label_type=TOKEN_LABEL, creator=self.owner
        )
        set_permissions_for_obj_to_user(
            self.owner, self.document, [PermissionTypes.CRUD]
        )
        set_permissions_for_obj_to_user(self.owner, self.corpus, [PermissionTypes.CRUD])

        self.annotation = Annotation.objects.create(
            page=0,
            raw_text="anchor",
            document=self.document,
            corpus=self.corpus,
            annotation_label=self.label,
            creator=self.owner,
            annotation_type=TOKEN_LABEL,
            link_url="https://example.com/old",
            json={"0": {"bounds": {}, "rawText": "anchor", "tokensJsons": []}},
        )
        set_permissions_for_obj_to_user(
            self.owner, self.annotation, [PermissionTypes.CRUD]
        )

        self.client = Client(schema)

    def _execute(self, *, link_url):
        return self.client.execute(
            UPDATE_ANNOTATION_MUTATION,
            variables={
                "id": to_global_id("AnnotationType", self.annotation.pk),
                "linkUrl": link_url,
            },
            context_value=_MutationContext(self.owner),
        )

    def test_update_sets_new_link_url(self):
        result = self._execute(link_url="https://example.com/new")
        self.assertNotIn("errors", result, msg=result.get("errors"))
        self.annotation.refresh_from_db()
        self.assertEqual(self.annotation.link_url, "https://example.com/new")

    def test_update_with_empty_string_clears_link_url(self):
        # The serializer normalises "" → None so the column ends up NULL.
        result = self._execute(link_url="")
        self.assertNotIn("errors", result, msg=result.get("errors"))
        self.annotation.refresh_from_db()
        self.assertIsNone(self.annotation.link_url)

    def test_update_rejects_unsafe_link_url(self):
        # serializer.validate_link_url calls validate_link_url which raises
        # ValidationError; the original value must remain.
        before = self.annotation.link_url
        result = self._execute(link_url="javascript:alert(1)")

        # The row must NOT have been updated regardless of how the rejection
        # surfaced (DRFMutation ok=False vs GraphQL-level error).
        self.annotation.refresh_from_db()
        self.assertEqual(self.annotation.link_url, before)

        # And the mutation must NOT report ok=True. Default to True in the
        # ``.get`` so a missing/absent ``updateAnnotation`` payload still
        # fails the assertion — silent absence is not success.
        payload = (result.get("data") or {}).get("updateAnnotation") or {}
        self.assertFalse(payload.get("ok", True))


class LinkUrlExporterTests(TestCase):
    """Coverage of ``link_url`` passthrough in the ETL exporters.

    Two independent code paths emit ``link_url`` into the export schema:
      * ``utils.etl.build_document_export`` (per-document V1 export, fork)
      * ``utils.export_v2.package_structural_annotation_set`` (structural
        sets in V2 export, indirectly via test_corpus_export_import_v2)

    Both branches are guarded by ``if annot.link_url:``. Without a test
    that uses an annotation with ``link_url`` set, the *inside* of the
    ``if`` block stays unhit and codecov flags those lines as missed
    patches.
    """

    def setUp(self):
        self.user = User.objects.create_user(username="exporter", password="x")
        self.label = AnnotationLabel.objects.create(
            text="Anchor", label_type=TOKEN_LABEL, creator=self.user
        )
        self.corpus = Corpus.objects.create(
            title="Exporter Corpus", creator=self.user, is_public=False
        )
        self.document = Document.objects.create(
            title="Exporter Doc",
            creator=self.user,
            is_public=False,
            backend_lock=False,
            page_count=1,
            file_type="text/plain",
        )

    def test_build_document_export_emits_link_url(self):
        """``etl.build_document_export`` must propagate link_url.

        The branch ``if annot.link_url: annot_export["link_url"] = ...`` is
        the contract for V1 export / corpus fork. Without it, OC_URL
        annotations silently lose their click targets on round-trip.
        """
        from opencontractserver.types.enums import AnnotationFilterMode
        from opencontractserver.utils.etl import (
            build_document_export,
            build_label_lookups,
        )

        Annotation.objects.create(
            page=0,
            raw_text="click here",
            document=self.document,
            corpus=self.corpus,
            annotation_label=self.label,
            creator=self.user,
            annotation_type=TOKEN_LABEL,
            link_url="https://example.com/exported",
            json={"0": {"bounds": {}, "rawText": "click here", "tokensJsons": []}},
        )

        # Pre-build label lookups (mirrors what export_tasks does before
        # invoking build_document_export per doc).
        lookups = build_label_lookups(
            corpus_id=self.corpus.id,
            analysis_ids=None,
            annotation_filter_mode=AnnotationFilterMode.CORPUS_LABELSET_PLUS_ANALYSES,
        )
        # Ensure our text label is wired into lookups so the annotation
        # passes the filter in build_document_export. build_label_lookups
        # pulls labels via the corpus labelset + referenced labels, so add
        # the label explicitly to the labelset for completeness.
        from opencontractserver.annotations.models import LabelSet

        labelset = LabelSet.objects.create(title="LS", creator=self.user)
        labelset.annotation_labels.add(self.label)
        self.corpus.label_set = labelset
        self.corpus.save()
        lookups = build_label_lookups(
            corpus_id=self.corpus.id,
            analysis_ids=None,
            annotation_filter_mode=AnnotationFilterMode.CORPUS_LABELSET_PLUS_ANALYSES,
        )

        (
            doc_name,
            base64_file,
            doc_export_data,
            text_lbls,
            doc_lbls,
        ) = build_document_export(
            label_lookups=lookups,
            doc_id=self.document.id,
            corpus_id=self.corpus.id,
            analysis_ids=None,
            annotation_filter_mode=AnnotationFilterMode.CORPUS_LABELSET_PLUS_ANALYSES,
        )

        # Find the annotation we wrote — it must carry the link_url in
        # the export payload.
        link_urls = [
            a.get("link_url")
            for a in doc_export_data.get("labelled_text", [])
            if a.get("link_url")
        ]
        self.assertIn("https://example.com/exported", link_urls)
