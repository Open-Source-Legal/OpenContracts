/**
 * CamlDirectiveRenderer — Generic renderer that resolves inline directives
 * in a CAML document by dispatching to registered handlers.
 *
 * This component wraps `CamlArticle` and:
 * 1. Extracts `{{@agent scope}}` directives from prose blocks
 * 2. Strips directive syntax from rendered content
 * 3. Looks up handlers from the directive registry
 * 4. Renders handler output (citation chips, review flags, etc.) after
 *    each prose block that contains directives
 *
 * The component is agent-agnostic — it doesn't know about @cite, @review,
 * or any specific directive. All behavior comes from registered handlers.
 */
import React, { useMemo } from "react";
import type { CamlDocument, CamlProse } from "@os-legal/caml";
import { CamlArticle, CamlThemeProvider } from "@os-legal/caml-react";

import { MarkdownMessageRenderer } from "../../threads/MarkdownMessageRenderer";
import {
  extractInlineDirectives,
  CamlInlineDirective,
} from "./inlineDirectives";
import {
  getDirectiveHandler,
  DirectiveHandlerContext,
} from "./directiveRegistry";
import {
  buildOcComponentCustomBlocks,
  resolveComponentMarker,
  type CamlComponentRegistry,
} from "../../../utils/camlComponents";
import { ErrorBoundary } from "../../widgets/ErrorBoundary";
import { ComponentEmbedErrorFallback } from "../../widgets/ComponentEmbedErrorFallback";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface CamlDirectiveRendererProps {
  /** The parsed CAML document (from `parseCaml()`) */
  document: CamlDocument;
  /** Context passed to all directive handlers */
  handlerContext: DirectiveHandlerContext;
  /** Optional stats to pass through to CamlArticle */
  stats?: {
    annotations?: number;
    documents?: number;
    contributors?: number;
    threads?: number;
  };
  /** Optional callback to resolve protocol URIs (e.g. corpus://icon) to image URLs */
  resolveImageSrc?: (src: string) => string | undefined;
  /** Optional registry of embedded component types (e.g. extract-grid). */
  componentRegistry?: CamlComponentRegistry;
}

// ---------------------------------------------------------------------------
// Inner component that renders a single directive via its registered handler.
// Only mounted when a handler exists (filtering happens in the parent), so
// the hook call is unconditional and React hook ordering is stable.
// ---------------------------------------------------------------------------

const DirectiveSlot: React.FC<{
  directive: CamlInlineDirective;
  context: DirectiveHandlerContext;
}> = ({ directive, context }) => {
  const handler = getDirectiveHandler(directive.agent)!;
  const result = handler(directive, context);
  return <>{result.node}</>;
};

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export const CamlDirectiveRenderer: React.FC<CamlDirectiveRendererProps> = ({
  document,
  handlerContext,
  stats,
  resolveImageSrc,
  componentRegistry,
}) => {
  // Single pass: extract directives and build cleaned document simultaneously.
  // Each prose block is parsed once via extractInlineDirectives, producing both
  // the stripped content and the directive list keyed by position.
  const { cleanedDocument, positionToDirectives } = useMemo(() => {
    const directiveMap = new Map<string, CamlInlineDirective[]>();

    const cleaned: CamlDocument = {
      ...document,
      chapters: document.chapters.map((chapter, ci) => ({
        ...chapter,
        blocks: chapter.blocks.map((block, bi) => {
          if (block.type !== "prose") return block;
          const proseBlock = block as CamlProse;
          const { content, directives } = extractInlineDirectives(
            proseBlock.content
          );
          if (directives.length > 0) {
            directiveMap.set(`${ci}-${bi}`, directives);
          }
          return { ...block, content };
        }),
      })),
    };

    return { cleanedDocument: cleaned, positionToDirectives: directiveMap };
  }, [document]);

  // Build a reverse lookup: cleaned content string -> position key.
  // Uses a counter suffix to disambiguate duplicate prose content —
  // if two blocks have identical text after directive stripping, each
  // gets a unique key like "content#0" / "content#1".
  const contentToPositionKey = useMemo(() => {
    const map = new Map<string, string>();
    const counts = new Map<string, number>();
    cleanedDocument.chapters.forEach((chapter, ci) => {
      chapter.blocks.forEach((block, bi) => {
        if (block.type !== "prose") return;
        const key = `${ci}-${bi}`;
        if (positionToDirectives.has(key)) {
          const trimmed = (block as CamlProse).content.trim();
          const count = counts.get(trimmed) ?? 0;
          counts.set(trimmed, count + 1);
          map.set(`${trimmed}#${count}`, key);
        }
      });
    });
    return map;
  }, [cleanedDocument, positionToDirectives]);

  // Track how many times each content string has been seen during
  // rendering so we can match it to the correct positional key.
  //
  // ASSUMPTION: CamlArticle calls renderMarkdown in document order, exactly
  // once per block. If CamlArticle ever renders out-of-order (e.g. Suspense
  // batching, virtual rendering), citations will appear on the wrong blocks.
  // TODO: Replace this workaround with the future `renderDirective` slot in
  // @os-legal/caml-react once available.
  const renderMarkdown = useMemo(() => {
    const renderCounts = new Map<string, number>();
    return (md: string) => {
      const trimmed = md.trim();
      const count = renderCounts.get(trimmed) ?? 0;
      renderCounts.set(trimmed, count + 1);
      const posKey = contentToPositionKey.get(`${trimmed}#${count}`);
      const directives = posKey ? positionToDirectives.get(posKey) : undefined;

      // Check for embedded component markers (e.g. [component:extract-grid ...])
      // Component-marker blocks are assumed to contain no inline directives.
      // Pass `md` as the React key so multiple markers in the same article
      // reconcile stably (otherwise React warns about missing `key` props).
      if (componentRegistry) {
        const resolved = resolveComponentMarker(md, componentRegistry, md);
        if (resolved) {
          return (
            <ErrorBoundary
              fallback={(error) => (
                <ComponentEmbedErrorFallback error={error} />
              )}
            >
              {resolved}
            </ErrorBoundary>
          );
        }
      }

      return (
        <>
          <MarkdownMessageRenderer content={md} />
          {directives
            ?.filter((d) => getDirectiveHandler(d.agent))
            .map((d) => (
              <DirectiveSlot
                key={`${d.agent}-${d.scope}-${d.offset}`}
                directive={d}
                context={handlerContext}
              />
            ))}
        </>
      );
    };
  }, [
    contentToPositionKey,
    positionToDirectives,
    handlerContext,
    componentRegistry,
  ]);

  // Custom block dispatch for the project's `::: oc-component` fence used by
  // the editor to embed components (e.g. extract grids). The fence wraps a
  // plain `[component:TYPE ...]` marker, so we delegate to the same
  // renderMarkdown path that handles inline markers.
  const customBlocks = useMemo(
    () => buildOcComponentCustomBlocks(renderMarkdown),
    [renderMarkdown]
  );

  return (
    <CamlThemeProvider>
      <CamlArticle
        document={cleanedDocument}
        stats={stats}
        renderMarkdown={renderMarkdown}
        resolveImageSrc={resolveImageSrc}
        customBlocks={customBlocks}
      />
    </CamlThemeProvider>
  );
};
