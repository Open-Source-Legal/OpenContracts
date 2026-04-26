/**
 * User Profile Route Component
 *
 * Issue: #611 - Create User Profile Page with badge display and stats
 * Epic: #572 - Social Features Epic
 *
 * Renders the user profile resolved by CentralRouteManager from the
 * /users/:slug route. URL parsing and entity fetching live in
 * CentralRouteManager; this component reads reactive vars and renders.
 *
 * The /profile redirect (current user) is handled by ProfileRedirect.
 */

import React from "react";
import { useReactiveVar } from "@apollo/client";
import {
  backendUserObj,
  openedUser,
  routeLoading,
  routeError,
} from "../../graphql/cache";
import { ModernLoadingDisplay } from "../widgets/ModernLoadingDisplay";
import { ModernErrorDisplay } from "../widgets/ModernErrorDisplay";
import { UserProfile } from "../../views/UserProfile";

export const UserProfileRoute: React.FC = () => {
  const user = useReactiveVar(openedUser);
  const loading = useReactiveVar(routeLoading);
  const error = useReactiveVar(routeError);
  const currentUser = useReactiveVar(backendUserObj);

  if (loading && !user) {
    return <ModernLoadingDisplay type="default" message="Loading profile..." />;
  }

  if (error || !user) {
    return (
      <ModernErrorDisplay
        type="generic"
        title="User Not Found"
        error={
          error?.message || "User does not exist or their profile is private"
        }
      />
    );
  }

  const isOwnProfile = currentUser?.id === user.id;

  return <UserProfile user={user} isOwnProfile={isOwnProfile} />;
};
