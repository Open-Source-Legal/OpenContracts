import React, { useState } from "react";
import { gql, useQuery, useReactiveVar } from "@apollo/client";
import { useNavigate } from "react-router-dom";
import { Button, Table } from "@os-legal/ui";
import styled from "styled-components";
import { Activity, ArrowLeft, RefreshCw } from "lucide-react";

import {
  ErrorMessage,
  InfoMessage,
  LoadingState,
  WarningMessage,
} from "../widgets/feedback";
import {
  OS_LEGAL_COLORS,
  OS_LEGAL_TYPOGRAPHY,
} from "../../assets/configurations/osLegalStyles";
import {
  IMPORT_BATCH_TABLE_MIN_WIDTH_PX,
  INGESTION_MONITOR_PAGE_SIZE,
  INGESTION_TABLE_MIN_WIDTH_PX,
  MOBILE_VIEW_BREAKPOINT,
} from "../../assets/configurations/constants";
import {
  CardSegment as StyledSegment,
  PageHeader as BasePageHeader,
  ScrollableTableWrapper,
} from "../layout/SharedSegments";
import {
  formatFileSize,
  formatDuration,
  formatDateTime,
} from "../../utils/formatters";
import { backendUserObj } from "../../graphql/cache";

// ---------------------------------------------------------------------------
// GraphQL operations
// ---------------------------------------------------------------------------

const GET_ADMIN_DOCUMENT_INGESTION = gql`
  query GetAdminDocumentIngestion($status: String, $limit: Int, $offset: Int) {
    adminDocumentIngestion(status: $status, limit: $limit, offset: $offset) {
      totalCount
      limit
      offset
      items {
        id
        title
        creatorUsername
        creatorEmail
        fileType
        pageCount
        sizeBytes
        processingStatus
        processingError
        created
        processingStarted
        processingFinished
        elapsedSeconds
      }
    }
  }
`;

const GET_ADMIN_WORKER_UPLOADS = gql`
  query GetAdminWorkerUploads($status: String, $limit: Int, $offset: Int) {
    adminWorkerUploads(status: $status, limit: $limit, offset: $offset) {
      totalCount
      limit
      offset
      items {
        id
        corpusId
        corpusTitle
        workerAccountName
        status
        errorMessage
        fileName
        sizeBytes
        resultDocumentId
        created
        processingStarted
        processingFinished
        elapsedSeconds
      }
    }
  }
`;

const GET_ADMIN_CORPUS_IMPORTS = gql`
  query GetAdminCorpusImports($status: String, $limit: Int, $offset: Int) {
    adminCorpusImports(status: $status, limit: $limit, offset: $offset) {
      totalCount
      limit
      offset
      items {
        id
        importRunId
        corpusId
        corpusTitle
        creatorUsername
        status
        expectedDocCount
        totalCountDocs
        doneCount
        failedCount
        pendingCount
        percentFailed
        created
        modified
      }
    }
  }
`;

const GET_ADMIN_BULK_IMPORT_SESSIONS = gql`
  query GetAdminBulkImportSessions($status: String, $limit: Int, $offset: Int) {
    adminBulkImportSessions(status: $status, limit: $limit, offset: $offset) {
      totalCount
      limit
      offset
      items {
        id
        kind
        filename
        creatorUsername
        status
        errorMessage
        totalSize
        receivedSize
        receivedParts
        totalChunks
        percentComplete
        targetCorpusId
        created
        modified
      }
    }
  }
`;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface PageInfo {
  totalCount: number;
  limit: number;
  offset: number;
}

interface DocumentRow {
  id: string;
  title: string | null;
  creatorUsername: string | null;
  creatorEmail: string | null;
  fileType: string | null;
  pageCount: number | null;
  sizeBytes: number | null;
  processingStatus: string | null;
  processingError: string | null;
  created: string | null;
  processingStarted: string | null;
  processingFinished: string | null;
  elapsedSeconds: number | null;
}

interface WorkerUploadRow {
  id: string;
  corpusId: number | null;
  corpusTitle: string | null;
  workerAccountName: string | null;
  status: string | null;
  errorMessage: string | null;
  fileName: string | null;
  sizeBytes: number | null;
  resultDocumentId: number | null;
  created: string | null;
  processingStarted: string | null;
  processingFinished: string | null;
  elapsedSeconds: number | null;
}

interface CorpusImportRow {
  id: string;
  importRunId: string;
  corpusId: number | null;
  corpusTitle: string | null;
  creatorUsername: string | null;
  status: string | null;
  expectedDocCount: number | null;
  totalCountDocs: number | null;
  doneCount: number | null;
  failedCount: number | null;
  pendingCount: number | null;
  percentFailed: number | null;
  created: string | null;
  modified: string | null;
}

interface BulkSessionRow {
  id: string;
  kind: string | null;
  filename: string | null;
  creatorUsername: string | null;
  status: string | null;
  errorMessage: string | null;
  totalSize: number | null;
  receivedSize: number | null;
  receivedParts: number | null;
  totalChunks: number | null;
  percentComplete: number | null;
  targetCorpusId: string | null;
  created: string | null;
  modified: string | null;
}

type TabKey = "documents" | "imports";

// ---------------------------------------------------------------------------
// Status badge styling
// ---------------------------------------------------------------------------

type BadgeVariant = "success" | "danger" | "warning" | "info" | "neutral";

const VARIANT_COLORS: Record<BadgeVariant, { bg: string; fg: string }> = {
  success: {
    bg: OS_LEGAL_COLORS.successSurface,
    fg: OS_LEGAL_COLORS.successText,
  },
  danger: { bg: OS_LEGAL_COLORS.dangerSurface, fg: OS_LEGAL_COLORS.dangerText },
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

/** Map any backend status string (any case) onto a badge colour variant. */
function statusVariant(status: string | null | undefined): BadgeVariant {
  const s = (status || "").toLowerCase();
  if (s === "completed" || s === "done") return "success";
  if (s === "failed") return "danger";
  if (s === "processing" || s === "assembling" || s === "finalizing")
    return "info";
  if (s === "pending" || s === "enumerating" || s === "ready") return "warning";
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

const StatusBadge: React.FC<{ status: string | null | undefined }> = ({
  status,
}) => (
  <StatusPill $variant={statusVariant(status)}>
    {(status || "unknown").toLowerCase()}
  </StatusPill>
);

// ---------------------------------------------------------------------------
// Styled components
// ---------------------------------------------------------------------------

const Container = styled.div`
  /* width: 100% (with box-sizing: border-box from index.css) clamps this page to
     its parent's width. Without it the page is a flex item of the column-direction
     #AppContainer, whose default align-items: stretch does NOT shrink an item below
     the intrinsic width of its content — so a wide ScrollableTableWrapper child
     blew the page out past the viewport. body has overflow-x: hidden, so that
     overflow was clipped and unreachable: the inner table scroll never engaged
     because the wrapper itself had grown wider than the screen. max-width still
     caps + centres the page on desktop. (min-width: 0 does NOT fix this — the
     overflow is on the flex cross axis, not the main axis.) */
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

const TabBar = styled.div`
  display: flex;
  gap: 0.25rem;
  border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
  margin-bottom: 1.5rem;
`;

const TabButton = styled.button<{ $active: boolean }>`
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
  font-size: 0.95rem;
  font-weight: 600;
  padding: 0.65rem 1rem;
  background: none;
  border: none;
  border-bottom: 2px solid
    ${({ $active }) => ($active ? OS_LEGAL_COLORS.accent : "transparent")};
  color: ${({ $active }) =>
    $active ? OS_LEGAL_COLORS.textPrimary : OS_LEGAL_COLORS.textSecondary};
  cursor: pointer;
  transition: color 0.15s ease, border-color 0.15s ease;

  &:hover {
    color: ${OS_LEGAL_COLORS.textPrimary};
  }
`;

const SectionHeader = styled.div`
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
`;

const SectionTitle = styled.h2`
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
  font-size: 1.1rem;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textPrimary};
  margin: 0;
`;

const FilterRow = styled.div`
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
`;

const FilterLabel = styled.label`
  font-size: 0.8rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
`;

const FilterSelect = styled.select`
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
  font-size: 0.85rem;
  padding: 0.3rem 0.5rem;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 6px;
  background: ${OS_LEGAL_COLORS.surface};
  color: ${OS_LEGAL_COLORS.textPrimary};
  cursor: pointer;
`;

const SectionWrapper = styled.div`
  margin-bottom: 2.5rem;
`;

const TruncatedCell = styled.span`
  display: inline-block;
  max-width: 220px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  vertical-align: bottom;
`;

const ErrorCell = styled.span`
  display: inline-block;
  max-width: 240px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  vertical-align: bottom;
  color: ${OS_LEGAL_COLORS.dangerText};
  font-size: 0.8rem;
`;

const StackedCell = styled.div`
  display: flex;
  flex-direction: column;
  line-height: 1.25;
`;

const SubText = styled.span`
  font-size: 0.75rem;
  color: ${OS_LEGAL_COLORS.textTertiary};
`;

const PctFailed = styled.span<{ $danger: boolean }>`
  font-weight: 600;
  color: ${({ $danger }) =>
    $danger ? OS_LEGAL_COLORS.dangerText : OS_LEGAL_COLORS.textSecondary};
`;

const PaginationBar = styled.div`
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 0.75rem;
  margin-top: 0.75rem;
  font-size: 0.85rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
`;

// ---------------------------------------------------------------------------
// Small reusable bits
// ---------------------------------------------------------------------------

const ALL = "";

const StatusFilter: React.FC<{
  value: string;
  options: { value: string; label: string }[];
  onChange: (v: string) => void;
  testId?: string;
}> = ({ value, options, onChange, testId }) => (
  <FilterRow>
    <FilterLabel>Status</FilterLabel>
    <FilterSelect
      data-testid={testId}
      value={value}
      onChange={(e) => onChange(e.target.value)}
    >
      <option value={ALL}>All</option>
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </FilterSelect>
  </FilterRow>
);

const Pagination: React.FC<{
  page: PageInfo | undefined;
  offset: number;
  onOffsetChange: (offset: number) => void;
  testId?: string;
}> = ({ page, offset, onOffsetChange, testId }) => {
  if (!page) return null;
  const { totalCount, limit } = page;
  const shownStart = totalCount === 0 ? 0 : offset + 1;
  const shownEnd = Math.min(offset + limit, totalCount);
  const hasPrev = offset > 0;
  const hasNext = offset + limit < totalCount;
  return (
    <PaginationBar data-testid={testId}>
      <span>
        {shownStart}–{shownEnd} of {totalCount}
      </span>
      <Button
        size="sm"
        variant="secondary"
        disabled={!hasPrev}
        onClick={() => onOffsetChange(Math.max(0, offset - limit))}
      >
        Prev
      </Button>
      <Button
        size="sm"
        variant="secondary"
        disabled={!hasNext}
        onClick={() => onOffsetChange(offset + limit)}
      >
        Next
      </Button>
    </PaginationBar>
  );
};

// Status option sets — each `value` is sent verbatim as the backend status
// filter. The casing intentionally mirrors each underlying model's stored
// values (so the values read true to the data even though the service layer
// normalises case per subject: `.lower()` for documents/corpus-imports,
// `.upper()` for worker uploads/bulk sessions). Keep them mirroring the model.
// DocumentProcessingStatus values are lowercase.
const DOC_STATUS_OPTIONS = [
  { value: "pending", label: "Pending" },
  { value: "processing", label: "Processing" },
  { value: "completed", label: "Completed" },
  { value: "failed", label: "Failed" },
];
// UploadStatus values are uppercase.
const WORKER_STATUS_OPTIONS = [
  { value: "PENDING", label: "Pending" },
  { value: "PROCESSING", label: "Processing" },
  { value: "COMPLETED", label: "Completed" },
  { value: "FAILED", label: "Failed" },
];
// PendingCorpusImport.Status values are lowercase.
const CORPUS_IMPORT_STATUS_OPTIONS = [
  { value: "enumerating", label: "Enumerating" },
  { value: "ready", label: "Ready" },
  { value: "finalizing", label: "Finalizing" },
  { value: "done", label: "Done" },
  { value: "failed", label: "Failed" },
];
// ChunkedUploadStatus values are uppercase.
const BULK_SESSION_STATUS_OPTIONS = [
  { value: "PENDING", label: "Pending" },
  { value: "ASSEMBLING", label: "Assembling" },
  { value: "COMPLETED", label: "Completed" },
  { value: "FAILED", label: "Failed" },
];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export const IngestionMonitor: React.FC = () => {
  const navigate = useNavigate();
  const currentUser = useReactiveVar(backendUserObj);
  const isSuperuser = currentUser?.isSuperuser === true;

  const [activeTab, setActiveTab] = useState<TabKey>("documents");

  // Independent filter + paging state per list.
  const [docStatus, setDocStatus] = useState<string>(ALL);
  const [docOffset, setDocOffset] = useState<number>(0);
  const [workerStatus, setWorkerStatus] = useState<string>(ALL);
  const [workerOffset, setWorkerOffset] = useState<number>(0);
  const [importStatus, setImportStatus] = useState<string>(ALL);
  const [importOffset, setImportOffset] = useState<number>(0);
  const [sessionStatus, setSessionStatus] = useState<string>(ALL);
  const [sessionOffset, setSessionOffset] = useState<number>(0);

  const limit = INGESTION_MONITOR_PAGE_SIZE;
  const onDocuments = activeTab === "documents";
  const onImports = activeTab === "imports";

  const docsQuery = useQuery(GET_ADMIN_DOCUMENT_INGESTION, {
    variables: { status: docStatus || null, limit, offset: docOffset },
    skip: !isSuperuser || !onDocuments,
    fetchPolicy: "network-only",
  });
  const workerQuery = useQuery(GET_ADMIN_WORKER_UPLOADS, {
    variables: { status: workerStatus || null, limit, offset: workerOffset },
    skip: !isSuperuser || !onDocuments,
    fetchPolicy: "network-only",
  });
  const importsQuery = useQuery(GET_ADMIN_CORPUS_IMPORTS, {
    variables: { status: importStatus || null, limit, offset: importOffset },
    skip: !isSuperuser || !onImports,
    fetchPolicy: "network-only",
  });
  const sessionsQuery = useQuery(GET_ADMIN_BULK_IMPORT_SESSIONS, {
    variables: { status: sessionStatus || null, limit, offset: sessionOffset },
    skip: !isSuperuser || !onImports,
    fetchPolicy: "network-only",
  });

  const handleRefresh = () => {
    if (onDocuments) {
      docsQuery.refetch();
      workerQuery.refetch();
    } else {
      importsQuery.refetch();
      sessionsQuery.refetch();
    }
  };

  // A status-filter change should reset that list back to the first page.
  const makeStatusHandler =
    (setStatus: (v: string) => void, setOffset: (n: number) => void) =>
    (v: string) => {
      setStatus(v);
      setOffset(0);
    };

  // ``backendUserObj`` is null both while the reactive var is still loading
  // and for anonymous users. Render nothing until it resolves so the "Access
  // Denied" warning never flashes for an admin whose user object simply hasn't
  // populated yet (it appears only once we know the user is a non-superuser).
  if (currentUser === null) {
    return null;
  }

  if (!isSuperuser) {
    return (
      <Container>
        <WarningMessage title="Access Denied">
          Only administrators can view the ingestion monitor.
        </WarningMessage>
      </Container>
    );
  }

  const docPage: PageInfo | undefined = docsQuery.data?.adminDocumentIngestion;
  const docItems: DocumentRow[] =
    docsQuery.data?.adminDocumentIngestion?.items ?? [];
  const workerPage: PageInfo | undefined = workerQuery.data?.adminWorkerUploads;
  const workerItems: WorkerUploadRow[] =
    workerQuery.data?.adminWorkerUploads?.items ?? [];
  const importPage: PageInfo | undefined =
    importsQuery.data?.adminCorpusImports;
  const importItems: CorpusImportRow[] =
    importsQuery.data?.adminCorpusImports?.items ?? [];
  const sessionPage: PageInfo | undefined =
    sessionsQuery.data?.adminBulkImportSessions;
  const sessionItems: BulkSessionRow[] =
    sessionsQuery.data?.adminBulkImportSessions?.items ?? [];

  return (
    <Container>
      <BackLink onClick={() => navigate("/admin/settings")}>
        <ArrowLeft size={14} />
        Back to Admin Settings
      </BackLink>

      <PageHeader>
        <div>
          <PageTitle>
            <Activity size={28} color={OS_LEGAL_COLORS.accent} />
            Ingestion Monitor
          </PageTitle>
          <PageSubtitle>
            Diagnose document ingestion and import batches. Shows processing
            status, owners, file metadata and elapsed time — never document
            contents.
          </PageSubtitle>
        </div>
        <Button variant="secondary" onClick={handleRefresh}>
          <RefreshCw size={14} style={{ marginRight: 6 }} />
          Refresh
        </Button>
      </PageHeader>

      <TabBar>
        <TabButton
          data-testid="tab-documents"
          $active={onDocuments}
          onClick={() => setActiveTab("documents")}
        >
          Document Ingestion
        </TabButton>
        <TabButton
          data-testid="tab-imports"
          $active={onImports}
          onClick={() => setActiveTab("imports")}
        >
          Import Batches
        </TabButton>
      </TabBar>

      {onDocuments && (
        <>
          {/* ---- Documents ---- */}
          <SectionWrapper>
            <SectionHeader>
              <SectionTitle>Documents</SectionTitle>
              <StatusFilter
                testId="doc-status-filter"
                value={docStatus}
                options={DOC_STATUS_OPTIONS}
                onChange={makeStatusHandler(setDocStatus, setDocOffset)}
              />
            </SectionHeader>
            <StyledSegment>
              {docsQuery.loading ? (
                <LoadingState message="Loading documents…" />
              ) : docsQuery.error ? (
                <ErrorMessage title="Error loading documents">
                  {docsQuery.error.message}
                </ErrorMessage>
              ) : docItems.length === 0 ? (
                <InfoMessage title="No documents">
                  No documents match the selected filter.
                </InfoMessage>
              ) : (
                <ScrollableTableWrapper
                  $minWidth={`${INGESTION_TABLE_MIN_WIDTH_PX}px`}
                  data-testid="documents-table-scroll"
                >
                  <Table variant="minimal">
                    <Table.Head>
                      <Table.Row>
                        <Table.HeadCell>Owner</Table.HeadCell>
                        <Table.HeadCell>Title</Table.HeadCell>
                        <Table.HeadCell>Type</Table.HeadCell>
                        <Table.HeadCell>Size</Table.HeadCell>
                        <Table.HeadCell>Pages</Table.HeadCell>
                        <Table.HeadCell>Status</Table.HeadCell>
                        <Table.HeadCell>Elapsed</Table.HeadCell>
                        <Table.HeadCell>Created</Table.HeadCell>
                        <Table.HeadCell>Error</Table.HeadCell>
                      </Table.Row>
                    </Table.Head>
                    <Table.Body>
                      {docItems.map((d) => (
                        <Table.Row key={d.id}>
                          <Table.Cell>
                            <StackedCell>
                              <span>{d.creatorUsername || "—"}</span>
                              {d.creatorEmail && (
                                <SubText>{d.creatorEmail}</SubText>
                              )}
                            </StackedCell>
                          </Table.Cell>
                          <Table.Cell>
                            <TruncatedCell title={d.title || ""}>
                              {d.title || "—"}
                            </TruncatedCell>
                          </Table.Cell>
                          <Table.Cell>{d.fileType || "—"}</Table.Cell>
                          <Table.Cell>
                            {formatFileSize(d.sizeBytes) || "—"}
                          </Table.Cell>
                          <Table.Cell>{d.pageCount ?? "—"}</Table.Cell>
                          <Table.Cell>
                            <StatusBadge status={d.processingStatus} />
                          </Table.Cell>
                          <Table.Cell>
                            {formatDuration(d.elapsedSeconds)}
                          </Table.Cell>
                          <Table.Cell>{formatDateTime(d.created)}</Table.Cell>
                          <Table.Cell>
                            {d.processingError ? (
                              <ErrorCell title={d.processingError}>
                                {d.processingError}
                              </ErrorCell>
                            ) : (
                              "—"
                            )}
                          </Table.Cell>
                        </Table.Row>
                      ))}
                    </Table.Body>
                  </Table>
                </ScrollableTableWrapper>
              )}
              <Pagination
                page={docPage}
                offset={docOffset}
                onOffsetChange={setDocOffset}
                testId="documents-pagination"
              />
            </StyledSegment>
          </SectionWrapper>

          {/* ---- Worker upload queue ---- */}
          <SectionWrapper>
            <SectionHeader>
              <SectionTitle>Worker Upload Queue</SectionTitle>
              <StatusFilter
                testId="worker-status-filter"
                value={workerStatus}
                options={WORKER_STATUS_OPTIONS}
                onChange={makeStatusHandler(setWorkerStatus, setWorkerOffset)}
              />
            </SectionHeader>
            <StyledSegment>
              {workerQuery.loading ? (
                <LoadingState message="Loading worker uploads…" />
              ) : workerQuery.error ? (
                <ErrorMessage title="Error loading worker uploads">
                  {workerQuery.error.message}
                </ErrorMessage>
              ) : workerItems.length === 0 ? (
                <InfoMessage title="No worker uploads">
                  No worker/pipeline uploads match the selected filter.
                </InfoMessage>
              ) : (
                <ScrollableTableWrapper
                  $minWidth={`${INGESTION_TABLE_MIN_WIDTH_PX}px`}
                  data-testid="worker-uploads-table-scroll"
                >
                  <Table variant="minimal">
                    <Table.Head>
                      <Table.Row>
                        <Table.HeadCell>Worker</Table.HeadCell>
                        <Table.HeadCell>Corpus</Table.HeadCell>
                        <Table.HeadCell>File</Table.HeadCell>
                        <Table.HeadCell>Size</Table.HeadCell>
                        <Table.HeadCell>Status</Table.HeadCell>
                        <Table.HeadCell>Elapsed</Table.HeadCell>
                        <Table.HeadCell>Created</Table.HeadCell>
                        <Table.HeadCell>Error</Table.HeadCell>
                      </Table.Row>
                    </Table.Head>
                    <Table.Body>
                      {workerItems.map((w) => (
                        <Table.Row key={w.id}>
                          <Table.Cell>{w.workerAccountName || "—"}</Table.Cell>
                          <Table.Cell>
                            <TruncatedCell title={w.corpusTitle || ""}>
                              {w.corpusTitle || `#${w.corpusId ?? "?"}`}
                            </TruncatedCell>
                          </Table.Cell>
                          <Table.Cell>
                            <TruncatedCell title={w.fileName || ""}>
                              {w.fileName || "—"}
                            </TruncatedCell>
                          </Table.Cell>
                          <Table.Cell>
                            {formatFileSize(w.sizeBytes) || "—"}
                          </Table.Cell>
                          <Table.Cell>
                            <StatusBadge status={w.status} />
                          </Table.Cell>
                          <Table.Cell>
                            {formatDuration(w.elapsedSeconds)}
                          </Table.Cell>
                          <Table.Cell>{formatDateTime(w.created)}</Table.Cell>
                          <Table.Cell>
                            {w.errorMessage ? (
                              <ErrorCell title={w.errorMessage}>
                                {w.errorMessage}
                              </ErrorCell>
                            ) : (
                              "—"
                            )}
                          </Table.Cell>
                        </Table.Row>
                      ))}
                    </Table.Body>
                  </Table>
                </ScrollableTableWrapper>
              )}
              <Pagination
                page={workerPage}
                offset={workerOffset}
                onOffsetChange={setWorkerOffset}
                testId="worker-uploads-pagination"
              />
            </StyledSegment>
          </SectionWrapper>
        </>
      )}

      {onImports && (
        <>
          {/* ---- Corpus-export imports ---- */}
          <SectionWrapper>
            <SectionHeader>
              <SectionTitle>Corpus-Export Imports</SectionTitle>
              <StatusFilter
                testId="import-status-filter"
                value={importStatus}
                options={CORPUS_IMPORT_STATUS_OPTIONS}
                onChange={makeStatusHandler(setImportStatus, setImportOffset)}
              />
            </SectionHeader>
            <StyledSegment>
              {importsQuery.loading ? (
                <LoadingState message="Loading corpus imports…" />
              ) : importsQuery.error ? (
                <ErrorMessage title="Error loading corpus imports">
                  {importsQuery.error.message}
                </ErrorMessage>
              ) : importItems.length === 0 ? (
                <InfoMessage title="No corpus imports">
                  No corpus-export import runs match the selected filter.
                </InfoMessage>
              ) : (
                <ScrollableTableWrapper
                  $minWidth={`${IMPORT_BATCH_TABLE_MIN_WIDTH_PX}px`}
                  data-testid="corpus-imports-table-scroll"
                >
                  <Table variant="minimal">
                    <Table.Head>
                      <Table.Row>
                        <Table.HeadCell>Corpus</Table.HeadCell>
                        <Table.HeadCell>Owner</Table.HeadCell>
                        <Table.HeadCell>Status</Table.HeadCell>
                        <Table.HeadCell>
                          Docs (done/failed/pending)
                        </Table.HeadCell>
                        <Table.HeadCell>% Failed</Table.HeadCell>
                        <Table.HeadCell>Started</Table.HeadCell>
                        <Table.HeadCell>Updated</Table.HeadCell>
                      </Table.Row>
                    </Table.Head>
                    <Table.Body>
                      {importItems.map((imp) => (
                        <Table.Row key={imp.id}>
                          <Table.Cell>
                            <TruncatedCell title={imp.corpusTitle || ""}>
                              {imp.corpusTitle || `#${imp.corpusId ?? "?"}`}
                            </TruncatedCell>
                          </Table.Cell>
                          <Table.Cell>{imp.creatorUsername || "—"}</Table.Cell>
                          <Table.Cell>
                            <StatusBadge status={imp.status} />
                          </Table.Cell>
                          <Table.Cell>
                            {imp.doneCount ?? 0}/{imp.failedCount ?? 0}/
                            {imp.pendingCount ?? 0}
                            <SubText> of {imp.totalCountDocs ?? 0}</SubText>
                          </Table.Cell>
                          <Table.Cell>
                            <PctFailed $danger={(imp.percentFailed ?? 0) > 0}>
                              {(imp.percentFailed ?? 0).toFixed(1)}%
                            </PctFailed>
                          </Table.Cell>
                          <Table.Cell>{formatDateTime(imp.created)}</Table.Cell>
                          <Table.Cell>
                            {formatDateTime(imp.modified)}
                          </Table.Cell>
                        </Table.Row>
                      ))}
                    </Table.Body>
                  </Table>
                </ScrollableTableWrapper>
              )}
              <Pagination
                page={importPage}
                offset={importOffset}
                onOffsetChange={setImportOffset}
                testId="corpus-imports-pagination"
              />
            </StyledSegment>
          </SectionWrapper>

          {/* ---- Bulk document imports ---- */}
          <SectionWrapper>
            <SectionHeader>
              <SectionTitle>Bulk Document Imports</SectionTitle>
              <StatusFilter
                testId="session-status-filter"
                value={sessionStatus}
                options={BULK_SESSION_STATUS_OPTIONS}
                onChange={makeStatusHandler(setSessionStatus, setSessionOffset)}
              />
            </SectionHeader>
            <StyledSegment>
              {sessionsQuery.loading ? (
                <LoadingState message="Loading bulk imports…" />
              ) : sessionsQuery.error ? (
                <ErrorMessage title="Error loading bulk imports">
                  {sessionsQuery.error.message}
                </ErrorMessage>
              ) : sessionItems.length === 0 ? (
                <InfoMessage title="No bulk imports">
                  No bulk document-zip imports match the selected filter.
                </InfoMessage>
              ) : (
                <ScrollableTableWrapper
                  $minWidth={`${IMPORT_BATCH_TABLE_MIN_WIDTH_PX}px`}
                  data-testid="bulk-sessions-table-scroll"
                >
                  <Table variant="minimal">
                    <Table.Head>
                      <Table.Row>
                        <Table.HeadCell>File</Table.HeadCell>
                        <Table.HeadCell>Kind</Table.HeadCell>
                        <Table.HeadCell>Owner</Table.HeadCell>
                        <Table.HeadCell>Status</Table.HeadCell>
                        <Table.HeadCell>Progress</Table.HeadCell>
                        <Table.HeadCell>Created</Table.HeadCell>
                        <Table.HeadCell>Error</Table.HeadCell>
                      </Table.Row>
                    </Table.Head>
                    <Table.Body>
                      {sessionItems.map((s) => (
                        <Table.Row key={s.id}>
                          <Table.Cell>
                            <TruncatedCell title={s.filename || ""}>
                              {s.filename || "—"}
                            </TruncatedCell>
                          </Table.Cell>
                          <Table.Cell>{s.kind || "—"}</Table.Cell>
                          <Table.Cell>{s.creatorUsername || "—"}</Table.Cell>
                          <Table.Cell>
                            <StatusBadge status={s.status} />
                          </Table.Cell>
                          <Table.Cell>
                            <StackedCell>
                              <span>
                                {(s.percentComplete ?? 0).toFixed(0)}%
                              </span>
                              <SubText>
                                {formatFileSize(s.receivedSize)} /{" "}
                                {formatFileSize(s.totalSize) || "—"}
                              </SubText>
                            </StackedCell>
                          </Table.Cell>
                          <Table.Cell>{formatDateTime(s.created)}</Table.Cell>
                          <Table.Cell>
                            {s.errorMessage ? (
                              <ErrorCell title={s.errorMessage}>
                                {s.errorMessage}
                              </ErrorCell>
                            ) : (
                              "—"
                            )}
                          </Table.Cell>
                        </Table.Row>
                      ))}
                    </Table.Body>
                  </Table>
                </ScrollableTableWrapper>
              )}
              <Pagination
                page={sessionPage}
                offset={sessionOffset}
                onOffsetChange={setSessionOffset}
                testId="bulk-sessions-pagination"
              />
            </StyledSegment>
          </SectionWrapper>
        </>
      )}
    </Container>
  );
};

export default IngestionMonitor;
