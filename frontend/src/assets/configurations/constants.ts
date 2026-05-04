import { OS_LEGAL_COLORS } from "./osLegalStyles";

export const VERSION_TAG = "v3.0.0.rc1";
export const MOBILE_VIEW_BREAKPOINT = 600;
// Tablet breakpoint - used for sidebar collapse behavior (larger than mobile)
export const TABLET_BREAKPOINT = 768;
// Desktop breakpoint - minimum width for desktop-only features (TABLET_BREAKPOINT + 1)
export const DESKTOP_BREAKPOINT = 769;

// Icon defaults
/** Default pixel size for DynamicIcon width and height */
export const DYNAMIC_ICON_DEFAULT_SIZE = 16;
/** Icon size for FilterTabItem icons in tab bars */
export const FILTER_TAB_ICON_SIZE = 14;

// Mention search configuration
// Debounce delay before firing search queries (ms)
export const MENTION_SEARCH_DEBOUNCE_MS = 300;
// Minimum characters required before triggering a search
export const MENTION_SEARCH_MIN_CHARS = 2;
// Mention preview character limit (Issue #689)
// Used for truncating annotation text in mention chips and pickers
export const MENTION_PREVIEW_LENGTH = 24;

// CAML article configuration
// The conventional document title for corpus articles (like GitHub's README)
export const CAML_ARTICLE_FILENAME = "Readme.CAML";
// MIME type used by the backend for CAML/Markdown documents
export const MARKDOWN_MIME_TYPE = "text/markdown";

// Label/UI colors
// Default neutral gray color (Tailwind slate-400) used for inactive/placeholder states
export const DEFAULT_LABEL_COLOR = "94a3b8";
// Primary teal color used for new label creation
export const PRIMARY_LABEL_COLOR = "0F766E";
// Default color for agent messages when no badge color is configured
export const DEFAULT_AGENT_COLOR = "#4A90E2";
// Color for text block deep link highlights (teal, distinct from chat source blue #5C7C9D)
export const TEXT_BLOCK_HIGHLIGHT_COLOR = "#0EA5E9";
// Sentinel ID used to inject text block deep links as virtual chat sources
// in the TxtAnnotator (so they render with the same highlight machinery).
export const TEXT_BLOCK_DEEPLINK_ID = "__text_block_deeplink__";

// File size constants for formatting
export const FILE_SIZE = {
  BYTES_PER_KB: 1024,
  BYTES_PER_MB: 1024 * 1024,
  BYTES_PER_GB: 1024 * 1024 * 1024,
} as const;

// Time unit constants for relative time formatting
export const TIME_UNITS = {
  MS_PER_SECOND: 1000,
  MS_PER_MINUTE: 1000 * 60,
  MS_PER_HOUR: 1000 * 60 * 60,
  MS_PER_DAY: 1000 * 60 * 60 * 24,
  HOURS_PER_DAY: 24,
  DAYS_PER_WEEK: 7,
  DAYS_PER_MONTH: 30,
} as const;

// Document view mode constants
export const VIEW_MODES = {
  GRID: "grid",
  LIST: "list",
  COMPACT: "compact",
} as const;

export type ViewMode = (typeof VIEW_MODES)[keyof typeof VIEW_MODES];

// Document status filter constants
export const STATUS_FILTERS = {
  ALL: "all",
  PROCESSED: "processed",
  PROCESSING: "processing",
} as const;

export type StatusFilter = (typeof STATUS_FILTERS)[keyof typeof STATUS_FILTERS];

// Context menu layout constants
/** Minimum gap (px) between context menu edges and viewport edges */
export const CONTEXT_MENU_VIEWPORT_PADDING = 8;

// Selection action menu approximate dimensions (used for viewport clamping)
export const SELECTION_MENU = {
  APPROX_WIDTH: 200,
  APPROX_HEIGHT: 200,
} as const;

// Debounce timing constants
export const DEBOUNCE = {
  SEARCH_MS: 1000,
  EXTRACT_SEARCH_MS: 500,
  CLICK_OUTSIDE_DELAY_MS: 100,
  CORPUS_SEARCH_MS: 400,
  CORPUS_SEARCH_MAX_WAIT_MS: 1000,
  /** Debounce time for metadata cell auto-save */
  METADATA_SAVE_MS: 1500,
} as const;

// Upload constraints
export const UPLOAD = {
  /** Maximum file size in bytes (100MB) */
  MAX_FILE_SIZE_BYTES: 100 * 1024 * 1024,
  /** Maximum file size display string */
  MAX_FILE_SIZE_DISPLAY: "100MB",
  /** Progress percentage shown while bulk upload is in flight (before completion) */
  BULK_PROGRESS_INITIAL: 50,
  /** Maximum number of corpuses to show in the inline selector preview */
  CORPUS_PREVIEW_LIMIT: 5,
} as const;

// Document metadata constraints
export const DOCUMENT_METADATA = {
  /** Maximum title length in characters */
  MAX_TITLE_LENGTH: 255,
  /** Maximum description length in characters */
  MAX_DESCRIPTION_LENGTH: 2000,
  /** Maximum slug length in characters */
  MAX_SLUG_LENGTH: 100,
} as const;

// Polling constants (legacy - most polling replaced by WebSocket notifications)
export const POLLING = {
  DOCUMENT_PROCESSING_INTERVAL_MS: 15000,
  DOCUMENT_PROCESSING_TIMEOUT_MS: 600000,
} as const;

// Extract status constants
export const EXTRACT_STATUS = {
  RUNNING: "Running",
  COMPLETED: "Completed",
  FAILED: "Failed",
  NOT_STARTED: "Not Started",
} as const;

export type ExtractStatus =
  (typeof EXTRACT_STATUS)[keyof typeof EXTRACT_STATUS];

// Extract chip color mapping
export const EXTRACT_STATUS_COLORS = {
  [EXTRACT_STATUS.RUNNING]: "info",
  [EXTRACT_STATUS.COMPLETED]: "success",
  [EXTRACT_STATUS.FAILED]: "error",
  [EXTRACT_STATUS.NOT_STARTED]: "default",
} as const;

// Tool usage UI constants (used by chat ToolUsageIndicator)
export const TOOL_UNKNOWN_LABEL = "Unknown Tool";

// Tool popover positioning constants (used by ToolUsageIndicator portal)
/** Z-index for the fixed-position tool popover rendered via portal */
export const POPOVER_Z_INDEX = 100002;

// Z-index layer constants for consistent stacking
// Note: @os-legal/ui Modal uses z-index 400, so in-page overlays must stay below that.
export const Z_INDEX = {
  /** In-page loading overlays (position: absolute within a relative parent) */
  OVERLAY: 10,
  /** Document header — establishes stacking context above content when backdrop-filter is active.
   *  Does not spatially overlap the sidebar (flex column layout), so 50 < sidebar's 90 is fine. */
  HEADER: 50,
  /** Standard dropdown overlays (pickers, menus) */
  DROPDOWN: 100,
  /** Modal-level overlays (dialogs, full-screen) */
  MODAL: 1000,
  /** Full-viewport transparent overlay behind context menus (click-outside capture) */
  CONTEXT_MENU_OVERLAY: 9998,
  /** Floating context menu container */
  CONTEXT_MENU: 9999,
} as const;
/** Gap in pixels between the badge and the popover */
export const POPOVER_GAP = 8;
/**
 * Maximum height of the tool popover in pixels.
 * Must match ToolPopoverBody max-height (400px) + header height (~100px).
 * If ToolPopoverBody max-height changes, update this value accordingly.
 */
export const POPOVER_MAX_HEIGHT = 500;

// Conversation type constants (matches backend ConversationTypeChoices)
export const CONVERSATION_TYPE = {
  CHAT: "CHAT",
  THREAD: "THREAD",
} as const;

// WebSocket error type constants (matches backend WS_ERROR_* constants)
export const WS_ERROR_CONTEXT_EXHAUSTED = "CONTEXT_EXHAUSTED";

export type ConversationType =
  (typeof CONVERSATION_TYPE)[keyof typeof CONVERSATION_TYPE];

// Document relationship pagination limits
export const DOCUMENT_RELATIONSHIP_PAGINATION_LIMIT = 50;
export const DOCUMENT_RELATIONSHIP_TOC_LIMIT = 500;
// Limit for fetching corpus documents in TOC (includes standalone docs)
// Backend enforces max 100 records per page on documents connection
export const CORPUS_DOCUMENTS_TOC_LIMIT = 100;

// Document annotation index (within-document TOC)
// Keep in sync with opencontractserver/constants/annotations.py
export const DOCUMENT_ANNOTATION_INDEX_LIMIT = 500;
export const DOCUMENT_ANNOTATION_INDEX_MAX_DEPTH = 6;
// Built-in annotation label names (OC_ namespace)
// Keep in sync with opencontractserver/constants/annotations.py
export const STRUCTURAL_LABEL_PREFIX = "OC_";
export const OC_SECTION_LABEL = "OC_SECTION";

// Document search/picker limits
export const DOCUMENT_PICKER_SEARCH_LIMIT = 20;

// Discover cross-content search (DiscoverSearchResults view)
/** Number of results shown per section on the "All" tab (preview mode). */
export const DISCOVER_SEARCH_ALL_TAB_PREVIEW = 5;
/** Number of results shown when an entity tab is selected. */
export const DISCOVER_SEARCH_ENTITY_TAB_LIMIT = 25;
/** Debounce (ms) before firing cross-content search queries. */
export const DISCOVER_SEARCH_DEBOUNCE_MS = 250;

// Mutation batching
export const MUTATION_BATCH_SIZE = 10;

// Annotation pagination constants
export const ANNOTATION_PAGINATION = {
  /** Number of annotations to load per page in browse mode */
  PAGE_SIZE: 20,
  /** Number of results per semantic search request */
  SEMANTIC_SEARCH_LIMIT: 20,
  /** Maximum accumulated semantic search results before capping */
  MAX_SEMANTIC_RESULTS: 500,
} as const;

// Mention type configuration
// Defines which mention types have active navigation routes
// When a route is added for a type, set navigable: true
export const MENTION_TYPES = {
  user: {
    navigable: true,
    label: "User",
  },
  corpus: {
    navigable: true,
    label: "Corpus",
  },
  document: {
    navigable: true,
    label: "Document",
  },
  annotation: {
    navigable: true,
    label: "Annotation",
  },
  agent: {
    navigable: false, // No agent detail page yet
    label: "AI Agent",
  },
  source: {
    navigable: true,
    label: "Source",
  },
} as const;

export type MentionType = keyof typeof MENTION_TYPES;

// Pipeline configuration UI constants
export const PIPELINE_UI = {
  /** Default icon size for pipeline component icons (in pixels) */
  ICON_SIZE: 48,
  /** Primary accent color used in pipeline configuration UI */
  PRIMARY_ACCENT_COLOR: "#6366f1",
  /** Maximum allowed secrets payload size (in bytes) */
  MAX_SECRET_SIZE_BYTES: 10240,
} as const;

/**
 * Legacy MIME type for plain text files used in some parts of the system.
 * Standard type is "text/plain", but some documents use this non-standard value.
 */
export const LEGACY_TEXT_MIME_TYPE = "application/txt";

/**
 * Standard MIME type for DOCX (Word) documents.
 */
export const DOCX_MIME_TYPE =
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document";

/**
 * Maximum number of DOCX byte arrays to cache in memory.
 * Oldest entry is evicted when the limit is reached.
 */
export const DOCX_CACHE_MAX_ENTRIES = 3;

/**
 * @deprecated Use the `supportedMimeTypes` GraphQL query instead.
 * Retained as a static fallback for components that haven't migrated yet.
 */
export const SUPPORTED_MIME_TYPES = [
  { value: "application/pdf", label: "PDF", shortLabel: "PDF" },
  { value: "text/plain", label: "Plain Text", shortLabel: "TXT" },
  {
    value: DOCX_MIME_TYPE,
    label: "Word Document",
    shortLabel: "DOCX",
  },
] as const;

/**
 * Lookup map from full MIME type to short label (e.g., "text/plain" → "TXT").
 * Used for matching component supportedFileTypes which use short forms.
 */
export const MIME_TO_SHORT_LABEL: Record<string, string> = Object.fromEntries(
  SUPPORTED_MIME_TYPES.map((m) => [m.value, m.shortLabel])
);

// Message count badge color constants (used by chatUtils.ts getMessageCountColor)
export const MESSAGE_COUNT_COLORS = {
  /** Zero-count badge gradient start */
  ZERO_GRADIENT_START: "#EDF2F7",
  /** Zero-count badge gradient end */
  ZERO_GRADIENT_END: "#E2E8F0",
  /** Zero-count badge text color */
  ZERO_TEXT: "#4A5568",
  /** Primary gradient color (blue) - RGB components */
  PRIMARY_R: 43,
  PRIMARY_G: 108,
  PRIMARY_B: 176,
  /** Secondary gradient color (dark blue) - RGB components */
  SECONDARY_R: 44,
  SECONDARY_G: 82,
  SECONDARY_B: 130,
  /** Base opacity for gradient start */
  BASE_ALPHA_START: 0.7,
  /** Intensity multiplier for gradient start alpha */
  INTENSITY_ALPHA_START: 0.3,
  /** Base opacity for gradient end */
  BASE_ALPHA_END: 0.8,
  /** Intensity multiplier for gradient end alpha */
  INTENSITY_ALPHA_END: 0.2,
  /** Base badge opacity */
  BASE_OPACITY: 0.8,
  /** Intensity multiplier for badge opacity */
  INTENSITY_OPACITY: 0.2,
  /** Intensity threshold for switching text color to light */
  LIGHT_TEXT_THRESHOLD: 0.3,
  /** Light text color (used on dark backgrounds) */
  LIGHT_TEXT: "white",
  /** Dark text color (used on light backgrounds) */
  DARK_TEXT: "#1A202C",
  /** Zero-count badge opacity */
  ZERO_OPACITY: 0.9,
} as const;

// Warning color for partially supported file types (amber/yellow)
export const PARTIALLY_SUPPORTED_WARNING_COLOR = "#D69E2E";

// Extract grid embed display limits
/** Maximum character length for cell values before truncation in ExtractGridEmbed. */
export const EXTRACT_GRID_CELL_TRUNCATE_LENGTH = 100;
/**
 * Server-side cap on the number of datacells fetched for an extract grid
 * embed. Passed as the `limit` argument to `fullDatacellList` so the payload
 * is bounded even for extracts with hundreds of documents and columns. When
 * the extract has more cells than this, the component displays a
 * "showing N of M" indicator and the overflow rows are omitted.
 *
 * Sized so that typical use cases (a few dozen documents x <= 20 columns)
 * fit comfortably without truncation. Resolves #1204.
 *
 * IMPORTANT: If you change this value, update the backend constant
 * ``MAX_FULL_DATACELL_LIST_LIMIT`` in
 * ``opencontractserver/constants/extracts.py`` at the same time.
 * An automated CI sync-check is tracked in issue #1256.
 */
export const EXTRACT_GRID_EMBED_CELL_LIMIT = 500;
/**
 * Maximum number of document rows rendered in an ExtractGridEmbed. If the
 * fetched (already server-bounded) payload resolves to more rows than this,
 * the table is clipped and a "showing N of M" indicator is displayed. This
 * is a pure display bound — the fetched payload is always bounded by
 * `EXTRACT_GRID_EMBED_CELL_LIMIT` on the server side.
 */
export const EXTRACT_GRID_EMBED_MAX_ROWS = 200;
// Datacell status indicator colors (used in ExtractGridEmbed status dots).
// Values reference OS_LEGAL_COLORS design tokens for consistency.
export const DATACELL_STATUS_COLORS = {
  FAILED: OS_LEGAL_COLORS.danger,
  COMPLETE: OS_LEGAL_COLORS.green,
  PENDING: OS_LEGAL_COLORS.textMuted,
} as const;

// Processing failure UI colors (used in DocumentItem, ModernDocumentItem)
export const FAILURE_COLORS = {
  ICON_BG: "#dc2626",
  BORDER: "#ef4444",
  BORDER_LIGHT: "#fca5a5",
  BORDER_LIGHTER: "#fecaca",
  BG: "#fef2f2",
  BG_OVERLAY: "rgba(254, 226, 226, 0.8)",
  TEXT: "#dc2626",
  TEXT_DARK: "#b91c1c",
  SHADOW: "rgba(220, 38, 38, 0.3)",
} as const;

// Corpus landing page constants
/** Number of recent discussion threads shown on the corpus landing page */
export const RECENT_THREAD_LIMIT = 3;

// Creative Commons license options for corpus licensing.
// SPDX identifiers: https://spdx.org/licenses/
export const LICENSE_OPTIONS = [
  { value: "", label: "No license selected" },
  { value: "CC-BY-4.0", label: "CC BY 4.0 — Attribution" },
  { value: "CC-BY-SA-4.0", label: "CC BY-SA 4.0 — Attribution-ShareAlike" },
  {
    value: "CC-BY-NC-4.0",
    label: "CC BY-NC 4.0 — Attribution-NonCommercial",
  },
  {
    value: "CC-BY-NC-SA-4.0",
    label: "CC BY-NC-SA 4.0 — Attribution-NonCommercial-ShareAlike",
  },
  {
    value: "CC-BY-ND-4.0",
    label: "CC BY-ND 4.0 — Attribution-NoDerivatives",
  },
  {
    value: "CC-BY-NC-ND-4.0",
    label: "CC BY-NC-ND 4.0 — Attribution-NonCommercial-NoDerivatives",
  },
  { value: "CC0-1.0", label: "CC0 1.0 — Public Domain Dedication" },
  { value: "CUSTOM", label: "Custom License" },
] as const;

export type LicenseValue = (typeof LICENSE_OPTIONS)[number]["value"];

/**
 * Known acronyms that should be preserved in display names.
 * Used by getComponentDisplayName to properly capitalize technology names.
 */
export const KNOWN_ACRONYMS: Record<string, string> = {
  openai: "OpenAI",
  modernbert: "ModernBERT",
  bert: "BERT",
  gpt: "GPT",
  llm: "LLM",
  api: "API",
  pdf: "PDF",
  ocr: "OCR",
  nlp: "NLP",
  nlm: "NLM",
};

// Annotation visual styling
/** RGB tuple for the rejected/maroon pulse animation and static state */
export const REJECTED_RGB = { r: 128, g: 0, b: 0 } as const;
/** RGB tuple for the approved/green pulse animation */
export const APPROVED_RGB = { r: 46, g: 204, b: 113 } as const;
/** Border-radius for annotation bounding boxes and label pills */
export const ANNOTATION_BOUNDARY_RADIUS = "6px";
/** Border-radius for individual annotation tokens */
export const ANNOTATION_TOKEN_RADIUS = "4px";

// Annotation boundary box-shadow layers (selected state)
export const BOUNDARY_SHADOW_SELECTED = {
  outerBlur: 14,
  outerSpread: 4,
  outerOpacity: 0.13,
  midBlur: 5,
  midSpread: 1,
  midOpacity: 0.1,
  insetBlur: 8,
  insetSpread: 2,
  insetOpacity: 0.07,
} as const;

// Annotation boundary box-shadow layers (unselected state)
export const BOUNDARY_SHADOW_UNSELECTED = {
  outerBlur: 10,
  outerSpread: 2,
  outerOpacity: 0.07,
  midBlur: 3,
  midSpread: 0,
  midOpacity: 0.05,
  insetBlur: 6,
  insetSpread: 1,
  insetOpacity: 0.04,
} as const;

// Annotation boundary background opacity
export const BOUNDARY_OPACITY_SELECTED = 0.18;
export const BOUNDARY_OPACITY_UNSELECTED = 0.06;

// Token highlight opacity
export const TOKEN_OPACITY_HIGH = 0.38;
export const TOKEN_OPACITY_LOW = 0.22;

// Token shadow
export const TOKEN_SHADOW_BLUR = 4;
export const TOKEN_SHADOW_SPREAD = 1;

// Token expansion (px added around each token to close inter-token gaps)
export const TOKEN_EXPANSION_PX = 1;

// PAWLs coordinate normalization
/** Half a PDF point tolerance for comparing PAWLs vs PDF.js page dimensions */
export const PAWLS_COORDINATE_EPSILON = 0.5;

/**
 * Fraction of page dimensions above which a single token is considered
 * a degenerate page-level element (e.g. full-page image capture from Docling).
 * Such tokens are excluded from annotation overlap detection because they
 * would cause every annotation's bounding box to span the entire page.
 */
export const PAGE_SPANNING_TOKEN_THRESHOLD = 0.9;

// Compact annotation JSON v2 safety limits
/** Maximum span for a single range segment (safety guard). */
export const COMPACT_JSON_MAX_RANGE_SPAN = 10_000;
/** Maximum total tokens across all pages (safety guard). */
export const COMPACT_JSON_MAX_TOTAL_TOKENS = 50_000;

// Corpus action template picker dropdown width (px)
export const PICKER_DROPDOWN_WIDTH = 380;

// Minimum left offset (px) to prevent dropdown from going off-screen
export const PICKER_DROPDOWN_VIEWPORT_PADDING = 8;

// Modal content layout constants
/** Maximum height for scrollable modal body content (e.g. document picker) */
export const MODAL_BODY_MAX_HEIGHT = "70vh";

// Corpus action trigger display labels
// Maps backend trigger enum values (lowercase) to user-facing short labels
export const TRIGGER_LABELS: Record<string, string> = {
  add_document: "On Add",
  edit_document: "On Edit",
  new_thread: "On Thread",
  new_message: "On Message",
} as const;

// Default agent task instructions used when creating a thread-moderation
// CorpusAction (rendered as the placeholder/initial value in the modal).
export const DEFAULT_MODERATOR_INSTRUCTIONS = `You are a thread moderator for this corpus. Your role is to:
1. Monitor discussion threads and messages for policy compliance
2. Take appropriate moderation actions when needed
3. Respond helpfully to user questions when appropriate

You have access to thread context, messages, and moderation tools. Use them judiciously.`;

// Default agent task instructions used when creating a document-processing
// CorpusAction (rendered as the initial value when an add/edit document
// trigger is selected).
export const DEFAULT_DOCUMENT_AGENT_INSTRUCTIONS =
  "You are a document processing agent for this corpus.";
