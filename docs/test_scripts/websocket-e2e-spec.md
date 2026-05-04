# Test: WebSocket auth handshake e2e spec

## Purpose

Verifies the full real-browser → Vite proxy → Daphne ASGI → consumer
pipeline for the new `Sec-WebSocket-Protocol`-based JWT transport
introduced by PR #1502. The Python-side coverage in
`opencontractserver/tests/test_websocket_auth.py` exercises the
middleware + `AuthHandshakeMixin` against Channels'
`WebsocketCommunicator`, which bypasses the actual browser handshake,
the Vite proxy, and Daphne's scope assembly. This spec closes that gap.

## Prerequisites

- The local stack is running with **Daphne** (not `runserver`):
  ```bash
  docker compose -f local.yml up -d
  ```
- Migrations have run so the `admin` superuser exists with the password
  in `.envs/.local/.django` (or `Openc0ntracts_def@ult` in CI).
- The frontend dev server is reachable on `http://127.0.0.1:5173`
  (Playwright's `webServer` block boots it automatically).

## Auth-only run (no LLM, no cassette)

The notification, `?token=` regression, and anonymous-rejection tests
do not touch the LLM. Run them locally without VCR setup:

```bash
cd frontend
yarn playwright test --grep "WebSocket auth handshake" \
  --grep-invert "authenticated query streams" \
  --reporter=list
```

This subset:

- Logs in, asserts AUTH_OK + CONNECTED on `ws/notification-updates/`
  with `anonymous: false`.
- Triggers a real BADGE award via `docker compose exec` and asserts
  the resulting `NOTIFICATION_CREATED` frame arrives on the open
  socket.
- Opens a marker-only (no token) socket and asserts close 4001.
- Opens a `?token=…` URL (no subprotocol) with a real JWT and asserts
  the consumer ignores it (close 4001), proving the URL transport is
  fully removed.
- Uploads a private doc, then opens an anonymous socket against its
  agent-chat URL, asserts close 4003.
- Opens an anonymous agent-chat socket against a public document,
  sends an in-band `AUTH` frame with a fresh JWT, asserts AUTH_OK
  with `refreshed: true` and exactly one socket was opened (no
  reconnect churn).

## Full run (with cassette)

The `agent ws: authenticated query streams AUTH_OK then ASYNC_FINISH`
test exercises the LLM path. It is gated on `OC_LLM_VCR_MODE=replay`
and a cassette at:

```
opencontractserver/tests/fixtures/cassettes/e2e_websocket_auth/agent_chat.yaml
```

### First-time recording

To record the cassette (one-time, then commit):

1. Start the local stack with VCR in `record` mode and a real key:
   ```bash
   export OPENAI_API_KEY=sk-...your-real-key...
   export OC_LLM_VCR_MODE=record
   export OC_LLM_VCR_CASSETTE=/app/opencontractserver/tests/fixtures/cassettes/e2e_websocket_auth/agent_chat.yaml
   docker compose -f local.yml -f local.e2e-coverage.yml up -d
   ```
2. Run the full spec (will hit OpenAI):
   ```bash
   cd frontend
   OC_LLM_VCR_MODE=record \
   E2E_TEST_PASSWORD=Openc0ntracts_def@ult \
   yarn playwright test --grep "WebSocket auth handshake" --reporter=list
   ```
3. Confirm the cassette file exists and commit it:
   ```bash
   git add opencontractserver/tests/fixtures/cassettes/e2e_websocket_auth/agent_chat.yaml
   ```

### Replay mode (default in CI)

```bash
OC_LLM_VCR_MODE=replay \
E2E_TEST_PASSWORD=Openc0ntracts_def@ult \
yarn playwright test --grep "WebSocket auth handshake" --reporter=list
```

The CI workflow `.github/workflows/frontend-e2e-websocket.yml` does
this automatically with a fake `OPENAI_API_KEY` so any cassette miss
fails loudly.

## Expected Results

- All non-LLM tests pass on a fresh local stack.
- The LLM-gated test passes when `OC_LLM_VCR_MODE=replay` AND the
  cassette is present. It is skipped otherwise.
- Coverage for `config/websocket/**`, `frontend/src/utils/websocketAuth.ts`,
  `frontend/src/hooks/useWebSocketAuth.ts`, `frontend/src/hooks/useNotificationWebSocket.ts`,
  `frontend/src/hooks/useAgentChat.ts`, and
  `frontend/src/components/chat/get_websockets.ts` is uploaded to Codecov
  under flags `frontend-e2e,frontend,websocket` and `backend-e2e,websocket`.

## Cleanup

The spec uses `Date.now()` suffixes for corpus / document names so reruns
do not collide with prior runs. To wipe everything between local runs:

```bash
docker compose -f local.yml down -v
```

This destroys the postgres volume and starts fresh on the next
`docker compose up`.
