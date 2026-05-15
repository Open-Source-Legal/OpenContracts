/**
 * Helpers for OC_URL annotations — annotations whose label text is
 * ``OC_URL`` and whose ``linkUrl`` is opened on click.
 *
 * Centralised here so that the PDF and text/markdown renderers share the
 * same is-url check and open behaviour. Updating click semantics in one
 * place keeps the two viewers in lock-step.
 */

import { OC_URL_LABEL } from "../../../assets/configurations/constants";
import {
  ServerSpanAnnotation,
  ServerTokenAnnotation,
} from "../types/annotations";

/**
 * Whether an annotation should behave as a clickable hyperlink. True when
 * the annotation carries the OC_URL label *and* has a non-empty
 * ``linkUrl``. We require both so an OC_URL annotation with a missing
 * URL (e.g. while the author is still editing) falls back to normal
 * selection behaviour.
 */
export function isUrlAnnotation(
  annotation: ServerTokenAnnotation | ServerSpanAnnotation
): boolean {
  return (
    annotation.annotationLabel?.text === OC_URL_LABEL &&
    typeof annotation.linkUrl === "string" &&
    annotation.linkUrl.trim().length > 0
  );
}

/**
 * Allow-list mirrored from the backend (``Annotation.validate_link_url``)
 * so the renderer refuses to open dangerous schemes even if the database
 * was bypassed (e.g. via a stale cached annotation).
 *
 * Exported so authoring UIs (e.g. ``CreateUrlAnnotationModal``) can validate
 * client-side input with the *same* rules — the allow-list lives in exactly
 * one place on the frontend and one place on the backend.
 */
export function isSafeUrl(url: string): boolean {
  const normalized = url.trim();
  if (normalized.length === 0) return false;
  // Reject protocol-relative URLs (``//evil.com``). They start with ``/``
  // but browsers resolve them as ``https://evil.com``, which would turn
  // the site-relative branch into an open redirect.
  if (normalized.startsWith("//")) return false;
  const lower = normalized.toLowerCase();
  return (
    lower.startsWith("http://") ||
    lower.startsWith("https://") ||
    normalized.startsWith("/")
  );
}

/**
 * Open the annotation's ``linkUrl``.
 *
 * External http(s) targets use ``window.open`` with
 * ``noopener,noreferrer`` so the opened page cannot reach back into the
 * OpenContracts session.
 *
 * Site-relative paths route through the supplied ``navigate`` callback
 * (typically ``useNavigate()`` from react-router-dom) so the SPA router
 * resolves them in place — preserving the Apollo cache and component
 * state. If no ``navigate`` is supplied (e.g. when called from a context
 * that lacks the router) the implementation falls back to
 * ``window.location.assign`` as a hard navigation. Call sites should
 * prefer the ``navigate`` form.
 *
 * Returns ``true`` when navigation was attempted, ``false`` when the URL
 * was missing or unsafe.
 */
export function openAnnotationUrl(
  annotation: ServerTokenAnnotation | ServerSpanAnnotation,
  navigate?: (to: string) => void
): boolean {
  const url = annotation.linkUrl;
  if (!url) return false;
  // Trim once and reuse for the safety check and the actual navigation;
  // ``isSafeUrl`` would otherwise trim again internally.
  const normalized = url.trim();
  if (!isSafeUrl(normalized)) return false;
  if (normalized.startsWith("/")) {
    if (navigate) {
      navigate(normalized);
    } else {
      window.location.assign(normalized);
    }
  } else {
    window.open(normalized, "_blank", "noopener,noreferrer");
  }
  return true;
}
