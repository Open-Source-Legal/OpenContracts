"""
Unit tests for ``requests_doc_label_annotations``.

This helper drives the focused doc-label prefetch in
``resolve_documents`` (config/graphql/document_queries.py). A regression
here either re-enables the per-document N+1 in
``resolve_doc_annotations_optimized`` (false negative) or applies the
focused prefetch to queries that don't ask for the badge (false positive,
unnecessary JOIN). Both are silent in production, so they need direct
coverage.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

from django.test import SimpleTestCase
from graphql import parse
from graphql.language.ast import FragmentDefinitionNode, OperationDefinitionNode

from config.graphql.custom_resolvers import requests_doc_label_annotations


def _info_for(query: str, variables: dict | None = None) -> SimpleNamespace:
    """
    Build a minimal stand-in for ``graphene.ResolveInfo`` carrying the
    fields ``requests_doc_label_annotations`` actually inspects:
    ``field_nodes``, ``fragments``, and ``variable_values``.
    """
    document = parse(query)
    operation = cast(OperationDefinitionNode, document.definitions[0])
    documents_field = operation.selection_set.selections[0]
    fragments = {
        cast(FragmentDefinitionNode, d).name.value: d
        for d in document.definitions
        if d.kind == "fragment_definition"
    }
    return SimpleNamespace(
        field_nodes=[documents_field],
        fragments=fragments,
        variable_values=variables or {},
    )


class RequestsDocLabelAnnotationsTests(SimpleTestCase):
    def test_returns_true_for_get_documents_with_annotate_doc_labels(self) -> None:
        """The corpus list view (``GET_DOCUMENTS`` with the badge alias)."""
        info = _info_for("""
            query {
              documents {
                edges {
                  node {
                    id
                    doc_label_annotations: docAnnotations(
                      annotationLabel_LabelType: "DOC_TYPE_LABEL"
                    ) {
                      edges { node { id } }
                    }
                  }
                }
              }
            }
            """)
        self.assertTrue(requests_doc_label_annotations(info))

    def test_returns_true_when_label_type_is_a_variable(self) -> None:
        """The argument may be supplied as an operation variable."""
        info = _info_for(
            """
            query ($lt: String!) {
              documents {
                edges {
                  node {
                    docAnnotations(annotationLabel_LabelType: $lt) {
                      edges { node { id } }
                    }
                  }
                }
              }
            }
            """,
            variables={"lt": "DOC_TYPE_LABEL"},
        )
        self.assertTrue(requests_doc_label_annotations(info))

    def test_returns_false_when_doc_annotations_omitted(self) -> None:
        info = _info_for("""
            query {
              documents { edges { node { id title } } }
            }
            """)
        self.assertFalse(requests_doc_label_annotations(info))

    def test_returns_false_for_unrelated_label_type(self) -> None:
        info = _info_for("""
            query {
              documents {
                edges {
                  node {
                    docAnnotations(annotationLabel_LabelType: "TOKEN_LABEL") {
                      edges { node { id } }
                    }
                  }
                }
              }
            }
            """)
        self.assertFalse(requests_doc_label_annotations(info))

    def test_traverses_fragment_spreads(self) -> None:
        """Selection-set walk must follow fragment spreads."""
        info = _info_for("""
            query {
              documents {
                edges {
                  node {
                    ...DocFields
                  }
                }
              }
            }
            fragment DocFields on DocumentType {
              docAnnotations(annotationLabel_LabelType: "DOC_TYPE_LABEL") {
                edges { node { id } }
              }
            }
            """)
        self.assertTrue(requests_doc_label_annotations(info))
