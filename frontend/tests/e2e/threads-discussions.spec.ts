/**
 * E2E integration test: threads and discussions.
 *
 * Exercises the full discussion-thread user journey end-to-end against
 * the real Vite + Django + Postgres stack:
 *
 *   1. Anonymous /discussions and /threads pages render with their
 *      empty-state chrome (filter pills, search box, section headers).
 *   2. An authenticated user creates a corpus, opens its inline
 *      discussions view, creates a new thread via the modal, posts a
 *      reply, and verifies the message round-trips through the
 *      `createThread` + `createThreadMessage` GraphQL mutations.
 *   3. The newly-created thread shows up in the global /discussions feed
 *      under "Corpus Discussions" — proving the GET_CONVERSATIONS query
 *      with `hasCorpus=true` returns it.
 *
 * Spec ordering: this file's name sorts AFTER `corpus-workflow` and
 * BEFORE `view-interactions`. The tests are self-contained — we create
 * our own corpus rather than relying on data from other specs — so it
 * is safe to run in isolation as well as in the workflow's full sweep.
 */

import { test, expect } from "./fixtures";
import {
  TEST_USER,
  loginViaUI,
  spaNavigate,
  expectViewVisible,
  createCorpusViaUI,
  openCorpusDiscussionsViaUI,
  createThreadViaUI,
  postThreadReplyViaUI,
} from "./helpers";

// Per-run suffix prevents collisions when the same Postgres database is
// reused across CI retries or local re-runs. Mirrors the pattern used in
// `extract-pdf-workflow.spec.ts`.
const RUN_ID = Date.now();
const CORPUS_TITLE = `E2E Discussions Corpus ${RUN_ID}`;
const CORPUS_DESCRIPTION = "Corpus created by the threads/discussions spec.";

const THREAD_TITLE = `Question about contract clauses ${RUN_ID}`;
const THREAD_DESCRIPTION =
  "Looking for guidance on how this clause is typically interpreted.";
const THREAD_INITIAL_MESSAGE = `What does the indemnification clause typically cover in vendor contracts? (${RUN_ID})`;
const THREAD_REPLY_MESSAGE = `In my experience, indemnification covers third-party IP claims and data breach liabilities. (${RUN_ID})`;

test.describe("Threads and discussions", () => {
  /* ─────────────────────────────────────────────────────────────────────
   * Anonymous coverage pass.
   *
   * The discussion list and thread search routes are public — they
   * surface only the user's visible/public threads but the page chrome
   * itself renders for anyone. Hit each route once with no auth so the
   * Istanbul coverage trace records their initial mounts.
   * ────────────────────────────────────────────────────────────────── */
  test.describe("anonymous user", () => {
    test("renders /discussions filter chrome and section headers", async ({
      page,
    }) => {
      await page.goto("/discussions");

      // Page heading.
      await expect(
        page.getByRole("heading", { name: /^Discussions$/ }).first()
      ).toBeVisible({ timeout: 20_000 });

      // FilterTabs render four buttons — ensure the tablist is present
      // even with zero data. We just check the "All" tab as a smoke
      // signal; the per-tab labels live in the rendered DOM as plain
      // text inside <button>s.
      await expect(page.getByText(/^All$/).first()).toBeVisible();

      // SearchBox placeholder as a stable identifier for the search input.
      await expect(
        page.getByPlaceholder(/Search discussions/i).first()
      ).toBeVisible();

      // The three section headers always render in the "all" tab even
      // when their counts are zero. Only check the first to avoid
      // ordering flakes.
      await expect(page.getByText(/Corpus Discussions/i).first()).toBeVisible({
        timeout: 10_000,
      });
    });

    test("renders /threads search route", async ({ page }) => {
      await page.goto("/threads");

      await expect(
        page.getByRole("heading", { name: /Search Discussions/i }).first()
      ).toBeVisible({ timeout: 20_000 });

      // ThreadSearch's SearchBar exposes its placeholder; this is the
      // most stable handle for the input.
      await expect(
        page.getByPlaceholder(/Search discussions by keywords/i).first()
      ).toBeVisible();
    });
  });

  /* ─────────────────────────────────────────────────────────────────────
   * Authenticated flow.
   *
   * One serial test that walks the entire create-thread / post-reply /
   * verify-listing journey. SPA-navigation (history.pushState +
   * popstate) preserves the in-memory authToken across views — a
   * full page.goto would tear down the React tree and lose it.
   * ────────────────────────────────────────────────────────────────── */
  test.describe("authenticated user", () => {
    test("creates a corpus thread, replies, and sees it in the global feed", async ({
      page,
    }) => {
      // ── Step 1: Login ────────────────────────────────────────────
      await test.step("login", async () => {
        await loginViaUI(page, TEST_USER.username, TEST_USER.password);
      });

      // ── Step 2: Create a corpus to host the discussion ───────────
      await test.step("create corpus to host thread", async () => {
        await createCorpusViaUI(page, CORPUS_TITLE, CORPUS_DESCRIPTION);
      });

      // ── Step 3: Open corpus discussions view ─────────────────────
      await test.step("open corpus discussions inline view", async () => {
        await openCorpusDiscussionsViaUI(page, CORPUS_TITLE);
      });

      // ── Step 4: Create a thread via the modal ────────────────────
      await test.step("create new thread via modal", async () => {
        await createThreadViaUI(
          page,
          THREAD_TITLE,
          THREAD_DESCRIPTION,
          THREAD_INITIAL_MESSAGE
        );

        // The thread description appears in the ThreadDetail header
        // (compact mode), and the initial message shows up in the
        // message list immediately after creation.
        await expect(
          page.getByText(THREAD_INITIAL_MESSAGE).first()
        ).toBeVisible({ timeout: 15_000 });
      });

      // ── Step 5: Reply to the thread ──────────────────────────────
      await test.step("post a reply to the thread", async () => {
        await postThreadReplyViaUI(page, THREAD_REPLY_MESSAGE);

        // Both the original initial message and the reply must be
        // individually visible after the GraphQL refetch — that's a
        // direct check on the thread state rather than coupling to the
        // exact "N messages" header phrasing.
        await expect(
          page.getByText(THREAD_INITIAL_MESSAGE).first()
        ).toBeVisible({ timeout: 15_000 });
        await expect(page.getByText(THREAD_REPLY_MESSAGE).first()).toBeVisible({
          timeout: 15_000,
        });
      });

      // ── Step 6: Back to thread list and verify it's listed ───────
      await test.step("return to thread list and verify entry", async () => {
        // The compact ThreadDetail header has a back button with
        // aria-label="Back to discussions".
        await page
          .getByRole("button", { name: /Back to discussions/i })
          .first()
          .click();

        // The list view reuses ThreadList; each card has
        // role="article" + aria-label="Thread: <title>".
        await expect(
          page.getByRole("article", {
            name: new RegExp(`Thread:\\s*${THREAD_TITLE}`, "i"),
          })
        ).toBeVisible({ timeout: 15_000 });
      });

      // ── Step 7: Confirm thread shows in global /discussions feed ─
      await test.step("verify thread surfaces in global discussions", async () => {
        await spaNavigate(page, "/discussions");

        await expectViewVisible(page, {
          kind: "anyText",
          texts: [/^Discussions$/i, /Search discussions/i],
        });

        // The "Corpus Discussions" section is server-filtered by
        // hasCorpus=true. Our newly-created thread MUST appear there.
        // ThreadListItem renders the title as a heading-ish styled
        // <ThreadTitle> — match by visible text + the role="article"
        // wrapper that ThreadListItem provides.
        await expect(
          page.getByRole("article", {
            name: new RegExp(`Thread:\\s*${THREAD_TITLE}`, "i"),
          })
        ).toBeVisible({ timeout: 20_000 });
      });

      // ── Step 8: Click the thread from the global feed ────────────
      await test.step("open the thread by clicking from the global feed", async () => {
        // Clicking a ThreadListItem navigates to the corpus thread URL
        // (ThreadListItem builds a slug-based href via getCorpusThreadUrl).
        // Since it's an SPA navigation, the in-memory authToken survives.
        await page
          .getByRole("article", {
            name: new RegExp(`Thread:\\s*${THREAD_TITLE}`, "i"),
          })
          .first()
          .click();

        // We land back on the thread detail; both messages should be
        // fetched via GET_THREAD_DETAIL and visible.
        await expect(
          page.getByRole("heading", { name: THREAD_TITLE }).first()
        ).toBeVisible({ timeout: 20_000 });
        await expect(
          page.getByText(THREAD_INITIAL_MESSAGE).first()
        ).toBeVisible();
        await expect(
          page.getByText(THREAD_REPLY_MESSAGE).first()
        ).toBeVisible();
      });
    });
  });
});
