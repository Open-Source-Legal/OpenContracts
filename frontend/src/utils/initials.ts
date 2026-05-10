/**
 * Display-name → initials helpers.
 *
 * Pulled out of avatar components so multiple surfaces (mobile nav user
 * chip, desktop avatar, badge popover, etc.) render the same initials
 * for the same name. Keep this dependency-free — utility files in
 * ``frontend/src/utils/`` should be pure functions per CLAUDE.md.
 */

/**
 * Two-character initials for a display name. First letters of the first
 * two whitespace-separated words, uppercased. Falls back to ``"?"`` for
 * empty / whitespace-only input so an avatar always has something to
 * render.
 *
 * @example
 *   initialsFor("Alice Anderson")        // "AA"
 *   initialsFor("alice anderson smith")  // "AA" (first two words)
 *   initialsFor("alice")                 // "A"
 *   initialsFor("")                      // "?"
 *   initialsFor("   ")                   // "?"
 */
export function initialsFor(name: string): string {
  const trimmed = name.trim();
  if (!trimmed) return "?";
  const parts = trimmed.split(/\s+/).slice(0, 2);
  return parts.map((p) => p[0]?.toUpperCase() ?? "").join("") || "?";
}
