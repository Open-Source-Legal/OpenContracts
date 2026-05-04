/**
 * E2E test helpers shared across the integration specs.
 *
 * All views in `frontend/src/views/` are catalogued here so the navigation
 * spec can iterate over them. For each view we record:
 *   - `path`          The URL path (or "/" for the discover landing).
 *   - `name`          A human-readable label used in test titles.
 *   - `matcher`       Visible text or selector that proves the view
 *                     rendered. We deliberately use "any of" lists where
 *                     the rendered copy varies (loading vs settled, etc).
 *   - `requiresAuth`  Whether navigating to the path while anonymous still
 *                     produces a usable view. Anonymous-friendly views are
 *                     also exercised in the unauthenticated test pass to
 *                     boost line coverage.
 *
 * View → route mapping is taken from `App.tsx`. Routes whose elements live
 * in `src/components/routes/` (e.g. `LeaderboardRoute`, `UserProfileRoute`)
 * still ultimately render a view from `src/views/`, so they're included.
 */

import { Page, WebSocket as PWWebSocket, expect } from "@playwright/test";
import { execSync } from "child_process";
import * as path from "path";

export interface ViewSpec {
  /** URL path, e.g. "/corpuses". */
  path: string;
  /** Human-readable label. */
  name: string;
  /** Visible text or selector that proves the view rendered. */
  matcher: ViewMatcher;
  /** True if the view requires an authenticated user to be useful. */
  requiresAuth: boolean;
  /** True if the route redirects (e.g. /profile → /users/<slug>). */
  redirects?: boolean;
}

export type ViewMatcher =
  | { kind: "text"; text: string | RegExp }
  | { kind: "anyText"; texts: Array<string | RegExp> }
  | { kind: "selector"; selector: string };

/**
 * Catalog of every routed view in `src/views/`. Order matters for the
 * navigation walk: we go from public/landing pages first to deeper
 * authenticated views last, mirroring how a real user would discover
 * the product.
 */
export const VIEWS: ViewSpec[] = [
  {
    path: "/",
    name: "DiscoveryLanding",
    matcher: {
      kind: "anyText",
      texts: [/Featured Collections/i, /Recent Activity/i, /Top Contributors/i],
    },
    requiresAuth: false,
  },
  {
    path: "/corpuses",
    name: "Corpuses",
    matcher: { kind: "text", text: /Your\s+corpuses/i },
    requiresAuth: false,
  },
  {
    path: "/documents",
    name: "Documents",
    matcher: { kind: "text", text: /Your\s+documents/i },
    requiresAuth: false,
  },
  {
    path: "/label_sets",
    name: "LabelSets",
    matcher: { kind: "text", text: /Organize your\s+labels/i },
    requiresAuth: false,
  },
  {
    path: "/annotations",
    name: "Annotations",
    matcher: { kind: "text", text: /Browse\s+annotations/i },
    requiresAuth: false,
  },
  {
    path: "/extracts",
    name: "Extracts",
    matcher: { kind: "text", text: /Extract\s+structured data/i },
    requiresAuth: false,
  },
  {
    path: "/discussions",
    name: "GlobalDiscussions",
    matcher: {
      kind: "anyText",
      texts: [/^Discussions$/i, /Search discussions/i],
    },
    requiresAuth: false,
  },
  {
    path: "/threads",
    name: "ThreadSearchRoute",
    matcher: { kind: "text", text: /Search Discussions/i },
    requiresAuth: false,
  },
  {
    path: "/privacy",
    name: "PrivacyPolicy",
    matcher: {
      kind: "anyText",
      texts: [/PRIVACY NOTICE/i, /personal information/i],
    },
    requiresAuth: false,
  },
  {
    path: "/terms_of_service",
    name: "TermsOfService",
    matcher: { kind: "text", text: /Terms of Service/i },
    requiresAuth: false,
  },
  // /profile is NOT included because it always redirects to /users/<slug>
  // via React Router's <Navigate>. The pushState-based spaNavigate helper
  // cannot follow <Navigate> redirects, so we skip it here. The dedicated
  // user-and-extract-routes spec covers /profile via spaNavigate(..., true).
  {
    // Resolved by CentralRouteManager Phase 1 → openedUser → UserProfileRoute.
    path: "/users/admin",
    name: "UserProfile",
    matcher: { kind: "anyText", texts: [/admin/i, /Profile/i] },
    requiresAuth: true,
  },
];

/**
 * Credentials for the initial superuser created by
 * `opencontractserver/users/migrations/0003_create_initial_superuser.py`.
 * The CI workflow sets E2E_TEST_USERNAME and E2E_TEST_PASSWORD via the
 * `env:` block on the Playwright step; local callers must export them or
 * the test will fail with a clear message.
 */
export const TEST_USER = {
  username: process.env.E2E_TEST_USERNAME || "admin",
  password: (() => {
    const pw = process.env.E2E_TEST_PASSWORD;
    if (!pw) {
      throw new Error(
        "E2E_TEST_PASSWORD environment variable is not set. " +
          "Set it to the superuser password before running E2E tests."
      );
    }
    return pw;
  })(),
};

/**
 * Wait for a `ViewMatcher` to be satisfied on the page. Uses Playwright's
 * built-in expect retry loop so flaky data fetches don't fail the test.
 */
export async function expectViewVisible(
  page: Page,
  matcher: ViewMatcher,
  timeoutMs = 20_000
): Promise<void> {
  switch (matcher.kind) {
    case "text": {
      await expect(page.getByText(matcher.text).first()).toBeVisible({
        timeout: timeoutMs,
      });
      return;
    }
    case "anyText": {
      // At least one of the candidate texts must become visible.
      // Uses Playwright's built-in retry via expect().toPass().
      await expect(async () => {
        for (const text of matcher.texts) {
          if (await page.getByText(text).first().isVisible()) {
            return;
          }
        }
        throw new Error(`none of [${matcher.texts.join(", ")}] visible yet`);
      }).toPass({ timeout: timeoutMs, intervals: [250] });
      return;
    }
    case "selector": {
      await expect(page.locator(matcher.selector).first()).toBeVisible({
        timeout: timeoutMs,
      });
      return;
    }
  }
}

/**
 * Perform a UI-driven password login against the live frontend. The login
 * form lives at `src/views/Login.tsx`; on success it stores an in-memory
 * authToken and `navigate("/")`s the user away. We wait for that redirect
 * so callers get a page already in the authenticated state.
 *
 * NOTE: the Apollo reactive var that holds the token is in-memory only,
 * so any subsequent full `page.goto(...)` would lose it. Use SPA-style
 * navigation (`spaNavigate` below or `page.click` on a NavMenu link)
 * instead of `page.goto` after this function returns.
 */
export async function loginViaUI(
  page: Page,
  username: string = TEST_USER.username,
  password: string = TEST_USER.password
): Promise<void> {
  await page.goto("/login");

  // The login form has placeholder-only labels; rely on the placeholders
  // (which are stable copy in `Login.tsx`) to find the inputs.
  const usernameInput = page.getByPlaceholder("Username");
  const passwordInput = page.getByPlaceholder("Password");
  await expect(usernameInput).toBeVisible({ timeout: 30_000 });
  await usernameInput.fill(username);
  await passwordInput.fill(password);

  await page.getByRole("button", { name: /^login$/i }).click();

  // After a successful login the SPA navigates back to "/". The login
  // mutation also fires a cache reset, so we wait both for the URL
  // change AND for one of the discovery-page sentinels to appear.
  await expect(page).toHaveURL(/\/(\?.*)?$/, { timeout: 30_000 });
}

/**
 * Navigate within the React Router SPA without performing a full
 * page reload. This preserves the in-memory authToken set by `loginViaUI`.
 *
 * Implementation: we push the new path onto window.history and dispatch
 * a `popstate` event so the @remix-run/router BrowserHistory listener
 * picks up the change and re-renders. CentralRouteManager then syncs
 * Apollo reactive vars from the new URL.
 *
 * FRAGILITY NOTE: This relies on @remix-run/router (used by react-router v6)
 * listening to popstate events. If React Router changes how BrowserHistory
 * subscribes to navigation events, this will break silently. Verify after
 * any react-router upgrade.
 */
export async function spaNavigate(
  page: Page,
  path: string,
  /** Skip URL assertion for routes that redirect (e.g. /profile → /users/slug). */
  expectRedirect = false
): Promise<void> {
  await page.evaluate((targetPath) => {
    window.history.pushState({}, "", targetPath);
    window.dispatchEvent(new PopStateEvent("popstate", { state: {} }));
  }, path);

  if (expectRedirect) {
    // Wait for the React Router <Navigate> redirect to settle.
    await page.waitForTimeout(2000);
    // Verify we navigated away from the original path.
    await expect(page).not.toHaveURL(
      new RegExp(`${path.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}$`)
    );
  } else {
    // Assert the URL actually changed to catch silent navigation failures.
    await expect(page).toHaveURL(
      new RegExp(`${path.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`)
    );
  }
}

/**
 * Admin views that require superuser access. Separated from the main
 * VIEWS catalog because the navigation spec runs on an empty database
 * where these are not relevant.
 */
export const ADMIN_VIEWS: ViewSpec[] = [
  {
    path: "/admin/settings",
    name: "GlobalSettings",
    matcher: { kind: "text", text: /Global Settings/i },
    requiresAuth: true,
  },
  {
    path: "/system_settings",
    name: "SystemSettings",
    matcher: {
      kind: "anyText",
      texts: [/System Settings/i, /Error Loading Settings/i, /Admin Settings/i],
    },
    requiresAuth: true,
  },
];

/**
 * Create a corpus via the UI by clicking the Add button on /corpuses,
 * filling the modal, and submitting. Waits for the success toast.
 *
 * Caller must already be authenticated and on a page where spaNavigate works.
 */
export async function createCorpusViaUI(
  page: Page,
  title: string,
  description: string
): Promise<void> {
  await spaNavigate(page, "/corpuses");
  await expectViewVisible(page, { kind: "text", text: /Your\s+corpuses/i });

  // Click the "New Corpus" button (or "Create Your First Corpus" on empty state)
  const createBtn = page.getByRole("button", {
    name: /New Corpus|Create Your First Corpus/i,
  });
  await createBtn.first().click();

  // Fill the modal form
  await expect(page.locator("#corpus-title")).toBeVisible({ timeout: 10_000 });
  await page.fill("#corpus-title", title);
  await page.fill("#corpus-description", description);

  // Submit — the button text "Create Corpus" appears twice (menu item + modal button).
  // Target the one inside the modal footer.
  await page
    .locator(".oc-modal-footer button", { hasText: /Create Corpus/i })
    .click();

  // Wait for the success toast and modal to close
  await expect(page.getByText(/Created corpus/i)).toBeVisible({
    timeout: 15_000,
  });
  await expect(page.locator("#corpus-title")).not.toBeVisible({
    timeout: 5_000,
  });
}

/**
 * Upload a plain-text document from the /documents view. Opens the upload
 * modal, attaches a file created from `content`, fills title/description,
 * and submits. Waits for the upload to complete.
 *
 * Caller must already be authenticated.
 */
export async function uploadDocumentViaUI(
  page: Page,
  filename: string,
  content: string,
  title: string,
  description: string,
  /** If provided, selects this corpus in the upload wizard's corpus step. */
  corpusTitle?: string
): Promise<void> {
  await spaNavigate(page, "/documents");
  await expectViewVisible(page, { kind: "text", text: /Your\s+documents/i });

  // Click the "Upload" button
  await page.getByRole("button", { name: /^Upload$/i }).click();

  // Wait for the upload modal's file dropzone
  await expect(page.getByTestId("file-dropzone")).toBeVisible({
    timeout: 10_000,
  });

  // Create a text file buffer and attach it via the hidden file input
  const buffer = Buffer.from(content, "utf-8");
  const fileInput = page.locator('input[type="file"]').first();
  await fileInput.setInputFiles({
    name: filename,
    mimeType: "text/plain",
    buffer,
  });

  // Click "Continue" to move from Select step to Details step
  await page.getByRole("button", { name: /Continue/i }).click();

  // Wait for the "Details" step to appear
  await expect(page.locator("#document-title")).toBeVisible({
    timeout: 10_000,
  });
  await page.fill("#document-title", title);
  await page.fill("#document-description", description);

  if (corpusTitle) {
    // Click "Continue" to advance to the Corpus step
    await page.getByRole("button", { name: /Continue/i }).click();

    // Wait for corpus step and select our corpus from the list
    const corpusSearch = page.getByPlaceholder(/Search corpuses/i);
    await expect(corpusSearch).toBeVisible({ timeout: 10_000 });
    await corpusSearch.fill(corpusTitle);
    await page.waitForTimeout(500);

    // Click the matching corpus item in the list (skip the search input itself)
    await page
      .locator("button, [role='button']", {
        hasText: new RegExp(corpusTitle),
      })
      .first()
      .click();
    await page.waitForTimeout(300);

    // Click the Upload button in the modal footer (last one to avoid matching header text)
    await page
      .locator("button")
      .filter({ hasText: /Upload/i })
      .last()
      .click();
  } else {
    // Skip corpus association and upload directly
    await page.getByRole("button", { name: /Skip Corpus/i }).click();
  }

  // Wait for upload to complete — the modal closes or shows a completion state
  await expect(page.locator("#document-title")).not.toBeVisible({
    timeout: 60_000,
  });
}

/**
 * Upload a PDF document from disk via the /documents upload modal.
 *
 * Mirrors `uploadDocumentViaUI` but reads a real file and sets the
 * mimeType to "application/pdf" so Django's parser-router picks the
 * PDF parser pipeline (PAWLs + embeddings) rather than TxtParser.
 *
 * Caller must already be authenticated.
 */
export async function uploadPdfViaUI(
  page: Page,
  fixturePath: string,
  title: string,
  description: string,
  corpusTitle: string
): Promise<void> {
  await spaNavigate(page, "/documents");
  await expectViewVisible(page, { kind: "text", text: /Your\s+documents/i });

  await page.getByRole("button", { name: /^Upload$/i }).click();

  await expect(page.getByTestId("file-dropzone")).toBeVisible({
    timeout: 10_000,
  });

  // Read the PDF off disk and attach it via the hidden file input.
  // setInputFiles accepts a path string directly, so no buffering is
  // needed — Playwright streams the file into the page.
  const fileInput = page.locator('input[type="file"]').first();
  await fileInput.setInputFiles(fixturePath);

  // Step: Select → Details
  await page.getByRole("button", { name: /Continue/i }).click();
  await expect(page.locator("#document-title")).toBeVisible({
    timeout: 10_000,
  });
  await page.fill("#document-title", title);
  await page.fill("#document-description", description);

  // Step: Details → Corpus
  await page.getByRole("button", { name: /Continue/i }).click();

  const corpusSearch = page.getByPlaceholder(/Search corpuses/i);
  await expect(corpusSearch).toBeVisible({ timeout: 10_000 });
  await corpusSearch.fill(corpusTitle);
  await page.waitForTimeout(500);

  await page
    .locator("button, [role='button']", {
      hasText: new RegExp(corpusTitle),
    })
    .first()
    .click();
  await page.waitForTimeout(300);

  // Click the modal-footer "Upload" button (last match avoids the
  // header copy that says the same thing).
  await page
    .locator("button")
    .filter({ hasText: /Upload/i })
    .last()
    .click();

  // The modal closes when the upload mutation resolves. Embedding /
  // parsing keep running in Celery — that's the "wait for ready" step
  // a separate helper handles.
  await expect(page.locator("#document-title")).not.toBeVisible({
    timeout: 60_000,
  });
}

/**
 * Create a new Extract via the /extracts page UI. Opens the "New Extract"
 * modal, names it, selects the named corpus from the CorpusDropdown, and
 * submits. Waits for the success toast + modal close.
 *
 * Caller must already be authenticated.
 */
export async function createExtractViaUI(
  page: Page,
  extractName: string,
  corpusTitle: string
): Promise<void> {
  await spaNavigate(page, "/extracts");
  await expectViewVisible(page, {
    kind: "text",
    text: /Extract\s+structured data/i,
  });

  // The "New Extract" button is the primary CTA on the authenticated extracts
  // view. On a completely empty state it renders as "Create Your First Extract".
  const newBtn = page.getByRole("button", {
    name: /New Extract|Create Your First Extract|Create Extract/i,
  });
  await newBtn.first().click();

  // Modal title appears.
  await expect(page.getByText(/Create New Extract/i)).toBeVisible({
    timeout: 10_000,
  });

  // Fill the extract name (plain <input> with known placeholder).
  await page
    .getByPlaceholder(/Enter a descriptive name for your extract/i)
    .fill(extractName);

  // Corpus dropdown — rendered by the @os-legal/ui Dropdown component with
  // mode="select" and searchable="async".
  //
  // The trigger is a div[role="combobox"] that shows the placeholder text
  // when nothing is selected. Clicking it opens the menu and reveals a
  // search <input class="oc-dropdown__search-input">. Type the corpus name,
  // wait for the option to appear, and click it.
  const corpusCombobox = page.locator('[role="combobox"]', {
    hasText: new RegExp("Choose a corpus to load documents from", "i"),
  });
  if (await corpusCombobox.isVisible().catch(() => false)) {
    await corpusCombobox.click();
    const searchInput = page.locator(".oc-dropdown__search-input");
    await expect(searchInput).toBeVisible({ timeout: 5_000 });
    await searchInput.fill(corpusTitle);
    // Wait for the async search debounce and re-render.
    await page.waitForTimeout(600);
    await page
      .locator('[role="option"]', {
        hasText: new RegExp(corpusTitle.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")),
      })
      .first()
      .click();
  }

  // Submit — the modal footer's primary button reads "Create Extract".
  await page
    .locator("button", { hasText: /^Create Extract$/i })
    .last()
    .click();

  await expect(page.getByText(/Extract created successfully/i)).toBeVisible({
    timeout: 15_000,
  });
}

/**
 * Open an extract from the /extracts list page by clicking its card.
 * Waits for the extract detail page (Schema tab visible) to settle.
 *
 * Caller must already be authenticated.
 */
export async function openExtractByName(
  page: Page,
  extractName: string
): Promise<void> {
  await spaNavigate(page, "/extracts");
  await expectViewVisible(page, {
    kind: "text",
    text: /Extract\s+structured data/i,
  });

  // Each extract renders as a CollectionCard (role="article") with
  // aria-label="Extract: <name>". Click it to navigate to the detail view.
  //
  // Toast notifications from earlier steps ("Extract Complete", etc.)
  // can hover over the card and intercept the click. We close any
  // visible close-buttons on toast alerts first, then use force-click
  // as a belt-and-braces fallback against any remaining transient
  // overlay. The card itself is stable; the surrounding toast layer is
  // the only flake source.
  for (const closeBtn of await page
    .locator('[role="alert"] button[aria-label="close"]')
    .all()) {
    if (await closeBtn.isVisible().catch(() => false)) {
      await closeBtn.click().catch(() => {});
    }
  }
  await page.waitForTimeout(300);

  const card = page
    .locator('[role="article"]', {
      hasText: new RegExp(extractName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")),
    })
    .first();
  await expect(card).toBeVisible({ timeout: 15_000 });
  await card.click({ force: true });

  // The detail page loads tabs; Schema tab proves we are on the right page.
  await expect(page.getByRole("tab", { name: /^Schema$/i })).toBeVisible({
    timeout: 15_000,
  });
}

/**
 * Add a single column to the currently-open extract detail page.
 * Switches to the Schema tab, opens the column-creation modal via the
 * "Add" button, fills name + query, and submits. Defaults output type to
 * a primitive string ("str") — the modal initialises to that value.
 *
 * Caller must already be on the extract detail page.
 */
export async function addColumnViaUI(
  page: Page,
  columnName: string,
  query: string
): Promise<void> {
  // Switch to Schema tab.
  await page.getByRole("tab", { name: /^Schema$/i }).click();
  await page.waitForTimeout(300);

  // The Schema tab header renders an "+ Add Column" button (from
  // ExtractDetailContent line ~789). When there are no columns the empty-state
  // also shows an "Add Column" button. Both call handleAddColumn. Match either.
  await page
    .getByRole("button", { name: /Add Column/i })
    .first()
    .click();

  // Wait for the column-creation modal (has "Enter column name" input).
  await expect(page.getByPlaceholder(/Enter column name/i)).toBeVisible({
    timeout: 10_000,
  });

  await page.getByPlaceholder(/Enter column name/i).fill(columnName);
  await page
    .getByPlaceholder(/What query shall we use to guide the LLM extraction/i)
    .fill(query);

  // Submit — the modal footer's primary button reads "Create Column".
  await page.getByRole("button", { name: /^Create Column$/i }).click();

  // Wait for the column to appear in the schema list.
  await expect(
    page
      .locator(".oc-tab-panel, [role='tabpanel']")
      .filter({ hasText: /Extract Schema/i })
      .getByText(new RegExp(columnName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")))
      .first()
  ).toBeVisible({ timeout: 15_000 });
}

/**
 * Add the named documents to the currently-open extract via the Data
 * tab's "Add documents" floating button. Opens SelectDocumentsModal,
 * waits for all document cards to load (graphene returns up to 100 in
 * one page, so all documents appear immediately), clicks each target
 * card by filtering on its visible title text, then confirms with
 * "Add Documents".
 *
 * NOTE: The modal's search bar performs full-text content search (not
 * title search). We do NOT use it — we filter cards by visible title
 * text directly. All cards are in the DOM and Playwright's `click()`
 * scrolls them into view automatically.
 *
 * If a document is already in the extract, `filterDocIds` removes it
 * from the modal, so it won't appear. The step is skipped gracefully
 * in that case.
 *
 * Caller must already be on the extract detail page.
 */
export async function addDocumentsToExtractViaUI(
  page: Page,
  documentTitles: string[]
): Promise<void> {
  // Switch to the Data tab — the "Add documents" FAB only lives there.
  await page.getByRole("tab", { name: /^Data$/i }).click();
  await page.waitForTimeout(300);

  // The "Add documents" button only shows before the extract is started.
  // If the extract already has rows (docs added from a previous run with
  // the same RUN_ID), the button may or may not be present.
  const addBtn = page.getByRole("button", { name: /Add documents/i }).first();
  const addBtnVisible = await addBtn
    .isVisible({ timeout: 5_000 })
    .catch(() => false);

  if (!addBtnVisible) {
    // Extract already started or docs already present; nothing to do.
    return;
  }

  await addBtn.click();

  // The modal header confirms it opened.
  await expect(page.getByText(/Select Document\(s\)/i)).toBeVisible({
    timeout: 10_000,
  });

  // Wait briefly for at least one document card to load. The query fetches
  // up to RELAY_CONNECTION_MAX_LIMIT (100) in one page, so all cards are
  // in the DOM immediately. Cards are tagged with
  // `data-testid="document-card"` (ModernDocumentItem.tsx); we then filter
  // by the visible title text.
  //
  // The modal can legitimately render zero cards when every requested
  // document is already attached to the extract (the corpus
  // auto-populates extract rows on creation). In that case the modal
  // shows an empty state, not a card list. Probe with a short timeout so
  // we don't hang on the all-already-attached path; the no-op bailout
  // below handles it.
  const firstCard = page.locator("[data-testid='document-card']").first();
  const haveAnyCards = await firstCard
    .isVisible({ timeout: 5_000 })
    .catch(() => false);
  if (!haveAnyCards) {
    await page.getByRole("button", { name: /^Cancel$/i }).click();
    return;
  }

  // Collect which titles we actually need to click (some may already be in
  // the extract and filtered out of the modal by filterDocIds).
  const titlesToAdd: string[] = [];
  for (const title of documentTitles) {
    const card = page
      .locator("[data-testid='document-card']")
      .filter({ hasText: title });
    const count = await card.count();
    if (count > 0) {
      titlesToAdd.push(title);
    }
    // If count === 0, this doc is already in the extract (filtered out).
  }

  if (titlesToAdd.length === 0) {
    // All documents already in the extract; close modal and return.
    await page.getByRole("button", { name: /^Cancel$/i }).click();
    return;
  }

  for (const title of titlesToAdd) {
    const card = page
      .locator("[data-testid='document-card']")
      .filter({ hasText: title })
      .first();
    // click() scrolls the element into view automatically.
    await card.click();
    await page.waitForTimeout(200);
  }

  // Click the modal confirm button. SelectDocumentsModal renders
  // <Button variant="primary">Add Documents</Button> in the ModalFooter.
  await page.getByRole("button", { name: /^Add Documents$/i }).click();

  // The modal closes and rows for both documents now appear in the grid.
  for (const title of documentTitles) {
    await expect(page.getByText(title).first()).toBeVisible({
      timeout: 30_000,
    });
  }
}

/**
 * Click the extract's "Start Extract" button (a <Button> on the full-page
 * ExtractDetail header), then poll until the running overlay disappears.
 * Throws loudly if "Extraction failed" renders instead of completion.
 *
 * Default ceiling: 12 minutes — two LLM round-trips + AG-Grid render +
 * Apollo cache settle.
 *
 * Caller must already be on the extract detail page.
 */
export async function runExtractAndWaitForFinish(
  page: Page,
  timeoutMs: number = 12 * 60 * 1000
): Promise<void> {
  // If the extract was already run (e.g. a previous partial test run with
  // the same RUN_ID), "Start Extract" won't be visible. In that case,
  // check that we're already in a finished/data state and return early.
  const startBtn = page.getByRole("button", { name: /^Start Extract$/i });
  const startBtnVisible = await startBtn
    .isVisible({ timeout: 5_000 })
    .catch(() => false);

  if (!startBtnVisible) {
    // Either already running or already finished. Wait for Data tab to be
    // visible (finished state) or "Extraction in progress" to clear.
    await expect(async () => {
      const failed = await page
        .getByText(/Extraction failed/i)
        .isVisible()
        .catch(() => false);
      if (failed) {
        throw new Error("Extract is in failed state.");
      }
      const running = await page
        .getByText(/Extraction in progress/i)
        .isVisible()
        .catch(() => false);
      if (running) {
        throw new Error("still running");
      }
      await expect(page.getByRole("tab", { name: /^Data$/i })).toBeVisible();
    }).toPass({ timeout: timeoutMs, intervals: [5_000, 10_000] });
    return;
  }

  // Full-page ExtractDetail renders a <Button> with text "Start Extract".
  await startBtn.first().click();

  // While running, ExtractDetail / ExtractDetailContent renders
  // "Extraction in progress..." as a styled RunningTitle overlay.
  await expect(page.getByText(/Extraction in progress/i)).toBeVisible({
    timeout: 60_000,
  });

  // Poll until either the overlay disappears (success) or the failed state
  // renders. toPass retries the inner async function until it does not throw.
  await expect(async () => {
    const failed = await page
      .getByText(/Extraction failed/i)
      .isVisible()
      .catch(() => false);
    if (failed) {
      throw new Error(
        "Extract run failed — 'Extraction failed' overlay is visible. " +
          "Check the backend Celery logs and ensure OPENAI_API_KEY is set correctly."
      );
    }

    const stillRunning = await page
      .getByText(/Extraction in progress/i)
      .isVisible()
      .catch(() => false);
    if (stillRunning) {
      throw new Error("still running — waiting for completion");
    }

    // The overlay is gone and neither failed state is present: extraction
    // completed successfully. Verify the Data tab is visible again.
    await expect(page.getByRole("tab", { name: /^Data$/i })).toBeVisible();
  }).toPass({ timeout: timeoutMs, intervals: [5_000, 10_000] });

  // The "Extraction in progress" overlay disappearing only means the
  // backend marked the Extract row complete. AG-Grid still has to fetch
  // the per-cell `data` payloads via Apollo — until that round-trip
  // finishes the grid renders a "Loading..." placeholder where the cell
  // values should be. Asserting on cell text before this completes is
  // the source of intermittent "row has no non-empty extracted cell"
  // false negatives, since the placeholder is whitespace-only.
  //
  // Wait for the placeholder to clear before returning. We give Apollo a
  // generous ceiling (the cell-data query can be slow on cold caches);
  // catch+swallow the timeout because some rows legitimately render with
  // no placeholder when the grid happens to hydrate within the same tick
  // as the overlay disappears.
  await page
    .getByText(/^\s*Loading\.\.\.\s*$/)
    .first()
    .waitFor({ state: "detached", timeout: 30_000 })
    .catch(() => {});
}

/**
 * Open the Iterations tab on the currently-open extract detail page,
 * click "New iteration", choose an axis, optionally rename, leave
 * "Run immediately" UNCHECKED, and submit.
 *
 * Caller must already be on the extract detail page (any tab).
 *
 * INTENTIONAL CHOICE: we default to autoStart=false because a second
 * extract run would require a second LLM round-trip — and the VCR
 * cassette for the e2e workflow only covers the parent extract's calls.
 * Iteration B with no cells still produces a meaningful diff (every
 * parent cell becomes ONLY_IN_A), which is enough to prove the
 * iteration creation + diff query end-to-end.
 *
 * Returns the name the iteration was created with so callers can locate
 * the row in the iterations list afterwards.
 */
export async function forkExtractIterationViaUI(
  page: Page,
  iterationName: string,
  axis: "MODEL" | "DOCUMENT_VERSIONS" | "FIELDSET" = "MODEL",
  autoStart: boolean = false,
  /**
   * Only used when axis === "MODEL". The dialog renders a "Model identifier"
   * input that NewIterationDialog packs into modelConfig = { model }. Without
   * a non-empty value the mutation inherits the parent's empty model_config,
   * which makes the backend's iterationAxis resolver return null (no diff
   * across model_config). Default to a stub so the axis chip renders.
   */
  modelIdentifier: string = "anthropic:claude-opus-4-7"
): Promise<string> {
  // Switch to Iterations tab. ExtractDetailContent's Tabs renders this
  // tab as the fourth child, label "Iterations".
  await page.getByRole("tab", { name: /^Iterations$/i }).click();
  await page.waitForTimeout(300);

  // The toolbar's primary CTA reads "New iteration" (NewIterationDialog
  // trigger in ExtractIterationsTab.tsx).
  await page
    .getByRole("button", { name: /^New iteration$/i })
    .first()
    .click();

  // Modal has aria-label="New iteration".
  const dialog = page.getByRole("dialog", { name: /^New iteration$/i });
  await expect(dialog).toBeVisible({ timeout: 10_000 });

  // Axis cards are <button> elements inside the dialog. The default
  // selection is MODEL; only re-click when the caller wants a different
  // axis. Each card's label includes a Lucide icon plus the axis name.
  if (axis !== "MODEL") {
    const label =
      axis === "DOCUMENT_VERSIONS" ? /Document versions/i : /^Schema$/i;
    await dialog.getByRole("button", { name: label }).first().click();
  }

  // Name field is the only text input that takes the placeholder
  // "Defaults to <source name> (iteration N)".
  await dialog
    .getByPlaceholder(/Defaults to .*iteration N/i)
    .fill(iterationName);

  // For MODEL-axis runs, fill the "Model identifier" input. The backend
  // iterationAxis resolver compares (self.model_config or {}) to
  // (parent.model_config or {}) — without a value here the iteration
  // inherits parent's empty config and the resolver returns null, so
  // the axis chip never renders.
  if (axis === "MODEL" && modelIdentifier) {
    const modelInput = dialog.getByPlaceholder(/anthropic:claude/i).first();
    if (await modelInput.isVisible().catch(() => false)) {
      await modelInput.fill(modelIdentifier);
    }
  }

  // "Run immediately" toggle. The dialog ships with checked=true; flip
  // it off when autoStart=false so the new iteration is created without
  // queueing run_extract (no extra LLM traffic needed for this assertion
  // — see the comment on this helper).
  const runNow = dialog.locator('input[type="checkbox"]').first();
  const checked = await runNow.isChecked();
  if (checked !== autoStart) {
    await runNow.click();
  }

  // Submit — the dialog footer's primary button reads "Create iteration".
  await dialog
    .getByRole("button", { name: /^Create iteration$/i })
    .first()
    .click();

  // Toast confirms creation. ExtractIterationsTab fires
  // `toast.success("Iteration queued.")` on the mutation onCompleted hook.
  await expect(page.getByText(/Iteration queued\./i)).toBeVisible({
    timeout: 15_000,
  });

  // Dialog closes after the mutation completes.
  await expect(dialog).not.toBeVisible({ timeout: 10_000 });

  return iterationName;
}

/**
 * Click the parent (current) extract row and the named iteration row
 * in the Iterations tab so the compare view loads. Returns once the
 * "Comparing 2 iterations" chip is visible (proving both selections
 * were registered and the panel is about to render the diff).
 *
 * Caller must already be on the Iterations tab with the iteration row
 * visible.
 */
export async function selectIterationsForCompare(
  page: Page,
  parentExtractName: string,
  iterationName: string
): Promise<void> {
  // The current extract row carries an inline "(current)" label so we
  // can disambiguate it from any iteration that happens to share its
  // base name.
  const currentRow = page
    .locator("[data-testid='iteration-row']")
    .filter({ hasText: parentExtractName })
    .filter({ hasText: /\(current\)/i })
    .first();
  await expect(currentRow).toBeVisible({ timeout: 10_000 });
  await currentRow.click();

  const iterationRow = page
    .locator("[data-testid='iteration-row']")
    .filter({ hasText: iterationName })
    .first();
  await expect(iterationRow).toBeVisible({ timeout: 10_000 });
  await iterationRow.click();

  // The "Comparing 2 iterations" chip appears in the toolbar only when
  // the cap-of-2 selection set has reached size 2.
  await expect(page.getByText(/Comparing 2 iterations/i)).toBeVisible({
    timeout: 10_000,
  });
}

/**
 * Wait until a document with the given title finishes parsing +
 * embedding.
 *
 * UI signal: `data-processing="false"` on the document card element.
 * This attribute is set by Documents.tsx (the /documents view) on each
 * DocumentCardWrapper / ListItem / CompactItem and reflects
 * `doc.backendLock` directly — "true" while Celery is still parsing or
 * embedding, "false" once complete.
 *
 * We use a dedicated `data-processing` attribute rather than checking
 * disabled button states because the card-view action buttons in the
 * grid view live inside an `opacity: 0` hover-overlay and are never
 * reliably testable without triggering hover interactions.
 *
 * Cards are matched by `data-testid="document-card"` (set in both
 * Documents.tsx and ModernDocumentItem.tsx) and the visible title
 * text. Real-world ingestion can take "up to a few minutes" per PDF;
 * the default 8-minute ceiling leaves headroom for cold workers.
 */
export async function waitForDocumentReady(
  page: Page,
  documentTitle: string,
  timeoutMs: number = 8 * 60 * 1000
): Promise<void> {
  await expect(async () => {
    // Re-navigate on every attempt to force a fresh GraphQL fetch and
    // bypass any in-flight polling gaps.
    await spaNavigate(page, "/documents");

    // Don't gate on the "Your documents" heading. The route can render
    // the document grid before its surrounding chrome (the heading is
    // emitted by an outer layout component that occasionally hydrates
    // last). Wait directly on the card for the document we care about;
    // its presence is sufficient evidence the documents view loaded.
    const card = page
      .locator("[data-testid='document-card']")
      .filter({ hasText: documentTitle })
      .first();
    await expect(card).toBeVisible({ timeout: 30_000 });

    // `data-processing="true"` while backendLock === true.
    // "false" means parsing + embedding finished (or the document was
    // never locked, e.g. a plain-text file), so it is ready to use.
    const processing = await card.getAttribute("data-processing");
    if (processing === "true") {
      throw new Error(
        `Document "${documentTitle}" still processing (data-processing="true")`
      );
    }
  }).toPass({ timeout: timeoutMs, intervals: [5_000, 10_000, 15_000] });
}

/**
 * Open a corpus's inline Discussions view by:
 *   1. SPA-navigating to /corpuses
 *   2. Clicking the corpus card so CentralRouteManager loads it into
 *      `openedCorpus` and updates the URL to /c/<user>/<corpus>
 *   3. Re-using the resulting URL with `?view=discussions` appended so
 *      CorpusHome renders <CorpusDiscussionsInlineView>.
 *
 * Waits for the Discussions toolbar (the "All" filter pill) to be visible
 * before returning so callers can immediately click "New Discussion".
 *
 * Caller must already be authenticated.
 */
export async function openCorpusDiscussionsViaUI(
  page: Page,
  corpusTitle: string
): Promise<void> {
  await spaNavigate(page, "/corpuses");
  await expectViewVisible(page, { kind: "text", text: /Your\s+corpuses/i });

  await expect(page.getByText(corpusTitle).first()).toBeVisible({
    timeout: 15_000,
  });
  await page.getByText(corpusTitle).first().click();

  // The corpus URL is slug-based: /c/<user>/<corpus>. Wait for it to settle
  // before reading + appending the view param. We anchor on the URL pattern
  // rather than visible text because CorpusHome's landing copy varies based
  // on whether a Readme.CAML article exists.
  await expect(page).toHaveURL(/\/c\/[^/]+\/[^/?#]+/, { timeout: 15_000 });
  const url = new URL(page.url());
  url.searchParams.set("view", "discussions");
  // Strip the origin so spaNavigate sees a path+query string.
  await spaNavigate(page, url.pathname + url.search);

  // The CorpusDiscussionsView toolbar always renders the "All" filter pill
  // even when there are zero threads. Use it as the "view is ready" signal.
  // Match by visible label only — the count span is an SVG-icon-free child
  // whose textual interpolation varies (`All0` vs `All 0`) across browsers.
  await expect(
    page.getByRole("button", { name: /^All\b/i }).first()
  ).toBeVisible({ timeout: 20_000 });
}

/**
 * Click the "+New Discussion" CTA, fill the create-thread modal, and
 * submit. The visible label flips between "New Discussion" (full header)
 * and "New" (embedded mode), but both share the stable
 * `aria-label="Create new discussion"` accessibility name — that is the
 * selector we anchor on.
 *
 * On success, CorpusDiscussionsView's onSuccess handler closes the modal
 * AND navigates to the new thread (sets ?thread=<id>), so this helper
 * waits for the thread detail header to render before returning.
 *
 * Caller must already be on the corpus discussions view.
 */
export async function createThreadViaUI(
  page: Page,
  title: string,
  description: string | undefined,
  initialMessage: string
): Promise<void> {
  // The CreateButton renders aria-label="Create new discussion" in both
  // header and embedded modes (CorpusDiscussionsView.tsx:525, :540), so
  // accessible-name matching is stable across viewports.
  await page
    .getByRole("button", { name: /Create new discussion/i })
    .first()
    .click();

  // CreateThreadForm modal title.
  await expect(page.getByText(/Start New Discussion/i)).toBeVisible({
    timeout: 10_000,
  });

  // Scope all subsequent modal interactions to the form container that
  // owns #thread-title. This keeps the locators robust if a future preview
  // pane adds another ProseMirror to the page tree.
  const modal = page
    .locator("div")
    .filter({ has: page.locator("#thread-title") })
    .first();

  await modal.locator("#thread-title").fill(title);
  if (description) {
    await modal.locator("#thread-description").fill(description);
  }

  // The MessageComposer is built on TipTap (ProseMirror). Fill the
  // contenteditable .ProseMirror via keyboard.type — `.fill()` does not
  // reliably trigger TipTap's onUpdate hook in all browsers.
  const editor = modal.locator(".ProseMirror").first();
  await expect(editor).toBeVisible({ timeout: 10_000 });
  await editor.click();
  await page.keyboard.type(initialMessage);

  // Submit — the modal hosts exactly one composer SendButton.
  await modal
    .getByRole("button", { name: /^Send$/i })
    .first()
    .click();

  // The mutation onSuccess closes the modal and routes to ?thread=<id>.
  // The thread title appears in the ThreadDetail header.
  await expect(page.getByText(/Start New Discussion/i)).not.toBeVisible({
    timeout: 15_000,
  });
  await expect(page.getByRole("heading", { name: title }).first()).toBeVisible({
    timeout: 15_000,
  });
}

/**
 * Post a top-level reply to the currently-open thread via the bottom
 * ReplyForm composer. Returns once the new message text is visible in
 * the thread (proving the GraphQL mutation refetched the thread).
 *
 * Caller must already be on the thread detail view (with a visible
 * ReplyForm — i.e. the thread is not locked).
 */
export async function postThreadReplyViaUI(
  page: Page,
  replyContent: string
): Promise<void> {
  // ThreadDetail renders the ReplyForm composer at the bottom of the
  // page. There is no second ProseMirror at this stage — the create
  // modal is gone — so `.last()` deterministically picks the reply
  // composer regardless of any deep-link reply context that might
  // render an additional ReplyContext header above it.
  const replyEditor = page.locator(".ProseMirror").last();
  await expect(replyEditor).toBeVisible({ timeout: 10_000 });
  await replyEditor.click();
  await page.keyboard.type(replyContent);

  // The reply composer's Send button is the only one on the page in
  // thread-detail mode. After click, the message list refetches.
  await page
    .getByRole("button", { name: /^Send$/i })
    .last()
    .click();

  // Wait for the new message text to appear in the discussion list.
  await expect(page.getByText(replyContent).first()).toBeVisible({
    timeout: 15_000,
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// WebSocket auth e2e helpers (PR #1502 — Sec-WebSocket-Protocol JWT transport)
// ─────────────────────────────────────────────────────────────────────────────
//
// These helpers cover end-to-end testing of the websocket auth-handshake
// protocol. They:
//   - run small Django shell snippets via `docker compose exec` to set up
//     fixture data (badges, public flags) without going through the slow UI;
//   - capture WebSocket frames from the real browser session so assertions
//     run against the actual wire protocol (subprotocol echo, AUTH_OK,
//     AUTH_FAILED, AUTH_REFRESH_REQUIRED, NOTIFICATION_CREATED, etc.).
//
// Naming convention: `*ViaDocker` helpers shell out to the local stack and
// are NOT a substitute for UI-driven flows where the UI itself is what's
// being tested. They exist so the websocket spec can stay focused on the
// transport layer rather than re-uploading PDFs every test.

/**
 * Compose file the local stack runs under. The websocket e2e spec needs
 * `local.yml` (Daphne ASGI server) — `test.yml` runs `runserver` which
 * does not handle websockets in the same code path as production.
 */
const E2E_COMPOSE_FILE = process.env.E2E_COMPOSE_FILE || "local.yml";
const E2E_DJANGO_SERVICE = process.env.E2E_DJANGO_SERVICE || "django";

/**
 * Repo root, computed from this file's location. The compose files live
 * at the repo root, but the playwright runner cwd is `frontend/`, so all
 * docker invocations need an absolute `-f` path.
 */
const REPO_ROOT = path.resolve(__dirname, "..", "..", "..");

/**
 * Run a Python snippet inside the Django container and return stdout.
 * Throws if the container isn't running (caller should skip the test).
 *
 * The snippet is piped to `manage.py shell` over stdin (rather than
 * `-c "..."`) so multi-line statements with dict literals, kwargs that
 * span lines, and trailing commas all work without collapsing to a
 * `;`-joined one-liner. The previous one-liner approach broke on
 * `Model.objects.create(\n    field=value,\n)` because `,\n;` is invalid
 * Python syntax.
 */
function runDjangoShell(snippet: string): string {
  const dedented = snippet.replace(/^[ \t]+/gm, "").trim();
  const composePath = path.join(REPO_ROOT, E2E_COMPOSE_FILE);
  const args = [
    "compose",
    "-f",
    composePath,
    "exec",
    "-T",
    E2E_DJANGO_SERVICE,
    "python",
    "manage.py",
    "shell",
  ];
  // execFileSync would be safer than execSync for arg quoting, but we
  // need the snippet on stdin and execSync supports the `input` option
  // cleanly. Wrap each arg in single quotes (compose path has no
  // single quotes; service/file names are alphanumeric).
  const quoted = args.map((a) => `'${a}'`).join(" ");
  return execSync(`docker ${quoted}`, {
    encoding: "utf-8",
    cwd: REPO_ROOT,
    input: dedented + "\n",
    stdio: ["pipe", "pipe", "pipe"],
  });
}

/**
 * Award a tiny throwaway global badge to the named user so the post_save
 * signal fires `broadcast_notification_via_websocket`. Used by the
 * notification subscribe/receive test to prove the consumer delivers a
 * frame end-to-end.
 *
 * The Badge model has a UNIQUE on `name` and the UserBadge model has a
 * unique (user, badge) for global badges, so both names include a
 * timestamp suffix to keep reruns isolated.
 */
export function triggerBadgeNotificationViaDocker(username: string): void {
  const tag = `${Date.now()}-${Math.floor(Math.random() * 1e6)}`;
  runDjangoShell(`
    from django.contrib.auth import get_user_model
    from opencontractserver.badges.models import Badge, UserBadge, BadgeTypeChoices
    User = get_user_model()
    u = User.objects.get(username='${username}')
    b = Badge.objects.create(
        name='E2E WS Badge ${tag}',
        description='Triggered by websocket-auth.spec.ts',
        icon='Award',
        badge_type=BadgeTypeChoices.GLOBAL,
        creator=u,
    )
    UserBadge.objects.create(user=u, badge=b)
    print('badge_awarded')
  `);
}

/**
 * Mark a document public so anonymous WS connections to UnifiedAgentConsumer
 * pass the resource-permission check. Looks up by exact title (RUN_ID
 * suffixes make the test specs unique enough that this is unambiguous).
 */
export function markDocumentPublicViaDocker(documentTitle: string): void {
  runDjangoShell(`
    from opencontractserver.documents.models import Document
    d = Document.objects.get(title='${documentTitle}')
    d.is_public = True
    d.save(update_fields=['is_public'])
    print('document_made_public')
  `);
}

/**
 * Look up the Relay global ID for a document by exact title via Django
 * shell. Bypasses GraphQL entirely so it works even when the page-context
 * fetch is anonymous (the e2e fixture's GraphQL proxy doesn't forward the
 * page's bearer token).
 */
export function getDocumentGlobalIdViaDocker(documentTitle: string): string {
  const out = runDjangoShell(`
    from opencontractserver.documents.models import Document
    from graphql_relay import to_global_id
    d = Document.objects.get(title='${documentTitle}')
    print(to_global_id('DocumentType', d.id))
  `);
  const lines = out
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter((l) => l.length > 0);
  return lines[lines.length - 1];
}

/**
 * Issue a fresh JWT for the given user and return the encoded token.
 * Used by the in-band refresh test to swap an existing socket's auth
 * without forcing the spec to round-trip through the password mutation.
 */
export function issueJwtForUserViaDocker(username: string): string {
  const out = runDjangoShell(`
    from django.contrib.auth import get_user_model
    from graphql_jwt.shortcuts import get_token
    User = get_user_model()
    u = User.objects.get(username='${username}')
    print(get_token(u))
  `);
  // The `print()` line is the LAST non-empty line of stdout; preceding
  // lines are Django's startup banner ("System check identified no issues").
  const lines = out
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter((l) => l.length > 0);
  return lines[lines.length - 1];
}

/**
 * Captured WebSocket activity for a single page session.
 *
 * Use `attachWebSocketCapture(page)` BEFORE navigating and read the
 * `sockets` array after — Playwright's `framereceived` events are
 * delivered synchronously as the page runs, so we need the listeners
 * attached before any socket opens.
 */
export interface CapturedWebSocket {
  url: string;
  /** Frames received from server, parsed as JSON when possible. */
  framesReceived: any[];
  /** Frames sent from client. */
  framesSent: any[];
  /** Close code, populated once the socket closes. */
  closeCode?: number;
  closeReason?: string;
  /** True until `socketclose` fires. */
  closed: boolean;
  /** Raw Playwright handle, used by tests that want to wait for `socketerror`. */
  raw: PWWebSocket;
}

export interface WebSocketCapture {
  /** All sockets opened during the capture window, in open order. */
  sockets: CapturedWebSocket[];
  /** Filter helpers — the spec mostly cares about one consumer at a time. */
  forUrlContains: (substring: string) => CapturedWebSocket[];
}

function tryParseJson(text: string): any {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

/**
 * Attach Playwright's WebSocket listener to the page and start collecting
 * frames into the returned `WebSocketCapture`.
 *
 * Must be called BEFORE the page opens any sockets (typically right after
 * `page.goto`).
 */
export function attachWebSocketCapture(page: Page): WebSocketCapture {
  const sockets: CapturedWebSocket[] = [];

  page.on("websocket", (ws) => {
    const captured: CapturedWebSocket = {
      url: ws.url(),
      framesReceived: [],
      framesSent: [],
      closed: false,
      raw: ws,
    };
    sockets.push(captured);

    ws.on("framereceived", (data) => {
      // Playwright only delivers text frames as `payload`; binary frames
      // arrive as a Buffer. Our consumers all send JSON text, so we
      // prefer the parsed form for ergonomics but fall back to raw.
      const text =
        typeof data.payload === "string"
          ? data.payload
          : data.payload?.toString?.("utf-8") ?? "";
      captured.framesReceived.push(tryParseJson(text));
    });
    ws.on("framesent", (data) => {
      const text =
        typeof data.payload === "string"
          ? data.payload
          : data.payload?.toString?.("utf-8") ?? "";
      captured.framesSent.push(tryParseJson(text));
    });
    ws.on("close", () => {
      captured.closed = true;
    });
    // Playwright's WebSocket close-code surface is limited — the
    // close event fires without code/reason. To capture them, hook
    // into the close inside `page.evaluate` if you need them; in
    // practice the receivedFrames stream + auth-failed frame is the
    // assertion we care about.
  });

  return {
    sockets,
    forUrlContains: (substring) =>
      sockets.filter((s) => s.url.includes(substring)),
  };
}

/**
 * Wait until at least one captured socket whose URL contains `urlSubstring`
 * has received a frame matching `predicate`. Returns the matched frame.
 *
 * Polls the in-memory capture every 100ms — Playwright fires `framereceived`
 * synchronously so a freshly-arrived frame becomes visible to this loop on
 * the next tick.
 */
export async function waitForWsFrame(
  capture: WebSocketCapture,
  urlSubstring: string,
  predicate: (frame: any) => boolean,
  timeoutMs = 15_000
): Promise<any> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    for (const sock of capture.forUrlContains(urlSubstring)) {
      const match = sock.framesReceived.find((f) => predicate(f));
      if (match) return match;
    }
    await new Promise((r) => setTimeout(r, 100));
  }
  throw new Error(
    `Timed out waiting for WS frame matching predicate on URL containing "${urlSubstring}". ` +
      `Sockets captured: ${capture.sockets
        .map((s) => `${s.url} (frames=${s.framesReceived.length})`)
        .join(", ")}`
  );
}

/**
 * Open a raw WebSocket from inside the page, with the supplied subprotocols
 * (or none), wait for the first close event, and return its code + any frames
 * received before it closed.
 *
 * Used by the auth-rejection tests where we want full control over the
 * handshake — the production hooks always include the `opencontracts.jwt.v1`
 * marker, which is exactly what we need to prove can NOT be skipped.
 */
export async function openRawWebSocket(
  page: Page,
  url: string,
  protocols: string[]
): Promise<{ closeCode: number; frames: any[] }> {
  return await page.evaluate(
    ([wsUrl, wsProtocols]) =>
      new Promise<{ closeCode: number; frames: any[] }>((resolve) => {
        const frames: any[] = [];
        // Empty array → omit subprotocol entirely (used by the
        // ?token=... regression test).
        const ws =
          (wsProtocols as string[]).length === 0
            ? new WebSocket(wsUrl as string)
            : new WebSocket(wsUrl as string, wsProtocols as string[]);
        ws.onmessage = (ev) => {
          try {
            frames.push(JSON.parse(ev.data));
          } catch {
            frames.push(ev.data);
          }
        };
        ws.onclose = (ev) => resolve({ closeCode: ev.code, frames });
        ws.onerror = () => {
          // onerror always fires before onclose, so resolve in onclose.
        };
        // Hard ceiling so a hung socket fails the test rather than
        // hanging the run forever. The longest legitimate close path
        // (rate-limit guard then close) takes well under 5s.
        setTimeout(() => {
          try {
            ws.close();
          } catch {}
        }, 8000);
      }),
    [url, protocols] as const
  );
}

/**
 * Resolve the page-side WebSocket URL for the websocket spec.
 *
 * Production hooks build URLs from `window.location` (vite proxies /ws/*
 * to Django:8000 in dev). The spec does the same so we exercise the same
 * code path the production hooks use.
 */
export async function getPageWsBaseUrl(page: Page): Promise<string> {
  return await page.evaluate(() => {
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    return `${proto}://${window.location.host}`;
  });
}
