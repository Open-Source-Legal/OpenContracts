import React from "react";
import styled from "styled-components";
import { StatBlock, StatGrid } from "@os-legal/ui";
import { useLandingContent } from "../../config/landingContent";

// Wrapper to increase stat sizes to match design reference
const StatsWrapper = styled.div`
  /* Override StatBlock value size for larger display */
  [class*="StatBlock"] > *:first-child,
  [data-testid="stat-value"] {
    font-size: 42px !important;
  }
`;

interface CommunityStats {
  totalUsers: number;
  totalThreads: number;
  totalMessages: number;
  totalAnnotations: number;
  activeUsersThisWeek: number;
  activeUsersThisMonth: number;
}

interface StatsSectionProps {
  stats: CommunityStats | null;
  loading?: boolean;
}

/**
 * Stats Section - matches Storybook design
 *
 * Features:
 * - 2-column grid layout
 * - Large teal numbers (no icons)
 * - Label and sublabel text
 * - Clean, minimal styling
 */

function formatNumber(num: number): string {
  if (num >= 1000000) {
    return (num / 1000000).toFixed(1) + "M";
  }
  if (num >= 1000) {
    return (num / 1000).toFixed(1) + "K";
  }
  return num.toLocaleString();
}

/**
 * Stat configurations come from the active landingContent variant
 * (see `src/config/landingContent`). The key field must match a
 * GraphQL `CommunityStats` field — the JSON `CommunityStatKey` union
 * keeps that contract honest at build time.
 */
export const StatsSection: React.FC<StatsSectionProps> = ({
  stats,
  loading,
}) => {
  const { stats: statConfigs } = useLandingContent();
  return (
    <StatsWrapper>
      <StatGrid columns={4}>
        {statConfigs.map((config) => {
          const value =
            loading || !stats
              ? "—"
              : formatNumber(
                  stats[config.key as keyof CommunityStats] as number
                );

          return (
            <StatBlock
              key={config.key}
              value={value}
              label={config.label}
              sublabel={config.sublabel}
            />
          );
        })}
      </StatGrid>
    </StatsWrapper>
  );
};
