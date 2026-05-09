import styled from "styled-components";
import {
  OS_LEGAL_COLORS,
  OS_LEGAL_SPACING,
} from "../../assets/configurations/osLegalStyles";

/**
 * Shared primitives for the modern OS-Legal page layout used by the
 * top-level views rendered below the AppShell — Documents, Extracts,
 * LabelSets, Annotations, DiscoveryLanding, ExtractDetail.
 *
 * Layout is intentionally consistent: a scrollable Inter-font shell, a
 * centered main column with a configurable max-width, a Georgia hero,
 * and a stats / section pattern.
 */

/** Outer scroll shell with the standard background + Inter font. */
export const PageContainer = styled.div`
  height: 100%;
  background: ${OS_LEGAL_COLORS.background};
  font-family: "Inter", -apple-system, BlinkMacSystemFont, sans-serif;
  overflow-y: auto;
  overflow-x: hidden;
`;

interface ContentContainerProps {
  /** Max width for the centered content column. Defaults to "narrow" (900px). */
  $maxWidth?: "narrow" | "wide";
  /** Tighter top padding for detail pages. Defaults to false. */
  $compact?: boolean;
}

/**
 * Centered main column. Use $maxWidth="narrow" (900px, list pages) or
 * "wide" (1200px, detail/landing pages with sidebars). Set $compact for the
 * tighter top padding used by detail pages like ExtractDetail.
 */
export const ContentContainer = styled.main<ContentContainerProps>`
  max-width: ${(props) => (props.$maxWidth === "wide" ? "1200px" : "900px")};
  margin: 0 auto;
  padding: ${(props) => (props.$compact ? "32px 24px 80px" : "48px 24px 80px")};

  @media (max-width: 768px) {
    padding: ${(props) =>
      props.$compact ? "24px 16px 60px" : "32px 16px 60px"};
  }
`;

interface HeroSectionProps {
  /** Override the default 48px margin-bottom (Annotations uses 40px). */
  $marginBottom?: number;
}

/** Hero header section — pairs HeroTitle + HeroSubtitle (+ optional content). */
export const HeroSection = styled.section<HeroSectionProps>`
  margin-bottom: ${(props) => props.$marginBottom ?? 48}px;
`;

interface HeroTitleProps {
  /** Override the default 16px margin-bottom (Annotations uses 12px). */
  $marginBottom?: number;
}

/**
 * Georgia-serif page hero. Wrap the accent word in <span> to receive the
 * accent color.
 */
export const HeroTitle = styled.h1<HeroTitleProps>`
  font-family: "Georgia", "Times New Roman", serif;
  font-size: 42px;
  font-weight: 400;
  line-height: 1.2;
  color: ${OS_LEGAL_COLORS.textPrimary};
  margin: 0 0 ${(props) => props.$marginBottom ?? 16}px;

  span {
    color: ${OS_LEGAL_COLORS.accent};
  }

  @media (max-width: 768px) {
    font-size: 32px;
  }
`;

/** Body subtitle paired with HeroTitle. */
export const HeroSubtitle = styled.p`
  font-size: 17px;
  line-height: 1.6;
  color: ${OS_LEGAL_COLORS.textSecondary};
  margin: 0 0 32px;
  max-width: 600px;
`;

/**
 * Wrapper for the @os-legal/ui StatGrid + StatBlock cluster. Bumps the
 * value font-size to 36px (28px on mobile) so list-page stats read more
 * prominently than the library default.
 *
 * NOTE: the [class*="StatBlock"] selector is an intentional coupling to
 * `@os-legal/ui` internals. styled-components hashes the StatBlock's
 * generated class so it stays stable inside any single bundle of
 * `@os-legal/ui`, but if the library ever renames or restructures
 * StatBlock, this override silently stops applying with no compile-time
 * signal. The [data-testid="stat-value"] fallback below is a stable
 * second selector — bump the library version cautiously and re-check
 * the rendered DOM if list-page stats look smaller than expected.
 */
export const StatsContainer = styled.div`
  margin-bottom: 48px;
  padding: 32px 0;

  /* Override stat value size for list-page prominence. */
  [class*="StatBlock"] > *:first-child,
  [data-testid="stat-value"] {
    font-size: 36px !important;
  }

  @media (max-width: 768px) {
    padding: 24px 0;

    [class*="StatBlock"] > *:first-child,
    [data-testid="stat-value"] {
      font-size: 28px !important;
    }
  }
`;

interface SectionHeaderProps {
  /** Override the default 16px horizontal gap between children. Pass 0 to suppress. */
  $gap?: number;
  /**
   * Whether children should wrap to a new line when the row overflows.
   * Defaults to true (matching the list-page pattern in Documents/Extracts/LabelSets).
   * DiscoveryLanding's "Recent Activity" / "Suggested Corpora" rows pass false to
   * preserve the pre-refactor single-line layout.
   */
  $wrap?: boolean;
}

/** Flex row used above lists/grids: [SectionTitle … ActionButtons]. */
export const SectionHeader = styled.div<SectionHeaderProps>`
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
  gap: ${(props) => props.$gap ?? 16}px;
  flex-wrap: ${(props) => (props.$wrap === false ? "nowrap" : "wrap")};
`;

/** Georgia serif section heading rendered in the accent color. */
export const SectionTitle = styled.h2`
  font-family: "Georgia", "Times New Roman", serif;
  font-size: 24px;
  font-weight: 400;
  color: ${OS_LEGAL_COLORS.accent};
  margin: 0;
`;

/** Card wrapper around the @os-legal/ui EmptyState component. */
export const EmptyStateWrapper = styled.div`
  padding: 48px 24px;
  background: ${OS_LEGAL_COLORS.surface};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: ${OS_LEGAL_SPACING.borderRadiusEmptyState};
`;
