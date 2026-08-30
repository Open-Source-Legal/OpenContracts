- **Added `backend-ci-gate`, a Backend CI check that branch protection can
  actually require.** `main` has no `required_status_checks` object at all, so
  nothing gates a merge on CI having run — PR #2262 merged with Backend CI
  never having run on its head at all, and the push that merged it then failed
  its linter, skipping `pytest` entirely. Requiring the `pytest` job is not the
  fix: GitHub reports a job skipped by its own `if:` as **Success** to branch
  protection, so a red linter (which skips `pytest`) still reads green —
  PRs #2260, #2264 and #2265 sit in exactly that state. And requiring any job
  in this workflow while its `pull_request` trigger carried
  `paths-ignore: [docs/**]` would have left docs-only PRs permanently Pending,
  since a workflow skipped by path filtering never reports at all. The new
  `gate` job always runs and inspects the other jobs' results itself,
  distinguishing "skipped because this PR touches no backend code" from
  "skipped because something upstream broke". Its decision table lives in
  `.github/scripts/backend_ci_gate.sh` and is self-tested (`--self-test`) on
  every run; `.github/scripts/require_backend_ci_gate.sh` applies the branch
  protection without clobbering the rest of the object.
