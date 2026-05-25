import React from "react";

import {
  OS_LEGAL_COLORS,
  OS_LEGAL_TYPOGRAPHY,
} from "../../assets/configurations/osLegalStyles";

interface CiteWordmarkProps {
  /** Pixel size of the rendered wordmark. Width auto-scales. */
  size?: number;
  /** Variant. "dark" = slate on transparent, "light" = warm-paper on transparent (for navy chrome). */
  variant?: "dark" | "light";
  /** Accessible label. Defaults to "cite". */
  ariaLabel?: string;
  className?: string;
  style?: React.CSSProperties;
}

/**
 * The `[cite]` wordmark, set in Source Serif 4 with the bracket characters
 * preserved (per the brand system, the brackets are part of the wordmark,
 * not decoration).
 *
 * Renders as inline SVG with a font fallback chain (Source Serif Pro,
 * Georgia, serif) so the mark reads correctly before web fonts load.
 *
 * Wrapped in React.memo: every prop is a primitive, and the wordmark
 * lives in chrome (NavMenu, Footer) that re-renders on unrelated state.
 */
const CiteWordmarkInner: React.FC<CiteWordmarkProps> = ({
  size = 28,
  variant = "dark",
  ariaLabel = "cite",
  className,
  style,
}) => {
  const fill =
    variant === "light"
      ? OS_LEGAL_COLORS.warmPaper
      : OS_LEGAL_COLORS.textPrimary;
  // Source SVG viewBox is 200×80 (aspect 2.5). Width scales accordingly.
  const height = size;
  const width = size * 2.5;
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 200 80"
      width={width}
      height={height}
      role="img"
      aria-label={ariaLabel}
      className={className}
      style={style}
    >
      <text
        x="100"
        y="56"
        textAnchor="middle"
        style={{
          fontFamily: OS_LEGAL_TYPOGRAPHY.fontFamilySerif,
          fontSize: "56px",
          fontWeight: 400,
          fill,
          letterSpacing: "-1px",
        }}
      >
        [cite]
      </text>
    </svg>
  );
};

export const CiteWordmark = React.memo(CiteWordmarkInner);

export default CiteWordmark;
