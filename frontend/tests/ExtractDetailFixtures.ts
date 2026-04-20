/**
 * Test fixtures for ExtractDetail component tests.
 *
 * Separated from the test wrapper to avoid Playwright CT mount issues
 * (importing non-component exports from wrapper files can prevent
 * the component transform from working correctly).
 */
import { MockedResponse } from "@apollo/client/testing";
import {
  REQUEST_GET_EXTRACT,
  GET_CORPUSES,
  GET_FIELDSETS,
} from "../src/graphql/queries";
import {
  REQUEST_START_EXTRACT,
  REQUEST_DELETE_COLUMN,
  REQUEST_CREATE_COLUMN,
  REQUEST_CREATE_FIELDSET,
  REQUEST_UPDATE_EXTRACT,
  REQUEST_ADD_DOC_TO_EXTRACT,
  REQUEST_REMOVE_DOC_FROM_EXTRACT,
} from "../src/graphql/mutations";
import type {
  ExtractType,
  ColumnType,
  DocumentType,
  DatacellType,
} from "../src/types/graphql-api";

// ─── Factories ────────────────────────────────────────────────────────────

export const makeMockExtract = (
  overrides: Partial<ExtractType> = {}
): ExtractType =>
  ({
    id: "RXh0cmFjdFR5cGU6MQ==",
    name: "Test Extract",
    created: "2024-01-15T10:30:00Z",
    started: null,
    finished: null,
    error: null,
    corpus: {
      id: "Q29ycHVzVHlwZTox",
      title: "Test Corpus",
      __typename: "CorpusType",
    },
    creator: {
      id: "VXNlclR5cGU6MQ==",
      username: "testuser",
      __typename: "UserType",
    },
    fieldset: {
      id: "fieldset-1",
      name: "Test Fieldset",
      inUse: false,
      __typename: "FieldsetType",
    },
    myPermissions: ["read_extract", "update_extract", "remove_extract"],
    __typename: "ExtractType",
    ...overrides,
  } as unknown as ExtractType);

export const makeMockColumn = (
  overrides: Partial<ColumnType> = {}
): ColumnType =>
  ({
    id: "col-1",
    name: "Sample Column",
    query: "What is the contract term?",
    matchText: null,
    outputType: "str",
    limitToLabel: null,
    instructions: null,
    taskName: null,
    extractIsList: false,
    __typename: "ColumnType",
    ...overrides,
  } as unknown as ColumnType);

export const makeMockDocument = (
  overrides: Partial<DocumentType> = {}
): DocumentType =>
  ({
    id: "doc-1",
    title: "Contract.pdf",
    description: "A contract document",
    pageCount: 10,
    fileType: "pdf",
    __typename: "DocumentType",
    ...overrides,
  } as unknown as DocumentType);

export const makeMockCell = (
  overrides: Partial<DatacellType> = {}
): DatacellType =>
  ({
    id: "cell-1",
    completed: "2024-01-15T12:00:00Z",
    started: "2024-01-15T11:00:00Z",
    data: { value: "Example value" },
    rawData: null,
    correctedData: null,
    column: { id: "col-1", name: "Sample Column", __typename: "ColumnType" },
    document: {
      id: "doc-1",
      title: "Contract.pdf",
      fileType: "pdf",
      __typename: "DocumentType",
    },
    fullSourceList: [],
    approvedBy: null,
    rejectedBy: null,
    __typename: "DatacellType",
    ...overrides,
  } as unknown as DatacellType);

// ─── Mock builder ─────────────────────────────────────────────────────────

interface BuildMocksOptions {
  extract: ExtractType;
  columns?: ColumnType[];
  documents?: DocumentType[];
  cells?: DatacellType[];
}

export const buildExtractDetailMocks = ({
  extract,
  columns = [],
  documents = [],
  cells = [],
}: BuildMocksOptions): MockedResponse[] => {
  const extractWithData = {
    ...extract,
    fieldset: extract.fieldset
      ? {
          ...extract.fieldset,
          description: (extract.fieldset as any).description ?? null,
          fullColumnList: columns,
        }
      : null,
    fullDocumentList: documents,
    fullDatacellList: cells,
  };

  const baseResponse: MockedResponse = {
    request: { query: REQUEST_GET_EXTRACT, variables: { id: extract.id } },
    result: { data: { extract: extractWithData } },
  };

  // Duplicate for refetch calls
  const getExtractMocks = [
    baseResponse,
    { ...baseResponse },
    { ...baseResponse },
  ];

  const passthroughMutation = (query: any): MockedResponse => ({
    request: { query },
    variableMatcher: () => true,
    result: { data: null },
  });

  return [
    ...getExtractMocks,
    passthroughMutation(REQUEST_START_EXTRACT),
    passthroughMutation(REQUEST_DELETE_COLUMN),
    passthroughMutation(REQUEST_CREATE_COLUMN),
    passthroughMutation(REQUEST_CREATE_FIELDSET),
    passthroughMutation(REQUEST_UPDATE_EXTRACT),
    passthroughMutation(REQUEST_ADD_DOC_TO_EXTRACT),
    passthroughMutation(REQUEST_REMOVE_DOC_FROM_EXTRACT),
    {
      request: { query: GET_CORPUSES },
      variableMatcher: () => true,
      result: {
        data: {
          corpuses: {
            edges: [],
            pageInfo: {
              hasNextPage: false,
              hasPreviousPage: false,
              startCursor: null,
              endCursor: null,
              __typename: "PageInfo",
            },
            __typename: "CorpusTypeConnection",
          },
        },
      },
    },
    {
      request: { query: GET_FIELDSETS },
      variableMatcher: () => true,
      result: {
        data: {
          fieldsets: {
            edges: [],
            pageInfo: {
              hasNextPage: false,
              hasPreviousPage: false,
              startCursor: null,
              endCursor: null,
              __typename: "PageInfo",
            },
            __typename: "FieldsetTypeConnection",
          },
        },
      },
    },
  ];
};
