import React from "react";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { InMemoryCache } from "@apollo/client";
import { relayStylePagination } from "@apollo/client/utilities";
import { Provider } from "jotai";
import { MemoryRouter } from "react-router-dom";
import {
  openedCorpus,
  researchSearchTerm,
  authToken,
} from "../src/graphql/cache";
import { GET_RESEARCH_REPORTS } from "../src/graphql/queries";
import { ResearchReportListItem } from "../src/types/graphql-api";
import { DEFAULT_LIST_PAGE_SIZE } from "../src/assets/configurations/constants";
import { toGlobalId } from "../src/utils/idValidation";
import { CorpusResearchReportCards } from "../src/components/research/CorpusResearchReportCards";

export const CORPUS_ID = toGlobalId("CorpusType", 1);

function reportsMock(nodes: ResearchReportListItem[]): MockedResponse {
  return {
    // Exact variables (incl. status: undefined for the "all" filter) so the
    // mock matches via @wry/equality. maxUsageCount=Infinity lets this single
    // mock serve every re-render fire — otherwise the query drains a fixed
    // bucket and the final fire resolves to an error ("No more mocked
    // responses"), which the component's error state would then surface.
    request: {
      query: GET_RESEARCH_REPORTS,
      variables: {
        corpusId: CORPUS_ID,
        status: undefined,
        limit: DEFAULT_LIST_PAGE_SIZE,
      },
    },
    maxUsageCount: Number.POSITIVE_INFINITY,
    result: {
      data: {
        researchReports: {
          edges: nodes.map((node) => ({ node })),
          pageInfo: {
            hasNextPage: false,
            hasPreviousPage: false,
            startCursor: null,
            endCursor: null,
          },
        },
      },
    },
  };
}

function reportsMocks(nodes: ResearchReportListItem[]): MockedResponse[] {
  return [reportsMock(nodes)];
}

/**
 * Mounts CorpusResearchReportCards with the openedCorpus reactive var seeded
 * (as CentralRouteManager would) and a MockedProvider for the reports
 * connection. authToken is cleared so the refetch effect stays dormant and the
 * test exercises exactly one fetch.
 */
export const CorpusResearchReportCardsTestWrapper: React.FC<{
  nodes: ResearchReportListItem[];
}> = ({ nodes }) => {
  // Seed the reactive vars SYNCHRONOUSLY, before the child first renders (a
  // useState initializer runs during this render, ahead of children). Doing it
  // in an effect would let CorpusResearchReportCards mount with a stale/leftover
  // authToken and kick off its refetch-on-auth loop before we clear it.
  React.useState(() => {
    authToken(null);
    researchSearchTerm("");
    openedCorpus({ id: CORPUS_ID } as any);
    return null;
  });

  React.useEffect(
    () => () => {
      openedCorpus(null);
      researchSearchTerm("");
    },
    []
  );

  return (
    <Provider>
      <MemoryRouter>
        <MockedProvider
          mocks={reportsMocks(nodes)}
          cache={
            new InMemoryCache({
              // Match MockedProvider's addTypename={false}: a typename-adding
              // cache would inject __typename into the query the mock link sees,
              // so the mock (authored without __typename) stops matching and the
              // query falls through to "No more mocked responses".
              addTypename: false,
              typePolicies: {
                Query: {
                  fields: {
                    // Mirror production (cache.ts) so the connection merges
                    // instead of re-driving the network-only query in a loop.
                    researchReports: relayStylePagination([
                      "corpusId",
                      "status",
                    ]),
                  },
                },
              },
            })
          }
          addTypename={false}
        >
          <div style={{ height: 700 }}>
            <CorpusResearchReportCards activeFilter="all" />
          </div>
        </MockedProvider>
      </MemoryRouter>
    </Provider>
  );
};
