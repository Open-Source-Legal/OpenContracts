/**
 * GovernanceGraphEmbed — CAML embed wrapper for the governance graph (the
 * corpus reference web: documents above, cited law on the shelf below).
 *
 * Marker: ``[component:governance-graph]`` (optional ``corpusId=`` override).
 * Reads the ambient corpus id + ``onExploreGraph`` callback from
 * ``CamlEmbedContext``; data fetching + the bootstrap CTA live in
 * ``GovernanceGraphLive``.
 */
import React from "react";

import { GovernanceGraphLive } from "../GovernanceGraphLive";
import { useCamlEmbedContext } from "../../../caml/CamlEmbedContext";

// Props are the untyped CAML marker attributes (all strings); ``corpusId`` is
// the only one this embed consumes.
export const GovernanceGraphEmbed: React.FC<
  Record<string, string | undefined>
> = ({ corpusId: corpusIdProp }) => {
  const { corpusId: ctxCorpusId, onExploreGraph } = useCamlEmbedContext();
  const corpusId = corpusIdProp || ctxCorpusId;
  if (!corpusId) return null;
  // On the article home, a collection that cites no in-system law shows nothing
  // here rather than an owner-only bootstrap CTA.
  return (
    <GovernanceGraphLive
      corpusId={corpusId}
      onExplore={onExploreGraph}
      hideWhenEmpty
    />
  );
};
