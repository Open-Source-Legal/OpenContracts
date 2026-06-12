"""Validate every fully-literal gql document in frontend/src against the
GraphQL spec rules plus the project's hardening rules.

Why this exists: the served endpoint's ``validation_rules`` once REPLACED
graphql-core's spec rule set (graphql-core semantics for an explicit rules
list), silently disabling unknown-argument/field and variable-type
validation — invalid frontend documents shipped and "worked" with their
bogus parts ignored. This sweep enumerates them.

Usage (inside the django container, from the repo root):

    docker compose -f local.yml run --rm django python scripts/validate_frontend_graphql.py

Interpolated templates (``${...}``) and fragment-only documents are skipped:
the former cannot be parsed standalone, the latter are interpolated into
full operations client-side and never reach the server alone (validating
them standalone yields spurious NoUnusedFragments errors).

The same sweep runs in CI via
``opencontractserver/tests/architecture/test_frontend_graphql_documents.py``.
"""

import pathlib
import re
import sys


def iter_documents(root: pathlib.Path):
    """Yield ``(path, document_text)`` for fully-literal gql documents."""
    gql_re = re.compile(r"gql`([^`]*)`", re.DOTALL)
    for path in sorted(root.rglob("*.ts*")):
        if ".test." in path.name or "__tests__" in path.parts:
            continue  # test fixtures may query deliberately-fake fields
        try:
            text = path.read_text()
        except Exception:
            continue
        for m in gql_re.finditer(text):
            doc_text = m.group(1)
            if "${" in doc_text:
                continue
            yield path, doc_text


def strip_client_fields(doc):
    """Remove ``@client``-directed selections, as Apollo does before sending.

    Client-only fields (local state) never reach the server, so validating
    them against the server schema produces spurious unknown-field errors.
    """
    from graphql.language import visit
    from graphql.language.visitor import REMOVE, Visitor

    class _StripClient(Visitor):
        def enter_field(self, node, *_args):
            if any(d.name.value == "client" for d in node.directives or ()):
                return REMOVE
            return None

    return visit(doc, _StripClient())


def validate_documents(root: pathlib.Path):
    """Return ``(checked, failures)`` where failures are (path, name, errors)."""
    from graphql import parse, validate
    from graphql.validation import specified_rules

    from config.graphql.schema import schema
    from config.graphql.security import DepthLimitValidationRule

    rules = [*specified_rules, DepthLimitValidationRule]

    checked = 0
    failures = []
    for path, doc_text in iter_documents(root):
        try:
            doc = parse(doc_text)
        except Exception as exc:
            checked += 1
            failures.append((path, "?", [f"parse failure: {exc}"]))
            continue
        if not any(getattr(d, "operation", None) is not None for d in doc.definitions):
            continue  # fragment-only — interpolated client-side
        checked += 1
        doc = strip_client_fields(doc)
        errors = validate(schema.graphql_schema, doc, rules)
        if errors:
            name = re.search(r"(query|mutation|subscription)\s+(\w+)", doc_text)
            failures.append(
                (
                    path,
                    name.group(2) if name else "?",
                    [str(e.message) for e in errors],
                )
            )
    return checked, failures


def main() -> int:
    import django

    django.setup()

    root = pathlib.Path(__file__).resolve().parent.parent / "frontend" / "src"
    checked, failures = validate_documents(root)
    for path, name, errors in failures:
        print(f"INVALID {path.relative_to(root)} :: {name}")
        for e in errors[:4]:
            print(f"   - {e[:160]}")
    print(f"\nchecked={checked} invalid={len(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    import os

    # ``python scripts/x.py`` puts scripts/ on sys.path, not the repo root.
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
    sys.exit(main())
