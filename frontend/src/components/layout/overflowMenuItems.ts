/**
 * Essential links that must remain reachable from the NavMenu overflow on
 * every view — including long-scroll surfaces (corpus Annotations / Analyses
 * / Extracts) where the in-flow Footer is effectively unreachable without
 * scrolling through thousands of cards. See issue #1609.
 *
 * Audit of the Footer (`frontend/src/components/layout/Footer.tsx`):
 *  - Privacy Policy  → /privacy            (route exists, keep)
 *  - Terms of Service → /terms_of_service  (route exists, keep)
 *  - GitHub          → external repo link  (keep)
 *  - Site Map        → /                   (redundant with the brand logo, drop)
 *  - Contact Us      → /contact            (route is NOT registered in App.tsx
 *                                           — would 404; intentionally omitted
 *                                           from the always-on overflow rather
 *                                           than promote a broken destination)
 *
 * The in-flow Footer keeps its current link set unchanged for landing /
 * corpus list / settings views, per the issue ("don't toggle visibility
 * per-route").
 */

/**
 * Discriminated union so TypeScript enforces that exactly one of ``to`` or
 * ``href`` is set — a link with neither would silently render
 * ``<a href={undefined}>`` and a link with both would be ambiguous.
 */
export type OverflowMenuLink =
  | { id: string; label: string; to: string; href?: never }
  | { id: string; label: string; to?: never; href: string };

export const OVERFLOW_MENU_LINKS: OverflowMenuLink[] = [
  {
    id: "overflow_privacy",
    label: "Privacy Policy",
    to: "/privacy",
  },
  {
    id: "overflow_terms",
    label: "Terms of Service",
    to: "/terms_of_service",
  },
  {
    id: "overflow_github",
    label: "GitHub",
    href: "https://github.com/Open-Source-Legal",
  },
];
