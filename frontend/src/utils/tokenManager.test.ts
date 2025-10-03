import { describe, it, expect, beforeEach, vi } from "vitest";
import {
  getToken,
  setAuth0TokenGetter,
  clearAuth0TokenGetter,
} from "./tokenManager";

// Mock the env module
const mockGetRuntimeEnv = vi.fn();
vi.mock("./env", () => ({
  getRuntimeEnv: () => mockGetRuntimeEnv(),
}));

// Mock the cache module
const mockAuthToken = vi.fn();
vi.mock("../graphql/cache", () => ({
  authToken: () => mockAuthToken(),
}));

describe("tokenManager", () => {
  beforeEach(() => {
    // Reset all mocks before each test
    vi.clearAllMocks();
    clearAuth0TokenGetter();

    // Reset getRuntimeEnv to default (non-Auth0)
    mockGetRuntimeEnv.mockReturnValue({
      REACT_APP_USE_AUTH0: false,
      REACT_APP_APPLICATION_DOMAIN: "",
      REACT_APP_APPLICATION_CLIENT_ID: "",
      REACT_APP_AUDIENCE: "",
      REACT_APP_API_ROOT_URL: "",
      REACT_APP_USE_ANALYZERS: false,
      REACT_APP_ALLOW_IMPORTS: false,
    });

    // Reset authToken to return empty string by default
    mockAuthToken.mockReturnValue("");
  });

  describe("Non-Auth0 Mode", () => {
    it("should return cached token from authToken reactive var", async () => {
      const cachedToken = "cached-token-123";
      mockAuthToken.mockReturnValue(cachedToken);

      const token = await getToken();

      expect(token).toBe(cachedToken);
    });

    it("should return empty string when no cached token", async () => {
      mockAuthToken.mockReturnValue("");

      const token = await getToken();

      expect(token).toBe("");
    });

    it("should return empty string when cached token is null", async () => {
      mockAuthToken.mockReturnValue(null);

      const token = await getToken();

      expect(token).toBe("");
    });

    it("should not call Auth0 token getter even if registered", async () => {
      const cachedToken = "cached-token-456";
      mockAuthToken.mockReturnValue(cachedToken);

      const mockAuth0Getter = vi.fn().mockResolvedValue("auth0-token");
      setAuth0TokenGetter(mockAuth0Getter);

      const token = await getToken();

      expect(token).toBe(cachedToken);
      expect(mockAuth0Getter).not.toHaveBeenCalled();
    });
  });

  describe("Auth0 Mode", () => {
    beforeEach(() => {
      mockGetRuntimeEnv.mockReturnValue({
        REACT_APP_USE_AUTH0: true,
        REACT_APP_APPLICATION_DOMAIN: "test.auth0.com",
        REACT_APP_APPLICATION_CLIENT_ID: "test-client-id",
        REACT_APP_AUDIENCE: "test-audience",
        REACT_APP_API_ROOT_URL: "",
        REACT_APP_USE_ANALYZERS: false,
        REACT_APP_ALLOW_IMPORTS: false,
      });
    });

    it("should call Auth0 token getter when registered", async () => {
      const mockAuth0Token = "auth0-fresh-token-123";
      const mockAuth0Getter = vi.fn().mockResolvedValue(mockAuth0Token);

      setAuth0TokenGetter(mockAuth0Getter);

      const token = await getToken();

      expect(token).toBe(mockAuth0Token);
      expect(mockAuth0Getter).toHaveBeenCalledTimes(1);
    });

    it("should return empty string when Auth0 getter returns null", async () => {
      const mockAuth0Getter = vi.fn().mockResolvedValue(null);

      setAuth0TokenGetter(mockAuth0Getter);

      const token = await getToken();

      expect(token).toBe("");
      expect(mockAuth0Getter).toHaveBeenCalled();
    });

    it("should return empty string when Auth0 getter returns empty string", async () => {
      const mockAuth0Getter = vi.fn().mockResolvedValue("");

      setAuth0TokenGetter(mockAuth0Getter);

      const token = await getToken();

      expect(token).toBe("");
    });

    it("should fallback to cached token when Auth0 getter not registered", async () => {
      const cachedToken = "fallback-cached-token";
      mockAuthToken.mockReturnValue(cachedToken);

      const token = await getToken();

      expect(token).toBe(cachedToken);
    });

    it("should fallback to cached token when Auth0 getter fails", async () => {
      const cachedToken = "fallback-token-after-error";
      mockAuthToken.mockReturnValue(cachedToken);

      const mockAuth0Getter = vi
        .fn()
        .mockRejectedValue(new Error("Auth0 error"));

      setAuth0TokenGetter(mockAuth0Getter);

      // Spy on console.error to suppress error output in tests
      const consoleErrorSpy = vi
        .spyOn(console, "error")
        .mockImplementation(() => {});

      const token = await getToken();

      expect(token).toBe(cachedToken);
      expect(mockAuth0Getter).toHaveBeenCalled();
      expect(consoleErrorSpy).toHaveBeenCalledWith(
        expect.stringContaining("[tokenManager] Failed to get Auth0 token"),
        expect.any(Error)
      );

      consoleErrorSpy.mockRestore();
    });

    it("should return empty string when Auth0 fails and no cached token", async () => {
      mockAuthToken.mockReturnValue("");

      const mockAuth0Getter = vi
        .fn()
        .mockRejectedValue(new Error("Network error"));

      setAuth0TokenGetter(mockAuth0Getter);

      const consoleErrorSpy = vi
        .spyOn(console, "error")
        .mockImplementation(() => {});

      const token = await getToken();

      expect(token).toBe("");

      consoleErrorSpy.mockRestore();
    });
  });

  describe("Token Getter Management", () => {
    it("should allow registering an Auth0 token getter", async () => {
      mockGetRuntimeEnv.mockReturnValue({
        REACT_APP_USE_AUTH0: true,
        REACT_APP_APPLICATION_DOMAIN: "",
        REACT_APP_APPLICATION_CLIENT_ID: "",
        REACT_APP_AUDIENCE: "",
        REACT_APP_API_ROOT_URL: "",
        REACT_APP_USE_ANALYZERS: false,
        REACT_APP_ALLOW_IMPORTS: false,
      });

      const mockGetter = vi.fn().mockResolvedValue("token-123");

      setAuth0TokenGetter(mockGetter);

      await getToken();

      expect(mockGetter).toHaveBeenCalled();
    });

    it("should allow clearing the Auth0 token getter", async () => {
      mockGetRuntimeEnv.mockReturnValue({
        REACT_APP_USE_AUTH0: true,
        REACT_APP_APPLICATION_DOMAIN: "",
        REACT_APP_APPLICATION_CLIENT_ID: "",
        REACT_APP_AUDIENCE: "",
        REACT_APP_API_ROOT_URL: "",
        REACT_APP_USE_ANALYZERS: false,
        REACT_APP_ALLOW_IMPORTS: false,
      });

      const cachedToken = "cached-token";
      mockAuthToken.mockReturnValue(cachedToken);

      const mockGetter = vi.fn().mockResolvedValue("auth0-token");
      setAuth0TokenGetter(mockGetter);

      clearAuth0TokenGetter();

      const token = await getToken();

      expect(token).toBe(cachedToken);
      expect(mockGetter).not.toHaveBeenCalled();
    });

    it("should allow replacing the Auth0 token getter", async () => {
      mockGetRuntimeEnv.mockReturnValue({
        REACT_APP_USE_AUTH0: true,
        REACT_APP_APPLICATION_DOMAIN: "",
        REACT_APP_APPLICATION_CLIENT_ID: "",
        REACT_APP_AUDIENCE: "",
        REACT_APP_API_ROOT_URL: "",
        REACT_APP_USE_ANALYZERS: false,
        REACT_APP_ALLOW_IMPORTS: false,
      });

      const mockGetter1 = vi.fn().mockResolvedValue("token-1");
      const mockGetter2 = vi.fn().mockResolvedValue("token-2");

      setAuth0TokenGetter(mockGetter1);
      setAuth0TokenGetter(mockGetter2);

      const token = await getToken();

      expect(token).toBe("token-2");
      expect(mockGetter1).not.toHaveBeenCalled();
      expect(mockGetter2).toHaveBeenCalled();
    });
  });

  describe("Edge Cases", () => {
    it("should handle synchronous errors in Auth0 getter", async () => {
      mockGetRuntimeEnv.mockReturnValue({
        REACT_APP_USE_AUTH0: true,
        REACT_APP_APPLICATION_DOMAIN: "",
        REACT_APP_APPLICATION_CLIENT_ID: "",
        REACT_APP_AUDIENCE: "",
        REACT_APP_API_ROOT_URL: "",
        REACT_APP_USE_ANALYZERS: false,
        REACT_APP_ALLOW_IMPORTS: false,
      });

      const cachedToken = "fallback";
      mockAuthToken.mockReturnValue(cachedToken);

      const mockGetter = vi.fn().mockImplementation(() => {
        throw new Error("Synchronous error");
      });

      setAuth0TokenGetter(mockGetter);

      const consoleErrorSpy = vi
        .spyOn(console, "error")
        .mockImplementation(() => {});

      const token = await getToken();

      expect(token).toBe(cachedToken);

      consoleErrorSpy.mockRestore();
    });

    it("should handle undefined return from authToken", async () => {
      mockAuthToken.mockReturnValue(undefined);

      const token = await getToken();

      expect(token).toBe("");
    });

    it("should work correctly when called multiple times concurrently", async () => {
      mockGetRuntimeEnv.mockReturnValue({
        REACT_APP_USE_AUTH0: true,
        REACT_APP_APPLICATION_DOMAIN: "",
        REACT_APP_APPLICATION_CLIENT_ID: "",
        REACT_APP_AUDIENCE: "",
        REACT_APP_API_ROOT_URL: "",
        REACT_APP_USE_ANALYZERS: false,
        REACT_APP_ALLOW_IMPORTS: false,
      });

      const mockGetter = vi.fn().mockResolvedValue("concurrent-token");
      setAuth0TokenGetter(mockGetter);

      const [token1, token2, token3] = await Promise.all([
        getToken(),
        getToken(),
        getToken(),
      ]);

      expect(token1).toBe("concurrent-token");
      expect(token2).toBe("concurrent-token");
      expect(token3).toBe("concurrent-token");
      expect(mockGetter).toHaveBeenCalledTimes(3);
    });
  });
});
