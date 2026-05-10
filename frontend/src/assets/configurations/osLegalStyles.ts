/**
 * OS Legal Style Design System Tokens
 *
 * Shared styling constants for the Documents tab and related components.
 * This file defines the visual language for folder browsing, document cards,
 * and related UI elements following a clean, professional aesthetic.
 *
 * ## Usage Guidelines
 *
 * ### Colors
 * - **accent/accentHover**: Use for primary actions, selected states, and brand emphasis
 * - **textPrimary**: Main content text, headings, and important labels
 * - **textSecondary**: Supporting text, metadata, and secondary information
 * - **textMuted**: Placeholder text, disabled states, and tertiary content
 * - **surface/surfaceHover**: Card backgrounds, input fields, and interactive surfaces
 * - **border/borderHover**: Dividers, input borders, and subtle separations
 * - **selected***: Highlight selected items in lists and trees
 * - **dropTarget***: Visual feedback during drag-and-drop operations
 * - **folder***: Folder-specific styling (icon color, gradient backgrounds)
 * - **danger/success**: Semantic colors for destructive/positive actions
 *
 * ### Typography
 * - **fontFamilySerif**: Legal documents, formal content, and headings
 * - **fontFamilySans**: UI elements, buttons, and general interface text
 *
 * ### Spacing
 * - **borderRadiusCard**: Larger containers like cards and panels (12px)
 * - **borderRadiusButton**: Smaller elements like buttons and inputs (8px)
 * - **shadow***: Elevation levels for layered UI elements
 *
 * ## Accessibility Notes
 * - accent (#0f766e) on white background: 4.57:1 contrast ratio (WCAG AA compliant)
 * - textPrimary (#1e293b) on white: 12.63:1 contrast ratio (WCAG AAA compliant)
 * - textSecondary (#64748b) on white: 4.54:1 contrast ratio (WCAG AA compliant)
 * - textMuted (#94a3b8) on white: 2.78:1 contrast ratio (use for large text only)
 * - For critical UI elements, prefer textPrimary or textSecondary over textMuted
 */

/**
 * Color palette for the OS Legal design system.
 * All colors are defined as constants to ensure consistency across components.
 */
export const OS_LEGAL_COLORS = {
  // Brand accent colors - teal theme
  /** Primary accent color - teal (#0f766e). Use for buttons, links, and emphasis. */
  accent: "#0f766e",
  /** Hover state for accent color. Slightly darker for visual feedback. */
  accentHover: "#0d6860",
  /** Light accent background. Use for selected items and subtle highlights. */
  accentLight: "rgba(15, 118, 110, 0.1)",
  /** Medium accent opacity. Use for focus rings and selected outlines. */
  accentMedium: "rgba(15, 118, 110, 0.2)",
  /** Light accent surface (teal-50). Use for selected item backgrounds. */
  accentSurface: "#f0fdfa",

  // Interactive colors - blue theme
  /** Primary interactive blue - buttons, focus rings, toggles, active states. */
  primaryBlue: "#3b82f6",
  /** Hover/active state for primary blue. Slightly darker for visual feedback. */
  primaryBlueHover: "#2563eb",
  /**
   * Navigation accent blue (#4a90e2). Used in NavigationItem / NavigationToggle
   * gradients and shadows, plus several legacy chat/search/note components.
   * Distinct from `primaryBlue` (#3b82f6) — see issue #1446 for harmonization.
   */
  navBlue: "#4a90e2",
  /**
   * Navigation accent indigo (#6366f1). Used as the second gradient stop
   * alongside `navBlue` in nav active/hover states. See issue #1446.
   */
  navIndigo: "#6366f1",

  // Text colors - slate scale
  /** Primary text color - dark slate. Use for headings and main content. */
  textPrimary: "#1e293b",
  /** Secondary text color - medium slate. Use for supporting text and metadata. */
  textSecondary: "#64748b",
  /** Tertiary text color - dark medium slate. Between primary and secondary. */
  textTertiary: "#475569",
  /** Muted text color - light slate. Use sparingly; does not meet WCAG AA for small text. */
  textMuted: "#94a3b8",

  // Surface and background colors
  /** Page background color - off-white for subtle depth. */
  background: "#fafafa",
  /** Card and panel surface color - pure white. */
  surface: "white",
  /** Hover state for surfaces - very light gray. */
  surfaceHover: "#f8fafc",
  /** Light surface - subtle gray for badges, tags, and secondary surfaces. */
  surfaceLight: "#f1f5f9",

  // Border colors
  /** Default border color - light gray for subtle separation. */
  border: "#e2e8f0",
  /** Hover state for borders - slightly darker for emphasis. */
  borderHover: "#cbd5e1",

  // Selection states
  /** Background for selected items. Uses accent color with low opacity. */
  selectedBg: "rgba(15, 118, 110, 0.1)",
  /** Border for selected items. Uses solid accent color. */
  selectedBorder: "#0f766e",

  // Drag-and-drop visual feedback - green theme for positive action
  /** Drop target background - green tint indicates valid drop zone. */
  dropTargetBg: "rgba(34, 197, 94, 0.1)",
  /** Drop target border - green outline for clear visual feedback. */
  dropTargetBorder: "rgba(34, 197, 94, 0.3)",
  /** Drop target active/hover state - more prominent green. */
  dropTargetActive: "rgba(34, 197, 94, 0.5)",

  // Folder-specific colors - amber/golden theme
  /** Folder icon color - amber/golden for visual distinction from documents. */
  folderIcon: "#D97706",
  /** Darker amber companion to folderIcon (used as gradient end-stop). */
  folderIconDark: "#b45309",
  /** Folder background gradient - warm amber tones. */
  folderIconBg: "linear-gradient(135deg, #FEF3C7 0%, #FDE68A 100%)",

  // Semantic colors for actions
  /** Danger/destructive color - red. Use for delete, remove, and warning states. */
  danger: "#dc2626",
  /** Danger hover state - darker red. */
  dangerHover: "#b91c1c",
  /** Danger background - light red tint. */
  dangerLight: "rgba(220, 38, 38, 0.1)",
  /** Danger surface background - very light red for panels/modals. */
  dangerSurface: "#fef2f2",
  /** Danger surface hover state - slightly darker. */
  dangerSurfaceHover: "#fee2e2",
  /** Danger border color - light red for subtle borders. */
  dangerBorder: "#fecaca",
  /** Danger border hover state - more prominent red. */
  dangerBorderHover: "#f87171",
  /** Danger text color - dark red for text on danger surfaces. */
  dangerText: "#991b1b",

  /** Success color - green. Use for confirmations and positive feedback. */
  success: "#16a34a",
  /** Success hover state - darker green. */
  successHover: "#15803d",
  /** Success background - light green tint. */
  successLight: "rgba(22, 163, 74, 0.1)",
  /** Success surface background - very light green for panels/messages. */
  successSurface: "#f0fdf4",
  /** Success border color - light green for subtle borders. */
  successBorder: "#bbf7d0",
  /** Success text color - dark green for text on success surfaces. */
  successText: "#166534",

  // Info colors - blue theme for informational messages
  // Authoritative values also defined as CSS custom properties in index.css
  // (--oc-info-surface, --oc-info-border, --oc-info-text). Keep in sync.
  /** Info surface background - very light blue. */
  infoSurface: "#f0f9ff",
  /** Info border color - light blue. */
  infoBorder: "#bae6fd",
  /** Info text color - dark blue. */
  infoText: "#0369a1",

  // Warning colors - amber theme for caution messages
  // Authoritative values also defined as CSS custom properties in index.css
  // (--oc-warning-surface, --oc-warning-border, --oc-warning-text). Keep in sync.
  /** Warning surface background - very light amber. */
  warningSurface: "#fefce8",
  /** Warning border color - amber. */
  warningBorder: "#fde68a",
  /** Warning text color - dark amber. */
  warningText: "#854d0e",

  // Extended blue palette
  /** Dark blue - headings and strong emphasis on info surfaces. */
  blueDark: "#1e40af",
  /** Light blue surface - subtle blue backgrounds. */
  blueSurface: "#eff6ff",
  /** Light blue border - borders on blue surfaces. */
  blueBorder: "#bfdbfe",

  // Extended green palette
  /** Bright green - positive indicators, online status. */
  green: "#22c55e",
  /** Medium green - success accents. */
  greenMedium: "#10b981",
  /** Dark green - success accents on dark backgrounds. */
  greenDark: "#059669",

  // Dark surface colors (for dark-themed panels like cookie consent)
  /** Dark surface background - slate. */
  darkSurface: "#1e293b",
  /** Dark surface text - light gray for readability on dark backgrounds. */
  darkSurfaceText: "#e2e8f0",
  /** Dark surface border - muted separator on dark backgrounds. */
  darkSurfaceBorder: "#475569",

  // Neutral gray palette
  /** Near-white surface - barely visible gray backgrounds. */
  gray50: "#f9fafb",
  /** Light gray border - input borders, dividers. */
  gray200: "#e9ecef",
  /** Medium gray text - labels and secondary content. */
  gray500: "#868e96",
  /** Dark gray text - stronger secondary text. */
  gray700: "#495057",

  // Chart accent colors - for data visualizations
  /** Chart purple - vivid violet for chart series and data points. */
  chartPurple: "#8b5cf6",
  /** Chart pink - vivid pink for chart series and data points. */
  chartPink: "#ec4899",
  /** Chart teal - vivid teal for chart series and data points. */
  chartTeal: "#14b8a6",

  // Annotation source badge colors
  /** Agent badge color - purple for AI-generated annotations. */
  agentPurple: "#7c3aed",
  /** Agent badge background - light purple (violet-100). */
  agentPurpleLight: "#ede9fe",
  /** Structural badge background - light amber (amber-100). */
  structuralLight: "#fef3c7",

  // Extended yellow palette
  /** Light yellow surface - medium score indicators (yellow-100). */
  yellowLight: "#fef9c3",

  // Search and chat source highlight colors
  /** Active/selected search result highlight. */
  searchHighlightActive: "#FFFF00",
  /** Inactive search result highlight. */
  searchHighlight: "#FFFF99",
  /** Active/selected chat source highlight. */
  chatSourceHighlightActive: "#A8FFA8",
  /** Inactive chat source highlight. */
  chatSourceHighlight: "#D2FFD2",

  // Chat widget palette (used by widgets/chat styles)
  // The chat message bubbles use a slightly different slate scale than
  // textPrimary/textSecondary so message body text reads as distinctly
  // "chat-typed" rather than as standard UI labels. Kept here so the
  // values are reusable across all chat sibling style modules.
  /** Chat source brand color - blue-gray used by indicators/sources (#5c7c9d). */
  chatSourceBlue: "#5c7c9d",
  /** Chat source brand color - hover/darker shade (#4a6b8c). */
  chatSourceBlueHover: "#4a6b8c",
  /** Chat assistant message body text - very dark slate (#1a1f36). */
  chatMessageTextAssistant: "#1a1f36",
  /** Chat user message body text - dark slate (#2d3748). */
  chatMessageTextUser: "#2d3748",
  /** Chat source preview body text - medium slate (#4a5568). */
  chatSourcePreviewText: "#4a5568",
  /** Inline code color in chat markdown - medium blue (#2b6cb0). */
  chatCodeText: "#2b6cb0",
  /** Chat username text - near-black (#1a1a1a). */
  chatUsernameText: "#1a1a1a",
  /** Chat assistant avatar gradient start - bright blue (#2185d0). */
  chatAvatarAssistantStart: "#2185d0",
  /** Chat assistant avatar gradient end - darker blue (#1678c2). */
  chatAvatarAssistantEnd: "#1678c2",

  // Extended Tailwind-style cool gray scale used by timeline/code blocks
  /** Cool gray-700 - timeline args & code block text (#374151). */
  coolGray700: "#374151",
  /** Cool gray-600 - timeline item text (#4b5563). */
  coolGray600: "#4b5563",
  /** Cool gray-500 - timeline title text (#6b7280). */
  coolGray500: "#6b7280",
  /** Cool gray-400 - timeline disclosure indicator (#9ca3af). */
  coolGray400: "#9ca3af",
  /** Cool gray-800 - timeline item title (expanded state) (#1f2937). */
  coolGray800: "#1f2937",
} as const;

/**
 * Create an rgba color string from the accent color (#0f766e = rgb(15, 118, 110))
 * with a given opacity. Use instead of hardcoded rgba(15, 118, 110, ...) values.
 */
export const accentAlpha = (opacity: number): string =>
  `rgba(15, 118, 110, ${opacity})`;

/**
 * Create an rgba color string from primaryBlue (#3b82f6 = rgb(59, 130, 246))
 * with a given opacity. Use instead of hardcoded rgba(74, 144, 226, ...) values.
 */
export const primaryBlueAlpha = (opacity: number): string =>
  `rgba(59, 130, 246, ${opacity})`;

/**
 * Create an rgba color string from navBlue (#4a90e2 = rgb(74, 144, 226))
 * with a given opacity. Use instead of hardcoded rgba(74, 144, 226, ...) values.
 */
export const navBlueAlpha = (opacity: number): string =>
  `rgba(74, 144, 226, ${opacity})`;

/**
 * Create an rgba color string from navIndigo (#6366f1 = rgb(99, 102, 241))
 * with a given opacity. Use instead of hardcoded rgba(99, 102, 241, ...) values.
 */
export const navIndigoAlpha = (opacity: number): string =>
  `rgba(99, 102, 241, ${opacity})`;

/**
 * Create an rgba color string from the chat-source blue-gray (#5c7c9d = rgb(92, 124, 157))
 * with a given opacity. Use instead of hardcoded rgba(92, 124, 157, ...) values.
 */
export const chatSourceBlueAlpha = (opacity: number): string =>
  `rgba(92, 124, 157, ${opacity})`;

/**
 * Create an rgba color string for success glow effects (rgb(0, 255, 0))
 * with a given opacity. Use instead of hardcoded rgba(0, 255, 0, ...) values.
 */
export const successGlowAlpha = (opacity: number): string =>
  `rgba(0, 255, 0, ${opacity})`;

/**
 * Create an rgba color string for danger glow effects (rgb(255, 0, 0))
 * with a given opacity. Use instead of hardcoded rgba(255, 0, 0, ...) values.
 */
export const dangerGlowAlpha = (opacity: number): string =>
  `rgba(255, 0, 0, ${opacity})`;

/**
 * Create an rgba color string from folderIcon amber (#D97706 = rgb(217, 119, 6))
 * with a given opacity. Use instead of hardcoded rgba(245, 158, 11, ...) values.
 */
export const folderIconAlpha = (opacity: number): string =>
  `rgba(217, 119, 6, ${opacity})`;

/**
 * Create an rgba color string for translucent white surfaces (rgb(255, 255, 255)).
 * Used by chat message bubbles and source preview containers.
 */
export const whiteAlpha = (opacity: number): string =>
  `rgba(255, 255, 255, ${opacity})`;

/**
 * Create an rgba color string for translucent black overlays (rgb(0, 0, 0)).
 * Used by hover backgrounds and subtle borders inside chat code blocks.
 */
export const blackAlpha = (opacity: number): string =>
  `rgba(0, 0, 0, ${opacity})`;

/**
 * Create an rgba color string from coolGray400 (#9ca3af = rgb(156, 163, 175))
 * with a given opacity. Use instead of hardcoded rgba(156, 163, 175, ...) values
 * for neutral borders and subtle backgrounds (e.g. timeline panel chrome).
 */
export const coolGray400Alpha = (opacity: number): string =>
  `rgba(156, 163, 175, ${opacity})`;

/**
 * Create an rgba color string from the success green (#22c55e = rgb(34, 197, 94))
 * with a given opacity. Use instead of hardcoded rgba(34, 197, 94, ...) values.
 */
export const greenAlpha = (opacity: number): string =>
  `rgba(34, 197, 94, ${opacity})`;

/**
 * Typography definitions for the OS Legal design system.
 */
export const OS_LEGAL_TYPOGRAPHY = {
  /** Serif font stack - for legal documents and formal content. */
  fontFamilySerif: '"Georgia", "Times New Roman", serif',
  /** Sans-serif font stack - for UI elements and general text. */
  fontFamilySans: '"Inter", -apple-system, BlinkMacSystemFont, sans-serif',
} as const;

/**
 * Spacing and dimension constants for the OS Legal design system.
 */
export const OS_LEGAL_SPACING = {
  /** Border radius for cards and larger containers. */
  borderRadiusCard: "12px",
  /** Border radius for buttons and smaller elements. */
  borderRadiusButton: "8px",

  // ── Page-level layout tokens ──
  // Used by ContentContainer / PageContainer across list views
  // (CorpusListView, Documents, Extracts, LabelSets, GlobalSettingsPanel, etc.)

  /** Maximum content width for centered page layouts. */
  pageMaxWidth: "900px",
  /** Maximum width for subtitle / descriptive text below hero headings. */
  subtitleMaxWidth: "600px",

  /** Desktop padding for ContentContainer (top horizontal bottom). */
  pagePaddingDesktop: "3rem 1.5rem 5rem",
  /** Tablet padding (≤ 768px). */
  pagePaddingTablet: "2rem 1rem 3.75rem",
  /** Mobile padding (≤ 480px). */
  pagePaddingMobile: "1.5rem 0.75rem 3rem",

  /** Standard section spacing (hero ↔ content). */
  sectionGapDesktop: "3rem",
  /** Reduced section spacing for tablet / mobile. */
  sectionGapMobile: "2rem",

  /** Standard gap between heading and its subtitle. */
  headingBottomGap: "1rem",

  /** Maximum width for centred modal dialogs (cookie consent, settings). */
  modalMaxWidth: "760px",
  /** Side margin around full-bleed modals on smaller viewports. */
  modalSideGutter: "2rem",

  /** Border radius for inset list items inside cards. */
  borderRadiusListItem: "6px",
  /** Border radius for full-width empty-state cards (above borderRadiusCard). */
  borderRadiusEmptyState: "16px",
  /** Border-left thickness for callout / disclaimer blocks. */
  borderAccentWidth: "3px",

  /** Square dimension for circular icon badges (desktop). */
  iconBadgeDesktop: "40px",
  /** Square dimension for circular icon badges (mobile). */
  iconBadgeMobile: "34px",
} as const;

/**
 * Font-size tokens for the OS Legal design system.
 * Pixel-equivalent comments are included for reference (at 16px root).
 */
export const OS_LEGAL_FONT_SIZES = {
  /** Hero / page title — desktop (≈ 42px). */
  heroDesktop: "2.625rem",
  /** Hero / page title — tablet (≈ 32px). */
  heroTablet: "2rem",
  /** Hero / page title — mobile (≈ 26px). */
  heroMobile: "1.625rem",

  /** Hero subtitle — desktop (≈ 17px). */
  subtitleDesktop: "1.0625rem",
  /** Hero subtitle — tablet/mobile (≈ 15px). */
  subtitleMobile: "0.9375rem",

  /** Card title (≈ 18px). */
  cardTitle: "1.125rem",
  /** Card title — tablet/mobile (≈ 16px). */
  cardTitleMobile: "1rem",
  /** Card description (≈ 14px). */
  cardDescription: "0.875rem",
  /** Card description — mobile (≈ 13px). */
  cardDescriptionMobile: "0.8rem",
  /** Small badge / label text (≈ 12px). */
  badge: "0.75rem",
} as const;

/**
 * Shadow constants for the OS Legal design system.
 * Separated from spacing for semantic clarity.
 */
export const OS_LEGAL_SHADOWS = {
  /** Default card shadow - subtle elevation. */
  card: "0 4px 12px rgba(0, 0, 0, 0.04)",
  /** Hover card shadow - more prominent elevation. */
  cardHover: "0 8px 24px rgba(0, 0, 0, 0.08)",
  /** Drop shadow for centred modal overlays. */
  modalOverlay: "0 25px 50px -12px rgba(15, 23, 42, 0.25)",
} as const;
