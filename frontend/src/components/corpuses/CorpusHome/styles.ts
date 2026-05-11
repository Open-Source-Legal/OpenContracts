/**
 * Shared styled components for CorpusHome views
 * Supports both landing (centered) and details (two-column/tabbed) layouts
 */

import styled from "styled-components";
import { motion } from "framer-motion";
import {
  CORPUS_COLORS,
  CORPUS_FONTS,
  CORPUS_RADII,
  CORPUS_SHADOWS,
  CORPUS_TRANSITIONS,
  mediaQuery,
} from "../styles/corpusDesignTokens";
import { OS_LEGAL_COLORS } from "../../../assets/configurations/osLegalStyles";

// ============================================================================
// SHARED CONTAINERS
// ============================================================================

/** Base container shared by both views */
export const BaseContainer = styled.div`
  display: flex;
  flex-direction: column;
  flex: 1;
  background: ${OS_LEGAL_COLORS.surfaceHover};
  overflow: hidden;
  position: relative;
  height: 100%;
  max-height: 100%;
  min-height: 0;
`;

// ============================================================================
// LANDING VIEW STYLES
// ============================================================================

/** Landing page container - centered, scrollable content */
export const LandingContainer = styled(BaseContainer)`
  align-items: center;
  overflow-y: auto;
  overflow-x: hidden;
  min-height: 100%;

  &::-webkit-scrollbar {
    width: 6px;
  }

  &::-webkit-scrollbar-track {
    background: transparent;
  }

  &::-webkit-scrollbar-thumb {
    background: ${CORPUS_COLORS.slate[200]};
    border-radius: 3px;

    &:hover {
      background: ${CORPUS_COLORS.slate[300]};
    }
  }

  ${mediaQuery.mobile} {
    scrollbar-width: none;

    &::-webkit-scrollbar {
      display: none;
    }
  }
`;

/** Centered content wrapper for landing view. */
export const LandingContent = styled.div`
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 100%;
  max-width: 800px;
  padding: 2rem 1.5rem;
  box-sizing: border-box;

  ${mediaQuery.tablet} {
    padding: 1.25rem 1rem 2.5rem;
  }

  ${mediaQuery.mobile} {
    padding: 1rem 1.5rem 2.5rem;
  }
`;

/** Hero section for landing view - centered header content */
export const LandingHero = styled.div`
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: 1rem;
  padding: 2rem 1rem;
  width: 100%;
  box-sizing: border-box;

  ${mediaQuery.tablet} {
    padding: 1.25rem 0.75rem;
    gap: 0.75rem;
  }

  ${mediaQuery.mobile} {
    padding: 0.75rem 0.75rem;
    gap: 0.5rem;
  }
`;

/** Centered breadcrumbs for landing view */
export const CenteredBreadcrumbs = styled.nav`
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  font-size: 0.875rem;
  color: ${CORPUS_COLORS.slate[500]};

  a {
    color: ${CORPUS_COLORS.slate[500]};
    text-decoration: none;
    transition: color ${CORPUS_TRANSITIONS.fast};

    &:hover {
      color: ${CORPUS_COLORS.teal[700]};
    }
  }

  svg {
    width: 14px;
    height: 14px;
    color: ${CORPUS_COLORS.slate[300]};
  }

  .current {
    color: ${CORPUS_COLORS.slate[700]};
    font-weight: 500;
  }

  ${mediaQuery.mobile} {
    display: none;
  }
`;

/** Mobile-only return control for corpus landing pages.
 *  The desktop breadcrumb remains the richer orientation affordance; this
 *  compact row gives narrow screens an explicit way out without changing the
 *  centered hero/title layout. */
export const MobileReturnButton = styled.button`
  display: none;
  align-items: center;
  gap: 0.25rem;
  min-height: 32px;
  padding: 0.25rem 0;
  background: transparent;
  border: none;
  color: ${CORPUS_COLORS.slate[500]};
  font-size: 0.8125rem;
  font-weight: 500;
  cursor: pointer;
  transition: color ${CORPUS_TRANSITIONS.fast};

  svg {
    width: 14px;
    height: 14px;
    transition: transform ${CORPUS_TRANSITIONS.fast};
  }

  &:hover {
    color: ${CORPUS_COLORS.teal[700]};

    svg {
      transform: translateX(-2px);
    }
  }

  &:focus-visible {
    outline: 2px solid ${CORPUS_COLORS.teal[500]};
    outline-offset: 4px;
  }

  ${mediaQuery.mobile} {
    display: inline-flex;
  }
`;

/** Corpus badge - teal background, uppercase */
export const CorpusBadge = styled.span`
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.375rem 0.875rem;
  border-radius: ${CORPUS_RADII.full};
  background: ${CORPUS_COLORS.teal[700]};
  color: ${CORPUS_COLORS.white};
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;

  ${mediaQuery.mobile} {
    display: none;
  }
`;

/** Row wrapper that pairs the mobile hamburger with the title.
 *  On desktop the hamburger is hidden so the title centers alone. */
export const TitleRow = styled.div`
  display: flex;
  align-items: center;
  gap: 0.5rem;
`;

/** Large serif title for landing view */
export const LandingTitle = styled.h1`
  margin: 0;
  font-family: ${CORPUS_FONTS.serif};
  font-size: 2.75rem;
  font-weight: 400;
  color: ${CORPUS_COLORS.slate[800]};
  letter-spacing: -0.02em;
  line-height: 1.15;
  text-align: center;

  ${mediaQuery.tablet} {
    font-size: 1.875rem;
  }

  ${mediaQuery.mobile} {
    font-size: 1.5rem;
  }
`;

/** Description subtitle under the title - left-aligned body copy within
 *  the centered hero container, matching the discovery page pattern of
 *  centered headings with left-aligned prose. Clamped to 3 lines; the
 *  native title attribute provides a tooltip for the full text. */
export const LandingDescription = styled.p`
  margin: 0;
  margin-top: 1rem;
  font-family: ${CORPUS_FONTS.sans};
  font-size: 1.125rem;
  font-weight: 400;
  color: ${CORPUS_COLORS.slate[500]};
  line-height: 1.65;
  text-align: left;
  max-width: 600px;
  width: 100%;
  display: -webkit-box;
  -webkit-line-clamp: 4;
  -webkit-box-orient: vertical;
  overflow: hidden;
  cursor: default;

  ${mediaQuery.tablet} {
    font-size: 1rem;
    margin-top: 0.75rem;
  }
`;

/** Hero image avatar — circular crop with soft-vignette fade at the edges.
 *  The container's border-radius clips to a circle; the radial-gradient mask
 *  on the img adds an intentional feathered edge so the photo fades rather
 *  than ending with a hard pixel boundary. */
export const HeroImageBand = styled.div`
  width: 200px;
  height: 200px;
  border-radius: 50%;
  overflow: hidden;
  margin-top: 0.5rem;
  flex-shrink: 0;

  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
    /* Soft vignette — feathers the photo edges inside the circular crop */
    mask-image: radial-gradient(circle, black 55%, transparent 75%);
    -webkit-mask-image: radial-gradient(circle, black 55%, transparent 75%);
  }

  ${mediaQuery.tablet} {
    width: 176px;
    height: 176px;
  }

  ${mediaQuery.mobile} {
    width: 160px;
    height: 160px;
  }
`;

/** No description placeholder with action — left-aligned to match
 *  the LandingDescription styling. */
export const NoDescriptionContainer = styled.div`
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.5rem;
  margin-top: 1rem;
  width: 100%;
  max-width: 600px;
`;

export const NoDescriptionText = styled.span`
  font-size: 0.9375rem;
  color: ${CORPUS_COLORS.slate[400]};
  font-style: italic;
`;

export const AddDescriptionLink = styled.button`
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0;
  background: none;
  border: none;
  color: ${CORPUS_COLORS.teal[700]};
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  transition: all ${CORPUS_TRANSITIONS.fast};

  &:hover {
    color: ${CORPUS_COLORS.teal[600]};
    text-decoration: underline;
  }

  &:focus-visible {
    outline: 2px solid ${CORPUS_COLORS.teal[500]};
    outline-offset: 2px;
  }

  svg {
    width: 14px;
    height: 14px;
  }
`;

/** Metadata row — positioned above the title as contextual orientation.
 *  Lightweight, muted, gives the reader context before the content. */
export const CenteredMetadataRow = styled.div`
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 1rem;
  flex-wrap: wrap;

  ${mediaQuery.tablet} {
    gap: 0.75rem;
  }

  ${mediaQuery.mobile} {
    .hide-mobile {
      display: none;
    }
  }
`;

/** Metadata item with icon */
export const MetadataItem = styled.div`
  display: flex;
  align-items: center;
  gap: 0.375rem;
  font-size: 0.8125rem;
  color: ${CORPUS_COLORS.slate[500]};

  svg {
    width: 14px;
    height: 14px;
    color: ${CORPUS_COLORS.slate[400]};
  }

  ${mediaQuery.tablet} {
    font-size: 0.75rem;

    svg {
      width: 12px;
      height: 12px;
    }
  }
`;

/** Metadata separator */
export const MetadataSeparator = styled.div`
  width: 1px;
  height: 16px;
  background: ${CORPUS_COLORS.slate[200]};

  ${mediaQuery.tablet} {
    height: 12px;
  }
`;

/** Access badge (Public/Private) */
export const AccessBadge = styled.div<{ $isPublic?: boolean }>`
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.25rem 0.625rem;
  border-radius: ${CORPUS_RADII.sm};
  font-size: 0.75rem;
  font-weight: 500;
  background: ${(props) =>
    props.$isPublic ? CORPUS_COLORS.teal[50] : "#fef3c7"};
  color: ${(props) => (props.$isPublic ? CORPUS_COLORS.teal[700] : "#92400e")};

  svg {
    width: 12px;
    height: 12px;
  }
`;

/** Pill toggle container — sits inline in the metadata row */
export const PillToggle = styled.button`
  display: inline-flex;
  align-items: center;
  position: relative;
  padding: 2px;
  border-radius: ${CORPUS_RADII.full};
  border: 1px solid ${CORPUS_COLORS.slate[200]};
  background: ${CORPUS_COLORS.slate[100]};
  cursor: pointer;
  transition: border-color ${CORPUS_TRANSITIONS.fast};

  &:hover {
    border-color: ${CORPUS_COLORS.teal[300]};
  }

  &:focus-visible {
    outline: 2px solid ${CORPUS_COLORS.teal[500]};
    outline-offset: 2px;
  }
`;

/** Individual label inside the pill */
export const PillToggleLabel = styled.span<{ $active: boolean }>`
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.25rem 0.625rem;
  border-radius: ${CORPUS_RADII.full};
  font-size: 0.6875rem;
  font-weight: 600;
  letter-spacing: 0.02em;
  white-space: nowrap;
  z-index: 1;
  transition: color ${CORPUS_TRANSITIONS.fast},
    background ${CORPUS_TRANSITIONS.fast};
  color: ${(props) =>
    props.$active ? CORPUS_COLORS.white : CORPUS_COLORS.slate[500]};
  background: ${(props) =>
    props.$active ? CORPUS_COLORS.teal[700] : "transparent"};

  svg {
    width: 12px;
    height: 12px;
  }

  ${mediaQuery.tablet} {
    font-size: 0.625rem;
    padding: 0.1875rem 0.5rem;

    svg {
      width: 10px;
      height: 10px;
    }
  }
`;

/** Chat section wrapper for landing view */
export const ChatSection = styled.div`
  width: 100%;
  max-width: 600px;
  margin-top: 1.5rem;

  ${mediaQuery.tablet} {
    margin-top: 1rem;
  }
`;

/** About card wrapper for landing view - simpler styling */
export const LandingAboutCard = styled(motion.div)`
  background: ${CORPUS_COLORS.white};
  border-radius: ${CORPUS_RADII.lg};
  box-shadow: ${CORPUS_SHADOWS.card};
  border: 1px solid ${CORPUS_COLORS.slate[200]};
  width: 100%;
  margin-top: 2rem;
  overflow: hidden;

  ${mediaQuery.tablet} {
    margin-top: 1.5rem;
  }
`;

/** View Details — subtle text link, not a prominent button.
 *  Content should be king; navigation chrome stays quiet. */
export const ViewDetailsButton = styled.button`
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0;
  margin-top: 0.5rem;
  background: none;
  border: none;
  color: ${CORPUS_COLORS.slate[400]};
  font-size: 0.8125rem;
  font-weight: 500;
  cursor: pointer;
  transition: color ${CORPUS_TRANSITIONS.fast};

  svg {
    width: 14px;
    height: 14px;
    transition: transform ${CORPUS_TRANSITIONS.fast};
  }

  &:hover {
    color: ${CORPUS_COLORS.teal[700]};

    svg {
      transform: translateX(3px);
    }
  }

  &:focus-visible {
    outline: 2px solid ${CORPUS_COLORS.teal[500]};
    outline-offset: 4px;
  }

  ${mediaQuery.tablet} {
    font-size: 0.75rem;
  }
`;

// ============================================================================
// DETAILS VIEW STYLES - Minimalist Typography-First Design
// ============================================================================

/** Details view container - subtle background with padding for floating page effect */
export const DetailsContainer = styled(BaseContainer)`
  background: ${CORPUS_COLORS.slate[100]};
  padding: 1.5rem;

  ${mediaQuery.tablet} {
    padding: 0;
    background: ${CORPUS_COLORS.white};
  }
`;

/** Unified page wrapper - contains header + content, max-width constrained */
export const DetailsPage = styled.div`
  display: flex;
  flex-direction: column;
  width: 100%;
  max-width: 1200px;
  height: 100%;
  min-height: 0; /* Allow flex shrinking */
  margin: 0 auto;
  background: ${CORPUS_COLORS.white};
  border-radius: ${CORPUS_RADII.lg};
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05),
    0 0 0 1px ${CORPUS_COLORS.slate[200]};
  overflow: hidden; /* Contain children */

  ${mediaQuery.tablet} {
    max-width: 100%;
    border-radius: 0;
    box-shadow: none;
  }
`;

/** Header section for details view */
export const DetailsHeader = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  padding: 2rem 2.5rem 1.5rem;
  border-bottom: 1px solid ${CORPUS_COLORS.slate[200]};
  flex-shrink: 0;

  ${mediaQuery.tablet} {
    padding: 1rem 1rem 0.75rem;
  }
`;

/** Back button - minimal, text-like */
export const BackButton = styled(motion.button)`
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0;
  margin-bottom: 1rem;
  background: transparent;
  border: none;
  color: ${CORPUS_COLORS.slate[400]};
  font-size: 0.8125rem;
  font-weight: 500;
  letter-spacing: 0.02em;
  text-transform: uppercase;
  cursor: pointer;
  transition: color ${CORPUS_TRANSITIONS.fast};
  align-self: flex-start;

  svg {
    width: 14px;
    height: 14px;
    transition: transform ${CORPUS_TRANSITIONS.fast};
  }

  &:hover {
    color: ${CORPUS_COLORS.teal[700]};

    svg {
      transform: translateX(-3px);
    }
  }

  &:focus-visible {
    outline: 2px solid ${CORPUS_COLORS.teal[500]};
    outline-offset: 4px;
  }

  ${mediaQuery.mobile} {
    margin-bottom: 0.25rem;
  }
`;

/** Title row for details header */
export const DetailsTitleRow = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
`;

/** Title section for details header */
export const DetailsTitleSection = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
`;

/** Title for details view - bold typography */
export const DetailsTitle = styled.h1`
  margin: 0;
  font-family: ${CORPUS_FONTS.serif};
  font-size: 2.25rem;
  font-weight: 400;
  color: ${CORPUS_COLORS.slate[900]};
  letter-spacing: -0.025em;
  line-height: 1.2;

  ${mediaQuery.tablet} {
    font-size: 1.75rem;
  }

  ${mediaQuery.mobile} {
    font-size: 1.5rem;
  }
`;

/** Main content area - fills remaining space.
 *  Row direction on desktop (for TwoColumnLayout),
 *  column direction on tablet/mobile (for MobileTabContainer). */
export const DetailsMainContent = styled.div`
  flex: 1;
  overflow: hidden;
  display: flex;
  min-height: 0;

  ${mediaQuery.tablet} {
    flex-direction: column;
  }
`;

/** Two-column layout - Documents sidebar + About main content */
export const TwoColumnLayout = styled.div`
  display: flex;
  width: 100%;
  height: 100%;
  min-height: 0; /* Allow flex shrinking */

  ${mediaQuery.tablet} {
    display: none;
  }
`;

/** Documents sidebar - percentage-based with bounds */
export const DocumentsSidebar = styled.div`
  width: 40%;
  min-width: 320px;
  max-width: 480px;
  border-right: 1px solid ${CORPUS_COLORS.slate[200]};
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-height: 0; /* Allow flex shrinking */
`;

/** Sidebar header - minimal label, aligned with content */
export const SidebarLabel = styled.div`
  padding: 1.5rem 1.5rem 1rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
`;

/** Section label - uppercase, readable, muted */
export const SectionLabel = styled.span`
  font-size: 0.875rem;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: ${CORPUS_COLORS.slate[400]};
`;

/** Sidebar content - scrollable document list */
export const SidebarContent = styled.div`
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 0 0.5rem 1rem;

  &::-webkit-scrollbar {
    width: 6px;
  }

  &::-webkit-scrollbar-track {
    background: transparent;
  }

  &::-webkit-scrollbar-thumb {
    background: ${CORPUS_COLORS.slate[200]};
    border-radius: 3px;

    &:hover {
      background: ${CORPUS_COLORS.slate[300]};
    }
  }
`;

/** About main content area */
export const AboutMainContent = styled.div`
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-width: 0;
  min-height: 0; /* Allow flex shrinking */
`;

/** About header - label + actions */
export const AboutHeader = styled.div`
  padding: 1.5rem 2.5rem 1rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
`;

/** About actions - inline, minimal */
export const AboutActions = styled.div`
  display: flex;
  align-items: center;
  gap: 1rem;
`;

/** Text button - minimal, link-like */
export const TextButton = styled.button`
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0;
  background: transparent;
  border: none;
  color: ${CORPUS_COLORS.slate[400]};
  font-size: 0.8125rem;
  font-weight: 500;
  cursor: pointer;
  transition: color ${CORPUS_TRANSITIONS.fast};

  svg {
    width: 14px;
    height: 14px;
  }

  &:hover {
    color: ${CORPUS_COLORS.teal[700]};
  }

  &:focus-visible {
    outline: 2px solid ${CORPUS_COLORS.teal[500]};
    outline-offset: 4px;
  }
`;

/** Primary text button */
export const TextButtonPrimary = styled(TextButton)`
  color: ${CORPUS_COLORS.teal[700]};

  &:hover {
    color: ${CORPUS_COLORS.teal[600]};
  }
`;

/** About body - scrollable content, fills available width */
export const AboutBody = styled.div`
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 0 2.5rem 2rem;

  /* Typography for readable prose - human-sized for desktop */
  font-size: 1.3125rem;
  line-height: 1.9;
  color: ${CORPUS_COLORS.slate[600]};

  /* Paragraph spacing */
  p {
    margin-bottom: 1.5em;
    /* Optimal reading width per paragraph */
    max-width: 60ch;
  }

  /* First paragraph - lead-in */
  p:first-of-type {
    font-size: 1.4375rem;
    color: ${CORPUS_COLORS.slate[700]};
  }

  &::-webkit-scrollbar {
    width: 6px;
  }

  &::-webkit-scrollbar-track {
    background: transparent;
  }

  &::-webkit-scrollbar-thumb {
    background: ${CORPUS_COLORS.slate[200]};
    border-radius: 3px;

    &:hover {
      background: ${CORPUS_COLORS.slate[300]};
    }
  }
`;

/** Expand button - minimal */
export const ExpandButton = styled.button`
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0;
  background: transparent;
  border: none;
  color: ${CORPUS_COLORS.slate[400]};
  font-size: 0.75rem;
  font-weight: 500;
  cursor: pointer;
  transition: color ${CORPUS_TRANSITIONS.fast};

  svg {
    width: 12px;
    height: 12px;
  }

  &:hover {
    color: ${CORPUS_COLORS.teal[700]};
  }

  &:focus-visible {
    outline: 2px solid ${CORPUS_COLORS.teal[500]};
    outline-offset: 4px;
  }
`;

// Keep old exports for backwards compatibility but mark as deprecated
/** @deprecated Use DocumentsSidebar instead */
export const ColumnWrapper = styled.div`
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
`;

/** @deprecated Use SidebarLabel/AboutHeader instead */
export const ColumnHeader = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.5rem;
  flex-shrink: 0;
`;

/** @deprecated Use SectionLabel instead */
export const ColumnTitle = styled.h2`
  margin: 0;
  font-size: 0.6875rem;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: ${CORPUS_COLORS.slate[400]};
`;

/** @deprecated Use AboutActions instead */
export const ColumnActions = styled.div`
  display: flex;
  align-items: center;
  gap: 0.5rem;
`;

/** @deprecated Use TextButton instead */
export const ColumnActionButton = styled.button`
  display: flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0;
  border: none;
  background: transparent;
  color: ${CORPUS_COLORS.slate[400]};
  font-size: 0.8125rem;
  font-weight: 500;
  cursor: pointer;
  transition: color ${CORPUS_TRANSITIONS.fast};

  svg {
    width: 14px;
    height: 14px;
  }

  &:hover {
    color: ${CORPUS_COLORS.teal[700]};
  }
`;

/** @deprecated Use TextButtonPrimary instead */
export const ColumnActionButtonPrimary = styled(ColumnActionButton)`
  color: ${CORPUS_COLORS.teal[700]};

  &:hover {
    color: ${CORPUS_COLORS.teal[600]};
  }
`;

/** @deprecated Use SidebarContent/AboutBody instead */
export const ColumnContent = styled.div`
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  min-height: 0;
`;

/** @deprecated No longer used */
export const ColumnCard = styled.div`
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
`;

// ============================================================================
// MOBILE TAB STYLES
// ============================================================================

/** Mobile tab container - only visible on tablet/mobile */
export const MobileTabContainer = styled.div`
  display: none;

  ${mediaQuery.tablet} {
    display: flex;
    flex-direction: column;
    flex: 1;
    min-height: 0;
    overflow: hidden;
  }
`;

/** Mobile tab list — transparent underline tabs, no card borders */
export const MobileTabList = styled.div`
  display: flex;
  background: transparent;
  border-bottom: 1px solid ${CORPUS_COLORS.slate[200]};
  flex-shrink: 0;
`;

/** Mobile tab button — transparent with underline indicator */
export const MobileTab = styled.button<{ $active: boolean }>`
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  padding: 0.75rem 1rem;
  border: none;
  background: transparent;
  color: ${(props) =>
    props.$active ? CORPUS_COLORS.teal[700] : CORPUS_COLORS.slate[400]};
  font-size: 0.875rem;
  font-weight: ${(props) => (props.$active ? "600" : "500")};
  cursor: pointer;
  transition: all ${CORPUS_TRANSITIONS.fast};
  position: relative;

  ${(props) =>
    props.$active &&
    `
    &::after {
      content: '';
      position: absolute;
      bottom: -1px;
      left: 0;
      right: 0;
      height: 2px;
      background: ${CORPUS_COLORS.teal[700]};
    }
  `}

  &:hover {
    color: ${(props) =>
      props.$active ? CORPUS_COLORS.teal[700] : CORPUS_COLORS.slate[600]};
  }

  &:focus-visible {
    outline: 2px solid ${CORPUS_COLORS.teal[500]};
    outline-offset: -2px;
  }

  svg {
    width: 16px;
    height: 16px;
  }
`;

/** Mobile tab content — borderless, flows naturally */
export const MobileTabContent = styled.div`
  display: flex;
  flex-direction: column;
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  background: ${CORPUS_COLORS.white};
  min-height: 0;

  > :last-child {
    flex: 1 0 auto;
    min-height: 0;
  }

  &::-webkit-scrollbar {
    width: 6px;
  }

  &::-webkit-scrollbar-track {
    background: transparent;
  }

  &::-webkit-scrollbar-thumb {
    background: ${CORPUS_COLORS.slate[200]};
    border-radius: 3px;

    &:hover {
      background: ${CORPUS_COLORS.slate[300]};
    }
  }
`;

/** Lightweight action row for mobile About tab — right-aligned, no background */
export const MobileAboutActions = styled.div`
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 1rem;
  padding: 0.75rem 1rem 0;
`;

/** Toolbar above the mobile document list — search + expand toggle */
export const MobileDocToolbar = styled.div`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1rem;
  border-bottom: 1px solid ${CORPUS_COLORS.slate[200]};
  flex-shrink: 0;
`;

/** Lightweight text input for instant document filtering on mobile */
export const MobileSearchInput = styled.input`
  flex: 1;
  padding: 0.5rem 0.75rem;
  border: 1px solid ${CORPUS_COLORS.slate[200]};
  border-radius: ${CORPUS_RADII.sm};
  font-size: 0.8125rem;
  background: ${CORPUS_COLORS.white};
  color: ${CORPUS_COLORS.slate[700]};

  &:focus {
    outline: 2px solid ${CORPUS_COLORS.teal[500]};
    outline-offset: -1px;
  }

  &::placeholder {
    color: ${CORPUS_COLORS.slate[400]};
  }
`;

// ============================================================================
// HEADER ROW (breadcrumb / back-button + mobile menu)
// ============================================================================

/** Flex row that holds breadcrumbs (or a back button) and the mobile menu
 *  button side-by-side, keeping the menu button outside the <nav> landmark.
 *  Defaults to centered layout; the landing view uses position:absolute on the
 *  menu button so breadcrumbs stay visually centered. Pass $justify to override
 *  (e.g. "space-between" in the details view). */
export const HeaderRow = styled.div<{
  $justify?: string;
  $mobileJustify?: string;
}>`
  display: flex;
  align-items: center;
  justify-content: ${(props) => props.$justify || "center"};
  width: 100%;
  position: relative;

  ${mediaQuery.mobile} {
    justify-content: ${(props) =>
      props.$mobileJustify || props.$justify || "center"};
  }
`;

// ============================================================================
// MOBILE MENU BUTTON
// ============================================================================

/** Mobile-only menu button — styled to match MetadataItem weight
 *  so it blends into the metadata row without drawing attention. */
export const MobileMenuButton = styled.button`
  display: none;
  align-items: center;
  justify-content: center;
  padding: 0;
  background: none;
  border: none;
  color: ${CORPUS_COLORS.slate[400]};
  cursor: pointer;
  transition: color ${CORPUS_TRANSITIONS.fast};
  flex-shrink: 0;

  &:hover {
    color: ${CORPUS_COLORS.teal[700]};
  }

  &:focus-visible {
    outline: 2px solid ${CORPUS_COLORS.teal[500]};
    outline-offset: 4px;
  }

  svg {
    width: 16px;
    height: 16px;
  }

  ${mediaQuery.tablet} {
    display: flex;
  }
`;

// ============================================================================
// EXPAND TOGGLE BUTTON
// ============================================================================

/** Expand/Collapse all toggle button */
export const ExpandToggleButton = styled.button`
  display: flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.5rem 0.875rem;
  border: 1px solid ${CORPUS_COLORS.slate[200]};
  border-radius: ${CORPUS_RADII.sm};
  background: ${CORPUS_COLORS.white};
  color: ${CORPUS_COLORS.slate[600]};
  font-size: 0.8125rem;
  font-weight: 500;
  cursor: pointer;
  transition: all ${CORPUS_TRANSITIONS.fast};

  svg {
    width: 14px;
    height: 14px;
  }

  &:hover {
    background: ${CORPUS_COLORS.slate[50]};
    border-color: ${CORPUS_COLORS.teal[200]};
    color: ${CORPUS_COLORS.teal[700]};
  }

  &:focus-visible {
    outline: 2px solid ${CORPUS_COLORS.teal[500]};
    outline-offset: 2px;
  }
`;
