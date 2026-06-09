import React, { useMemo } from "react";
import { useQuery } from "@apollo/client";
import styled from "styled-components";
import { Sparkles, Compass } from "lucide-react";

import { OS_LEGAL_COLORS } from "../../../../assets/configurations/osLegalStyles";
import {
  GET_CORPUS_DOCUMENT_GRAPH,
  GetCorpusDocumentGraphInputType,
  GetCorpusDocumentGraphOutputType,
} from "../../../../graphql/queries";
import { IntelligencePanel } from "./IntelligencePanel";
import { DocumentGraphGlimpse } from "./DocumentGraphGlimpse";

/**
 * CorpusIntelligenceOverview — the composed "God's-eye view" block injected
 * into the corpus landing. It fuses three already-existing capabilities into
 * one coherent surface so a normal user immediately experiences large-scale
 * document intelligence:
 *
 *   1. IntelligencePanel  — insight-framed at-a-glance metrics.
 *   2. DocumentGraphGlimpse — a visual of how the documents interconnect.
 *   3. SuggestedQuestions — one-click cross-document Q&A via the corpus agent.
 *
 * All data comes from existing/new GraphQL resolvers; the chat path reuses the
 * landing's ``onChatSubmit`` (CorpusChat) — no new chat plumbing.
 */

// Templated cross-document prompts. Kept generic so they read well for any
// collection; they seed the existing corpus agent via ``onChatSubmit``.
const SUGGESTED_QUESTIONS: string[] = [
  "What are the key themes across these documents?",
  "Summarize the most important findings in this collection.",
  "How do these documents relate to one another?",
  "What are the main risks or obligations across these documents?",
  "What's notable or unusual across these documents?",
];

interface CorpusIntelligenceOverviewProps {
  corpusId: string;
  /** Submit a query to the corpus agent (reuses the landing chat path). */
  onAskQuestion?: (query: string) => void;
  /** Escape hatch to the fuller documents/relationships view. */
  onExploreGraph?: () => void;
  testId?: string;
}

const OverviewSection = styled.section`
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  width: 100%;
  margin-top: 1rem;
`;

const SectionHeader = styled.div`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.75rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: ${OS_LEGAL_COLORS.textMuted};

  svg {
    width: 15px;
    height: 15px;
    color: ${OS_LEGAL_COLORS.primaryBlue};
  }
`;

const SuggestionsCard = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  padding: 1rem 1.25rem 1.25rem;
  background: ${OS_LEGAL_COLORS.surfaceLight};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 14px;
`;

const SuggestionsTitle = styled.div`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.875rem;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textPrimary};

  svg {
    color: ${OS_LEGAL_COLORS.primaryBlue};
  }
`;

const SuggestionChips = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
`;

const SuggestionChip = styled.button`
  display: inline-flex;
  align-items: center;
  padding: 0.5rem 0.85rem;
  background: white;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 999px;
  font-size: 0.8125rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
  cursor: pointer;
  transition: all 0.15s ease;
  text-align: left;

  &:hover {
    border-color: ${OS_LEGAL_COLORS.primaryBlue};
    color: ${OS_LEGAL_COLORS.primaryBlue};
    background: ${OS_LEGAL_COLORS.surfaceHover};
  }
`;

export const CorpusIntelligenceOverview: React.FC<
  CorpusIntelligenceOverviewProps
> = ({
  corpusId,
  onAskQuestion,
  onExploreGraph,
  testId = "corpus-intelligence-overview",
}) => {
  const variables = useMemo(() => ({ corpusId }), [corpusId]);

  const { data: graphData } = useQuery<
    GetCorpusDocumentGraphOutputType,
    GetCorpusDocumentGraphInputType
  >(GET_CORPUS_DOCUMENT_GRAPH, { variables });

  const graph = graphData?.corpusDocumentGraph;

  return (
    <OverviewSection data-testid={testId}>
      <div>
        <SectionHeader>
          <Compass />
          Collection intelligence
        </SectionHeader>
      </div>

      <IntelligencePanel corpusId={corpusId} />

      <DocumentGraphGlimpse
        nodes={graph?.nodes ?? []}
        edges={graph?.edges ?? []}
        totalNodeCount={graph?.totalNodeCount ?? 0}
        totalEdgeCount={graph?.totalEdgeCount ?? 0}
        truncated={graph?.truncated ?? false}
        onExplore={onExploreGraph}
      />

      {onAskQuestion && (
        <SuggestionsCard data-testid={`${testId}-suggestions`}>
          <SuggestionsTitle>
            <Sparkles size={16} />
            Ask across every document
          </SuggestionsTitle>
          <SuggestionChips>
            {SUGGESTED_QUESTIONS.map((q) => (
              <SuggestionChip
                key={q}
                type="button"
                onClick={() => onAskQuestion(q)}
                data-testid={`${testId}-suggestion`}
              >
                {q}
              </SuggestionChip>
            ))}
          </SuggestionChips>
        </SuggestionsCard>
      )}
    </OverviewSection>
  );
};
