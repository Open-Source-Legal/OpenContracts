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
import { EXTRACT_GRID_EMBED_CELL_LIMIT } from "../src/assets/configurations/constants";
import { GET_EXTRACT_GRID_EMBED } from "../src/graphql/queries";

const TEST_EXTRACT_ID = "RXh0cmFjdFR5cGU6MQ==";

/**
 * Shared mock variables for the GET_EXTRACT_GRID_EMBED query. All mocks must
 * match these exactly — Apollo's MockedProvider does strict variable matching
 * and the component now passes an explicit `limit` (see #1204).
 */
const MOCK_VARS = {
  extractId: TEST_EXTRACT_ID,
  limit: EXTRACT_GRID_EMBED_CELL_LIMIT,
};

/** Mock: populated extract with 2 documents and 2 columns */
const populatedExtractMock: MockedResponse = {
  request: {
    query: GET_EXTRACT_GRID_EMBED,
    variables: MOCK_VARS,
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
        datacellCount: 4,
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
    variables: MOCK_VARS,
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
        datacellCount: 0,
        fullDatacellList: [],
      },
    },
  },
};

/** Mock: extract not found (null result) */
const notFoundExtractMock: MockedResponse = {
  request: {
    query: GET_EXTRACT_GRID_EMBED,
    variables: MOCK_VARS,
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
    variables: MOCK_VARS,
  },
  delay: 100_000,
  result: {
    data: {
      extract: null,
    },
  },
};

/**
 * Mock: extract whose derived row count exceeds `EXTRACT_GRID_EMBED_MAX_ROWS`.
 *
 * The server-side `limit` is already capped at `EXTRACT_GRID_EMBED_CELL_LIMIT`
 * so the fetched payload is bounded; the component still clips the rendered
 * row count as a display bound and surfaces the truncation via the partial-
 * data footer banner ("Showing N of M documents").
 */
const tooManyRowsExtractMock: MockedResponse = {
  request: {
    query: GET_EXTRACT_GRID_EMBED,
    variables: MOCK_VARS,
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
        datacellCount: 201,
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

/**
 * Mock: fetched payload is bounded by the server-side `limit`. Simulates an
 * extract where the true `datacellCount` (800) exceeds the returned slice
 * (4 cells = 2 rows × 2 columns). The component should render the partial
 * table and show a "Showing 4 of 800 cells" footer banner.
 */
const partialExtractMock: MockedResponse = {
  request: {
    query: GET_EXTRACT_GRID_EMBED,
    variables: MOCK_VARS,
  },
  result: {
    data: {
      extract: {
        __typename: "ExtractType",
        id: TEST_EXTRACT_ID,
        name: "Partial Extract",
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
        datacellCount: 800,
        fullDatacellList: [
          {
            __typename: "DatacellType",
            id: "partial-cell-1",
            column: {
              __typename: "ColumnType",
              id: "col-1",
              name: "Effective Date",
            },
            document: {
              __typename: "DocumentType",
              id: "doc-a",
              title: "Document A",
              slug: "document-a",
              creator: { __typename: "UserType", slug: "test-user" },
            },
            data: "2024-01-01",
            correctedData: null,
            completed: "2024-03-01T12:00:00Z",
            failed: null,
            fullSourceList: [],
          },
          {
            __typename: "DatacellType",
            id: "partial-cell-2",
            column: {
              __typename: "ColumnType",
              id: "col-2",
              name: "Governing Law",
            },
            document: {
              __typename: "DocumentType",
              id: "doc-a",
              title: "Document A",
              slug: "document-a",
              creator: { __typename: "UserType", slug: "test-user" },
            },
            data: "Delaware",
            correctedData: null,
            completed: "2024-03-01T12:00:00Z",
            failed: null,
            fullSourceList: [],
          },
          {
            __typename: "DatacellType",
            id: "partial-cell-3",
            column: {
              __typename: "ColumnType",
              id: "col-1",
              name: "Effective Date",
            },
            document: {
              __typename: "DocumentType",
              id: "doc-b",
              title: "Document B",
              slug: "document-b",
              creator: { __typename: "UserType", slug: "test-user" },
            },
            data: "2024-02-01",
            correctedData: null,
            completed: "2024-03-01T12:00:00Z",
            failed: null,
            fullSourceList: [],
          },
          {
            __typename: "DatacellType",
            id: "partial-cell-4",
            column: {
              __typename: "ColumnType",
              id: "col-2",
              name: "Governing Law",
            },
            document: {
              __typename: "DocumentType",
              id: "doc-b",
              title: "Document B",
              slug: "document-b",
              creator: { __typename: "UserType", slug: "test-user" },
            },
            data: "New York",
            correctedData: null,
            completed: "2024-03-01T12:00:00Z",
            failed: null,
            fullSourceList: [],
          },
        ],
      },
    },
  },
};

/**
 * Mock: both truncation paths fire simultaneously. The fetched payload has
 * 201 cells (one per document, 1 column) but `datacellCount` is 1000,
 * meaning the server bounded the payload. The component also clips the
 * rendered rows at EXTRACT_GRID_EMBED_MAX_ROWS (200). The combined banner
 * should mention both the document clip and the cell bound.
 */
const bothTruncatedExtractMock: MockedResponse = {
  request: {
    query: GET_EXTRACT_GRID_EMBED,
    variables: MOCK_VARS,
  },
  result: {
    data: {
      extract: {
        __typename: "ExtractType",
        id: TEST_EXTRACT_ID,
        name: "Both Truncated Extract",
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
        datacellCount: 1000,
        fullDatacellList: Array.from({ length: 201 }, (_, i) => ({
          __typename: "DatacellType" as const,
          id: `both-cell-${i}`,
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
    variables: MOCK_VARS,
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
  | "too-many-rows"
  | "partial"
  | "both-truncated";

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
    partial: partialExtractMock,
    "both-truncated": bothTruncatedExtractMock,
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
