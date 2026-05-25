/**
 * Typed schema for the landing- and About-page content packs.
 *
 * Two variants ship in this directory:
 *
 *  - `default.json` — the world-facing OSS pitch ("citation layer for
 *    agentic workflows"). Lands well with developers, researchers, and
 *    teams sizing the project up from the README/repo.
 *  - `publicRecord.json` — the named-incumbents pitch for the
 *    `cite.opensource.legal` deployment ("citation layer underneath
 *    the public record"). Lands well with end-users on a specific
 *    deployment of cite for the public domain.
 *
 * To add a new variant, drop a JSON file in this directory that matches
 * `LandingContent`, register it in `index.ts`, and set
 * `REACT_APP_LANDING_VARIANT=<your-key>` on the deployment.
 *
 * Inline italics inside body copy are written as `*word*` and rendered
 * through `renderInlineMarkup` so the cite product name picks up the
 * Source Serif italic treatment in body context (per the brand spec).
 */

/**
 * Keys of `CommunityStats` the StatsSection knows how to render.
 * Constrain JSON to this union so a typo in a variant fails at build.
 */
export type CommunityStatKey =
  | "totalUsers"
  | "totalAnnotations"
  | "totalThreads"
  | "activeUsersThisWeek";

export interface HeroContent {
  /** Render the [•] icon mark before the first headline line. */
  showMark: boolean;
  /** First headline line (slate). Plain text. */
  primary: string;
  /** Second headline line (teal accent). Plain text. */
  accent: string;
  /** Subheadline; supports `*italic*` markup. */
  subheadline: string;
  /** Placeholder text for the discover search input. */
  searchPlaceholder: string;
}

export interface StatConfig {
  /** GraphQL field on `communityStats` to surface. */
  key: CommunityStatKey;
  /** Bold label below the value (sentence case). */
  label: string;
  /** Muted caption beneath the label. */
  sublabel: string;
}

export interface GetStartedAction {
  id: string;
  label: string;
  /** Internal route (`/...`) or external URL when `external: true`. */
  path: string;
  external?: boolean;
}

export interface GetStartedContent {
  title: string;
  actions: GetStartedAction[];
}

export interface CallToActionContent {
  /** Small uppercase eyebrow above the headline. */
  eyebrow: string;
  /** Headline; supports `*italic*` markup. */
  headline: string;
  /** Body paragraph; supports `*italic*` markup. */
  body: string;
  primaryLabel: string;
  secondaryLabel: string;
  /** Path for the secondary link (typically `/about`). */
  secondaryPath: string;
}

export interface AboutSection {
  title: string;
  /** One paragraph per array entry; each supports `*italic*` markup. */
  paragraphs: string[];
}

export interface AboutFooterLink {
  label: string;
  href: string;
  /** Routed via react-router-dom <Link> when true; otherwise an <a>. */
  internal?: boolean;
}

export interface AboutContent {
  eyebrow: string;
  title: string;
  /** Lede paragraph below the title; supports `*italic*` markup. */
  lede: string;
  sections: AboutSection[];
  footerLinks: AboutFooterLink[];
}

export interface LandingContent {
  hero: HeroContent;
  stats: StatConfig[];
  getStarted: GetStartedContent;
  callToAction: CallToActionContent;
  about: AboutContent;
}
