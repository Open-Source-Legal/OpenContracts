- **Graduated the `conversation & threading` test domain out of the mypy
  baseline (#1738).** Removed the 7 `[mypy-opencontractserver.tests.test_*]`
  `ignore_errors` blocks for the chat/threads feature:
  `test_conversation_mutations_graphql`, `test_conversation_permissions`,
  `test_conversation_query`, `test_conversation_search`,
  `test_long_conversation_api`, `test_thread_corpus_actions`,
  `test_threading`. Pruned the corresponding 433 lines from
  `docs/typing/mypy_baseline.txt` (3375 → 2942) and fixed the 361 errors that
  actually surface. The baseline had drifted: e.g. `test_conversation_search`
  fell 77 → 23 (its historical `set_permissions_for_obj_to_user` arg-type
  errors no longer reproduce under `django-stubs==6.0.5`), while
  `test_conversation_permissions` grew 86 → 159 after recent edits. Fixes use
  the established patterns — class-level annotations for
  `setUpClass`/`setUpTestData` attributes (the recommended fix from #1479), the
  graphene `self.client` → `self.graphene_client` rename (3 files), and
  `assert ... is not None` narrowing of Optional ORM/embedding returns. The
  three `setUpClass`-heavy files also swapped their module-level
  `User = get_user_model()` alias for the concrete
  `from opencontractserver.users.models import User` import, since mypy rejects
  a `get_user_model()` variable as a type annotation.
- **Declared the `_skip_signals` fixture flag on `BaseOCModel`
  (`opencontractserver/shared/Models.py`).** `_skip_signals` is an out-of-band
  attribute that tests/fixtures and one production path
  (`llms/tools/moderation_tools.py`) set on model instances so the signal
  handlers in `*/signals.py` skip their side effects (notifications, badge
  awards, corpus-action triggers). It was undeclared, which forced a
  `# type: ignore[attr-defined]` in `moderation_tools.py` and produced 26
  `attr-defined` errors in `test_thread_corpus_actions`. Declaring it once as
  `_skip_signals: bool` on the shared base (a type-only bare annotation;
  Django's model metaclass ignores it at runtime, so `hasattr`/`getattr`
  guards still behave identically) removes the existing ignore, clears all 26
  test errors, and future-proofs the other still-baselined tests that use the
  flag (`test_badges`, `test_leaderboard`, `test_notifications`). The full
  project surface (`mypy --config-file mypy.ini opencontractserver config`)
  stays clean under both the pre-commit pin (`mypy==2.0.0`) and CI's pin
  (`mypy==2.1.0`).
