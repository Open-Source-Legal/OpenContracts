/**
 * Test wrapper for ExtractDetailContent component tests.
 *
 * Provides MockedProvider with REQUEST_GET_EXTRACT mocks plus all the
 * mutation mocks the component may invoke during interaction tests.
 *
 * Inner InMemoryCache is created per-mount (see CLAUDE.md pitfall #8 — cache
 * serialization crashes across Playwright workers when defined at module
 * scope).
 */

import React, { useRef } from "react";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { InMemoryCache } from "@apollo/client";
import { MemoryRouter } from "react-router-dom";
import { Provider as JotaiProvider } from "jotai";
import { ToastContainer } from "react-toastify";
import {
  ExtractDetailContent,
  ExtractDetailContentHandle,
} from "../src/components/extracts/ExtractDetailContent";
import {
  REQUEST_GET_EXTRACT,
  GET_REGISTERED_EXTRACT_TASKS,
  SEARCH_DOCUMENTS,
} from "../src/graphql/queries";
import {
  REQUEST_ADD_DOC_TO_EXTRACT,
  REQUEST_REMOVE_DOC_FROM_EXTRACT,
  REQUEST_DELETE_COLUMN,
  REQUEST_CREATE_COLUMN,
  REQUEST_CREATE_FIELDSET,
  REQUEST_UPDATE_EXTRACT,
  REQUEST_START_EXTRACT,
  REQUEST_APPROVE_DATACELL,
  REQUEST_EDIT_DATACELL,
  REQUEST_REJECT_DATACELL,
  REQUEST_UPDATE_COLUMN,
  UPLOAD_DOCUMENT,
} from "../src/graphql/mutations";
import {
  ColumnType,
  DatacellType,
  DocumentType,
  ExtractType,
} from "../src/types/graphql-api";

// ---------------------------------------------------------------------------
// Error boundary — render failures show as visible text, not a blank screen.
// ---------------------------------------------------------------------------

class ErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { error: string | null }
> {
  state = { error: null as string | null };
  static getDerivedStateFromError(error: Error) {
    return { error: `${error.name}: ${error.message}` };
  }
  render() {
    if (this.state.error) {
      return (
        <pre data-testid="error-boundary" style={{ color: "red" }}>
          {this.state.error}
        </pre>
      );
    }
    return this.props.children;
  }
}

// ---------------------------------------------------------------------------
// Fixture data — shared across tests via overrides.
// ---------------------------------------------------------------------------

const defaultColumns: ColumnType[] = [
  {
    id: "col-1",
    name: "Contract Value",
    query: "What is the contract value?",
    outputType: "str",
    matchText: "",
    limitToLabel: "",
    instructions: "",
    taskName: "doc_extract_query_task",
    extractIsList: false,
  } as ColumnType,
  {
    id: "col-2",
    name: "Effective Date",
    query: "When is the effective date?",
    outputType: "str",
    matchText: "",
    limitToLabel: "",
    instructions: "",
    taskName: "doc_extract_query_task",
    extractIsList: false,
  } as ColumnType,
];

const defaultDocuments: DocumentType[] = [
  {
    id: "doc-1",
    title: "Master Service Agreement.pdf",
    description: "MSA",
    pageCount: 12,
    fileType: "application/pdf",
  } as DocumentType,
  {
    id: "doc-2",
    title: "Non-Disclosure Agreement.pdf",
    description: "NDA",
    pageCount: 4,
    fileType: "application/pdf",
  } as DocumentType,
];

const defaultCells: DatacellType[] = [
  {
    id: "cell-1",
    column: { id: "col-1", name: "Contract Value" } as ColumnType,
    document: {
      id: "doc-1",
      title: "Master Service Agreement.pdf",
      fileType: "application/pdf",
    } as DocumentType,
    fullSourceList: [],
    data: { data: "$150,000" },
    dataDefinition: "",
    started: "2024-01-01T00:00:00Z",
    completed: "2024-01-02T00:00:00Z",
    failed: null,
    correctedData: null,
    stacktrace: null,
    approvedBy: null,
    rejectedBy: null,
  } as DatacellType,
  {
    id: "cell-2",
    column: { id: "col-2", name: "Effective Date" } as ColumnType,
    document: {
      id: "doc-1",
      title: "Master Service Agreement.pdf",
      fileType: "application/pdf",
    } as DocumentType,
    fullSourceList: [],
    data: { data: "2024-03-15" },
    dataDefinition: "",
    started: "2024-01-01T00:00:00Z",
    completed: "2024-01-02T00:00:00Z",
    failed: null,
    correctedData: null,
    stacktrace: null,
    approvedBy: null,
    rejectedBy: null,
  } as DatacellType,
];

// ---------------------------------------------------------------------------
// Variants — which scenario we want to mock.
// ---------------------------------------------------------------------------

export type ExtractScenario =
  | "complete" // started & finished, no error
  | "running" // started, not finished, no error
  | "failed" // started, has error
  | "not-started" // no started
  | "not-found" // extract is null
  | "no-documents" // complete but with 0 documents
  | "no-columns" // complete but fieldset has 0 columns (non-editable)
  | "no-columns-editable"; // not started, fieldset has 0 columns (editable)

function buildExtractPayload(scenario: ExtractScenario, extractId: string) {
  // Typenames are required because the InMemoryCache below uses
  // `typePolicies` with `keyFields`. Without __typename, Apollo can't
  // normalize — it still returns `data` to the component, but this pattern
  // matches the proven ExtractGridEmbedTestWrapper setup and avoids subtle
  // cache-miss behavior with `cache-and-network` fetch policy.
  const fullColumnList = defaultColumns.map((col) => ({
    ...col,
    __typename: "ColumnType",
  }));
  const fullDocumentList = defaultDocuments.map((doc) => ({
    ...doc,
    __typename: "DocumentType",
  }));
  const fullDatacellList = defaultCells.map((cell) => ({
    ...cell,
    __typename: "DatacellType",
    column: { ...(cell.column as any), __typename: "ColumnType" },
    document: { ...(cell.document as any), __typename: "DocumentType" },
    fullSourceList: [],
  }));

  const base = {
    __typename: "ExtractType",
    id: extractId,
    corpus: {
      __typename: "CorpusType",
      id: "corpus-1",
      title: "Test Corpus",
    },
    name: "Test Extract",
    creator: {
      __typename: "UserType",
      id: "user-1",
      username: "testuser",
    },
    created: "2024-01-01T00:00:00Z",
    started: null as string | null,
    finished: null as string | null,
    error: null as string | null,
    fieldset: {
      __typename: "FieldsetType",
      id: "fieldset-1",
      name: "Test Fieldset",
      inUse: false,
      fullColumnList,
    },
    fullDocumentList,
    fullDatacellList,
  };

  switch (scenario) {
    case "complete":
      return {
        ...base,
        started: "2024-01-01T00:00:00Z",
        finished: "2024-01-02T00:00:00Z",
      };
    case "running":
      return {
        ...base,
        started: "2024-01-01T00:00:00Z",
      };
    case "failed":
      return {
        ...base,
        started: "2024-01-01T00:00:00Z",
        error: "Extraction failed due to parser error",
      };
    case "not-started":
      return base;
    case "not-found":
      return null;
    case "no-documents":
      return {
        ...base,
        started: "2024-01-01T00:00:00Z",
        finished: "2024-01-02T00:00:00Z",
        fullDocumentList: [],
        fullDatacellList: [],
      };
    case "no-columns":
      return {
        ...base,
        started: "2024-01-01T00:00:00Z",
        finished: "2024-01-02T00:00:00Z",
        fieldset: { ...base.fieldset, fullColumnList: [] },
      };
    case "no-columns-editable":
      return {
        ...base,
        fieldset: { ...base.fieldset, fullColumnList: [] },
      };
  }
}

// ---------------------------------------------------------------------------
// Build the mock list for a given scenario.
// ---------------------------------------------------------------------------

function buildMocks(
  scenario: ExtractScenario,
  extractId: string,
  options: {
    neverResolve?: boolean;
    extraMocks?: MockedResponse[];
  } = {}
): MockedResponse[] {
  const extractPayload = buildExtractPayload(scenario, extractId);

  const getExtractBase: MockedResponse = {
    request: {
      query: REQUEST_GET_EXTRACT,
      variables: { id: extractId },
    },
    result: { data: { extract: extractPayload } },
    // When neverResolve is true we add a long delay so the query appears
    // perpetually pending — useful for asserting the loading state.
    ...(options.neverResolve ? { delay: 60_000 } : {}),
  };

  // Mocks for optional mutations / lookups. Using variableMatcher: () => true
  // so they match regardless of which input the component sends.
  const extractTasksMock: MockedResponse = {
    request: { query: GET_REGISTERED_EXTRACT_TASKS },
    variableMatcher: () => true,
    result: {
      data: {
        registeredExtractTasks: {
          "opencontractserver.tasks.data_extract_tasks.doc_extract_query_task":
            "Extract structured data using LLM queries",
        },
      },
    },
  };

  const searchDocsMock: MockedResponse = {
    request: { query: SEARCH_DOCUMENTS },
    variableMatcher: () => true,
    result: {
      data: {
        documents: {
          edges: [],
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

  const addDocsMock: MockedResponse = {
    request: { query: REQUEST_ADD_DOC_TO_EXTRACT },
    variableMatcher: () => true,
    result: {
      data: {
        addDocsToExtract: {
          ok: true,
          message: "Added",
          objs: [],
        },
      },
    },
  };

  const removeDocsMock: MockedResponse = {
    request: { query: REQUEST_REMOVE_DOC_FROM_EXTRACT },
    variableMatcher: () => true,
    result: {
      data: {
        removeDocsFromExtract: { ok: true, message: "Removed", idsRemoved: [] },
      },
    },
  };

  const deleteColumnMock: MockedResponse = {
    request: { query: REQUEST_DELETE_COLUMN },
    variableMatcher: () => true,
    result: {
      data: {
        deleteColumn: { ok: true, message: "Deleted", deletedId: "col-1" },
      },
    },
  };

  const createColumnMock: MockedResponse = {
    request: { query: REQUEST_CREATE_COLUMN },
    variableMatcher: () => true,
    result: {
      data: {
        createColumn: {
          ok: true,
          message: "Created",
          obj: {
            id: "col-new",
            name: "New Column",
            query: "",
            matchText: "",
            outputType: "str",
            limitToLabel: "",
            instructions: "",
            taskName: "doc_extract_query_task",
          },
        },
      },
    },
  };

  const updateColumnMock: MockedResponse = {
    request: { query: REQUEST_UPDATE_COLUMN },
    variableMatcher: () => true,
    result: {
      data: {
        updateColumn: {
          ok: true,
          message: "Updated",
          obj: {
            id: "col-1",
            name: "Contract Value",
            query: "",
            matchText: "",
            outputType: "str",
            limitToLabel: "",
            instructions: "",
            taskName: "doc_extract_query_task",
          },
        },
      },
    },
  };

  const createFieldsetMock: MockedResponse = {
    request: { query: REQUEST_CREATE_FIELDSET },
    variableMatcher: () => true,
    result: {
      data: {
        createFieldset: {
          ok: true,
          message: "Created",
          obj: {
            id: "fieldset-new",
            name: "Test Fieldset (edited)",
            description: "",
          },
        },
      },
    },
  };

  const updateExtractMock: MockedResponse = {
    request: { query: REQUEST_UPDATE_EXTRACT },
    variableMatcher: () => true,
    result: {
      data: {
        updateExtract: {
          ok: true,
          message: "Updated",
          obj: { id: extractId },
        },
      },
    },
  };

  const startExtractMock: MockedResponse = {
    request: { query: REQUEST_START_EXTRACT },
    variableMatcher: () => true,
    result: {
      data: {
        startExtract: {
          ok: true,
          message: "Started",
          obj: {
            id: extractId,
            started: "2024-06-01T00:00:00Z",
            finished: null,
          },
        },
      },
    },
  };

  const approveMock: MockedResponse = {
    request: { query: REQUEST_APPROVE_DATACELL },
    variableMatcher: () => true,
    result: {
      data: {
        approveDatacell: {
          ok: true,
          message: "Approved",
          obj: {
            id: "cell-1",
            data: {},
            started: "2024-01-01",
            completed: "2024-01-01",
            stacktrace: null,
            correctedData: null,
            column: { id: "col-1" },
            document: { id: "doc-1" },
            approvedBy: { id: "user-1", username: "u" },
            rejectedBy: null,
          },
        },
      },
    },
  };

  const rejectMock: MockedResponse = {
    request: { query: REQUEST_REJECT_DATACELL },
    variableMatcher: () => true,
    result: {
      data: {
        rejectDatacell: {
          ok: true,
          message: "Rejected",
          obj: {
            id: "cell-1",
            data: {},
            started: "2024-01-01",
            completed: "2024-01-01",
            stacktrace: null,
            correctedData: null,
            column: { id: "col-1" },
            document: { id: "doc-1" },
            approvedBy: null,
            rejectedBy: { id: "user-1", username: "u" },
          },
        },
      },
    },
  };

  const editMock: MockedResponse = {
    request: { query: REQUEST_EDIT_DATACELL },
    variableMatcher: () => true,
    result: {
      data: {
        editDatacell: {
          ok: true,
          message: "Edited",
          obj: {
            id: "cell-1",
            data: {},
            started: "2024-01-01",
            completed: "2024-01-01",
            stacktrace: null,
            correctedData: { data: "edited" },
            approvedBy: null,
            rejectedBy: null,
          },
        },
      },
    },
  };

  const uploadDocMock: MockedResponse = {
    request: { query: UPLOAD_DOCUMENT },
    variableMatcher: () => true,
    result: {
      data: {
        uploadDocument: {
          ok: true,
          message: "Uploaded",
          document: {
            id: "doc-new",
            icon: "",
            pdfFile: "",
            title: "Uploaded.pdf",
            description: "",
            backendLock: false,
            fileType: "application/pdf",
            docAnnotations: { edges: [] },
          },
        },
      },
    },
  };

  // Duplicate getExtractBase a few times to cover cache-and-network + refetch.
  return [
    getExtractBase,
    { ...getExtractBase },
    { ...getExtractBase },
    extractTasksMock,
    { ...extractTasksMock },
    { ...extractTasksMock },
    { ...extractTasksMock },
    searchDocsMock,
    { ...searchDocsMock },
    addDocsMock,
    { ...addDocsMock },
    removeDocsMock,
    { ...removeDocsMock },
    deleteColumnMock,
    { ...deleteColumnMock },
    createColumnMock,
    { ...createColumnMock },
    updateColumnMock,
    { ...updateColumnMock },
    createFieldsetMock,
    { ...createFieldsetMock },
    updateExtractMock,
    { ...updateExtractMock },
    startExtractMock,
    { ...startExtractMock },
    approveMock,
    rejectMock,
    editMock,
    uploadDocMock,
    ...(options.extraMocks ?? []),
  ];
}

// ---------------------------------------------------------------------------
// Wrapper component
// ---------------------------------------------------------------------------

interface ExtractDetailContentTestWrapperProps {
  scenario?: ExtractScenario;
  /** When true, the REQUEST_GET_EXTRACT mock delays by 60s so the loading
   *  state is observable. */
  loadingForever?: boolean;
  extractId?: string;
  additionalMocks?: MockedResponse[];
  onExtractLoaded?: (extract: ExtractType) => void;
  /** Renders a hidden button that triggers the imperative exportToCsv method
   *  so tests can verify the handle without reaching into internal refs. */
  withExportButton?: boolean;
  /** Renders a hidden button that triggers the imperative startExtract method. */
  withStartButton?: boolean;
}

export const ExtractDetailContentTestWrapper: React.FC<
  ExtractDetailContentTestWrapperProps
> = ({
  scenario = "complete",
  loadingForever = false,
  extractId = "extract-1",
  additionalMocks = [],
  onExtractLoaded,
  withExportButton = false,
  withStartButton = false,
}) => {
  const handleRef = useRef<ExtractDetailContentHandle>(null);

  const cache = new InMemoryCache({
    typePolicies: {
      ExtractType: { keyFields: ["id"] },
      DatacellType: { keyFields: ["id"] },
      ColumnType: { keyFields: ["id"] },
      DocumentType: { keyFields: ["id"] },
      FieldsetType: { keyFields: ["id"] },
    },
  });

  const mocks = buildMocks(scenario, extractId, {
    neverResolve: loadingForever,
    extraMocks: additionalMocks,
  });

  return (
    <MemoryRouter initialEntries={["/extracts/" + extractId]}>
      <JotaiProvider>
        {/* addTypename prop is deprecated in Apollo 3.14+; omit to use the
            default (true). Mocks must include __typename everywhere. */}
        <MockedProvider mocks={mocks} cache={cache}>
          <ErrorBoundary>
            <div
              style={{
                height: "800px",
                width: "100%",
                padding: "16px",
                background: "#f8fafc",
              }}
            >
              {withExportButton && (
                <button
                  data-testid="trigger-export-csv"
                  onClick={() => handleRef.current?.exportToCsv()}
                >
                  Trigger Export
                </button>
              )}
              {withStartButton && (
                <button
                  data-testid="trigger-start-extract"
                  onClick={() => handleRef.current?.startExtract()}
                >
                  Trigger Start
                </button>
              )}
              <ExtractDetailContent
                ref={handleRef}
                extractId={extractId}
                onExtractLoaded={onExtractLoaded}
              />
            </div>
            {/* Portal target for react-toastify so tests can assert on
                mutation success/error toasts. */}
            <ToastContainer position="top-right" autoClose={false} />
          </ErrorBoundary>
        </MockedProvider>
      </JotaiProvider>
    </MemoryRouter>
  );
};
