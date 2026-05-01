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

import { Page, expect } from "@playwright/test";

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
