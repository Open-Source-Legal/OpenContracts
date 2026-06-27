import {
  EXTRACT_GRID_CELL_TRUNCATE_LENGTH,
  FILE_SIZE,
  LAW_AUTHORITY_ACRONYMS,
  TIME_UNITS,
} from "../assets/configurations/constants";

/**
 * Formats a byte count into a human-readable file size string.
 * @param bytes - The number of bytes to format
 * @returns Formatted string like "1.5 KB" or "2.3 MB", or empty string if null/undefined
 */
export function formatFileSize(bytes?: number | null): string {
  if (bytes == null) return "";
  if (bytes < FILE_SIZE.BYTES_PER_KB) return `${bytes} B`;
  if (bytes < FILE_SIZE.BYTES_PER_MB) {
    return `${(bytes / FILE_SIZE.BYTES_PER_KB).toFixed(1)} KB`;
  }
  return `${(bytes / FILE_SIZE.BYTES_PER_MB).toFixed(1)} MB`;
}

/** Formats an elapsed duration in seconds as e.g. "850ms"/"4.2s"/"3m 5s"/"1h 2m", or "—". */
export function formatDuration(seconds?: number | null): string {
  if (seconds == null) return "—";
  if (seconds < 1) return `${Math.round(seconds * 1000)}ms`;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const totalMinutes = Math.floor(seconds / 60);
  const remSeconds = Math.round(seconds % 60);
  if (totalMinutes < 60) return `${totalMinutes}m ${remSeconds}s`;
  const hours = Math.floor(totalMinutes / 60);
  const remMinutes = totalMinutes % 60;
  return `${hours}h ${remMinutes}m`;
}

/**
 * Formats a whole-second elapsed duration: `< 60s → "Ns"`, `< 1h → "Nm Ns"`,
 * else `"Nh Nm"`. Distinct from {@link formatDuration} (which renders
 * sub-second precision like "4.2s"): callers that measure in whole seconds
 * (e.g. an analysis run's start→finish span) read cleaner as "47s" / "2m 7s"
 * than as the unscannable raw second count "127s".
 * @param secs - Whole-second elapsed duration (non-negative).
 */
export function formatElapsedSeconds(secs: number): string {
  // Floor to whole seconds and clamp negatives (clock skew / out-of-order
  // timestamps) so a fractional or negative input never renders e.g. "2m 7.5s"
  // or "-5s". Callers pass whole seconds today, but this keeps the util safe.
  const total = Math.max(0, Math.floor(secs));
  if (total < 60) return `${total}s`;
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  if (minutes < 60) return `${minutes}m ${seconds}s`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m`;
}

/**
 * Formats a document count with a correctly pluralised noun.
 * @param count - The number of documents
 * @returns e.g. "1 document" or "3 documents"
 */
export function pluralizeDocuments(count: number): string {
  return `${count} document${count === 1 ? "" : "s"}`;
}

/**
 * Formats a place count with a correctly pluralised noun (corpus map, #1821).
 * @param count - The number of geographic places
 * @returns e.g. "1 place" or "12 places"
 */
export function pluralizePlaces(count: number): string {
  return `${count} place${count === 1 ? "" : "s"}`;
}

/**
 * Formats a date string into a relative time description.
 * @param dateString - ISO date string to format
 * @returns Relative time string like "Just now", "5 hours ago", "3 days ago", or empty string if invalid
 */
export function formatRelativeTime(dateString?: string | null): string {
  if (!dateString) return "";
  const date = new Date(dateString);
  if (isNaN(date.getTime())) return "";
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffHours = diffMs / TIME_UNITS.MS_PER_HOUR;
  const diffDays = diffHours / TIME_UNITS.HOURS_PER_DAY;

  if (diffHours < 1) return "Just now";
  if (diffHours < TIME_UNITS.HOURS_PER_DAY) {
    return `${Math.floor(diffHours)} hours ago`;
  }
  if (diffDays < TIME_UNITS.DAYS_PER_WEEK) {
    return `${Math.floor(diffDays)} days ago`;
  }
  return date.toLocaleDateString();
}

/**
 * Formats a date string into a compact relative time description.
 * Used in activity feeds and compact displays.
 * @param dateString - ISO date string to format
 * @returns Compact time string like "5h ago", "3d ago", or empty string if invalid
 */
export function formatCompactRelativeTime(dateString?: string | null): string {
  if (!dateString) return "";
  const date = new Date(dateString);
  if (isNaN(date.getTime())) return "";
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSecs = Math.floor(diffMs / TIME_UNITS.MS_PER_SECOND);
  const diffMins = Math.floor(diffSecs / 60);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / TIME_UNITS.HOURS_PER_DAY);

  if (diffDays > TIME_UNITS.DAYS_PER_MONTH) {
    return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  } else if (diffDays > 0) {
    return `${diffDays}d ago`;
  } else if (diffHours > 0) {
    return `${diffHours}h ago`;
  } else if (diffMins > 0) {
    return `${diffMins}m ago`;
  } else {
    return "Just now";
  }
}

/**
 * Extracts initials from a name or email for avatar display.
 * Handles email addresses by taking first letter before @.
 * @param name - Name or email to extract initials from
 * @returns 1-2 character initial string, or "U" if no name provided
 */
export function getInitials(name?: string | null): string {
  if (!name) return "U";
  // Handle email addresses - take first letter before @
  if (name.includes("@")) {
    return name.split("@")[0].charAt(0).toUpperCase();
  }
  return name
    .split(" ")
    .map((n) => n[0])
    .join("")
    .toUpperCase()
    .slice(0, 2);
}

/**
 * Formats a date string into a short localized format.
 * @param dateString - ISO date string to format
 * @returns Formatted date string like "Oct 5, 2023", or empty string if invalid
 */
export function formatShortDate(dateString?: string | null): string {
  if (!dateString) return "";
  const date = new Date(dateString);
  if (isNaN(date.getTime())) return "";
  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

/** Formats a date string as a localized date+time, or "—" when empty. */
export function formatDateTime(value?: string | null): string {
  return value ? new Date(value).toLocaleString() : "—";
}

/**
 * Formats a setting name into a human-readable label.
 * Uses the description if provided, otherwise converts snake_case to Title Case.
 * @param name - The setting name (e.g., "api_key")
 * @param description - Optional description to use as the label
 * @returns Formatted label (e.g., "API Key" or the provided description)
 */
export function formatSettingLabel(
  name: string,
  description?: string | null
): string {
  if (description && description.trim()) {
    return description.trim();
  }
  return name.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

/**
 * Truncate a string at a code-point boundary, appending an ellipsis if needed.
 *
 * Uses `Array.from` to iterate code points rather than UTF-16 code units so
 * that surrogate pairs (emoji / non-BMP characters) are never split.  The fast
 * path (`s.length <= maxLen`) skips the `Array.from` allocation entirely since
 * UTF-16 length is always >= code-point count.
 */
export function truncateAtCodePoint(s: string, maxLen: number): string {
  if (s.length <= maxLen) return s;
  const cps = Array.from(s);
  return cps.length > maxLen ? cps.slice(0, maxLen).join("") + "\u2026" : s;
}

// Strip Markdown / HTML markup for plaintext preview rendering.
// Order-sensitive: fenced blocks must run before inline code so triple
// backticks aren't mistakenly stripped as inline pairs.
export function stripMarkdown(input?: string | null): string {
  if (!input) return "";
  return input
    .replace(/```[\s\S]*?```/g, " ") // fenced code blocks
    .replace(/`([^`]*)`/g, "$1") // inline code
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, "$1") // images → alt text
    .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1") // links → label
    .replace(/<\/?[a-zA-Z][^>]*>/g, " ") // HTML tags
    .replace(/&[a-z0-9#]+;/gi, " ") // HTML entities
    .replace(/^\s{0,3}#{1,6}\s+/gm, "") // ATX headers
    .replace(/^\s{0,3}>\s?/gm, "") // blockquote markers
    .replace(/^\s*[-*+]\s+/gm, "") // unordered list bullets
    .replace(/^\s*\d+\.\s+/gm, "") // ordered list markers
    .replace(/(\*\*|__)(.*?)\1/g, "$2") // bold
    .replace(/(\*|_)(.*?)\1/g, "$2") // italic
    .replace(/~~(.*?)~~/g, "$1") // strikethrough
    .replace(/\s+/g, " ")
    .trim();
}

export function formatCellValue(
  data: string | number | boolean | Record<string, unknown> | null | undefined
): string {
  if (data === null || data === undefined) return "\u2014";
  if (typeof data === "boolean") return data ? "Yes" : "No";
  if (typeof data === "object") {
    return truncateAtCodePoint(
      JSON.stringify(data),
      EXTRACT_GRID_CELL_TRUNCATE_LENGTH
    );
  }
  // Apply the same code-point-safe truncation to raw string/number values
  // so that unexpectedly long cell contents don't blow out the table layout.
  return truncateAtCodePoint(String(data), EXTRACT_GRID_CELL_TRUNCATE_LENGTH);
}

/**
 * Acronyms that should stay fully upper-cased when humanizing a SCREAMING_SNAKE
 * label token (e.g. "SEC_HEADER" -> "SEC Header", not "Sec Header").
 *
 * Deliberately a starting set, not an exhaustive one — extend it here as new
 * pipeline label prefixes emerge (an unlisted acronym degrades gracefully to
 * Title Case, e.g. "Gdpr", so misses are cosmetic).
 */
const LABEL_ACRONYMS = new Set([
  "SEC",
  "OC",
  "IPO",
  "SPAC",
  "LLC",
  "AI",
  "API",
  "URL",
  "ID",
  "PII",
  "US",
  "EU",
  "FTS",
]);

/**
 * Humanize a machine-style annotation-label name for display in user-facing
 * "insight" surfaces. SCREAMING_SNAKE_CASE provider/pipeline tokens
 * ("SEC_HEADER", "EXHIBIT_REFERENCE") read as jargon; this splits on
 * underscores and Title-Cases each word while preserving known acronyms.
 *
 * Labels that already look human are left untouched: anything without an
 * underscore — "S-1", "10-K", "Exhibit", "Risk Factor", "Contract Clause" —
 * is returned verbatim, so we only rewrite the genuinely machine-shaped tokens.
 */
export function humanizeLabel(label: string): string {
  if (!label || !label.includes("_")) return label;
  return label
    .split("_")
    .filter((word) => word.length > 0)
    .map((word) =>
      LABEL_ACRONYMS.has(word.toUpperCase())
        ? word.toUpperCase()
        : word.charAt(0).toUpperCase() + word.slice(1).toLowerCase()
    )
    .join(" ");
}

const LAW_ACRONYM_SET = new Set<string>(LAW_AUTHORITY_ACRONYMS);

/**
 * Display form for a canonical law key from the reference web:
 * "dgcl:203" → "DGCL § 203", "securities-act:4(a)(2)" → "Securities Act
 * § 4(a)(2)". Acronym authority words upper-case; the rest title-case. Used
 * for governance-graph ghost nodes and the wanted-authorities backlog.
 */
export function formatCanonicalLawKey(key: string): string {
  const [prefix, section] = key.split(":", 2);
  const display = prefix
    .split("-")
    .map((part) =>
      LAW_ACRONYM_SET.has(part)
        ? part.toUpperCase()
        : part.charAt(0).toUpperCase() + part.slice(1)
    )
    .join(" ");
  return section ? `${display} § ${section}` : display;
}

/**
 * Display form for an authority jurisdiction code:
 * "us-de" → "U.S. — DE", "us-federal" → "U.S. Federal", other codes upper-cased.
 *
 * Returns `null` when the code is absent so each caller picks its own
 * placeholder (table cells render `?? "—"`; the governance graph renders
 * `?? ""` or conditionally hides the field). Shared by the Authority Sources
 * monitor and the governance-graph explorer so a code never renders two ways.
 */
export function formatJurisdiction(j?: string | null): string | null {
  if (!j) return null;
  if (j === "us-federal") return "U.S. Federal";
  const m = j.match(/^us-([a-z]{2})$/);
  if (m) return `U.S. — ${m[1].toUpperCase()}`;
  return j.toUpperCase();
}

/**
 * Capitalize the first letter and de-snake/-kebab the rest:
 * "deferred_cap" → "Deferred cap", "us-code" → "Us code". Returns `null` for
 * empty input so callers choose their own placeholder. Shared by the Authority
 * Sources monitor and the governance-graph explorer (CLAUDE.md DRY).
 */
export function titleCase(s?: string | null): string | null {
  return s
    ? s.charAt(0).toUpperCase() + s.slice(1).replace(/[_-]/g, " ")
    : null;
}

/**
 * Compact currency formatting for collection data-story / poster surfaces.
 * Values ≥ $10M drop the decimal ($15M); $1M–$10M keep one ($1.5M); thousands
 * round to $K; below that to whole dollars.
 * @param n - A dollar amount
 * @returns A short currency string like "$15M", "$1.5M", "$250K", or "$900"
 */
export function formatCompactMoney(n: number): string {
  if (n >= 1_000_000)
    return `$${(n / 1_000_000).toFixed(n >= 10_000_000 ? 0 : 1)}M`;
  if (n >= 1_000) return `$${Math.round(n / 1_000)}K`;
  return `$${Math.round(n)}`;
}

/**
 * Parse a leading ISO date (YYYY-MM-DD…) to epoch milliseconds (UTC midnight).
 * Tolerates surrounding whitespace and trailing time components.
 * @param d - A date-ish string
 * @returns Epoch ms, or null when there is no parseable leading ISO date
 */
export function parseIsoDateMs(d: string | null | undefined): number | null {
  if (!d) return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(d.trim());
  if (!m) return null;
  const t = Date.parse(`${m[1]}-${m[2]}-${m[3]}T00:00:00Z`);
  return Number.isNaN(t) ? null : t;
}
