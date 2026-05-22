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
