import React from "react";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { InMemoryCache } from "@apollo/client";
import { Provider } from "jotai";
import { MemoryRouter, useLocation } from "react-router-dom";
import { ResearchReportDetail } from "../src/views/ResearchReportDetail";
import { openedResearchReport, authToken } from "../src/graphql/cache";
import { GET_RESEARCH_REPORT } from "../src/graphql/queries";
import { JobStatus, ResearchReportType } from "../src/types/graphql-api";
import { toGlobalId } from "../src/utils/idValidation";

/**
 * Build a mock research report. Defaults describe a COMPLETED report with one
 * citation and one source document; override `status`/fields for other states.
 */
export function buildMockReport(
  overrides: Partial<ResearchReportType> = {}
): ResearchReportType {
  const corpus = {
    id: toGlobalId("CorpusType", 1),
    slug: "cases",
    title: "Cases",
    creator: { id: toGlobalId("UserType", 1), slug: "john" },
  };

  return {
    id: toGlobalId("ResearchReportType", 1),
    status: JobStatus.Completed,
    prompt: "Find every indemnification clause across the corpus.",
    title: "Indemnification Review",
    slug: "indemnification-review",
    content:
      "## Summary\n\nThe corpus contains several indemnification clauses.[^1]\n\n## Sources\n\n[^1]: Doc A page 2",
    findings: [],
    citations: [
      {
        footnote: 1,
        annotation_id: 10,
        document_id: 1,
        page: 2,
        raw_text: "indemnify and hold harmless",
        display: 'Doc A (doc 1) page 2 — "indemnify and hold harmless"',
      },
    ],
    toolCallLog: [],
    modelUsage: { total_tokens: 1234 },
    warnings: [],
    durationSeconds: 125,
    stepCount: 12,
    maxSteps: 60,
    cancelRequested: false,
    errorMessage: "",
    created: "2026-05-28T12:00:00Z",
    modified: "2026-05-28T12:10:00Z",
    startedAt: "2026-05-28T12:00:05Z",
    completedAt: "2026-05-28T12:02:10Z",
    lastProgressAt: "2026-05-28T12:02:00Z",
    myPermissions: [
      "read_researchreport",
      "update_researchreport",
      "remove_researchreport",
    ],
    corpus,
    fullSourceAnnotationList: [
      {
        id: toGlobalId("ServerAnnotationType", 10),
        page: 2,
        rawText: "indemnify",
      },
    ],
    fullSourceDocumentList: [
      {
        id: toGlobalId("DocumentType", 1),
        slug: "doc-a",
        title: "Doc A",
        creator: { id: toGlobalId("UserType", 1), slug: "john" },
        corpus,
      },
    ],
    ...overrides,
    // Single cast at the boundary keeps the factory readable — production
    // types are still enforced everywhere the real report flows.
  } as unknown as ResearchReportType;
}

/**
 * Hidden probe that mirrors the in-memory router location into the DOM.
 * MemoryRouter never touches ``window.location``, so client-side navigations
 * (e.g. clicking a report-body footnote) are invisible to ``page.url()``; this
 * lets a test assert where ``navigate()`` actually went.
 */
const LocationProbe: React.FC = () => {
  const location = useLocation();
  return (
    <div data-testid="router-location" style={{ display: "none" }}>
      {location.pathname + location.search}
    </div>
  );
};

const createTestCache = () =>
  new InMemoryCache({
    typePolicies: {
      ResearchReportType: { keyFields: ["id"] },
    },
  });

export const ResearchReportDetailTestWrapper: React.FC<{
  report: ResearchReportType;
}> = ({ report }) => {
  // Seed the entity reactive var the way CentralRouteManager would, BEFORE the
  // child's first render, using the synchronous useState-initializer trick
  // (same pattern as CorpusResearchReportCardsTestWrapper). A useEffect fires
  // only AFTER the first render, so the detail view would flash its "not found"
  // state for one frame — a flakiness risk on slow CI.
  React.useState(() => {
    authToken("test-token");
    openedResearchReport(report);
    return null;
  });
  // Reset on unmount so the seeded var doesn't leak across tests.
  React.useEffect(() => {
    return () => {
      openedResearchReport(null);
    };
  }, []);

  const mocks: MockedResponse[] = [
    {
      request: { query: GET_RESEARCH_REPORT, variables: { id: report.id } },
      // maxUsageCount=Infinity lets this single mock serve every fire of the
      // query — the detail view uses notifyOnNetworkStatusChange and may
      // refetch (terminal-notification path) or poll (non-terminal states).
      // Without it a second trip drains the bucket and resolves to a "No more
      // mocked responses" error, which the view's not-found state would surface.
      // Mirrors CorpusResearchReportCardsTestWrapper.
      maxUsageCount: Number.POSITIVE_INFINITY,
      result: { data: { researchReport: report } },
    },
  ];

  return (
    <Provider>
      <MemoryRouter initialEntries={[`/research/${report.slug}`]}>
        <MockedProvider
          mocks={mocks}
          cache={createTestCache()}
          addTypename={false}
        >
          <div style={{ height: 800 }}>
            <LocationProbe />
            <ResearchReportDetail />
          </div>
        </MockedProvider>
      </MemoryRouter>
    </Provider>
  );
};
