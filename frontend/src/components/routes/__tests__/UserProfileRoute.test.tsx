import { render, screen } from "@testing-library/react";
import { MockedProvider } from "@apollo/client/testing";
import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { UserProfileRoute } from "../UserProfileRoute";
import {
  backendUserObj,
  openedUser,
  routeLoading,
  routeError,
} from "../../../graphql/cache";

vi.mock("../../../views/UserProfile", () => ({
  UserProfile: ({ user, isOwnProfile }: any) => (
    <div>
      <span>UserProfile:{user?.slug}</span>
      <span>isOwn:{String(Boolean(isOwnProfile))}</span>
    </div>
  ),
}));

vi.mock("../../widgets/ModernLoadingDisplay", () => ({
  ModernLoadingDisplay: () => <div>Loading...</div>,
}));

vi.mock("../../widgets/ModernErrorDisplay", () => ({
  ModernErrorDisplay: ({ error, title }: any) => (
    <div>
      <div>Title: {title}</div>
      <div>Error: {error?.message || error}</div>
    </div>
  ),
}));

/**
 * Tests for UserProfileRoute (dumb consumer).
 *
 * URL parsing, the GET_USER query, and the /profile redirect now live in
 * CentralRouteManager and ProfileRedirect respectively. UserProfileRoute
 * only reads the routing reactive vars (openedUser / routeLoading /
 * routeError) plus backendUserObj for ownership comparison and renders.
 */
describe("UserProfileRoute", () => {
  const renderRoute = () =>
    render(
      <MockedProvider mocks={[]} addTypename={false}>
        <MemoryRouter initialEntries={["/users/alice"]}>
          <UserProfileRoute />
        </MemoryRouter>
      </MockedProvider>
    );

  const profile = {
    id: "u-1",
    slug: "alice",
    username: "alice",
    email: "alice@example.com",
    name: "Alice",
    firstName: "Alice",
    lastName: "",
    isProfilePublic: true,
    reputationGlobal: 0,
    totalMessages: 0,
    totalThreadsCreated: 0,
    totalAnnotationsCreated: 0,
    totalDocumentsUploaded: 0,
  };

  beforeEach(() => {
    backendUserObj(null);
    openedUser(null);
    routeLoading(false);
    routeError(null);
  });

  afterEach(() => {
    vi.clearAllMocks();
    backendUserObj(null);
    openedUser(null);
    routeLoading(false);
    routeError(null);
  });

  it("shows loading UI when routeLoading is true and no user is resolved", () => {
    routeLoading(true);
    renderRoute();
    expect(screen.getByText("Loading...")).toBeInTheDocument();
  });

  it("renders 'User Not Found' when routeError is set", () => {
    routeError(new Error("nope"));
    renderRoute();
    expect(screen.getByText(/Title:.*User Not Found/)).toBeInTheDocument();
    expect(screen.getByText(/Error:.*nope/)).toBeInTheDocument();
  });

  it("renders 'User Not Found' when no user is in the reactive var", () => {
    renderRoute();
    expect(screen.getByText(/Title:.*User Not Found/)).toBeInTheDocument();
    expect(
      screen.getByText(/Error:.*does not exist or their profile is private/)
    ).toBeInTheDocument();
  });

  it("renders UserProfile with isOwnProfile=true when viewer matches openedUser", () => {
    backendUserObj({ id: "u-1", slug: "alice" } as any);
    openedUser(profile as any);
    renderRoute();
    expect(screen.getByText("UserProfile:alice")).toBeInTheDocument();
    expect(screen.getByText("isOwn:true")).toBeInTheDocument();
  });

  it("sets isOwnProfile=false when the viewer is a different user", () => {
    backendUserObj({ id: "u-99", slug: "bob" } as any);
    openedUser(profile as any);
    renderRoute();
    expect(screen.getByText("UserProfile:alice")).toBeInTheDocument();
    expect(screen.getByText("isOwn:false")).toBeInTheDocument();
  });

  it("prefers the resolved user over the loading state when both are set", () => {
    routeLoading(true);
    openedUser(profile as any);
    renderRoute();
    expect(screen.getByText("UserProfile:alice")).toBeInTheDocument();
    expect(screen.queryByText("Loading...")).toBeNull();
  });
});
