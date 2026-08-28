# Authentication Pattern Documentation

## Overview

OpenContracts uses a centralized authentication gate pattern to ensure authentication is fully initialized before rendering any protected content. This eliminates race conditions where components might try to make authenticated API requests before the auth token is available.

## The Problem

### Race Condition on Direct Navigation

When users navigate directly to a protected route (e.g., `/corpuses`), a race condition can occur:

1. Component mounts immediately
2. Component tries to fetch data via GraphQL
3. Auth0 authentication happens asynchronously
4. GraphQL request is sent without auth token (still being fetched)
5. Server returns empty results or authentication errors
6. Auth token becomes available (too late)
7. User sees empty content despite being authenticated

### Symptoms

- Empty corpus/document lists when navigating directly to URLs
- GraphQL requests with empty Authorization headers
- Content appearing only after clicking navigation links (which trigger refetch)
- Inconsistent behavior between direct navigation and in-app navigation

## The Solution: AuthGate Pattern

### Architecture

```
App.tsx
  └── AuthGate (blocks rendering until auth ready)
       └── Routes
            ├── Corpuses (auth guaranteed ready)
            ├── Documents (auth guaranteed ready)
            └── Other Components (auth guaranteed ready)
```

### How It Works

1. **AuthGate Component** wraps all routes
2. **Blocks Rendering** while authentication initializes
3. **Shows Loading Screen** during auth initialization
4. **Sets Auth State Atomically** - token, user, and status together
5. **Renders Children** only after auth is complete

## Implementation

### AuthGate Component

Located at: `/src/components/auth/AuthGate.tsx`

```typescript
export const AuthGate: React.FC<AuthGateProps> = ({
  children,
  useAuth0: useAuth0Flag,
  audience
}) => {
  const [authInitialized, setAuthInitialized] = useState(false);

  // Auth0 authentication flow
  useEffect(() => {
    if (useAuth0Flag) {
      // Wait for Auth0 to load
      if (auth0Loading) return;

      if (isAuthenticated && user) {
        // Fetch token
        getAccessTokenSilently(...)
          .then((token) => {
            // Set everything atomically
            authToken(token);
            userObj(user);
            authStatusVar("AUTHENTICATED");
            setAuthInitialized(true);
          });
      } else {
        // Not authenticated
        authStatusVar("ANONYMOUS");
        setAuthInitialized(true);
      }
    } else {
      // Non-Auth0 mode
      authStatusVar("ANONYMOUS");
      setAuthInitialized(true);
    }
  }, [...]);

  // Block rendering until ready
  if (!authInitialized) {
    return <Loader>Initializing...</Loader>;
  }

  return <>{children}</>;
};
```

### Session Expiry & Stale Refresh Tokens

The app uses rotating refresh tokens with `cacheLocation="localstorage"` and
`useRefreshTokensFallback: false` (see `src/index.tsx` and
`src/utils/Auth0ProviderWithHistory.tsx`). When Auth0 rejects the stored
refresh token — expired past its idle/absolute lifetime, revoked, or lost to
rotation reuse-detection (tenant log event `fertft`, surfaced by the SDK as
`invalid_grant` "Unknown or invalid refresh token." or
`missing_refresh_token`) — the localstorage cache would otherwise keep
`isAuthenticated=true` and replay the same failed token exchange on every
page load.

`AuthGate` treats these as _expected_ session expiry
(`AuthGate.tsx::isRefreshTokenError` / `clearStaleAuth0Session`): it clears
the SDK cache locally via `logout({ openUrl: false })`, drops the
has-authenticated fast-path flag, shows a one-time informational toast
("Your session has expired"), and falls back to anonymous. Transient/unknown
errors do NOT wipe the cache — the session may recover on the next load —
and still surface an error toast.

### App.tsx Integration

```typescript
// Before: Routes render immediately, auth happens in parallel
<Routes>
  <Route path="/corpuses" element={<Corpuses />} />
</Routes>

// After: Routes only render after auth completes
<AuthGate useAuth0={REACT_APP_USE_AUTH0} audience={REACT_APP_AUDIENCE}>
  <Routes>
    <Route path="/corpuses" element={<Corpuses />} />
  </Routes>
</AuthGate>
```

### Apollo Client Auth Link

Located at: `/src/index.tsx`

```typescript
const authLink = new ApolloLink((operation, forward) => {
  operation.setContext(({ headers }) => {
    const token = authToken(); // Get current token from reactive var
    return {
      headers: {
        Authorization: token ? `Bearer ${token}` : "",
        ...headers,
      },
    };
  });
  return forward(operation);
});
```

## Benefits

### 1. Eliminates Race Conditions

- Auth always completes before components mount
- No queries sent without authentication
- Consistent behavior on all navigation types

### 2. Simplified Component Logic

- Components don't need auth checks
- No skip/refetch logic in queries
- Standard `useQuery` instead of `useLazyQuery`

### 3. Better User Experience

- Clear loading state during initialization
- No empty content flashes
- Predictable navigation behavior

### 4. Centralized Auth Logic

- Single source of truth for auth state
- Easier to maintain and debug
- Consistent auth handling across the app

## Usage Guidelines

### For New Components

1. **Don't check auth status** - Assume it's ready
2. **Use regular queries** - No need for skip logic
3. **Trust the token** - It will be available

```typescript
// Good - Simple query, auth is guaranteed ready
const { data, loading } = useQuery(GET_DATA);

// Bad - Unnecessary auth checks
const auth = useReactiveVar(authStatusVar);
const { data, loading } = useQuery(GET_DATA, {
  skip: auth === "LOADING", // Not needed!
});
```

### For Auth State Changes

The AuthGate handles initial authentication. For logout/login:

1. **Logout**: Clear reactive variables

```typescript
authToken("");
userObj(null);
authStatusVar("ANONYMOUS");
```

2. **Login (non-Auth0)**: Set reactive variables

```typescript
authToken(token);
userObj(user);
authStatusVar("AUTHENTICATED");
```

### Debugging Auth Issues

1. Check browser console for AuthGate logs
2. Verify token in Apollo DevTools
3. Check Network tab for Authorization headers
4. Ensure AuthGate wraps all protected routes

## Common Pitfalls

### 1. Bypassing AuthGate

```typescript
// Bad - Route outside AuthGate
<Route path="/public" element={<Public />} />
<AuthGate>
  <Route path="/protected" element={<Protected />} />
</AuthGate>

// Good - All routes inside AuthGate
<AuthGate>
  <Route path="/public" element={<Public />} />
  <Route path="/protected" element={<Protected />} />
</AuthGate>
```

### 2. Manual Auth Checks

```typescript
// Bad - Redundant auth checking
if (authStatus === "AUTHENTICATED") {
  return <Content />;
} else {
  return <Login />;
}

// Good - Let AuthGate handle it
return <Content />; // Auth already guaranteed
```

### 3. Complex Query Logic

```typescript
// Bad - Overly complex auth-aware queries
const [fetchData, { data }] = useLazyQuery(GET_DATA);
useEffect(() => {
  if (authToken) fetchData();
}, [authToken]);

// Good - Simple query
const { data } = useQuery(GET_DATA);
```

## Testing

### Unit Tests

```typescript
describe("AuthGate", () => {
  it("shows loading while auth initializes", () => {
    render(
      <AuthGate>
        <Content />
      </AuthGate>
    );
    expect(screen.getByText("Initializing...")).toBeInTheDocument();
  });

  it("renders children after auth completes", async () => {
    render(
      <AuthGate>
        <Content />
      </AuthGate>
    );
    await waitFor(() => {
      expect(screen.getByText("Content")).toBeInTheDocument();
    });
  });
});
```

### E2E Tests

1. Navigate directly to protected route
2. Verify loading screen appears
3. Verify content loads after auth
4. Check network requests have auth headers

## Migration Guide

### Converting Existing Components

1. **Remove auth checks**

```typescript
// Before
const authStatus = useReactiveVar(authStatusVar);
if (authStatus === "LOADING") return <Loader />;

// After
// Just render normally, auth is ready
```

2. **Simplify queries**

```typescript
// Before
const { data } = useQuery(GET_DATA, {
  skip: !authToken,
});

// After
const { data } = useQuery(GET_DATA);
```

3. **Remove manual refetch logic**

```typescript
// Before
useEffect(() => {
  if (authToken) refetch();
}, [authToken]);

// After
// Not needed, query runs when component mounts
```

## Architecture Decisions

### Why AuthGate?

1. **Single Responsibility**: Auth logic in one place
2. **Fail-Safe**: Can't accidentally render without auth
3. **Performance**: Prevents unnecessary failed requests
4. **Maintainability**: Easy to modify auth flow

### Why Reactive Variables?

Apollo Client reactive variables provide:

- Global state management
- Automatic re-renders on change
- Integration with Apollo cache
- No prop drilling needed

### Why Not Context API?

While Context could work, reactive variables:

- Integrate better with Apollo Client
- Don't require provider wrapping
- Work seamlessly with Apollo DevTools
- Provide simpler API

## Related Documentation

- [Navigation System](./NAVIGATION_SYSTEM_COMPLETE.md) - How routing works
- [GraphQL Queries](../graphql/queries.ts) - Query definitions
- [Apollo Cache](../graphql/cache.ts) - Reactive variable definitions
