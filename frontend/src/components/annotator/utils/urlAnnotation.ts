/**
 * Helpers for link annotations — annotations whose ``linkUrl`` is opened
 * on click.
 *
 * Centralised here so that the PDF and text/markdown renderers share the
 * same is-url check and open behaviour. Updating click semantics in one
 * place keeps the two viewers in lock-step.
 */

import { REFERENCE_MENTION_DISPLAY_NAMES } from "../../../assets/configurations/constants";
import {
  ServerSpanAnnotation,
  ServerTokenAnnotation,
} from "../types/annotations";

/**
 * Whether an annotation should behave as a clickable hyperlink: true for
 * ANY annotation with a non-empty ``linkUrl``. ``link_url`` is validated
 * server-side (``Annotation.validate_link_url``) and only set on
 * annotations that genuinely point somewhere — user-authored OC_URL links
 * and enrichment reference mentions (OC_REF_LAW / OC_REF_DOC, whose
 * canonical ``/d/…`` paths route to the cited statute section or exhibit).
 * An annotation with a missing URL (e.g. an OC_URL the author is still
 * editing) falls back to normal selection behaviour. Authoring affordances
 * (the edit-URL modal flow) key off the OC_URL label directly, not this
 * predicate.
 */
export function isUrlAnnotation(
  annotation: ServerTokenAnnotation | ServerSpanAnnotation
): boolean {
  return (
    typeof annotation.linkUrl === "string" &&
    annotation.linkUrl.trim().length > 0
  );
}

/**
 * Human-facing chip label for an annotation. Enrichment reference mentions
 * carry machine-readable label codes (``OC_REF_LAW`` …); surfacing those raw
 * on the hover chip reads as noise. Map them to plain names ("Law",
 * "Exhibit", …); everything else shows its own label text unchanged.
 */
export function annotationChipLabel(
  annotation: ServerTokenAnnotation | ServerSpanAnnotation
): string {
  const text = annotation.annotationLabel?.text ?? "";
  return REFERENCE_MENTION_DISPLAY_NAMES[text] ?? text;
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
