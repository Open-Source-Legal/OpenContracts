/**
 * errorLink Tests
 *
 * Verifies the Apollo error link actually executes its handler by piping a
 * terminating mock link that emits synthetic errors through the real
 * `errorLink`. This exercises every catch/return branch:
 *
 *  - GraphQL 401 / 403 / UNAUTHENTICATED → clears auth state + warn toast
 *  - Expired-JWT message variants → warn toast + window.location.reload
 *  - Message-based unauthorized / not-authenticated detection
 *  - Non-auth GraphQL errors → logged but auth state untouched
 *  - Network 401/403 → clears auth state + warn toast
 *  - Generic network error → error toast, auth state untouched
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { GraphQLError } from "graphql";
import {
  ApolloLink,
  Observable,
  execute,
  gql,
  FetchResult,
} from "@apollo/client";
import { toast } from "react-toastify";

import { errorLink } from "./errorLink";
import { authToken, authStatusVar, userObj } from "./cache";

// --- Mocks ------------------------------------------------------------------

vi.mock("react-toastify", () => ({
  toast: {
    warning: vi.fn(),
    error: vi.fn(),
  },
}));

// --- Helpers ----------------------------------------------------------------

const TEST_QUERY = gql`
  query Test {
    noop
  }
`;

/**
 * Build a terminating link that emits a GraphQL response containing the
 * provided errors (as a FetchResult) and then completes.
 */
function graphQLErrorLink(errors: GraphQLError[]): ApolloLink {
  return new ApolloLink(
    () =>
      new Observable<FetchResult>((observer) => {
        observer.next({ errors });
        observer.complete();
      })
  );
}

/**
 * Build a terminating link that errors the observable with a fake
 * "network error" (has `statusCode`, mimicking HttpLink behavior).
 */
function networkErrorLink(err: unknown): ApolloLink {
  return new ApolloLink(
    () =>
      new Observable<FetchResult>((observer) => {
        observer.error(err);
      })
  );
}

/**
 * Run a single operation through `errorLink -> terminating`. Returns a
 * promise that resolves once the observable completes or errors, so
 * tests can assert on side effects after the link chain has run.
 */
async function runOperation(terminating: ApolloLink): Promise<void> {
  await new Promise<void>((resolve) => {
    execute(ApolloLink.from([errorLink, terminating]), {
      query: TEST_QUERY,
    }).subscribe({
      next: () => {},
      error: () => resolve(),
      complete: () => resolve(),
    });
  });
}

// --- Tests ------------------------------------------------------------------

describe("errorLink", () => {
  let reloadSpy: ReturnType<typeof vi.fn>;
  let consoleErrorSpy: ReturnType<typeof vi.spyOn>;
  let consoleLogSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();

    // Seed authenticated state for each test
    authToken("test-token");
    authStatusVar("AUTHENTICATED");
    userObj({ email: "test@example.com", sub: "user123" } as any);

    // Stub window.location.reload (the real method is non-configurable in jsdom)
    reloadSpy = vi.fn();
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { ...window.location, reload: reloadSpy },
    });

    consoleErrorSpy = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);
    consoleLogSpy = vi
      .spyOn(console, "log")
      .mockImplementation(() => undefined);
  });

  afterEach(() => {
    vi.useRealTimers();
    consoleErrorSpy.mockRestore();
    consoleLogSpy.mockRestore();
  });

  // --- GraphQL errors -------------------------------------------------------

  describe("GraphQL auth errors", () => {
    it("clears auth state and shows toast on 401", async () => {
      const err = new GraphQLError("Forbidden", {
        extensions: { code: 401 },
      });

      await runOperation(graphQLErrorLink([err]));

      expect(authToken()).toBe("");
      expect(userObj()).toBeNull();
      expect(authStatusVar()).toBe("ANONYMOUS");
      expect(toast.warning).toHaveBeenCalledWith(
        expect.stringContaining("Your session has expired"),
        expect.objectContaining({ toastId: "auth-error" })
      );
      // Non-auth "other error" log path must not fire
      expect(reloadSpy).not.toHaveBeenCalled();
    });

    it("clears auth state on 403", async () => {
      const err = new GraphQLError("Forbidden", {
        extensions: { status: 403 },
      });

      await runOperation(graphQLErrorLink([err]));

      expect(authToken()).toBe("");
      expect(authStatusVar()).toBe("ANONYMOUS");
      expect(toast.warning).toHaveBeenCalledOnce();
    });

    it("clears auth state on UNAUTHENTICATED extension code", async () => {
      const err = new GraphQLError("nope", {
        extensions: { statusCode: "UNAUTHENTICATED" },
      });

      await runOperation(graphQLErrorLink([err]));

      expect(authToken()).toBe("");
      expect(authStatusVar()).toBe("ANONYMOUS");
    });

    it("detects 'unauthorized' in the error message", async () => {
      const err = new GraphQLError("User is Unauthorized for this resource");

      await runOperation(graphQLErrorLink([err]));

      expect(authToken()).toBe("");
      expect(authStatusVar()).toBe("ANONYMOUS");
    });

    it("detects 'not authenticated' in the error message", async () => {
      const err = new GraphQLError("User is not authenticated");

      await runOperation(graphQLErrorLink([err]));

      expect(authToken()).toBe("");
      expect(authStatusVar()).toBe("ANONYMOUS");
    });

    it("handles expired JWT with a reload and dedicated toast", async () => {
      const err = new GraphQLError("Signature has expired");

      await runOperation(graphQLErrorLink([err]));

      expect(toast.warning).toHaveBeenCalledWith(
        expect.stringContaining("session has expired. Refreshing"),
        expect.objectContaining({ toastId: "token-expired" })
      );
      expect(authToken()).toBe("");
      expect(reloadSpy).not.toHaveBeenCalled();

      // The link schedules reload via setTimeout(_, 1000)
      vi.advanceTimersByTime(1000);
      expect(reloadSpy).toHaveBeenCalledTimes(1);
    });

    it("leaves auth state untouched for non-auth GraphQL errors", async () => {
      const err = new GraphQLError("Internal server error", {
        extensions: { code: 500 },
      });

      await runOperation(graphQLErrorLink([err]));

      expect(authToken()).toBe("test-token");
      expect(authStatusVar()).toBe("AUTHENTICATED");
      expect(toast.warning).not.toHaveBeenCalled();
      expect(toast.error).not.toHaveBeenCalled();

      // Non-auth branch still logs for debugging
      const logged = consoleErrorSpy.mock.calls.some(
        (call: unknown[]) =>
          typeof call[0] === "string" &&
          (call[0] as string).includes("[GraphQL Error]")
      );
      expect(logged).toBe(true);
    });
  });

  // --- Network errors -------------------------------------------------------

  describe("Network errors", () => {
    it("clears auth state on 401 network error", async () => {
      const netErr = Object.assign(new Error("Unauthorized"), {
        statusCode: 401,
      });

      await runOperation(networkErrorLink(netErr));

      expect(authToken()).toBe("");
      expect(authStatusVar()).toBe("ANONYMOUS");
      expect(toast.warning).toHaveBeenCalledWith(
        expect.stringContaining("Your session has expired"),
        expect.objectContaining({ toastId: "auth-error" })
      );
    });

    it("clears auth state on 403 network error", async () => {
      const netErr = Object.assign(new Error("Forbidden"), {
        statusCode: 403,
      });

      await runOperation(networkErrorLink(netErr));

      expect(authToken()).toBe("");
      expect(authStatusVar()).toBe("ANONYMOUS");
    });

    it("shows network error toast for non-auth network failures", async () => {
      const netErr = Object.assign(new Error("ECONNREFUSED"), {
        statusCode: 0,
      });

      await runOperation(networkErrorLink(netErr));

      // Auth state preserved
      expect(authToken()).toBe("test-token");
      expect(authStatusVar()).toBe("AUTHENTICATED");

      expect(toast.error).toHaveBeenCalledWith(
        expect.stringContaining("Network error"),
        expect.objectContaining({ toastId: "network-error" })
      );
    });
  });
});
