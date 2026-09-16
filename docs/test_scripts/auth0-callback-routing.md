# Test: Auth0 callbacks survive frontend initialization

## Purpose

Verify that `Auth0ProviderWithHistory` lets the SDK consume an OAuth callback
before application routing effects run, preserves the login return path, and
surfaces failed callbacks.

## Prerequisites

- An Auth0-enabled frontend with its origin allowed in Auth0's callback settings.
- Browser developer tools with **Preserve log** enabled in the Network tab.
- For the automated regression: installed frontend dependencies.

## Steps

1. Open the frontend in a fresh browser context and click **Login**. Auth0's
   `/authorize` request should lead to Universal Login. With an existing SSO
   session, Auth0 may immediately return to the application instead.
2. Complete login, starting from `/documents` to exercise the return path.
   Observe the callback containing `code` and `state`. Before application URL
   synchronization runs, the SDK should send an authorization-code exchange to
   Auth0's `/oauth/token` endpoint.
3. Confirm that callback parameters disappear, the browser returns to
   `/documents`, and GraphQL `GetMe` runs with an Authorization header. A non-null
   backend identity should enable signed-in navigation. Do not copy access tokens,
   authorization codes, or complete token responses into logs or issue reports.
4. In a separate disposable browser context, visit
   `/?error=access_denied&error_description=Callback+diagnostic&state=diagnostic`.
   The app should display **Sign-in could not be completed. Please try again.**,
   clean the callback URL, and allow anonymous browsing and a new login attempt.
5. Run the automated regression, which uses the real React SDK and router with
   a simulated token endpoint and backend:

   ```bash
   cd frontend
   ./node_modules/.bin/vitest run src/utils/Auth0ProviderWithHistory.test.tsx
   ```

## Expected results

Both successful and failed callbacks are consumed before application effects
can rewrite their query parameters. Backend validation still determines whether
the user is signed in. Ordinary anonymous startup completes without a token
exchange or error.

Before the fix, the regression's code exchange never starts and its OAuth error
never appears. The production bundle `index-BpSUWDBR.js` was also observed
rewriting a synthetic error callback to `/?selectedOnly=true` and then `/`
without displaying an authentication error; its fresh-browser login redirect
successfully reached Auth0 Universal Login. No production account was used.

## Cleanup

Close the disposable browser contexts. Automated tests use synthetic credentials
and do not contact Auth0 or the production backend.
