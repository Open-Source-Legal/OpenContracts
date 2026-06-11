import styled, { keyframes } from "styled-components";

import { OS_LEGAL_COLORS } from "../../../../assets/configurations/osLegalStyles";

/**
 * Shared card chrome for the corpus-intelligence graph glimpses
 * (``DocumentGraphGlimpse``, ``GovernanceGraphGlimpse``): the card shell,
 * header, SVG frame, skeleton, legend, empty state, and explore link are
 * identical between them — only the graph inside differs.
 */

export const GraphCard = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  width: 100%;
  padding: 1rem 1.25rem 1.25rem;
  background: ${OS_LEGAL_COLORS.surfaceLight};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 14px;
`;

export const GraphHeader = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
`;

export const GraphTitle = styled.div<{ $iconColor?: string }>`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.875rem;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textPrimary};

  svg {
    color: ${(props) => props.$iconColor || OS_LEGAL_COLORS.primaryBlue};
  }
`;

export const GraphMeta = styled.span`
  font-size: 0.75rem;
  color: ${OS_LEGAL_COLORS.textMuted};
  font-variant-numeric: tabular-nums;
`;

export const SvgWrapper = styled.div`
  width: 100%;
  background: white;
  border-radius: 10px;
  overflow: hidden;

  svg {
    display: block;
    width: 100%;
    height: auto;
  }
`;

export const ExploreLink = styled.button`
  align-self: flex-end;
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  background: none;
  border: none;
  padding: 0.25rem 0.25rem;
  font-size: 0.8125rem;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.primaryBlue};
  cursor: pointer;

  &:hover {
    text-decoration: underline;
  }

  svg {
    width: 14px;
    height: 14px;
  }
`;

export const EmptyState = styled.div`
  padding: 1.5rem 1rem;
  text-align: center;
  font-size: 0.8125rem;
  color: ${OS_LEGAL_COLORS.textMuted};
`;

const shimmer = keyframes`
  0% { opacity: 0.45; }
  50% { opacity: 0.8; }
  100% { opacity: 0.45; }
`;

/**
 * First-load placeholder matching the SVG's aspect ratio so the card doesn't
 * reflow when the graph arrives. Mirrors IntelligencePanel's StatSkeleton.
 */
export const GraphSkeleton = styled.div<{
  $viewWidth: number;
  $viewHeight: number;
}>`
  width: 100%;
  aspect-ratio: ${(props) => props.$viewWidth} / ${(props) => props.$viewHeight};
  border-radius: 10px;
  background: ${OS_LEGAL_COLORS.surfaceHover};
  animation: ${shimmer} 1.2s ease-in-out infinite;
`;

/**
 * Legend — without it a graph is just dots and lines: a first-time viewer
 * can't tell what an edge or a big node means. Glimpses render entries
 * conditionally on the vocabulary actually present in the data.
 */
export const Legend = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 0.3rem 1.1rem;
  font-size: 0.75rem;
  color: ${OS_LEGAL_COLORS.textMuted};
`;

export const LegendItem = styled.span`
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  white-space: nowrap;
`;
