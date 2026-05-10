import React from "react";
import {
  DiscoveryContainer,
  DiscoveryHeader,
  DiscoveryTitle,
  DiscoveryFilterBar,
  DiscoverySectionHeader,
  DiscoverySectionIcon,
  DiscoverySectionTitle,
  DiscoverySectionCount,
} from "../src/components/layout/DiscoveryViewLayout";

/**
 * Renders the full DiscoveryViewLayout primitive set in their canonical
 * arrangement — the same composition used by GlobalDiscussions and
 * DiscoverSearchResults — so the test can verify props flow through and
 * capture a documentation screenshot of the shared chrome.
 */
export const DiscoveryViewLayoutShowcase: React.FC = () => {
  return (
    <DiscoveryContainer data-testid="discovery-container">
      <DiscoveryHeader data-testid="discovery-header">
        <DiscoveryTitle data-testid="discovery-title">
          Global Discussions
        </DiscoveryTitle>
      </DiscoveryHeader>

      <DiscoveryFilterBar data-testid="discovery-filter-bar">
        <span>All</span>
        <span>Search</span>
      </DiscoveryFilterBar>

      <DiscoverySectionHeader data-testid="discovery-section-header">
        <DiscoverySectionIcon
          $color="#22c55e"
          data-testid="discovery-section-icon"
        >
          <svg viewBox="0 0 24 24">
            <circle cx="12" cy="12" r="6" fill="currentColor" />
          </svg>
        </DiscoverySectionIcon>
        <DiscoverySectionTitle data-testid="discovery-section-title">
          Recent Threads
        </DiscoverySectionTitle>
        <DiscoverySectionCount data-testid="discovery-section-count">
          12
        </DiscoverySectionCount>
      </DiscoverySectionHeader>
    </DiscoveryContainer>
  );
};

interface PropsHarnessProps {
  $titleMarginBottom?: string;
  $iconColor?: string;
}

/**
 * Renders DiscoveryTitle + DiscoverySectionIcon with prop overrides so
 * tests can assert the resolved CSS reflects the requested transient props.
 */
export const DiscoveryViewLayoutPropsHarness: React.FC<PropsHarnessProps> = ({
  $titleMarginBottom,
  $iconColor,
}) => {
  return (
    <DiscoveryContainer>
      <DiscoveryTitle
        $marginBottom={$titleMarginBottom}
        data-testid="discovery-title"
      >
        Discoveries
      </DiscoveryTitle>
      <DiscoverySectionIcon
        $color={$iconColor ?? "#3b82f6"}
        data-testid="discovery-section-icon"
      >
        <svg viewBox="0 0 24 24">
          <circle cx="12" cy="12" r="6" fill="currentColor" />
        </svg>
      </DiscoverySectionIcon>
    </DiscoveryContainer>
  );
};
