import React, { useState, useCallback, useEffect, useRef } from "react";
import styled from "styled-components";
import { OS_LEGAL_COLORS } from "../assets/configurations/osLegalStyles";
import {
  PageContainer,
  ContentContainer,
  SectionHeader,
  SectionTitle,
} from "../components/layout/PageLayout";
import { gql, useQuery, useReactiveVar } from "@apollo/client";
import { RefreshCw, X, AlertCircle } from "lucide-react";
import { userObj } from "../graphql/cache";
import {
  // New components using OS-Legal-Style library
  NewHeroSection,
  StatsSection,
  FeaturedCollections,
  ActivitySection,
  GetStarted,
  CompactLeaderboard,
  // Legacy components still in use
  CallToAction,
} from "../components/landing";
import {
  GET_DISCOVERY_DATA,
  GetDiscoveryDataOutput,
} from "../graphql/landing-queries";

// Local storage key for anonymous user dismissal
const GETTING_STARTED_DISMISSED_KEY = "oc_getting_started_dismissed";

// Query to get current user preferences
const GET_USER_PREFERENCES = gql`
  query GetUserPreferences {
    me {
      id
      dismissedGettingStarted
    }
  }
`;

interface UserPreferencesData {
  me: {
    id: string;
    dismissedGettingStarted: boolean;
  } | null;
}

/**
 * Discover Page - Clean, minimal design following Storybook reference
 *
 * Layout:
 * - Centered content container (max-width: 900px)
 * - Clean white/light gray background
 * - Minimal hero with serif typography
 * - 2-column stats grid
 * - Featured collections with section header
 * - Activity feed
 */

const SectionLink = styled.a`
  font-size: 14px;
  font-weight: 500;
  color: ${OS_LEGAL_COLORS.textSecondary};
  text-decoration: none;
  display: flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;

  &:hover {
    color: ${OS_LEGAL_COLORS.accent};
  }

  svg {
    width: 16px;
    height: 16px;
  }
`;

const Section = styled.section<{ $marginBottom?: number }>`
  margin-bottom: ${(props) => props.$marginBottom || 56}px;
`;

const ErrorBanner = styled.div`
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 1rem;
  padding: 1rem 2rem;
  background: linear-gradient(
    135deg,
    ${OS_LEGAL_COLORS.dangerSurfaceHover} 0%,
    ${OS_LEGAL_COLORS.dangerSurface} 100%
  );
  border-bottom: 1px solid ${OS_LEGAL_COLORS.dangerBorder};
  font-size: 0.9375rem;

  @media (max-width: 640px) {
    flex-wrap: wrap;
    padding: 1rem;
    gap: 0.75rem;
  }
`;

const ErrorContent = styled.div`
  display: flex;
  align-items: center;
  gap: 0.75rem;
  color: ${OS_LEGAL_COLORS.dangerText};

  svg {
    flex-shrink: 0;
  }
`;

const ErrorActions = styled.div`
  display: flex;
  align-items: center;
  gap: 0.5rem;
`;

const ErrorButton = styled.button<{ $variant?: "primary" | "secondary" }>`
  display: flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.5rem 0.875rem;
  border-radius: 8px;
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;

  ${(props) =>
    props.$variant === "primary"
      ? `
    background: ${OS_LEGAL_COLORS.danger};
    color: white;
    border: none;

    &:hover {
      background: ${OS_LEGAL_COLORS.dangerHover};
    }

    &:disabled {
      opacity: 0.7;
      cursor: not-allowed;
    }
  `
      : `
    background: transparent;
    color: ${OS_LEGAL_COLORS.dangerHover};
    border: 1px solid ${OS_LEGAL_COLORS.dangerBorder};

    &:hover {
      background: ${OS_LEGAL_COLORS.dangerSurfaceHover};
    }
  `}

  svg {
    width: 16px;
    height: 16px;
  }

  @keyframes spin {
    from {
      transform: rotate(0deg);
    }
    to {
      transform: rotate(360deg);
    }
  }

  &.loading svg {
    animation: spin 1s linear infinite;
  }
`;

const ChevronIcon = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
    <path d="M6.22 4.22a.75.75 0 011.06 0l3.25 3.25a.75.75 0 010 1.06l-3.25 3.25a.75.75 0 01-1.06-1.06L8.94 8 6.22 5.28a.75.75 0 010-1.06z" />
  </svg>
);

interface DiscoveryLandingProps {
  /** Override auth state for testing */
  isAuthenticatedOverride?: boolean;
}

export const DiscoveryLanding: React.FC<DiscoveryLandingProps> = ({
  isAuthenticatedOverride,
}) => {
  const currentUser = useReactiveVar(userObj);
  // Use userObj for auth check - consistent with NavMenu pattern
  const isAuthenticated =
    isAuthenticatedOverride !== undefined
      ? isAuthenticatedOverride
      : Boolean(currentUser);

  // State for error banner dismiss
  const [errorDismissed, setErrorDismissed] = useState(false);
  const [isRetrying, setIsRetrying] = useState(false);

  // State for category filtering
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);

  // State for Getting Started dismissal (local state for anonymous users)
  const [localDismissed, setLocalDismissed] = useState(() => {
    // Check localStorage for anonymous users
    if (typeof window !== "undefined") {
      return localStorage.getItem(GETTING_STARTED_DISMISSED_KEY) === "true";
    }
    return false;
  });

  // Query user preferences if authenticated
  const { data: userPrefsData } = useQuery<UserPreferencesData>(
    GET_USER_PREFERENCES,
    {
      skip: !isAuthenticated,
      fetchPolicy: "cache-and-network",
    }
  );

  // Determine if Getting Started is dismissed
  const isGettingStartedDismissed = isAuthenticated
    ? userPrefsData?.me?.dismissedGettingStarted || localDismissed
    : localDismissed;

  // Handle Getting Started dismiss
  const handleDismissGettingStarted = useCallback(() => {
    setLocalDismissed(true);
    // For anonymous users, store in localStorage
    if (!isAuthenticated && typeof window !== "undefined") {
      localStorage.setItem(GETTING_STARTED_DISMISSED_KEY, "true");
    }
  }, [isAuthenticated]);

  // Fetch all discovery data in a single query
  const { data, loading, error, refetch } = useQuery<GetDiscoveryDataOutput>(
    GET_DISCOVERY_DATA,
    {
      variables: {
        corpusLimit: 6,
        discussionLimit: 5,
        leaderboardLimit: 6,
        conversationType: "THREAD" as const,
      },
      // Refresh data periodically for fresh content
      pollInterval: 5 * 60 * 1000, // 5 minutes
      // Use cache first for faster initial load
      fetchPolicy: "cache-and-network",
    }
  );

  // Track if this is the initial mount to avoid refetching on first render
  const isInitialMount = useRef(true);

  // Refetch discovery data when auth state changes (user logs in/out)
  // This ensures the landing page shows updated counts and content
  // based on the user's permissions after authentication
  useEffect(() => {
    if (isInitialMount.current) {
      isInitialMount.current = false;
      return;
    }
    // Auth state changed (login/logout) - refetch to get updated data
    refetch();
  }, [currentUser, refetch]);

  // Handle retry with loading state
  const handleRetry = useCallback(async () => {
    setIsRetrying(true);
    setErrorDismissed(false);
    try {
      await refetch();
    } finally {
      setIsRetrying(false);
    }
  }, [refetch]);

  // Reset dismissed state when error changes (new error appears)
  const showError = error && !errorDismissed;

  return (
    <PageContainer>
      {/* Error Banner - Only show if there's an error and not dismissed */}
      {showError && (
        <ErrorBanner>
          <ErrorContent>
            <AlertCircle size={20} />
            <span>Unable to load some content. Please try again.</span>
          </ErrorContent>
          <ErrorActions>
            <ErrorButton
              $variant="primary"
              onClick={handleRetry}
              disabled={isRetrying}
              className={isRetrying ? "loading" : ""}
            >
              <RefreshCw size={16} />
              {isRetrying ? "Retrying..." : "Retry"}
            </ErrorButton>
            <ErrorButton
              $variant="secondary"
              onClick={() => setErrorDismissed(true)}
            >
              <X size={16} />
              Dismiss
            </ErrorButton>
          </ErrorActions>
        </ErrorBanner>
      )}

      <ContentContainer>
        {/* Hero Section - Minimal design with search and category tabs */}
        <NewHeroSection
          selectedCategory={selectedCategory}
          onCategoryChange={setSelectedCategory}
        />

        {/* Stats Section - 2-column grid, no icons */}
        <Section $marginBottom={56}>
          <StatsSection
            stats={data?.communityStats || null}
            loading={loading}
          />
        </Section>

        {/* Get Started - Prominent placement for new users */}
        <Section $marginBottom={56}>
          <GetStarted
            isAuthenticated={isAuthenticated}
            isDismissed={isGettingStartedDismissed}
            onDismiss={handleDismissGettingStarted}
          />
        </Section>

        {/* Featured Collections with Section Header */}
        <Section $marginBottom={56}>
          {/* $gap=0 / $wrap=false preserves the pre-refactor single-line layout. */}
          <SectionHeader $gap={0} $wrap={false}>
            <SectionTitle>Featured Collections</SectionTitle>
            <SectionLink href="/corpuses">
              View all
              <ChevronIcon />
            </SectionLink>
          </SectionHeader>
          <FeaturedCollections
            corpuses={data?.corpuses?.edges || null}
            loading={loading}
            selectedCategory={selectedCategory}
          />
        </Section>

        {/* Recent Activity with Section Header */}
        <Section $marginBottom={56}>
          <SectionHeader>
            <SectionTitle>Recent Activity</SectionTitle>
          </SectionHeader>
          <ActivitySection
            discussions={data?.conversations?.edges || null}
            loading={loading}
            totalCount={data?.conversations?.totalCount}
          />
        </Section>

        {/* Top Contributors - Compact leaderboard using OS-Legal-Style */}
        <Section $marginBottom={56}>
          <SectionHeader>
            <SectionTitle>Top Contributors</SectionTitle>
          </SectionHeader>
          <CompactLeaderboard
            contributors={data?.globalLeaderboard || null}
            loading={loading}
          />
        </Section>

        {/* Call to Action - Only for anonymous users */}
        <CallToAction isAuthenticated={isAuthenticated} />
      </ContentContainer>
    </PageContainer>
  );
};

export default DiscoveryLanding;
