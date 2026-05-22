"""Structural-contract tests for the Phase 3 service packages.

Phase 3 of the service-layer centralization roadmap (issue #1717) split the
former ``annotations/query_optimizer.py`` monolith and relocated the two
misfiled optimizer classes into per-app ``services/`` packages. These tests
pin the *structural* contract of that relocation — they are deliberately not
behavioural: the behavioural regression gate is the unchanged optimizer test
suite (``test_query_optimizer_methods.py``, ``test_metadata_query_optimizer.py``,
``test_version_aware_query_optimizer.py``, ``test_query_optimizer_structural_sets.py``,
and friends), whose only edit was the mechanical import/class-name repoint.

See ``docs/refactor_plans/2026-05-19-service-layer-centralization-design.md``.
"""

from __future__ import annotations

import importlib

from django.test import SimpleTestCase

from opencontractserver.shared.services import BaseService


class Phase3ServiceRelocationTests(SimpleTestCase):
    """SCENARIO: the five relocated services live in per-app ``services/``
    packages and inherit the shared ``BaseService`` foundation.

    BUSINESS RULE: a user-context caller imports a service from its app's
    ``services`` package — ``from opencontractserver.<app>.services import
    <Name>Service`` — and never from a ``query_optimizer`` module.
    """

    def test_annotation_services_exported_from_package(self):
        from opencontractserver.annotations.services import (
            AnnotationService,
            RelationshipService,
        )

        self.assertTrue(issubclass(AnnotationService, BaseService))
        self.assertTrue(issubclass(RelationshipService, BaseService))

    def test_analysis_service_exported_from_package(self):
        from opencontractserver.analyzer.services import AnalysisService

        self.assertTrue(issubclass(AnalysisService, BaseService))

    def test_extract_services_exported_from_package(self):
        from opencontractserver.extracts.services import (
            ExtractService,
            MetadataService,
        )

        self.assertTrue(issubclass(ExtractService, BaseService))
        self.assertTrue(issubclass(MetadataService, BaseService))

    def test_former_query_optimizer_modules_are_gone(self):
        """No re-export shim: the former modules must not import.

        Design-doc §9 success criterion — ``query optimizer`` is no longer a
        public API concept for these five classes.
        """
        for dotted in (
            "opencontractserver.annotations.query_optimizer",
            "opencontractserver.extracts.query_optimizer",
        ):
            with self.assertRaises(ModuleNotFoundError):
                importlib.import_module(dotted)

    def test_annotation_service_public_surface(self):
        from opencontractserver.annotations.services import AnnotationService

        for method in (
            "get_document_annotations",
            "get_annotations_for_path",
            "get_corpus_annotations",
            "get_extract_annotation_summary",
        ):
            self.assertTrue(
                callable(getattr(AnnotationService, method, None)),
                f"AnnotationService.{method} is missing",
            )

    def test_relationship_service_public_surface(self):
        from opencontractserver.annotations.services import RelationshipService

        for method in ("get_document_relationships", "get_relationship_summary"):
            self.assertTrue(
                callable(getattr(RelationshipService, method, None)),
                f"RelationshipService.{method} is missing",
            )

    def test_analysis_service_public_surface(self):
        from opencontractserver.analyzer.services import AnalysisService

        for method in (
            "check_analysis_permission",
            "get_visible_analyses",
            "get_analysis_annotations",
        ):
            self.assertTrue(
                callable(getattr(AnalysisService, method, None)),
                f"AnalysisService.{method} is missing",
            )

    def test_extract_service_public_surface(self):
        from opencontractserver.extracts.services import ExtractService

        for method in (
            "check_extract_permission",
            "get_visible_extracts",
            "get_extract_datacells",
        ):
            self.assertTrue(
                callable(getattr(ExtractService, method, None)),
                f"ExtractService.{method} is missing",
            )

    def test_metadata_service_public_surface(self):
        from opencontractserver.extracts.services import MetadataService

        for method in (
            "get_corpus_metadata_columns",
            "get_document_metadata",
            "get_documents_metadata_batch",
            "get_metadata_completion_status",
            "check_metadata_mutation_permission",
            "validate_metadata_column",
        ):
            self.assertTrue(
                callable(getattr(MetadataService, method, None)),
                f"MetadataService.{method} is missing",
            )

    def test_package_init_and_submodule_resolve_to_same_class(self):
        """The package ``__init__`` re-export and the concrete submodule
        agree — callers may use either import path.
        """
        from opencontractserver.annotations.services import (
            AnnotationService as PkgAnnotation,
        )
        from opencontractserver.annotations.services.annotation_service import (
            AnnotationService as ModAnnotation,
        )
        from opencontractserver.extracts.services import MetadataService as PkgMetadata
        from opencontractserver.extracts.services.metadata import (
            MetadataService as ModMetadata,
        )

        self.assertIs(PkgAnnotation, ModAnnotation)
        self.assertIs(PkgMetadata, ModMetadata)
