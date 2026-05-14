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
        # GraphQL surface: DRFMutation returns ok=False on validation error.
        # The exact key path is mutation-specific; what matters is the row
        # was NOT updated.
        self.annotation.refresh_from_db()
        self.assertEqual(self.annotation.link_url, before)
        # The mutation should NOT have set ok=True
        if "data" in result and result["data"]:
            payload = result["data"].get("updateAnnotation") or {}
            self.assertFalse(payload.get("ok", False))
