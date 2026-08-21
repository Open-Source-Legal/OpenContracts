- **`require_backend_ci_gate.sh` replaced the required-checks list instead of
  adding to it.** Adding a second required context — which
  `docs/development/test-suite.md` explicitly tells you to do once another
  workflow grows its own gate — would have silently *unrequired*
  `backend-ci-gate`, with no error and a verification print that looked
  correct. It also hardcoded `strict: false` (reverting a maintainer who had
  turned it on) and dropped the `app_id` GitHub pins each check to, widening
  the requirement to any app. The merge now unions contexts, preserves
  `strict` and `app_id`, migrates a legacy `contexts` list, and is idempotent.
  It moved to `.github/scripts/branch_protection_body.py` with a 13-case
  `--self-test`, reachable as `require_backend_ci_gate.sh --self-test`.
  `.github/scripts/**` is now in Backend CI's path filter, so a change to the
  code that decides whether a merge is allowed runs the full suite.
