/**
 * useNavMenu logout-cleanup tests.
 *
 * Pins the new behaviour added to `requestLogout()`: it must drop the
 * `oc_has_authenticated` hint from `localStorage` so the next visit
 * takes AuthGate's fast first-time-visitor path instead of the slow
 * silent-token verification. The catch branch (localStorage unavailable)
 * must not crash the logout flow.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react-hooks";

// --- Mock external hook dependencies before importing useNavMenu ----------

const mockNavigate = vi.fn();
const mockLogout = vi.fn();
const mockLoginWithPopup = vi.fn();
const mockLoginWithRedirect = vi.fn();
const mockResetOnAuthChange = vi.fn(() => Promise.resolve());

vi.mock("react-router-dom", () => ({
  useLocation: () => ({ pathname: "/" }),
  useNavigate: () => mockNavigate,
}));

vi.mock("@auth0/auth0-react", () => ({
  useAuth0: () => ({
    loginWithRedirect: mockLoginWithRedirect,
    loginWithPopup: mockLoginWithPopup,
    logout: mockLogout,
    user: undefined,
    isLoading: false,
  }),
}));

vi.mock("../../hooks/UseEnv", () => ({
  useEnv: () => ({
    REACT_APP_USE_AUTH0: false,
    REACT_APP_AUDIENCE: "",
  }),
}));

vi.mock("../../../hooks/useCacheManager", () => ({
  useCacheManager: () => ({ resetOnAuthChange: mockResetOnAuthChange }),
}));

// Imported after the mocks above so the mocked deps are picked up.
import { useNavMenu } from "../useNavMenu";
import { authToken, authStatusVar, userObj } from "../../../graphql/cache";

describe("useNavMenu.requestLogout", () => {
  beforeEach(() => {
    authToken("seed-token");
    authStatusVar("AUTHENTICATED");
    userObj({ id: "user-1" } as any);
    localStorage.setItem("oc_has_authenticated", "true");
  });

  afterEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    authToken("");
    authStatusVar("ANONYMOUS");
    userObj(null);
  });

  it("clears auth state and removes the oc_has_authenticated hint", async () => {
    const { result } = renderHook(() => useNavMenu());

    await act(async () => {
      result.current.requestLogout();
      // Let the fire-and-forget cache reset settle.
      await Promise.resolve();
    });

    expect(authToken()).toBe("");
    expect(authStatusVar()).toBe("ANONYMOUS");
    expect(userObj()).toBeNull();
    expect(localStorage.getItem("oc_has_authenticated")).toBeNull();
    expect(mockResetOnAuthChange).toHaveBeenCalledWith({
      reason: "user_logout",
      refetchActive: false,
    });
    // Auth0 disabled in this test → falls back to navigate("/").
    expect(mockNavigate).toHaveBeenCalledWith("/");
    expect(mockLogout).not.toHaveBeenCalled();
  });

  it("swallows localStorage errors so logout still completes", async () => {
    const removeItemSpy = vi
      .spyOn(Storage.prototype, "removeItem")
      .mockImplementation(() => {
        throw new Error("storage disabled");
      });

    const { result } = renderHook(() => useNavMenu());

    await act(async () => {
      result.current.requestLogout();
      await Promise.resolve();
    });

    expect(removeItemSpy).toHaveBeenCalledWith("oc_has_authenticated");
    expect(authToken()).toBe("");
    expect(authStatusVar()).toBe("ANONYMOUS");
    expect(mockResetOnAuthChange).toHaveBeenCalled();
    expect(mockNavigate).toHaveBeenCalledWith("/");

    removeItemSpy.mockRestore();
  });
});
