/**
 * Shared visual-design tokens for the DocumentKnowledgeBase surfaces.
 *
 * Single source of truth for the "calm, layered, native-quality" aesthetic:
 * a soft layered-shadow scale (depth over flat hairline borders), a deliberate
 * corner-radius scale, a teal focus ring, and a warm-neutral surface tint.
 * Both the desktop control/chat/filter surfaces and the mobile DKB layout
 * (`layouts/mobile/mobileTheme.ts` re-exports these) consume them, so editing
 * a value here updates every surface at once. Colors stay sourced from
 * {@link OS_LEGAL_COLORS} — these tokens add structure, not new hues.
 */

/** Soft layered-shadow scale. Replaces flat 1px hairline borders. */
export const SHADOW = {
  /** Barely-there lift for resting cards and chips. */
  subtle: "0 1px 2px rgba(15, 23, 42, 0.04), 0 1px 3px rgba(15, 23, 42, 0.06)",
  /** Floating cards, inputs, menu rows. */
  raised: "0 2px 8px rgba(15, 23, 42, 0.06), 0 6px 20px rgba(15, 23, 42, 0.07)",
  /** Pop-over menus / dropdowns. */
  menu: "0 4px 12px rgba(15, 23, 42, 0.08), 0 12px 32px rgba(15, 23, 42, 0.1)",
  /** Bottom chrome (tab bar / ask bar) — a soft upward shadow. */
  chrome: "0 -2px 16px rgba(15, 23, 42, 0.07)",
  /** Header chrome — a soft downward shadow. */
  header: "0 2px 12px rgba(15, 23, 42, 0.06)",
} as const;

/** Corner-radius scale. Apply deliberately by element size. */
export const RADIUS = {
  /** Small controls — chips, step buttons. */
  sm: "10px",
  /** Compact interactive controls — toggles, trigger surfaces. */
  control: "12px",
  /** Medium surfaces — cards, inputs, icon containers, menus. */
  md: "14px",
  /** Large surfaces — sheets, prominent cards. */
  lg: "18px",
  /** Fully rounded — pills, circular buttons. */
  pill: "999px",
} as const;

/** Teal-tinted focus ring for inputs. */
export const FOCUS_RING = "0 0 0 3px rgba(15, 118, 110, 0.16)";

/**
 * Warm-neutral page surface tint. Slightly cooler-warm than pure white so
 * white cards and chrome read as layered rather than stark white-on-white.
 */
export const SURFACE_TINT = "#f5f6f8";
