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

export interface CreatorRef {
  id?: string | null;
  slug?: string | null;
}

/** Public display for a user reference. Always returns a non-empty
 *  string. Prefer slug; fall back to a redacted ``user_<id>`` handle. */
export function getCreatorDisplay(
  creator: CreatorRef | null | undefined
): string {
  if (!creator) return "Unknown";
  if (creator.slug) return creator.slug;
  if (creator.id) return `user_${creator.id}`;
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
