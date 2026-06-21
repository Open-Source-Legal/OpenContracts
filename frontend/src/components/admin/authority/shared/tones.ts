/**
 * Shared tone palette for the Authority Console.
 *
 * Extracted from the (previously duplicated) tone maps in AuthorityMappings and
 * AuthoritySourcesMonitor so every console chip / badge speaks the same visual
 * language. A "tone" is a semantic colour band; concrete value→tone mappings
 * (source colours, discovery-state colours, …) live with the component that
 * owns that vocabulary.
 */
import { OS_LEGAL_COLORS } from "../../../../assets/configurations/osLegalStyles";

export type Tone = "info" | "success" | "warning" | "danger" | "neutral";

export const TONE_COLORS: Record<
  Tone,
  { fg: string; bg: string; border: string }
> = {
  info: {
    fg: OS_LEGAL_COLORS.infoText,
    bg: OS_LEGAL_COLORS.infoSurface,
    border: OS_LEGAL_COLORS.infoBorder,
  },
  success: {
    fg: OS_LEGAL_COLORS.successText,
    bg: OS_LEGAL_COLORS.successSurface,
    border: OS_LEGAL_COLORS.successBorder,
  },
  warning: {
    fg: OS_LEGAL_COLORS.warningText,
    bg: OS_LEGAL_COLORS.warningSurface,
    border: OS_LEGAL_COLORS.warningBorder,
  },
  danger: {
    fg: OS_LEGAL_COLORS.dangerText,
    bg: OS_LEGAL_COLORS.dangerSurface,
    border: OS_LEGAL_COLORS.dangerBorder,
  },
  neutral: {
    fg: OS_LEGAL_COLORS.textSecondary,
    bg: OS_LEGAL_COLORS.surfaceLight,
    border: OS_LEGAL_COLORS.border,
  },
};

/** Tone for an AuthorityKeyEquivalence/Namespace ``source`` value. */
const SOURCE_TONES: Record<string, Tone> = {
  manual: "success",
  popular_name: "info",
  uslm: "info",
  baseline: "neutral",
};
export const sourceTone = (s: string): Tone => SOURCE_TONES[s] ?? "neutral";

/** Tone for an AuthorityFrontier ``discovery_state`` value. */
const STATE_TONES: Record<string, Tone> = {
  queued: "neutral",
  in_progress: "info",
  ingested: "success",
  resolved: "success",
  pending_approval: "warning",
  deferred_cap: "warning",
  failed: "danger",
  unsupported: "danger",
  blocked_license: "danger",
  blocked_domain: "danger",
  unlocated: "danger",
};
export const stateTone = (s: string): Tone => STATE_TONES[s] ?? "neutral";

/** Human label for a discovery_state / source code (underscores → spaces). */
export const humanizeCode = (s: string): string =>
  s ? s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()) : s;
