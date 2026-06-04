import React, { useEffect, useMemo, useRef } from "react";
import { notifyTransientNetworkError } from "../../utils/networkNotifications";
import { useQuery, useReactiveVar } from "@apollo/client";
import styled from "styled-components";
import { Button, EmptyState } from "@os-legal/ui";
import { Sparkles } from "lucide-react";

import {
  openedCorpus,
  researchSearchTerm,
  authToken,
} from "../../graphql/cache";
import {
  GET_RESEARCH_REPORTS,
  GetResearchReportsInput,
  GetResearchReportsOutput,
} from "../../graphql/queries";
import { JobStatus } from "../../types/graphql-api";
import { DEFAULT_LIST_PAGE_SIZE } from "../../assets/configurations/constants";
import { OS_LEGAL_COLORS } from "../../assets/configurations/osLegalStyles";
import { ResearchReportListCard } from "./ResearchReportListCard";

/** Filter-tab id → backend status arg (undefined = no status filter). */
const FILTER_TO_STATUS: Record<string, JobStatus | undefined> = {
  all: undefined,
  queued: JobStatus.Queued,
  running: JobStatus.Running,
  completed: JobStatus.Completed,
  failed: JobStatus.Failed,
  cancelled: JobStatus.Cancelled,
};

const Container = styled.div`
  height: 100%;
  overflow-y: auto;
  padding: 20px;
`;

const Grid = styled.div`
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
`;

const LoadMoreRow = styled.div`
  display: flex;
  justify-content: center;
  padding: 24px 0;
`;

const StateWrapper = styled.div`
  padding: 48px 16px;
`;

const Hint = styled.p`
  font-size: 13px;
  color: ${OS_LEGAL_COLORS.textMuted};
  margin: 16px auto 0;
  max-width: 420px;
  text-align: center;
  line-height: 1.5;
`;

interface CorpusResearchReportCardsProps {
  /** Filter by status: all | queued | running | completed | failed | cancelled */
  activeFilter?: string;
}

/**
 * Corpus-scoped list of deep-research reports (creator-only). The backend
 * connection filters by corpus + status; free-text search is applied
 * client-side on the loaded page (the connection exposes no name argument).
 */
export const CorpusResearchReportCards: React.FC<
  CorpusResearchReportCardsProps
> = ({ activeFilter = "all" }) => {
  const opened_corpus = useReactiveVar(openedCorpus);
  const research_search_term = useReactiveVar(researchSearchTerm);
  const auth_token = useReactiveVar(authToken);

  const variables = useMemo<GetResearchReportsInput>(
    () => ({
      corpusId: opened_corpus?.id ?? "",
      status: FILTER_TO_STATUS[activeFilter],
      limit: DEFAULT_LIST_PAGE_SIZE,
    }),
    [opened_corpus?.id, activeFilter]
  );

  const { loading, error, data, fetchMore, refetch } = useQuery<
    GetResearchReportsOutput,
    GetResearchReportsInput
  >(GET_RESEARCH_REPORTS, {
    variables,
    // First execution: cache-and-network paints cached cards immediately while
    // revalidating against the server. Subsequent executions (re-renders): drop
    // to cache-first so we don't fire a network refetch storm — fresh data
    // arrives via the explicit refetch()/completion-notification paths instead.
    fetchPolicy: "cache-and-network",
    nextFetchPolicy: "cache-first",
    notifyOnNetworkStatusChange: true,
    skip: !opened_corpus?.id,
  });

  // Skip the initial run: useQuery already fetches on mount, so refetching
  // here too would double-fetch. Only refetch on a subsequent auth change.
  const didMountRef = useRef(false);
  useEffect(() => {
    if (!didMountRef.current) {
      didMountRef.current = true;
      return;
    }
    if (auth_token && opened_corpus?.id) {
      refetch();
    }
  }, [auth_token, opened_corpus?.id, refetch]);

  // Fire the error toast from an effect, not the render body — a render-body
  // call re-fires on every re-render while ``error`` stays truthy.
  useEffect(() => {
    if (error) {
      notifyTransientNetworkError(
        "ERROR\nCould not fetch research reports for this corpus.",
        { toastId: "fetch-research-reports-error" }
      );
    }
  }, [error]);

  const allReports = useMemo(
    () => (data?.researchReports?.edges ?? []).map((e) => e.node),
    [data]
  );

  // Client-side title search (connection has no name argument).
  const reports = useMemo(() => {
    const q = research_search_term.trim().toLowerCase();
    if (!q) return allReports;
    return allReports.filter((r) => r.title?.toLowerCase().includes(q));
  }, [allReports, research_search_term]);

  const pageInfo = data?.researchReports?.pageInfo;

  const handleLoadMore = () => {
    if (!pageInfo?.hasNextPage) return;
    fetchMore({
      variables: { ...variables, cursor: pageInfo.endCursor },
    });
  };

  // Only surface the error state once the request has settled (not while a
  // retry is in flight) so a transient error doesn't flash over the spinner.
  if (error && !loading && allReports.length === 0) {
    return (
      <Container>
        <StateWrapper>
          <EmptyState
            icon={<Sparkles />}
            title="Could not load reports"
            description="There was a problem fetching deep-research reports for this corpus. Please try again."
            size="lg"
          />
        </StateWrapper>
      </Container>
    );
  }

  if (loading && allReports.length === 0) {
    return (
      <Container>
        <StateWrapper>
          <EmptyState
            icon={<Sparkles />}
            title="Loading research…"
            description="Fetching deep-research reports for this corpus."
            size="md"
          />
        </StateWrapper>
      </Container>
    );
  }

  if (reports.length === 0) {
    return (
      <Container>
        <StateWrapper>
          <EmptyState
            icon={<Sparkles />}
            title={
              research_search_term ? "No matching reports" : "No research yet"
            }
            description={
              research_search_term
                ? pageInfo?.hasNextPage
                  ? "No research reports on the loaded page match your search — load more to search further."
                  : "No research reports match your search."
                : "Deep-research reports run from the corpus chat will appear here."
            }
            size="lg"
          />
          {!research_search_term && (
            <Hint>
              Ask the corpus assistant to “research” a question — it kicks off a
              long-running job and the report shows up here when it's ready.
            </Hint>
          )}
          {research_search_term && pageInfo?.hasNextPage && (
            <LoadMoreRow>
              <Button
                variant="secondary"
                onClick={handleLoadMore}
                disabled={loading}
              >
                Load more
              </Button>
            </LoadMoreRow>
          )}
        </StateWrapper>
      </Container>
    );
  }

  return (
    <Container>
      <Grid>
        {reports.map((report) => (
          <ResearchReportListCard key={report.id} report={report} />
        ))}
      </Grid>
      {pageInfo?.hasNextPage && (
        <LoadMoreRow>
          <Button
            variant="secondary"
            onClick={handleLoadMore}
            disabled={loading}
          >
            Load more
          </Button>
        </LoadMoreRow>
      )}
    </Container>
  );
};

export default CorpusResearchReportCards;
