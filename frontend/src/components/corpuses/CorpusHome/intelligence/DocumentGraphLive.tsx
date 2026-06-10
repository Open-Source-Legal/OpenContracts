import React, { useMemo } from "react";
import { useQuery } from "@apollo/client";

import {
  GET_CORPUS_DOCUMENT_GRAPH,
  GetCorpusDocumentGraphInputType,
  GetCorpusDocumentGraphOutputType,
} from "../../../../graphql/queries";
import { DocumentGraphGlimpse } from "./DocumentGraphGlimpse";

/**
 * DocumentGraphLive — fetches the corpus document-relationship graph and feeds
 * the presentational ``DocumentGraphGlimpse``. Shared by the composed
 * ``CorpusIntelligenceOverview`` (landing fallback) and the ``document-graph``
 * CAML embed so the query wiring lives in one place.
 */
interface DocumentGraphLiveProps {
  corpusId: string;
  onExplore?: () => void;
  testId?: string;
}

export const DocumentGraphLive: React.FC<DocumentGraphLiveProps> = ({
  corpusId,
  onExplore,
  testId,
}) => {
  const variables = useMemo(() => ({ corpusId }), [corpusId]);

  const { data, loading } = useQuery<
    GetCorpusDocumentGraphOutputType,
    GetCorpusDocumentGraphInputType
  >(GET_CORPUS_DOCUMENT_GRAPH, { variables });

  const graph = data?.corpusDocumentGraph;

  return (
    <DocumentGraphGlimpse
      nodes={graph?.nodes ?? []}
      edges={graph?.edges ?? []}
      totalNodeCount={graph?.totalNodeCount ?? 0}
      totalEdgeCount={graph?.totalEdgeCount ?? 0}
      truncated={graph?.truncated ?? false}
      loading={loading && !graph}
      onExplore={onExplore}
      testId={testId}
    />
  );
};
