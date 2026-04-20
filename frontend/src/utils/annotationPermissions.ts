/**
 * Pure predicates for annotation permission gating.
 *
 * The frontend gates write UI (edit, delete buttons, selection affordances) on
 * permission checks; the backend remains the source of truth. These helpers
 * centralize the predicates so the rules are testable and behave the same in
 * every consumer.
 *
 * Backend reference: `docs/permissioning/consolidated_permissioning_guide.md`.
 * The backend enforces `Effective Permission = MIN(document, corpus)`. The
 * frontend is intentionally more permissive for UX — it shows the control if
 * *either* the corpus *or* the document grants edit — because a failed save
 * surfaces via the server response, and hiding edit UI prematurely frustrates
 * corpus curators who lack explicit per-document grants.
 */
import { PermissionTypes } from "../components/types";

/**
 * Minimal shape needed to evaluate annotation-level gates. Accepting a
 * `Pick` keeps these helpers usable for both `ServerTokenAnnotation` /
 * `ServerSpanAnnotation` instances and plain fixture objects in tests.
 */
export type AnnotationPermissionShape = {
  structural: boolean;
  myPermissions: PermissionTypes[];
};

export interface EffectiveEditOptions {
  /** Explicit override — e.g. when viewing a historical snapshot. */
  readOnly: boolean;
  /** Corpus context is required before any annotation can be created/edited. */
  corpusId: string | null | undefined;
  /** Whether the current corpus grants CAN_UPDATE. */
  canUpdateCorpus: boolean;
  /** Document-level permissions already transformed via `getPermissions`. */
  documentPermissions: PermissionTypes[];
}

/**
 * Whether the user can create or edit annotations on the current document.
 *
 * Rules (evaluated in order):
 *   1. `readOnly` override wins — never edit.
 *   2. Without a corpus, annotations cannot be persisted, so editing is off.
 *   3. If the corpus grants CAN_UPDATE, edit is allowed.
 *   4. Fallback: allow if the document itself grants CAN_UPDATE.
 */
export function canEditAnnotationsInCorpus(
  opts: EffectiveEditOptions
): boolean {
  if (opts.readOnly) return false;
  if (!opts.corpusId) return false;
  if (opts.canUpdateCorpus) return true;
  return opts.documentPermissions.includes(PermissionTypes.CAN_UPDATE);
}

/**
 * Whether the delete affordance should render for a given annotation.
 *
 * Structural annotations (document structure detected by the parser) are
 * read-only for everyone except superusers, and superuser status is resolved
 * server-side — from the frontend's perspective, structural is always
 * delete-gated.
 */
export function canDeleteAnnotation(
  annotation: AnnotationPermissionShape,
  readOnly: boolean
): boolean {
  if (readOnly) return false;
  if (annotation.structural) return false;
  return annotation.myPermissions.includes(PermissionTypes.CAN_REMOVE);
}

/**
 * Whether the edit affordance should render for a given annotation.
 * Same structural/readOnly gates as {@link canDeleteAnnotation}, but checked
 * against CAN_UPDATE.
 */
export function canUpdateAnnotation(
  annotation: AnnotationPermissionShape,
  readOnly: boolean
): boolean {
  if (readOnly) return false;
  if (annotation.structural) return false;
  return annotation.myPermissions.includes(PermissionTypes.CAN_UPDATE);
}
