import { OS_LEGAL_COLORS } from "../assets/configurations/osLegalStyles";

// Leaderboard-specific avatar palette.  The violet/pink accents below are
// not present in OS_LEGAL_COLORS but live here so the whole palette stays a
// single audit-able list; exported so theme audits can import the literals
// directly instead of round-tripping through this module's behaviour.
export const AVATAR_VIOLET = "#8B5CF6";
export const AVATAR_PINK = "#EC4899";

const AVATAR_COLOR_PALETTE = [
  OS_LEGAL_COLORS.primaryBlue,
  OS_LEGAL_COLORS.greenMedium,
  OS_LEGAL_COLORS.folderIcon,
  OS_LEGAL_COLORS.dangerBorderHover,
  AVATAR_VIOLET,
  AVATAR_PINK,
] as const;

/**
 * Gets initials from a friendly display name for avatar display.
 *
 * The backend ``displayName`` resolver redacts raw OAuth ``provider|sub``
 * shapes, so this only needs to handle plain names. The ``|`` branch is
 * a defensive fallback for legacy cached values.
 */
export function getLeaderboardInitials(name?: string): string {
  if (!name) return "?";
  if (name.includes("|")) {
    const provider = name.split("|")[0];
    if (provider.includes("google")) return "G";
    if (provider.includes("github")) return "GH";
    return "U";
  }
  const tokens = name.trim().split(/\s+/).filter(Boolean);
  if (tokens.length >= 2) {
    return (tokens[0][0] + tokens[1][0]).toUpperCase();
  }
  if (tokens.length === 1) {
    // Use the trimmed token, not the raw input — leading whitespace would
    // otherwise turn ``"  alice"`` into ``"  "``.
    return tokens[0].substring(0, 2).toUpperCase();
  }
  return "?";
}

/**
 * Gets a consistent avatar background color for a user based on their ID.
 */
export function getLeaderboardAvatarColor(userId?: string): string {
  if (!userId) return AVATAR_COLOR_PALETTE[0];
  const hash = userId.split("").reduce((sum, ch) => sum + ch.charCodeAt(0), 0);
  return AVATAR_COLOR_PALETTE[hash % AVATAR_COLOR_PALETTE.length];
}
