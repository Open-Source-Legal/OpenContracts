import React from "react";
import { Table } from "@os-legal/ui";
import styled from "styled-components";

import { EnrichmentAnalysisRow } from "../../../graphql/mutations";
import {
  OS_LEGAL_COLORS,
  OS_LEGAL_TYPOGRAPHY,
} from "../../../assets/configurations/osLegalStyles";
import {
  CardSegment,
  ScrollableTableWrapper,
} from "../../layout/SharedSegments";
import { LoadingState, ErrorMessage } from "../../widgets/feedback";
import { formatDateTime } from "../../../utils/formatters";
import { useEnrichmentJobs } from "./useEnrichmentJobs";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface EnrichmentJobListProps {
  corpusId: string;
  /** Optional backend status filter (e.g. "RUNNING", "COMPLETED"). */
  statusFilter?: string | null;
  /**
   * Optimistic rows to prepend before the server-fetched list.
   * Rows already present (matched by id) in the fetched data are deduplicated.
   */
  extraJobs?: EnrichmentAnalysisRow[];
}

// ---------------------------------------------------------------------------
// Status badge
// ---------------------------------------------------------------------------

type BadgeVariant = "success" | "danger" | "warning" | "info" | "neutral";

const VARIANT_COLORS: Record<BadgeVariant, { bg: string; fg: string }> = {
  success: {
    bg: OS_LEGAL_COLORS.successSurface,
    fg: OS_LEGAL_COLORS.successText,
  },
  danger: {
    bg: OS_LEGAL_COLORS.dangerSurface,
    fg: OS_LEGAL_COLORS.dangerText,
  },
  warning: {
    bg: OS_LEGAL_COLORS.warningSurface,
    fg: OS_LEGAL_COLORS.warningText,
  },
  info: { bg: OS_LEGAL_COLORS.infoSurface, fg: OS_LEGAL_COLORS.infoText },
  neutral: {
    bg: OS_LEGAL_COLORS.surfaceHover,
    fg: OS_LEGAL_COLORS.textSecondary,
  },
};

/** Map any backend Analysis status string onto a badge colour variant. */
function statusVariant(status: string | null | undefined): BadgeVariant {
  const s = (status ?? "").toLowerCase();
  if (s === "completed") return "success";
  if (s === "failed") return "danger";
  if (s === "running") return "info";
  if (s === "queued" || s === "created") return "warning";
  return "neutral";
}

const StatusPill = styled.span<{ $variant: BadgeVariant }>`
  display: inline-block;
  padding: 0.15rem 0.6rem;
  border-radius: 9999px;
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: capitalize;
  white-space: nowrap;
  background: ${({ $variant }) => VARIANT_COLORS[$variant].bg};
  color: ${({ $variant }) => VARIANT_COLORS[$variant].fg};
`;

const StatusBadge: React.FC<{
  status: string | null | undefined;
}> = ({ status }) => (
  <StatusPill
    $variant={statusVariant(status)}
    data-testid="enrichment-job-status"
  >
    {(status ?? "unknown").toLowerCase()}
  </StatusPill>
);

// ---------------------------------------------------------------------------
// Styled helpers
// ---------------------------------------------------------------------------

const EmptyState = styled.div`
  padding: 2rem;
  text-align: center;
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
  font-size: 0.95rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
`;

const StackedCell = styled.div`
  display: flex;
  flex-direction: column;
  line-height: 1.25;
`;

const ErrorCell = styled.span`
  display: inline-block;
  max-width: 260px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  vertical-align: bottom;
  color: ${OS_LEGAL_COLORS.dangerText};
  font-size: 0.8rem;
`;

const ResultSummary = styled.span`
  font-size: 0.82rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
`;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const ENRICHMENT_SUFFIX = "corpus_reference_enrichment";
const CRAWL_SUFFIX = "crawl_authorities";

function jobLabel(taskName: string): string {
  if (taskName.endsWith(ENRICHMENT_SUFFIX)) return "Reference enrichment";
  if (taskName.endsWith(CRAWL_SUFFIX)) return "Authority crawl";
  return taskName;
}

interface EnrichmentResult {
  references_created?: number;
  law_references_linked?: number;
  [key: string]: unknown;
}

interface CrawlResult {
  authorities_ingested?: number;
  [key: string]: unknown;
}

function parseResultSummary(
  taskName: string,
  resultMessage: string | null | undefined
): string | null {
  if (!resultMessage) return null;
  try {
    const parsed = JSON.parse(resultMessage);
    if (taskName.endsWith(ENRICHMENT_SUFFIX)) {
      const r = parsed as EnrichmentResult;
      return `${r.references_created ?? 0} refs · ${
        r.law_references_linked ?? 0
      } linked`;
    }
    if (taskName.endsWith(CRAWL_SUFFIX)) {
      const r = parsed as CrawlResult;
      return `${r.authorities_ingested ?? 0} ingested`;
    }
  } catch {
    // non-JSON or unexpected shape — degrade gracefully
  }
  return null;
}

function elapsedLabel(
  started: string | null | undefined,
  completed: string | null | undefined
): string | null {
  if (!started || !completed) return null;
  const startMs = new Date(started).getTime();
  const endMs = new Date(completed).getTime();
  if (Number.isNaN(startMs) || Number.isNaN(endMs)) return null;
  const secs = Math.round((endMs - startMs) / 1000);
  return `${secs}s`;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export const EnrichmentJobList: React.FC<EnrichmentJobListProps> = ({
  corpusId,
  statusFilter,
  extraJobs = [],
}) => {
  const {
    jobs: fetchedJobs,
    loading,
    error,
  } = useEnrichmentJobs(corpusId, statusFilter);

  if (loading) {
    return <LoadingState message="Loading enrichment jobs…" />;
  }

  if (error) {
    return (
      <ErrorMessage title="Error loading enrichment jobs">
        {error.message}
      </ErrorMessage>
    );
  }

  // Deduplicate: once the real row arrives via refetch it supersedes the
  // optimistic copy.  Build the set of ids already returned by the server,
  // then only keep optimistic rows whose id has NOT yet been fetched.
  const fetchedIds = new Set(fetchedJobs.map((j) => j.id));
  const merged: EnrichmentAnalysisRow[] = [
    ...fetchedJobs,
    ...(extraJobs ?? []).filter((o) => !fetchedIds.has(o.id)),
  ];

  // Sort newest-first by analysisStarted (falls back to string compare which
  // is fine for ISO timestamps, and nulls sort to the end).
  const sorted = [...merged].sort((a, b) => {
    const ta = a.analysisStarted ?? "";
    const tb = b.analysisStarted ?? "";
    return tb.localeCompare(ta);
  });

  return (
    <div data-testid="enrichment-job-list">
      <CardSegment>
        {sorted.length === 0 ? (
          <EmptyState>No enrichment runs yet.</EmptyState>
        ) : (
          <ScrollableTableWrapper $minWidth="640px">
            <Table variant="minimal">
              <Table.Head>
                <Table.Row>
                  <Table.HeadCell>Job</Table.HeadCell>
                  <Table.HeadCell>Status</Table.HeadCell>
                  <Table.HeadCell>Started</Table.HeadCell>
                  <Table.HeadCell>Finished</Table.HeadCell>
                  <Table.HeadCell>Elapsed</Table.HeadCell>
                  <Table.HeadCell>Result</Table.HeadCell>
                </Table.Row>
              </Table.Head>
              <Table.Body>
                {sorted.map((job) => {
                  const label = jobLabel(job.analyzer.taskName);
                  const elapsed = elapsedLabel(
                    job.analysisStarted,
                    job.analysisCompleted
                  );
                  const summary = parseResultSummary(
                    job.analyzer.taskName,
                    job.resultMessage
                  );
                  const isFailed =
                    (job.status ?? "").toLowerCase() === "failed";

                  return (
                    <Table.Row key={job.id} data-testid="enrichment-job-row">
                      <Table.Cell>{label}</Table.Cell>
                      <Table.Cell>
                        <StatusBadge status={job.status} />
                      </Table.Cell>
                      <Table.Cell>
                        {formatDateTime(job.analysisStarted)}
                      </Table.Cell>
                      <Table.Cell>
                        {formatDateTime(job.analysisCompleted)}
                      </Table.Cell>
                      <Table.Cell>{elapsed ?? "—"}</Table.Cell>
                      <Table.Cell>
                        {isFailed && job.errorMessage ? (
                          <StackedCell>
                            <ErrorCell title={job.errorMessage}>
                              {job.errorMessage}
                            </ErrorCell>
                          </StackedCell>
                        ) : summary ? (
                          <ResultSummary>{summary}</ResultSummary>
                        ) : (
                          "—"
                        )}
                      </Table.Cell>
                    </Table.Row>
                  );
                })}
              </Table.Body>
            </Table>
          </ScrollableTableWrapper>
        )}
      </CardSegment>
    </div>
  );
};

export default EnrichmentJobList;
