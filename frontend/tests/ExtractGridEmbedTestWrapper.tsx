/**
 * Test wrapper for ExtractGridEmbed.
 *
 * Provides MockedProvider with GraphQL mocks for the GET_EXTRACT_GRID_EMBED
 * query. Supports multiple visual states: loading, error, empty, and populated.
 */
import React from "react";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { InMemoryCache } from "@apollo/client";
import { MemoryRouter } from "react-router-dom";
import { Provider } from "jotai";

import { ExtractGridEmbed } from "../src/components/extracts/ExtractGridEmbed";
import { GET_EXTRACT_GRID_EMBED } from "../src/graphql/queries";
import { EXTRACT_GRID_EMBED_MAX_CELLS } from "../src/assets/configurations/constants";

const TEST_EXTRACT_ID = "RXh0cmFjdFR5cGU6MQ==";

/**
 * Variables passed to GET_EXTRACT_GRID_EMBED. The component sends
 * `datacellFirst: EXTRACT_GRID_EMBED_MAX_CELLS` as a payload cap, so the mock
 * variables must match exactly (Apollo's MockedProvider compares variables
 * by deep equality).
 */
const DEFAULT_QUERY_VARIABLES = {
  extractId: TEST_EXTRACT_ID,
  datacellFirst: EXTRACT_GRID_EMBED_MAX_CELLS,
};

/** Mock: populated extract with 2 documents and 2 columns */
const populatedExtractMock: MockedResponse = {
  request: {
    query: GET_EXTRACT_GRID_EMBED,
    variables: DEFAULT_QUERY_VARIABLES,
  },
  result: {
    data: {
      extract: {
        __typename: "ExtractType",
        id: TEST_EXTRACT_ID,
        name: "Contract Key Terms",
        corpus: {
          __typename: "CorpusType",
          id: "Q29ycHVzVHlwZTox",
          slug: "supply-chain-analysis",
          creator: { __typename: "UserType", slug: "test-user" },
        },
        fieldset: {
          __typename: "FieldsetType",
          id: "fieldset-1",
          fullColumnList: [
            { __typename: "ColumnType", id: "col-1", name: "Effective Date" },
            { __typename: "ColumnType", id: "col-2", name: "Governing Law" },
          ],
        },
        fullDatacellList: [
          {
            __typename: "DatacellType",
            id: "cell-1",
            column: {
              __typename: "ColumnType",
              id: "col-1",
              name: "Effective Date",
            },
            document: {
              __typename: "DocumentType",
              id: "doc-1",
              title: "Master Services Agreement",
              slug: "master-services-agreement",
              creator: { __typename: "UserType", slug: "test-user" },
            },
            data: "2024-01-15",
            correctedData: null,
            completed: "2024-03-01T12:00:00Z",
            failed: null,
            fullSourceList: [
              { __typename: "AnnotationType", id: "src-1", page: 2 },
            ],
          },
          {
            __typename: "DatacellType",
            id: "cell-2",
            column: {
              __typename: "ColumnType",
              id: "col-2",
              name: "Governing Law",
            },
            document: {
              __typename: "DocumentType",
              id: "doc-1",
              title: "Master Services Agreement",
              slug: "master-services-agreement",
              creator: { __typename: "UserType", slug: "test-user" },
            },
            data: "State of Delaware",
            correctedData: null,
            completed: "2024-03-01T12:00:00Z",
            failed: null,
            fullSourceList: [
              { __typename: "AnnotationType", id: "src-2", page: 5 },
            ],
          },
          {
            __typename: "DatacellType",
            id: "cell-3",
            column: {
              __typename: "ColumnType",
              id: "col-1",
              name: "Effective Date",
            },
            document: {
              __typename: "DocumentType",
              id: "doc-2",
              title: "NDA - Acme Corp",
              slug: "nda-acme-corp",
              creator: { __typename: "UserType", slug: "test-user" },
            },
            data: "2023-11-01",
            correctedData: "2023-11-02",
            completed: "2024-03-01T12:00:00Z",
            failed: null,
            fullSourceList: [],
          },
          {
            __typename: "DatacellType",
            id: "cell-4",
            column: {
              __typename: "ColumnType",
              id: "col-2",
              name: "Governing Law",
            },
            document: {
              __typename: "DocumentType",
              id: "doc-2",
              title: "NDA - Acme Corp",
              slug: "nda-acme-corp",
              creator: { __typename: "UserType", slug: "test-user" },
            },
            data: null,
            correctedData: null,
            completed: null,
            failed: "2024-03-01T12:00:00Z",
            fullSourceList: [],
          },
        ],
      },
    },
  },
};

/** Mock: extract exists but has no datacells (empty state) */
const emptyExtractMock: MockedResponse = {
  request: {
    query: GET_EXTRACT_GRID_EMBED,
    variables: DEFAULT_QUERY_VARIABLES,
  },
  result: {
    data: {
      extract: {
        __typename: "ExtractType",
        id: TEST_EXTRACT_ID,
        name: "Empty Extract",
        corpus: {
          __typename: "CorpusType",
          id: "Q29ycHVzVHlwZTox",
          slug: "supply-chain-analysis",
          creator: { __typename: "UserType", slug: "test-user" },
        },
        fieldset: {
          __typename: "FieldsetType",
          id: "fieldset-1",
          fullColumnList: [
            { __typename: "ColumnType", id: "col-1", name: "Term" },
          ],
        },
        fullDatacellList: [],
      },
    },
  },
};

/** Mock: extract not found (null result) */
const notFoundExtractMock: MockedResponse = {
  request: {
    query: GET_EXTRACT_GRID_EMBED,
    variables: DEFAULT_QUERY_VARIABLES,
  },
  result: {
    data: {
      extract: null,
    },
  },
};

/** Mock: delayed response to test loading state (100s delay so it never resolves during test) */
const loadingExtractMock: MockedResponse = {
  request: {
    query: GET_EXTRACT_GRID_EMBED,
    variables: DEFAULT_QUERY_VARIABLES,
  },
  delay: 100_000,
  result: {
    data: {
      extract: null,
    },
  },
};

/** Mock: extract with more than EXTRACT_GRID_EMBED_MAX_ROWS documents (too-many-rows guard) */
const tooManyRowsExtractMock: MockedResponse = {
  request: {
    query: GET_EXTRACT_GRID_EMBED,
    variables: DEFAULT_QUERY_VARIABLES,
  },
  result: {
    data: {
      extract: {
        __typename: "ExtractType",
        id: TEST_EXTRACT_ID,
        name: "Large Extract",
        corpus: {
          __typename: "CorpusType",
          id: "Q29ycHVzVHlwZTox",
          slug: "supply-chain-analysis",
          creator: { __typename: "UserType", slug: "test-user" },
        },
        fieldset: {
          __typename: "FieldsetType",
          id: "fieldset-1",
          fullColumnList: [
            { __typename: "ColumnType", id: "col-1", name: "Term" },
          ],
        },
        fullDatacellList: Array.from({ length: 201 }, (_, i) => ({
          __typename: "DatacellType" as const,
          id: `cell-${i}`,
          column: {
            __typename: "ColumnType" as const,
            id: "col-1",
            name: "Term",
          },
          document: {
            __typename: "DocumentType" as const,
            id: `doc-${i}`,
            title: `Document ${i}`,
            slug: `document-${i}`,
            creator: { __typename: "UserType" as const, slug: "test-user" },
          },
          data: `value-${i}`,
          correctedData: null,
          completed: "2024-03-01T12:00:00Z",
          failed: null,
          fullSourceList: [],
        })),
      },
    },
  },
};

/** Mock: GraphQL error */
const errorExtractMock: MockedResponse = {
  request: {
    query: GET_EXTRACT_GRID_EMBED,
    variables: DEFAULT_QUERY_VARIABLES,
  },
  error: new Error("Network error"),
};

function createTestCache() {
  return new InMemoryCache({
    typePolicies: {
      ExtractType: { keyFields: ["id"] },
    },
  });
}

export type ExtractGridEmbedState =
  | "populated"
  | "empty"
  | "not-found"
  | "error"
  | "missing-id"
  | "loading"
  | "too-many-rows";

export interface ExtractGridEmbedTestWrapperProps {
  state?: ExtractGridEmbedState;
}

export const ExtractGridEmbedTestWrapper: React.FC<
  ExtractGridEmbedTestWrapperProps
> = ({ state = "populated" }) => {
  const mockMap: Record<
    Exclude<ExtractGridEmbedState, "missing-id">,
    MockedResponse
  > = {
    populated: populatedExtractMock,
    empty: emptyExtractMock,
    "not-found": notFoundExtractMock,
    error: errorExtractMock,
    loading: loadingExtractMock,
    "too-many-rows": tooManyRowsExtractMock,
  };

  const extractId = state === "missing-id" ? undefined : TEST_EXTRACT_ID;
  const mocks = state === "missing-id" ? [] : [mockMap[state]];

  return (
    <Provider>
      <MemoryRouter>
        <MockedProvider mocks={mocks} cache={createTestCache()} addTypename>
          <div style={{ width: "800px", padding: "16px" }}>
            <ExtractGridEmbed extractId={extractId} />
          </div>
        </MockedProvider>
      </MemoryRouter>
    </Provider>
  );
};

export { TEST_EXTRACT_ID };
