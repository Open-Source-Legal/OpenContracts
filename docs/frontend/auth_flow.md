# Frontend authentication flow

Auth0 authentication uses the official `@auth0/auth0-react` SDK and Universal
Login in the same browser tab. The SDK handles authorization code exchange with
PKCE, OAuth state, token expiry, and refresh-token rotation. OpenContracts never
collects Auth0 passwords or embeds the hosted page in an iframe.

## Session lifecycle

Django cookie sessions are created only by the admin login view
(`config/admin_auth/views.py`): password logins are tagged with `ModelBackend`
and Auth0 token logins with `Auth0AdminBackend`, both of which restore sessions
through `ModelBackend.get_user` and reject deactivated accounts. The header-only
JWT backends never create sessions; their `get_user` shares
`config/jwt_auth/shortcuts.py::get_active_user` so a session tagged with them
would behave the same. Disabling an account removes its authenticated access on
the next request; public access and other valid credentials are unaffected.

1. `AuthGate` waits for the SDK's `isLoading` state to settle. In local-password
   deployments it instead reads a candidate JWT from sessionStorage.
2. AuthGate clears the old Apollo store before publishing credentials.
3. `useBackendSession` sends a `GET_ME` request with that credential and
   `fetchPolicy: "no-cache"`. A stored token or SDK profile alone does not grant
   access to authenticated controls.
4. A successful response populates both `backendUserObj` and the compatibility
   `userObj`, then sets `authStatusVar` to `AUTHENTICATED`. A successful local
   `tokenAuth` response also supplies a backend identity immediately.
5. `authInitCompleteVar` signals that initialization has settled, allowing routing
   and subscriptions to proceed. Navigation and protected actions use the
   validated identity, including extracts, label sets, analyses, and power mode.

A successful response with `me: null` invalidates the session. A missing response,
network failure, or server error is not evidence of revocation: initial validation
has a 15-second deadline and offers **Retry** and **Continue signed out**. The login
button remains available after failure. Background checks on reconnection and tab
visibility preserve mounted editors and the last validated identity during outages.
A later `me: null` still clears the session.

An unchanged background response preserves the identity object's reference, so
open profile forms keep unsaved edits. If silent SSO returns a different backend
user ID, the application advances the session epoch and clears the old identity,
cache, dialogs, and route entities before validating the replacement account.
The SDK keeps the replacement account signed in during this transition.

## Storage and refresh behavior

Auth0 uses the SDK's built-in memory cache. Access and refresh tokens are not
written to localStorage. On rollout, the current client's legacy SDK localStorage
entries are removed. The existing audience, scopes, and backend bearer-token
handling remain unchanged.

Refresh-token rotation remains enabled. After a page reload, the SDK can attempt
silent SSO using its iframe fallback, with a 10-second authorization timeout. If
browser cookie restrictions prevent restoration, the user can click **Login** to
continue through same-tab Universal Login. There is no automatic redirect or
reload loop. In-memory storage intentionally does not promise persistence across
browser restarts or tabs.

Local-password JWTs use sessionStorage so refresh works within the tab, with a
fixed 24-hour restoration deadline and a binding to the configured API URL. No
profile or privilege fields are persisted. The backend still determines the JWT's
actual validity; the restoration deadline cannot extend it. Legacy localStorage
sessions are discarded. Blocked storage falls back to a login for the current page;
malformed data and cleanup failures never prevent initialization.

sessionStorage is still readable by application JavaScript. This limits persistence
but does not make a local JWT immune to XSS. Moving tokens to HttpOnly cookies would
require a separate backend change.

## Requests, failures, and logout

`authLink` asks the Auth0 SDK for an access token before authenticated GraphQL
requests. The SDK caches or renews it as needed; the shared token is updated for
WebSocket consumers. Backend identity checks first ask the SDK to renew if needed,
then are pinned to the resulting candidate token.
Anonymous requests omit Authorization, including any stale header from a reused
operation context.

`errorLink` invalidates sessions for HTTP/GraphQL 401, `UNAUTHENTICATED`, and known
JWT authentication errors. HTTP/GraphQL 403 and ordinary permission-denied messages
preserve the session. Expired credentials prompt sign-in without reloading or
replaying mutations.

`clearAuthSession` clears tokens, both identities, saved local credentials, and
Apollo cache data. AuthGate also calls the SDK's `logout({ openUrl: false })` for
invalid sessions. Explicit Auth0 logout uses the SDK's normal logout redirect.
Login/logout generations prevent late requests and identity checks from reviving
an older session or caching its data. The route manager clears route entities
before paint and fetches fresh data for the new viewer; it does not reuse a lazy
query's previous result from an earlier login.

Cleanup closes `authInitCompleteVar` before advancing the session epoch. Routing,
identity validation, and gated content wait for all asynchronous cleanup handlers
to settle, including overlapping invalidations. Document modals live inside
`AuthGate` so their initial queries cannot be canceled by the startup cache reset.

Login return paths preserve application queries and fragments. They must resolve
to this origin, cannot contain backslashes/control characters, and exclude OAuth
callback parameters. Successful and failed callbacks replace the callback URL in
history.

## Auth0 configuration

Keep the application's origin in **Allowed Callback URLs**, **Allowed Logout
URLs**, and **Allowed Web Origins**. Keep **Refresh Token Rotation** enabled on the
SPA and **Allow Offline Access** enabled on the API. No client secret belongs in
the frontend. See [authentication configuration](../configuration/authentication.md).

These choices follow Auth0's [React SDK documentation](https://auth0.com/docs/libraries/auth0-react),
[hosted versus embedded login guidance](https://auth0.com/docs/authenticate/login/universal-vs-embedded-login),
and [token storage recommendations](https://auth0.com/docs/secure/security-guidance/data-security/token-storage).
