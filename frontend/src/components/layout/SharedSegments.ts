import styled from "styled-components";
import { OS_LEGAL_COLORS } from "../../assets/configurations/osLegalStyles";

/**
 * Card-like segment with plain white background.
 * Use for admin panels, tables, and general content containers.
 */
export const CardSegment = styled.div`
  padding: 1rem;
  border-radius: 12px;
  background: white;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
`;

/**
 * Card-like segment with subtle gradient background.
 * Use for feature cards, leaderboards, and badge displays.
 */
export const GradientSegment = styled.div`
  padding: 1rem;
  border-radius: 16px;
  background: linear-gradient(
    135deg,
    #ffffff 0%,
    ${OS_LEGAL_COLORS.surfaceHover} 100%
  );
  border: 1px solid ${OS_LEGAL_COLORS.border};
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
`;

/**
 * Horizontally scrollable wrapper for a wide data table.
 *
 * Multi-column tables overflow narrow viewports; without a scroll container
 * the browser crushes columns until cell content wraps character-by-character
 * (issue #1749). Wrapping the table keeps it at a readable `$minWidth` and
 * scrolls it horizontally on small screens instead. On viewports wider than
 * `$minWidth` the table still fills the container as usual.
 *
 * The `min-width` is applied to the direct child (the table element) rather
 * than via a `table` selector so it holds regardless of whether the UI table
 * renders as a `<table>` or a `<div role="table">`. Wrap exactly one table.
 */
export const ScrollableTableWrapper = styled.div<{ $minWidth: string }>`
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;

  > * {
    min-width: ${({ $minWidth }) => $minWidth};
  }
`;
