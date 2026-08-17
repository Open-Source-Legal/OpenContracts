# Frontend Authentication Flow

This document describes the frontend authentication flow in OpenContracts, including how Auth0 integration works, race condition handling, and the coordination between authentication state and Apollo cache operations.

## Overview

OpenContracts uses Auth0 for authentication with an AuthGate pattern that ensures authentication is fully initialized before rendering any protected content. This eliminates race conditions where components might try to make authenticated API requests before the auth token is available.

## Key Components

| Component | Location | Purpose |
|-----------|----------|---------|
| `authInitCompleteVar` | `frontend/src/graphql/cache.ts` | Reactive variable signaling when auth init is fully complete, including cache operations |
| `AuthGate` | `frontend/src/components/auth/AuthGate.tsx` | Guards the app, ensuring auth is resolved before rendering children |
| `GET_ME` query | `frontend/src/App.tsx` | Fetches backend user details, skipped until both `auth_token` AND `auth_init_complete` are true |
| `useCacheManager` | `frontend/src/hooks/useCacheManager.ts` | Hook for Apollo cache reset operations during auth changes |

## Authentication Flow Diagram

```
Page Load
    │
    ▼
AuthGate shows loading screen
    │
    ▼
Auth0 SDK loads (isLoading: true → false)
    │
    ├─── isAuthenticated && user? ───────────────────┐
    │         YES                                    │ NO
    │           │                                    │
    │           ▼                                    ▼
    │    getAccessTokenSilently()          getAccessTokenSilently()
    │           │                          (verify: race condition?)
    │           ▼                                    │
    │    Set token, user, status           ┌────────┴────────┐
    │           │                          │                 │
    │           ▼                       SUCCESS           FAILURE
    │    clearStore() [await]              │                 │
    │           │                          ▼                 ▼
    │           ▼                    Race condition!    Anonymous
    │    authInitCompleteVar(true)   Handle as auth     user
    │           │                          │                 │
    │           ▼                          ▼                 ▼
    └───────────┴──────────────────────────┴─────────────────┘
                                   │
                                   ▼
                    authInitialized = true
                    Render children
                                   │
                                   ▼
                    GET_ME fires (skip condition satisfied)
                    DiscoveryLanding queries fire
```

## Detailed Flow

### 1. Initial Load

When the app loads, `AuthGate` renders a loading screen while authentication initializes:

```typescript
if (!authInitialized || authStatus === "LOADING") {
  return <ModernLoadingDisplay type="auth" message="Initializing OpenContracts" />;
}
```

### 2. Auth0 SDK Resolution

Once the Auth0 SDK finishes loading (`isLoading: false`), AuthGate checks if the user is authenticated.

### 3a. Authenticated Path (`isAuthenticated && user`)

1. Call `getAccessTokenSilently()` to get the access token
2. Set auth state **synchronously** before any async operations:
   ```typescript
   authToken(token);
   userObj(user);
   authStatusVar("AUTHENTICATED");
   ```
3. Clear stale cache data via `resetOnAuthChange()` (awaited)
4. Set `authInitCompleteVar(true)` **after** cache clear completes
5. Set local `authInitialized` state to true

### 3b. Unauthenticated Path - Race Condition Handling

When `isAuthenticated` is `false`, there's a potential race condition during Auth0 callback where the SDK hasn't updated state yet but tokens exist. AuthGate handles this by:

1. Attempting `getAccessTokenSilently()` to verify actual auth state
2. If token obtained: race condition detected - handle as authenticated
3. If token fetch fails with expected errors (`login_required`, etc.): user is truly anonymous
4. Set `authInitCompleteVar(true)` after resolution

### 4. Rendering Children

Once `authInitialized` is true, AuthGate renders its children:

```typescript
return <>{children}</>;
```

### 5. App.tsx Query Behavior

The `GET_ME` query in `App.tsx` uses a skip condition that ensures it only fires after auth initialization is complete:

```typescript
const { data: meData } = useQuery<GetMeOutputs>(GET_ME, {
  skip: !auth_token || !auth_init_complete,
  fetchPolicy: "network-only",
});
```

## Key Guarantees

1. **No query fires until `authInitCompleteVar` is true** - This prevents `clearStore()` from aborting in-flight queries

2. **Race condition handled** - If `isAuthenticated` is briefly false during Auth0 callback, we verify via `getAccessTokenSilently()`

3. **No forced login** - Users can stay anonymous after logout; login is always opt-in via UI

4. **Auth state set before cache clear** - Ensures any refetches triggered by cache operations have correct credentials

## Reactive Variables

### Auth State Variables (`cache.ts`)

```typescript
// User object from Auth0
export const userObj = makeVar<User | null>(null);

// JWT access token
export const authToken = makeVar<string>("");

// Auth lifecycle status
export type AuthStatus = "LOADING" | "AUTHENTICATED" | "ANONYMOUS";
export const authStatusVar = makeVar<AuthStatus>("LOADING");

// Signals when auth init (including cache clear) is complete
export const authInitCompleteVar = makeVar<boolean>(false);

// Backend user object (from GET_ME query)
export const backendUserObj = makeVar<UserType | null>(null);
```

### Why Two Completion Signals?

`authStatusVar` and `authInitCompleteVar` serve different purposes:

- **`authStatusVar`** - Set **before** cache clear to ensure credentials are available for any refetches
- **`authInitCompleteVar`** - Set **after** cache clear to signal it's safe to make new queries

This ordering prevents queries like GET_ME from being aborted by `clearStore()`.

## Cache Management

AuthGate uses `useCacheManager` hook to clear stale data on auth changes:

```typescript
const { resetOnAuthChange } = useCacheManager();

// On successful auth
await resetOnAuthChange({
  reason: "auth0_login",
  refetchActive: false,
});
```

The `refetchActive: false` option is used because:
- Auth state is already set
- Component mount will trigger necessary queries with correct credentials

## Error Handling

### Token Fetch Errors

When `getAccessTokenSilently()` fails:

| Error Code | Meaning | Action |
|------------|---------|--------|
| `login_required` | User needs to log in | Fall back to anonymous |
| `consent_required` | User needs to consent | Fall back to anonymous |
| `interaction_required` | User interaction needed | Fall back to anonymous |
| Other errors | Unexpected failure | Fall back to anonymous + show toast |

### No Auto-Redirect

AuthGate deliberately does NOT auto-redirect to login because:
- Users who logged out explicitly want to be anonymous
- Forcing login creates poor UX
- Users can always click the login button if they want to authenticate

## LocalStorage Persistence

AuthGate tracks if a user has ever authenticated:

```typescript
const HAS_AUTHENTICATED_KEY = "oc_has_authenticated";

// Set after successful auth
localStorage.setItem(HAS_AUTHENTICATED_KEY, "true");
```

This helps distinguish:
- First-time visitors (never authenticated)
- Returning users with expired sessions

## Component Usage Guidelines

### Do NOT Check Auth Status

With AuthGate, components don't need auth checks:

```typescript
// BAD - Unnecessary auth checking
const authStatus = useReactiveVar(authStatusVar);
if (authStatus === "LOADING") return <Loader />;

// GOOD - Auth is guaranteed ready by AuthGate
return <Content />;
```

### Use Simple Queries

```typescript
// BAD - Unnecessary skip logic
const { data } = useQuery(GET_DATA, {
  skip: !authToken,
});

// GOOD - Auth is ready, just query
const { data } = useQuery(GET_DATA);
```

**Exception**: The `GET_ME` query in `App.tsx` is special because it runs at the root level and needs both the token AND confirmation that cache operations are complete.

### Refetching Data on Auth Changes

When a component is **already mounted** and the user logs in or out, queries don't automatically refetch because AuthGate uses `refetchActive: false` during auth transitions. Components that need fresh data after auth changes should watch `authToken` and refetch:

```typescript
import { useEffect, useRef } from "react";
import { useReactiveVar } from "@apollo/client";
import { authToken } from "../graphql/cache";

function MyComponent() {
  const auth_token = useReactiveVar(authToken);
  const isInitialMount = useRef(true);

  const { data, refetch } = useQuery(MY_QUERY, {
    fetchPolicy: "cache-and-network",
  });

  // Refetch when auth state changes (login/logout)
  useEffect(() => {
    if (isInitialMount.current) {
      isInitialMount.current = false;
      return;
    }
    // Auth state changed - refetch to get updated data
    refetch();
  }, [auth_token, refetch]);

  return <>{/* component content */}</>;
}
```

**When to use this pattern:**
- Landing pages showing aggregate stats (counts depend on permissions)
- List views that should show different items based on auth status
- Any component displaying permission-sensitive data that stays mounted across login

**Examples in codebase:**
- `DiscoveryLanding.tsx` - Refetches community stats and trending content
- `CorpusQueryList.tsx` - Refetches corpus queries when auth changes

## Testing

### Component Test Setup

When testing components that depend on auth:

```typescript
// Mock the auth state
import { authToken, authStatusVar, authInitCompleteVar } from "./graphql/cache";

beforeEach(() => {
  authToken("test-token");
  authStatusVar("AUTHENTICATED");
  authInitCompleteVar(true);
});
```

### AuthGate Unit Tests

See `frontend/src/components/auth/AuthGate.test.tsx` for test examples.

## Related Documentation

- [Authentication Pattern](../../frontend/src/docs/AUTHENTICATION_PATTERN.md) - Detailed AuthGate pattern documentation
- [Routing System](./routing_system.md) - How routing works with auth
- [Apollo Cache](../architecture/apollo_cache.md) - Cache management details

## Troubleshooting

### Empty Lists on Direct Navigation

**Symptom**: Navigating directly to a URL shows empty content

**Cause**: Query fired before auth was ready

**Solution**: Ensure component is inside AuthGate and doesn't have unnecessary skip logic

### NS_BINDING_ABORTED Errors

**Symptom**: Network requests aborted with NS_BINDING_ABORTED

**Cause**: `clearStore()` aborting in-flight queries

**Solution**: Ensure queries wait for `authInitCompleteVar` to be true before firing

### Stale Data After Login

**Symptom**: Old user's data shows after logging in as different user

**Cause**: Cache not cleared on auth change

**Solution**: `resetOnAuthChange()` should be called and awaited before setting `authInitCompleteVar(true)`
