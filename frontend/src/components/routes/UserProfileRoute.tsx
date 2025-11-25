/**
 * User Profile Route Component
 *
 * Issue: #611 - Create User Profile Page with badge display and stats
 * Epic: #572 - Social Features Epic
 *
 * Slug-based route component that resolves user profile and renders the UserProfile view.
 * Handles both /profile (current user) and /users/:slug (any user) routes.
 */

import React from "react";
import { useParams, Navigate } from "react-router-dom";
import { useQuery, useReactiveVar } from "@apollo/client";
import { GET_USER, GetUserInput, GetUserOutput } from "../../graphql/queries";
import { backendUserObj } from "../../graphql/cache";
import { ModernLoadingDisplay } from "../widgets/ModernLoadingDisplay";
import { ModernErrorDisplay } from "../widgets/ModernErrorDisplay";
import { UserProfile } from "../../views/UserProfile";

export const UserProfileRoute: React.FC = () => {
  const { slug } = useParams<{ slug: string }>();
  const currentUser = useReactiveVar(backendUserObj);

  // If no slug provided, redirect to current user's profile
  if (!slug) {
    if (!currentUser?.slug) {
      return <Navigate to="/login" replace />;
    }
    return <Navigate to={`/users/${currentUser.slug}`} replace />;
  }

  const { data, loading, error } = useQuery<GetUserOutput, GetUserInput>(
    GET_USER,
    {
      variables: { slug },
      skip: !slug,
    }
  );

  if (loading) {
    return <ModernLoadingDisplay type="default" message="Loading profile..." />;
  }

  if (error) {
    return (
      <ModernErrorDisplay
        type="generic"
        title="User Not Found"
        error={`Could not find user with slug "${slug}"`}
      />
    );
  }

  if (!data?.userBySlug) {
    return (
      <ModernErrorDisplay
        type="generic"
        title="User Not Found"
        error={`User "${slug}" does not exist or their profile is private`}
      />
    );
  }

  const isOwnProfile = currentUser?.id === data.userBySlug.id;

  return <UserProfile user={data.userBySlug} isOwnProfile={isOwnProfile} />;
};
