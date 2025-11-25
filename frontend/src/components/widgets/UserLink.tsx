/**
 * User Link Component
 *
 * Issue: #611 - Create User Profile Page with badge display and stats
 * Epic: #572 - Social Features Epic
 *
 * Reusable component for linking usernames to user profiles.
 * Can be used throughout the app in threads, messages, annotations, etc.
 */

import React from "react";
import { Link } from "react-router-dom";
import styled from "styled-components";
import { color } from "../../theme/colors";

const StyledLink = styled(Link)`
  color: ${color.B6};
  font-weight: 600;
  text-decoration: none;
  transition: color 0.2s;

  &:hover {
    color: ${color.B7};
    text-decoration: underline;
  }
`;

const StyledSpan = styled.span`
  color: ${color.N7};
  font-weight: 600;
`;

export interface UserLinkProps {
  username: string;
  slug?: string;
  /** If true, don't render as a link (for anonymous users or disabled state) */
  disableLink?: boolean;
  /** Additional CSS class name */
  className?: string;
}

export const UserLink: React.FC<UserLinkProps> = ({
  username,
  slug,
  disableLink,
  className,
}) => {
  if (disableLink || !slug) {
    return <StyledSpan className={className}>{username}</StyledSpan>;
  }

  return (
    <StyledLink to={`/users/${slug}`} className={className}>
      {username}
    </StyledLink>
  );
};
