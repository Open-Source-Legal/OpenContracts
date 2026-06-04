# Changelog fragments (`changelog.d/`)

**Do not edit `CHANGELOG.md` directly in a PR.** Add a *fragment* here instead.

Every PR that touches `CHANGELOG.md`'s `## [Unreleased]` section edits the same
lines, so concurrent PRs collide constantly. Fragments fix this at the root:
each PR adds its **own uniquely-named file**, so two PRs can never touch the
same lines — merge conflicts on the changelog become structurally impossible.
At release time the fragments are collated into `CHANGELOG.md` and deleted.

## How to add an entry

Create one file per change, named:

```
changelog.d/<slug>.<type>.md
```

- `<slug>` — anything unique. The PR number is ideal (`1901`), or a short
  kebab-case description (`pdf-white-line`). Uniqueness is all that matters.
- `<type>` — one of the [Keep a Changelog](https://keepachangelog.com/) groups
  (case-insensitive): `added`, `changed`, `deprecated`, `removed`, `fixed`,
  `security`.

The file body is the markdown bullet(s) — **the same prose you'd have written
under the section header**, just without the `### Fixed` line itself.

### Example

`changelog.d/1901-pdf-white-line.fixed.md`:

```markdown
- **Fixed white-line artifact in PDF annotation highlights.** When a bounding
  box was hidden, `SelectionLayer` (`frontend/src/components/.../Selection.tsx`)
  still rendered a 1px border, leaving a white seam across the token. ...
```

That's it. No `### Fixed` header inside the file — the type comes from the
filename, and the collation script adds the header.

## Multiple categories in one PR

Add multiple fragments — e.g. `1908-search.added.md` and `1908-search.fixed.md`.

## Previewing / releasing

```bash
# See what the next release section will look like:
python scripts/collate_changelog.py --preview

# Validate fragment names/contents (used by CI / pre-commit):
python scripts/collate_changelog.py --check

# At release time: fold all fragments into CHANGELOG.md's [Unreleased]
# section (grouped by category) and delete the fragment files:
python scripts/collate_changelog.py --apply
```

See `scripts/collate_changelog.py --help` for details.
