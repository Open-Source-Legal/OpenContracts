import React, {
  useState,
  useEffect,
  useCallback,
  useRef,
  useMemo,
} from "react";
import { Button, Table } from "@os-legal/ui";
import { Loader2, Circle } from "lucide-react";
import { useQuery, useMutation, useLazyQuery } from "@apollo/client";
import { toast } from "react-toastify";
import styled from "styled-components";
import { debounce } from "lodash";

import {
  GET_CORPUS_METADATA_COLUMNS,
  GET_DOCUMENTS_METADATA_BATCH,
  SET_METADATA_VALUE,
  DELETE_METADATA_VALUE,
  GetCorpusMetadataColumnsInput,
  GetCorpusMetadataColumnsOutput,
  GetDocumentsMetadataBatchInput,
  GetDocumentsMetadataBatchOutput,
  SetMetadataValueInput,
  SetMetadataValueOutput,
  DeleteMetadataValueInput,
  DeleteMetadataValueOutput,
} from "../../graphql/metadataOperations";
import {
  MetadataColumn,
  MetadataDataType,
  MetadataDatacell,
  validateMetadataValue,
  formatMetadataValue,
  getDefaultValueForDataType,
} from "../../types/metadata";
import { DocumentType, PageInfo } from "../../types/graphql-api";
import { MetadataCellEditor } from "../metadata/editors/MetadataCellEditor";
import { FetchMoreOnVisible } from "../widgets/infinite_scroll/FetchMoreOnVisible";
import { DEBOUNCE } from "../../assets/configurations/constants";
import { InfoMessage, LoadingState } from "../widgets/feedback";
import { OS_LEGAL_COLORS } from "../../assets/configurations/osLegalStyles";

interface DocumentMetadataGridProps {
  corpusId: string;
  documents: DocumentType[];
  loading?: boolean;
  onDocumentClick?: (document: DocumentType) => void;
  pageInfo?: PageInfo;
  fetchMore?: (args?: any) => void | any;
  hasMore?: boolean;
}

const GridContainer = styled.div`
  height: 100%;
  width: 100%;
  position: relative;
  background: #ffffff;
  border-radius: 16px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
`;

const GridWrapper = styled.div`
  flex: 1;
  overflow: auto;
  position: relative;
  min-height: 0;
  -webkit-overflow-scrolling: touch;
`;

const DocumentNameCell = styled.span`
  font-weight: 600;
  cursor: pointer;
  color: ${OS_LEGAL_COLORS.primaryBlue};

  &:hover {
    color: ${OS_LEGAL_COLORS.primaryBlueHover};
    text-decoration: underline;
  }
`;

const EditableCell = styled.div.attrs<{
  isEditing: boolean;
  hasError: boolean;
}>((props) => ({
  // Ensure onClick is properly passed through
  onClick: props.onClick,
}))`
  min-height: 2rem;
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  cursor: pointer;
  display: flex;
  align-items: center;
  background: ${(props) =>
    props.isEditing
      ? OS_LEGAL_COLORS.infoSurface
      : props.hasError
        ? OS_LEGAL_COLORS.dangerSurface
        : "transparent"};
  border: 1px solid
    ${(props) =>
      props.isEditing
        ? OS_LEGAL_COLORS.primaryBlue
        : props.hasError
          ? OS_LEGAL_COLORS.danger
          : "transparent"};

  &:hover {
    background: ${(props) =>
      props.isEditing
        ? OS_LEGAL_COLORS.infoSurface
        : OS_LEGAL_COLORS.surfaceHover};
  }
`;

const EmptyValue = styled.span`
  color: ${OS_LEGAL_COLORS.borderHover};
  font-style: italic;
`;

const ErrorTooltip = styled.div`
  position: absolute;
  bottom: -2rem;
  left: 0.5rem;
  z-index: 10;
  background: ${OS_LEGAL_COLORS.danger};
  color: white;
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  font-size: 0.75rem;
  max-width: 200px;
  white-space: nowrap;
  pointer-events: none;
`;

const PaginationFooter = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem;
  border-top: 1px solid ${OS_LEGAL_COLORS.border};
  background: ${OS_LEGAL_COLORS.surfaceHover};
`;

const PaginationInfo = styled.div`
  color: ${OS_LEGAL_COLORS.textSecondary};
  font-size: 0.875rem;
`;

interface CellKey {
  documentId: string;
  columnId: string;
}

export const DocumentMetadataGrid: React.FC<DocumentMetadataGridProps> = ({
  corpusId,
  documents,
  loading: documentsLoading,
  onDocumentClick,
  pageInfo,
  fetchMore,
  hasMore,
}) => {
  const [editingCell, setEditingCell] = useState<CellKey | null>(null);
  const [cellValues, setCellValues] = useState<Record<string, any>>({});
  const [validationErrors, setValidationErrors] = useState<
    Record<string, string>
  >({});
  const [dirtyFields, setDirtyFields] = useState<Set<string>>(new Set());
  const [savingFields, setSavingFields] = useState<Set<string>>(new Set());

  // Ref to access current validationErrors from debounced callback without
  // causing the debounced function to be recreated on every change
  const validationErrorsRef = useRef(validationErrors);
  validationErrorsRef.current = validationErrors;

  // Query metadata columns
  const { data: columnsData, loading: columnsLoading } = useQuery<
    GetCorpusMetadataColumnsOutput,
    GetCorpusMetadataColumnsInput
  >(GET_CORPUS_METADATA_COLUMNS, {
    variables: { corpusId },
  });

  // For now, we'll need to load metadata per document
  // In a real implementation, we'd want a batch query
  const [datacellsMap, setDatacellsMap] = useState<
    Record<string, MetadataDatacell[]>
  >({});

  // Mutations
  const [setMetadataValue] = useMutation<
    SetMetadataValueOutput,
    SetMetadataValueInput
  >(SET_METADATA_VALUE, {
    onCompleted: (data, options) => {
      const variables = options?.variables;
      if (variables) {
        const key = getCellKey({
          documentId: variables.documentId,
          columnId: variables.columnId,
        });
        setSavingFields((prev) => {
          const next = new Set(prev);
          next.delete(key);
          return next;
        });
      }

      if (data.setMetadataValue.ok) {
        const key = getCellKey(editingCell!);
        setDirtyFields((prev) => {
          const next = new Set(prev);
          next.delete(key);
          return next;
        });
      } else {
        toast.error(data.setMetadataValue.message);
      }
    },
    onError: (error, options) => {
      const variables = options?.variables;
      if (variables) {
        const key = getCellKey({
          documentId: variables.documentId,
          columnId: variables.columnId,
        });
        setSavingFields((prev) => {
          const next = new Set(prev);
          next.delete(key);
          return next;
        });
      }
      toast.error(`Failed to save: ${error.message}`);
    },
  });

  const [deleteMetadataValue] = useMutation<
    DeleteMetadataValueOutput,
    DeleteMetadataValueInput
  >(DELETE_METADATA_VALUE);

  // Helper functions
  const getCellKey = (cell: CellKey): string =>
    `${cell.documentId}-${cell.columnId}`;

  const getDatacell = (
    documentId: string,
    columnId: string
  ): MetadataDatacell | undefined => {
    const datacells = datacellsMap[documentId] || [];
    return datacells.find((d) => d.column.id === columnId);
  };

  const getCellValue = (documentId: string, columnId: string): any => {
    const key = getCellKey({ documentId, columnId });
    if (cellValues.hasOwnProperty(key)) {
      return cellValues[key];
    }
    const datacell = getDatacell(documentId, columnId);
    return datacell?.data?.value;
  };

  const handleCellClick = (documentId: string, columnId: string) => {
    // Don't enter edit mode if clicking the same cell
    if (
      editingCell?.documentId === documentId &&
      editingCell?.columnId === columnId
    ) {
      return;
    }
    setEditingCell({ documentId, columnId });
  };

  const handleCellChange = (value: any) => {
    if (!editingCell) return;

    const key = getCellKey(editingCell);
    setCellValues((prev) => ({ ...prev, [key]: value }));
    setDirtyFields((prev) => new Set(prev).add(key));

    // Validate
    const column = columns.find((c) => c.id === editingCell.columnId);
    if (column) {
      const isValid = validateMetadataValue(value, column);
      if (isValid) {
        setValidationErrors((prev) => {
          const next = { ...prev };
          delete next[key];
          return next;
        });
      } else {
        setValidationErrors((prev) => ({
          ...prev,
          [key]: "Invalid value",
        }));
      }
    }

    // Debounced save
    debouncedSave(editingCell.documentId, editingCell.columnId, value);
  };

  // Use useMemo instead of useCallback to create a stable debounced function.
  // We read validationErrors from a ref to avoid recreating the debounced
  // function on every keystroke (which would defeat the debounce).
  const debouncedSave = useMemo(
    () =>
      debounce(async (documentId: string, columnId: string, value: any) => {
        const key = getCellKey({ documentId, columnId });
        const error = validationErrorsRef.current[key];

        if (error) {
          return; // Don't save if there's a validation error
        }

        // Set saving state
        setSavingFields((prev) => new Set(prev).add(key));

        // Save the value
        try {
          if (value === null || value === undefined || value === "") {
            // Delete the datacell if value is empty
            await deleteMetadataValue({
              variables: { documentId, corpusId, columnId },
            });
          } else {
            await setMetadataValue({
              variables: { documentId, corpusId, columnId, value },
            });
          }
        } catch (error) {
          // Error handling is done in mutation callbacks
          setSavingFields((prev) => {
            const next = new Set(prev);
            next.delete(key);
            return next;
          });
        }
      }, DEBOUNCE.METADATA_SAVE_MS),
    [corpusId, setMetadataValue, deleteMetadataValue]
  );

  // Cancel pending debounced saves on unmount
  useEffect(() => {
    return () => {
      debouncedSave.cancel();
    };
  }, [debouncedSave]);

  const handleNavigate = (direction: "next" | "previous" | "down" | "up") => {
    if (!editingCell) return;

    switch (direction) {
      case "next":
        // Move to next column
        const currentColIndex = columns.findIndex(
          (c) => c.id === editingCell.columnId
        );
        if (currentColIndex < columns.length - 1) {
          setEditingCell({
            documentId: editingCell.documentId,
            columnId: columns[currentColIndex + 1].id,
          });
        }
        break;
      case "previous":
        // Move to previous column
        const prevColIndex = columns.findIndex(
          (c) => c.id === editingCell.columnId
        );
        if (prevColIndex > 0) {
          setEditingCell({
            documentId: editingCell.documentId,
            columnId: columns[prevColIndex - 1].id,
          });
        }
        break;
      case "down":
        // Move to next row
        const currentDocIndex = documents.findIndex(
          (d) => d.id === editingCell.documentId
        );
        if (currentDocIndex < documents.length - 1) {
          setEditingCell({
            documentId: documents[currentDocIndex + 1].id,
            columnId: editingCell.columnId,
          });
        } else {
          setEditingCell(null);
        }
        break;
      case "up":
        // Move to previous row
        const prevDocIndex = documents.findIndex(
          (d) => d.id === editingCell.documentId
        );
        if (prevDocIndex > 0) {
          setEditingCell({
            documentId: documents[prevDocIndex - 1].id,
            columnId: editingCell.columnId,
          });
        }
        break;
    }
  };

  // Navigation is now handled directly by the MetadataCellEditor

  // Process columns
  const columns = (columnsData?.corpusMetadataColumns || [])
    .filter((col) => col.isManualEntry)
    .map((col) => ({
      ...col,
      dataType: col.dataType as MetadataDataType,
    }))
    .sort(
      (a, b) =>
        ((a as any).displayOrder ?? (a as any).orderIndex ?? 0) -
        ((b as any).displayOrder ?? (b as any).orderIndex ?? 0)
    );

  // Batch query to fetch metadata for all documents at once
  const [fetchDocumentsMetadataBatch] = useLazyQuery<
    GetDocumentsMetadataBatchOutput,
    GetDocumentsMetadataBatchInput
  >(GET_DOCUMENTS_METADATA_BATCH);

  // Load metadata for all documents in a single batch query
  useEffect(() => {
    const loadMetadata = async () => {
      const newDatacellsMap: Record<string, MetadataDatacell[]> = {};

      // For testing purposes, if documents have a metadata property, use it
      // This allows tests to provide pre-loaded metadata
      let hasPreloadedData = false;
      documents.forEach((doc) => {
        if ((doc as any).metadata?.edges) {
          newDatacellsMap[doc.id] = (doc as any).metadata.edges.map(
            (edge: any) => edge.node
          );
          hasPreloadedData = true;
        }
      });

      // If no preloaded data, fetch from backend using batch query
      if (!hasPreloadedData && corpusId && documents.length > 0) {
        try {
          const documentIds = documents.map((doc) => doc.id);
          const { data } = await fetchDocumentsMetadataBatch({
            variables: {
              documentIds,
              corpusId,
            },
          });

          if (data?.documentsMetadataDatacellsBatch) {
            // Map results back to documents by documentId
            for (const result of data.documentsMetadataDatacellsBatch) {
              newDatacellsMap[result.documentId] =
                result.datacells as MetadataDatacell[];
            }
          }
        } catch (error) {
          console.error("Failed to fetch metadata batch:", error);
        }
      }

      if (Object.keys(newDatacellsMap).length > 0 || documents.length > 0) {
        setDatacellsMap(newDatacellsMap);
      }
    };

    loadMetadata();
  }, [documents, corpusId, fetchDocumentsMetadataBatch]);

  const loading = columnsLoading || documentsLoading;

  if (loading) {
    return (
      <GridContainer>
        <LoadingState message="Loading metadata..." />
      </GridContainer>
    );
  }

  if (columns.length === 0) {
    return (
      <GridContainer>
        <InfoMessage
          title="No Metadata Fields Defined"
          style={{ margin: "1rem" }}
        >
          This corpus doesn't have any metadata fields yet. Go to corpus
          settings to create metadata fields.
        </InfoMessage>
      </GridContainer>
    );
  }

  return (
    <GridContainer>
      <GridWrapper id="document-metadata-grid-wrapper">
        <Table variant="bordered" size="sm" stickyHeader>
          <Table.Head>
            <Table.Row>
              <Table.HeadCell sticky="left">Document</Table.HeadCell>
              {columns.map((column) => (
                <Table.HeadCell key={column.id}>
                  {column.name}
                  {column.validationConfig?.required && (
                    <span
                      style={{
                        color: OS_LEGAL_COLORS.danger,
                        marginLeft: "0.25rem",
                      }}
                    >
                      *
                    </span>
                  )}
                </Table.HeadCell>
              ))}
            </Table.Row>
          </Table.Head>
          <Table.Body>
            {documents.map((document) => (
              <Table.Row key={document.id}>
                <Table.Cell
                  sticky="left"
                  onClick={() => onDocumentClick?.(document)}
                >
                  <DocumentNameCell>{document.title}</DocumentNameCell>
                </Table.Cell>
                {columns.map((column) => {
                  const isEditing =
                    editingCell?.documentId === document.id &&
                    editingCell?.columnId === column.id;
                  const cellKey = getCellKey({
                    documentId: document.id,
                    columnId: column.id,
                  });
                  const value = getCellValue(document.id, column.id);
                  const hasError = !!validationErrors[cellKey];
                  const isDirty = dirtyFields.has(cellKey);
                  const isSaving = savingFields.has(cellKey);

                  return (
                    <Table.Cell key={column.id} className="metadata-grid-cell">
                      {isEditing ? (
                        <MetadataCellEditor
                          column={column}
                          value={value}
                          onChange={handleCellChange}
                          onBlur={() => setEditingCell(null)}
                          onNavigate={handleNavigate}
                          error={validationErrors[cellKey]}
                          autoFocus
                        />
                      ) : (
                        <div style={{ position: "relative" }}>
                          <EditableCell
                            isEditing={false}
                            hasError={hasError}
                            onClick={(e) => {
                              e.stopPropagation();
                              handleCellClick(document.id, column.id);
                            }}
                            data-testid={`cell-${document.id}-${column.id}`}
                          >
                            {value !== null &&
                            value !== undefined &&
                            value !== "" ? (
                              <span>
                                {formatMetadataValue(value, column.dataType)}
                                {isSaving && (
                                  <Loader2
                                    size={12}
                                    color={OS_LEGAL_COLORS.primaryBlue}
                                    style={{
                                      marginLeft: "0.5rem",
                                      animation: "spin 1s linear infinite",
                                    }}
                                    data-testid="saving-indicator"
                                  />
                                )}
                                {isDirty && !isSaving && (
                                  <Circle
                                    size={8}
                                    color={OS_LEGAL_COLORS.primaryBlue}
                                    fill={OS_LEGAL_COLORS.primaryBlue}
                                    style={{ marginLeft: "0.5rem" }}
                                  />
                                )}
                              </span>
                            ) : (
                              <EmptyValue>Click to edit</EmptyValue>
                            )}
                          </EditableCell>
                          {hasError && (
                            <ErrorTooltip>
                              {validationErrors[cellKey]}
                            </ErrorTooltip>
                          )}
                        </div>
                      )}
                    </Table.Cell>
                  );
                })}
              </Table.Row>
            ))}
          </Table.Body>
        </Table>
        {hasMore && fetchMore && (
          <PaginationFooter>
            <PaginationInfo>
              Showing {documents.length} of many documents
            </PaginationInfo>
            <Button
              variant="primary"
              size="sm"
              onClick={() => {
                if (!documentsLoading && pageInfo?.hasNextPage && fetchMore) {
                  fetchMore({
                    variables: {
                      limit: 20,
                      cursor: pageInfo.endCursor,
                    },
                  });
                }
              }}
              disabled={documentsLoading}
              loading={documentsLoading}
            >
              Load More Documents
            </Button>
          </PaginationFooter>
        )}
      </GridWrapper>
    </GridContainer>
  );
};
