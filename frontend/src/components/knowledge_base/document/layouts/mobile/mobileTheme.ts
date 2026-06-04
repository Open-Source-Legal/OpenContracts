/**
 * Mobile-named aliases for the shared DocumentKnowledgeBase design tokens.
 *
 * The actual values live in
 * {@link ../../../../../assets/configurations/designTokens} — the single
 * source of truth shared with the desktop chat/filter/control surfaces. This
 * module only re-exports them under the `MOBILE_*` names the mobile layout
 * already consumes, so editing a token in one place updates both layouts.
 */
import {
  FOCUS_RING,
  RADIUS,
  SHADOW,
  SURFACE_TINT,
} from "../../../../../assets/configurations/designTokens";

/** Corner-radius scale. Apply deliberately by element size. */
export const MOBILE_RADIUS = RADIUS;

/** Soft layered-shadow scale. Replaces flat 1px hairline borders. */
export const MOBILE_SHADOW = SHADOW;

/** Warm-neutral page surface tint so white cards and chrome visibly float. */
export const MOBILE_SURFACE_TINT = SURFACE_TINT;

/** Teal-tinted focus ring for inputs. */
export const MOBILE_FOCUS_RING = FOCUS_RING;

/**
 * Spacing scale (px) for mobile sheet padding and stacked-element gaps.
 * Kept here alongside the other mobile-layout tokens so the values are named
 * (no magic numbers) and tunable in one place. `blockCompact` matches the
 * existing EmptyState padding; `blockRoomy` gives a loader a touch more room.
 */
export const MOBILE_SPACING = {
  /** Inline (horizontal) padding for sheet text blocks. */
  inline: 16,
  /** Vertical padding for a compact text state (EmptyState). */
  blockCompact: 24,
  /** Vertical padding for a state needing more breathing room (loader). */
  blockRoomy: 40,
  /** Gap between stacked loader elements (spinner ↔ label). */
  stackGap: 12,
} as const;
