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
import { authToken, authStatusVar, userObj } from "../../graphql/cache";

// Mock Auth0
vi.mock("@auth0/auth0-react");

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

describe("AuthGate", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Reset reactive vars
    authToken("");
    authStatusVar("LOADING");
    userObj(null);
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

      expect(
        screen.getByText("Initializing OpenContracts")
      ).toBeInTheDocument();
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
      const mockUseAuth0 = useAuth0 as MockedFunction<typeof useAuth0>;
      mockUseAuth0.mockReturnValue({
        isLoading: false,
        isAuthenticated: false,
        user: undefined,
        ...baseAuth0Props,
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

    it("preserves current path when redirecting to login on login_required error", async () => {
      const mockUser = { email: "test@example.com", sub: "user123" };
      const mockLoginWithRedirect = vi.fn();
      const mockGetAccessTokenSilently = vi.fn().mockRejectedValue({
        error: "login_required",
        message: "Login required",
      });

      // Mock window.location
      const originalLocation = window.location;
      delete (window as any).location;
      window.location = {
        ...originalLocation,
        pathname: "/corpus/123/document/456",
        search: "?page=2",
        origin: "http://localhost:3000",
      } as any;

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

      // Wait for loginWithRedirect to be called
      await waitFor(() => {
        expect(mockLoginWithRedirect).toHaveBeenCalled();
      });

      // Verify loginWithRedirect was called with appState containing current path
      expect(mockLoginWithRedirect).toHaveBeenCalledWith({
        authorizationParams: {
          audience: "test-audience",
          scope: "openid profile email",
          redirect_uri: "http://localhost:3000",
        },
        appState: {
          returnTo: "/corpus/123/document/456?page=2",
        },
      });

      // Restore window.location
      (window as any).location = originalLocation;
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
      expect(
        screen.getByText("Initializing OpenContracts")
      ).toBeInTheDocument();
      expect(screen.queryByText("Protected Content")).not.toBeInTheDocument();

      // Wait for token fetch to complete
      await waitFor(() => {
        expect(
          screen.queryByText("Initializing OpenContracts")
        ).not.toBeInTheDocument();
        expect(screen.getByText("Protected Content")).toBeInTheDocument();
      });

      // Verify auth state is correct
      expect(authToken()).toBe(mockToken);
      expect(authStatusVar()).toBe("AUTHENTICATED");
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
  });
});
