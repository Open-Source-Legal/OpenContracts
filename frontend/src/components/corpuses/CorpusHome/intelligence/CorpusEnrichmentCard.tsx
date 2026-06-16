import React, { useEffect, useState } from "react";
import styled from "styled-components";
import { Link2 } from "lucide-react";

import { OS_LEGAL_COLORS } from "../../../../assets/configurations/osLegalStyles";
import { EnrichmentAnalysisRow } from "../../../../graphql/mutations";
import { EnrichmentRunner } from "../../../admin/enrichment/EnrichmentRunner";
import { EnrichmentJobList } from "../../../admin/enrichment/EnrichmentJobList";
import {
  useEnrichmentJobs,
  ACTIVE_STATUSES,
} from "../../../admin/enrichment/useEnrichmentJobs";

/**
 * CorpusEnrichmentCard — compact card for corpus owners / editors to run and
 * monitor reference-enrichment jobs directly from the Intelligence home.
 *
 * Renders nothing for viewers who lack CAN_UPDATE; the parent derives the
 * boolean from `getPermissions(fullCorpus.myPermissions).includes(CAN_UPDATE)`
 * using the same data source as the rest of CorpusLandingView.
 */

export interface CorpusEnrichmentCardProps {
  /** Global relay id for the corpus. */
  corpusId: string;
  /** Resolved CAN_UPDATE permission — passed in by the parent to avoid a
   *  duplicate permission query. Renders nothing when false. */
  canUpdate: boolean;
}

// ---------------------------------------------------------------------------
// Styled components — mirrors the SubCard / SubCardTitle pattern used in
// IntelligencePanel so the card blends into the intelligence stack.
// ---------------------------------------------------------------------------

const Card = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  padding: 1rem 1.25rem;
  background: ${OS_LEGAL_COLORS.surfaceLight};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 14px;
`;

const CardHeader = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
`;

const CardTitle = styled.div`
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

const CardCaption = styled.p`
  margin: 0;
  font-size: 0.75rem;
  color: ${OS_LEGAL_COLORS.textMuted};
  line-height: 1.45;
`;

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export const CorpusEnrichmentCard: React.FC<CorpusEnrichmentCardProps> = ({
  corpusId,
  canUpdate,
}) => {
  const { jobs, refetch } = useEnrichmentJobs(corpusId);
  const [optimistic, setOptimistic] = useState<EnrichmentAnalysisRow[]>([]);

  // Prune optimistic rows that have now been confirmed by a real refetch.
  useEffect(() => {
    if (!optimistic.length) return;
    const ids = new Set(jobs.map((j) => j.id));
    if (optimistic.some((o) => ids.has(o.id))) {
      setOptimistic((prev) => prev.filter((o) => !ids.has(o.id)));
    }
  }, [jobs]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!canUpdate) return null;

  const running = [...jobs, ...optimistic].some((j) =>
    ACTIVE_STATUSES.includes(j.status ?? "")
  );

  return (
    <Card data-testid="corpus-enrichment-card">
      <CardHeader>
        <CardTitle>
          <Link2 />
          Reference enrichment
        </CardTitle>
        <CardCaption>
          Detect and link the citation web; optionally crawl missing
          authorities.
        </CardCaption>
      </CardHeader>

      <EnrichmentRunner
        corpusId={corpusId}
        compact
        runningJobExists={running}
        onRan={(rows) => {
          setOptimistic(rows);
          refetch();
        }}
      />

      <EnrichmentJobList corpusId={corpusId} extraJobs={optimistic} />
    </Card>
  );
};
