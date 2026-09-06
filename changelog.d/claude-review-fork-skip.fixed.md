- **`claude-review` reported a red X on every fork PR that no contributor
  could clear.** `.github/workflows/claude-code-review.yml` triggers on
  `pull_request`, but GitHub clamps runs whose head is a fork: the declared
  `id-token: write` is silently dropped and the secret store is withheld
  (`Secret source: None`, `claude_code_oauth_token: ""`). The action failed
  with *"Could not fetch an OIDC token. Did you remember to add `id-token:
  write` to your workflow permissions?"* — an error that accuses the workflow
  file even though the permission is declared on line 43, sending anyone who
  debugs from the message alone to edit code that is already correct
  (run 33611167884, PR #2296). Re-running with "Approve and run" does not
  restore secrets, and `GITHUB_TOKEN` is read-only on fork PRs, so the
  `gh pr comment` the job is asked to make could not have posted either — three
  independent blockers, any one of them fatal. The job now carries
  `if: github.event.pull_request.head.repo.full_name == github.repository`
  and reports **skipped** on forks, which is what actually happened. Dependabot
  is unaffected: its branches live in this repository, so the guard passes and
  the OIDC exchange works as before (run 33788653880). The comment above the
  guard records why `pull_request_target` is not the fix — it would put the
  OAuth secret and a write-capable token in a job checking out untrusted head
  code — and points at the `@claude` mention path in
  `.github/workflows/claude.yml` for reviewing a fork PR on demand.
