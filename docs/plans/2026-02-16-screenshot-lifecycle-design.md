# Screenshot Lifecycle: Evergreen vs Release-Locked

## Problem

All auto-generated documentation screenshots go to `docs/assets/images/screenshots/auto/` and are overwritten by CI on every PR. This is correct for living docs (README, quickstart) but wrong for release notes — those should capture how the UI looked at that specific release and never change.

## Design

### Two functions, two directories

| Function | Output Directory | CI Behavior | Use Case |
|----------|-----------------|-------------|----------|
| `docScreenshot(page, name, opts?)` | `auto/` | Overwritten every PR | Evergreen docs |
| `releaseScreenshot(page, version, name, opts?)` | `releases/{version}/` | Never touched | Release notes |

### `releaseScreenshot` API

```ts
export async function releaseScreenshot(
  page: Page,
  version: string,    // e.g. "v3.0.0.b3"
  name: string,       // e.g. "landing-page"
  options?: { clip?, fullPage?, element? }
): Promise<void>
```

- **Write-once**: If file already exists, returns immediately (no-op)
- **Version validation**: Must match `v\d+\.\d+\.\d+` with optional suffix
- **Name validation**: Same lowercase-alphanumeric-with-hyphens as docScreenshot
- **Location**: Same file as `docScreenshot` (`frontend/tests/utils/docScreenshot.ts`)

### CI workflow

No changes needed. The existing `screenshots.yml` only `git add`s `auto/` — release directories are naturally ignored.

### Call pattern in tests

Tests call both functions when a screenshot serves dual purposes:

```ts
await docScreenshot(page, "landing--discovery-page--anonymous", { fullPage: true });
await releaseScreenshot(page, "v3.0.0.b3", "landing-page", { fullPage: true });
```

### Markdown references

Release notes use release-locked paths:
```md
![Landing Page](../assets/images/screenshots/releases/v3.0.0.b3/landing-page.png)
```

## Files Modified

1. `frontend/tests/utils/docScreenshot.ts` — add `releaseScreenshot` export
2. 8 test files — add `releaseScreenshot` calls
3. `docs/releases/v3.0.0.b3.md` — update 10 image paths
4. `CLAUDE.md` — document the new function
