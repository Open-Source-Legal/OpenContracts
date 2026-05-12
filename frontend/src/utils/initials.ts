// Display-name → initials. First letters of the first two
// whitespace-separated words, uppercased; "?" for empty input.
//
// Scope: tuned for Latin / CJK display names where whitespace is the
// natural word separator (Auth0 names, local usernames). Scripts that
// don't separate words with whitespace — Arabic, Thai, written Chinese
// without spaces, etc. — collapse to a single initial (the first
// codepoint of the whole string). That degrades gracefully but isn't a
// linguistically correct "initial"; switch to ICU word-segmentation
// (``Intl.Segmenter`` with ``granularity: 'word'``) if richer handling
// is ever needed.
export function initialsFor(name: string): string {
  const trimmed = name.trim();
  if (!trimmed) return "?";
  const parts = trimmed.split(/\s+/).slice(0, 2);
  return parts.map((p) => p[0]?.toUpperCase() ?? "").join("") || "?";
}
