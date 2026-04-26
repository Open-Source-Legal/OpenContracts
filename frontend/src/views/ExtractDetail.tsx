import React, {
  useState,
  useEffect,
  useCallback,
  useMemo,
  useRef,
} from "react";
import styled from "styled-components";
import { OS_LEGAL_COLORS } from "../assets/configurations/osLegalStyles";
import { useNavigate } from "react-router-dom";
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
  Download,
  RefreshCw,
  Play,
  Plus,
  Trash2,
} from "lucide-react";

import {
  ColumnType,
  DatacellType,
  DocumentType,
  ExtractType,
} from "../types/graphql-api";
import { openedExtract } from "../graphql/cache";
import {
  RequestGetExtractOutput,
  REQUEST_GET_EXTRACT,
  RequestGetExtractInput,
} from "../graphql/queries";
import {
  REQUEST_ADD_DOC_TO_EXTRACT,
  REQUEST_REMOVE_DOC_FROM_EXTRACT,
  REQUEST_DELETE_COLUMN,
  REQUEST_CREATE_COLUMN,
  REQUEST_CREATE_FIELDSET,
  REQUEST_UPDATE_EXTRACT,
  REQUEST_START_EXTRACT,
  RequestAddDocToExtractInputType,
  RequestAddDocToExtractOutputType,
  RequestRemoveDocFromExtractInputType,
  RequestRemoveDocFromExtractOutputType,
  RequestDeleteColumnInputType,
  RequestDeleteColumnOutputType,
  RequestCreateColumnInputType,
  RequestCreateColumnOutputType,
  RequestCreateFieldsetInputType,
  RequestCreateFieldsetOutputType,
  RequestUpdateExtractInputType,
  RequestUpdateExtractOutputType,
  RequestStartExtractInputType,
  RequestStartExtractOutputType,
} from "../graphql/mutations";
import {
  ExtractDataGrid,
  ExtractDataGridHandle,
} from "../components/extracts/datagrid/DataGrid";
import { CreateColumnModal } from "../components/widgets/modals/CreateColumnModal";
import { ConfirmModal } from "../components/widgets/modals/ConfirmModal";
import { getExtractStatus, formatExtractDate } from "../utils/extractUtils";
import { useExtractCompletionNotification } from "../hooks/useExtractCompletionNotification";

// ═══════════════════════════════════════════════════════════════════════════════
// STYLED COMPONENTS
// ═══════════════════════════════════════════════════════════════════════════════

const PageContainer = styled.div`
  height: 100%;
  background: ${OS_LEGAL_COLORS.background};
  font-family: "Inter", -apple-system, BlinkMacSystemFont, sans-serif;
  overflow-y: auto;
  overflow-x: hidden;
`;

const ContentContainer = styled.main`
  max-width: 1200px;
  margin: 0 auto;
  padding: 32px 24px 80px;

  @media (max-width: 768px) {
    padding: 24px 16px 60px;
  }
`;

const BackButton = styled.button`
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 24px;
  padding: 8px 0;
  font-size: 14px;
  font-weight: 500;
  color: ${OS_LEGAL_COLORS.textSecondary};
  text-decoration: none;
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

const StatsSection = styled.div`
  margin-bottom: 32px;
`;

const TabsSection = styled.div`
  margin-bottom: 24px;
`;

const DataHeader = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
`;

const DataTitle = styled.span`
  font-size: 14px;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textSecondary};
  text-transform: uppercase;
  letter-spacing: 0.05em;
`;

const DataCount = styled.span`
  font-size: 13px;
  color: ${OS_LEGAL_COLORS.textMuted};
`;

const GridContainer = styled.div`
  min-height: 400px;
  background: #ffffff;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 12px;
  overflow: hidden;
`;

const DocumentsList = styled.div`
  display: flex;
  flex-direction: column;
  gap: 8px;
`;

const DocumentItem = styled.div`
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  background: #ffffff;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 8px;
  transition: border-color 0.15s;

  &:hover {
    border-color: ${OS_LEGAL_COLORS.borderHover};
  }
`;

const DocumentIcon = styled.div`
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  background: ${OS_LEGAL_COLORS.surfaceLight};
  color: ${OS_LEGAL_COLORS.textSecondary};
  flex-shrink: 0;
`;

const DocumentInfo = styled.div`
  flex: 1;
  min-width: 0;
`;

const DocumentName = styled.div`
  font-size: 14px;
  font-weight: 500;
  color: ${OS_LEGAL_COLORS.textPrimary};
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
`;

const DocumentMeta = styled.div`
  font-size: 12px;
  color: ${OS_LEGAL_COLORS.textMuted};
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 2px;
`;

const SchemaList = styled.div`
  display: flex;
  flex-direction: column;
  gap: 12px;
`;

const SchemaColumn = styled.div`
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: #ffffff;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 8px;
`;

const SchemaColumnIcon = styled.div`
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  background: ${OS_LEGAL_COLORS.surfaceLight};
  color: ${OS_LEGAL_COLORS.textSecondary};
`;

const SchemaColumnInfo = styled.div`
  flex: 1;
`;

const SchemaColumnName = styled.div`
  font-size: 14px;
  font-weight: 500;
  color: ${OS_LEGAL_COLORS.textPrimary};
`;

const SchemaColumnType = styled.div`
  font-size: 12px;
  color: ${OS_LEGAL_COLORS.textMuted};
  margin-top: 2px;
`;

const SchemaColumnActions = styled.div`
  display: flex;
  gap: 4px;
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
  border-radius: 6px;
  color: ${OS_LEGAL_COLORS.textSecondary};
  cursor: pointer;
  transition: all 0.15s;

  &:hover {
    background: ${OS_LEGAL_COLORS.surfaceLight};
    color: ${OS_LEGAL_COLORS.textPrimary};
    border-color: ${OS_LEGAL_COLORS.borderHover};
  }

  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
`;

const RunningState = styled.div`
  padding: 48px 24px;
  text-align: center;
  background: #ffffff;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 16px;
`;

const Spinner = styled.div`
  width: 48px;
  height: 48px;
  margin: 0 auto 16px;
  border-radius: 50%;
  border: 4px solid ${OS_LEGAL_COLORS.border};
  border-top-color: #e85a4f;
  animation: spin 1s linear infinite;

  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
`;

const RunningTitle = styled.h3`
  margin: 0 0 8px;
  font-size: 18px;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textPrimary};
`;

const RunningDescription = styled.p`
  margin: 0;
  color: ${OS_LEGAL_COLORS.textSecondary};
  font-size: 14px;
`;

const EmptyWrapper = styled.div`
  padding: 48px 24px;
  background: white;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 16px;
`;

// ═══════════════════════════════════════════════════════════════════════════════
// ICONS
// ═══════════════════════════════════════════════════════════════════════════════

const DocumentSvgIcon = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
    <path d="M4 1.5A1.5 1.5 0 015.5 0h5.586a.5.5 0 01.353.146l2.415 2.415a.5.5 0 01.146.353V14.5a1.5 1.5 0 01-1.5 1.5h-7A1.5 1.5 0 014 14.5v-13zM5.5 1a.5.5 0 00-.5.5v13a.5.5 0 00.5.5h7a.5.5 0 00.5-.5V3.707L10.293 1H5.5z" />
    <path d="M6 4.5a.5.5 0 01.5-.5h3a.5.5 0 010 1h-3a.5.5 0 01-.5-.5zm0 2a.5.5 0 01.5-.5h5a.5.5 0 010 1h-5a.5.5 0 01-.5-.5zm0 2a.5.5 0 01.5-.5h5a.5.5 0 010 1h-5a.5.5 0 01-.5-.5zm0 2a.5.5 0 01.5-.5h3a.5.5 0 010 1h-3a.5.5 0 01-.5-.5z" />
  </svg>
);

const ColumnSvgIcon = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
    <path d="M0 2a1 1 0 011-1h14a1 1 0 011 1v12a1 1 0 01-1 1H1a1 1 0 01-1-1V2zm5 0v12h6V2H5zM4 2H1v12h3V2zm8 0v12h3V2h-3z" />
  </svg>
);

const RowSvgIcon = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
    <path d="M0 2a1 1 0 011-1h14a1 1 0 011 1v12a1 1 0 01-1 1H1a1 1 0 01-1-1V2zm1 4h14V2H1v4zm0 1v4h14V7H1zm0 5v2h14v-2H1z" />
  </svg>
);

const CheckSvgIcon = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
    <path
      fillRule="evenodd"
      d="M8 16A8 8 0 108 0a8 8 0 000 16zm3.78-9.72a.75.75 0 00-1.06-1.06L7 8.94 5.28 7.22a.75.75 0 00-1.06 1.06l2.25 2.25a.75.75 0 001.06 0l4.25-4.25z"
      clipRule="evenodd"
    />
  </svg>
);

const TableSvgIcon = () => (
  <svg width="40" height="40" viewBox="0 0 40 40" fill="currentColor">
    <path d="M6 8a4 4 0 014-4h20a4 4 0 014 4v24a4 4 0 01-4 4H10a4 4 0 01-4-4V8zm4-2a2 2 0 00-2 2v6h24V8a2 2 0 00-2-2H10zm22 10H8v16a2 2 0 002 2h20a2 2 0 002-2V16zm-22 4h8v4H10v-4zm10 0h10v4H20v-4zm-10 6h8v4H10v-4zm10 0h10v4H20v-4z" />
  </svg>
);

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export const ExtractDetail: React.FC = () => {
  const navigate = useNavigate();
  const dataGridRef = useRef<ExtractDataGridHandle>(null);

  // Get extract from reactive var (set by CentralRouteManager or route)
  const extractFromVar = useReactiveVar(openedExtract);

  // Local state
  const [extract, setExtract] = useState<ExtractType | null>(extractFromVar);
  const [cells, setCells] = useState<DatacellType[]>([]);
  const [rows, setRows] = useState<DocumentType[]>([]);
  const [columns, setColumns] = useState<ColumnType[]>([]);
  const [activeTab, setActiveTab] = useState("data");
  const [isColumnModalOpen, setIsColumnModalOpen] = useState(false);
  const [editingColumn, setEditingColumn] = useState<ColumnType | null>(null);
  const [deleteColumnId, setDeleteColumnId] = useState<string | null>(null);

  // Sync with reactive var - always update local state to match reactive var
  useEffect(() => {
    setExtract(extractFromVar);
  }, [extractFromVar]);

  // Query for full extract data
  const {
    loading,
    data: extractData,
    refetch,
  } = useQuery<RequestGetExtractOutput, RequestGetExtractInput>(
    REQUEST_GET_EXTRACT,
    {
      variables: { id: extract?.id ?? "" },
      skip: !extract?.id,
      nextFetchPolicy: "network-only",
      notifyOnNetworkStatusChange: true,
    }
  );

  // Listen for extract completion via WebSocket (replaces polling)
  const isRunningExtract = Boolean(
    extract && extract.started && !extract.finished && !extract.error
  );
  useExtractCompletionNotification({
    extractId: extract?.id ?? null,
    onComplete: () => {
      // Refetch to get updated data when extract completes
      refetch();
    },
    enabled: isRunningExtract,
  });

  // Update local state when query data changes
  useEffect(() => {
    if (extractData?.extract) {
      const { fullDatacellList, fullDocumentList, fieldset } =
        extractData.extract;
      setCells(fullDatacellList ?? []);
      setRows(fullDocumentList ?? []);
      setColumns(fieldset?.fullColumnList ?? []);
      setExtract(extractData.extract);
    }
  }, [extractData]);

  // Mutations
  const [addDocsToExtract, { loading: addDocsLoading }] = useMutation<
    RequestAddDocToExtractOutputType,
    RequestAddDocToExtractInputType
  >(REQUEST_ADD_DOC_TO_EXTRACT, {
    onCompleted: (data) => {
      setRows((prev) => [
        ...prev,
        ...(data.addDocsToExtract.objs as DocumentType[]),
      ]);
      toast.success("Added documents to extract.");
    },
    onError: () => toast.error("Could not add documents."),
  });

  const [removeDocsFromExtract, { loading: removeDocsLoading }] = useMutation<
    RequestRemoveDocFromExtractOutputType,
    RequestRemoveDocFromExtractInputType
  >(REQUEST_REMOVE_DOC_FROM_EXTRACT, {
    onCompleted: (data) => {
      setRows((prev) =>
        prev.filter(
          (r) => !data.removeDocsFromExtract.idsRemoved.includes(r.id)
        )
      );
      toast.success("Removed documents from extract.");
    },
    onError: () => toast.error("Could not remove documents."),
  });

  const [deleteColumn] = useMutation<
    RequestDeleteColumnOutputType,
    RequestDeleteColumnInputType
  >(REQUEST_DELETE_COLUMN, {
    onCompleted: (data) => {
      setColumns((prev) =>
        prev.filter((c) => c.id !== data.deleteColumn.deletedId)
      );
      toast.success("Column deleted.");
    },
    onError: () => toast.error("Could not delete column."),
  });

  const [createFieldset] = useMutation<
    RequestCreateFieldsetOutputType,
    RequestCreateFieldsetInputType
  >(REQUEST_CREATE_FIELDSET);

  const [updateExtract] = useMutation<
    RequestUpdateExtractOutputType,
    RequestUpdateExtractInputType
  >(REQUEST_UPDATE_EXTRACT, {
    onCompleted: () => {
      toast.success("Extract updated.");
      refetch();
    },
    onError: () => toast.error("Could not update extract."),
  });

  const [createColumn] = useMutation<
    RequestCreateColumnOutputType,
    RequestCreateColumnInputType
  >(REQUEST_CREATE_COLUMN, {
    onCompleted: (data) => {
      if (data.createColumn.ok) {
        setColumns((prev) => [...prev, data.createColumn.obj]);
        toast.success("Column created.");
      }
      setIsColumnModalOpen(false);
      setEditingColumn(null);
    },
    onError: () => {
      toast.error("Could not create column.");
      setIsColumnModalOpen(false);
    },
  });

  const [startExtract, { loading: startLoading }] = useMutation<
    RequestStartExtractOutputType,
    RequestStartExtractInputType
  >(REQUEST_START_EXTRACT, {
    onCompleted: (data) => {
      toast.success("Extract started!");
      setExtract((prev) =>
        prev ? { ...prev, ...data.startExtract.obj } : prev
      );
    },
    onError: () => toast.error("Could not start extract."),
  });

  // Handlers
  const handleBack = () => {
    // Navigate to the browse list — CentralRouteManager Phase 1 will clear
    // openedExtract when the new path is parsed as a browse route.
    navigate("/extracts");
  };

  const handleAddDocIds = useCallback(
    (extractId: string, documentIds: string[]) => {
      addDocsToExtract({ variables: { extractId, documentIds } });
    },
    [addDocsToExtract]
  );

  const handleRemoveDocIds = useCallback(
    (extractId: string, documentIds: string[]) => {
      removeDocsFromExtract({
        variables: { extractId, documentIdsToRemove: documentIds },
      });
    },
    [removeDocsFromExtract]
  );

  const handleDeleteColumn = async (columnId: string) => {
    if (!extract?.fieldset?.id) return;

    if (!extract.fieldset.inUse) {
      await deleteColumn({ variables: { id: columnId } });
    } else {
      // Create new fieldset without deleted column
      try {
        const { data: fieldsetData } = await createFieldset({
          variables: {
            name: `${extract.fieldset.name} (edited)`,
            description: extract.fieldset.description || "",
          },
        });

        const newFieldsetId = fieldsetData?.createFieldset.obj.id;
        if (!newFieldsetId) throw new Error("Fieldset creation failed.");

        const columnsToCopy = columns.filter((col) => col.id !== columnId);
        await Promise.all(
          columnsToCopy.map((column) =>
            createColumn({
              variables: {
                fieldsetId: newFieldsetId,
                name: column.name,
                query: column.query || "",
                matchText: column.matchText,
                outputType: column.outputType,
                limitToLabel: column.limitToLabel,
                instructions: column.instructions,
                taskName: column.taskName,
              },
            })
          )
        );

        await updateExtract({
          variables: { id: extract.id, fieldsetId: newFieldsetId },
        });
      } catch (error) {
        console.error(error);
        toast.error("Error deleting column.");
      }
    }
    setDeleteColumnId(null);
  };

  const handleAddColumn = () => {
    setEditingColumn(null);
    setIsColumnModalOpen(true);
  };

  const handleEditColumn = (column: ColumnType) => {
    setEditingColumn(column);
    setIsColumnModalOpen(true);
  };

  const handleColumnSubmit = async (
    data: Omit<RequestCreateColumnInputType, "fieldsetId">
  ) => {
    if (editingColumn) {
      // Update existing column - handled by CreateColumnModal
    } else {
      await createColumn({
        variables: {
          fieldsetId: extract?.fieldset?.id,
          ...data,
        },
      });
    }
    setIsColumnModalOpen(false);
    setEditingColumn(null);
  };

  const handleExportCsv = () => {
    dataGridRef.current?.exportToCsv();
  };

  const handleRowUpdate = useCallback((updatedRow: DocumentType) => {
    setRows((prev) =>
      prev.map((row) => (row.id === updatedRow.id ? updatedRow : row))
    );
  }, []);

  // Computed values
  const isRunning = extract?.started && !extract?.finished && !extract?.error;
  const isComplete = extract?.started && extract?.finished && !extract?.error;
  const isFailed = Boolean(extract?.error);
  const canEdit = !extract?.started;

  const statusProps = extract ? getExtractStatus(extract) : null;

  const stats = useMemo(() => {
    const completedCells = cells.filter((c) => c.completed).length;
    const totalCells = cells.length;
    const successRate =
      totalCells > 0 ? Math.round((completedCells / totalCells) * 100) : 0;

    return {
      documents: rows.length,
      columns: columns.length,
      rows: rows.length,
      successRate: isComplete ? `${successRate}%` : "—",
    };
  }, [rows, columns, cells, isComplete]);

  // Loading state
  if (!extract) {
    return (
      <PageContainer>
        <ContentContainer>
          <BackButton onClick={handleBack}>
            <ArrowLeft size={16} />
            Back to Extracts
          </BackButton>
          <EmptyWrapper>
            <EmptyState
              icon={<TableSvgIcon />}
              title="Extract not found"
              description="The extract you're looking for doesn't exist or you don't have access."
              size="lg"
              action={
                <Button variant="primary" onClick={handleBack}>
                  Go to Extracts
                </Button>
              }
            />
          </EmptyWrapper>
        </ContentContainer>
      </PageContainer>
    );
  }

  return (
    <PageContainer>
      <ContentContainer>
        {/* Back link */}
        <BackButton onClick={handleBack}>
          <ArrowLeft size={16} />
          Back to Extracts
        </BackButton>

        {/* Header */}
        <Header>
          <HeaderMain>
            <TitleRow>
              <Title>{extract.name}</Title>
              {statusProps && (
                <Chip size="sm" color={statusProps.color} static>
                  {statusProps.label}
                </Chip>
              )}
            </TitleRow>
            <Meta>
              {extract.corpus && <span>from {extract.corpus.title}</span>}
              {extract.corpus && <MetaSeparator />}
              <span>Created {formatExtractDate(extract.created)}</span>
              {extract.finished && (
                <>
                  <MetaSeparator />
                  <span>Completed {formatExtractDate(extract.finished)}</span>
                </>
              )}
            </Meta>
          </HeaderMain>
          <Actions>
            {canEdit && (
              <Button
                variant="primary"
                size="sm"
                leftIcon={<Play size={16} />}
                onClick={() =>
                  startExtract({ variables: { extractId: extract.id } })
                }
                disabled={
                  startLoading || rows.length === 0 || columns.length === 0
                }
              >
                Start Extract
              </Button>
            )}
            <IconButton aria-label="Refresh" onClick={() => refetch()}>
              <RefreshCw size={16} />
            </IconButton>
            <Button
              variant="secondary"
              size="sm"
              leftIcon={<Download size={16} />}
              onClick={handleExportCsv}
              disabled={loading || Boolean(isRunning)}
            >
              Export CSV
            </Button>
          </Actions>
        </Header>

        {/* Stats */}
        <StatsSection>
          <StatGrid columns={4}>
            <StatBlock
              value={String(stats.documents)}
              label="Documents"
              sublabel="processed"
              icon={<DocumentSvgIcon />}
            />
            <StatBlock
              value={String(stats.columns)}
              label="Columns"
              sublabel="in schema"
              icon={<ColumnSvgIcon />}
            />
            <StatBlock
              value={String(stats.rows)}
              label="Rows"
              sublabel="extracted"
              icon={<RowSvgIcon />}
            />
            <StatBlock
              value={stats.successRate}
              label="Success Rate"
              sublabel="all documents"
              icon={<CheckSvgIcon />}
            />
          </StatGrid>
        </StatsSection>

        {/* Running state overlay */}
        {isRunning && (
          <RunningState>
            <Spinner />
            <RunningTitle>Extraction in progress...</RunningTitle>
            <RunningDescription>
              Processing documents. You can leave this page and check back
              later.
            </RunningDescription>
          </RunningState>
        )}

        {/* Failed state */}
        {isFailed && (
          <EmptyWrapper>
            <EmptyState
              title="Extraction failed"
              description="The extraction could not be completed. Please check the configuration and try again."
              size="lg"
              action={
                <Button
                  variant="primary"
                  leftIcon={<RefreshCw size={16} />}
                  onClick={() =>
                    startExtract({ variables: { extractId: extract.id } })
                  }
                >
                  Retry Extract
                </Button>
              }
            />
          </EmptyWrapper>
        )}

        {/* Tabs - only show when not running and not failed */}
        {!isRunning && !isFailed && (
          <TabsSection>
            <Tabs value={activeTab} onChange={setActiveTab}>
              <TabList>
                <Tab value="data">Data</Tab>
                <Tab value="documents">Documents</Tab>
                <Tab value="schema">Schema</Tab>
              </TabList>

              <TabPanels>
                {/* Data Tab */}
                <TabPanel value="data">
                  <div style={{ marginTop: 24 }}>
                    <DataHeader>
                      <DataTitle>Extracted Data</DataTitle>
                      <DataCount>{rows.length} rows</DataCount>
                    </DataHeader>
                    <GridContainer>
                      <ExtractDataGrid
                        ref={dataGridRef}
                        extract={extract}
                        cells={cells}
                        rows={rows}
                        columns={columns}
                        onAddDocIds={handleAddDocIds}
                        onRemoveDocIds={handleRemoveDocIds}
                        onRemoveColumnId={(id) => setDeleteColumnId(id)}
                        onUpdateRow={handleRowUpdate}
                        onAddColumn={handleAddColumn}
                        loading={loading || addDocsLoading || removeDocsLoading}
                      />
                    </GridContainer>
                  </div>
                </TabPanel>

                {/* Documents Tab */}
                <TabPanel value="documents">
                  <div style={{ marginTop: 24 }}>
                    <DataHeader>
                      <DataTitle>Source Documents</DataTitle>
                      <DataCount>{rows.length} documents</DataCount>
                    </DataHeader>
                    {rows.length > 0 ? (
                      <DocumentsList>
                        {rows.map((doc) => (
                          <DocumentItem key={doc.id}>
                            <DocumentIcon>
                              <DocumentSvgIcon />
                            </DocumentIcon>
                            <DocumentInfo>
                              <DocumentName>{doc.title}</DocumentName>
                              <DocumentMeta>
                                <span>PDF</span>
                                <span>-</span>
                                <span>1 row extracted</span>
                              </DocumentMeta>
                            </DocumentInfo>
                          </DocumentItem>
                        ))}
                      </DocumentsList>
                    ) : (
                      <EmptyWrapper>
                        <EmptyState
                          icon={<DocumentSvgIcon />}
                          title="No documents yet"
                          description="Add documents to this extract to start extracting data."
                          size="md"
                        />
                      </EmptyWrapper>
                    )}
                  </div>
                </TabPanel>

                {/* Schema Tab */}
                <TabPanel value="schema">
                  <div style={{ marginTop: 24 }}>
                    <DataHeader>
                      <DataTitle>Extract Schema</DataTitle>
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: 16,
                        }}
                      >
                        <DataCount>{columns.length} columns</DataCount>
                        {canEdit && (
                          <Button
                            variant="secondary"
                            size="sm"
                            leftIcon={<Plus size={14} />}
                            onClick={handleAddColumn}
                          >
                            Add Column
                          </Button>
                        )}
                      </div>
                    </DataHeader>
                    {columns.length > 0 ? (
                      <SchemaList>
                        {columns.map((col) => (
                          <SchemaColumn key={col.id}>
                            <SchemaColumnIcon>
                              <ColumnSvgIcon />
                            </SchemaColumnIcon>
                            <SchemaColumnInfo>
                              <SchemaColumnName>{col.name}</SchemaColumnName>
                              <SchemaColumnType>
                                {col.outputType}
                              </SchemaColumnType>
                            </SchemaColumnInfo>
                            {canEdit && (
                              <SchemaColumnActions>
                                <IconButton
                                  aria-label="Edit column"
                                  onClick={() => handleEditColumn(col)}
                                >
                                  <RefreshCw size={14} />
                                </IconButton>
                                <IconButton
                                  aria-label="Delete column"
                                  onClick={() => setDeleteColumnId(col.id)}
                                >
                                  <Trash2 size={14} />
                                </IconButton>
                              </SchemaColumnActions>
                            )}
                          </SchemaColumn>
                        ))}
                      </SchemaList>
                    ) : (
                      <EmptyWrapper>
                        <EmptyState
                          icon={<ColumnSvgIcon />}
                          title="No columns defined"
                          description="Add columns to define what data to extract from documents."
                          size="md"
                          action={
                            canEdit ? (
                              <Button
                                variant="primary"
                                leftIcon={<Plus size={16} />}
                                onClick={handleAddColumn}
                              >
                                Add First Column
                              </Button>
                            ) : undefined
                          }
                        />
                      </EmptyWrapper>
                    )}
                  </div>
                </TabPanel>
              </TabPanels>
            </Tabs>
          </TabsSection>
        )}
      </ContentContainer>

      {/* Modals */}
      <CreateColumnModal
        open={isColumnModalOpen}
        existing_column={editingColumn}
        onClose={() => {
          setIsColumnModalOpen(false);
          setEditingColumn(null);
        }}
        onSubmit={handleColumnSubmit}
      />

      <ConfirmModal
        message={`Are you sure you want to delete this column?`}
        visible={deleteColumnId !== null}
        yesAction={() => deleteColumnId && handleDeleteColumn(deleteColumnId)}
        noAction={() => setDeleteColumnId(null)}
        toggleModal={() => setDeleteColumnId(null)}
      />
    </PageContainer>
  );
};

export default ExtractDetail;
