import { OS_LEGAL_COLORS } from "../assets/configurations/osLegalStyles";

const AVATAR_COLOR_PALETTE = [
  OS_LEGAL_COLORS.primaryBlue,
  OS_LEGAL_COLORS.greenMedium,
  OS_LEGAL_COLORS.folderIcon,
  OS_LEGAL_COLORS.dangerBorderHover,
  "#8B5CF6",
  "#EC4899",
] as const;

/**
 * Gets initials from a friendly display name for avatar display.
 *
 * Issue #1557: ``displayName`` from the backend is already redacted, so we
 * no longer need to inspect raw OAuth ``provider|sub`` formats — but we still
 * defend against the legacy shape just in case it shows up.
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
  return name.substring(0, 2).toUpperCase();
}

/**
 * Gets a consistent avatar background color for a user based on their ID.
 */
export function getLeaderboardAvatarColor(userId?: string): string {
  if (!userId) return AVATAR_COLOR_PALETTE[0];
  const hash = userId.split("").reduce((sum, ch) => sum + ch.charCodeAt(0), 0);
  return AVATAR_COLOR_PALETTE[hash % AVATAR_COLOR_PALETTE.length];
}
