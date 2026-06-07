import React, { useState, useEffect, useMemo } from "react";
import styled, { keyframes } from "styled-components";
import { OS_LEGAL_COLORS } from "../assets/configurations/osLegalStyles";
import {
  PageContainer,
  ContentContainer,
} from "../components/layout/PageLayout";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useReactiveVar } from "@apollo/client";
import { toast } from "react-toastify";
import {
  Button,
  Chip,
  StatBlock,
  StatGrid,
  Tabs,
  TabList,
  Tab,
  TabPanels,
  TabPanel,
  EmptyState,
} from "@os-legal/ui";
import {
  ArrowLeft,
  RefreshCw,
  XCircle,
  FileText,
  Quote,
  FileStack,
  Activity,
  AlertTriangle,
} from "lucide-react";

import type { Components } from "react-markdown";

import {
  CorpusType,
  DocumentType,
  JobStatus,
  ResearchCitation,
  ResearchReportType,
} from "../types/graphql-api";
import { openedResearchReport } from "../graphql/cache";
import {
  GET_RESEARCH_REPORT,
  GetResearchReportInput,
  GetResearchReportOutput,
} from "../graphql/queries";
import {
  CANCEL_RESEARCH_REPORT,
  CancelResearchReportInput,
  CancelResearchReportOutput,
} from "../graphql/mutations";
import {
  RESEARCH_REPORT_POLL_INTERVAL_MS,
  RESEARCH_REPORT_UPDATE_PERMISSION,
} from "../assets/configurations/constants";
import {
  getResearchStatus,
  formatResearchDate,
  formatResearchDuration,
  isTerminalResearchStatus,
} from "../utils/researchUtils";
import { getCorpusUrl, getDocumentUrl } from "../utils/navigationUtils";
import { getNumericIdFromGlobalId } from "../utils/idValidation";
import { SafeMarkdown } from "../components/knowledge_base/markdown/SafeMarkdown";
import { useResearchCompletionNotification } from "../hooks/useResearchCompletionNotification";

// ═══════════════════════════════════════════════════════════════════════════
// STYLED COMPONENTS (vocabulary mirrors views/ExtractDetail.tsx)
// ═══════════════════════════════════════════════════════════════════════════

const BackButton = styled.button`
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 24px;
  padding: 8px 0;
  font-size: 14px;
  font-weight: 500;
  color: ${OS_LEGAL_COLORS.textSecondary};
  background: none;
  border: none;
  cursor: pointer;
  transition: color 0.15s;

  &:hover {
    color: ${OS_LEGAL_COLORS.textPrimary};
  }
`;

const Header = styled.header`
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 32px;

  @media (max-width: 768px) {
    flex-direction: column;
  }
`;

const HeaderMain = styled.div`
  flex: 1;
  min-width: 0;
`;

const TitleRow = styled.div`
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
  flex-wrap: wrap;
`;

const Title = styled.h1`
  font-family: "Georgia", "Times New Roman", serif;
  font-size: 32px;
  font-weight: 400;
  color: ${OS_LEGAL_COLORS.textPrimary};
  margin: 0;
  line-height: 1.2;

  @media (max-width: 768px) {
    font-size: 26px;
  }
`;

const Meta = styled.div`
  font-size: 14px;
  color: ${OS_LEGAL_COLORS.textSecondary};
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
`;

const MetaSeparator = styled.span`
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: ${OS_LEGAL_COLORS.textMuted};
`;

const Actions = styled.div`
  display: flex;
  gap: 8px;
  flex-shrink: 0;

  @media (max-width: 768px) {
    width: 100%;
  }
`;

const IconButton = styled.button`
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  padding: 0;
  background: transparent;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 8px;
  color: ${OS_LEGAL_COLORS.textSecondary};
  cursor: pointer;
  transition: all 0.15s;

  &:hover {
    border-color: ${OS_LEGAL_COLORS.borderHover};
    color: ${OS_LEGAL_COLORS.textPrimary};
  }
`;

const StatsSection = styled.div`
  margin-bottom: 32px;
`;

const TabsSection = styled.div`
  margin-bottom: 24px;
`;

const spin = keyframes`
  to { transform: rotate(360deg); }
`;

const RunningState = styled.div`
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 56px 24px;
  background: ${OS_LEGAL_COLORS.surface};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 12px;
`;

const Spinner = styled.div`
  width: 36px;
  height: 36px;
  border: 3px solid ${OS_LEGAL_COLORS.border};
  border-top-color: ${OS_LEGAL_COLORS.textSecondary};
  border-radius: 50%;
  animation: ${spin} 0.9s linear infinite;
  margin-bottom: 20px;
`;

const RunningTitle = styled.h3`
  font-size: 18px;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textPrimary};
  margin: 0 0 8px;
`;

const RunningDescription = styled.p`
  font-size: 14px;
  color: ${OS_LEGAL_COLORS.textSecondary};
  margin: 0 0 20px;
  max-width: 440px;
`;

const ProgressTrack = styled.div`
  width: 100%;
  max-width: 320px;
  height: 6px;
  background: ${OS_LEGAL_COLORS.surfaceLight};
  border-radius: 999px;
  overflow: hidden;
`;

const ProgressFill = styled.div<{ $pct: number }>`
  height: 100%;
  width: ${(p) => Math.max(2, Math.min(100, p.$pct))}%;
  background: ${OS_LEGAL_COLORS.textSecondary};
  border-radius: 999px;
  transition: width 0.4s ease;
`;

const ProgressLabel = styled.div`
  font-size: 12px;
  color: ${OS_LEGAL_COLORS.textMuted};
  margin-top: 10px;
`;

const PromptCard = styled.div`
  padding: 16px 18px;
  background: ${OS_LEGAL_COLORS.surfaceLight};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 10px;
  font-size: 14px;
  color: ${OS_LEGAL_COLORS.textSecondary};
  margin-bottom: 24px;
  line-height: 1.55;
`;

const PromptLabel = styled.div`
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: ${OS_LEGAL_COLORS.textMuted};
  margin-bottom: 6px;
`;

const MarkdownWrapper = styled.div`
  margin-top: 24px;
  font-size: 15px;
  line-height: 1.7;
  color: ${OS_LEGAL_COLORS.textPrimary};

  h1,
  h2,
  h3 {
    font-family: "Georgia", "Times New Roman", serif;
    color: ${OS_LEGAL_COLORS.textPrimary};
  }

  a {
    color: ${OS_LEGAL_COLORS.textSecondary};
    text-decoration: underline;
  }

  .footnotes {
    margin-top: 32px;
    padding-top: 16px;
    border-top: 1px solid ${OS_LEGAL_COLORS.border};
    font-size: 13px;
    color: ${OS_LEGAL_COLORS.textSecondary};
  }
`;

// A footnote definition that resolves to a cited annotation. Rendered as a
// click target (not an ``<a>``) so the inner ``↩`` back-reference anchor stays
// valid — wrapping the whole ``<li>`` in an anchor would nest anchors.
const FootnoteItem = styled.li`
  cursor: pointer;
  border-radius: 6px;
  padding: 2px 6px;
  margin: 0 -6px;
  transition: background 0.15s, color 0.15s;

  &:hover {
    background: ${OS_LEGAL_COLORS.surfaceLight};
    color: ${OS_LEGAL_COLORS.textPrimary};
  }

  &:focus-visible {
    outline: 2px solid ${OS_LEGAL_COLORS.borderHover};
    outline-offset: 2px;
  }
`;

const List = styled.div`
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 24px;
`;

const Row = styled.div`
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 14px 16px;
  background: ${OS_LEGAL_COLORS.surface};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 8px;
`;

// Internal document/citation links must route client-side — a bare ``<a
// href>`` to an in-app path (``/d/...``) triggers a full page reload.
const RowLink = styled(Link)`
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 14px 16px;
  background: ${OS_LEGAL_COLORS.surface};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 8px;
  text-decoration: none;
  color: inherit;
  transition: border-color 0.15s;

  &:hover {
    border-color: ${OS_LEGAL_COLORS.borderHover};
  }
`;

const FootnoteBadge = styled.span`
  flex-shrink: 0;
  min-width: 24px;
  height: 24px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0 6px;
  border-radius: 6px;
  background: ${OS_LEGAL_COLORS.surfaceLight};
  color: ${OS_LEGAL_COLORS.textSecondary};
  font-size: 12px;
  font-weight: 600;
`;

const RowBody = styled.div`
  flex: 1;
  min-width: 0;
`;

const RowTitle = styled.div`
  font-size: 14px;
  font-weight: 500;
  color: ${OS_LEGAL_COLORS.textPrimary};
`;

const RowMeta = styled.div`
  font-size: 12px;
  color: ${OS_LEGAL_COLORS.textMuted};
  margin-top: 3px;
  word-break: break-word;
`;

const RunDetailBlock = styled.div`
  margin-top: 24px;
`;

const RunDetailLabel = styled.div`
  font-size: 13px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: ${OS_LEGAL_COLORS.textSecondary};
  margin-bottom: 8px;
`;

const CodeBlock = styled.pre`
  background: ${OS_LEGAL_COLORS.surfaceLight};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 8px;
  padding: 14px 16px;
  font-size: 12.5px;
  line-height: 1.5;
  overflow-x: auto;
  color: ${OS_LEGAL_COLORS.textSecondary};
  white-space: pre-wrap;
  word-break: break-word;
`;

const WarningChip = styled.div`
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  margin: 0 8px 8px 0;
  border-radius: 999px;
  background: ${OS_LEGAL_COLORS.warningSurface};
  color: ${OS_LEGAL_COLORS.warningText};
  font-size: 12px;
`;

const EmptyWrapper = styled.div`
  padding: 32px 0;
`;

const TabPanelInner = styled.div`
  padding-top: 8px;
`;

// ═══════════════════════════════════════════════════════════════════════════

/**
 * Build the in-app deep-link for a single citation: the cited document, with
 * the cited annotation selected via ``?ann=<globalId>``.
 *
 * The annotation's *canonical* global ID is taken from ``annGlobalIdByPk``
 * (seeded from the server's ``fullSourceAnnotationList``) rather than
 * reconstructed from the raw PK — the GraphQL typename is ``ServerAnnotationType``,
 * so a ``toGlobalId("AnnotationType", pk)`` guess would deep-link to the wrong
 * (or no) entity. Returns ``null`` when the document is unknown or slugs are
 * missing (``getDocumentUrl`` yields ``"#"``). Shared by the Citations tab rows
 * and the report-body ``## Sources`` footnotes so both stay in lock-step.
 */
function buildCitationHref(
  citation: ResearchCitation,
  docsByPk: Map<number, DocumentType>,
  annGlobalIdByPk: Map<number, string>,
  corpus: CorpusType | null | undefined
): string | null {
  const docPk =
    citation.document_id != null ? Number(citation.document_id) : null;
  const doc = docPk != null ? docsByPk.get(docPk) : undefined;
  if (!doc || !corpus) return null;

  const annPk =
    citation.annotation_id != null ? Number(citation.annotation_id) : null;
  const annGlobalId = annPk != null ? annGlobalIdByPk.get(annPk) : undefined;

  const href = getDocumentUrl(doc, corpus, {
    annotationIds: annGlobalId ? [annGlobalId] : undefined,
  });
  return href && href !== "#" ? href : null;
}

/**
 * ResearchReportDetail - read-only detail view for a deep-research report at
 * /research/:slug. Reports are creator-only (v1) — no sharing controls.
 *
 * Seeds from the openedResearchReport reactive var (set by CentralRouteManager)
 * and refetches the full report via GET_RESEARCH_REPORT. While the job is
 * non-terminal it polls for live stepCount/lastProgressAt and also listens for
 * the terminal WebSocket notification to refetch + stop polling promptly.
 */
export const ResearchReportDetail: React.FC = () => {
  const navigate = useNavigate();
  const reportVar = useReactiveVar(openedResearchReport);
  const [activeTab, setActiveTab] = useState("report");

  const { data, refetch, startPolling, stopPolling } = useQuery<
    GetResearchReportOutput,
    GetResearchReportInput
  >(GET_RESEARCH_REPORT, {
    variables: { id: reportVar?.id ?? "" },
    skip: !reportVar?.id,
    notifyOnNetworkStatusChange: true,
  });

  // Prefer freshly-fetched data; fall back to the route-resolved snapshot.
  const report: ResearchReportType | null = data?.researchReport ?? reportVar;
  const status = report?.status;
  const isTerminal = isTerminalResearchStatus(status);

  // Poll while the job is running/queued; stop once terminal (no server
  // progress events in v1). startPolling/stopPolling are no-ops when skipped.
  useEffect(() => {
    if (!report?.id) return;
    if (!isTerminal) {
      startPolling(RESEARCH_REPORT_POLL_INTERVAL_MS);
    } else {
      stopPolling();
    }
    return () => stopPolling();
  }, [report?.id, isTerminal, startPolling, stopPolling]);

  // Refetch + stop polling the moment a terminal notification lands.
  useResearchCompletionNotification({
    reportId: report?.id ?? null,
    onComplete: () => {
      refetch();
    },
    enabled: Boolean(report?.id) && !isTerminal,
  });

  const [cancelReport, { loading: cancelLoading }] = useMutation<
    CancelResearchReportOutput,
    CancelResearchReportInput
  >(CANCEL_RESEARCH_REPORT);

  const handleBack = () => {
    const url = getCorpusUrl(report?.corpus, { tab: "research" });
    if (url !== "#") {
      navigate(url);
    } else {
      // No corpus context (e.g. arrived via a direct link); fall back to home
      // rather than navigate(-1), which dead-ends when there's no history.
      navigate("/");
    }
  };

  const handleCancel = async () => {
    if (!report?.id) return;
    try {
      const res = await cancelReport({ variables: { id: report.id } });
      const payload = res.data?.cancelResearchReport;
      if (payload?.ok) {
        toast.success("Cancellation requested. The job will stop shortly.");
        refetch();
      } else {
        toast.error(payload?.message || "Could not cancel the research job.");
      }
    } catch (e) {
      console.error("Failed to cancel research report:", e);
      toast.error("Could not cancel the research job.");
    }
  };

  // Map raw document PKs (in the citations JSON) → source document objects so
  // citation rows can deep-link to the cited document.
  const docsByPk = useMemo(() => {
    const map = new Map<number, DocumentType>();
    (report?.fullSourceDocumentList ?? []).forEach((doc) => {
      try {
        map.set(getNumericIdFromGlobalId(doc.id), doc);
      } catch {
        // skip undecodable ids
      }
    });
    return map;
  }, [report?.fullSourceDocumentList]);

  // Map raw annotation PKs (in the citations JSON) → the canonical global ID
  // the backend emitted in ``fullSourceAnnotationList``. Reconstructing the
  // global ID via ``toGlobalId("AnnotationType", pk)`` would guess the wrong
  // typename — annotations are emitted as ``ServerAnnotationType`` — producing
  // a deep-link that resolves to the wrong (or no) entity. Using the server's
  // own ``id`` keeps the link correct regardless of the GraphQL type name.
  const annGlobalIdByPk = useMemo(() => {
    const map = new Map<number, string>();
    (report?.fullSourceAnnotationList ?? []).forEach((ann) => {
      try {
        map.set(getNumericIdFromGlobalId(ann.id), ann.id);
      } catch {
        // skip undecodable ids
      }
    });
    return map;
  }, [report?.fullSourceAnnotationList]);

  // Map footnote number → cited-source deep-link, so the report body's
  // ``## Sources`` footnotes (rendered markdown) become click-to-source links,
  // mirroring the Citations tab. Keyed by the ``[^n]`` footnote number the
  // backend emits (``citation.footnote``), which is what react-markdown surfaces
  // on each footnote ``<li id="user-content-fn-n">``.
  const footnoteHrefByNumber = useMemo(() => {
    const map = new Map<number, string>();
    (report?.citations ?? []).forEach((c) => {
      if (c.footnote == null) return;
      const href = buildCitationHref(
        c,
        docsByPk,
        annGlobalIdByPk,
        report?.corpus
      );
      if (href) map.set(Number(c.footnote), href);
    });
    return map;
  }, [report?.citations, docsByPk, annGlobalIdByPk, report?.corpus]);

  // Footnote definitions in the report body deep-link to their cited source.
  // Only footnote ``<li>``s (id ``user-content-fn-<n>``) are upgraded; ordinary
  // list items render untouched. Navigation is client-side (``navigate``) and a
  // click on the inner ``↩`` back-reference anchor is left to its native scroll.
  const reportMarkdownComponents = useMemo<Components>(
    () => ({
      li: ({ node, children, ...props }) => {
        const id = typeof props.id === "string" ? props.id : undefined;
        const match = id ? /^user-content-fn-(\d+)$/.exec(id) : null;
        const href = match
          ? footnoteHrefByNumber.get(Number(match[1]))
          : undefined;
        if (!href) {
          return <li {...props}>{children}</li>;
        }
        return (
          <FootnoteItem
            {...props}
            role="link"
            tabIndex={0}
            title="Open the cited source"
            onClick={(e) => {
              // Defer to the back-reference anchor's native ``#fnref`` scroll.
              if ((e.target as HTMLElement).closest("a")) return;
              navigate(href);
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                navigate(href);
              }
            }}
          >
            {children}
          </FootnoteItem>
        );
      },
    }),
    [footnoteHrefByNumber, navigate]
  );

  const statusProps = report ? getResearchStatus(status) : null;
  const canCancel =
    !isTerminal &&
    Boolean(report?.myPermissions?.includes(RESEARCH_REPORT_UPDATE_PERMISSION));

  const citations = report?.citations ?? [];
  const sourceDocs = report?.fullSourceDocumentList ?? [];
  const warnings = report?.warnings ?? [];

  // Not found / not yet resolved
  if (!report) {
    return (
      <PageContainer>
        <ContentContainer $maxWidth="wide" $compact>
          <BackButton onClick={handleBack}>
            <ArrowLeft size={16} />
            Back
          </BackButton>
          <EmptyWrapper>
            <EmptyState
              icon={<FileText />}
              title="Research report not found"
              description="This research report doesn't exist or you don't have access."
              size="lg"
            />
          </EmptyWrapper>
        </ContentContainer>
      </PageContainer>
    );
  }

  // Non-terminal states: the report is still being produced. Named "active"
  // (not "isRunning") because it also covers the pre-run Created/Queued states.
  const isActive =
    status === JobStatus.Created ||
    status === JobStatus.Queued ||
    status === JobStatus.Running;
  const isFailed = status === JobStatus.Failed;
  const isCompleted = status === JobStatus.Completed;
  const isCancelled = status === JobStatus.Cancelled;
  const stepPct =
    report.maxSteps && report.maxSteps > 0
      ? ((report.stepCount ?? 0) / report.maxSteps) * 100
      : 0;

  return (
    <PageContainer>
      <ContentContainer $maxWidth="wide" $compact>
        <BackButton onClick={handleBack}>
          <ArrowLeft size={16} />
          Back to Research
        </BackButton>

        {/* Header */}
        <Header>
          <HeaderMain>
            <TitleRow>
              <Title>{report.title}</Title>
              {statusProps && (
                <Chip size="sm" color={statusProps.color} static>
                  {statusProps.label}
                </Chip>
              )}
            </TitleRow>
            <Meta>
              {report.corpus?.title && <span>from {report.corpus.title}</span>}
              {report.corpus?.title && <MetaSeparator />}
              <span>Created {formatResearchDate(report.created)}</span>
              {report.completedAt && (
                <>
                  <MetaSeparator />
                  <span>Finished {formatResearchDate(report.completedAt)}</span>
                </>
              )}
            </Meta>
          </HeaderMain>
          <Actions>
            {canCancel && (
              <Button
                variant="secondary"
                size="sm"
                leftIcon={<XCircle size={16} />}
                onClick={handleCancel}
                disabled={cancelLoading || report.cancelRequested}
              >
                {report.cancelRequested ? "Cancelling…" : "Cancel"}
              </Button>
            )}
            <IconButton aria-label="Refresh" onClick={() => refetch()}>
              <RefreshCw size={16} />
            </IconButton>
          </Actions>
        </Header>

        {/* Active (created / queued / running) state */}
        {isActive && (
          <>
            <PromptCard>
              <PromptLabel>Research task</PromptLabel>
              {report.prompt}
            </PromptCard>
            <RunningState>
              <Spinner />
              <RunningTitle>
                {status === JobStatus.Running
                  ? "Research in progress…"
                  : "Queued…"}
              </RunningTitle>
              <RunningDescription>
                This runs autonomously (typically 5–30 minutes). You can leave
                this page — we'll notify you when the report is ready.
              </RunningDescription>
              <ProgressTrack>
                <ProgressFill $pct={stepPct} />
              </ProgressTrack>
              <ProgressLabel>
                Step {report.stepCount ?? 0} of {report.maxSteps ?? "—"}
                {report.lastProgressAt
                  ? ` · last activity ${new Date(
                      report.lastProgressAt
                    ).toLocaleTimeString()}`
                  : ""}
              </ProgressLabel>
            </RunningState>
          </>
        )}

        {/* Failed state */}
        {isFailed && (
          <EmptyWrapper>
            <EmptyState
              icon={<AlertTriangle />}
              title="Research failed"
              description={
                report.errorMessage ||
                "The research job could not be completed."
              }
              size="lg"
            />
          </EmptyWrapper>
        )}

        {/* Completed / cancelled: stats + report */}
        {(isCompleted || isCancelled) && (
          <>
            <StatsSection>
              <StatGrid columns={4}>
                <StatBlock
                  value={formatResearchDuration(report.durationSeconds) ?? "—"}
                  label="Duration"
                  sublabel="wall clock"
                />
                <StatBlock
                  value={`${report.stepCount ?? 0}`}
                  label="Steps"
                  sublabel={`of ${report.maxSteps ?? "—"} budget`}
                />
                <StatBlock
                  value={`${sourceDocs.length}`}
                  label="Sources"
                  sublabel="documents"
                />
                <StatBlock
                  value={`${citations.length}`}
                  label="Citations"
                  sublabel="footnotes"
                />
              </StatGrid>
            </StatsSection>

            {warnings.length > 0 && (
              <div>
                {warnings.map((w) => (
                  <WarningChip key={String(w)}>
                    <AlertTriangle size={12} />
                    {String(w)}
                  </WarningChip>
                ))}
              </div>
            )}

            <TabsSection>
              <Tabs value={activeTab} onChange={setActiveTab}>
                <TabList>
                  <Tab value="report">
                    <FileText size={14} /> Report
                  </Tab>
                  <Tab value="citations">
                    <Quote size={14} /> Citations ({citations.length})
                  </Tab>
                  <Tab value="sources">
                    <FileStack size={14} /> Sources ({sourceDocs.length})
                  </Tab>
                  <Tab value="details">
                    <Activity size={14} /> Run details
                  </Tab>
                </TabList>

                <TabPanels>
                  {/* Report */}
                  <TabPanel value="report">
                    <TabPanelInner>
                      {report.content ? (
                        <MarkdownWrapper>
                          <SafeMarkdown components={reportMarkdownComponents}>
                            {report.content}
                          </SafeMarkdown>
                        </MarkdownWrapper>
                      ) : (
                        <EmptyWrapper>
                          <EmptyState
                            title="No report body"
                            description="This run finished without a rendered report."
                            size="md"
                          />
                        </EmptyWrapper>
                      )}
                    </TabPanelInner>
                  </TabPanel>

                  {/* Citations */}
                  <TabPanel value="citations">
                    <TabPanelInner>
                      {citations.length === 0 ? (
                        <EmptyWrapper>
                          <EmptyState
                            title="No citations"
                            description="This report did not cite any sources."
                            size="md"
                          />
                        </EmptyWrapper>
                      ) : (
                        <List>
                          {citations.map((c, i) => {
                            const href = buildCitationHref(
                              c,
                              docsByPk,
                              annGlobalIdByPk,
                              report.corpus
                            );
                            const text =
                              c.display || c.raw_text || `Source ${c.footnote}`;
                            // Footnotes are unique per report, so they make a
                            // stable key (index-only keys break row identity
                            // when the conditional flips between RowLink/Row).
                            const rowKey =
                              c.footnote != null
                                ? `fn-${c.footnote}`
                                : `i-${i}`;
                            const inner = (
                              <>
                                <FootnoteBadge>{c.footnote}</FootnoteBadge>
                                <RowBody>
                                  <RowMeta>{text}</RowMeta>
                                </RowBody>
                              </>
                            );
                            return href ? (
                              <RowLink key={rowKey} to={href}>
                                {inner}
                              </RowLink>
                            ) : (
                              <Row key={rowKey}>{inner}</Row>
                            );
                          })}
                        </List>
                      )}
                    </TabPanelInner>
                  </TabPanel>

                  {/* Sources */}
                  <TabPanel value="sources">
                    <TabPanelInner>
                      {sourceDocs.length === 0 ? (
                        <EmptyWrapper>
                          <EmptyState
                            title="No source documents"
                            description="No documents were recorded for this run."
                            size="md"
                          />
                        </EmptyWrapper>
                      ) : (
                        <List>
                          {sourceDocs.map((doc) => {
                            const href = getDocumentUrl(
                              doc,
                              report.corpus ?? undefined
                            );
                            const inner = (
                              <>
                                <FileText
                                  size={18}
                                  color={OS_LEGAL_COLORS.textMuted}
                                />
                                <RowBody>
                                  <RowTitle>
                                    {doc.title || "Untitled document"}
                                  </RowTitle>
                                </RowBody>
                              </>
                            );
                            return href && href !== "#" ? (
                              <RowLink key={doc.id} to={href}>
                                {inner}
                              </RowLink>
                            ) : (
                              <Row key={doc.id}>{inner}</Row>
                            );
                          })}
                        </List>
                      )}
                    </TabPanelInner>
                  </TabPanel>

                  {/* Run details */}
                  <TabPanel value="details">
                    <TabPanelInner>
                      <RunDetailBlock>
                        <RunDetailLabel>Task</RunDetailLabel>
                        <PromptCard>{report.prompt}</PromptCard>
                      </RunDetailBlock>
                      {report.modelUsage &&
                        Object.keys(report.modelUsage).length > 0 && (
                          <RunDetailBlock>
                            <RunDetailLabel>Model usage</RunDetailLabel>
                            <CodeBlock>
                              {JSON.stringify(report.modelUsage, null, 2)}
                            </CodeBlock>
                          </RunDetailBlock>
                        )}
                      {report.toolCallLog && report.toolCallLog.length > 0 && (
                        <RunDetailBlock>
                          <RunDetailLabel>
                            Tool calls ({report.toolCallLog.length})
                          </RunDetailLabel>
                          <CodeBlock>
                            {JSON.stringify(report.toolCallLog, null, 2)}
                          </CodeBlock>
                        </RunDetailBlock>
                      )}
                    </TabPanelInner>
                  </TabPanel>
                </TabPanels>
              </Tabs>
            </TabsSection>
          </>
        )}
      </ContentContainer>
    </PageContainer>
  );
};

export default ResearchReportDetail;
