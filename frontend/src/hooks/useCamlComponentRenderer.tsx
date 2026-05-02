/**
 * useCamlComponentRenderer — Hook that creates a `renderMarkdown` callback
 * for CamlArticle which intercepts `[component:TYPE ...]` markers and
 * renders registered React components in their place.
 *
 * Also returns a `customBlocks` map that handles the project-specific
 * `::: oc-component` fence used by the editor's "Insert Extract Grid"
 * action. The fence is needed because the library's parser does not handle
 * a `::: prose` fence (block.content is undefined → ProseBlock crashes).
 *
 * Usage:
 *   const registry = { "extract-grid": ExtractGridEmbed };
 *   const { renderMarkdown, customBlocks } = useCamlComponentRenderer(registry);
 *   <CamlArticle
 *     document={doc}
 *     renderMarkdown={renderMarkdown}
 *     customBlocks={customBlocks}
 *   />
 */
import React, { useCallback, useMemo } from "react";
import { MarkdownMessageRenderer } from "../components/threads/MarkdownMessageRenderer";
import { ErrorBoundary } from "../components/widgets/ErrorBoundary";
import { ComponentEmbedErrorFallback } from "../components/widgets/ComponentEmbedErrorFallback";
import {
  buildOcComponentCustomBlocks,
  resolveComponentMarker,
} from "../utils/camlComponents";
export type { CamlComponentRegistry } from "../utils/camlComponents";

export interface CamlComponentRendererBindings {
  /** Pass to `<CamlArticle renderMarkdown={...}>`. */
  renderMarkdown: (md: string) => React.ReactNode;
  /** Pass to `<CamlArticle customBlocks={...}>`. */
  customBlocks: Record<string, (block: unknown) => React.ReactNode>;
}

/**
 * Returns the `renderMarkdown` and `customBlocks` callbacks needed by
 * `CamlArticle` to resolve `[component:TYPE ...]` markers. `renderMarkdown`
 * intercepts standalone markers in prose blocks (legacy / inline use); the
 * `oc-component` custom block intercepts markers wrapped in the project's
 * dedicated fence.
 */
export function useCamlComponentRenderer(
  registry: Record<
    string,
    React.ComponentType<Record<string, string | undefined>>
  >
): CamlComponentRendererBindings {
  const renderMarkdown = useCallback(
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

  const customBlocks = useMemo(
    () => buildOcComponentCustomBlocks(renderMarkdown),
    [renderMarkdown]
  );

  return { renderMarkdown, customBlocks };
}
