/**
 * Shared visual-design tokens for the mobile DocumentKnowledgeBase layout.
 *
 * Keeps the "calm, layered, native-quality" aesthetic DRY: a deliberate radius
 * scale, a soft layered-shadow scale (depth over borders) and a warm-neutral
 * surface tint so white cards and chrome visibly float. Colors stay sourced
 * from {@link OS_LEGAL_COLORS} — these tokens add structure, not new hues.
 */

/** Corner-radius scale. Apply deliberately by element size. */
export const MOBILE_RADIUS = {
  /** Small controls — chips, step buttons. */
  sm: "10px",
  /** Medium surfaces — cards, inputs, icon containers. */
  md: "14px",
  /** Large surfaces — sheets, prominent cards. */
  lg: "18px",
  /** Fully rounded — pills, circular buttons. */
  pill: "999px",
} as const;

/** Soft layered-shadow scale. Replaces flat 1px hairline borders. */
export const MOBILE_SHADOW = {
  /** Barely-there lift for resting cards and chips. */
  subtle: "0 1px 2px rgba(15, 23, 42, 0.04), 0 1px 3px rgba(15, 23, 42, 0.06)",
  /** Floating cards, inputs, menu rows. */
  raised: "0 2px 8px rgba(15, 23, 42, 0.06), 0 6px 20px rgba(15, 23, 42, 0.07)",
  /** Bottom chrome (tab bar / ask bar) — a soft upward shadow. */
  chrome: "0 -2px 16px rgba(15, 23, 42, 0.07)",
  /** Header chrome — a soft downward shadow. */
  header: "0 2px 12px rgba(15, 23, 42, 0.06)",
} as const;

/**
 * Warm-neutral page surface tint. Slightly cooler-warm than pure white so
 * white cards and chrome read as layered rather than stark white-on-white.
 */
export const MOBILE_SURFACE_TINT = "#f5f6f8";

/** Teal-tinted focus ring for inputs. */
export const MOBILE_FOCUS_RING = "0 0 0 3px rgba(15, 118, 110, 0.16)";
