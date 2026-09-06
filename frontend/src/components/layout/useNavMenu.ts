import { useLocation, useNavigate } from "react-router-dom";
import { useAuth0 } from "@auth0/auth0-react";
import { useReactiveVar } from "@apollo/client";
import {
  authToken,
  authStatusVar,
  userObj,
  backendUserObj,
  showExportModal,
} from "../../graphql/cache";
import { header_menu_items } from "../../assets/configurations/menus";
import { useEnv } from "../hooks/UseEnv";
import { useCacheManager } from "../../hooks/useCacheManager";
import { clearLocalAuthSession } from "../../utils/localAuthSession";

/**
 * Shared navigation menu logic for both desktop and mobile nav components.
 * Handles auth resolution, menu filtering, active state, and logout.
 */
export const useNavMenu = () => {
  const { REACT_APP_USE_AUTH0, REACT_APP_AUDIENCE } = useEnv();
  const {
    loginWithRedirect,
    loginWithPopup,
    logout,
    user: auth0_user,
    isLoading: auth0Loading,
  } = useAuth0();
  const cache_user = useReactiveVar(userObj);
  const backendUser = useReactiveVar(backendUserObj);
  const authStatus = useReactiveVar(authStatusVar);
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { resetOnAuthChange } = useCacheManager();

  // Local login initially supplies ``cache_user`` directly. After a page
  // refresh only the persisted JWT is restored; GET_ME then repopulates
  // ``backendUser``. Use that canonical backend identity so the navigation
  // does not incorrectly render "Login" for a restored session.
  const user = REACT_APP_USE_AUTH0
    ? auth0_user
    : backendUser || cache_user;
  // ``useAuth0()`` must be called unconditionally (hooks rules), but without a
  // mounted Auth0Provider it returns the default context whose ``isLoading`` is
  // permanently true. Consumers gate the whole auth surface on this flag
  // (``hideAuth``, ``hideUserMenu``, and the anonymous login button), so
  // passing it through unguarded hid the entire user menu AND the login button
  // in every ``REACT_APP_USE_AUTH0=false`` deployment. Same guard App.tsx
  // applies for the same reason.
  const isLoading = REACT_APP_USE_AUTH0
    ? auth0Loading
    : authStatus === "AUTHENTICATED" && !user;
  const show_export_modal = useReactiveVar(showExportModal);

  // Filter menu items based on authentication
  const public_header_items = header_menu_items.filter(
    (item) => !item.protected
  );
  const private_header_items = header_menu_items.filter(
    (item) => item.protected
  );

  /**
   * Determines whether a menu item should be shown as active based on the current
   * location pathname. We consider an item active when the pathname is exactly
   * the route OR it is a sub-route (i.e. pathname starts with `${route}/`).
   */
  const isActive = (route: string) => {
    if (route === "/") {
      // Discover/Home is only active on exact "/" path
      return pathname === "/";
    }
    return pathname === route || pathname.startsWith(`${route}/`);
  };

  /**
   * Logs out the user. Uses Auth0 logout if Auth0 is enabled, otherwise
   * clears local auth state and redirects to home.
   * CentralRouteManager will automatically clear entity state when navigating to "/".
   *
   * IMPORTANT: Clears the Apollo cache on logout to ensure:
   * 1. Security: Previous user's data is not accessible
   * 2. Data freshness: Next login starts with clean cache
   *
   * Order of operations: Clear auth state FIRST (prevents new authenticated
   * queries), then fire-and-forget cache clear (removes cached data).
   * We don't await cache clear since logout shouldn't block on it.
   */
  const requestLogout = () => {
    // IMPORTANT: Clear auth state BEFORE calling resetOnAuthChange().
    // The useRefetchOnAuthChange hook (App.tsx) checks authToken() inside its
    // onClearStore callback — an empty token signals "logout" and skips the
    // refetch. If this ordering is reversed, the hook would re-issue all
    // active queries with the still-valid token before it's cleared.
    // See: useRefetchOnAuthChange.ts lines 31-36.
    clearLocalAuthSession();
    authToken("");
    userObj(null);
    authStatusVar("ANONYMOUS");

    // Fire-and-forget cache clear (don't block logout on this).
    resetOnAuthChange({ reason: "user_logout", refetchActive: false }).catch(
      (error) =>
        console.warn("[useNavMenu] Cache reset failed on logout:", {
          error: error instanceof Error ? error.message : error,
          userId: REACT_APP_USE_AUTH0
            ? auth0_user?.sub
            : backendUser?.id || cache_user?.id,
          timestamp: new Date().toISOString(),
        })
    );

    if (REACT_APP_USE_AUTH0) {
      logout({
        logoutParams: {
          returnTo: window.location.origin,
        },
      });
    } else {
      navigate("/");
    }
  };

  /**
   * Initiates login flow. Tries popup first, falls back to redirect if popup fails.
   */
  const doLogin = async () => {
    try {
      await loginWithPopup({
        authorizationParams: {
          audience: REACT_APP_AUDIENCE || undefined,
          scope: "openid profile email",
          redirect_uri: window.location.origin,
        },
      });
    } catch (error) {
      await loginWithRedirect({
        appState: {
          returnTo: window.location.pathname + window.location.search,
        },
        authorizationParams: {
          audience: REACT_APP_AUDIENCE || undefined,
          scope: "openid profile email",
        },
      });
    }
  };

  // isSuperuser is sourced from backendUserObj (populated by GET_ME query),
  // not from Auth0 user or cache_user which don't carry this field.
  const isSuperuser = backendUser?.isSuperuser === true;

  return {
    // Auth state
    user,
    isSuperuser,
    isLoading,
    REACT_APP_USE_AUTH0,
    REACT_APP_AUDIENCE,

    // Menu items
    public_header_items,
    private_header_items,

    // UI state
    show_export_modal,
    pathname,

    // Functions
    isActive,
    requestLogout,
    doLogin,
    loginWithPopup,
    loginWithRedirect,

    // Navigation
    navigate,
  };
};
