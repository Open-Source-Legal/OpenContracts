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

export interface OverflowMenuLink {
  id: string;
  label: string;
  /** Internal route path; mutually exclusive with ``href``. */
  to?: string;
  /** External URL; mutually exclusive with ``to``. Opens in a new tab. */
  href?: string;
}

export const overflow_menu_links: OverflowMenuLink[] = [
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
