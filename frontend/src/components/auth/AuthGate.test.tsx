import {
  describe,
  it,
  expect,
  vi,
  beforeEach,
  type MockedFunction,
} from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { useAuth0 } from "@auth0/auth0-react";
import { AuthGate } from "./AuthGate";
import {
  authToken,
  authStatusVar,
  userObj,
  authInitCompleteVar,
} from "../../graphql/cache";

// Mock Auth0
vi.mock("@auth0/auth0-react");

// Mock getRuntimeEnv to return a consistent domain for testing
vi.mock("../../utils/env", () => ({
  getRuntimeEnv: () => ({
    REACT_APP_APPLICATION_DOMAIN: "test-tenant.auth0.com",
    REACT_APP_APPLICATION_CLIENT_ID: "test-client-id",
    REACT_APP_AUDIENCE: "test-audience",
    REACT_APP_API_ROOT_URL: "http://localhost:8000",
    REACT_APP_USE_AUTH0: true,
  }),
}));

// Mock useCacheManager - we don't need to test cache behavior here
vi.mock("../../hooks/useCacheManager", () => ({
  useCacheManager: () => ({
    resetOnAuthChange: vi.fn().mockResolvedValue({ success: true }),
    refreshActiveQueries: vi.fn().mockResolvedValue({ success: true }),
    invalidateEntityQueries: vi.fn().mockResolvedValue({ success: true }),
    invalidateDocumentQueries: vi.fn().mockResolvedValue({ success: true }),
    invalidateCorpusQueries: vi.fn().mockResolvedValue({ success: true }),
    logCacheSize: vi.fn(),
  }),
}));

// Mock toast
vi.mock("react-toastify", () => ({
  toast: {
    error: vi.fn(),
    info: vi.fn(),
  },
}));

// Helper for Auth0 mock properties (required in newer @auth0/auth0-react versions)
const baseAuth0Props = {
  getAccessTokenSilently: vi.fn(),
  loginWithRedirect: vi.fn(),
  logout: vi.fn(),
  getIdTokenClaims: vi.fn(),
  loginWithPopup: vi.fn(),
  getAccessTokenWithPopup: vi.fn(),
  handleRedirectCallback: vi.fn(),
  connectAccountWithRedirect: vi.fn(),
  getDpopNonce: vi.fn(),
  setDpopNonce: vi.fn(),
  generateDpopProof: vi.fn(),
  createFetcher: vi.fn(),
  error: undefined,
  isReadOnly: false,
};

// Keys used by AuthGate to track if user has authenticated before
const HAS_AUTHENTICATED_KEY = "oc_has_authenticated";
const AUTH_DOMAIN_KEY = "oc_auth0_domain";

describe("AuthGate", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Reset reactive vars
    authToken("");
    authStatusVar("LOADING");
    userObj(null);
    authInitCompleteVar(false);
    // Clear localStorage before each test
    localStorage.removeItem(HAS_AUTHENTICATED_KEY);
    localStorage.removeItem(AUTH_DOMAIN_KEY);
  });

  describe("Auth0 Mode", () => {
    it("shows loading screen while Auth0 is loading", () => {
      const mockUseAuth0 = useAuth0 as MockedFunction<typeof useAuth0>;
      mockUseAuth0.mockReturnValue({
        ...baseAuth0Props,
        isLoading: true,
        isAuthenticated: false,
        user: undefined,
      });

      render(
        <AuthGate useAuth0={true} audience="test-audience">
          <div>Protected Content</div>
        </AuthGate>
      );

      expect(screen.getByText("Initializing cite")).toBeInTheDocument();
      expect(screen.queryByText("Protected Content")).not.toBeInTheDocument();
    });

    it("fetches token and renders children when authenticated", async () => {
      const mockToken = "test-token-123";
      const mockUser = { email: "test@example.com", sub: "user123" };
      const mockGetAccessTokenSilently = vi.fn().mockResolvedValue(mockToken);

      const mockUseAuth0 = useAuth0 as MockedFunction<typeof useAuth0>;
      mockUseAuth0.mockReturnValue({
        isLoading: false,
        isAuthenticated: true,
        user: mockUser,
        ...baseAuth0Props,
        getAccessTokenSilently: mockGetAccessTokenSilently,
      });

      render(
        <AuthGate useAuth0={true} audience="test-audience">
          <div>Protected Content</div>
        </AuthGate>
      );

      // Wait for auth to complete
      await waitFor(() => {
        expect(screen.getByText("Protected Content")).toBeInTheDocument();
      });

      // Verify auth state was set correctly
      expect(authToken()).toBe(mockToken);
      expect(authStatusVar()).toBe("AUTHENTICATED");
      expect(userObj()).toEqual(mockUser);

      // Verify token was fetched with correct params
      expect(mockGetAccessTokenSilently).toHaveBeenCalledWith({
        authorizationParams: {
          audience: "test-audience",
          scope: "openid profile email",
        },
      });
    });

    it("sets anonymous status when not authenticated", async () => {
      // Mock getAccessTokenSilently to reject - simulates truly anonymous user
      const mockGetAccessTokenSilently = vi.fn().mockRejectedValue({
        error: "login_required",
        message: "Login required",
      });

      const mockUseAuth0 = useAuth0 as MockedFunction<typeof useAuth0>;
      mockUseAuth0.mockReturnValue({
        isLoading: false,
        isAuthenticated: false,
        user: undefined,
        ...baseAuth0Props,
        getAccessTokenSilently: mockGetAccessTokenSilently,
      });

      render(
        <AuthGate useAuth0={true} audience="test-audience">
          <div>Protected Content</div>
        </AuthGate>
      );

      // Wait for auth to complete
      await waitFor(() => {
        expect(screen.getByText("Protected Content")).toBeInTheDocument();
      });

      // Verify anonymous state
      expect(authToken()).toBe("");
      expect(authStatusVar()).toBe("ANONYMOUS");
      expect(userObj()).toBeNull();
    });

    it("handles token fetch errors gracefully", async () => {
      const mockUser = { email: "test@example.com", sub: "user123" };
      const mockGetAccessTokenSilently = vi
        .fn()
        .mockRejectedValue(new Error("Token fetch failed"));

      const mockUseAuth0 = useAuth0 as MockedFunction<typeof useAuth0>;
      mockUseAuth0.mockReturnValue({
        isLoading: false,
        isAuthenticated: true,
        user: mockUser,
        ...baseAuth0Props,
        getAccessTokenSilently: mockGetAccessTokenSilently,
      });

      render(
        <AuthGate useAuth0={true} audience="test-audience">
          <div>Protected Content</div>
        </AuthGate>
      );

      // Wait for auth to complete (even with error)
      await waitFor(() => {
        expect(screen.getByText("Protected Content")).toBeInTheDocument();
      });

      // Verify it falls back to anonymous on error
      expect(authToken()).toBe("");
      expect(authStatusVar()).toBe("ANONYMOUS");
      expect(userObj()).toBeNull();
    });

    it("falls back to anonymous on session error (does not auto-redirect)", async () => {
      // When isAuthenticated is true but getAccessTokenSilently fails with
      // login_required, we should fall back to anonymous mode instead of
      // auto-redirecting to login. This allows users who logged out to
      // stay anonymous if they want.
      const mockUser = { email: "test@example.com", sub: "user123" };
      const mockLoginWithRedirect = vi.fn();
      const mockGetAccessTokenSilently = vi.fn().mockRejectedValue({
        error: "login_required",
        message: "Login required",
      });

      // Set flag indicating user has previously authenticated on this tenant
      localStorage.setItem(HAS_AUTHENTICATED_KEY, "true");
      localStorage.setItem(AUTH_DOMAIN_KEY, "test-tenant.auth0.com");

      const mockUseAuth0 = useAuth0 as MockedFunction<typeof useAuth0>;
      mockUseAuth0.mockReturnValue({
        ...baseAuth0Props,
        isLoading: false,
        isAuthenticated: true,
        user: mockUser,
        getAccessTokenSilently: mockGetAccessTokenSilently,
        loginWithRedirect: mockLoginWithRedirect,
      });

      render(
        <AuthGate useAuth0={true} audience="test-audience">
          <div>Protected Content</div>
        </AuthGate>
      );

      // Should render content as anonymous (not redirect to login)
      await waitFor(() => {
        expect(screen.getByText("Protected Content")).toBeInTheDocument();
      });

      // loginWithRedirect should NOT be called - we allow anonymous access
      expect(mockLoginWithRedirect).not.toHaveBeenCalled();

      // Verify anonymous state
      expect(authToken()).toBe("");
      expect(authStatusVar()).toBe("ANONYMOUS");
      expect(userObj()).toBeNull();
    });

    it("defaults first-time visitor to anonymous on login_required error", async () => {
      const mockUser = { email: "test@example.com", sub: "user123" };
      const mockLoginWithRedirect = vi.fn();
      const mockGetAccessTokenSilently = vi.fn().mockRejectedValue({
        error: "login_required",
        message: "Login required",
      });

      // Ensure no previous auth flag exists (first-time visitor)
      localStorage.removeItem(HAS_AUTHENTICATED_KEY);

      const mockUseAuth0 = useAuth0 as MockedFunction<typeof useAuth0>;
      mockUseAuth0.mockReturnValue({
        ...baseAuth0Props,
        isLoading: false,
        isAuthenticated: true,
        user: mockUser,
        getAccessTokenSilently: mockGetAccessTokenSilently,
        loginWithRedirect: mockLoginWithRedirect,
      });

      render(
        <AuthGate useAuth0={true} audience="test-audience">
          <div>Protected Content</div>
        </AuthGate>
      );

      // Wait for auth to complete - should render content as anonymous
      await waitFor(() => {
        expect(screen.getByText("Protected Content")).toBeInTheDocument();
      });

      // Verify loginWithRedirect was NOT called for first-time visitor
      expect(mockLoginWithRedirect).not.toHaveBeenCalled();

      // Verify anonymous state
      expect(authToken()).toBe("");
      expect(authStatusVar()).toBe("ANONYMOUS");
      expect(userObj()).toBeNull();
    });

    it("sets auth flag on successful authentication", async () => {
      const mockToken = "test-token-123";
      const mockUser = { email: "test@example.com", sub: "user123" };
      const mockGetAccessTokenSilently = vi.fn().mockResolvedValue(mockToken);

      // Ensure no previous auth flag exists
      localStorage.removeItem(HAS_AUTHENTICATED_KEY);

      const mockUseAuth0 = useAuth0 as MockedFunction<typeof useAuth0>;
      mockUseAuth0.mockReturnValue({
        isLoading: false,
        isAuthenticated: true,
        user: mockUser,
        ...baseAuth0Props,
        getAccessTokenSilently: mockGetAccessTokenSilently,
      });

      render(
        <AuthGate useAuth0={true} audience="test-audience">
          <div>Protected Content</div>
        </AuthGate>
      );

      await waitFor(() => {
        expect(screen.getByText("Protected Content")).toBeInTheDocument();
      });

      // Verify auth flag and domain were set
      expect(localStorage.getItem(HAS_AUTHENTICATED_KEY)).toBe("true");
      expect(localStorage.getItem(AUTH_DOMAIN_KEY)).toBe(
        "test-tenant.auth0.com"
      );
    });
  });

  describe("Non-Auth0 Mode", () => {
    it("immediately sets anonymous status and renders children", async () => {
      // Mock useAuth0 to return minimal values for non-Auth0 mode
      const mockUseAuth0 = useAuth0 as MockedFunction<typeof useAuth0>;
      mockUseAuth0.mockReturnValue({
        isLoading: false,
        isAuthenticated: false,
        user: undefined,
        ...baseAuth0Props,
      });

      render(
        <AuthGate useAuth0={false}>
          <div>Protected Content</div>
        </AuthGate>
      );

      // Should immediately render children in non-Auth0 mode
      await waitFor(() => {
        expect(screen.getByText("Protected Content")).toBeInTheDocument();
      });

      // Verify anonymous state
      expect(authStatusVar()).toBe("ANONYMOUS");
      expect(authToken()).toBe("");
      expect(userObj()).toBeNull();
    });
  });

  describe("Race Condition Prevention", () => {
    it("blocks rendering until auth is fully initialized", async () => {
      // Use fake timers to prevent timer pollution between tests
      vi.useFakeTimers();

      const mockToken = "test-token-123";
      const mockUser = { email: "test@example.com", sub: "user123" };
      const mockGetAccessTokenSilently = vi.fn().mockImplementation(
        () =>
          new Promise((resolve) => {
            // Simulate async token fetch
            setTimeout(() => resolve(mockToken), 100);
          })
      );

      const mockUseAuth0 = useAuth0 as MockedFunction<typeof useAuth0>;
      mockUseAuth0.mockReturnValue({
        isLoading: false,
        isAuthenticated: true,
        user: mockUser,
        ...baseAuth0Props,
        getAccessTokenSilently: mockGetAccessTokenSilently,
      });

      render(
        <AuthGate useAuth0={true} audience="test-audience">
          <div>Protected Content</div>
        </AuthGate>
      );

      // Initially should show loading
      expect(screen.getByText("Initializing cite")).toBeInTheDocument();
      expect(screen.queryByText("Protected Content")).not.toBeInTheDocument();

      // Advance timers to trigger the token fetch
      await vi.advanceTimersByTimeAsync(100);

      // Wait for token fetch to complete
      await waitFor(() => {
        expect(screen.queryByText("Initializing cite")).not.toBeInTheDocument();
        expect(screen.getByText("Protected Content")).toBeInTheDocument();
      });

      // Verify auth state is correct
      expect(authToken()).toBe(mockToken);
      expect(authStatusVar()).toBe("AUTHENTICATED");

      // Restore real timers to prevent pollution of subsequent tests
      vi.useRealTimers();
    });

    it("ensures token is set before marking as authenticated", async () => {
      const mockToken = "test-token-123";
      const mockUser = { email: "test@example.com", sub: "user123" };
      const mockGetAccessTokenSilently = vi.fn().mockResolvedValue(mockToken);

      const mockUseAuth0 = useAuth0 as MockedFunction<typeof useAuth0>;
      mockUseAuth0.mockReturnValue({
        isLoading: false,
        isAuthenticated: true,
        user: mockUser,
        ...baseAuth0Props,
        getAccessTokenSilently: mockGetAccessTokenSilently,
      });

      render(
        <AuthGate useAuth0={true} audience="test-audience">
          <div>Protected Content</div>
        </AuthGate>
      );

      await waitFor(() => {
        expect(screen.getByText("Protected Content")).toBeInTheDocument();
      });

      // The critical test: token should be set when status is AUTHENTICATED
      const token = authToken();
      const status = authStatusVar();

      expect(token).toBeTruthy();
      expect(status).toBe("AUTHENTICATED");

      // They should both be set (no race condition where status is AUTHENTICATED but token is empty)
      if (status === "AUTHENTICATED") {
        expect(token).not.toBe("");
      }
    });

    it("sets authInitCompleteVar after cache operations complete", async () => {
      const mockToken = "test-token-123";
      const mockUser = { email: "test@example.com", sub: "user123" };
      const mockGetAccessTokenSilently = vi.fn().mockResolvedValue(mockToken);

      // Verify initial state
      expect(authInitCompleteVar()).toBe(false);

      const mockUseAuth0 = useAuth0 as MockedFunction<typeof useAuth0>;
      mockUseAuth0.mockReturnValue({
        isLoading: false,
        isAuthenticated: true,
        user: mockUser,
        ...baseAuth0Props,
        getAccessTokenSilently: mockGetAccessTokenSilently,
      });

      render(
        <AuthGate useAuth0={true} audience="test-audience">
          <div>Protected Content</div>
        </AuthGate>
      );

      await waitFor(() => {
        expect(screen.getByText("Protected Content")).toBeInTheDocument();
      });

      // After auth completes, authInitCompleteVar should be true
      expect(authInitCompleteVar()).toBe(true);
      expect(authToken()).toBe(mockToken);
      expect(authStatusVar()).toBe("AUTHENTICATED");
    });

    it("sets authInitCompleteVar for anonymous users", async () => {
      // Verify initial state
      expect(authInitCompleteVar()).toBe(false);

      // Mock getAccessTokenSilently to reject - simulates truly anonymous user
      const mockGetAccessTokenSilently = vi.fn().mockRejectedValue({
        error: "login_required",
        message: "Login required",
      });

      const mockUseAuth0 = useAuth0 as MockedFunction<typeof useAuth0>;
      mockUseAuth0.mockReturnValue({
        isLoading: false,
        isAuthenticated: false,
        user: undefined,
        ...baseAuth0Props,
        getAccessTokenSilently: mockGetAccessTokenSilently,
      });

      render(
        <AuthGate useAuth0={true} audience="test-audience">
          <div>Protected Content</div>
        </AuthGate>
      );

      await waitFor(() => {
        expect(screen.getByText("Protected Content")).toBeInTheDocument();
      });

      // After auth completes (even as anonymous), authInitCompleteVar should be true
      expect(authInitCompleteVar()).toBe(true);
      expect(authStatusVar()).toBe("ANONYMOUS");
    });

    it("sets authInitCompleteVar in non-Auth0 mode", async () => {
      // Verify initial state
      expect(authInitCompleteVar()).toBe(false);

      const mockUseAuth0 = useAuth0 as MockedFunction<typeof useAuth0>;
      mockUseAuth0.mockReturnValue({
        isLoading: false,
        isAuthenticated: false,
        user: undefined,
        ...baseAuth0Props,
      });

      render(
        <AuthGate useAuth0={false}>
          <div>Protected Content</div>
        </AuthGate>
      );

      await waitFor(() => {
        expect(screen.getByText("Protected Content")).toBeInTheDocument();
      });

      // Should be set immediately in non-Auth0 mode
      expect(authInitCompleteVar()).toBe(true);
      expect(authStatusVar()).toBe("ANONYMOUS");
    });

    it("handles Auth0 callback race condition - isAuthenticated false but tokens exist", async () => {
      // Simulate the race condition during Auth0 callback:
      // isAuthenticated is false (SDK state not updated yet)
      // but getAccessTokenSilently succeeds (tokens are in cache)
      const mockToken = "race-condition-token";
      const mockGetAccessTokenSilently = vi.fn().mockResolvedValue(mockToken);

      // Simulate OAuth callback URL so the fast-path doesn't skip verification
      const originalSearch = window.location.search;
      Object.defineProperty(window, "location", {
        writable: true,
        value: { ...window.location, search: "?code=abc&state=xyz" },
      });

      const mockUseAuth0 = useAuth0 as MockedFunction<typeof useAuth0>;
      mockUseAuth0.mockReturnValue({
        isLoading: false,
        isAuthenticated: false, // SDK state not yet updated
        user: undefined,
        ...baseAuth0Props,
        getAccessTokenSilently: mockGetAccessTokenSilently,
      });

      render(
        <AuthGate useAuth0={true} audience="test-audience">
          <div>Protected Content</div>
        </AuthGate>
      );

      // Should render children after detecting we have tokens, and auth
      // state should be set correctly despite isAuthenticated being false.
      // All assertions in one waitFor to avoid reading stale reactive vars
      // between async promise resolutions.
      await waitFor(() => {
        expect(screen.getByText("Protected Content")).toBeInTheDocument();
        expect(authToken()).toBe(mockToken);
        expect(authStatusVar()).toBe("AUTHENTICATED");
        expect(authInitCompleteVar()).toBe(true);
      });

      // Verify getAccessTokenSilently was called to verify auth state
      expect(mockGetAccessTokenSilently).toHaveBeenCalled();

      // Restore original location
      Object.defineProperty(window, "location", {
        writable: true,
        value: { ...window.location, search: originalSearch },
      });
    });
  });
});
