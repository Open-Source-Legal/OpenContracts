/**
 * Shared hook that clears the ?tb= text block highlight when the user
 * interacts with annotations or chat sources, preventing a stale
 * deep-link highlight from persisting indefinitely in the URL.
 *
 * Must be called from a single-instance component per document viewer
 * (e.g. PDFAnnotator / TxtAnnotatorWrapper) — NOT from per-page
 * components like PDFPage, which would fire O(visible-pages) navigate
 * calls.
 */

import { useEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { highlightedTextBlock } from "../../../graphql/cache";
import { updateTextBlockParam } from "../../../utils/navigationUtils";

export function useClearTextBlockOnInteraction(
  selectedAnnotations: string[],
  selectedMessageId: string | null
) {
  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    // Read the reactive var directly (not via useReactiveVar) — we only
    // clear on user interaction, not whenever the var itself changes.
    if (
      (selectedAnnotations.length > 0 || selectedMessageId) &&
      highlightedTextBlock()
    ) {
      updateTextBlockParam(location, navigate, null);
    }
  }, [selectedAnnotations, selectedMessageId, location, navigate]);
}
