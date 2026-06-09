import React from "react";
import styled from "styled-components";
import { Compass } from "lucide-react";

import { OS_LEGAL_COLORS } from "../../../../assets/configurations/osLegalStyles";
import { IntelligencePanel } from "./IntelligencePanel";
import { DocumentGraphLive } from "./DocumentGraphLive";
import { SuggestedQuestions } from "./SuggestedQuestions";

/**
 * CorpusIntelligenceOverview — the composed "God's-eye view" block. It fuses
 * three already-existing capabilities into one coherent surface:
 *
 *   1. IntelligencePanel    — insight-framed at-a-glance metrics.
 *   2. DocumentGraphLive     — a visual of how the documents interconnect.
 *   3. SuggestedQuestions   — one-click cross-document Q&A via the corpus agent.
 *
 * It is the **no-CAML fallback**: corpora without a Readme.CAML article render
 * this on the landing. Corpora with an article compose the same three pieces as
 * individual CAML embeds (see ``intelligence/embeds``), so the building blocks
 * are shared rather than duplicated.
 */

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

export const CorpusIntelligenceOverview: React.FC<
  CorpusIntelligenceOverviewProps
> = ({
  corpusId,
  onAskQuestion,
  onExploreGraph,
  testId = "corpus-intelligence-overview",
}) => {
  return (
    <OverviewSection data-testid={testId}>
      <div>
        <SectionHeader>
          <Compass />
          Collection intelligence
        </SectionHeader>
      </div>

      <IntelligencePanel corpusId={corpusId} />

      <DocumentGraphLive corpusId={corpusId} onExplore={onExploreGraph} />

      {onAskQuestion && (
        <SuggestedQuestions onAskQuestion={onAskQuestion} testId={testId} />
      )}
    </OverviewSection>
  );
};
