export const VERSION_TAG = "v3.0.0.rc1";
export const MOBILE_VIEW_BREAKPOINT = 600;
// Tablet breakpoint - used for sidebar collapse behavior (larger than mobile)
export const TABLET_BREAKPOINT = 768;
// Desktop breakpoint - minimum width for desktop-only features (TABLET_BREAKPOINT + 1)
export const DESKTOP_BREAKPOINT = 769;

// Mention preview character limit (Issue #689)
// Used for truncating annotation text in mention chips and pickers
export const MENTION_PREVIEW_LENGTH = 24;

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

// Conversation type constants (matches backend ConversationTypeChoices)
export const CONVERSATION_TYPE = {
  CHAT: "CHAT",
  THREAD: "THREAD",
} as const;

export type ConversationType =
  (typeof CONVERSATION_TYPE)[keyof typeof CONVERSATION_TYPE];

// Document relationship pagination limits
export const DOCUMENT_RELATIONSHIP_PAGINATION_LIMIT = 50;
export const DOCUMENT_RELATIONSHIP_TOC_LIMIT = 500;
// Limit for fetching corpus documents in TOC (includes standalone docs)
// Backend enforces max 100 records per page on documents connection
export const CORPUS_DOCUMENTS_TOC_LIMIT = 100;

// Document search/picker limits
export const DOCUMENT_PICKER_SEARCH_LIMIT = 20;

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
  /** Minimum width for component cards in grid layout (in pixels) */
  COMPONENT_GRID_MIN_WIDTH: 140,
  /** Primary accent color used in pipeline configuration UI */
  PRIMARY_ACCENT_COLOR: "#6366f1",
  /** Height for pipeline connector line (in pixels) */
  CONNECTOR_HEIGHT_PX: 24,
  /** Minimum height for component cards (in pixels) */
  COMPONENT_CARD_MIN_HEIGHT_PX: 120,
  /** Maximum allowed secrets payload size (in bytes) */
  MAX_SECRET_SIZE_BYTES: 10240,
  /** Width of the left-side flow channel in the pipeline view (in pixels) */
  CHANNEL_WIDTH_PX: 36,
  /** Width of the horizontal connector arm from channel to stage card (in pixels) */
  CONNECTOR_ARM_WIDTH_PX: 28,
  /** Diameter of the junction node circles on the channel (in pixels) */
  JUNCTION_SIZE_PX: 16,
  /** Vertical spacing between stage rows in the pipeline view (in pixels) */
  STAGE_SPACING_PX: 48,
  /** Number of flow particles in the channel animation */
  FLOW_PARTICLE_COUNT: 8,
} as const;

/**
 * Legacy MIME type for plain text files used in some parts of the system.
 * Standard type is "text/plain", but some documents use this non-standard value.
 */
export const LEGACY_TEXT_MIME_TYPE = "application/txt";

// Supported MIME types for pipeline configuration
export const SUPPORTED_MIME_TYPES = [
  { value: "application/pdf", label: "PDF", shortLabel: "PDF" },
  { value: "text/plain", label: "Plain Text", shortLabel: "TXT" },
  {
    value:
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
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
