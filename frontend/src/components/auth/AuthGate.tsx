import React, { useEffect, useState } from "react";
import { useAuth0 } from "@auth0/auth0-react";
import { useReactiveVar } from "@apollo/client";
import { authToken, authStatusVar, userObj } from "../../graphql/cache";
import { toast } from "react-toastify";
import { ModernLoadingDisplay } from "../widgets/ModernLoadingDisplay";
import {
  setAuth0TokenGetter,
  clearAuth0TokenGetter,
} from "../../utils/tokenManager";

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

  // Auth0 hooks
  const {
    isLoading: auth0Loading,
    isAuthenticated,
    user,
    getAccessTokenSilently,
  } = useAuth0();

  // Handle Auth0 authentication
  useEffect(() => {
    if (!useAuth0Flag) {
      // Non-Auth0 mode: immediately mark as initialized
      if (authStatusVar() === "LOADING") {
        authStatusVar("ANONYMOUS");
      }
      setAuthInitialized(true);
      return;
    }

    // Auth0 mode
    if (auth0Loading) {
      console.log("[AuthGate] Auth0 is still loading...");
      return;
    }

    // Auth0 has finished loading
    if (isAuthenticated && user) {
      console.log("[AuthGate] User is authenticated, setting up Auth0...");

      // Register the Auth0 token getter for use throughout the app
      setAuth0TokenGetter(() =>
        getAccessTokenSilently({
          authorizationParams: {
            audience: audience || undefined,
            scope: "openid profile email",
          },
        })
      );

      // Fetch initial token to verify authentication and set user
      getAccessTokenSilently({
        authorizationParams: {
          audience: audience || undefined,
          scope: "openid profile email",
        },
      })
        .then((token) => {
          if (token) {
            console.log("[AuthGate] Initial token obtained successfully");
            // Set token in cache for backward compatibility
            authToken(token);
            userObj(user);
            authStatusVar("AUTHENTICATED");

            setAuthInitialized(true);
          } else {
            console.error("[AuthGate] No token received from Auth0");
            clearAuth0TokenGetter();
            authToken("");
            userObj(null);
            authStatusVar("ANONYMOUS");
            setAuthInitialized(true);
            toast.error("Unable to authenticate: no token received");
          }
        })
        .catch((error) => {
          console.error("[AuthGate] Error getting access token:", error);
          clearAuth0TokenGetter();
          authToken("");
          userObj(null);
          authStatusVar("ANONYMOUS");
          setAuthInitialized(true);
          toast.error("Authentication failed: " + error.message);
        });
    } else {
      // Not authenticated
      console.log("[AuthGate] User is not authenticated");
      clearAuth0TokenGetter();
      authToken("");
      userObj(null);
      authStatusVar("ANONYMOUS");
      setAuthInitialized(true);
    }
  }, [
    useAuth0Flag,
    auth0Loading,
    isAuthenticated,
    user,
    getAccessTokenSilently,
    audience,
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
