import React, { useState } from "react";
import { useReactiveVar } from "@apollo/client";
import { useNavigate } from "react-router-dom";
import { Zap, ArrowLeft } from "lucide-react";
import styled from "styled-components";

import { WarningMessage } from "../widgets/feedback";
import {
  OS_LEGAL_COLORS,
  OS_LEGAL_TYPOGRAPHY,
} from "../../assets/configurations/osLegalStyles";
import { MOBILE_VIEW_BREAKPOINT } from "../../assets/configurations/constants";
import {
  CardSegment as StyledSegment,
  PageHeader as BasePageHeader,
} from "../layout/SharedSegments";
import { backendUserObj } from "../../graphql/cache";
import { CorpusDropdown } from "../widgets/selectors/CorpusDropdown";
import { CorpusType } from "../../types/graphql-api";
import { EnrichmentRunner } from "./enrichment/EnrichmentRunner";
import { EnrichmentJobList } from "./enrichment/EnrichmentJobList";
import { useOptimisticRows } from "./enrichment/useOptimisticRows";

// ---------------------------------------------------------------------------
// Styled components (mirror IngestionMonitor shell styling)
// ---------------------------------------------------------------------------

const Container = styled.div`
  width: 100%;
  max-width: 1280px;
  margin: 0 auto;
  padding: 2rem;

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    padding: 1rem;
  }
`;

const BackLink = styled.button`
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
  font-size: 0.875rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
  background: none;
  border: none;
  padding: 0;
  cursor: pointer;
  margin-bottom: 1.5rem;
  transition: color 0.15s ease;

  &:hover {
    color: ${OS_LEGAL_COLORS.accent};
  }
`;

const PageHeader = styled(BasePageHeader)`
  align-items: flex-start;
  margin-bottom: 2rem;
`;

const PageTitle = styled.h1`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySerif};
  font-size: 1.75rem;
  font-weight: 700;
  color: ${OS_LEGAL_COLORS.textPrimary};
  margin: 0 0 0.5rem 0;
`;

const PageSubtitle = styled.p`
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
  color: ${OS_LEGAL_COLORS.textSecondary};
  font-size: 1rem;
  margin: 0;
  line-height: 1.5;
  max-width: 48rem;
`;

const PickerSection = styled(StyledSegment)`
  margin-bottom: 1.5rem;
`;

const PickerLabel = styled.label`
  display: block;
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
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

// ---------------------------------------------------------------------------
// Inner component that can call hooks unconditionally once corpus is wired
// ---------------------------------------------------------------------------

interface EnrichmentPanelProps {
  corpusId: string;
}

/**
 * Renders the Runner + JobList for a selected corpus.
 * Extracted so hooks are always called at the top level of this component,
 * never inside a conditional block of the parent.
 */
const EnrichmentPanel: React.FC<EnrichmentPanelProps> = ({ corpusId }) => {
  const { jobs, optimistic, running, loading, error, handleRan } =
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
      />
    </ContentSection>
  );
};

// ---------------------------------------------------------------------------
// Main page component
// ---------------------------------------------------------------------------

export const AdminEnrichment: React.FC = () => {
  const navigate = useNavigate();
  const currentUser = useReactiveVar(backendUserObj);
  const isSuperuser = currentUser?.isSuperuser === true;

  const [selectedCorpusId, setSelectedCorpusId] = useState<string | null>(null);

  const handleCorpusChange = (corpus: CorpusType | null) => {
    setSelectedCorpusId(corpus?.id ?? null);
  };

  // Wait for reactive var to resolve before deciding access.
  if (currentUser === null) {
    return null;
  }

  if (!isSuperuser) {
    return (
      <Container>
        <WarningMessage title="Access Denied">
          Only administrators can access the enrichment runner.
        </WarningMessage>
      </Container>
    );
  }

  return (
    <Container data-testid="admin-enrichment">
      <BackLink onClick={() => navigate("/admin/settings")}>
        <ArrowLeft size={14} />
        Back to Admin Settings
      </BackLink>

      <PageHeader>
        <div>
          <PageTitle>
            <Zap size={28} color={OS_LEGAL_COLORS.accent} />
            Enrichment Runner
          </PageTitle>
          <PageSubtitle>
            Select a corpus to run reference-enrichment and authority-discovery
            analyses, or review the status of past jobs.
          </PageSubtitle>
        </div>
      </PageHeader>

      <PickerSection>
        <PickerLabel htmlFor="corpus-picker">Corpus</PickerLabel>
        <CorpusDropdown
          value={selectedCorpusId}
          onChange={handleCorpusChange}
          placeholder="Select a corpus…"
        />
      </PickerSection>

      {selectedCorpusId && <EnrichmentPanel corpusId={selectedCorpusId} />}
    </Container>
  );
};

export default AdminEnrichment;
