/**
 * CamlEmbedContext — ambient context for corpus-scoped CAML component embeds.
 *
 * CAML `[component:TYPE ...]` markers only carry author-typed string props, so
 * a corpus-scoped embed (the intelligence panel, document graph, ask-across-docs
 * chips) would otherwise need the author to paste a global corpus id and wire
 * callbacks by hand. Instead, the surfaces that render CAML for a corpus
 * (`CorpusArticleView`, the `CamlArticleEditor` preview) provide this context,
 * and the embeds read it. A marker `corpusId=` prop, when present, overrides the
 * ambient value.
 *
 * Keeping callbacks here (rather than baking chat plumbing into the embeds) lets
 * `ask-across-docs` feed the article's existing floating chat — no duplicate
 * chat affordance.
 */
import React, { createContext, useContext } from "react";

export interface CamlEmbedContextValue {
  /** Relay global id of the corpus the CAML article belongs to. */
  corpusId?: string;
  /** Submit a cross-document question to the corpus agent (article chat path). */
  onAskQuestion?: (query: string) => void;
  /** Escape hatch to the fuller documents/relationships view. */
  onExploreGraph?: () => void;
}

const CamlEmbedContext = createContext<CamlEmbedContextValue>({});

export const CamlEmbedProvider = CamlEmbedContext.Provider;

/** Read the ambient CAML embed context (corpus id + chat/explore callbacks). */
export function useCamlEmbedContext(): CamlEmbedContextValue {
  return useContext(CamlEmbedContext);
}
