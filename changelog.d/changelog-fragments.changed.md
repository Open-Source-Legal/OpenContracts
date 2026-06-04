- **Changelog now uses per-PR fragments to eliminate `CHANGELOG.md` merge
  conflicts.** Every PR previously inserted its entry at the top of the single
  `## [Unreleased]` section, so concurrent PRs collided on the same lines
  (the file changed in hundreds of commits per month, perpetually conflicting).
  PRs now add a uniquely-named fragment under `changelog.d/<slug>.<type>.md`
  instead — unique filenames mean two PRs can never touch the same lines, so
  changelog conflicts are structurally impossible. `scripts/collate_changelog.py`
  collates fragments into `CHANGELOG.md` at release time (`--check` / `--preview`
  / `--apply`), a `repo: local` pre-commit hook validates fragment names, and
  `CHANGELOG.md merge=union` in `.gitattributes` is a safety net for direct
  edits. See `changelog.d/README.md`.
