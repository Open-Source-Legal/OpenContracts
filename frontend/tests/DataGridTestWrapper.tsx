import React, { useRef } from "react";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { InMemoryCache } from "@apollo/client";
import { MemoryRouter } from "react-router-dom";
import {
  ExtractDataGrid,
  ExtractDataGridHandle,
} from "../src/components/extracts/datagrid/DataGrid";
import {
  REQUEST_APPROVE_DATACELL,
  REQUEST_EDIT_DATACELL,
  REQUEST_REJECT_DATACELL,
  REQUEST_UPDATE_COLUMN,
  REQUEST_CREATE_COLUMN,
  UPLOAD_DOCUMENT,
} from "../src/graphql/mutations";
import {
  REQUEST_GET_EXTRACT,
  GET_REGISTERED_EXTRACT_TASKS,
  SEARCH_DOCUMENTS,
} from "../src/graphql/queries";
import {
  ColumnType,
  DatacellType,
  DocumentType,
  ExtractType,
  PageInfo,
} from "../src/types/graphql-api";

// ---------------------------------------------------------------------------
// Error boundary to surface render errors visibly instead of blank screen
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
// Default mock data
// ---------------------------------------------------------------------------

const defaultExtract: ExtractType = {
  id: "extract-1",
  name: "Test Extract",
  started: null,
  finished: null,
  error: "",
  fieldset: {
    id: "fieldset-1",
    name: "Test Fieldset",
    description: "",
    inUse: false,
    creator: { id: "user-1", email: "test@example.com" },
    columns: { edges: [] },
  },
  corpus: {
    id: "corpus-1",
    title: "Test Corpus",
  } as any,
  creator: { id: "user-1", email: "test@example.com" },
  created: "2024-01-01T00:00:00Z",
};

const defaultColumns: ColumnType[] = [
  {
    id: "col-1",
    name: "Contract Value",
    outputType: "str",
    extractIsList: false,
    taskName: "doc_extract_query_task",
  },
  {
    id: "col-2",
    name: "Effective Date",
    outputType: "str",
    extractIsList: false,
    taskName: "doc_extract_query_task",
  },
];

const defaultDocuments: DocumentType[] = [
  {
    id: "doc-1",
    title: "Master Service Agreement.pdf",
  } as DocumentType,
  {
    id: "doc-2",
    title: "Non-Disclosure Agreement.pdf",
  } as DocumentType,
];

const defaultCells: DatacellType[] = [
  {
    id: "cell-1",
    document: { id: "doc-1" } as DocumentType,
    column: { id: "col-1" } as ColumnType,
    data: { data: "$150,000" },
    dataDefinition: "",
    started: "2024-01-01T00:00:00Z",
    completed: "2024-01-01T00:00:00Z",
    failed: null,
    approvedBy: null,
    rejectedBy: null,
    correctedData: null,
    extract: { id: "extract-1" } as ExtractType,
  },
  {
    id: "cell-2",
    document: { id: "doc-1" } as DocumentType,
    column: { id: "col-2" } as ColumnType,
    data: { data: "2024-03-15" },
    dataDefinition: "",
    started: "2024-01-01T00:00:00Z",
    completed: "2024-01-01T00:00:00Z",
    failed: null,
    approvedBy: null,
    rejectedBy: null,
    correctedData: null,
    extract: { id: "extract-1" } as ExtractType,
  },
  {
    id: "cell-3",
    document: { id: "doc-2" } as DocumentType,
    column: { id: "col-1" } as ColumnType,
    data: { data: "$75,000" },
    dataDefinition: "",
    started: "2024-01-01T00:00:00Z",
    completed: "2024-01-01T00:00:00Z",
    failed: null,
    approvedBy: null,
    rejectedBy: null,
    correctedData: null,
    extract: { id: "extract-1" } as ExtractType,
  },
  {
    id: "cell-4",
    document: { id: "doc-2" } as DocumentType,
    column: { id: "col-2" } as ColumnType,
    data: { data: "2024-06-01" },
    dataDefinition: "",
    started: "2024-01-01T00:00:00Z",
    completed: "2024-01-01T00:00:00Z",
    failed: null,
    approvedBy: null,
    rejectedBy: null,
    correctedData: null,
    extract: { id: "extract-1" } as ExtractType,
  },
];

// ---------------------------------------------------------------------------
// Mock builders
// ---------------------------------------------------------------------------

const defaultPageInfo: PageInfo = {
  hasNextPage: false,
  hasPreviousPage: false,
  startCursor: null,
  endCursor: null,
};

function createMocks(
  extract: ExtractType,
  additionalMocks: MockedResponse[] = []
): MockedResponse[] {
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
            approvedBy: { id: "user-1", username: "testuser" },
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
            rejectedBy: { id: "user-1", username: "testuser" },
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
            name: "Updated Column",
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

  const uploadDocumentMock: MockedResponse = {
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

  const getExtractMock: MockedResponse = {
    request: {
      query: REQUEST_GET_EXTRACT,
      variables: { id: extract.id },
    },
    result: {
      data: {
        extract: {
          id: extract.id,
          corpus: { id: "corpus-1", title: "Test Corpus" },
          name: extract.name,
          fieldset: {
            id: "fieldset-1",
            name: "Test Fieldset",
            inUse: false,
            fullColumnList: [],
          },
          creator: { id: "user-1", username: "testuser" },
          created: extract.created,
          started: extract.started || null,
          finished: extract.finished || null,
          error: extract.error || null,
          fullDocumentList: [],
          fullDatacellList: [],
        },
      },
    },
  };

  // Mock for ExtractTaskDropdown inside CreateColumnModal
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

  // Mock for SelectDocumentsModal
  const searchDocumentsMock: MockedResponse = {
    request: { query: SEARCH_DOCUMENTS },
    variableMatcher: () => true,
    result: {
      data: {
        documents: {
          edges: [],
          pageInfo: defaultPageInfo,
          __typename: "DocumentTypeConnection",
        },
      },
    },
  };

  return [
    approveMock,
    { ...approveMock },
    rejectMock,
    { ...rejectMock },
    editMock,
    { ...editMock },
    updateColumnMock,
    { ...updateColumnMock },
    createColumnMock,
    { ...createColumnMock },
    uploadDocumentMock,
    { ...uploadDocumentMock },
    getExtractMock,
    { ...getExtractMock },
    { ...getExtractMock },
    extractTasksMock,
    { ...extractTasksMock },
    { ...extractTasksMock },
    { ...extractTasksMock },
    searchDocumentsMock,
    { ...searchDocumentsMock },
    { ...searchDocumentsMock },
    ...additionalMocks,
  ];
}

// ---------------------------------------------------------------------------
// Wrapper component
// ---------------------------------------------------------------------------

interface DataGridTestWrapperProps {
  extract?: ExtractType;
  columns?: ColumnType[];
  rows?: DocumentType[];
  cells?: DatacellType[];
  loading?: boolean;
  additionalMocks?: MockedResponse[];
  onAddDocIds?: (extractId: string, documentIds: string[]) => void;
  onRemoveDocIds?: (extractId: string, documentIds: string[]) => void;
  onRemoveColumnId?: (columnId: string) => void;
  onAddColumn?: () => void;
  /** When true, renders a test-only "Trigger Export" button that calls the
   *  imperative `exportToCsv` handle on the grid, letting us exercise CSV
   *  export without reaching into internal refs from test code. */
  withExportButton?: boolean;
}

export const DataGridTestWrapper: React.FC<DataGridTestWrapperProps> = ({
  extract = defaultExtract,
  columns = defaultColumns,
  rows = defaultDocuments,
  cells = defaultCells,
  loading = false,
  additionalMocks = [],
  onAddDocIds = () => {},
  onRemoveDocIds = () => {},
  onRemoveColumnId = () => {},
  onAddColumn = () => {},
  withExportButton = false,
}) => {
  const gridRef = useRef<ExtractDataGridHandle>(null);
  // InMemoryCache must be created inside the component to avoid
  // serialization crashes across test workers (see CLAUDE.md pitfall #8).
  const cache = new InMemoryCache({
    typePolicies: {
      DatacellType: { keyFields: ["id"] },
      ColumnType: { keyFields: ["id"] },
      DocumentType: { keyFields: ["id"] },
      ExtractType: { keyFields: ["id"] },
    },
  });

  return (
    <MemoryRouter initialEntries={["/extracts"]}>
      <MockedProvider
        mocks={createMocks(extract, additionalMocks)}
        cache={cache}
        addTypename={false}
      >
        <ErrorBoundary>
          <div
            style={{
              height: "600px",
              width: "100%",
              padding: "16px",
              background: "#f8fafc",
            }}
          >
            {withExportButton && (
              <button
                data-testid="trigger-export-csv"
                onClick={() => gridRef.current?.exportToCsv()}
              >
                Trigger Export
              </button>
            )}
            <ExtractDataGrid
              ref={gridRef}
              extract={extract}
              cells={cells}
              rows={rows}
              columns={columns}
              onAddDocIds={onAddDocIds}
              onRemoveDocIds={onRemoveDocIds}
              onRemoveColumnId={onRemoveColumnId}
              onAddColumn={onAddColumn}
              loading={loading}
            />
          </div>
        </ErrorBoundary>
      </MockedProvider>
    </MemoryRouter>
  );
};
