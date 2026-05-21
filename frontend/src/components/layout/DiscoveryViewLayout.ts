import styled from "styled-components";
import {
  CORPUS_COLORS,
  CORPUS_FONTS,
  CORPUS_RADII,
  mediaQuery,
} from "../threads/styles/discussionStyles";

/**
 * Shared primitives for the discussion / cross-content discovery layout
 * used by GlobalDiscussions and DiscoverSearchResults.
 *
 * Naming: the `Discovery` prefix avoids collisions with the modern
 * OS-Legal page primitives in PageLayout.tsx (which use generic names
 * like `PageContainer` / `SectionTitle`). Views import each set as
 * needed.
 */

/** Outer scroll shell with the constrained 1200px (75rem) reading column.
 *  Pass `$fabClearance` on views that render a fixed FAB so trailing
 *  content can scroll clear of it. */
export const DiscoveryContainer = styled.div<{ $fabClearance?: boolean }>`
  max-width: 75rem;
  margin: 0 auto;
  padding: 2.5rem 4rem;
  height: 100%;
  overflow-y: auto;
  overflow-x: hidden;

  @media (max-width: 1400px) {
    padding: 2rem 3rem;
  }

  @media (max-width: 1024px) {
    padding: 1.5rem 2rem;
  }

  ${mediaQuery.mobile} {
    padding: 1rem;
  }

  /* Clearance for a fixed FAB (3rem tall, ≤2rem from the bottom edge).
     Declared after the breakpoint shorthands so it overrides their
     padding-bottom at every width. */
  ${({ $fabClearance }) => $fabClearance && "padding-bottom: 7rem;"}
`;

/** Page header — wraps the title row + filter bar. */
export const DiscoveryHeader = styled.div`
  margin-bottom: 1.5rem;
`;

/** Serif page title. Pass $marginBottom to override the default 0. */
export const DiscoveryTitle = styled.h1<{ $marginBottom?: string }>`
  font-family: ${CORPUS_FONTS.serif};
  font-size: 2rem;
  font-weight: 700;
  color: ${CORPUS_COLORS.slate[900]};
  margin: 0 0 ${(props) => props.$marginBottom ?? "0"} 0;
  letter-spacing: -0.02em;

  ${mediaQuery.mobile} {
    font-size: 1.5rem;
  }
`;

/** Horizontal bar pairing FilterTabs + SearchBox. */
export const DiscoveryFilterBar = styled.div`
  display: flex;
  gap: 0.75rem;
  align-items: center;
  margin-bottom: 1.5rem;
  flex-wrap: wrap;

  ${mediaQuery.mobile} {
    gap: 0.5rem;
  }
`;

/**
 * Section heading row: icon + title + count, with a slate-200 underline.
 * The icon's background color is supplied per-section via $color.
 */
export const DiscoverySectionHeader = styled.div`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.75rem;
  padding-bottom: 0.625rem;
  border-bottom: 1px solid ${CORPUS_COLORS.slate[200]};
`;

/** Colored icon tile rendered inside DiscoverySectionHeader. */
export const DiscoverySectionIcon = styled.div<{ $color: string }>`
  width: 1.625rem;
  height: 1.625rem;
  border-radius: ${CORPUS_RADII.sm};
  background: ${(props) => props.$color};
  display: flex;
  align-items: center;
  justify-content: center;
  color: ${CORPUS_COLORS.white};
  flex-shrink: 0;

  svg {
    width: 0.875rem;
    height: 0.875rem;
  }
`;

/** Serif heading inside DiscoverySectionHeader. */
export const DiscoverySectionTitle = styled.h2`
  font-family: ${CORPUS_FONTS.serif};
  font-size: 1.125rem;
  font-weight: 600;
  color: ${CORPUS_COLORS.slate[800]};
  margin: 0;
`;

/** Right-aligned count caption inside DiscoverySectionHeader. */
export const DiscoverySectionCount = styled.span`
  font-family: ${CORPUS_FONTS.sans};
  font-size: 0.8125rem;
  color: ${CORPUS_COLORS.slate[400]};
  font-weight: 500;
  margin-left: auto;
`;
