/**
 * Registry of bundled landing/About content variants and the hook
 * components use to read the active variant.
 *
 * Variant is chosen by `REACT_APP_LANDING_VARIANT` (runtime, set in
 * `frontend/public/env-config.js` or via the deployer's env). Unknown
 * variant strings fall back to `default` rather than crashing — the
 * world-facing pitch is always a safe default.
 *
 * To add a new variant:
 *   1. Drop a `<key>.json` file in this directory matching
 *      `LandingContent` from `./types`.
 *   2. Register it below.
 *   3. Document the key in README.md so deployers can find it.
 */
import { useMemo } from "react";

import { useEnv } from "../../components/hooks/UseEnv";

import defaultContent from "./default.json";
import publicRecordContent from "./publicRecord.json";
import type { LandingContent } from "./types";

export const LANDING_VARIANTS: Readonly<Record<string, LandingContent>> = {
  default: defaultContent as LandingContent,
  "public-record": publicRecordContent as LandingContent,
};

export const DEFAULT_LANDING_VARIANT = "default";

/**
 * Returns the active LandingContent pack. Memoizes on variant key so
 * components stay referentially stable across rerenders.
 */
export function useLandingContent(): LandingContent {
  const env = useEnv();
  const variant = env.REACT_APP_LANDING_VARIANT || DEFAULT_LANDING_VARIANT;
  return useMemo(
    () =>
      LANDING_VARIANTS[variant] ?? LANDING_VARIANTS[DEFAULT_LANDING_VARIANT],
    [variant]
  );
}

export { renderInlineMarkup } from "./renderInlineMarkup";

export type { LandingContent } from "./types";
export type {
  HeroContent,
  StatConfig,
  GetStartedContent,
  GetStartedAction,
  CallToActionContent,
  AboutContent,
  AboutSection,
  AboutFooterLink,
  CommunityStatKey,
} from "./types";
