/**
 * CollectionDataStoryEmbed — CAML embed wrapper for the collection data story
 * (composition / timeline / value from the default Collection Profile extract).
 *
 * Marker: ``[component:collection-datastory]`` (optional ``corpusId=`` override).
 * Reads the ambient corpus id from ``CamlEmbedContext``; the live data + all
 * self-hiding logic live in ``CollectionDataStory``.
 */
import React from "react";

import { CollectionDataStory } from "../CollectionDataStory";
import { SpendingBeeswarm } from "../SpendingBeeswarm";
import { useCamlEmbedContext } from "../../../caml/CamlEmbedContext";

export const CollectionDataStoryEmbed: React.FC<
  Record<string, string | undefined>
> = ({ corpusId: corpusIdProp }) => {
  const { corpusId: ctxCorpusId } = useCamlEmbedContext();
  const corpusId = corpusIdProp || ctxCorpusId;
  if (!corpusId) return null;
  return (
    <>
      {/* PHASE-0 de-risk scaffolding — preview the shareable beeswarm artifact
          inline. Moves to its own poster route in Phase 1; remove this mount. */}
      <SpendingBeeswarm corpusId={corpusId} />
      <CollectionDataStory corpusId={corpusId} />
    </>
  );
};
