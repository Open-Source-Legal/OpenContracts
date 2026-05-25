import React from "react";

interface CiteMarkProps {
  /** Pixel size of the rendered square. Stroke weights scale with size. */
  size?: number;
  /** Bracket color. Defaults to slate ink. */
  bracketColor?: string;
  /** Center node color. Defaults to teal accent. */
  nodeColor?: string;
  /** Override stroke weight. Default scales: 1.2px@16, 1.8px@32, 2.4px@48+. */
  strokeWidth?: number;
  /** Accessible label. Defaults to "cite mark". */
  ariaLabel?: string;
  className?: string;
  style?: React.CSSProperties;
}

const strokeFor = (size: number) => {
  if (size <= 18) return 1.2;
  if (size <= 36) return 1.8;
  if (size <= 56) return 2.4;
  return 3;
};

/**
 * Bracketed teal node — the cite icon mark.
 * Renders inline; viewBox is 64×64 and the geometry matches the
 * production SVG in /assets/brand/icon_mark.svg.
 *
 * Wrapped in React.memo: every prop is a primitive, and the mark
 * appears in NavMenu / Footer / About / Login / CTA where the parent
 * re-renders on unrelated state changes.
 */
const CiteMarkInner: React.FC<CiteMarkProps> = ({
  size = 24,
  bracketColor = "#1E293B",
  nodeColor = "#0F766E",
  strokeWidth,
  ariaLabel = "cite mark",
  className,
  style,
}) => {
  const sw = strokeWidth ?? strokeFor(size);
  // An empty `ariaLabel` marks the mark as decorative — render it
  // `aria-hidden` and drop the `role="img"` slot so screen readers skip
  // it entirely. Callers that pass a real label keep the labelled image
  // semantics so the mark stays announceable as the cite brand glyph.
  const decorative = !ariaLabel;
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 64 64"
      width={size}
      height={size}
      role={decorative ? undefined : "img"}
      aria-label={decorative ? undefined : ariaLabel}
      aria-hidden={decorative ? true : undefined}
      className={className}
      style={style}
    >
      <g transform="translate(32, 32)">
        <line
          x1="-19"
          y1="-20"
          x2="-19"
          y2="20"
          stroke={bracketColor}
          strokeWidth={sw}
        />
        <line
          x1="-19"
          y1="-20"
          x2="-11"
          y2="-20"
          stroke={bracketColor}
          strokeWidth={sw}
        />
        <line
          x1="-19"
          y1="20"
          x2="-11"
          y2="20"
          stroke={bracketColor}
          strokeWidth={sw}
        />
        <line
          x1="19"
          y1="-20"
          x2="19"
          y2="20"
          stroke={bracketColor}
          strokeWidth={sw}
        />
        <line
          x1="19"
          y1="-20"
          x2="11"
          y2="-20"
          stroke={bracketColor}
          strokeWidth={sw}
        />
        <line
          x1="19"
          y1="20"
          x2="11"
          y2="20"
          stroke={bracketColor}
          strokeWidth={sw}
        />
        <circle cx="0" cy="0" r="7" fill={nodeColor} />
      </g>
    </svg>
  );
};

export const CiteMark = React.memo(CiteMarkInner);

export default CiteMark;
