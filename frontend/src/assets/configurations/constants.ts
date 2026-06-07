import { OS_LEGAL_COLORS } from "./osLegalStyles";

// Rendered in the NavBar version pill. v3.0.0.rc1 ships the cite rebrand
// as a release candidate; the GA cut will drop the suffix.
export const VERSION_TAG = "v3.0.0.rc1";
// Small-mobile breakpoint - used by chat widget styles for the tightest
// viewports (very small phones), where chat-bubble arrows are removed and
// font sizes shrink. Distinct from MOBILE_VIEW_BREAKPOINT (600).
export const SMALL_MOBILE_BREAKPOINT = 480;
export const MOBILE_VIEW_BREAKPOINT = 600;
// Tablet breakpoint - used for sidebar collapse behavior (larger than mobile)
export const TABLET_BREAKPOINT = 768;
// Desktop breakpoint - minimum width for desktop-only features (TABLET_BREAKPOINT + 1)
export const DESKTOP_BREAKPOINT = 769;
// Tablet-landscape breakpoint - point where two-pane layouts compress their list
// pane (e.g. extract split view, thread search) before fully collapsing at TABLET_BREAKPOINT.
export const TABLET_LANDSCAPE_BREAKPOINT = 1024;
// Cookie consent modal collapses its two-column data grid below this width.
export const COOKIE_CONSENT_GRID_BREAKPOINT = 720;

// Minimum table widths feeding the `ScrollableTableWrapper` $minWidth prop on
// each admin/badges view. Below the wrapper's parent width the table scrolls
// horizontally; above it the table fills naturally. Tuned per-table so columns
// stay readable instead of column-crushed on narrow viewports.
export const BADGE_TABLE_MIN_WIDTH_PX = 600;
export const AGENT_TABLE_MIN_WIDTH_PX = 720;
export const WORKER_TABLE_MIN_WIDTH_PX = 760;
// Ingestion-monitor (admin) tables: the document/worker-queue table is the
// widest (creator, title, type, size, pages, status, timings) and the
// import-batch table a touch narrower.
export const INGESTION_TABLE_MIN_WIDTH_PX = 920;
export const IMPORT_BATCH_TABLE_MIN_WIDTH_PX = 860;

// Default page size for the admin Ingestion Monitor list queries. Mirrors the
// backend ADMIN_INGESTION_DEFAULT_PAGE_SIZE so Prev/Next paging lines up with
// the server's clamping.
export const INGESTION_MONITOR_PAGE_SIZE = 50;

// Icon defaults
/** Default pixel size for DynamicIcon width and height */
export const DYNAMIC_ICON_DEFAULT_SIZE = 16;
/** Icon size for FilterTabItem icons in tab bars */
export const FILTER_TAB_ICON_SIZE = 14;

// Document zoom bounds
// Shared by every zoom surface (ZoomControls, useZoomManager wheel/keyboard/
// pinch handlers, and the mobile fit-to-width hook) so the clamp is defined
// in exactly one place.
/** Minimum document zoom level (50%). */
export const ZOOM_MIN = 0.5;
/** Maximum document zoom level (400%). */
export const ZOOM_MAX = 4;
/**
 * Total horizontal breathing room (px) the shared fit-to-width helper
 * reserves off the viewer container width so the fitted page does not
 * butt up against the container edges. Used by both the desktop
 * initial-zoom calculation in PDFPage and the mobile fit-to-width hook
 * via ``utils/pdfZoom.ts``. Leaving this cushion prevents horizontal
 * overflow on narrower laptop viewports (see issue #1736).
 */
export const FIT_WIDTH_MARGIN = 16;

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
  /** Generic debounce for client-side list search boxes (extracts, research, …). */
  LIST_SEARCH_MS: 500,
  CLICK_OUTSIDE_DELAY_MS: 100,
  CORPUS_SEARCH_MS: 400,
  CORPUS_SEARCH_MAX_WAIT_MS: 1000,
  /** Debounce time for metadata cell auto-save */
  METADATA_SAVE_MS: 1500,
} as const;

// Upload constraints
export const UPLOAD = {
  /**
   * Maximum single-document size in bytes (2GB). Files larger than
   * ``CHUNK_THRESHOLD_BYTES`` are uploaded in chunks (see ``importHttp``),
   * so this is no longer bounded by the 100MB upstream proxy (Cloudflare)
   * request cap. The backend ``MAX_DOCUMENT_IMPORT_SIZE_BYTES`` is the
   * authoritative ceiling and returns 413 above it.
   */
  MAX_FILE_SIZE_BYTES: 2 * 1024 * 1024 * 1024,
  /** Maximum single-document size display string */
  MAX_FILE_SIZE_DISPLAY: "2GB",
  /**
   * Slice size (50MB) for chunked uploads. Must stay below the smallest
   * upstream proxy body limit (Cloudflare caps proxied requests at 100MB);
   * 50MB leaves ~2x headroom for multipart framing. Mirrors the backend
   * ``CHUNKED_UPLOAD_PART_MAX_BYTES`` guard (90MB).
   *
   * NOTE: this MUST stay below the backend ``CHUNKED_UPLOAD_PART_MAX_BYTES``
   * (``config/settings/base.py``); a part larger than that backend cap is
   * rejected with a 413 at ``store_chunk``. Do not widen this past the
   * backend value without bumping it too.
   */
  CHUNK_SIZE_BYTES: 50 * 1024 * 1024,
  /**
   * Files larger than this are uploaded via the chunked endpoints instead
   * of a single request. Equal to one chunk, so anything that would risk
   * the proxy cap is chunked while small files keep the single-shot path.
   */
  CHUNK_THRESHOLD_BYTES: 50 * 1024 * 1024,
  /**
   * How many parts to upload concurrently. The backend serialises writes
   * per ``(session, index)`` and supports idempotent re-upload, so parallel
   * part PUTs are safe; 4 keeps a fat pipe busy without overwhelming the
   * browser's per-host connection pool.
   */
  CHUNK_CONCURRENCY: 4,
  /**
   * Maximum attempts per part before the whole upload aborts. The backend
   * persists parts and accepts idempotent re-upload, so a transient network
   * blip on one part of a long upload can be retried instead of discarding
   * the whole transfer.
   */
  CHUNK_MAX_ATTEMPTS: 3,
  /**
   * Base delay (ms) for exponential backoff between part retries:
   * attempt N waits ``CHUNK_RETRY_BASE_DELAY_MS * 2**(N-1)``.
   */
  CHUNK_RETRY_BASE_DELAY_MS: 500,
  /** Progress percentage shown while bulk upload is in flight (before completion) */
  BULK_PROGRESS_INITIAL: 50,
  /** Maximum number of corpuses to show in the inline selector preview */
  CORPUS_PREVIEW_LIMIT: 5,
  /** Maximum corpus-import / bulk ZIP size in bytes (500MB) */
  MAX_IMPORT_ZIP_BYTES: 500 * 1024 * 1024,
  /** Maximum corpus-import / bulk ZIP size display string */
  MAX_IMPORT_ZIP_DISPLAY: "500MB",
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

// Deep-research report status constants.
// Keys match the backend JobStatus enum values
// (opencontractserver/types/enums.py); values are the display labels.
export const RESEARCH_STATUS = {
  QUEUED: "Queued",
  RUNNING: "Researching",
  COMPLETED: "Completed",
  FAILED: "Failed",
  CANCELLED: "Cancelled",
} as const;

export type ResearchStatusLabel =
  (typeof RESEARCH_STATUS)[keyof typeof RESEARCH_STATUS];

// Research chip color mapping (Chip `color` tokens from @os-legal/ui)
export const RESEARCH_STATUS_COLORS = {
  [RESEARCH_STATUS.QUEUED]: "default",
  [RESEARCH_STATUS.RUNNING]: "info",
  [RESEARCH_STATUS.COMPLETED]: "success",
  [RESEARCH_STATUS.FAILED]: "error",
  [RESEARCH_STATUS.CANCELLED]: "warning",
} as const;

// Poll interval (ms) the research report detail view uses while a job is
// non-terminal. The backend emits no per-step progress events in v1, so the
// view polls the (indexed, creator-only) single-report query for live
// stepCount/lastProgressAt and stops on the terminal WebSocket notification.
export const RESEARCH_REPORT_POLL_INTERVAL_MS = 5000;

// Guardian object-permission string that gates cancelling a research report.
// Centralised here (not inlined) so a typo can't silently disable Cancel for
// every user and any future check on the same model stays consistent.
export const RESEARCH_REPORT_UPDATE_PERMISSION = "update_researchreport";

// Max research prompt length. Mirrors the backend cap
// (opencontractserver/research/constants.py MAX_RESEARCH_PROMPT_CHARS) so the
// UI rejects over-long prompts before the round-trip.
export const MAX_RESEARCH_PROMPT_CHARS = 10000;

// Max research report title length. Mirrors the backend model column
// (opencontractserver/research/models.py ResearchReport.title max_length=255)
// so the UI caps the optional title before the round-trip rather than letting
// the DB silently truncate / the service reject it.
export const MAX_RESEARCH_TITLE_CHARS = 255;

// Tool usage UI constants (used by chat ToolUsageIndicator)
export const TOOL_UNKNOWN_LABEL = "Unknown Tool";

// Tool popover positioning constants (used by ToolUsageIndicator portal)
/** Z-index for the fixed-position tool popover rendered via portal */
export const POPOVER_Z_INDEX = 100002;

// Z-index layer constants for consistent stacking
// Note: @os-legal/ui Modal uses z-index 400, so in-page overlays must stay below that.
//
// The MOBILE_* slots are reserved for floating controls / labels rendered
// into ``document.body`` via ``createPortal`` on mobile — they intentionally
// sit *above* MODAL (so the annotation tools and document FAB can float
// over the DocumentKnowledgeBase fullscreen modal at z-index 3000) but
// *below* the MOBILE_ANNOTATION_LABEL_MODAL slot (so the label picker
// covers the annotation tools when both are visible).
export const Z_INDEX = {
  /** PDF page SelectionLayer — full-page overlay capturing mouse for the
   *  annotator. Sits above the rendered canvas so drag-to-select works. */
  PDF_SELECTION_LAYER: 1,
  /** PDF page NativeLinkLayer — anchors hovering over PDF.js external link
   *  annotations. Must sit above ``PDF_SELECTION_LAYER`` so its
   *  ``pointer-events: auto`` anchors receive clicks first. */
  PDF_NATIVE_LINK_LAYER: 2,
  /** Mobile floating document-controls pill — overlays the viewer's top-right
   *  corner inside ViewerArea's local stacking context, above the rendered
   *  page but below in-page loading overlays. */
  MOBILE_DOC_TOOLBAR_OVERLAY: 5,
  /** In-page loading overlays (position: absolute within a relative parent) */
  OVERLAY: 10,
  /** Document header — establishes stacking context above content when backdrop-filter is active.
   *  Does not spatially overlap the sidebar (flex column layout), so 50 < sidebar's 90 is fine. */
  HEADER: 50,
  /** Standard dropdown overlays (pickers, menus) */
  DROPDOWN: 100,
  /** Modal-level overlays (dialogs, full-screen) */
  MODAL: 1000,
  /** NavBar dropdowns / popovers anchored above the mobile sheet (z-index 1095) */
  NAVBAR_OVERLAY: 1200,
  /** DocumentKnowledgeBase fullscreen modal (set as a CSS variable too — keep in sync). */
  APP_MODAL: 3000,
  /** Children of the DocumentKnowledgeBase fullscreen modal (nested dialogs, popovers). */
  APP_MODAL_CHILD: 3100,
  /** Mobile annotation tools rendered via portal into document.body. */
  MOBILE_ANNOTATION_TOOLS: 3048,
  /** Mobile annotation-label modal — sits above APP_MODAL_CHILD so the label
   *  picker remains tappable even when a nested dialog is open inside the DKB
   *  fullscreen modal. */
  MOBILE_ANNOTATION_LABEL_MODAL: 3150,
  /** Full-viewport transparent overlay behind context menus (click-outside capture) */
  CONTEXT_MENU_OVERLAY: 9998,
  /** Floating context menu container */
  CONTEXT_MENU: 9999,
} as const;
/** Gap in pixels between the badge and the popover */
export const POPOVER_GAP = 8;
/**
 * Bottom offset for the mobile annotation tools floating bar (portalled to
 * document.body). Used inside ``visualViewportAwareBottom`` so the bar lifts
 * above the mobile keyboard / safe-area inset.
 */
export const MOBILE_ANNOTATION_TOOLS_BOTTOM = "1rem";
/**
 * Bottom offset for the FloatingDocumentControls speed dial on desktop.
 * Sits above the page footer / navbar.
 */
export const DESKTOP_FLOATING_CONTROLS_BOTTOM = "7rem";
/**
 * Bottom offset applied by FloatingDocumentControls' narrow-viewport
 * (``max-width: 768px``) media query. Passed through
 * ``visualViewportAwareBottom`` so the controls clear the safe-area inset.
 */
export const MOBILE_FLOATING_CONTROLS_BOTTOM = "6rem";
/**
 * Maximum height of the tool popover in pixels.
 * Must match ToolPopoverBody max-height (400px) + header height (~100px).
 * If ToolPopoverBody max-height changes, update this value accordingly.
 */
export const POPOVER_MAX_HEIGHT = 500;

/**
 * Cap on rendered rows in the mobile Find sheet results list. Searches for
 * common words in long documents can produce hundreds of matches; rendering
 * them all causes frame drops on mobile scroll. The prev/next chevrons and
 * the status counter still operate over the full match set — only the
 * in-sheet list view is truncated.
 */
export const MOBILE_FIND_MAX_VISIBLE_RESULTS = 100;

// Conversation type constants (matches backend ConversationTypeChoices)
export const CONVERSATION_TYPE = {
  CHAT: "CHAT",
  THREAD: "THREAD",
} as const;

// WebSocket error type constants (matches backend WS_ERROR_* constants)
export const WS_ERROR_CONTEXT_EXHAUSTED = "CONTEXT_EXHAUSTED";

// Chat send/scroll tuning constants (used by ChatTray's stream/send handler hooks)
/**
 * Debounce window (ms) for the chat-send lock. After a user-initiated send,
 * the lock stays held for this long to suppress double-fires from rapid
 * Enter presses or duplicate handlers.
 */
export const CHAT_SEND_LOCK_MS = 300;
/**
 * Auto-scroll suppression threshold (px). When the chat container's scrollTop
 * is more than this many pixels above the bottom we consider the user to have
 * intentionally scrolled up and skip the streaming-token auto-scroll so we
 * don't yank them back to the latest message.
 */
export const CHAT_AUTOSCROLL_THRESHOLD_PX = 100;
// Caps the chat message reading column on wide viewports (e.g. corpus chat) so
// lines stay scannable; a no-op on narrow surfaces already below this width.
export const CHAT_MESSAGE_MAX_WIDTH_REM = "60rem";
// User message bubble: solid neutral card surface + border so it reads as a
// distinct card against the near-white messages background (blue stays reserved
// for the assistant's identity).
export const CHAT_USER_MESSAGE_BG = "rgba(237, 240, 244, 0.92)";
export const CHAT_USER_MESSAGE_BORDER = "rgba(203, 210, 219, 0.9)";

export type ConversationType =
  (typeof CONVERSATION_TYPE)[keyof typeof CONVERSATION_TYPE];

// Document relationship pagination limits
export const DOCUMENT_RELATIONSHIP_PAGINATION_LIMIT = 50;
export const DOCUMENT_RELATIONSHIP_TOC_LIMIT = 500;
// Limit for fetching corpus documents in TOC (includes standalone docs)
// Backend enforces max 100 records per page on documents connection
export const CORPUS_DOCUMENTS_TOC_LIMIT = 100;

// Document relationship type / label filters used by the corpus TOC tree.
// Mirrors the backend's `RELATIONSHIP_TYPE_CHOICES` for the "RELATIONSHIP"
// member and the conventional "parent" annotation label text. Used as
// GraphQL variables so the server-side filter restricts the edges to the
// hierarchy-defining rows only.
export const DOCUMENT_RELATIONSHIP_TYPE_RELATIONSHIP = "RELATIONSHIP";
export const DOCUMENT_RELATIONSHIP_LABEL_PARENT = "parent";

// Deep-link to relationship hook: defensive retry interval used when the
// target annotation lives on a page the virtualised PDF renderer hasn't
// materialised yet. Set just longer than a typical page-mount cycle so
// the second pass reliably picks up the newly-registered ref.
export const JUMP_TO_RELATIONSHIP_SCROLL_RETRY_MS = 300;

// Document annotation index (within-document TOC)
// Keep in sync with opencontractserver/constants/annotations.py
export const DOCUMENT_ANNOTATION_INDEX_LIMIT = 500;
export const DOCUMENT_ANNOTATION_INDEX_MAX_DEPTH = 6;
// Built-in annotation label names (OC_ namespace)
// Keep in sync with opencontractserver/constants/annotations.py
export const STRUCTURAL_LABEL_PREFIX = "OC_";
export const OC_SECTION_LABEL = "OC_SECTION";
// Annotations carrying the OC_URL label render as clickable hyperlinks; their
// ``linkUrl`` field is opened on click. Keep in sync with
// opencontractserver/constants/annotations.py.
export const OC_URL_LABEL = "OC_URL";
// Sentinel id used when constructing a placeholder OC_URL ``AnnotationLabel``
// before the server has assigned a real id (e.g. when the user is creating
// a new link annotation from a selection). Surfaced as a named constant so
// downstream code that needs to recognise "this label is still pending"
// has a single source of truth instead of comparing against a raw string.
export const PENDING_OC_URL_LABEL_ID = "__pending_oc_url__";
// Default presentation for the OC_URL label. Mirrors the backend constants
// (``opencontractserver/constants/annotations.py``) so the placeholder used
// before the server has assigned a real label, the renderer's hyperlink
// styling, and the auto-created server-side label all agree.
export const OC_URL_LABEL_COLOR = "#2563EB";

// Geographic annotation conventions — issue #1819.
// Annotations carrying these labels are auto-created by the geocoding
// pipeline (``opencontractserver/utils/geocoding``) and store the resolved
// place (canonical name + lat/lng + admin codes) in ``annotation.data``.
// The map UI (#1820, #1821) reads these labels to drive pin clustering.
// Keep in sync with opencontractserver/constants/annotations.py.
export const OC_COUNTRY_LABEL = "OC_COUNTRY";
export const OC_STATE_LABEL = "OC_STATE";
export const OC_CITY_LABEL = "OC_CITY";

// Geographic label presentation — a coherent dark→light ramp (country deepest,
// city lightest) so a map cluster that mixes label types is legible at small
// zoom levels. Mirrors backend OC_*_LABEL_COLOR constants.
export const OC_COUNTRY_LABEL_COLOR = "#0E3A5F";
export const OC_STATE_LABEL_COLOR = "#1E6091";
export const OC_CITY_LABEL_COLOR = "#3E92CC";

// ---------------------------------------------------------------------------
// Geographic annotation map (Leaflet) — issue #1820
// ---------------------------------------------------------------------------
// The geographic GraphQL queries (globalGeographicAnnotations /
// geographicAnnotationsForCorpus) accept and return label types as the
// LOWERCASE literals below — NOT the OC_*_LABEL annotation-label text. The
// backend reverse-maps OC_COUNTRY -> "country" etc. (see
// GEOCODE_LABEL_TYPE_TO_LABEL_TEXT in
// opencontractserver/annotations/services/geographic_service.py).
export const GEO_LABEL_TYPE_COUNTRY = "country";
export const GEO_LABEL_TYPE_STATE = "state";
export const GEO_LABEL_TYPE_CITY = "city";

// Ordered coarse -> fine. Passed as the ``labelTypes`` query argument and used
// for the client-side zoom-band clustering selection.
export const GEO_LABEL_TYPES = [
  GEO_LABEL_TYPE_COUNTRY,
  GEO_LABEL_TYPE_STATE,
  GEO_LABEL_TYPE_CITY,
] as const;

// The geographic label types as a union ("country" | "state" | "city"). Use
// this instead of a bare ``string`` so pin/label typings stay compile-checked.
export type GeoLabelType = (typeof GEO_LABEL_TYPES)[number];

// OpenStreetMap raster tiles. No API key required.
export const MAP_TILE_URL_TEMPLATE =
  "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";
export const MAP_TILE_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

// Default viewport for a world-spanning map (roughly centred, fully zoomed out).
export const MAP_DEFAULT_CENTER: readonly [number, number] = [20, 0];
export const MAP_DEFAULT_ZOOM = 2;
export const MAP_MIN_ZOOM = 1;
export const MAP_MAX_ZOOM = 18;

// Default rendered height for the map container. Leaflet needs an explicit
// height or the tiles never paint.
export const MAP_DEFAULT_HEIGHT = "600px";

// leaflet.markercluster: max radius (px) within which markers are grouped.
export const MAP_CLUSTER_MAX_RADIUS = 60;

// URL query-param keys for persisting the map viewport (deep-link + refresh).
// Centralised so the Discover map tab and the planned Corpus Home map (#1821)
// share one set of names instead of diverging.
export const MAP_LAT_PARAM = "lat";
export const MAP_LNG_PARAM = "lng";
export const MAP_ZOOM_PARAM = "z";

// Zoom bands that select which geographic label type is shown. The server
// returns pins for *all* label types; the client picks one band by zoom so the
// map stays readable (coarse places when zoomed out, fine places when zoomed
// in). Lower bound is inclusive.
//   country: zoom <  MAP_ZOOM_STATE_MIN
//   state:   MAP_ZOOM_STATE_MIN <= zoom < MAP_ZOOM_CITY_MIN
//   city:    zoom >= MAP_ZOOM_CITY_MIN
export const MAP_ZOOM_STATE_MIN = 4;
export const MAP_ZOOM_CITY_MIN = 6;

// Debounce (ms) for bbox/zoom-driven refetches triggered by pan/zoom.
export const MAP_BBOX_REFETCH_DEBOUNCE_MS = 300;

// Auto-fit / deep-link focus framing for the per-corpus map (#1821). The corpus
// map opens framed on its pins (auto-fit) and can deep-link to a single place
// (focus); fitBounds / flyTo clamp into these so a lone pin doesn't slam to
// street level and a deep-linked place lands at a sensible granularity. The
// city band has no inherent upper bound, so MAP_FIT_MAX_ZOOM caps it.
export const MAP_FIT_MAX_ZOOM = 10;
export const MAP_FIT_PADDING_PX = 48;

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

/** Default page size for cursor-paginated list views (Annotations,
 *  Extracts, Documents). Reference this from per-feature pagination
 *  groups so the views stay in lockstep; the backend ``max_limit`` on
 *  the matching Relay connection must be >= this value. */
export const DEFAULT_LIST_PAGE_SIZE = 20;

// Annotation pagination constants
export const ANNOTATION_PAGINATION = {
  /** Number of annotations to load per page in browse mode */
  PAGE_SIZE: DEFAULT_LIST_PAGE_SIZE,
  /** Number of results per semantic search request */
  SEMANTIC_SEARCH_LIMIT: 20,
  /** Maximum accumulated semantic search results before capping */
  MAX_SEMANTIC_RESULTS: 500,
} as const;

// Extract pagination constants
export const EXTRACT_PAGINATION = {
  /** Number of extracts to load per page in the Extracts view */
  PAGE_SIZE: DEFAULT_LIST_PAGE_SIZE,
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

export const PDF_MIME_TYPE = "application/pdf";

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

// Corpus category (tag) default appearance. Mirrors the backend model
// defaults (opencontractserver/constants/corpus_categories.py) so a category
// created without an explicit icon/color renders identically on both sides.
/** Default Lucide icon name for a corpus category. */
export const DEFAULT_CATEGORY_ICON = "folder";
/** Default badge color (hex) for a corpus category. */
export const DEFAULT_CATEGORY_COLOR = "#3B82F6";
/**
 * Soft cap on a category description. Mirrors MAX_CATEGORY_DESCRIPTION_LENGTH
 * in opencontractserver/constants/corpus_categories.py so the textarea stops
 * the user before the server-side validation would reject the payload.
 */
export const MAX_CATEGORY_DESCRIPTION_LENGTH = 2000;

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
 * License pre-selected in the new-corpus modal. Users can change it before
 * creating, and the choice is purely a UX nudge — backend leaves the field
 * blank when the user doesn't pick one.
 */
export const DEFAULT_NEW_CORPUS_LICENSE: LicenseValue = "CC-BY-4.0";

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

// User identity / privacy display constants
//
// Number of trailing pk characters used in ``getCreatorDisplay``'s
// ``user_<suffix>`` fallback when a user has no ``slug``. Mirrors
// ``OAUTH_SUB_DISPLAY_SUFFIX_LENGTH`` in
// ``opencontractserver/constants/auth.py`` so the frontend redacted
// handle matches the backend's ``redacted_handle`` shape — keep in
// sync if the backend constant ever changes.
export const REDACTED_HANDLE_PK_SUFFIX_LENGTH = 6;

// Right-panel (chat / annotation tray) drag-resize bounds and snap targets.
// Used by useResizeHandle in the document KB viewer to clamp custom widths
// and to snap to the predefined "quarter" / "half" / "full" presets.
// The "full" preset deliberately stops at 90 % so a 10 % strip of the
// document remains visible behind the panel.
export const PANEL_WIDTH_MIN_PCT = 15;
export const PANEL_WIDTH_MAX_PCT = 95;
export const PANEL_WIDTH_QUARTER_PCT = 25;
export const PANEL_WIDTH_HALF_PCT = 50;
export const PANEL_WIDTH_FULL_PCT = 90;
export const PANEL_SNAP_THRESHOLD_PCT = 3;

// Cooldown between an action-menu interaction and the next selection start.
// Prevents the next mousedown / touchstart from being treated as a fresh
// selection while the menu is still dismissing.
export const SELECTION_MENU_COOLDOWN_MS = 300;
