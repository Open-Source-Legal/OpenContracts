import React from "react";

import { OS_LEGAL_TYPOGRAPHY } from "../../assets/configurations/osLegalStyles";

/**
 * Renders the minimal inline-italic markup used in landing/about content:
 * any `*span*` segment becomes a Source Serif italic `<em>`, the rest
 * stays as plain text. The asterisks themselves are stripped.
 *
 * This is intentionally simpler than a full Markdown parser. The cite
 * brand rule restricts italic to (a) the *cite* product name and
 * (b) publication/platform names in body copy. Both are flat inline
 * spans — no nesting, no links, no bold. Anything more elaborate
 * should live in JSX rather than the JSON content packs.
 *
 * Example:
 *   renderInlineMarkup("*cite* is the layer underneath *OpenStreetMap*.")
 *   → [<em>cite</em>, " is the layer underneath ", <em>OpenStreetMap</em>, "."]
 *
 * The returned `<em>` carries a serif font stack so the italics read as
 * publication-name treatment even inside an Inter-set sans paragraph.
 */
export function renderInlineMarkup(input: string): React.ReactNode[] {
  if (!input) return [];
  const segments = input.split(/(\*[^*]+\*)/g);
  // Safe: segments derive from static, immutable JSON content (the
  // landing/About content packs) — order never changes at runtime, no
  // user input flows through here, no list reordering or insertion.
  // Composing the index with a slice of the segment text would only
  // swap one stable key for another; React's reconciliation either way
  // is a straight-line replace.
  return segments
    .filter((segment) => segment.length > 0)
    .map((segment, index) => {
      if (segment.startsWith("*") && segment.endsWith("*")) {
        return (
          <em
            key={index}
            style={{
              fontFamily: OS_LEGAL_TYPOGRAPHY.fontFamilySerif,
              fontStyle: "italic",
              fontWeight: 400,
            }}
          >
            {segment.slice(1, -1)}
          </em>
        );
      }
      return <React.Fragment key={index}>{segment}</React.Fragment>;
    });
}
