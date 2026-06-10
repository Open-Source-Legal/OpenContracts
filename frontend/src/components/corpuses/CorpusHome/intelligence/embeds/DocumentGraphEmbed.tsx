/**
 * DocumentGraphEmbed — CAML embed wrapper for the document-relationship graph.
 *
 * Marker: ``[component:document-graph]`` (optional ``corpusId=`` override).
 * Reads the ambient corpus id + ``onExploreGraph`` callback from
 * ``CamlEmbedContext``; the live graph data is fetched by ``DocumentGraphLive``.
 */
import React from "react";

import { DocumentGraphLive } from "../DocumentGraphLive";
import { useCamlEmbedContext } from "../../../caml/CamlEmbedContext";

// Props are the untyped CAML marker attributes (all strings); ``corpusId`` is
// the only one this embed consumes. The broad record type is intentional, not
// an under-specified signature.
export const DocumentGraphEmbed: React.FC<
  Record<string, string | undefined>
> = ({ corpusId: corpusIdProp }) => {
  const { corpusId: ctxCorpusId, onExploreGraph } = useCamlEmbedContext();
  const corpusId = corpusIdProp || ctxCorpusId;
  if (!corpusId) return null;
  return <DocumentGraphLive corpusId={corpusId} onExplore={onExploreGraph} />;
};
