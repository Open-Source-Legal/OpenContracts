- **Graduated the `tests.test_admin*` chunk out of the mypy baseline
  (#1738).** Removed the two `[mypy-opencontractserver.tests.test_admin]`
  and `[mypy-opencontractserver.tests.test_admin_auth]` `ignore_errors`
  blocks and pruned the corresponding 122 lines from
  `docs/typing/mypy_baseline.txt` (2942 → 2820). Fixes follow the established
  patterns from earlier #1738 graduation passes:
  - `test_admin.py` (6 errors): swapped the module-level `User =
    get_user_model()` alias for the concrete
    `from opencontractserver.users.models import User` import (mypy rejects a
    `get_user_model()` variable as a type annotation); widened two helper
    signatures from `obj: object` to `obj: Model` so `_meta` / `pk` resolve;
    added `# type: ignore[arg-type]` on `CorpusAdmin(Corpus, None)` (the
    Django admin's `ModelAdmin` second-arg `AdminSite` is genuinely optional
    at runtime but typed as required) and `# type: ignore[method-assign]` on
    the `Mock()` reassignment of `message_user` (intentional test isolation).
  - `test_admin_auth.py` (116 errors): same `get_user_model()` → direct
    import swap, plus class-level annotations for the seven `TestCase`
    classes that store `User` instances on `setUpTestData(cls)` —
    `TestAdminClaimsSync.user`, `TestAuth0SuperuserAllowlist.user`,
    `TestAuth0AdminBackend.{staff_user, non_staff_user, inactive_staff,
    superuser}`, `TestAdminLoginView.{staff_user, regular_user}`,
    `TestAdminLogoutView.staff_user`, `TestGetUserByPayloadWithClaimSync.user`,
    `TestAdminLoginRateLimit.staff_user`. 17 `# type: ignore[attr-defined]`
    on `response.url` redirects (django-stubs' `_MonkeyPatchedWSGIResponse`
    doesn't expose `.url` even though Django's test client always sets it on
    302s).
  No production code changed. The full project surface
  (`mypy --config-file mypy.ini opencontractserver config`) stays clean under
  both the pre-commit pin (`mypy==2.0.0`) and CI's pin (`mypy==2.1.0`).
