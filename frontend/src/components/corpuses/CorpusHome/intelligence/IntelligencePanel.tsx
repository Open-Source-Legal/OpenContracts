import React, { useMemo } from "react";
import { useQuery } from "@apollo/client";
import styled, { keyframes } from "styled-components";
import { FileText, Share2, BookOpenCheck, Tags } from "lucide-react";

import { StatisticWithAnimation } from "../../CorpusDashboard";
import { OS_LEGAL_COLORS } from "../../../../assets/configurations/osLegalStyles";
import { safeCssColor } from "../../../../utils/colorUtils";
import { humanizeLabel } from "../../../../utils/formatters";
import {
  GET_CORPUS_STATS,
  GetCorpusStatsInputType,
  GetCorpusStatsOutputType,
  GET_CORPUS_INTELLIGENCE_AGGREGATES,
  GetCorpusIntelligenceAggregatesInputType,
  GetCorpusIntelligenceAggregatesOutputType,
} from "../../../../graphql/queries";

/**
 * IntelligencePanel — the insight-framed "at a glance" panel of the Corpus
 * Intelligence home. It reuses the existing ``corpus_stats`` query and the
 * shared ``StatisticWithAnimation`` card, and adds a label-distribution
 * mini-chart + summary-coverage bar from the new
 * ``corpus_intelligence_aggregates`` resolver. The framing is deliberately
 * "what's in here and how dense it is", not raw counts.
 */

interface IntelligencePanelProps {
  corpusId: string;
  testId?: string;
}

const PanelContainer = styled.div`
  display: flex;
  flex-direction: column;
  gap: 1rem;
  width: 100%;
`;

const StatsRow = styled.div`
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 0.75rem;

  @media (min-width: 768px) {
    gap: 1rem;
  }
`;

const SubCard = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 1rem 1.25rem;
  background: ${OS_LEGAL_COLORS.surfaceLight};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 14px;
`;

const SubCardTitle = styled.div`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.8125rem;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textPrimary};

  svg {
    width: 15px;
    height: 15px;
    color: ${OS_LEGAL_COLORS.primaryBlue};
  }
`;

const CoverageBarTrack = styled.div`
  width: 100%;
  height: 8px;
  background: ${OS_LEGAL_COLORS.surfaceHover};
  border-radius: 999px;
  overflow: hidden;
`;

const CoverageBarFill = styled.div<{ $pct: number }>`
  height: 100%;
  width: ${(p) => p.$pct}%;
  background: ${OS_LEGAL_COLORS.primaryBlue};
  border-radius: 999px;
  transition: width 0.6s ease;
`;

const CoverageCaption = styled.div`
  font-size: 0.75rem;
  color: ${OS_LEGAL_COLORS.textMuted};
  font-variant-numeric: tabular-nums;
`;

const LabelList = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
`;

const LabelRow = styled.div`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.75rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
`;

const LabelSwatch = styled.span<{ $color: string }>`
  width: 10px;
  height: 10px;
  border-radius: 3px;
  background: ${(p) => p.$color};
  flex-shrink: 0;
`;

const LabelName = styled.span`
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
`;

const LabelBarTrack = styled.div`
  flex: 1.5;
  height: 6px;
  background: ${OS_LEGAL_COLORS.surfaceHover};
  border-radius: 999px;
  overflow: hidden;
`;

const LabelBarFill = styled.div<{ $pct: number }>`
  height: 100%;
  width: ${(p) => p.$pct}%;
  /* A single restrained fill keeps the panel calm; per-label hue lives in the
     swatch. Earlier the bars used each label's raw colour, so a saturated tag
     (e.g. a bright orange) became the loudest element on the page and pulled
     focus from the document graph it sits beside. */
  background: ${OS_LEGAL_COLORS.primaryBlue};
  opacity: 0.55;
  border-radius: 999px;
`;

const LabelCount = styled.span`
  font-variant-numeric: tabular-nums;
  color: ${OS_LEGAL_COLORS.textMuted};
  min-width: 2ch;
  text-align: right;
`;

const InsightGrid = styled.div`
  display: grid;
  grid-template-columns: 1fr;
  gap: 1rem;

  @media (min-width: 768px) {
    grid-template-columns: 1fr 1fr;
  }
`;

const EmptyHint = styled.div`
  font-size: 0.75rem;
  color: ${OS_LEGAL_COLORS.textMuted};
`;

const shimmer = keyframes`
  0% { opacity: 0.45; }
  50% { opacity: 0.8; }
  100% { opacity: 0.45; }
`;

const StatSkeleton = styled.div`
  height: 84px;
  border-radius: 14px;
  background: ${OS_LEGAL_COLORS.surfaceHover};
  animation: ${shimmer} 1.2s ease-in-out infinite;
`;

export const IntelligencePanel: React.FC<IntelligencePanelProps> = ({
  corpusId,
  testId = "corpus-intelligence-panel",
}) => {
  const variables = useMemo(() => ({ corpusId }), [corpusId]);

  const { data: statsData, loading: statsLoading } = useQuery<
    GetCorpusStatsOutputType,
    GetCorpusStatsInputType
  >(GET_CORPUS_STATS, { variables });

  const { data: aggData, loading: aggLoading } = useQuery<
    GetCorpusIntelligenceAggregatesOutputType,
    GetCorpusIntelligenceAggregatesInputType
  >(GET_CORPUS_INTELLIGENCE_AGGREGATES, { variables });

  const stats = statsData?.corpusStats;
  const agg = aggData?.corpusIntelligenceAggregates;

  // First-load gating: without this every metric reads ``0`` while in flight,
  // which is indistinguishable from a genuinely empty corpus. Once data has
  // arrived a background refetch keeps the prior values rather than flashing
  // skeletons.
  const statsInitialLoading = statsLoading && !stats;
  const aggInitialLoading = aggLoading && !agg;

  const totalDocs = stats?.totalDocs ?? 0;
  const totalRelationships = stats?.totalRelationships ?? 0;
  const totalAnnotations = stats?.totalAnnotations ?? 0;
  const totalExtracts = stats?.totalExtracts ?? 0;

  const docsWithSummary = agg?.documentsWithSummary ?? 0;
  const summaryDenominator = agg?.totalDocuments ?? totalDocs;
  const coveragePct =
    summaryDenominator > 0
      ? Math.round((docsWithSummary / summaryDenominator) * 100)
      : 0;

  const labels = agg?.labelDistribution ?? [];
  const maxLabelCount = labels.reduce((m, l) => Math.max(m, l.count), 1);

  // Only surface metrics that are actually present. A prominent "0 Extracts"
  // card (or an empty connections count) reads as "this collection is empty"
  // and undercuts the at-a-glance intent — show what's here, not what isn't.
  const statCards = [
    { value: totalDocs, label: "Documents", icon: FileText },
    { value: totalRelationships, label: "Connections", icon: Share2 },
    { value: totalAnnotations, label: "Annotations", icon: Tags },
    { value: totalExtracts, label: "Extracts", icon: BookOpenCheck },
  ].filter((stat) => stat.value > 0);

  return (
    <PanelContainer data-testid={testId}>
      <StatsRow>
        {statsInitialLoading ? (
          <>
            <StatSkeleton data-testid={`${testId}-stat-skeleton`} />
            <StatSkeleton data-testid={`${testId}-stat-skeleton`} />
            <StatSkeleton data-testid={`${testId}-stat-skeleton`} />
            <StatSkeleton data-testid={`${testId}-stat-skeleton`} />
          </>
        ) : (
          statCards.map((stat) => (
            <StatisticWithAnimation
              key={stat.label}
              value={stat.value}
              label={stat.label}
              icon={stat.icon}
            />
          ))
        )}
      </StatsRow>

      <InsightGrid>
        <SubCard data-testid={`${testId}-coverage`}>
          <SubCardTitle>
            <BookOpenCheck />
            Summary coverage
          </SubCardTitle>
          <CoverageBarTrack>
            <CoverageBarFill $pct={coveragePct} />
          </CoverageBarTrack>
          <CoverageCaption>
            {docsWithSummary} of {summaryDenominator}{" "}
            {summaryDenominator === 1 ? "document" : "documents"} summarized (
            {coveragePct}%)
          </CoverageCaption>
        </SubCard>

        <SubCard data-testid={`${testId}-labels`}>
          <SubCardTitle>
            <Tags />
            Dominant labels
          </SubCardTitle>
          {aggInitialLoading ? (
            <EmptyHint>Loading labels…</EmptyHint>
          ) : labels.length === 0 ? (
            <EmptyHint>No labeled annotations yet.</EmptyHint>
          ) : (
            <LabelList>
              {labels.map((entry) => {
                const color = safeCssColor(
                  entry.color,
                  OS_LEGAL_COLORS.primaryBlue
                );
                const pct = Math.round((entry.count / maxLabelCount) * 100);
                const display = humanizeLabel(entry.label);
                return (
                  <LabelRow key={entry.label}>
                    <LabelSwatch $color={color} />
                    <LabelName title={display}>{display}</LabelName>
                    <LabelBarTrack>
                      <LabelBarFill $pct={pct} />
                    </LabelBarTrack>
                    <LabelCount>{entry.count}</LabelCount>
                  </LabelRow>
                );
              })}
            </LabelList>
          )}
        </SubCard>
      </InsightGrid>
    </PanelContainer>
  );
};
