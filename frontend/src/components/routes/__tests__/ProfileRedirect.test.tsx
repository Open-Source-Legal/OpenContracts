import { render, screen } from "@testing-library/react";
import { MockedProvider } from "@apollo/client/testing";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { ProfileRedirect } from "../ProfileRedirect";
import {
  backendUserObj,
  authStatusVar,
  authInitCompleteVar,
} from "../../../graphql/cache";

vi.mock("../../widgets/ModernLoadingDisplay", () => ({
  ModernLoadingDisplay: () => <div>Loading...</div>,
}));

/**
 * Tests for ProfileRedirect.
 *
 * /profile is auth-state-driven, not URL-state-driven, so the redirect lives
 * outside CentralRouteManager. ProfileRedirect waits for the auth pipeline
 * to complete, then issues a Navigate to /login (anonymous) or
 * /users/<slug> (logged in).
 */
describe("ProfileRedirect", () => {
  const LocationReporter: React.FC = () => {
    const location = useLocation();
    return <div data-testid="location">{location.pathname}</div>;
  };

  const renderAt = (path: string) =>
    render(
      <MockedProvider mocks={[]} addTypename={false}>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path="/profile" element={<ProfileRedirect />} />
            <Route path="/login" element={<LocationReporter />} />
            <Route path="/users/:slug" element={<LocationReporter />} />
          </Routes>
        </MemoryRouter>
      </MockedProvider>
    );

  beforeEach(() => {
    backendUserObj(null);
    authStatusVar("ANONYMOUS");
    authInitCompleteVar(true);
  });

  afterEach(() => {
    vi.clearAllMocks();
    backendUserObj(null);
    authStatusVar("LOADING");
    authInitCompleteVar(false);
  });

  it("redirects to /login when no user is authenticated", async () => {
    renderAt("/profile");
    const loc = await screen.findByTestId("location");
    expect(loc.textContent).toBe("/login");
  });

  it("redirects to /users/<slug> when a user is authenticated", async () => {
    authStatusVar("AUTHENTICATED");
    backendUserObj({ id: "u-1", slug: "alice" } as any);
    renderAt("/profile");
    const loc = await screen.findByTestId("location");
    expect(loc.textContent).toBe("/users/alice");
  });

  it("redirects to /login when the authenticated user has no slug", async () => {
    authStatusVar("AUTHENTICATED");
    backendUserObj({ id: "u-1" } as any);
    renderAt("/profile");
    const loc = await screen.findByTestId("location");
    expect(loc.textContent).toBe("/login");
  });

  it("renders the loading display while auth status is LOADING (no premature /login flash)", () => {
    authStatusVar("LOADING");
    authInitCompleteVar(false);
    renderAt("/profile");
    expect(screen.getByText("Loading...")).toBeInTheDocument();
    expect(screen.queryByTestId("location")).toBeNull();
  });

  it("renders the loading display while auth init is incomplete even after token resolves", () => {
    authStatusVar("AUTHENTICATED");
    authInitCompleteVar(false);
    backendUserObj(null);
    renderAt("/profile");
    expect(screen.getByText("Loading...")).toBeInTheDocument();
    expect(screen.queryByTestId("location")).toBeNull();
  });
});
