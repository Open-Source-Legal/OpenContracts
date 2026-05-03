import { onError } from "@apollo/client/link/error";
import { toast } from "react-toastify";
import { authToken, authStatusVar, userObj } from "./cache";

/**
 * Length of the response-body excerpt logged when JSON parsing fails. Long
 * enough to expose where the truncation occurred without flooding the console
 * with megabytes of body text on a wedged transport. The preview is
 * already-client-side data; capping at 500 chars exposes the truncation point
 * without risking megabytes of PII landing in the console if the body is huge.
 */
const PARSE_ERROR_BODY_PREVIEW_CHARS = 500;

/**
 * Toast ID used for ``ServerParseError``-driven toasts. Exported so tests can
 * import the same string the implementation emits, preventing silent drift if
 * the literal is ever renamed.
 */
export const SERVER_PARSE_ERROR_TOAST_ID = "server-parse-error";

/**
 * Detect Apollo's ``ServerParseError`` — thrown by ``parseJsonBody`` in
 * ``@apollo/client/link/http`` when the HTTP response cannot be parsed as
 * JSON (truncated body, unexpected content type, etc.).  Apollo sets
 * ``name === "ServerParseError"`` and attaches ``bodyText``/``response``,
 * so duck-type on those rather than ``instanceof``.
 */
const isServerParseError = (
  err: unknown
): err is Error & { bodyText?: string; response?: Response } => {
  return (
    err instanceof Error && err.name === "ServerParseError" && "bodyText" in err
  );
};

/**
 * Apollo error link that handles authentication errors and network errors.
 *
 * For 401/403 errors:
 * - Switches to ANONYMOUS mode (allows browsing public content)
 * - Shows a toast notification with option to log back in
 * - Clears auth token and user object
 *
 * For ServerParseError (malformed JSON response body):
 * - Logs the response status, URL, and a body excerpt for diagnosis
 * - Shows an actionable toast that distinguishes this from a connectivity
 *   failure
 *
 * For other GraphQL errors:
 * - Logs to console for debugging
 *
 * For network errors:
 * - Shows a toast notification
 */
export const errorLink = onError(
  ({ graphQLErrors, networkError, operation, forward }) => {
    if (graphQLErrors) {
      for (const err of graphQLErrors) {
        const statusCode =
          err.extensions?.code ||
          err.extensions?.status ||
          err.extensions?.statusCode;

        const isExpiredToken =
          err.message?.toLowerCase().includes("signature has expired") ||
          err.message?.toLowerCase().includes("token expired") ||
          err.message?.toLowerCase().includes("jwt expired");

        // Handle authentication errors (401/403) or expired tokens
        if (
          statusCode === 401 ||
          statusCode === 403 ||
          statusCode === "UNAUTHENTICATED" ||
          err.message?.toLowerCase().includes("unauthorized") ||
          err.message?.toLowerCase().includes("not authenticated") ||
          isExpiredToken
        ) {
          console.error(
            "[Apollo Error Link] Authentication error detected:",
            err
          );

          if (isExpiredToken) {
            console.log(
              "[Apollo Error Link] Token has expired - forcing page reload to trigger token refresh"
            );

            // Clear auth state
            authToken("");
            userObj(null);
            authStatusVar("ANONYMOUS");

            // Force a page reload to trigger AuthGate token refresh
            // This will call getAccessTokenSilently() which handles token refresh automatically
            toast.warning("Your session has expired. Refreshing...", {
              toastId: "token-expired",
              autoClose: 2000,
            });

            // Reload after a short delay to show the toast
            setTimeout(() => {
              window.location.reload();
            }, 1000);

            return;
          }

          // Switch to anonymous mode - allows user to browse public content
          // without forcing an immediate re-login
          authToken("");
          userObj(null);
          authStatusVar("ANONYMOUS");

          // Show user-friendly message with guidance
          toast.warning(
            "Your session has expired. Please log in again to access protected content.",
            {
              toastId: "auth-error", // Prevent duplicate toasts
              autoClose: 8000,
            }
          );

          return;
        }

        // Log other GraphQL errors for debugging
        console.error(
          `[GraphQL Error] Message: ${err.message}, Location: ${JSON.stringify(
            err.locations
          )}, Path: ${err.path}`,
          err
        );
      }
    }

    if (networkError) {
      const netErr = networkError as any;

      // Handle network-level authentication errors
      if (netErr.statusCode === 401 || netErr.statusCode === 403) {
        console.error("[Apollo Error Link] Network auth error:", networkError);

        // Switch to anonymous mode - allows user to browse public content
        authToken("");
        userObj(null);
        authStatusVar("ANONYMOUS");

        toast.warning(
          "Your session has expired. Please log in again to access protected content.",
          {
            toastId: "auth-error",
            autoClose: 8000,
          }
        );

        return;
      }

      // ServerParseError: the HTTP request returned a body that wasn't valid
      // JSON (e.g. truncated mid-stream by a worker timeout, an HTML error
      // page from an upstream proxy, or a partial chunked response). Apollo
      // wraps these as networkError so they otherwise hit the generic
      // "check your connection" toast — which misleads users since the
      // connection is fine. Log enough detail to diagnose, and surface a
      // distinct message.
      if (isServerParseError(networkError)) {
        const bodyText = networkError.bodyText ?? "";
        const preview = bodyText.slice(0, PARSE_ERROR_BODY_PREVIEW_CHARS);
        const operationLabel = operation.operationName || "unknown operation";
        console.error(
          "[Apollo Error Link] Server returned a malformed JSON response.",
          {
            operationName: operationLabel,
            status: networkError.response?.status,
            url: networkError.response?.url,
            bodyLength: bodyText.length,
            bodyPreview: preview,
            originalMessage: networkError.message,
          }
        );

        toast.error(
          `The server returned an unreadable response for "${operationLabel}". ` +
            `This usually means the request timed out or was interrupted. Please retry.`,
          {
            toastId: SERVER_PARSE_ERROR_TOAST_ID,
            autoClose: 8000,
          }
        );

        return;
      }

      // Log other network errors
      console.error(`[Network Error]: ${networkError}`, networkError);

      // Show user-friendly network error message
      toast.error(
        "Network error. Please check your connection and try again.",
        {
          toastId: "network-error",
          autoClose: 5000,
        }
      );
    }
  }
);
