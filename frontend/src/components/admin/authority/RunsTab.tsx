/**
 * Runs tab — dispatch reference-enrichment / authority-discovery analyses on a
 * corpus and review job status. Absorbed from the standalone AdminEnrichment
 * page: the corpus picker + the EnrichmentRunner / EnrichmentJobList (driven by
 * useOptimisticRows) are re-mounted unchanged inside the console shell. Those
 * runner/job-list components stay in components/admin/enrichment/ because the
 * per-corpus CorpusEnrichmentCard also consumes them — only the page wrapper is
 * absorbed here.
 */
import React, { useState } from "react";
import styled from "styled-components";

import { OS_LEGAL_COLORS } from "../../../assets/configurations/osLegalStyles";
import { CardSegment as StyledSegment } from "../../layout/SharedSegments";
import { CorpusDropdown } from "../../widgets/selectors/CorpusDropdown";
import { CorpusType } from "../../../types/graphql-api";
import { EnrichmentRunner } from "../enrichment/EnrichmentRunner";
import { EnrichmentJobList } from "../enrichment/EnrichmentJobList";
import { useOptimisticRows } from "../enrichment/useOptimisticRows";

const PickerSection = styled(StyledSegment)`
  margin-bottom: 1.5rem;
`;

const PickerLabel = styled.label`
  display: block;
  font-size: 0.875rem;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textSecondary};
  margin-bottom: 0.5rem;
`;

const ContentSection = styled.div`
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
`;

/**
 * Renders the Runner + JobList for a selected corpus. Extracted so the
 * useOptimisticRows hook is always called at the top level (never inside a
 * conditional branch of the parent).
 */
const EnrichmentPanel: React.FC<{ corpusId: string }> = ({ corpusId }) => {
  const { jobs, optimistic, running, totalCount, loading, error, handleRan } =
    useOptimisticRows(corpusId);

  return (
    <ContentSection>
      <EnrichmentRunner
        corpusId={corpusId}
        runningJobExists={running}
        onRan={handleRan}
      />
      <EnrichmentJobList
        jobs={jobs}
        loading={loading}
        error={error}
        extraJobs={optimistic}
        totalCount={totalCount}
      />
    </ContentSection>
  );
};

export const RunsTab: React.FC = () => {
  const [selectedCorpusId, setSelectedCorpusId] = useState<string | null>(null);

  return (
    <div data-testid="authority-runs-tab">
      <PickerSection>
        <PickerLabel htmlFor="corpus-picker">Corpus</PickerLabel>
        <CorpusDropdown
          value={selectedCorpusId}
          onChange={(corpus: CorpusType | null) =>
            setSelectedCorpusId(corpus?.id ?? null)
          }
          placeholder="Select a corpus…"
        />
      </PickerSection>

      {selectedCorpusId && <EnrichmentPanel corpusId={selectedCorpusId} />}
    </div>
  );
};
