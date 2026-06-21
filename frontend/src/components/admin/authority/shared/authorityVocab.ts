/**
 * Frontend mirror of the authority taxonomy vocabularies needed by the console's
 * create/edit forms. The authoritative source is the backend
 * ``opencontractserver/enrichment/constants.py`` (ALL_AUTHORITY_TYPES); these
 * options are kept in lock-step with it (the backend validates on write, so a
 * drift surfaces as a clean validation error rather than silent corruption).
 */
import { Tone } from "./tones";

export const REGISTRY_PAGE_SIZE = 50;

/** ALL_AUTHORITY_TYPES, in display order. */
export const AUTHORITY_TYPE_OPTIONS: readonly string[] = [
  "statute",
  "regulation",
  "admin-rule",
  "municipal-ordinance",
  "case",
  "constitution",
  "court-rule",
  "guidance",
  "treaty",
];

export const scopeTone = (scope: string): Tone =>
  scope === "global" ? "info" : "neutral";

export const scopeLabel = (scope: string): string =>
  scope === "global" ? "Global" : scope === "corpus" ? "Corpus-scoped" : scope;
