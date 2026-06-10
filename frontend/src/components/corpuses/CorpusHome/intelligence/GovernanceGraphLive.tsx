import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useLazyQuery, useMutation, useQuery } from "@apollo/client";
import styled, { keyframes } from "styled-components";
import { toast } from "react-toastify";
import { Loader2, Network } from "lucide-react";

import { OS_LEGAL_COLORS } from "../../../../assets/configurations/osLegalStyles";
import {
  ENRICHMENT_ANALYZER_TASK_NAME,
  GOVERNANCE_GRAPH_WEAVING_POLL_MS,
} from "../../../../assets/configurations/constants";
import {
  GET_GOVERNANCE_GRAPH,
  GET_ANALYZERS_FOR_ENRICHMENT,
  GetGovernanceGraphInputType,
  GetGovernanceGraphOutputType,
  GetAnalyzersForEnrichmentOutputType,
  GovernanceGraphNode,
  GovernanceGraphEdge,
} from "../../../../graphql/queries";
import {
  CREATE_CORPUS_ACTION,
  START_ANALYSIS,
  StartAnalysisInput,
  StartAnalysisOutput,
} from "../../../../graphql/mutations";
import { useNavigateToDocumentById } from "../../../../hooks/useNavigateToDocumentById";
import { GovernanceGraphGlimpse } from "./GovernanceGraphGlimpse";

// Stable empty-array references so the glimpse's layout memos stay cached
// while the query is in flight (see DocumentGraphLive for the rationale).
const EMPTY_NODES: GovernanceGraphNode[] = [];
const EMPTY_EDGES: GovernanceGraphEdge[] = [];

const spin = keyframes`
  to { transform: rotate(360deg); }
`;

const BootstrapButton = styled.button`
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.55rem 1.1rem;
  border: none;
  border-radius: 10px;
  background: ${OS_LEGAL_COLORS.primaryBlue};
  color: white;
  font-size: 0.8125rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s ease;

  &:hover {
    background: ${OS_LEGAL_COLORS.primaryBlueHover};
  }

  &:disabled {
    opacity: 0.7;
    cursor: default;
  }

  svg {
    width: 15px;
    height: 15px;
  }
`;

const WeavingNote = styled.span`
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.8125rem;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textSecondary};

  svg {
    width: 15px;
    height: 15px;
    animation: ${spin} 1.1s linear infinite;
  }
`;

/**
 * GovernanceGraphLive — fetches the corpus reference web and feeds the
 * presentational ``GovernanceGraphGlimpse``. Also owns the bootstrap flow:
 * when the corpus has no reference web yet, the empty state offers a
 * one-click "Map the reference web" that (1) starts an immediate
 * corpus-reference-enrichment analysis and (2) installs an ``add_document``
 * CorpusAction so the web keeps growing as documents arrive. While the first
 * run executes, the query polls until nodes appear.
 */
interface GovernanceGraphLiveProps {
  corpusId: string;
  onExplore?: () => void;
  testId?: string;
}

export const GovernanceGraphLive: React.FC<GovernanceGraphLiveProps> = ({
  corpusId,
  onExplore,
  testId = "governance-graph-live",
}) => {
  const navigateToDocument = useNavigateToDocumentById();
  const [weaving, setWeaving] = useState(false);
  const [bootstrapping, setBootstrapping] = useState(false);

  const variables = useMemo(() => ({ corpusId }), [corpusId]);

  const { data, loading, error, startPolling, stopPolling } = useQuery<
    GetGovernanceGraphOutputType,
    GetGovernanceGraphInputType
  >(GET_GOVERNANCE_GRAPH, { variables });

  const graph = data?.governanceGraph;
  const hasNodes = (graph?.nodes?.length ?? 0) > 0;

  // First nodes have arrived — the web is woven; stop polling.
  useEffect(() => {
    if (weaving && hasNodes) {
      stopPolling();
      setWeaving(false);
    }
  }, [weaving, hasNodes, stopPolling]);

  const [fetchAnalyzers] = useLazyQuery<GetAnalyzersForEnrichmentOutputType>(
    GET_ANALYZERS_FOR_ENRICHMENT,
    { fetchPolicy: "network-only" }
  );
  const [startAnalysis] = useMutation<StartAnalysisOutput, StartAnalysisInput>(
    START_ANALYSIS
  );
  const [createCorpusAction] = useMutation(CREATE_CORPUS_ACTION);

  /** Graph node click-through: resolve the document's slugs, then navigate
   * to its canonical path (works across corpora — statute sections navigate
   * into their authority corpus). */
  const handleSelectDocument = useCallback(
    (documentId: string) => {
      void navigateToDocument(documentId);
    },
    [navigateToDocument]
  );

  const handleBootstrap = useCallback(async () => {
    setBootstrapping(true);
    try {
      const { data: analyzerData } = await fetchAnalyzers();
      const analyzer = analyzerData?.analyzers?.edges
        ?.map((e) => e.node)
        .find((n) => n.taskName === ENRICHMENT_ANALYZER_TASK_NAME);
      if (!analyzer) {
        toast.error("Reference enrichment isn't available on this deployment.");
        return;
      }

      const { data: startData } = await startAnalysis({
        variables: { analyzerId: analyzer.id, corpusId },
      });
      if (!startData?.startAnalysisOnDoc?.ok) {
        toast.error(
          startData?.startAnalysisOnDoc?.message ||
            "Couldn't start reference enrichment."
        );
        return;
      }

      // Keep the web growing: install the add_document action. A failure
      // here (e.g. collaborator without update rights) shouldn't abort the
      // already-running first weave — surface it softly instead.
      try {
        await createCorpusAction({
          variables: {
            corpusId,
            trigger: "add_document",
            analyzerId: analyzer.id,
            name: "Reference enrichment (auto)",
          },
        });
      } catch {
        toast.info(
          "Mapping started — but the keep-it-updated action couldn't be " +
            "installed (you may need edit rights on this corpus)."
        );
      }

      setWeaving(true);
      startPolling(GOVERNANCE_GRAPH_WEAVING_POLL_MS);
      toast.success("Mapping the reference web — this can take a minute.");
    } catch (err) {
      toast.error("Couldn't start reference enrichment.");
    } finally {
      setBootstrapping(false);
    }
  }, [
    corpusId,
    fetchAnalyzers,
    startAnalysis,
    createCorpusAction,
    startPolling,
  ]);

  const emptyAction = weaving ? (
    <WeavingNote data-testid={`${testId}-weaving`}>
      <Loader2 />
      Weaving the reference web…
    </WeavingNote>
  ) : (
    <BootstrapButton
      onClick={handleBootstrap}
      disabled={bootstrapping}
      data-testid={`${testId}-bootstrap`}
    >
      {bootstrapping ? <Loader2 /> : <Network />}
      Map the reference web
    </BootstrapButton>
  );

  return (
    <GovernanceGraphGlimpse
      nodes={graph?.nodes ?? EMPTY_NODES}
      edges={graph?.edges ?? EMPTY_EDGES}
      documentCount={graph?.documentCount ?? 0}
      externalKeyCount={graph?.externalKeyCount ?? 0}
      mentionCount={graph?.mentionCount ?? 0}
      truncated={graph?.truncated ?? false}
      loading={loading && !graph}
      error={!!error && !graph}
      onSelectDocument={handleSelectDocument}
      onExplore={onExplore}
      emptyAction={emptyAction}
      testId={testId}
    />
  );
};
