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
 * Returns a CSS-color value that is safe to interpolate directly into a CSS
 * property (e.g. ``background: ${color}``). A bare hex color (#RGB, #RRGGBB,
 * #RRGGBBAA), a plain alphabetic named color (``red``, ``blue``), or a
 * functional ``rgb()/rgba()/hsl()/hsla()`` notation whose body contains ONLY
 * numerics and separators is allowed through; anything else — including values
 * with ``;``, ``{``, ``(`` (outside the allowed functions) or whitespace that
 * could break out of the property — collapses to ``fallback``. Guards against
 * (self-)XSS when the color originates from user-controlled data such as
 * annotation-label colors.
 *
 * The functional form is intentionally permissive about *which* numbers appear
 * (it does not range-check channels) but strict about *what characters* may
 * appear inside the parens (digits, ``.``, ``,``, ``%``, ``/`` and spaces only),
 * which is what makes it injection-safe.
 *
 * @param value - Candidate color string, or null/undefined
 * @param fallback - Color returned when ``value`` is missing/unsafe
 * @returns A safe CSS color string
 *
 * @example
 * safeCssColor("#4A90E2", "#000")              // "#4A90E2"
 * safeCssColor("red", "#000")                  // "red"
 * safeCssColor("rgb(255, 0, 0)", "#000")       // "rgb(255, 0, 0)"
 * safeCssColor("rgba(0,0,0,.5)", "#000")       // "rgba(0,0,0,.5)"
 * safeCssColor("red; } body { x:y", "#000")    // "#000"
 * safeCssColor("rgb(1); evil", "#000")         // "#000"
 * safeCssColor(null, "#000")                   // "#000"
 */
export function safeCssColor(
  value: string | null | undefined,
  fallback: string
): string {
  if (!value) return fallback;
  const trimmed = value.trim();
  const isHex = /^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$/.test(
    trimmed
  );
  const isNamed = /^[a-zA-Z]+$/.test(trimmed);
  // Functional notation: only the four color functions, and only numeric /
  // separator characters between the parens — no letters, ``;``, ``{`` etc.
  const isFunctional = /^(?:rgb|rgba|hsl|hsla)\([0-9.,%/\s]+\)$/i.test(trimmed);
  return isHex || isNamed || isFunctional ? trimmed : fallback;
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
