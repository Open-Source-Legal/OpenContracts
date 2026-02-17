# Screenshot Lifecycle Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a `releaseScreenshot` function that writes point-in-time screenshots to `releases/{version}/`, then migrate v3.0.0.b3 release notes to use it.

**Architecture:** Dual-function pattern — `docScreenshot` writes to `auto/` (evergreen, CI-overwritten), `releaseScreenshot` writes to `releases/{version}/` (write-once, never overwritten). Both live in the same utility file.

**Tech Stack:** TypeScript, Playwright, Node.js fs

---

### Task 1: Add `releaseScreenshot` to docScreenshot.ts

**Files:**
- Modify: `frontend/tests/utils/docScreenshot.ts`

**Step 1: Add the `releaseScreenshot` function after the existing `docScreenshot` function**

Add `existsSync` to the fs import, add a `RELEASES_DIR` constant, and add the new function:

```typescript
import { existsSync, mkdirSync } from "fs";

const RELEASES_DIR = resolve(
  __dirname,
  "../../../docs/assets/images/screenshots/releases"
);

export async function releaseScreenshot(
  page: Page,
  version: string,
  name: string,
  options?: {
    clip?: { x: number; y: number; width: number; height: number };
    fullPage?: boolean;
    element?: Locator;
  }
): Promise<void> {
  // Validate version format
  if (!/^v\d+\.\d+\.\d+/.test(version)) {
    throw new Error(
      `releaseScreenshot version "${version}" is invalid. ` +
        `Must start with v{major}.{minor}.{patch} (e.g. "v3.0.0.b3").`
    );
  }

  // Validate name
  if (!/^[a-z0-9]+(-[a-z0-9]+)*$/.test(name)) {
    throw new Error(
      `releaseScreenshot name "${name}" is invalid. ` +
        `Must be lowercase alphanumeric with single-hyphen separators.`
    );
  }

  const versionDir = join(RELEASES_DIR, version);
  const filePath = join(versionDir, `${name}.png`);

  // Write-once: if file already exists, skip capture
  if (existsSync(filePath)) {
    return;
  }

  mkdirSync(versionDir, { recursive: true });

  if (options?.element) {
    await options.element.screenshot({ path: filePath });
  } else {
    await page.screenshot({
      path: filePath,
      fullPage: options?.fullPage ?? false,
      ...(options?.clip ? { clip: options.clip } : {}),
    });
  }
}
```

**Step 2: Run TypeScript compilation to verify**

Run: `cd frontend && npx tsc --noEmit --pretty 2>&1 | head -20`
Expected: No errors related to docScreenshot.ts

**Step 3: Commit**

```bash
git add frontend/tests/utils/docScreenshot.ts
git commit -m "Add releaseScreenshot utility for point-in-time release screenshots"
```

---

### Task 2: Add `releaseScreenshot` calls to all 10 test sites

**Files:**
- Modify: `frontend/tests/landing-components.ct.tsx`
- Modify: `frontend/tests/VersionHistoryPanel.ct.tsx`
- Modify: `frontend/tests/DocumentDiscussionsContent.ct.tsx`
- Modify: `frontend/tests/threads/MessageItem.ct.tsx`
- Modify: `frontend/tests/admin-components.ct.tsx`
- Modify: `frontend/tests/BadgeCelebration.ct.tsx`
- Modify: `frontend/tests/folders/FolderTreeSidebar.ct.tsx`
- Modify: `frontend/tests/user-profile.ct.tsx`
- Modify: `frontend/tests/CorpusTabs.ct.tsx`

Each file needs: `import { releaseScreenshot } from "./utils/docScreenshot"` (adjusted path for nested dirs) added to the existing import, and a `releaseScreenshot` call right after the corresponding `docScreenshot` call.

**Mapping (test file → existing docScreenshot name → release name):**

| Test File | docScreenshot name | releaseScreenshot name |
|---|---|---|
| landing-components.ct.tsx | `landing--discovery-page--anonymous` | `landing-page` |
| landing-components.ct.tsx | `landing--leaderboard--with-data` | `leaderboard` |
| VersionHistoryPanel.ct.tsx | `versioning--history-panel--with-versions` | `version-history` |
| DocumentDiscussionsContent.ct.tsx | `discussions--thread-list--with-threads` | `discussion-thread` |
| threads/MessageItem.ct.tsx | `threads--agent-message--response` | `agent-response` |
| admin-components.ct.tsx | `admin--agent-config--create-modal` | `agent-config` |
| BadgeCelebration.ct.tsx | `badges--celebration-modal--auto-award` | `badge-celebration` |
| folders/FolderTreeSidebar.ct.tsx | `folders--tree-sidebar--nested` | `folder-tree` |
| user-profile.ct.tsx | `users--profile--public` | `user-profile` |
| CorpusTabs.ct.tsx | `corpus--analytics--dashboard` | `analytics` |

All use version `"v3.0.0.b3"` and pass the same options as the corresponding `docScreenshot` call.

**Step 1: Add imports and calls to all 10 test files**

**Step 2: Run all affected tests to verify screenshots are generated**

Run: `cd frontend && yarn test:ct --reporter=list -g "hero section|version metadata|thread list initially|agent message with correct|create agent modal|renders with badge information|nested structure|public user profile|Analytics tab|contributor rows" 2>&1 | tail -30`
Expected: All tests pass, release screenshots created in `docs/assets/images/screenshots/releases/v3.0.0.b3/`

**Step 3: Verify release screenshots exist**

Run: `ls -la docs/assets/images/screenshots/releases/v3.0.0.b3/`
Expected: 10 PNG files

**Step 4: Commit**

```bash
git add frontend/tests/ docs/assets/images/screenshots/releases/
git commit -m "Add v3.0.0.b3 release screenshots to all test sites"
```

---

### Task 3: Update v3.0.0.b3.md image references

**Files:**
- Modify: `docs/releases/v3.0.0.b3.md`

**Step 1: Replace all 10 image paths from `auto/` to `releases/v3.0.0.b3/`**

| Line | Old path | New path |
|------|----------|----------|
| 14 | `../assets/images/screenshots/auto/landing--discovery-page--anonymous.png` | `../assets/images/screenshots/releases/v3.0.0.b3/landing-page.png` |
| 88 | `../assets/images/screenshots/auto/versioning--history-panel--with-versions.png` | `../assets/images/screenshots/releases/v3.0.0.b3/version-history.png` |
| 137 | `../assets/images/screenshots/auto/discussions--thread-list--with-threads.png` | `../assets/images/screenshots/releases/v3.0.0.b3/discussion-thread.png` |
| 168 | `../assets/images/screenshots/auto/threads--agent-message--response.png` | `../assets/images/screenshots/releases/v3.0.0.b3/agent-response.png` |
| 192 | `../assets/images/screenshots/auto/admin--agent-config--create-modal.png` | `../assets/images/screenshots/releases/v3.0.0.b3/agent-config.png` |
| 243 | `../assets/images/screenshots/auto/badges--celebration-modal--auto-award.png` | `../assets/images/screenshots/releases/v3.0.0.b3/badge-celebration.png` |
| 270 | `../assets/images/screenshots/auto/folders--tree-sidebar--nested.png` | `../assets/images/screenshots/releases/v3.0.0.b3/folder-tree.png` |
| 319 | `../assets/images/screenshots/auto/users--profile--public.png` | `../assets/images/screenshots/releases/v3.0.0.b3/user-profile.png` |
| 359 | `../assets/images/screenshots/auto/landing--leaderboard--with-data.png` | `../assets/images/screenshots/releases/v3.0.0.b3/leaderboard.png` |
| 409 | `../assets/images/screenshots/auto/corpus--analytics--dashboard.png` | `../assets/images/screenshots/releases/v3.0.0.b3/analytics.png` |

**Step 2: Commit**

```bash
git add docs/releases/v3.0.0.b3.md
git commit -m "Point v3.0.0.b3 release notes at locked release screenshots"
```

---

### Task 4: Update CLAUDE.md documentation

**Files:**
- Modify: `CLAUDE.md`

**Step 1: Add release screenshot documentation to the existing "Automated Documentation Screenshots" section**

Add after the existing `docScreenshot` documentation:

```markdown
#### Release Screenshots (Point-in-Time)

For release notes, use `releaseScreenshot` to capture screenshots that are **locked in amber** — they capture the UI at a specific release and never change.

```typescript
import { releaseScreenshot } from "./utils/docScreenshot";

// After the component reaches desired state:
await releaseScreenshot(page, "v3.0.0.b3", "landing-page", { fullPage: true });
```

**Key differences from `docScreenshot`:**
- Output: `docs/assets/images/screenshots/releases/{version}/{name}.png`
- **Write-once**: If the file already exists, the function is a no-op (won't overwrite)
- CI never touches the `releases/` directory
- Name is a simple kebab-case string (no `--` segment convention needed)
- Version must match `v{major}.{minor}.{patch}` format (with optional suffix)

**When to use which:**
- `docScreenshot` → README, quickstart, guides (always fresh)
- `releaseScreenshot` → Release notes (frozen at release time)
```

**Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "Document releaseScreenshot utility in CLAUDE.md"
```
