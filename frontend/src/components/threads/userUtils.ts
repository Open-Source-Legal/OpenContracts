/**
 * Utility functions for formatting user display information
 */

/**
 * Format username with better fallbacks for OAuth IDs
 *
 * Handles various OAuth provider ID formats and falls back gracefully:
 * - Detects OAuth IDs like "google-oauth2|114688257717759010643"
 * - Extracts email local part when OAuth ID detected
 * - Falls back to "User" if no email available
 * - Returns raw username for normal usernames
 *
 * @param username - Raw username (may be OAuth ID)
 * @param email - User's email address
 * @returns Formatted username for display
 *
 * @example
 * formatUsername("google-oauth2|123456", "john@example.com") // "john"
 * formatUsername("john_doe", "john@example.com") // "john_doe"
 * formatUsername("google-oauth2|123456", undefined) // "User"
 */
export function formatUsername(
  username?: string | null,
  email?: string | null
): string {
  if (!username && !email) return "Anonymous";

  const rawUsername = username || email;
  if (!rawUsername) return "Anonymous";

  // Detect OAuth ID patterns (e.g., "google-oauth2|114688257717759010643", "auth0|123456")
  const isOAuthId = rawUsername.match(
    /^(google-oauth2|auth0|github|twitter|facebook|linkedin)\|/
  );

  if (isOAuthId && email) {
    // Extract local part of email (before @)
    const emailLocal = email.split("@")[0];
    // Clean up email local parts that might have dots or plus addressing
    return emailLocal.replace(/\+.*$/, "").replace(/\./g, " ");
  }

  if (isOAuthId) {
    return "User";
  }

  return rawUsername;
}

/**
 * Get user initials for avatar display
 *
 * @param username - Formatted username
 * @returns 1-2 character initials
 *
 * @example
 * getUserInitials("John Doe") // "JD"
 * getUserInitials("john") // "J"
 * getUserInitials("Anonymous") // "A"
 */
export function getUserInitials(username: string): string {
  if (!username || username === "Anonymous") return "A";

  const parts = username.trim().split(/\s+/);

  if (parts.length >= 2) {
    // First letter of first two words
    return (parts[0][0] + parts[1][0]).toUpperCase();
  }

  // First two letters of single word
  return username.slice(0, 2).toUpperCase();
}
