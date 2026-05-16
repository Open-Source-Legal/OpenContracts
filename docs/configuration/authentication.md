# Authentication Configuration

OpenContracts supports two authentication methods:

1. **Password authentication** (Django-based) -- simple, no external dependencies
2. **Auth0 authentication** (OAuth2/OIDC) -- supports self-registration, SSO, and social logins

Both methods work for the main frontend application and the Django admin dashboard.
You choose one method per deployment via environment variables.

---

## Option 1: Password Authentication (Default)

Password auth uses Django's built-in authentication system. Users are created manually
by an administrator -- there is no self-registration.

### Backend Configuration

Set the following in your backend environment file (`.envs/.local/.django` or `.envs/.production/.django`):

```bash
USE_AUTH0=False

# Initial admin account (set BEFORE first boot)
DJANGO_SUPERUSER_USERNAME=admin
DJANGO_SUPERUSER_PASSWORD=<choose-a-strong-password>
DJANGO_SUPERUSER_EMAIL=admin@example.com
```

If you don't set these before first boot, the defaults are used:
username `admin`, password `Openc0ntracts_def@ult`. Change the password immediately
if you use the defaults.

### Frontend Configuration

Set in your frontend environment file (`.envs/.local/.frontend` or `.envs/.production/.frontend`):

**Local development** (Vite, `VITE_*` prefix):

```bash
VITE_USE_AUTH0=false
VITE_API_ROOT_URL=http://localhost:8000
```

**Production** (Docker, `OPEN_CONTRACTS_*` prefix):

```bash
OPEN_CONTRACTS_REACT_APP_USE_AUTH0=false
OPEN_CONTRACTS_REACT_APP_API_ROOT_URL=https://your-domain.com
```

### Managing Users

With password auth, all user management is done through the Django admin dashboard
at `/admin/`. Log in with your superuser account and use the Users section to
create, modify, or deactivate users.

### Admin Dashboard Access

The Django admin is available at `/admin/`. Log in with any user that has
`is_staff=True`. The initial superuser account has both `is_staff` and `is_superuser`
set automatically.

---

## Option 2: Auth0 Authentication

Auth0 provides OAuth2/OIDC authentication with support for social logins (Google,
GitHub, etc.), SSO, and self-registration. New users who authenticate via Auth0
automatically get a Django account created.

### Auth0 Dashboard Setup

You need to create **one API**, **two applications**, and **one Action** in your
[Auth0 dashboard](https://manage.auth0.com/).

#### Step 1: Create an Auth0 Tenant

1. Go to [auth0.com](https://auth0.com) and sign up or log in
2. Click the tenant dropdown (top-left) and select **Create Tenant**
3. Choose a tenant name (e.g., `opencontracts-prod`) and a region (US, EU, or AU)
4. Your tenant domain will look like `opencontracts-prod.us.auth0.com`
   -- this becomes your `AUTH0_DOMAIN`

#### Step 2: Create an API

This defines the **audience** that access tokens are issued for. The backend
validates tokens against this audience.

1. Go to **Applications > APIs > Create API**
2. Configure:
    - **Name**: "OpenContracts API" (display name, your choice)
    - **Identifier**: a unique URI for your deployment (e.g., `https://contracts.opensource.legal`)
      -- this becomes your `AUTH0_API_AUDIENCE`
      -- it does not need to resolve to a real URL, it is just a logical identifier
    - **Signing Algorithm**: **RS256** (critical -- the backend only supports RS256)
3. Click **Create**
4. In the API's **Settings** tab, scroll to **Access Settings** and enable
   **Allow Offline Access**. This allows the frontend to request refresh tokens
   (via the `offline_access` scope), which are required for the SDK's
   `useRefreshTokens: true` configuration.
5. After creating the SPA application (Step 3 below), return here and go to the
   API's **Machine to Machine Applications** tab
6. Toggle the SPA application **on** to grant it access to this API

!!! warning "SPA must be authorized on the API"
    After creating both the API and the SPA application, you must return to the
    API's **Machine to Machine Applications** tab and grant the SPA access.
    Without this, `getAccessTokenSilently()` will fail with
    `"Client is not authorized to access resource server"`.

!!! warning "Allow Offline Access must be enabled on the API"
    Without **Allow Offline Access** on the API (Step 2, item 4), Auth0 will not
    issue refresh tokens even when the SDK requests the `offline_access` scope.
    This causes `"Missing Refresh Token"` errors on the frontend.

#### Step 3: Create a Single Page Application (SPA)

This is used by the React frontend to authenticate users via PKCE.

1. Go to **Applications > Applications > Create Application**
2. Choose **Single Page Web Applications**
3. Name it (e.g., "OpenContracts Frontend")
4. In the **Settings** tab, note the:
    - **Client ID** -- this becomes `AUTH0_CLIENT_ID` (backend) and
      `VITE_APPLICATION_CLIENT_ID` (frontend)
    - The **Domain** field confirms your `AUTH0_DOMAIN`
5. Configure the following URL fields (comma-separated for multiple environments):

    **Allowed Callback URLs**:
    ```
    http://localhost:3000, http://localhost:8000/admin/login/, https://your-domain.com, https://your-domain.com/admin/login/
    ```

    **Allowed Logout URLs**:
    ```
    http://localhost:3000, http://localhost:8000/admin/login/, https://your-domain.com, https://your-domain.com/admin/login/
    ```

    **Allowed Web Origins**:
    ```
    http://localhost:3000, http://localhost:8000, https://your-domain.com
    ```

6. Scroll to **Refresh Token Rotation** and enable **Rotation**. This is required
   because the frontend SDK uses `useRefreshTokens: true` to avoid cross-origin
   iframe issues on localhost. Optionally enable **Refresh Token Expiration** for
   additional security (recommended for production).
7. Save changes

!!! note "You do not need the Client Secret for the SPA"
    Single Page Applications use the PKCE (Proof Key for Code Exchange) flow,
    which does not require a client secret.

#### Step 4: Create a Machine-to-Machine (M2M) Application

This is used by the Django backend to call the Auth0 Management API (to fetch user
profiles like email, name, etc. after first login).

1. Go to **Applications > Applications > Create Application**
2. Choose **Machine to Machine Applications**
3. Name it (e.g., "OpenContracts Backend M2M")
4. When prompted to authorize an API, select the **Auth0 Management API**
   (`https://<your-tenant>.auth0.com/api/v2/`)
5. Grant the following **permissions/scopes**:
    - `read:users` -- fetch user profile data (email, name)
    - `read:user_idp_tokens` -- read identity provider tokens
6. Click **Authorize**, then save
7. Note the:
    - **Client ID** -- this is your `AUTH0_M2M_MANAGEMENT_API_ID`
    - **Client Secret** -- this is your `AUTH0_M2M_MANAGEMENT_API_SECRET`

!!! warning "The M2M app is separate from the SPA"
    The SPA and M2M applications serve different purposes and have different
    Client IDs. Do not reuse the SPA Client ID for M2M configuration.

#### Step 5: Create a Post-Login Action (for Admin Claims)

This Action injects custom claims into access tokens so the Django backend can
grant `is_staff` and `is_superuser` permissions to specific Auth0 users.

1. Go to **Actions > Flows > Login**
2. Click **Add Action > Build Custom**
3. Name it (e.g., "Add Admin Claims")
4. Replace the code with:

```javascript
exports.onExecutePostLogin = async (event, api) => {
  const namespace = 'https://contracts.opensource.legal/';

  // Read admin flags from user's app_metadata
  const isStaff = event.user.app_metadata?.is_staff || false;
  const isSuperuser = event.user.app_metadata?.is_superuser || false;

  // Add claims to the access token
  api.accessToken.setCustomClaim(`${namespace}is_staff`, isStaff);
  api.accessToken.setCustomClaim(`${namespace}is_superuser`, isSuperuser);
};
```

5. Click **Deploy**
6. Back in the Login Flow, **drag your Action** into the flow between "Start" and "Complete"
7. Click **Apply**

!!! warning "The Action must be active in the flow"
    Creating and deploying the Action is not enough. You must drag it into the
    Login Flow and click Apply, otherwise it will not execute.

!!! danger "The `namespace` value MUST match `AUTH0_ADMIN_CLAIM_NAMESPACE` exactly"
    The `namespace` constant in the Action above is the key under which claims
    are written into the access token. The Django backend reads claims at
    `AUTH0_ADMIN_CLAIM_NAMESPACE` (default `https://contracts.opensource.legal/`).
    If the two strings differ by even one character — including a typo
    (`opencontracts` vs `contracts`), a missing trailing slash, or `http` vs
    `https` — the backend will not find the claims, will treat them as missing,
    and will **set `is_staff` / `is_superuser` to `False` on the user on each
    sync cycle** (fail-closed sync; cached for 30 seconds per user via
    `_sync_admin_claims_cached`, so freshly logged-in users may have a brief
    window of elevated privileges before the next cache miss).
    See `sync_admin_claims_from_payload()` in
    `config/graphql_auth0_auth/utils.py`.

    Symptom: an Auth0 user with `app_metadata.is_superuser = true` logs in and
    the frontend admin links (e.g. the admin link in the user dropdown) do not
    appear, and `User.is_superuser` in the Django shell flips back to `False`
    shortly after each login.

    Fix: either change the Action's `namespace` to match the backend, or set
    `AUTH0_ADMIN_CLAIM_NAMESPACE` in the backend env to match the Action.
    To verify, decode your access token at jwt.io and confirm the claim keys
    are byte-for-byte identical to `AUTH0_ADMIN_CLAIM_NAMESPACE` + `is_staff` /
    `is_superuser`. After the fix, the 30-second claim cache means propagation
    is fast — clear the Django cache or restart the worker to apply it
    immediately.

!!! danger "Source admin claims from `app_metadata`, NEVER `user_metadata`"
    Auth0 distinguishes `app_metadata` (admin-controlled, read-only to the
    end user via the standard `/userinfo` endpoint) from `user_metadata`
    (which the user can write through self-service flows). The Action above
    correctly reads from `event.user.app_metadata`. **Sourcing
    `is_superuser` from `event.user.user_metadata` is a privilege-escalation
    bug**: any signed-up user can PATCH their own metadata to grant
    themselves Django superuser. Even with the
    `AUTH0_SUPERUSER_SUB_ALLOWLIST` defense-in-depth check below, do not
    rely on the allowlist as the only barrier — keep claims in
    `app_metadata`.

#### Step 6: Grant Admin Access to Auth0 Users

To give an Auth0 user admin access:

1. Go to **User Management > Users**
2. Find the user and click on them (or create a new user first)
3. Scroll to **app_metadata** and set:

```json
{
  "is_staff": true,
  "is_superuser": true
}
```

4. Save

- `is_staff` grants access to the Django admin dashboard
- `is_superuser` grants full permissions within Django admin
- Users without these flags can still use the main frontend application
- Changes take effect on the user's next login (when a new token is issued)

#### Step 7: Allow-list the Auth0 subs that may become Django superuser

Even after Step 6 sets `app_metadata.is_superuser = true` and the Action
injects the claim, the backend will refuse to flip `User.is_superuser`
until the user's Auth0 `sub` (the value of the `sub` claim, e.g.
`auth0|abc123…` or `google-oauth2|114688…`) appears in
`AUTH0_SUPERUSER_SUB_ALLOWLIST`. This second gate is defense-in-depth:
even if the Auth0 tenant is misconfigured to source admin claims from
user-writable metadata, an attacker cannot self-promote without also
forging a sub that appears in the deploy-time allowlist.

```bash
# Comma-separated list. Empty (the default) blocks ALL superuser elevation
# via JWT claim sync — any user listed here also still needs the
# {namespace}is_superuser=true claim from the Action above.
AUTH0_SUPERUSER_SUB_ALLOWLIST=auth0|abc123,google-oauth2|114688
```

The allowlist applies to `is_superuser` only — `is_staff` (admin login
without superuser powers) is still gated by the JWT claim alone. Existing
Django superusers whose subs are not in the allowlist will be demoted on
their next claim sync (within 30 seconds of their next API request);
populate this BEFORE you deploy the upgrade.

To find an Auth0 user's sub, decode their access token at jwt.io or use
the Auth0 dashboard URL (the user's profile URL ends in their sub).

### Summary of Auth0 Entities

| Auth0 Entity | Env Variable(s) | Purpose |
|-------------|-----------------|---------|
| Tenant domain | `AUTH0_DOMAIN` / `VITE_APPLICATION_DOMAIN` | Identity provider |
| API identifier | `AUTH0_API_AUDIENCE` / `VITE_AUDIENCE` | Token audience for access control |
| SPA Client ID | `AUTH0_CLIENT_ID` / `VITE_APPLICATION_CLIENT_ID` | Frontend authentication (PKCE) |
| M2M Client ID | `AUTH0_M2M_MANAGEMENT_API_ID` | Backend calls to Auth0 Management API |
| M2M Client Secret | `AUTH0_M2M_MANAGEMENT_API_SECRET` | Backend calls to Auth0 Management API |
| Post-Login Action | `AUTH0_ADMIN_CLAIM_NAMESPACE` | Injects admin claims into tokens |
| User app_metadata | -- | Controls `is_staff` / `is_superuser` in Django |
| Sub allowlist | `AUTH0_SUPERUSER_SUB_ALLOWLIST` | Defense-in-depth gate for `is_superuser` elevation |

### Backend Configuration

Set the following in your backend environment file (`.envs/.local/.django` or
`.envs/.production/.django`):

```bash
USE_AUTH0=True

# From Step 3 (SPA Application)
AUTH0_CLIENT_ID=<your-spa-client-id>

# From Step 1 (Tenant)
AUTH0_DOMAIN=<your-tenant>.us.auth0.com

# From Step 2 (API)
AUTH0_API_AUDIENCE=https://contracts.your-domain.com

# From Step 4 (M2M Application)
AUTH0_M2M_MANAGEMENT_API_ID=<your-m2m-client-id>
AUTH0_M2M_MANAGEMENT_API_SECRET=<your-m2m-client-secret>
AUTH0_M2M_MANAGEMENT_GRANT_TYPE=client_credentials

# Optional: custom namespace for admin claims (default shown below)
# Only change this if you use a different namespace in your Auth0 Action
# AUTH0_ADMIN_CLAIM_NAMESPACE=https://contracts.opensource.legal/

# Required for any user that should hold Django is_superuser. Empty
# (default) blocks ALL superuser elevation via JWT. See "Step 7" above.
# AUTH0_SUPERUSER_SUB_ALLOWLIST=auth0|abc123,google-oauth2|114688

# Optional: when True (default) any valid Auth0 token from the configured
# tenant auto-provisions a Django user the first time it is seen. If your
# tenant allows public signups and you do NOT want every signed-up user to
# get a Django account, set to False and provision users out of band via
# the management command or admin UI.
# AUTH0_CREATE_NEW_USERS=True
```

!!! note "User.email is informational, not an identity field"
    The Django `User.email` column has no `unique=True` constraint. The
    only identity field is `User.username`, which holds the Auth0 `sub`.
    Do not build sharing, invitation, or password-recovery flows that
    treat email as a primary key — duplicate-email rows are possible
    today and must be expected.

### Frontend Configuration

**Local development** (Vite, `.envs/.local/.frontend`):

```bash
VITE_USE_AUTH0=true
VITE_APPLICATION_DOMAIN=<your-tenant>.us.auth0.com
VITE_APPLICATION_CLIENT_ID=<your-spa-client-id>
VITE_AUDIENCE=https://contracts.your-domain.com
VITE_API_ROOT_URL=http://localhost:8000
```

**Production** (Docker, `.envs/.production/.frontend`):

```bash
OPEN_CONTRACTS_REACT_APP_USE_AUTH0=true
OPEN_CONTRACTS_REACT_APP_APPLICATION_DOMAIN=<your-tenant>.us.auth0.com
OPEN_CONTRACTS_REACT_APP_APPLICATION_CLIENT_ID=<your-spa-client-id>
OPEN_CONTRACTS_REACT_APP_AUDIENCE=https://contracts.your-domain.com
OPEN_CONTRACTS_REACT_APP_API_ROOT_URL=https://your-domain.com
```

!!! tip "Restart containers properly after changing env files"
    `docker compose restart` does NOT re-read `.env` files. You must run
    `docker compose up -d <service>` to recreate containers with the new values.

### Admin Dashboard Access with Auth0

When Auth0 is enabled, the admin login page at `/admin/login/` displays both:

- A **"Sign in with Auth0"** button
- A standard **username/password form** (fallback)

The Auth0 login flow:

1. User clicks "Sign in with Auth0"
2. Browser redirects to Auth0 for authentication
3. Auth0 redirects back to `/admin/login/` with an authorization code
4. The frontend JS SDK exchanges the code for an access token
5. The access token is posted to Django
6. Django decodes the token, syncs `is_staff`/`is_superuser` from the token claims,
   and creates a Django session

Users need `is_staff: true` in their Auth0 `app_metadata` (and the Post-Login Action
must be active) to access the admin dashboard. Users without this flag are denied
even if they authenticate successfully.

### How Auth0 User Creation Works

When a user authenticates via Auth0 for the first time:

1. A Django user account is created automatically with the Auth0 user ID
   (e.g., `google-oauth2|123456`) as the username
2. A random password is set (prevents password-based login for Auth0 users)
3. A background Celery task fetches the user's email, name, and other profile data
   from the Auth0 Management API (this is why the M2M application is required)
4. Admin claims (`is_staff`, `is_superuser`) are synced from the access token

This means the user's email may not appear immediately in Django -- it is populated
asynchronously within a few seconds of first login.

---

## Environment Variable Reference

### Backend Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `USE_AUTH0` | Yes | `False` | Enable Auth0 authentication |
| `AUTH0_CLIENT_ID` | If Auth0 | -- | SPA application client ID |
| `AUTH0_DOMAIN` | If Auth0 | -- | Auth0 tenant domain (e.g., `dev-xxxxx.auth0.com`) |
| `AUTH0_API_AUDIENCE` | If Auth0 | -- | API identifier/audience |
| `AUTH0_M2M_MANAGEMENT_API_ID` | If Auth0 | -- | M2M application client ID |
| `AUTH0_M2M_MANAGEMENT_API_SECRET` | If Auth0 | -- | M2M application client secret |
| `AUTH0_M2M_MANAGEMENT_GRANT_TYPE` | If Auth0 | -- | Always `client_credentials` |
| `AUTH0_ADMIN_CLAIM_NAMESPACE` | No | `https://contracts.opensource.legal/` | Namespace prefix for admin claims in tokens |
| `AUTH0_SUPERUSER_SUB_ALLOWLIST` | No | `[]` | Comma-separated Auth0 subs eligible for `is_superuser` elevation. Empty list blocks all JWT-driven superuser elevation (defense-in-depth). |
| `AUTH0_CREATE_NEW_USERS` | No | `True` | When True, any valid Auth0 token from the configured tenant auto-provisions a Django user. Set False to require out-of-band provisioning. |
| `AUTH0_ADMIN_CLAIMS_CACHE_TTL` | No | `30` | Seconds between automatic resyncs of `is_staff`/`is_superuser` from each verified token. Lower values give a tighter revocation SLA at the cost of slightly more frequent claim-sync writes on the per-request auth path. Admin login always bypasses this cache. |
| `DJANGO_SUPERUSER_USERNAME` | No | `admin` | Initial admin username |
| `DJANGO_SUPERUSER_PASSWORD` | No | `Openc0ntracts_def@ult` | Initial admin password |
| `DJANGO_SUPERUSER_EMAIL` | No | `support@opensource.legal` | Initial admin email |

### Frontend Variables

| Variable (Production) | Variable (Local/Vite) | Required | Description |
|-----------------------|----------------------|----------|-------------|
| `OPEN_CONTRACTS_REACT_APP_USE_AUTH0` | `VITE_USE_AUTH0` | Yes | Enable Auth0 on frontend |
| `OPEN_CONTRACTS_REACT_APP_APPLICATION_DOMAIN` | `VITE_APPLICATION_DOMAIN` | If Auth0 | Auth0 tenant domain |
| `OPEN_CONTRACTS_REACT_APP_APPLICATION_CLIENT_ID` | `VITE_APPLICATION_CLIENT_ID` | If Auth0 | SPA client ID |
| `OPEN_CONTRACTS_REACT_APP_AUDIENCE` | `VITE_AUDIENCE` | If Auth0 | API audience |
| `OPEN_CONTRACTS_REACT_APP_API_ROOT_URL` | `VITE_API_ROOT_URL` | Yes | Backend URL |

---

## Troubleshooting

### "Missing Refresh Token" error

**Symptom**: After authenticating, the browser console or a toast shows
`Authentication failed: Missing Refresh Token (audience: '...', scope: 'openid profile email offline_access')`.

**Cause**: The frontend SDK is configured with `useRefreshTokens: true` (to avoid
cross-origin iframe issues), which makes it request the `offline_access` scope. Auth0
only issues refresh tokens when both conditions are met:

1. The **API** has **Allow Offline Access** enabled (Step 2, item 4)
2. The **SPA application** has **Refresh Token Rotation** enabled (Step 3, item 6)

**Fix**: Enable both settings in your Auth0 dashboard. No code changes needed.

### Auth0 login redirects back to login page

**Symptom**: After Auth0 authentication, you're redirected back to `/admin/login/`
with an error message.

**Likely causes**:

1. **Post-Login Action not active**: The Action must be deployed AND dragged into
   the Login Flow. Check Actions > Flows > Login in your Auth0 dashboard.
2. **Missing `app_metadata`**: The user needs `is_staff: true` in their
   `app_metadata`. Check User Management > Users > (your user) > app_metadata.
3. **Wrong claim namespace**: The Action must use the namespace
   `https://contracts.opensource.legal/` (with trailing slash) unless you've
   overridden `AUTH0_ADMIN_CLAIM_NAMESPACE`.

### "Client is not authorized to access resource server"

**Symptom**: Browser console shows `getAccessTokenSilently()` failing with this error,
or the Auth0 `/authorize` endpoint returns a 403.

**Cause**: The SPA application has not been granted access to the API.

**Fix**: Go to **Applications > APIs > (your API) > Machine to Machine Applications**
tab and toggle the SPA application **on**. See Step 2, items 5-6.

### Auth0 `/authorize` returns 403

**Symptom**: Network tab shows a 403 response from
`https://<tenant>.auth0.com/authorize?...` on page load. The Auth0 login button
shows "Auth0 unavailable" or clicking it logs "Auth0 client not initialized".

**Likely causes**:

1. **Callback URL not whitelisted**: The `redirect_uri` in the request must exactly
   match one of the SPA's **Allowed Callback URLs**. For admin login this is
   `http://localhost:8000/admin/login/` (local) or
   `https://your-domain.com/admin/login/` (production).
2. **Web origin not whitelisted**: The SPA's **Allowed Web Origins** must include the
   origin making the request (e.g., `http://localhost:8000`).

### "Authentication failed" error

**Likely causes**:

1. **Mismatched audience**: The `AUTH0_API_AUDIENCE` backend variable must match
   the API identifier in Auth0 and the frontend `AUDIENCE` variable.
2. **Wrong domain**: `AUTH0_DOMAIN` must match your Auth0 tenant domain exactly.
3. **Expired or invalid token**: Check browser console for Auth0 SDK errors.

### Admin claim missing, defaulting to False

**Symptom**: Django logs show `Admin claim is_staff missing; defaulting to False`
(emitted at `INFO` level — bump `config.graphql_auth0_auth.utils` to `INFO` or
lower if you don't see it on production logging defaults) and the user is denied
admin access even though they authenticated successfully. Equivalently, the
frontend admin link in the user dropdown does not appear for a user that has
`app_metadata.is_superuser = true` in Auth0, and `User.is_superuser` in the
Django shell keeps flipping back to `False` after each sync cycle.

**Likely causes**:

1. **Namespace mismatch between the Action and the backend**: The Post-Login
   Action's `namespace` constant must match `AUTH0_ADMIN_CLAIM_NAMESPACE`
   byte-for-byte. A common pitfall is using `https://opencontracts.opensource.legal/`
   in the Action while the backend default is `https://contracts.opensource.legal/`
   (note: `opencontracts` vs `contracts`). Other common typos: missing trailing
   slash, `http` vs `https`. Decode your access token at jwt.io and confirm
   the claim key matches exactly.
2. **Post-Login Action not deployed or not in the flow**: Go to
   **Actions > Flows > Login** and verify the Action is dragged into the flow
   and **Apply** has been clicked.
3. **Missing `app_metadata`**: The user needs `is_staff: true` (and optionally
   `is_superuser: true`) in their `app_metadata`. Go to
   **User Management > Users > (your user) > app_metadata** and set it.
4. **Stale token**: The claims are set at login time. If you added `app_metadata`
   after the user logged in, they need to log out and log back in to get a new
   token with the updated claims.
5. **Stale claim cache after fixing the namespace**: Sync results are cached
   for `ADMIN_CLAIMS_CACHE_TTL` (30 seconds) per user via
   `_sync_admin_claims_cached()`. After correcting the namespace env var, the
   fix won't propagate for users whose claims were synced in the last 30
   seconds. Clear the Django cache (`cache.clear()` in a management shell)
   or restart the worker, then have the affected user log out and back in.
6. **Sub not in the superuser allowlist**: For `is_superuser` only, the user's
   Auth0 sub must be present in `AUTH0_SUPERUSER_SUB_ALLOWLIST` (see Step 7
   above). Confirm in a management shell with
   `from django.conf import settings; settings.AUTH0_SUPERUSER_SUB_ALLOWLIST`.
   `is_staff` is unaffected by this allowlist.

!!! tip "Diagnostic: confirm the namespace at runtime"
    Set the log level for `config.graphql_auth0_auth.utils` to `DEBUG`. The
    `sync_admin_claims` debug lines print the exact namespace the backend is
    using and the keys present in the decoded token, so a side-by-side comparison
    rules namespace mismatch in or out without needing jwt.io.

!!! info "Why missing claims revoke admin instead of being ignored"
    The backend sync is fail-closed: a claim that is missing or invalid is
    treated as `False` and the user's Django flag is set to `False` (only when
    the current value differs, so cached writes are a no-op). This prevents
    privilege retention if a user is removed from Auth0 admin, but it also
    means a misconfigured namespace will silently strip admin on each sync
    cycle (at most once every 30 seconds per user). See
    `sync_admin_claims_from_payload()` in
    `config/graphql_auth0_auth/utils.py`.

### User created but has no email

This is expected. The email is fetched asynchronously via a Celery background task
after first login. Check that:

1. Your M2M application credentials are correct
2. The M2M application has `read:users` permission on the Auth0 Management API
3. Celery workers are running

### Callback URL mismatch

Auth0 requires exact callback URL matching. Ensure your Auth0 SPA application's
**Allowed Callback URLs** includes:

- For frontend: `http://localhost:3000` (local) or `https://your-domain.com` (production)
- For admin: `http://localhost:8000/admin/login/` (local) or `https://your-domain.com/admin/login/` (production)

### Debug token claims

To see what claims are in an Auth0 access token, temporarily set the Django log
level for `config.graphql_auth0_auth.utils` to `DEBUG`. The `sync_admin_claims`
function logs the payload keys and claim values at debug level.
