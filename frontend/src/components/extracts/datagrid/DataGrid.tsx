import React, {
  forwardRef,
  useCallback,
  useMemo,
  useState,
  useRef,
  useEffect,
  useImperativeHandle,
} from "react";
import { useMutation } from "@apollo/client";
import { toast } from "react-toastify";
import {
  Button,
  Icon,
  Popup,
  Dimmer,
  Loader,
  Modal,
  Message,
  Checkbox,
  Table,
} from "semantic-ui-react";
import {
  REQUEST_APPROVE_DATACELL,
  REQUEST_EDIT_DATACELL,
  REQUEST_REJECT_DATACELL,
  RequestApproveDatacellInputType,
  RequestApproveDatacellOutputType,
  RequestEditDatacellInputType,
  RequestEditDatacellOutputType,
  RequestRejectDatacellInputType,
  RequestRejectDatacellOutputType,
  REQUEST_UPDATE_COLUMN,
  RequestUpdateColumnInputType,
  RequestUpdateColumnOutputType,
  REQUEST_CREATE_COLUMN,
  RequestCreateColumnInputType,
  RequestCreateColumnOutputType,
} from "../../../graphql/mutations";
import { ExtractCellFormatter } from "./ExtractCellFormatter";
import {
  ExtractGridColumn,
  ExtractGridRow,
  CellStatus,
} from "../../../types/extract-grid";
import {
  ColumnType,
  DatacellType,
  DocumentType,
  ExtractType,
} from "../../../types/graphql-api";
import { useDropzone } from "react-dropzone";
import { UPLOAD_DOCUMENT } from "../../../graphql/mutations";
import { parseOutputType } from "../../../utils/parseOutputType";
import { JSONSchema7 } from "json-schema";
import { TruncatedText } from "../../widgets/data-display/TruncatedText";
import { CreateColumnModal } from "../../widgets/modals/CreateColumnModal";
import { SelectDocumentsModal } from "../../widgets/modals/SelectDocumentsModal";
import { REQUEST_GET_EXTRACT } from "../../../graphql/queries";

interface DragState {
  isDragging: boolean;
  dragY: number | null;
}

interface DataGridProps {
  extract: ExtractType;
  cells: DatacellType[];
  rows: DocumentType[];
  columns: ColumnType[];
  onAddDocIds: (extractId: string, documentIds: string[]) => void;
  onRemoveDocIds: (extractId: string, documentIds: string[]) => void;
  onRemoveColumnId: (columnId: string) => void;
  onUpdateRow?: (newRow: DocumentType) => void;
  onAddColumn: () => void;
  loading?: boolean;
}

// Update the styles object with modern styling
const styles = {
  gridWrapper: {
    height: "100%",
    width: "100%",
    position: "relative",
    backgroundColor: "#ffffff",
    borderRadius: "16px",
    display: "flex",
    flexDirection: "column",
    overflow: "hidden",
    minHeight: 0,
  } as React.CSSProperties,
  tableContainer: {
    flex: 1,
    overflow: "auto",
    position: "relative",
    backgroundColor: "#fafbfc",
    minHeight: 0,
    WebkitOverflowScrolling: "touch", // Enable momentum scrolling on iOS
  } as React.CSSProperties,
  stickyHeader: {
    position: "sticky",
    top: 0,
    zIndex: 10,
    backgroundColor: "#f8fafc",
    borderBottom: "2px solid #e2e8f0",
  } as React.CSSProperties,
  headerCell: {
    backgroundColor: "#f8fafc !important",
    fontWeight: "700 !important",
    color: "#0f172a !important",
    position: "relative",
    borderBottom: "none !important",
    padding: "1rem 1.25rem !important",
    fontSize: "0.875rem !important",
    letterSpacing: "0.025em !important",
    textTransform: "uppercase",
  } as React.CSSProperties,
  headerControls: {
    display: "inline-flex",
    alignItems: "center",
    gap: "8px",
    marginLeft: "12px",
  } as React.CSSProperties,
  addColumnButton: {
    width: "32px",
    height: "32px",
    padding: 0,
    borderRadius: "10px",
    border: "2px dashed #cbd5e1",
    background: "rgba(59, 130, 246, 0.05)",
    color: "#3b82f6",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    cursor: "pointer",
    transition: "all 0.2s ease",
    "&:hover": {
      background: "rgba(59, 130, 246, 0.1)",
      borderColor: "#3b82f6",
      transform: "scale(1.05)",
    },
  } as React.CSSProperties,
  tableCell: {
    padding: "1rem 1.25rem !important",
    borderBottom: "1px solid #f1f5f9 !important",
    fontSize: "0.9375rem !important",
    color: "#334155 !important",
    transition: "background-color 0.15s ease",
    "&:hover": {
      backgroundColor: "#f8fafc",
    },
  } as React.CSSProperties,
  dropOverlay: {
    position: "absolute" as const,
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: "rgba(59, 130, 246, 0.02)",
    backdropFilter: "blur(8px)",
    display: "flex",
    justifyContent: "center",
    alignItems: "center",
    zIndex: 999,
    pointerEvents: "none" as const,
  },
  dropMessage: {
    padding: "32px 48px",
    backgroundColor: "rgba(255, 255, 255, 0.98)",
    borderRadius: "20px",
    boxShadow: "0 20px 40px rgba(0,0,0,0.1)",
    border: "3px dashed #3b82f6",
    fontSize: "1.125rem",
    fontWeight: "600",
    color: "#0f172a",
    backdropFilter: "blur(12px)",
  },
  placeholderRow: {
    textAlign: "center" as const,
    color: "#94a3b8",
    fontStyle: "italic",
    padding: "60px 20px",
    fontSize: "0.9375rem",
    backgroundColor: "#fafbfc",
  },
  frozenColumn: {
    position: "sticky" as const,
    left: 0,
    backgroundColor: "#ffffff",
    zIndex: 5,
    boxShadow: "3px 0 6px rgba(0,0,0,0.05)",
    borderRight: "1px solid #e2e8f0",
  },
  frozenHeaderColumn: {
    position: "sticky" as const,
    left: 0,
    backgroundColor: "#f8fafc !important",
    zIndex: 11,
    boxShadow: "3px 0 6px rgba(0,0,0,0.05)",
    borderRight: "1px solid #e2e8f0",
  },
  statusCell: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
  } as React.CSSProperties,
  statusDot: {
    width: "10px",
    height: "10px",
    borderRadius: "50%",
    flexShrink: 0,
  } as React.CSSProperties,
  approvedDot: {
    backgroundColor: "#10b981",
    boxShadow: "0 0 0 3px rgba(16, 185, 129, 0.1)",
  } as React.CSSProperties,
  rejectedDot: {
    backgroundColor: "#ef4444",
    boxShadow: "0 0 0 3px rgba(239, 68, 68, 0.1)",
  } as React.CSSProperties,
  pendingDot: {
    backgroundColor: "#f59e0b",
    boxShadow: "0 0 0 3px rgba(245, 158, 11, 0.1)",
  } as React.CSSProperties,
  emptyDot: {
    backgroundColor: "#e2e8f0",
    border: "2px solid #cbd5e1",
  } as React.CSSProperties,
  actionButton: {
    padding: "6px 12px",
    borderRadius: "8px",
    border: "1px solid #e2e8f0",
    background: "white",
    color: "#64748b",
    fontSize: "0.875rem",
    fontWeight: "500",
    cursor: "pointer",
    transition: "all 0.15s ease",
    display: "inline-flex",
    alignItems: "center",
    gap: "6px",
    "&:hover": {
      background: "#f8fafc",
      borderColor: "#cbd5e1",
      color: "#334155",
      transform: "translateY(-1px)",
    },
  } as React.CSSProperties,
  emptyState: {
    padding: "80px 40px",
    textAlign: "center" as const,
    backgroundColor: "#fafbfc",
    borderRadius: "12px",
    margin: "20px",
  } as React.CSSProperties,
  emptyStateIcon: {
    fontSize: "48px",
    color: "#cbd5e1",
    marginBottom: "16px",
  } as React.CSSProperties,
  emptyStateTitle: {
    fontSize: "1.25rem",
    fontWeight: "600",
    color: "#334155",
    marginBottom: "8px",
  } as React.CSSProperties,
  emptyStateText: {
    fontSize: "0.9375rem",
    color: "#64748b",
    maxWidth: "400px",
    margin: "0 auto",
  } as React.CSSProperties,
};

// Add interface for sort state
interface SortConfig {
  columnId: string;
  direction: "ASC" | "DESC";
}

// Add interface for the exposed methods
export interface ExtractDataGridHandle {
  exportToCsv: () => void;
}

// Add new interface for the delete modal state
interface DeleteColumnModalState {
  isOpen: boolean;
  columnToDelete: ColumnType | null;
}

export const ExtractDataGrid = forwardRef<ExtractDataGridHandle, DataGridProps>(
  (
    {
      extract,
      cells: initialCells,
      rows,
      columns,
      onAddDocIds,
      onRemoveDocIds,
      onRemoveColumnId,
      onUpdateRow,
      onAddColumn,
      loading,
    },
    ref
  ) => {
    // Debug logging to verify all fieldset columns are present
    useEffect(() => {
      console.log("DataGrid received columns:", columns);
      console.log("Number of columns:", columns.length);
      console.log(
        "Column names:",
        columns.map((c) => c.name)
      );
    }, [columns]);

    const [selectedRows, setSelectedRows] = useState<Set<string>>(new Set());
    const [isDeleting, setIsDeleting] = useState(false);
    const [sortConfig, setSortConfig] = useState<SortConfig | null>(null);

    // Add state and handlers for editing columns
    const [isCreateColumnModalOpen, setIsCreateColumnModalOpen] =
      useState(false);
    const [editingColumn, setEditingColumn] = useState<ColumnType | null>(null);

    const [dragState, setDragState] = useState<DragState>({
      isDragging: false,
      dragY: null,
    });
    const gridRef = useRef<HTMLDivElement>(null);

    // Local state for cells
    const [localCells, setLocalCells] = useState<DatacellType[]>(initialCells);

    // Add an effect to update localCells when initialCells changes
    useEffect(() => {
      setLocalCells(initialCells);
    }, [initialCells]);

    // Add a function to derive cell status from a cell
    const deriveCellStatus = useCallback(
      (cell: DatacellType): CellStatus => {
        const extractIsProcessing =
          extract.started && !extract.finished && !extract.error;
        const cellIsProcessing =
          cell.started && !cell.completed && !cell.failed;
        const isProcessing =
          cellIsProcessing || (extractIsProcessing && !cell.started);

        return {
          isLoading: Boolean(isProcessing),
          isApproved: Boolean(cell.approvedBy),
          isRejected: Boolean(cell.rejectedBy),
          isEdited: Boolean(cell.correctedData),
          originalData: cell.data || null,
          correctedData: cell.correctedData || null,
          error: cell.failed || null,
        };
      },
      [extract]
    );

    // Check if extract is complete
    const isExtractComplete =
      extract.started && extract.finished && !extract.error;

    // Convert data to grid format
    const gridRows = useMemo<ExtractGridRow[]>(() => {
      if (!rows || rows.length === 0) {
        return [];
      }

      return rows.map((row) => {
        const rowData: ExtractGridRow = {
          id: row.id,
          documentId: row.id,
          documentTitle: row.title || "",
        };

        columns.forEach((column) => {
          const cell = initialCells.find(
            (c) => c.document.id === row.id && c.column.id === column.id
          );

          if (cell) {
            rowData[column.id] = cell.data?.data || "";
          } else {
            rowData[column.id] = "";
          }
        });

        return rowData;
      });
    }, [rows, initialCells, columns]);

    // Separate mutations for edit, approve, and reject
    const [editDatacell] = useMutation<
      RequestEditDatacellOutputType,
      RequestEditDatacellInputType
    >(REQUEST_EDIT_DATACELL, {
      onCompleted: (data) => {
        toast.success("Cell updated!");
        const updatedCell = data.editDatacell.obj;
        setLocalCells((prev) =>
          prev.map((cell) => (cell.id === updatedCell.id ? updatedCell : cell))
        );
      },
      onError: () => toast.error("Failed to update cell!"),
    });

    const [approveDatacell] = useMutation<
      RequestApproveDatacellOutputType,
      RequestApproveDatacellInputType
    >(REQUEST_APPROVE_DATACELL, {
      onCompleted: (data) => {
        if (data.approveDatacell.ok) {
          toast.success("Cell approved!");
          const updatedCell = data.approveDatacell.obj;
          setLocalCells((prev) =>
            prev.map((cell) =>
              cell.id === updatedCell.id ? updatedCell : cell
            )
          );
        } else {
          toast.error(
            "Failed to approve cell: " + data.approveDatacell.message
          );
        }
      },
      onError: () => toast.error("Failed to approve cell!"),
    });

    const [rejectDatacell] = useMutation<
      RequestRejectDatacellOutputType,
      RequestRejectDatacellInputType
    >(REQUEST_REJECT_DATACELL, {
      onCompleted: (data) => {
        if (data.rejectDatacell.ok) {
          toast.success("Cell rejected!");
          const updatedCell = data.rejectDatacell.obj;
          setLocalCells((prev) =>
            prev.map((cell) =>
              cell.id === updatedCell.id ? updatedCell : cell
            )
          );
        } else {
          toast.error("Failed to reject cell: " + data.rejectDatacell.message);
        }
      },
      onError: () => toast.error("Failed to reject cell!"),
    });

    // Handlers for edit, approve, and reject
    const handleEditDatacell = useCallback(
      async (datacellId: string, editedData: any) => {
        if (!isExtractComplete) {
          toast.warn("Cannot edit cells until extract is complete");
          return;
        }

        await editDatacell({
          variables: {
            datacellId,
            editedData,
          },
        });
      },
      [editDatacell, isExtractComplete]
    );

    const handleApproveCell = useCallback(
      async (datacellId: string) => {
        if (!isExtractComplete) {
          toast.warn("Cannot approve cells until extract is complete");
          return;
        }

        await approveDatacell({
          variables: {
            datacellId,
          },
        });
      },
      [approveDatacell, isExtractComplete]
    );

    const handleRejectCell = useCallback(
      async (datacellId: string) => {
        if (!isExtractComplete) {
          toast.warn("Cannot reject cells until extract is complete");
          return;
        }

        await rejectDatacell({
          variables: {
            datacellId,
          },
        });
      },
      [rejectDatacell, isExtractComplete]
    );

    // Map cell statuses for quick access
    const cellStatusMap = useMemo(() => {
      const map = new Map<string, CellStatus>();
      localCells.forEach((cell) => {
        if (cell?.document?.id && cell?.column?.id) {
          const status = deriveCellStatus(cell);
          map.set(`${cell.document.id}-${cell.column.id}`, status);
        }
      });
      return map;
    }, [localCells, deriveCellStatus]);

    const handleEditColumn = (column: ColumnType) => {
      setEditingColumn(column);
      setIsCreateColumnModalOpen(true);
    };

    const handleAddColumn = () => {
      setIsCreateColumnModalOpen(true);
      setEditingColumn(null);
    };

    const handleColumnSubmit = async (data: any) => {
      if (editingColumn) {
        await updateColumnMutation({ variables: { ...data } });
      } else {
        await createColumn({
          variables: {
            fieldsetId: extract.fieldset?.id,
            ...data,
          },
        });
      }
      setIsCreateColumnModalOpen(false);
      setEditingColumn(null);
    };

    // Add createColumn mutation
    const [createColumn] = useMutation<
      RequestCreateColumnOutputType,
      RequestCreateColumnInputType
    >(REQUEST_CREATE_COLUMN, {
      refetchQueries: [
        {
          query: REQUEST_GET_EXTRACT,
          variables: { id: extract ? extract.id : "" },
        },
      ],
      onCompleted: (data) => {
        if (data.createColumn.ok) {
          toast.success("Column created successfully!");
        } else {
          toast.error(`Failed to create column: ${data.createColumn.message}`);
        }
      },
      onError: (error) => {
        console.error("Create column error:", error);
        toast.error("An error occurred while creating the column.");
      },
    });

    // Column schemas for validation
    const columnSchemas = useMemo(() => {
      const schemas = new Map<string, JSONSchema7>();
      columns.forEach((col) => {
        try {
          schemas.set(col.id, parseOutputType(col.outputType));
        } catch (error) {
          console.error(`Failed to parse schema for column ${col.id}:`, error);
          schemas.set(col.id, {});
        }
      });
      return schemas;
    }, [columns]);

    // Delete modal state
    const [deleteModalState, setDeleteModalState] =
      useState<DeleteColumnModalState>({
        isOpen: false,
        columnToDelete: null,
      });

    const handleDeleteColumn = (column: ColumnType) => {
      setDeleteModalState({
        isOpen: true,
        columnToDelete: column,
      });
    };

    const confirmDeleteColumn = async () => {
      if (!deleteModalState.columnToDelete) return;
      onRemoveColumnId(deleteModalState.columnToDelete.id);
      setDeleteModalState({
        isOpen: false,
        columnToDelete: null,
      });
    };

    const [updateColumnMutation] = useMutation<
      RequestUpdateColumnOutputType,
      RequestUpdateColumnInputType
    >(REQUEST_UPDATE_COLUMN, {
      refetchQueries: [
        {
          query: REQUEST_GET_EXTRACT,
          variables: { id: extract ? extract.id : "" },
        },
      ],
      onCompleted: (data) => {
        if (data.updateColumn.ok) {
          toast.success("Column updated successfully!");
        } else {
          toast.error(`Failed to update column: ${data.updateColumn.message}`);
        }
      },
      onError: (error) => {
        console.error("Update column error:", error);
        toast.error("An error occurred while updating the column.");
      },
    });

    // Upload document mutation
    const [uploadDocument] = useMutation(UPLOAD_DOCUMENT);

    // Handle document drops
    const onDrop = useCallback(
      async (acceptedFiles: File[]) => {
        try {
          const uploadPromises = acceptedFiles.map(async (file) => {
            const base64String = await new Promise<string>((resolve) => {
              const reader = new FileReader();
              reader.onload = () => {
                const base64 = (reader.result as string).split(",")[1];
                resolve(base64);
              };
              reader.readAsDataURL(file);
            });

            const response = await uploadDocument({
              variables: {
                base64FileString: base64String,
                filename: file.name,
                title: file.name,
                description: "",
                customMeta: {},
                makePublic: false,
                ...(extract.corpus?.id
                  ? { addToCorpusId: extract.corpus.id }
                  : {}),
              },
            });

            return response.data.uploadDocument.document.id;
          });

          const newDocumentIds = await Promise.all(uploadPromises);
          onAddDocIds(extract.id, newDocumentIds);
        } catch (error) {
          toast.error("Failed to upload documents");
          console.error("Upload error:", error);
        }
      },
      [extract, uploadDocument, onAddDocIds]
    );

    const { getRootProps, getInputProps, isDragActive } = useDropzone({
      onDrop,
      noClick: true,
      noKeyboard: true,
      accept: {
        "application/pdf": [".pdf"],
      },
    });

    const [openSelectDocumentsModal, setOpenSelectDocumentsModal] =
      useState<boolean>(false);

    const handleRowsDelete = useCallback(async () => {
      if (!extract.started && selectedRows.size > 0) {
        setIsDeleting(true);
        try {
          const documentIds = Array.from(selectedRows);
          await onRemoveDocIds(extract.id, documentIds);
          setSelectedRows(new Set());
          toast.success(
            `Successfully removed ${documentIds.length} document(s)`
          );
        } catch (error) {
          toast.error("Failed to remove selected documents");
          console.error("Delete error:", error);
        } finally {
          setIsDeleting(false);
        }
      }
    }, [extract.id, extract.started, selectedRows, onRemoveDocIds]);

    // Handle row selection
    const handleRowSelect = (rowId: string) => {
      setSelectedRows((prev) => {
        const newSet = new Set(prev);
        if (newSet.has(rowId)) {
          newSet.delete(rowId);
        } else {
          newSet.add(rowId);
        }
        return newSet;
      });
    };

    const handleSelectAll = () => {
      if (selectedRows.size === gridRows.length) {
        setSelectedRows(new Set());
      } else {
        setSelectedRows(new Set(gridRows.map((row) => row.id)));
      }
    };

    // Sorting logic
    const handleSort = (columnId: string) => {
      setSortConfig((current) => {
        if (!current || current.columnId !== columnId) {
          return { columnId, direction: "ASC" };
        }
        if (current.direction === "ASC") {
          return { columnId, direction: "DESC" };
        }
        return null;
      });
    };

    const sortedRows = useMemo(() => {
      if (!sortConfig) return gridRows;

      return [...gridRows].sort((a, b) => {
        const aValue = a[sortConfig.columnId];
        const bValue = b[sortConfig.columnId];

        if (aValue == null && bValue != null) return -1;
        if (aValue != null && bValue == null) return 1;
        if (aValue == null && bValue == null) return 0;

        let comparison = 0;
        if (typeof aValue === "number" && typeof bValue === "number") {
          comparison = aValue - bValue;
        } else {
          comparison = String(aValue).localeCompare(String(bValue));
        }

        return sortConfig.direction === "ASC" ? comparison : -comparison;
      });
    }, [gridRows, sortConfig]);

    // Export to CSV
    const exportToCsv = useCallback(() => {
      const csvRows = [];
      const headers = ["Document", ...columns.map((col) => col.name)];
      csvRows.push(headers.join(","));

      sortedRows.forEach((row) => {
        const csvRow = [row.documentTitle];
        columns.forEach((col) => {
          let cellValue = row[col.id];

          if (cellValue == null) {
            cellValue = "";
          } else if (typeof cellValue === "object") {
            cellValue = JSON.stringify(cellValue);
          } else {
            cellValue = String(cellValue);
          }

          cellValue = cellValue.replace(/"/g, '""');
          if (cellValue.includes(",") || cellValue.includes("\n")) {
            cellValue = `"${cellValue}"`;
          }

          csvRow.push(cellValue);
        });
        csvRows.push(csvRow.join(","));
      });

      const csvContent = csvRows.join("\n");
      const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${extract.name || "data"}.csv`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    }, [columns, sortedRows, extract.name]);

    useImperativeHandle(ref, () => ({
      exportToCsv,
    }));

    return (
      <>
        <SelectDocumentsModal
          open={openSelectDocumentsModal}
          onAddDocumentIds={(documentIds: string[]) =>
            onAddDocIds(extract.id, documentIds)
          }
          filterDocIds={rows.map((row) => row.id)}
          toggleModal={() =>
            setOpenSelectDocumentsModal(!openSelectDocumentsModal)
          }
        />

        <div {...getRootProps()} ref={gridRef} style={styles.gridWrapper}>
          {loading && (
            <Dimmer
              active
              inverted
              style={{
                position: "absolute",
                margin: 0,
                borderRadius: "16px",
                top: 0,
                left: 0,
                right: 0,
                bottom: 0,
                zIndex: 100,
              }}
            >
              <Loader>
                {extract.started && !extract.finished
                  ? "Processing..."
                  : "Loading..."}
              </Loader>
            </Dimmer>
          )}
          <input {...getInputProps()} />

          {!extract.started && selectedRows.size > 0 && (
            <div
              style={{
                padding: "0.75rem 1rem",
                borderBottom: "1px solid #e2e8f0",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                backgroundColor: "#f8fafc",
                position: "sticky",
                top: 0,
                zIndex: 9,
              }}
            >
              <Button
                negative
                size="small"
                onClick={handleRowsDelete}
                icon
                labelPosition="left"
                loading={isDeleting}
                disabled={isDeleting}
              >
                <Icon name="trash" />
                Delete Selected ({selectedRows.size})
              </Button>
            </div>
          )}

          <div style={styles.tableContainer}>
            {gridRows.length === 0 ? (
              <div style={styles.emptyState}>
                <Icon name="file pdf outline" style={styles.emptyStateIcon} />
                <h3 style={styles.emptyStateTitle}>No documents yet</h3>
                <p style={styles.emptyStateText}>
                  Drop PDF documents here or click the button below to add
                  documents to this extract
                </p>
              </div>
            ) : (
              <Table celled compact>
                <Table.Header style={styles.stickyHeader}>
                  <Table.Row>
                    {!extract.started && (
                      <Table.HeaderCell
                        style={{
                          ...styles.headerCell,
                          ...styles.frozenHeaderColumn,
                          width: "50px",
                        }}
                      >
                        <Checkbox
                          checked={
                            selectedRows.size === gridRows.length &&
                            gridRows.length > 0
                          }
                          indeterminate={
                            selectedRows.size > 0 &&
                            selectedRows.size < gridRows.length
                          }
                          onChange={handleSelectAll}
                          disabled={loading}
                        />
                      </Table.HeaderCell>
                    )}
                    <Table.HeaderCell
                      style={{
                        ...styles.headerCell,
                        ...styles.frozenHeaderColumn,
                        minWidth: "250px",
                      }}
                      onClick={() => handleSort("documentTitle")}
                    >
                      Document
                      {sortConfig?.columnId === "documentTitle" && (
                        <Icon
                          name={
                            sortConfig.direction === "ASC"
                              ? "angle up"
                              : "angle down"
                          }
                          style={{ marginLeft: "8px", opacity: 0.6 }}
                        />
                      )}
                    </Table.HeaderCell>
                    {columns.map((column) => (
                      <Table.HeaderCell
                        key={column.id}
                        style={{ ...styles.headerCell, minWidth: "180px" }}
                        onClick={() => handleSort(column.id)}
                      >
                        <div
                          style={{
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "space-between",
                          }}
                        >
                          <span
                            style={{ display: "flex", alignItems: "center" }}
                          >
                            {column.name}
                            {sortConfig?.columnId === column.id && (
                              <Icon
                                name={
                                  sortConfig.direction === "ASC"
                                    ? "angle up"
                                    : "angle down"
                                }
                                style={{ marginLeft: "8px", opacity: 0.6 }}
                              />
                            )}
                          </span>
                          {!extract.started && (
                            <span style={styles.headerControls}>
                              <Popup
                                content="Edit column"
                                trigger={
                                  <button
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      handleEditColumn(column);
                                    }}
                                    style={{
                                      ...styles.actionButton,
                                      padding: "4px 8px",
                                    }}
                                    disabled={loading}
                                  >
                                    <Icon
                                      name="edit"
                                      style={{ margin: 0, fontSize: "12px" }}
                                    />
                                  </button>
                                }
                              />
                              <Popup
                                content="Delete column"
                                trigger={
                                  <button
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      handleDeleteColumn(column);
                                    }}
                                    style={{
                                      ...styles.actionButton,
                                      padding: "4px 8px",
                                      color: "#ef4444",
                                    }}
                                    disabled={loading}
                                  >
                                    <Icon
                                      name="trash"
                                      style={{ margin: 0, fontSize: "12px" }}
                                    />
                                  </button>
                                }
                              />
                            </span>
                          )}
                        </div>
                      </Table.HeaderCell>
                    ))}
                    {!extract.started && (
                      <Table.HeaderCell
                        style={{ ...styles.headerCell, width: "80px" }}
                      >
                        <Popup
                          content="Add new column"
                          trigger={
                            <button
                              onClick={handleAddColumn}
                              style={styles.addColumnButton}
                              disabled={loading}
                            >
                              <Icon name="plus" style={{ margin: 0 }} />
                            </button>
                          }
                        />
                      </Table.HeaderCell>
                    )}
                  </Table.Row>
                </Table.Header>

                <Table.Body>
                  {sortedRows.map((row) => {
                    const isSelected = selectedRows.has(row.id);
                    return (
                      <Table.Row
                        key={row.id}
                        style={{
                          backgroundColor: isSelected ? "#eff6ff" : undefined,
                        }}
                      >
                        {!extract.started && (
                          <Table.Cell
                            style={{
                              ...styles.tableCell,
                              ...styles.frozenColumn,
                            }}
                          >
                            <Checkbox
                              checked={isSelected}
                              onChange={() => handleRowSelect(row.id)}
                              disabled={loading}
                            />
                          </Table.Cell>
                        )}
                        <Table.Cell
                          style={{
                            ...styles.tableCell,
                            ...styles.frozenColumn,
                          }}
                        >
                          <TruncatedText
                            text={row.documentTitle || ""}
                            limit={100}
                          />
                        </Table.Cell>
                        {columns.map((column) => {
                          const cell = localCells.find(
                            (c) =>
                              c.document?.id === row.id &&
                              c.column?.id === column.id
                          );
                          const cellStatus = cellStatusMap.get(
                            `${row.id}-${column.id}`
                          );

                          return (
                            <Table.Cell
                              key={column.id}
                              style={styles.tableCell}
                            >
                              <ExtractCellFormatter
                                value={row[column.id] || ""}
                                cellStatus={cellStatus || null}
                                onApprove={() =>
                                  handleApproveCell(cell?.id || "")
                                }
                                onReject={() =>
                                  handleRejectCell(cell?.id || "")
                                }
                                onEdit={handleEditDatacell}
                                cellId={cell?.id || ""}
                                readOnly={Boolean(
                                  !isExtractComplete || loading
                                )}
                                isExtractComplete={Boolean(isExtractComplete)}
                                schema={columnSchemas.get(column.id) || {}}
                                extractIsList={column.extractIsList || false}
                                row={row}
                                column={{
                                  key: column.id,
                                  name: column.name,
                                  id: column.id,
                                  width: 250,
                                  resizable: false,
                                }}
                                cell={cell}
                                extract={extract}
                              />
                            </Table.Cell>
                          );
                        })}
                        {!extract.started && (
                          <Table.Cell style={styles.tableCell} />
                        )}
                      </Table.Row>
                    );
                  })}
                </Table.Body>
              </Table>
            )}
          </div>

          {!extract.started && (
            <Button
              icon="file outline"
              circular
              onClick={() => setOpenSelectDocumentsModal(true)}
              style={{
                position: "absolute",
                bottom: "16px",
                left: "16px",
                zIndex: 1000,
              }}
              disabled={loading}
            >
              <Icon name="plus" corner="top right" />
            </Button>
          )}

          {isDragActive && (
            <div style={styles.dropOverlay}>
              <div style={styles.dropMessage}>
                Drop PDF documents here to add to{" "}
                {extract.corpus ? "corpus and extract" : "extract"}
              </div>
            </div>
          )}
        </div>

        <CreateColumnModal
          open={isCreateColumnModalOpen || editingColumn !== null}
          existing_column={editingColumn}
          onClose={() => {
            setIsCreateColumnModalOpen(false);
            setEditingColumn(null);
          }}
          onSubmit={handleColumnSubmit}
        />

        <Modal
          size="tiny"
          open={deleteModalState.isOpen}
          onClose={() =>
            setDeleteModalState({ isOpen: false, columnToDelete: null })
          }
          style={{ borderRadius: "12px", padding: "1.5rem" }}
        >
          <Modal.Header
            style={{ borderBottom: "1px solid #f1f5f9", paddingBottom: "1rem" }}
          >
            Confirm Delete
          </Modal.Header>
          <Modal.Content>
            <p style={{ color: "#475569" }}>
              Are you sure you want to delete the column "
              {deleteModalState.columnToDelete?.name}"?
            </p>
            {extract.fieldset?.inUse && (
              <Message warning>
                <Message.Header>Note:</Message.Header>
                <p>
                  This fieldset is used in multiple places. Deleting this column
                  will create a new copy of the fieldset for this extract only.
                </p>
              </Message>
            )}
          </Modal.Content>
          <Modal.Actions
            style={{ borderTop: "1px solid #f1f5f9", paddingTop: "1rem" }}
          >
            <Button
              basic
              onClick={() =>
                setDeleteModalState({ isOpen: false, columnToDelete: null })
              }
              style={{
                borderRadius: "6px",
                boxShadow: "none",
                border: "1px solid #e2e8f0",
              }}
            >
              Cancel
            </Button>
            <Button
              negative
              onClick={confirmDeleteColumn}
              style={{
                borderRadius: "6px",
                backgroundColor: "#ef4444",
                marginLeft: "0.75rem",
              }}
            >
              Delete
            </Button>
          </Modal.Actions>
        </Modal>
      </>
    );
  }
);
