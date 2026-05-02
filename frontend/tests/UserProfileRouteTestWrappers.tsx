import React from "react";
import { UserProfileRoute } from "../src/components/routes/UserProfileRoute";
import {
  openedUser,
  routeLoading,
  routeError,
  type OpenedUserProfile,
} from "../src/graphql/cache";

/**
 * Wrappers that seed the routing reactive vars before rendering
 * UserProfileRoute. Playwright CT mounts run in the browser, so
 * `test.beforeEach` callbacks (which run in node) cannot reach the makeVar
 * instances the component reads. Setting the vars synchronously in render
 * — before the child mounts — gives UserProfileRoute the exact state
 * CentralRouteManager would have set in production.
 */

export const UserProfileRouteLoadingWrapper: React.FC = () => {
  openedUser(null);
  routeLoading(true);
  routeError(null);
  return <UserProfileRoute />;
};

export const UserProfileRouteResetWrapper: React.FC = () => {
  openedUser(null);
  routeLoading(false);
  routeError(null);
  return <UserProfileRoute />;
};

export const UserProfileRouteSeededWrapper: React.FC<{
  user: OpenedUserProfile;
}> = ({ user }) => {
  openedUser(user);
  routeLoading(false);
  routeError(null);
  return <UserProfileRoute />;
};
