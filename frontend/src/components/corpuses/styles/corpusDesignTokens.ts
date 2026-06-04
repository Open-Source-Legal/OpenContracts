/**
 * Design tokens for the Corpus Detail Page
 * Following OS-Legal-Style design system
 */

// Color palette
export const CORPUS_COLORS = {
  // Teal accent (primary brand color for corpus views)
  teal: {
    50: "#f0fdfa",
    100: "#ccfbf1",
    200: "#99f6e4",
    300: "#5eead4",
    400: "#2dd4bf",
    500: "#14b8a6",
    600: "#0d9488",
    700: "#0f766e", // Primary accent
    800: "#115e59",
    900: "#134e4a",
  },

  // Slate for text and backgrounds
  slate: {
    50: "#f8fafc",
    100: "#f1f5f9",
    200: "#e2e8f0",
    300: "#cbd5e1",
    400: "#94a3b8",
    500: "#64748b",
    600: "#475569",
    700: "#334155",
    800: "#1e293b",
    900: "#0f172a",
  },

  // Semantic colors
  white: "#ffffff",
  black: "#000000",
} as const;

// Typography
export const CORPUS_FONTS = {
  // Serif for headings (Georgia)
  serif: '"Georgia", "Times New Roman", serif',
  // Sans-serif for body text (Inter/system)
  sans: '"Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
  // Monospace for code
  mono: '"SF Mono", Monaco, "Cascadia Code", monospace',
} as const;

// Font sizes
export const CORPUS_FONT_SIZES = {
  xs: "0.75rem", // 12px
  sm: "0.8125rem", // 13px
  base: "0.875rem", // 14px
  md: "0.9375rem", // 15px
  lg: "1rem", // 16px
  xl: "1.125rem", // 18px
  "2xl": "1.25rem", // 20px
  "3xl": "1.5rem", // 24px
  "4xl": "2rem", // 32px
  "5xl": "2.625rem", // 42px
} as const;

// Spacing
export const CORPUS_SPACING = {
  0: "0",
  1: "0.25rem", // 4px
  2: "0.5rem", // 8px
  3: "0.75rem", // 12px
  4: "1rem", // 16px
  5: "1.25rem", // 20px
  6: "1.5rem", // 24px
  8: "2rem", // 32px
  10: "2.5rem", // 40px
  12: "3rem", // 48px
} as const;

// Border radius
export const CORPUS_RADII = {
  sm: "6px",
  md: "8px",
  lg: "12px",
  xl: "16px",
  full: "9999px",
} as const;

// Shadows
export const CORPUS_SHADOWS = {
  sm: "0 1px 2px rgba(0, 0, 0, 0.05)",
  md: "0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06)",
  lg: "0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05)",
  xl: "0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)",
  card: "0 1px 3px rgba(0, 0, 0, 0.1)",
  cardHover: "0 4px 12px rgba(0, 0, 0, 0.08), 0 2px 4px rgba(0, 0, 0, 0.04)",
} as const;

// Transitions
export const CORPUS_TRANSITIONS = {
  fast: "0.15s ease",
  normal: "0.2s ease",
  slow: "0.3s ease",
} as const;

// Breakpoints (matching existing MOBILE_VIEW_BREAKPOINT)
export const CORPUS_BREAKPOINTS = {
  mobile: 600,
  tablet: 768,
  desktop: 1024,
  wide: 1280,
  // Optimal long-form reading measure (~65-75 chars). Caps article prose width
  // so lines stay comfortable on wide viewports. Sits between tablet (768) and
  // desktop (1024) on purpose -- it is a typographic measure, not a device size.
  readingMeasure: 720,
} as const;

// Combined export for convenience
export const CORPUS_TOKENS = {
  colors: CORPUS_COLORS,
  fonts: CORPUS_FONTS,
  fontSizes: CORPUS_FONT_SIZES,
  spacing: CORPUS_SPACING,
  radii: CORPUS_RADII,
  shadows: CORPUS_SHADOWS,
  transitions: CORPUS_TRANSITIONS,
  breakpoints: CORPUS_BREAKPOINTS,
} as const;

// Helper function for media queries
export const mediaQuery = {
  mobile: `@media (max-width: ${CORPUS_BREAKPOINTS.mobile}px)`,
  tablet: `@media (max-width: ${CORPUS_BREAKPOINTS.tablet}px)`,
  desktop: `@media (min-width: ${CORPUS_BREAKPOINTS.desktop}px)`,
  wide: `@media (min-width: ${CORPUS_BREAKPOINTS.wide}px)`,
} as const;
