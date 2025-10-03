/**
 * Token Manager - Centralized token fetching for Auth0 and non-Auth0 modes
 *
 * This module provides a single `getToken()` function that works for both authentication modes:
 * - Auth0 mode: Calls getAccessTokenSilently() on every request (auto-refreshes if needed)
 * - Non-Auth0 mode: Returns cached token from Apollo reactive var
 *
 * The Auth0 token getter is registered by AuthGate when the component mounts.
 */

import { authToken } from "../graphql/cache";
import { getRuntimeEnv } from "./env";

/**
 * Storage for the Auth0 token getter function.
 * This is set by AuthGate when using Auth0 authentication.
 */
let auth0TokenGetter: (() => Promise<string>) | null = null;

/**
 * Register the Auth0 token getter function.
 * Should be called by AuthGate when Auth0 authentication is initialized.
 *
 * @param getter - Async function that returns a fresh Auth0 token
 */
export function setAuth0TokenGetter(getter: () => Promise<string>): void {
  auth0TokenGetter = getter;
}

/**
 * Clear the Auth0 token getter (e.g., on logout).
 */
export function clearAuth0TokenGetter(): void {
  auth0TokenGetter = null;
}

/**
 * Get an authentication token for the current session.
 *
 * Behavior:
 * - Auth0 mode: Calls getAccessTokenSilently() which returns cached token if valid,
 *   or automatically refreshes using refresh token if expired
 * - Non-Auth0 mode: Returns the cached token from Apollo reactive var
 *
 * @returns Promise<string> - The authentication token (empty string if not available)
 */
export async function getToken(): Promise<string> {
  const { REACT_APP_USE_AUTH0 } = getRuntimeEnv();

  if (REACT_APP_USE_AUTH0 && auth0TokenGetter) {
    try {
      const token = await auth0TokenGetter();
      return token || "";
    } catch (error) {
      console.error("[tokenManager] Failed to get Auth0 token:", error);
      // Fall back to cached token if Auth0 fails
      return authToken() || "";
    }
  }

  // Non-Auth0 mode: use cached token
  return authToken() || "";
}
