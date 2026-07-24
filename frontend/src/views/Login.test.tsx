import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MockedProvider } from "@apollo/client/testing";
import { MemoryRouter } from "react-router-dom";
import { Login } from "./Login";
import { LOGIN_MUTATION } from "../graphql/mutations";
import { authToken, authStatusVar, userObj } from "../graphql/cache";

// Regression coverage for issue #2104: in the local (non-Auth0) username/
// password login flow, App.tsx's GET_ME query is only skipped while
// authToken() is falsy. If Login.tsx sets authToken() before awaiting
// resetOnAuthChange() (which calls Apollo's clearStore()), GET_ME starts
// fetching immediately and clearStore() cancels that now in-flight request,
// surfacing an Apollo "store reset while query was in flight" invariant
// violation as "Could not get user details from server". Asserting call
// order here pins the fix: resetOnAuthChange() must resolve before
// authToken() is set.
const resetOnAuthChangeMock = vi.fn();

vi.mock("../hooks/useCacheManager", () => ({
  useCacheManager: () => ({
    resetOnAuthChange: resetOnAuthChangeMock,
  }),
}));

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>(
    "react-router-dom"
  );
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

const mockUser = {
  id: "1",
  email: "test@example.com",
  name: "Test User",
  username: "testuser",
  isUsageCapped: false,
  isSuperuser: false,
};

describe("Login", () => {
  let tokenAtResetTime: string | undefined;

  beforeEach(() => {
    vi.clearAllMocks();
    authToken("");
    authStatusVar("LOADING");
    userObj(null);
    tokenAtResetTime = undefined;

    resetOnAuthChangeMock.mockImplementation(async () => {
      // Capture authToken() at the moment resetOnAuthChange (clearStore) is
      // invoked — it must still be unset so App.tsx's GET_ME query stays
      // skipped for the entire duration of the cache clear.
      tokenAtResetTime = authToken();
      return { success: true, message: "ok" };
    });
  });

  it("clears the cache before setting authToken, avoiding the GET_ME/clearStore race", async () => {
    const mocks = [
      {
        request: {
          query: LOGIN_MUTATION,
          variables: { username: "testuser", password: "hunter2" },
        },
        result: {
          data: {
            tokenAuth: {
              token: "test-jwt-token",
              refreshExpiresIn: 1234,
              payload: {},
              user: mockUser,
            },
          },
        },
      },
    ];

    render(
      <MockedProvider mocks={mocks} addTypename={false}>
        <MemoryRouter>
          <Login />
        </MemoryRouter>
      </MockedProvider>
    );

    await userEvent.type(screen.getByPlaceholderText("Username"), "testuser");
    await userEvent.type(screen.getByPlaceholderText("Password"), "hunter2");
    await userEvent.click(screen.getByRole("button", { name: /login/i }));

    await waitFor(() => {
      expect(resetOnAuthChangeMock).toHaveBeenCalledWith({
        reason: "user_login",
        refetchActive: false,
      });
    });

    await waitFor(() => {
      expect(authToken()).toBe("test-jwt-token");
    });

    // The critical assertion: authToken() was still empty when
    // resetOnAuthChange (clearStore) ran, so GET_ME could not have raced it.
    expect(tokenAtResetTime).toBe("");
    expect(authStatusVar()).toBe("AUTHENTICATED");
    expect(userObj()).toEqual(mockUser);
    expect(mockNavigate).toHaveBeenCalledWith("/");
  });

  it("still authenticates when resetOnAuthChange rejects (best-effort cache clear)", async () => {
    resetOnAuthChangeMock.mockImplementation(async () => {
      tokenAtResetTime = authToken();
      throw new Error("clearStore failed");
    });

    const mocks = [
      {
        request: {
          query: LOGIN_MUTATION,
          variables: { username: "testuser", password: "hunter2" },
        },
        result: {
          data: {
            tokenAuth: {
              token: "test-jwt-token",
              refreshExpiresIn: 1234,
              payload: {},
              user: mockUser,
            },
          },
        },
      },
    ];

    render(
      <MockedProvider mocks={mocks} addTypename={false}>
        <MemoryRouter>
          <Login />
        </MemoryRouter>
      </MockedProvider>
    );

    await userEvent.type(screen.getByPlaceholderText("Username"), "testuser");
    await userEvent.type(screen.getByPlaceholderText("Password"), "hunter2");
    await userEvent.click(screen.getByRole("button", { name: /login/i }));

    await waitFor(() => {
      expect(authToken()).toBe("test-jwt-token");
    });

    expect(tokenAtResetTime).toBe("");
    expect(authStatusVar()).toBe("AUTHENTICATED");
    expect(mockNavigate).toHaveBeenCalledWith("/");
  });
});
