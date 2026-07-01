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
import { useCamlEmbedContext } from "../../../caml/CamlEmbedContext";

export const CollectionDataStoryEmbed: React.FC<
  Record<string, string | undefined>
> = ({ corpusId: corpusIdProp }) => {
  const { corpusId: ctxCorpusId } = useCamlEmbedContext();
  const corpusId = corpusIdProp || ctxCorpusId;
  if (!corpusId) return null;
  return <CollectionDataStory corpusId={corpusId} />;
};
