/**
 * E2E integration test: WebSocket auth handshake (PR #1502).
 *
 * Verifies the full real-browser → Vite proxy → Daphne ASGI → consumer
 * pipeline for the new `Sec-WebSocket-Protocol`-based JWT transport. The
 * unit/integration coverage in `opencontractserver/tests/test_websocket_auth.py`
 * exercises the middleware + AuthHandshakeMixin against Channels'
 * `WebsocketCommunicator` — that's the right tool for protocol-level
 * assertions but it bypasses the actual browser handshake. This spec
 * covers the gap by:
 *
 *   1. Driving real `new WebSocket(url, protocols)` calls from the page,
 *      so subprotocol negotiation, header propagation through the Vite
 *      proxy, and Daphne's ASGI scope assembly are all exercised.
 *   2. Asserting on actual frames captured via Playwright's
 *      `page.on('websocket')`, so AUTH_OK / AUTH_FAILED / NOTIFICATION_*
 *      payloads are the source of truth (no mocks).
 *   3. Triggering server-side state changes (badge award) via a Django
 *      shell snippet so the real signal-driven broadcast path runs.
 *
 * Coverage by consumer:
 *
 *   * NotificationUpdatesConsumer
 *       - Authenticated subscribe + AUTH_OK
 *       - End-to-end NOTIFICATION_CREATED on badge award
 *       - Anonymous (no token) closes 4001
 *
 *   * UnifiedAgentConsumer
 *       - Authenticated chat sends AUTH_OK with anonymous=false, then
 *         streams ASYNC_FINISH (LLM call replayed from VCR cassette)
 *       - Anonymous on private doc closes 4003
 *       - In-band AUTH refresh swaps the user without socket churn
 *
 *   * Hard-cutover regression
 *       - `?token=…` URL parameter is ignored (anonymous → close)
 *
 * The LLM-touching test is gated by the presence of the cassette at
 * `opencontractserver/tests/fixtures/cassettes/e2e_websocket_auth/agent_chat.yaml`
 * and the `OC_LLM_VCR_MODE=replay` env var. The auth-only tests run
 * unconditionally and need no LLM access.
 */

import { test, expect } from "./fixtures";
import {
  TEST_USER,
  loginViaUI,
  uploadDocumentViaUI,
  createCorpusViaUI,
  waitForDocumentReady,
  spaNavigate,
  attachWebSocketCapture,
  waitForWsFrame,
  openRawWebSocket,
  getPageWsBaseUrl,
  triggerBadgeNotificationViaDocker,
  markDocumentPublicViaDocker,
  issueJwtForUserViaDocker,
  getDocumentGlobalIdViaDocker,
} from "./helpers";

// Unique per-run names so back-to-back local runs don't collide on
// existing rows. Same convention as extract-pdf-workflow.spec.ts.
const RUN_ID = Date.now();
const CORPUS_TITLE = `E2E WS Auth Corpus ${RUN_ID}`;
const DOC_TITLE = `E2E WS Auth Doc ${RUN_ID}`;
const DOC_CONTENT =
  "This is a test document used by the websocket-auth e2e spec. " +
  "The agent only needs SOME text to embed and answer against.";

test.describe("WebSocket auth handshake (full-stack)", () => {
  // The whole spec needs the local stack with Daphne (not test.yml's
  // runserver). The workflow boots `local.yml` before invoking us;
  // local devs need to do the same.
  //
  // We also gate the entire describe behind OC_RUN_WS_E2E so that the
  // generic `Frontend E2E Integration` workflow (which globs every
  // `tests/e2e/*.spec.ts`) doesn't pick this spec up — it runs against
  // `test.yml`'s runserver, which doesn't speak WebSockets, and the
  // helpers' `docker compose -f local.yml exec` calls would all fail.
  // The dedicated `Frontend E2E WebSocket Auth (VCR)` workflow sets
  // OC_RUN_WS_E2E=true.
  test.skip(
    process.env.OC_RUN_WS_E2E !== "true",
    "Set OC_RUN_WS_E2E=true to run; needs the local.yml stack (Daphne)."
  );

  test.setTimeout(15 * 60 * 1000);

  // ───────────────────────────────────────────────────────────────────
  // Notifications consumer — authenticated subscribe + receive
  // ───────────────────────────────────────────────────────────────────
  test("notification ws: authenticated subscribe receives AUTH_OK + CONNECTED + NOTIFICATION_CREATED", async ({
    page,
  }) => {
    // Capture frames BEFORE login navigates the page so we don't miss
    // any sockets that open during boot.
    const capture = attachWebSocketCapture(page);

    await loginViaUI(page, TEST_USER.username, TEST_USER.password);

    // The notification hook is wired into authenticated boot via
    // useBadgeNotifications / useExtractCompletionNotification /
    // useJobNotifications. Any of them opens the same shared socket
    // through `useWebSocketAuth`. Wait for AUTH_OK on that socket.
    const authOk = await waitForWsFrame(
      capture,
      "/ws/notification-updates/",
      (f) => f && f.type === "AUTH_OK",
      30_000
    );
    expect(authOk.anonymous).toBe(false);
    expect(authOk.username).toBe(TEST_USER.username);

    // The consumer also sends a CONNECTED frame post-accept with the
    // session id — proves the consumer ran past `accept_with_auth()`
    // (the AUTH_OK alone is from the mixin, before the consumer's own
    // setup completes).
    await waitForWsFrame(
      capture,
      "/ws/notification-updates/",
      (f) => f && f.type === "CONNECTED",
      10_000
    );

    // Now trigger a real badge award server-side. The post_save signal
    // calls broadcast_notification_via_websocket, which fans out to the
    // user's notification group → our open socket should receive a
    // NOTIFICATION_CREATED frame.
    triggerBadgeNotificationViaDocker(TEST_USER.username);

    const created = await waitForWsFrame(
      capture,
      "/ws/notification-updates/",
      (f) => f && f.type === "NOTIFICATION_CREATED",
      20_000
    );
    expect(created.notificationType).toBe("BADGE");
    expect(created.notificationId).toBeTruthy();
  });

  // ───────────────────────────────────────────────────────────────────
  // Notifications consumer — anonymous rejection
  // ───────────────────────────────────────────────────────────────────
  //
  // IMPORTANT: real browsers see close code 1006 here, NOT the
  // application-level 4001. NotificationUpdatesConsumer.connect() calls
  // `self.close(code=4001)` BEFORE `accept()` when the user isn't
  // authenticated — Channels translates a pre-accept close into an HTTP
  // 403 handshake rejection, which the browser surfaces as 1006
  // (abnormal close) regardless of the application code. The
  // `WebsocketCommunicator` tests in `test_websocket_auth.py` see the
  // 4001 directly because Channels exposes the intended code to its
  // test runner, but the wire-level browser behavior is different.
  //
  // For our purposes the assertion is: the connection is REJECTED
  // (anything other than 1000 normal-close). 1006 is the only
  // legitimate value here today; we match it explicitly so a future
  // change to accept-then-close (which WOULD let the browser see 4001)
  // is caught and the test gets updated rather than silently passing.
  test("notification ws: anonymous (marker only, no token) is rejected", async ({
    page,
  }) => {
    // The page itself doesn't need to be authenticated for this test —
    // we open a raw socket directly. We still need to land on a same-
    // origin page so the ws URL is reachable through Vite's proxy.
    await page.goto("/");

    const wsBase = await getPageWsBaseUrl(page);
    // Marker-only subprotocol: no token. Consumer must reject because
    // notification_updates requires an authenticated user (it does NOT
    // use allow_anonymous).
    const result = await openRawWebSocket(
      page,
      `${wsBase}/ws/notification-updates/`,
      ["opencontracts.jwt.v1"]
    );
    expect(result.closeCode).toBe(1006);
    // Sanity: no AUTH_OK frame should ever have been delivered for an
    // unauthenticated connection.
    expect(result.frames.some((f: any) => f && f.type === "AUTH_OK")).toBe(
      false
    );
  });

  // ───────────────────────────────────────────────────────────────────
  // Hard-cutover regression: ?token=… in URL must NOT authenticate.
  // ───────────────────────────────────────────────────────────────────
  test("notification ws: ?token=… URL parameter is ignored (rejected anonymous)", async ({
    page,
  }) => {
    await page.goto("/");

    // Issue a real, valid token but place it in the URL query string
    // (the deprecated transport). The consumer must treat the
    // connection as anonymous and reject the handshake.
    const validToken = issueJwtForUserViaDocker(TEST_USER.username);
    const wsBase = await getPageWsBaseUrl(page);

    // No subprotocol marker either — proves the URL fallback was
    // removed completely. Consumer drops to anonymous → reject.
    // (See the long comment on the previous test for why we expect
    // 1006 rather than the application-level 4001.)
    const result = await openRawWebSocket(
      page,
      `${wsBase}/ws/notification-updates/?token=${encodeURIComponent(
        validToken
      )}`,
      []
    );
    expect(result.closeCode).toBe(1006);
    expect(result.frames.some((f: any) => f && f.type === "AUTH_OK")).toBe(
      false
    );
  });

  // ───────────────────────────────────────────────────────────────────
  // UnifiedAgentConsumer — anonymous on private doc rejected
  // ───────────────────────────────────────────────────────────────────
  // Same pre-accept-close caveat as the notification anonymous test:
  // the consumer's intent is close-code 4003, but the browser sees
  // 1006 because the close happens before the WS handshake completes.
  // The application-level 4003 is asserted in
  // `test_websocket_auth.py::test_middleware_without_token`.
  test("agent ws: anonymous on private corpus is rejected", async ({
    page,
  }) => {
    // Setup: log in, create a private corpus + document so we have a
    // resource the anonymous request can be denied against.
    const setupCorpusTitle = `${CORPUS_TITLE}-priv`;
    await loginViaUI(page, TEST_USER.username, TEST_USER.password);
    await createCorpusViaUI(
      page,
      setupCorpusTitle,
      "Private corpus for agent-ws anon-rejection test"
    );
    await uploadDocumentViaUI(
      page,
      "ws-anon-reject.txt",
      DOC_CONTENT,
      `${DOC_TITLE}-priv`,
      "Private doc for agent-ws anon-rejection test",
      setupCorpusTitle
    );
    await waitForDocumentReady(page, `${DOC_TITLE}-priv`);

    // Resolve the document's Relay global ID via Django shell. We avoid
    // GraphQL here because the e2e fixture's request-router proxies any
    // page-context fetch through Node's fetch with CSRF-only headers
    // (no bearer token), and the documents resolver scopes anonymous
    // queries to public docs — which this private one is NOT.
    const docPk = getDocumentGlobalIdViaDocker(`${DOC_TITLE}-priv`);
    expect(docPk).toBeTruthy();

    // Now open a fresh anonymous browser context (no authToken) and
    // try to chat against the private doc. The consumer's connect()
    // path calls `_validate_resource_permissions` which closes 4003.
    const anonContext = await page.context().browser()!.newContext();
    const anonPage = await anonContext.newPage();
    try {
      await anonPage.goto("/");
      const wsBase = await getPageWsBaseUrl(anonPage);
      const url = `${wsBase}/ws/agent-chat/?document_id=${encodeURIComponent(
        docPk as string
      )}`;
      const result = await openRawWebSocket(anonPage, url, [
        "opencontracts.jwt.v1",
      ]);
      expect(result.closeCode).toBe(1006);
      expect(result.frames.some((f: any) => f && f.type === "AUTH_OK")).toBe(
        false
      );
    } finally {
      await anonContext.close();
    }
  });

  // ───────────────────────────────────────────────────────────────────
  // UnifiedAgentConsumer — authenticated chat completes (LLM via VCR)
  // ───────────────────────────────────────────────────────────────────
  test("agent ws: authenticated query streams AUTH_OK then ASYNC_FINISH (VCR)", async ({
    page,
  }) => {
    // Run when VCR is active in either mode:
    //   * `replay` — CI default, cassette must exist
    //   * `record` — local cassette refresh, requires real OPENAI_API_KEY
    // Skip otherwise so contributors don't need an OpenAI key just to
    // run the auth-only subset of the spec.
    const vcrMode = (process.env.OC_LLM_VCR_MODE || "").toLowerCase();
    test.skip(
      vcrMode !== "replay" && vcrMode !== "record",
      "Requires OC_LLM_VCR_MODE=replay or record + cassette under " +
        "opencontractserver/tests/fixtures/cassettes/e2e_websocket_auth/"
    );

    const capture = attachWebSocketCapture(page);

    await loginViaUI(page, TEST_USER.username, TEST_USER.password);
    await createCorpusViaUI(
      page,
      CORPUS_TITLE,
      "Corpus for agent-ws authenticated chat test"
    );
    await uploadDocumentViaUI(
      page,
      "ws-auth.txt",
      DOC_CONTENT,
      DOC_TITLE,
      "Doc for agent-ws authenticated chat test",
      CORPUS_TITLE
    );
    await waitForDocumentReady(page, DOC_TITLE);

    // Open the corpus, find the InlineChatBar on the landing view, type
    // a query, and submit. Corpuses.tsx wires the bar's onSubmit to set
    // `chatExpanded=true`, which mounts CorpusChat → useAgentChat →
    // useWebSocketAuth → opens the `/ws/agent-chat/` socket. We use the
    // visible placeholder text (stable copy in InlineChatBar.tsx) as
    // the locator anchor — the generated `data-testid` depends on a
    // parent's `testId` prop that varies with corpus mode.
    await spaNavigate(page, "/corpuses");
    await page.getByText(CORPUS_TITLE).first().click();
    await expect(page).toHaveURL(/\/c\/[^/]+\/[^/?#]+/, { timeout: 15_000 });

    const inlineInput = page
      .getByPlaceholder(/Ask a question about this corpus/i)
      .first();
    await expect(inlineInput).toBeVisible({ timeout: 30_000 });
    await inlineInput.fill("What is this document about?");
    await page.keyboard.press("Enter");

    // Wait for AUTH_OK on the agent-chat socket. Mounting CorpusChat
    // and the websocket handshake takes a moment.
    const authOk = await waitForWsFrame(
      capture,
      "/ws/agent-chat/",
      (f) => f && f.type === "AUTH_OK",
      45_000
    );
    expect(authOk.anonymous).toBe(false);

    // CorpusChat re-sends the seed query on mount. The unified
    // consumer streams ASYNC_START → ASYNC_CONTENT* → ASYNC_FINISH.
    // ASYNC_FINISH is the success terminus.
    await waitForWsFrame(
      capture,
      "/ws/agent-chat/",
      (f) => f && f.type === "ASYNC_FINISH",
      120_000
    );
  });

  // ───────────────────────────────────────────────────────────────────
  // In-band AUTH refresh — token rotation must NOT churn the socket
  // ───────────────────────────────────────────────────────────────────
  test("agent ws: in-band AUTH refresh swaps user without reconnect (Auth0 silent renewal sim)", async ({
    page,
  }) => {
    // Setup a public document so an anonymous initial connection succeeds
    // — that lets us upgrade to authenticated via an in-band AUTH frame
    // without needing to hold a valid token at connect time.
    const refreshCorpusTitle = `${CORPUS_TITLE}-refresh`;
    const refreshDocTitle = `${DOC_TITLE}-refresh`;
    await loginViaUI(page, TEST_USER.username, TEST_USER.password);
    await createCorpusViaUI(
      page,
      refreshCorpusTitle,
      "Corpus for in-band auth refresh test"
    );
    await uploadDocumentViaUI(
      page,
      "ws-refresh.txt",
      DOC_CONTENT,
      refreshDocTitle,
      "Doc for in-band refresh test",
      refreshCorpusTitle
    );
    await waitForDocumentReady(page, refreshDocTitle);

    // Mark the doc public so an anonymous connection passes the
    // resource permission check.
    markDocumentPublicViaDocker(refreshDocTitle);

    // Look up the document's global id via Django shell — even though
    // the doc is now public, going through GraphQL costs us a round-trip
    // and the shell helper is faster + more deterministic.
    const docId = getDocumentGlobalIdViaDocker(refreshDocTitle);
    expect(docId).toBeTruthy();

    // Mint a fresh JWT for our test user (will be sent in the AUTH frame).
    const freshToken = issueJwtForUserViaDocker(TEST_USER.username);

    await page.goto("/");
    const wsBase = await getPageWsBaseUrl(page);

    // Open the socket anonymously, send AUTH frame with the real token,
    // assert AUTH_OK with `refreshed: true` (the second AUTH_OK — the
    // first one is the initial-accept frame from the mixin).
    const result = await page.evaluate(
      async ([wsUrl, token]) => {
        return await new Promise<{
          framesReceived: any[];
          framesSent: any[];
          closeCode: number | null;
        }>((resolve) => {
          const framesReceived: any[] = [];
          const framesSent: any[] = [];
          let closeCode: number | null = null;
          const ws = new WebSocket(wsUrl as string, ["opencontracts.jwt.v1"]);
          ws.onmessage = (ev) => {
            try {
              const obj = JSON.parse(ev.data);
              framesReceived.push(obj);
              // Once we see the *initial* AUTH_OK (anonymous=true,
              // refreshed=false), send the AUTH refresh frame.
              if (
                obj.type === "AUTH_OK" &&
                obj.refreshed === false &&
                obj.anonymous === true
              ) {
                const msg = JSON.stringify({ type: "AUTH", token });
                framesSent.push(JSON.parse(msg));
                ws.send(msg);
              }
              // Once we see the refreshed AUTH_OK we're done — close cleanly.
              if (obj.type === "AUTH_OK" && obj.refreshed === true) {
                ws.close(1000, "test done");
              }
            } catch {
              framesReceived.push(ev.data);
            }
          };
          ws.onclose = (ev) => {
            closeCode = ev.code;
            resolve({ framesReceived, framesSent, closeCode });
          };
          // Safety timeout.
          setTimeout(() => {
            try {
              ws.close();
            } catch {}
          }, 12000);
        });
      },
      [
        `${wsBase}/ws/agent-chat/?document_id=${encodeURIComponent(
          docId as string
        )}`,
        freshToken,
      ] as const
    );

    // Initial AUTH_OK was anonymous; refresh AUTH_OK should not be.
    const authOks = result.framesReceived.filter(
      (f: any) => f && f.type === "AUTH_OK"
    );
    expect(authOks.length).toBeGreaterThanOrEqual(2);
    expect(authOks[0].anonymous).toBe(true);
    expect(authOks[0].refreshed).toBe(false);
    expect(authOks[authOks.length - 1].refreshed).toBe(true);
    expect(authOks[authOks.length - 1].anonymous).toBe(false);
    // We exactly sent ONE AUTH frame — proves no churn was needed.
    expect(
      result.framesSent.filter((f: any) => f?.type === "AUTH").length
    ).toBe(1);
    // Clean close — refresh path didn't error.
    expect(result.closeCode).toBe(1000);
  });
});
