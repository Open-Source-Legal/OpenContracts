import React from "react";
import {
  PageContainer,
  ContentContainer,
  HeroSection,
  HeroTitle,
  HeroSubtitle,
  StatsContainer,
  SectionHeader,
  SectionTitle,
  EmptyStateWrapper,
} from "../src/components/layout/PageLayout";

/**
 * Renders the full PageLayout primitive set in their canonical arrangement
 * — the same composition used by Documents / Extracts / LabelSets / Annotations
 * — so the test can verify props flow through and capture a documentation
 * screenshot of the shared chrome.
 */
export const PageLayoutShowcase: React.FC = () => {
  return (
    <PageContainer data-testid="page-container">
      <ContentContainer data-testid="content-container">
        <HeroSection data-testid="hero-section">
          <HeroTitle data-testid="hero-title">
            Open <span>Contracts</span>
          </HeroTitle>
          <HeroSubtitle data-testid="hero-subtitle">
            A unified workspace for document analytics.
          </HeroSubtitle>
        </HeroSection>

        <StatsContainer data-testid="stats-container">
          <div>Stat row goes here</div>
        </StatsContainer>

        <SectionHeader data-testid="section-header-default">
          <SectionTitle>Recent</SectionTitle>
          <span>View all</span>
        </SectionHeader>

        <SectionHeader
          $gap={0}
          $wrap={false}
          data-testid="section-header-no-gap"
        >
          <SectionTitle>Featured</SectionTitle>
          <span>View all</span>
        </SectionHeader>

        <EmptyStateWrapper data-testid="empty-state-wrapper">
          <div>Nothing here yet</div>
        </EmptyStateWrapper>
      </ContentContainer>
    </PageContainer>
  );
};

interface PropsHarnessProps {
  $maxWidth?: "narrow" | "wide";
  $compact?: boolean;
  $heroMarginBottom?: number;
  $titleMarginBottom?: number;
}

/**
 * Renders ContentContainer + HeroSection + HeroTitle with prop overrides so
 * tests can assert the resolved CSS reflects the requested transient props.
 */
export const PageLayoutPropsHarness: React.FC<PropsHarnessProps> = ({
  $maxWidth,
  $compact,
  $heroMarginBottom,
  $titleMarginBottom,
}) => {
  return (
    <PageContainer>
      <ContentContainer
        $maxWidth={$maxWidth}
        $compact={$compact}
        data-testid="content-container"
      >
        <HeroSection
          $marginBottom={$heroMarginBottom}
          data-testid="hero-section"
        >
          <HeroTitle
            $marginBottom={$titleMarginBottom}
            data-testid="hero-title"
          >
            Hero
          </HeroTitle>
        </HeroSection>
      </ContentContainer>
    </PageContainer>
  );
};
