import { render, screen, waitFor } from "@testing-library/react";
import { MockedProvider } from "@apollo/client/testing";
import { GraphQLError } from "graphql";
import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { UserProfileRoute } from "../UserProfileRoute";
import { backendUserObj } from "../../../graphql/cache";
import { GET_USER } from "../../../graphql/queries";

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
 * Tests for UserProfileRoute.
 *
 * The route handles both /profile (current user) and /users/:slug paths:
 *   - no slug + no logged-in user → redirect to /login
 *   - no slug + logged-in user   → redirect to /users/<currentUser.slug>
 *   - slug                        → query GET_USER and render UserProfile
 */
describe("UserProfileRoute", () => {
  const LocationReporter: React.FC = () => {
    const location = useLocation();
    return <div data-testid="location">{location.pathname}</div>;
  };

  beforeEach(() => {
    backendUserObj(null);
  });

  afterEach(() => {
    vi.clearAllMocks();
    backendUserObj(null);
  });

  const user = {
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

  const renderAtPath = (path: string, mocks: any[] = []) =>
    render(
      <MockedProvider mocks={mocks} addTypename={false}>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path="/profile" element={<UserProfileRoute />} />
            <Route path="/users/:slug" element={<UserProfileRoute />} />
            <Route path="/login" element={<LocationReporter />} />
          </Routes>
        </MemoryRouter>
      </MockedProvider>
    );

  it("redirects /profile to /login when no user is logged in", async () => {
    renderAtPath("/profile");
    const locationNode = await screen.findByTestId("location");
    expect(locationNode.textContent).toBe("/login");
  });

  it("redirects /profile to /users/<slug> when a user is logged in", async () => {
    backendUserObj({ id: "u-1", slug: "alice" } as any);

    render(
      <MockedProvider mocks={[]} addTypename={false}>
        <MemoryRouter initialEntries={["/profile"]}>
          <Routes>
            <Route path="/profile" element={<UserProfileRoute />} />
            <Route path="/users/:slug" element={<LocationReporter />} />
          </Routes>
        </MemoryRouter>
      </MockedProvider>
    );

    const loc = await screen.findByTestId("location");
    expect(loc.textContent).toBe("/users/alice");
  });

  it("redirects /profile and then renders /users/:slug without a Rules-of-Hooks crash (issue #1295)", async () => {
    // Regression guard: the pre-fix code called useQuery *after* the
    // early-return for the no-slug case, so when /profile redirected to
    // /users/:slug the same UserProfileRoute fiber transitioned from 0 to 1
    // hook and React threw. With useQuery hoisted unconditionally, the two
    // renders share the same hook ordering and the redirect survives.
    backendUserObj({ id: "u-1", slug: "alice" } as any);

    render(
      <MockedProvider
        mocks={[
          {
            request: { query: GET_USER, variables: { slug: "alice" } },
            result: { data: { userBySlug: user } },
          },
        ]}
        addTypename={false}
      >
        <MemoryRouter initialEntries={["/profile"]}>
          <Routes>
            <Route path="/profile" element={<UserProfileRoute />} />
            <Route path="/users/:slug" element={<UserProfileRoute />} />
          </Routes>
        </MemoryRouter>
      </MockedProvider>
    );

    await waitFor(() => {
      expect(screen.getByText("UserProfile:alice")).toBeInTheDocument();
    });
  });

  it("renders UserProfile with isOwnProfile=true when viewer is the profile owner", async () => {
    backendUserObj({ id: "u-1", slug: "alice" } as any);

    renderAtPath("/users/alice", [
      {
        request: { query: GET_USER, variables: { slug: "alice" } },
        result: { data: { userBySlug: user } },
      },
    ]);

    await waitFor(() => {
      expect(screen.getByText("UserProfile:alice")).toBeInTheDocument();
    });
    expect(screen.getByText("isOwn:true")).toBeInTheDocument();
  });

  it("shows loading UI while GET_USER is pending", () => {
    renderAtPath("/users/alice", [
      {
        request: { query: GET_USER, variables: { slug: "alice" } },
        delay: 100,
        result: { data: { userBySlug: user } },
      },
    ]);
    expect(screen.getByText("Loading...")).toBeInTheDocument();
  });

  it("renders 'User Not Found' when GET_USER returns an error", async () => {
    renderAtPath("/users/ghost", [
      {
        request: { query: GET_USER, variables: { slug: "ghost" } },
        result: { errors: [new GraphQLError("nope")] },
      },
    ]);

    await waitFor(() => {
      expect(screen.getByText(/Title:.*User Not Found/)).toBeInTheDocument();
    });
  });

  it("renders 'User Not Found' when no user is returned", async () => {
    renderAtPath("/users/missing", [
      {
        request: { query: GET_USER, variables: { slug: "missing" } },
        result: { data: { userBySlug: null } },
      },
    ]);

    await waitFor(() => {
      expect(screen.getByText(/Title:.*User Not Found/)).toBeInTheDocument();
    });
    expect(
      screen.getByText(/Error:.*does not exist or their profile is private/)
    ).toBeInTheDocument();
  });

  it("sets isOwnProfile=false when the viewer is a different user", async () => {
    backendUserObj({ id: "u-99", slug: "bob" } as any);

    renderAtPath("/users/alice", [
      {
        request: { query: GET_USER, variables: { slug: "alice" } },
        result: { data: { userBySlug: user } },
      },
    ]);

    await waitFor(() => {
      expect(screen.getByText("UserProfile:alice")).toBeInTheDocument();
    });
    expect(screen.getByText("isOwn:false")).toBeInTheDocument();
  });
});
