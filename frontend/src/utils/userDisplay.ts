/**
 * Privacy-preserving user display helpers.
 *
 * The backend redacts email/name/firstName/lastName/username for
 * non-self viewers (see ``config/graphql/user_types.py``), so the
 * frontend must:
 *   - render the public ``slug`` for any cross-user surface
 *   - compare by ``id`` for ownership checks (email may be ``null``)
 *
 * These helpers centralise both rules so individual components don't
 * re-derive them and silently regress if the privacy contract changes.
 */

import { REDACTED_HANDLE_PK_SUFFIX_LENGTH } from "../assets/configurations/constants";

export interface CreatorRef {
  id?: string | null;
  slug?: string | null;
}

/**
 * Decode the numeric primary key from a Relay global ID
 * (``base64("TypeName:pk")``). Returns ``null`` when the input is not a
 * valid Relay ID — caller should fall back to the raw value or a generic
 * placeholder. Pure helper, exported for tests.
 */
export function decodeRelayPk(id: string | null | undefined): string | null {
  if (!id) return null;
  try {
    const decoded =
      typeof atob === "function"
        ? atob(id)
        : Buffer.from(id, "base64").toString("binary");
    const sep = decoded.lastIndexOf(":");
    if (sep === -1) return null;
    const pk = decoded.slice(sep + 1);
    return pk || null;
  } catch {
    return null;
  }
}

/** Public display for a user reference. Always returns a non-empty
 *  string. Prefer slug; fall back to a ``user_<pk-suffix>`` handle that
 *  matches the backend ``_redacted_handle`` shape so two surfaces don't
 *  render different strings for the same user. */
export function getCreatorDisplay(
  creator: CreatorRef | null | undefined
): string {
  if (!creator) return "Unknown";
  if (creator.slug) return creator.slug;
  if (creator.id) {
    const pk = decodeRelayPk(creator.id);
    const suffix = (pk ?? creator.id).slice(-REDACTED_HANDLE_PK_SUFFIX_LENGTH);
    return `user_${suffix || "unknown"}`;
  }
  return "Unknown";
}

/** Initials helper for avatar fallbacks — derives from slug. */
export function getCreatorInitials(
  creator: CreatorRef | null | undefined
): string {
  const display = getCreatorDisplay(creator);
  // Slug uses hyphens between words (sanitize_slug normalises spaces to ``-``).
  const parts = display
    .replace(/^user_/, "")
    .split("-")
    .filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return (parts[0] || "?").substring(0, 2).toUpperCase();
}

/** Ownership comparison — id-based, robust to null email returns. */
export function isOwnedBy(
  creator: CreatorRef | null | undefined,
  currentUser: CreatorRef | null | undefined
): boolean {
  if (!creator || !currentUser) return false;
  if (!creator.id || !currentUser.id) return false;
  return creator.id === currentUser.id;
}
