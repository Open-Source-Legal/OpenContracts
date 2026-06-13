"""Every shipped frontend GraphQL document must pass spec validation.

With the served endpoint's validation rules now including the full GraphQL
spec set (see ``config/graphql/schema.py``), an invalid document is no longer
silently tolerated — it hard-fails at request time. This sweep moves that
failure to CI: it extracts every fully-literal ``gql`` template under
``frontend/src`` and validates it against the schema (with Apollo's
``@client`` selections stripped, exactly as the client does before sending).

Shares its implementation with ``scripts/validate_frontend_graphql.py``.
"""

import pathlib
import unittest

from django.test import TestCase

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
_FRONTEND_SRC = _REPO_ROOT / "frontend" / "src"


@unittest.skipUnless(
    _FRONTEND_SRC.is_dir(),
    "frontend/src not present in this checkout (backend-only image)",
)
class FrontendGraphQLDocumentsTest(TestCase):
    def test_all_literal_documents_are_schema_valid(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "validate_frontend_graphql",
            _REPO_ROOT / "scripts" / "validate_frontend_graphql.py",
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        checked, failures = module.validate_documents(_FRONTEND_SRC)
        self.assertGreater(checked, 100, "sweep found suspiciously few documents")
        details = "\n".join(
            f"{path}: {name}: {errors[:2]}" for path, name, errors in failures
        )
        self.assertFalse(
            failures,
            f"{len(failures)} invalid frontend GraphQL document(s):\n{details}",
        )
