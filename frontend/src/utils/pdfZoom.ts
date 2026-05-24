import {
  FIT_WIDTH_MARGIN,
  ZOOM_MAX,
  ZOOM_MIN,
} from "../assets/configurations/constants";

/**
 * Compute the fit-to-width zoom level for a PDF page rendered inside a
 * fixed-width container.
 *
 * The returned scale is the largest value that keeps the rendered page
 * narrower than the container by at least {@link FIT_WIDTH_MARGIN} CSS
 * pixels of total breathing room, then clamped to the shared
 * {@link ZOOM_MIN} / {@link ZOOM_MAX} bounds. Reserving a margin prevents
 * the page from butting up against the container edges and — more
 * importantly — prevents horizontal overflow that would otherwise force a
 * horizontal scrollbar at the moment of mount on narrower laptop viewports
 * (see issue #1736).
 *
 * Returns `null` when either input is non-positive — callers should
 * treat that as "geometry not ready yet" and retry once both values
 * are known.
 */
export function computeFitToWidthZoom(
  naturalPageWidth: number,
  containerWidth: number
): number | null {
  if (naturalPageWidth <= 0 || containerWidth <= 0) return null;

  const raw = (containerWidth - FIT_WIDTH_MARGIN) / naturalPageWidth;
  return Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, raw));
}
