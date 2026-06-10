/**
 * InsightPanelEmbed — CAML embed wrapper for the corpus IntelligencePanel.
 *
 * Marker: ``[component:insight-panel]`` (optional ``corpusId=`` override).
 * Reads the ambient corpus id from ``CamlEmbedContext`` so authors don't paste
 * a global id; falls back to a marker-provided ``corpusId`` when present.
 */
import React from "react";

import { IntelligencePanel } from "../IntelligencePanel";
import { useCamlEmbedContext } from "../../../caml/CamlEmbedContext";

// Props are the untyped CAML marker attributes (all strings); ``corpusId`` is
// the only one this embed consumes. The broad record type is intentional, not
// an under-specified signature.
export const InsightPanelEmbed: React.FC<
  Record<string, string | undefined>
> = ({ corpusId: corpusIdProp }) => {
  const { corpusId: ctxCorpusId } = useCamlEmbedContext();
  const corpusId = corpusIdProp || ctxCorpusId;
  if (!corpusId) return null;
  return <IntelligencePanel corpusId={corpusId} />;
};
