## Summary

<!-- What does this PR do, and why? -->

## Changes

<!-- Bullet list of the concrete changes. Reference specific files/functions where useful. -->

## Test plan

<!-- How did you verify this? Include the commands you ran and their result. -->

## Checklist

- [ ] Tests pass locally for any code this PR touches
- [ ] `pre-commit run --all-files` passes (black, isort, flake8, prettier)
- [ ] TypeScript compiles cleanly (`yarn build` or `yarn lint`), if frontend code changed
- [ ] A changelog fragment was added under `changelog.d/` (see `changelog.d/README.md`) for user-facing changes, bug fixes, new dependencies, or migrations
- [ ] Any new dependency was checked against what's already in the stack — a new SDK/library needs a reason it isn't already covered (e.g. by an existing `pydantic-ai-slim` extra)

## Contributor License Agreement

By submitting this pull request, you agree to license your contribution
under the project's [Contributor License Agreement](../CLA.md). First-time
contributors: a bot will comment on this PR asking you to confirm by
replying with a short sign phrase — no separate signup required.
