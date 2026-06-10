import React from "react";
import styled from "styled-components";
import { Sparkles } from "lucide-react";

import { OS_LEGAL_COLORS } from "../../../../assets/configurations/osLegalStyles";

/**
 * SuggestedQuestions — the "Ask across every document" card: one-click
 * cross-document prompts that seed the corpus agent via ``onAskQuestion``.
 *
 * Shared by the composed ``CorpusIntelligenceOverview`` (landing fallback) and
 * the ``ask-across-docs`` CAML embed so the prompt list and styling live in one
 * place.
 */

// Templated cross-document prompts. Kept generic so they read well for any
// collection; every one is explicitly corpus-wide so the agent synthesizes
// across documents rather than asking which document is meant.
export const SUGGESTED_QUESTIONS: string[] = [
  "What are the key themes across these documents?",
  "Summarize the most important findings in this collection.",
  "How do these documents relate to one another?",
  "What are the main risks or obligations across these documents?",
  "What's notable or unusual across these documents?",
];

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
  background: ${OS_LEGAL_COLORS.surface};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  /* 999px is the project-wide pill idiom (see IntelligencePanel bars/track). */
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

interface SuggestedQuestionsProps {
  onAskQuestion: (query: string) => void;
  testId?: string;
}

export const SuggestedQuestions: React.FC<SuggestedQuestionsProps> = ({
  onAskQuestion,
  testId = "ask-across-docs",
}) => (
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
);
