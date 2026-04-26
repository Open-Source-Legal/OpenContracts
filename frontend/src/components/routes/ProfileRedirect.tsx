/**
 * ProfileRedirect - Resolves /profile to the current user's canonical
 * /users/:slug URL.
 *
 * This is auth-state-driven (not URL-state-driven), so it lives outside
 * the CentralRouteManager entity-resolution path. It reads backendUserObj
 * and renders a React Router <Navigate> to the canonical profile URL,
 * which then triggers CentralRouteManager Phase 1 user resolution.
 *
 * Anonymous visitors are sent to /login.
 */

import React from "react";
import { Navigate } from "react-router-dom";
import { useReactiveVar } from "@apollo/client";
import {
  backendUserObj,
  authStatusVar,
  authInitCompleteVar,
} from "../../graphql/cache";
import { ModernLoadingDisplay } from "../widgets/ModernLoadingDisplay";

export const ProfileRedirect: React.FC = () => {
  const currentUser = useReactiveVar(backendUserObj);
  const authStatus = useReactiveVar(authStatusVar);
  const authInitComplete = useReactiveVar(authInitCompleteVar);

  // While Auth0 is still resolving the session, backendUserObj is null even
  // for an authenticated visitor. Redirecting before this settles would
  // briefly send an authenticated user to /login. Hold the render until the
  // auth pipeline (token + cache reset) signals it's done.
  if (authStatus === "LOADING" || !authInitComplete) {
    return <ModernLoadingDisplay type="default" message="Resolving profile…" />;
  }

  if (!currentUser?.slug) {
    return <Navigate to="/login" replace />;
  }

  return <Navigate to={`/users/${currentUser.slug}`} replace />;
};

export default ProfileRedirect;
