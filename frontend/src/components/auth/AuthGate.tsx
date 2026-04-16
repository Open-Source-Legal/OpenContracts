import React, { useEffect, useState, useRef } from "react";
import { useAuth0 } from "@auth0/auth0-react";
import { useReactiveVar } from "@apollo/client";
import {
  authToken,
  authStatusVar,
  userObj,
  authInitCompleteVar,
} from "../../graphql/cache";
import { toast } from "react-toastify";
import { ModernLoadingDisplay } from "../widgets/ModernLoadingDisplay";
import { useCacheManager } from "../../hooks/useCacheManager";
import { getRuntimeEnv } from "../../utils/env";

// LocalStorage key to track if user has ever successfully authenticated.
// Used to distinguish first-time visitors from returning users with expired sessions.
// Keyed by Auth0 domain so switching tenants resets the flag.
const HAS_AUTHENTICATED_KEY = "oc_has_authenticated";
const AUTH_DOMAIN_KEY = "oc_auth0_domain";

/**
 * Check if user has authenticated before on the CURRENT Auth0 tenant.
 * Returns false if the stored domain doesn't match (tenant was switched).
 */
function hasAuthenticatedOnCurrentTenant(): boolean {
  try {
    const { REACT_APP_APPLICATION_DOMAIN } = getRuntimeEnv();
    const storedDomain = localStorage.getItem(AUTH_DOMAIN_KEY);
    if (storedDomain && storedDomain !== REACT_APP_APPLICATION_DOMAIN) {
      // Tenant changed — clear stale flag so we don't try the slow iframe path
      localStorage.removeItem(HAS_AUTHENTICATED_KEY);
      localStorage.setItem(AUTH_DOMAIN_KEY, REACT_APP_APPLICATION_DOMAIN);
      return false;
    }
    return localStorage.getItem(HAS_AUTHENTICATED_KEY) === "true";
  } catch {
    return false;
  }
}

/** Store auth flag together with the current Auth0 domain. */
function markAuthenticated(): void {
  try {
    const { REACT_APP_APPLICATION_DOMAIN } = getRuntimeEnv();
    localStorage.setItem(HAS_AUTHENTICATED_KEY, "true");
    localStorage.setItem(AUTH_DOMAIN_KEY, REACT_APP_APPLICATION_DOMAIN);
  } catch {
    // localStorage may be unavailable
  }
}

interface AuthGateProps {
  children: React.ReactNode;
  useAuth0: boolean;
  audience?: string;
}

/**
 * AuthGate ensures authentication is fully initialized before rendering children.
 * This prevents race conditions where components try to make authenticated requests
 * before the auth token is available.
 */
export const AuthGate: React.FC<AuthGateProps> = ({
  children,
  useAuth0: useAuth0Flag,
  audience,
}) => {
  const [authInitialized, setAuthInitialized] = useState(false);
  const authStatus = useReactiveVar(authStatusVar);
  const { resetOnAuthChange } = useCacheManager();

  // Ref to prevent duplicate auth flows during race conditions
  // When the else branch starts handling auth (via getAccessTokenSilently),
  // this prevents the if branch from also handling it if state updates mid-flow
  const authFlowInProgressRef = useRef(false);

  // Auth0 hooks
  const {
    isLoading: auth0Loading,
    isAuthenticated,
    user,
    getAccessTokenSilently,
  } = useAuth0();

  // Handle Auth0 authentication
  useEffect(() => {
    // Cancellation flag: when the effect re-runs or the component unmounts,
    // in-flight promise callbacks must not update shared reactive variables.
    // Without this, unmounted components leak stale values into authToken/etc.
    let cancelled = false;

    if (!useAuth0Flag) {
      // Non-Auth0 mode: immediately mark as initialized
      if (authStatusVar() === "LOADING") {
        authStatusVar("ANONYMOUS");
      }
      authInitCompleteVar(true);
      setAuthInitialized(true);
      return () => {
        cancelled = true;
      };
    }

    // Auth0 mode
    if (auth0Loading) {
      console.log("[AuthGate] Auth0 is still loading...");
      return () => {
        cancelled = true;
      };
    }

    // Auth0 has finished loading
    if (isAuthenticated && user) {
      // Skip if another auth flow is already in progress (race condition handling)
      if (authFlowInProgressRef.current) {
        console.log(
          "[AuthGate] Auth flow already in progress, skipping duplicate..."
        );
        return () => {
          cancelled = true;
        };
      }

      console.log("[AuthGate] User is authenticated, fetching access token...");

      getAccessTokenSilently({
        authorizationParams: {
          audience: audience || undefined,
          scope: "openid profile email",
        },
      })
        .then(async (token) => {
          if (cancelled) return;
          if (token) {
            console.log("[AuthGate] Token obtained successfully");

            markAuthenticated();

            // RACE CONDITION PREVENTION: Auth state MUST be set synchronously BEFORE
            // cache clear. clearStore() is async and may trigger Apollo query refetches.
            // If auth state isn't set first, those refetches would execute with stale/missing
            // credentials, causing auth errors or returning anonymous data that gets cached.
            // By setting token/user/status synchronously here, any subsequent queries
            // (whether from cache clear or component mounts) will use correct auth context.
            authToken(token);
            userObj(user);
            authStatusVar("AUTHENTICATED");

            // Verify the token was set
            const verifyToken = authToken();
            console.log(
              "[AuthGate] Token verified:",
              verifyToken ? "Present" : "Missing"
            );

            // Clear any stale anonymous/previous-user cache data.
            // We MUST await this because clearStore() aborts in-flight queries.
            // If we set authInitCompleteVar(true) before clearStore() finishes,
            // GET_ME fires immediately and gets aborted (NS_BINDING_ABORTED).
            // refetchActive is false because no children are mounted yet —
            // there are zero active queries to refetch.
            try {
              await resetOnAuthChange({
                reason: "auth0_login",
                refetchActive: false,
              });
            } catch (cacheError) {
              // Log with context for debugging but don't block - cache clear is best-effort
              console.warn("[AuthGate] Cache reset failed on login:", {
                error:
                  cacheError instanceof Error ? cacheError.message : cacheError,
                userId: user?.sub,
              });
            }

            if (cancelled) return;

            // Signal that auth initialization (including cache clear) is complete.
            // This MUST be set AFTER clearStore() to prevent GET_ME from being aborted.
            authInitCompleteVar(true);
            setAuthInitialized(true);
          } else {
            console.error("[AuthGate] No token received from Auth0");
            authToken("");
            userObj(null);
            authStatusVar("ANONYMOUS");
            authInitCompleteVar(true);
            setAuthInitialized(true);
            toast.error("Unable to authenticate: no token received");
          }
        })
        .catch((error) => {
          if (cancelled) return;
          console.error("[AuthGate] Error getting access token:", error);

          // Token fetch failed even though isAuthenticated was true.
          // This can happen with session issues. Fall back to anonymous
          // and let user click login if they want to authenticate.
          const errorCode = error.error;
          const isSessionError =
            errorCode === "login_required" ||
            errorCode === "consent_required" ||
            errorCode === "interaction_required" ||
            error.message?.toLowerCase().includes("login required");

          if (isSessionError) {
            console.log(
              "[AuthGate] Session error, falling back to anonymous mode"
            );
          } else {
            console.error("[AuthGate] Auth error, falling back to anonymous");
            toast.error("Authentication failed: " + error.message);
          }

          authToken("");
          userObj(null);
          authStatusVar("ANONYMOUS");
          authInitCompleteVar(true);
          setAuthInitialized(true);
        });
    } else {
      // Not authenticated according to isAuthenticated flag.
      // BUT there's a race condition during Auth0 callback where isAuthenticated
      // is briefly false while the SDK is still updating state.
      // To handle this, we verify by attempting to get a token silently.
      // If tokens exist (from just-completed callback), getAccessTokenSilently succeeds
      // and we handle auth here instead of waiting for the buggy state update.

      // Skip if another auth flow is already in progress
      if (authFlowInProgressRef.current) {
        console.log(
          "[AuthGate] Auth flow already in progress, skipping duplicate..."
        );
        return () => {
          cancelled = true;
        };
      }

      // Detect if we're in an OAuth callback (URL has code + state params).
      // The race condition only occurs during callback processing, so we
      // only need the slow iframe verification in that case.
      const params = new URLSearchParams(window.location.search);
      const isOAuthCallback = params.has("code") && params.has("state");

      // Also check if the user has ever authenticated on the CURRENT tenant.
      // First-time visitors (or users who switched tenants) have no session
      // to verify — skip straight to anonymous.
      if (!isOAuthCallback && !hasAuthenticatedOnCurrentTenant()) {
        // No callback in progress and never authenticated — go anonymous immediately
        console.log(
          "[AuthGate] First-time visitor, skipping token verification"
        );
        authToken("");
        userObj(null);
        authStatusVar("ANONYMOUS");
        authInitCompleteVar(true);
        setAuthInitialized(true);
        return () => {
          cancelled = true;
        };
      }

      console.log(
        "[AuthGate] isAuthenticated is false, verifying with getAccessTokenSilently..."
      );

      // Mark that we're starting an auth flow
      authFlowInProgressRef.current = true;

      // Use a short timeout for the verification call. The default (60s)
      // causes a long hang when there's no valid session. During OAuth
      // callback the response is near-instant; for returning users with
      // expired sessions, 10s is plenty.
      getAccessTokenSilently({
        authorizationParams: {
          audience: audience || undefined,
          scope: "openid profile email",
        },
        timeoutInSeconds: 10,
      })
        .then((token) => {
          if (cancelled) return;
          // We have a token despite isAuthenticated being false!
          // This is the race condition. The SDK has tokens but hasn't updated isAuthenticated yet.
          // Set auth state now rather than waiting for the next effect run.
          console.log(
            "[AuthGate] Race condition detected - have token despite isAuthenticated:false"
          );

          markAuthenticated();

          // Set auth state with the token we just got
          // Note: we don't have the user object here, but it will be populated
          // when the effect runs again with correct isAuthenticated state
          authToken(token);
          authStatusVar("AUTHENTICATED");

          // Clear cache and complete initialization
          resetOnAuthChange({
            reason: "auth0_login_race_condition",
            refetchActive: false,
          })
            .catch((cacheError) => {
              console.warn("[AuthGate] Cache reset failed:", cacheError);
            })
            .finally(() => {
              if (cancelled) return;
              authInitCompleteVar(true);
              setAuthInitialized(true);
              // Note: we don't reset authFlowInProgressRef here because
              // we want to prevent any subsequent effect runs from restarting auth
            });
        })
        .catch((error) => {
          if (cancelled) return;
          // getAccessTokenSilently failed - user is not authenticated
          // This could be:
          // 1. First-time visitor (no prior session)
          // 2. Returning user whose session expired
          // 3. User who just logged out
          //
          // We don't auto-redirect to login because:
          // - Users who logged out explicitly want to be anonymous
          // - Forcing login creates poor UX
          // - Users can always click the login button if they want to authenticate
          const errorCode = error.error;
          const isExpectedAnonymous =
            errorCode === "login_required" ||
            errorCode === "consent_required" ||
            errorCode === "interaction_required";

          if (!isExpectedAnonymous) {
            // Unexpected error - log it
            console.error(
              "[AuthGate] Unexpected error from getAccessTokenSilently:",
              error
            );
          }

          // Set anonymous state - user can login via the UI if they want
          console.log("[AuthGate] User is not authenticated (verified)");
          authToken("");
          userObj(null);
          authStatusVar("ANONYMOUS");
          authInitCompleteVar(true);
          setAuthInitialized(true);
        });
    }

    return () => {
      cancelled = true;
    };
  }, [
    useAuth0Flag,
    auth0Loading,
    isAuthenticated,
    user,
    getAccessTokenSilently,
    audience,
    resetOnAuthChange,
  ]);

  // Show loading screen while auth is initializing
  if (!authInitialized || authStatus === "LOADING") {
    return (
      <ModernLoadingDisplay
        type="auth"
        message="Initializing OpenContracts"
        fullScreen={true}
        size="large"
      />
    );
  }

  // Auth is ready, render children
  return <>{children}</>;
};
