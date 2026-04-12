/**
 * useCamlComponentRenderer — Hook that creates a `renderMarkdown` callback
 * for CamlArticle which intercepts `[component:TYPE ...]` markers and
 * renders registered React components in their place.
 *
 * Usage:
 *   const registry = { "extract-grid": ExtractGridEmbed };
 *   const renderMarkdown = useCamlComponentRenderer(registry);
 *   <CamlArticle document={doc} renderMarkdown={renderMarkdown} />
 */
import React, { useCallback } from "react";
import { MarkdownMessageRenderer } from "../components/threads/MarkdownMessageRenderer";
import { ErrorBoundary } from "../components/widgets/ErrorBoundary";
import { ComponentEmbedErrorFallback } from "../components/widgets/ComponentEmbedErrorFallback";
import { resolveComponentMarker } from "../utils/camlComponents";
export type { CamlComponentRegistry } from "../utils/camlComponents";

/**
 * Returns a stable `renderMarkdown` callback that checks each prose block
 * for a `[component:TYPE ...]` marker. If it matches a registered component,
 * renders that component with the parsed props; otherwise falls back to the
 * standard markdown renderer.
 */
export function useCamlComponentRenderer(
  registry: Record<
    string,
    React.ComponentType<Record<string, string | undefined>>
  >
): (md: string) => React.ReactNode {
  return useCallback(
    (md: string) => {
      // Use the marker string as the React key so that multiple
      // `[component:...]` blocks in a single article each get a stable,
      // unique identity for reconciliation. Without a key, React warns
      // "Each child in a list should have a unique 'key' prop" and falls
      // back to positional reconciliation.
      const resolved = resolveComponentMarker(md, registry, md);
      if (resolved) {
        return (
          <ErrorBoundary
            fallback={(error) => <ComponentEmbedErrorFallback error={error} />}
          >
            {resolved}
          </ErrorBoundary>
        );
      }
      return <MarkdownMessageRenderer content={md} />;
    },
    [registry]
  );
}
