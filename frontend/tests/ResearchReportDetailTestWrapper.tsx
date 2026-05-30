import React from "react";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { InMemoryCache } from "@apollo/client";
import { Provider } from "jotai";
import { MemoryRouter } from "react-router-dom";
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

const createTestCache = () =>
  new InMemoryCache({
    typePolicies: {
      ResearchReportType: { keyFields: ["id"] },
    },
  });

export const ResearchReportDetailTestWrapper: React.FC<{
  report: ResearchReportType;
}> = ({ report }) => {
  // Seed the entity reactive var the way CentralRouteManager would; the detail
  // view falls back to it while the query loads, so content renders immediately.
  React.useEffect(() => {
    authToken("test-token");
    openedResearchReport(report);
    return () => {
      openedResearchReport(null);
    };
  }, [report]);

  const mocks: MockedResponse[] = [
    {
      request: { query: GET_RESEARCH_REPORT, variables: { id: report.id } },
      variableMatcher: () => true,
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
            <ResearchReportDetail />
          </div>
        </MockedProvider>
      </MemoryRouter>
    </Provider>
  );
};
