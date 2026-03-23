/**
 * Color manipulation utilities
 *
 * Provides functions for working with hex colors, converting to RGB/RGBA,
 * and validating color values. Used throughout the application for
 * styling components with dynamic colors.
 */

import {
  BOUNDARY_SHADOW_SELECTED,
  BOUNDARY_SHADOW_UNSELECTED,
} from "../assets/configurations/constants";

/**
 * Validates that a string is a valid hex color (3 or 6 digit format).
 * Accepts formats: #RGB, #RRGGBB, RGB, RRGGBB
 *
 * @param value - The string to validate
 * @returns True if the string is a valid hex color
 *
 * @example
 * isValidHexColor("#fff")     // true
 * isValidHexColor("#FF0000")  // true
 * isValidHexColor("abc123")   // true
 * isValidHexColor("invalid")  // false
 */
export function isValidHexColor(value: string): boolean {
  return /^#?([A-Fa-f0-9]{3}|[A-Fa-f0-9]{6})$/.test(value);
}

/**
 * Normalizes a 3-digit hex color to 6-digit format.
 * Passes through 6-digit colors unchanged.
 *
 * @param hex - The hex color string (e.g., "#abc" or "#aabbcc")
 * @returns Normalized 6-digit hex color (e.g., "#aabbcc")
 *
 * @example
 * normalizeHexColor("#abc")    // "#aabbcc"
 * normalizeHexColor("#FF0000") // "#FF0000"
 * normalizeHexColor("abc")     // "#aabbcc"
 */
export function normalizeHexColor(hex: string): string {
  // Remove # if present
  let cleanHex = hex.startsWith("#") ? hex.slice(1) : hex;

  // Expand 3-digit to 6-digit
  if (cleanHex.length === 3) {
    cleanHex = cleanHex
      .split("")
      .map((char) => char + char)
      .join("");
  }

  return `#${cleanHex}`;
}

/**
 * Converts a hex color string to an RGB object.
 *
 * @param hex - The hex color string (e.g., "#FF0000" or "#F00")
 * @returns An object with r, g, b number values (0-255)
 *
 * @example
 * hexToRgb("#FF0000") // { r: 255, g: 0, b: 0 }
 * hexToRgb("#F00")    // { r: 255, g: 0, b: 0 }
 */
export function hexToRgb(hex: string): { r: number; g: number; b: number } {
  // Remove # and normalize to 6 digits
  let cleanHex = hex.startsWith("#") ? hex.slice(1) : hex;
  if (cleanHex.length === 3) {
    cleanHex = cleanHex
      .split("")
      .map((char) => char + char)
      .join("");
  }

  const bigint = parseInt(cleanHex, 16);
  return {
    r: (bigint >> 16) & 255,
    g: (bigint >> 8) & 255,
    b: bigint & 255,
  };
}

/**
 * Converts a hex color to an RGBA color string.
 * Handles null/undefined input gracefully with a fallback color.
 * Supports both 3-digit (#abc) and 6-digit (#aabbcc) hex formats.
 *
 * @param hex - The hex color string, or null/undefined
 * @param alpha - The opacity value (0 to 1)
 * @param fallbackColor - RGB values to use if hex is invalid (default: blue)
 * @returns An RGBA color string
 *
 * @example
 * hexToRgba("#FF0000", 0.5)     // "rgba(255, 0, 0, 0.5)"
 * hexToRgba("#F00", 1)          // "rgba(255, 0, 0, 1)"
 * hexToRgba(null, 0.5)          // "rgba(74, 144, 226, 0.5)" (fallback blue)
 * hexToRgba("invalid", 0.5)     // "rgba(74, 144, 226, 0.5)" (fallback blue)
 */
export function hexToRgba(
  hex: string | null | undefined,
  alpha: number,
  fallbackColor: { r: number; g: number; b: number } = { r: 74, g: 144, b: 226 }
): string {
  // Guard against null/undefined
  if (!hex) {
    return `rgba(${fallbackColor.r}, ${fallbackColor.g}, ${fallbackColor.b}, ${alpha})`;
  }

  // Validate hex format
  if (!isValidHexColor(hex)) {
    return `rgba(${fallbackColor.r}, ${fallbackColor.g}, ${fallbackColor.b}, ${alpha})`;
  }

  const { r, g, b } = hexToRgb(hex);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

/**
 * Computes a multi-layer diffuse box-shadow for annotation bounding boxes.
 * Used by both SelectionBoundary and ResultBoundary to produce a soft
 * highlighter-pen glow effect.
 *
 * @param r - Red channel (0-255)
 * @param g - Green channel (0-255)
 * @param b - Blue channel (0-255)
 * @param selected - Whether the annotation is currently selected
 * @returns A CSS box-shadow string, or "none" if not visible
 */
export function computeAnnotationBoxShadow(
  r: number,
  g: number,
  b: number,
  selected: boolean
): string {
  const s = selected ? BOUNDARY_SHADOW_SELECTED : BOUNDARY_SHADOW_UNSELECTED;

  return [
    `0 0 ${s.outerBlur}px ${s.outerSpread}px rgba(${r}, ${g}, ${b}, ${s.outerOpacity})`,
    `0 0 ${s.midBlur}px ${s.midSpread}px rgba(${r}, ${g}, ${b}, ${s.midOpacity})`,
    `inset 0 0 ${s.insetBlur}px ${s.insetSpread}px rgba(${r}, ${g}, ${b}, ${s.insetOpacity})`,
  ].join(", ");
}

/**
 * Blends multiple hex colors together by averaging their RGB values.
 * Useful for creating overlay effects when multiple annotations overlap.
 *
 * @param colors - Array of hex color strings
 * @returns An RGB color string (not RGBA)
 *
 * @example
 * blendColors(["#FF0000", "#0000FF"]) // "rgb(127, 0, 127)"
 */
export function blendColors(colors: string[]): string {
  if (colors.length === 0) return "rgb(0, 0, 0)";
  if (colors.length === 1) return colors[0];

  let r = 0;
  let g = 0;
  let b = 0;

  for (const color of colors) {
    const rgb = hexToRgb(color);
    r += rgb.r;
    g += rgb.g;
    b += rgb.b;
  }

  r = Math.round(r / colors.length);
  g = Math.round(g / colors.length);
  b = Math.round(b / colors.length);

  return `rgb(${r}, ${g}, ${b})`;
}
