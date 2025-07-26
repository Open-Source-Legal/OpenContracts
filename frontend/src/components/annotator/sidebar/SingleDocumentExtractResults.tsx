import React, { useState, useRef } from "react";
import styled from "styled-components";
import { Code, Check, X, Eye, Edit3, EyeOff } from "lucide-react";
import { Dimmer, Loader } from "semantic-ui-react";
import { CellEditor } from "./CellEditor";
import {
  ColumnType,
  DatacellType,
  LabelDisplayBehavior,
} from "../../../types/graphql-api";
import { useMutation, gql } from "@apollo/client";
import {
  REQUEST_APPROVE_DATACELL,
  REQUEST_REJECT_DATACELL,
  RequestApproveDatacellInputType,
  RequestApproveDatacellOutputType,
  RequestRejectDatacellInputType,
  RequestRejectDatacellOutputType,
  REQUEST_EDIT_DATACELL,
  RequestEditDatacellOutputType,
  RequestEditDatacellInputType,
} from "../../../graphql/mutations";
import { TruncatedText } from "../../widgets/data-display/TruncatedText";
import { HighlightItem } from "./HighlightItem";
import {
  displayAnnotationOnAnnotatorLoad,
  onlyDisplayTheseAnnotations,
  showSelectedAnnotationOnly,
  showAnnotationBoundingBoxes,
  showStructuralAnnotations,
  showAnnotationLabels,
} from "../../../graphql/cache";
import { toast } from "react-toastify";
import { convertToServerAnnotation } from "../../../utils/transform";
import ReactJson from "react-json-view";
import { useAnalysisManager } from "../hooks/AnalysisHooks";

interface SingleDocumentExtractResultsProps {
  datacells: DatacellType[];
  columns: ColumnType[];
}

/**
 * SingleDocumentExtractResults component displays the extraction results forss a single document.
 * It renders a table with columns and their extracted data, along with any associated annotations.
 */
export const SingleDocumentExtractResults: React.FC<
  SingleDocumentExtractResultsProps
> = ({ datacells, columns }) => {
  // State variables
  const [hoveredRow, setHoveredRow] = useState<string | null>(null);
  const [tryingApprove, setTryingApprove] = useState(false);
  const [tryingReject, setTryingReject] = useState(false);
  const [activeCellId, setActiveCellId] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [annotationVisibility, setAnnotationVisibility] = useState<{
    [key: string]: boolean;
  }>({});
  const cellRefs = useRef<{ [key: string]: HTMLDivElement }>({});
  const [isEditing, setIsEditing] = useState(false);
  const [editingCell, setEditingCell] = useState<DatacellType | null>(null);

  const [requestApprove] = useMutation<
    RequestApproveDatacellOutputType,
    RequestApproveDatacellInputType
  >(REQUEST_APPROVE_DATACELL);

  const [requestReject] = useMutation<
    RequestRejectDatacellOutputType,
    RequestRejectDatacellInputType
  >(REQUEST_REJECT_DATACELL);

  const [updateDatacell, { loading: updatingDatacell }] = useMutation<
    RequestEditDatacellOutputType,
    RequestEditDatacellInputType
  >(REQUEST_EDIT_DATACELL, {
    update(cache, { data }) {
      if (data?.editDatacell?.obj) {
        const updatedCell = data.editDatacell.obj;

        cache.writeFragment({
          id: `DatacellType:${updatedCell.id}`,
          fragment: gql`
            fragment UpdatedDatacell on DatacellType {
              id
              data
              correctedData
              # Include other fields if necessary
            }
          `,
          data: updatedCell,
        });
      }
    },
  });

  const { dataCells, setDataCells } = useAnalysisManager();

  const lastCells = dataCells.length ? dataCells : datacells;

  // Compute activeCell dynamically
  const activeCell = activeCellId
    ? dataCells.find((cell) => cell.id === activeCellId)
    : null;

  /**
   * Toggles the visibility of annotations under a cell.
   * @param cellId - The ID of the datacell.
   */
  const toggleAnnotationVisibility = (cellId: string) => {
    setAnnotationVisibility((prevState) => ({
      ...prevState,
      [cellId]: !prevState[cellId],
    }));
  };

  /**
   * Gets the status color for a datacell based on its approval status.
   * @param cell - The datacell to get the status color for.
   * @returns The color representing the cell's status.
   */
  const getStatusColor = (cell: DatacellType): string => {
    if (cell.approvedBy) return "rgba(76, 175, 80, 0.05)"; // Light Green
    if (cell.rejectedBy) return "rgba(244, 67, 54, 0.05)"; // Light Red
    if (cell.correctedData) return "rgba(33, 150, 243, 0.05)"; // Light Blue
    return "transparent"; // Default
  };

  /**
   * Handles approving a datacell.
   * @param cell - The datacell to approve.
   */
  const handleApprove = (cell: DatacellType) => {
    setTryingApprove(true);

    requestApprove({ variables: { datacellId: cell.id } })
      .then((response) => {
        // Grab the real datacell
        const updatedCell = response.data?.approveDatacell?.obj;

        if (updatedCell) {
          setDataCells((prev) =>
            prev.map((c) => (c.id === updatedCell.id ? updatedCell : c))
          );
          toast.success("Cell approved successfully.");
        } else {
          toast.error("Failed to approve cell.");
        }
      })
      .catch(() => toast.error("Failed to approve cell."))
      .finally(() => setTryingApprove(false));
  };

  /**
   * Handles rejecting a datacell.
   * @param cell - The datacell to reject.
   */
  const handleReject = (cell: DatacellType) => {
    setTryingReject(true);

    requestReject({ variables: { datacellId: cell.id } })
      .then((response) => {
        // Grab the real datacell
        const updatedCell = response.data?.rejectDatacell?.obj;

        if (updatedCell) {
          setDataCells((prev) =>
            prev.map((c) => (c.id === updatedCell.id ? updatedCell : c))
          );
          toast.success("Cell rejected successfully.");
        } else {
          toast.error("Failed to reject cell.");
        }
      })
      .catch(() => toast.error("Failed to reject cell."))
      .finally(() => setTryingReject(false));
  };

  /**
   * Renders the value of a datacell.
   * @param cell - The datacell to render the value for.
   * @returns The rendered value as JSX.
   */
  const renderCellValue = (cell: DatacellType) => {
    const value = cell.correctedData?.data || cell.data?.data || "";
    const ref = cellRefs.current[cell.id];
    const cellWidth = ref?.offsetWidth ?? 0;

    return (
      <DataCell statusColor={getStatusColor(cell)}>
        <div style={{ flex: 1 }}>
          {typeof value === "object" && value !== null ? (
            <JsonViewButton
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                setActiveCellId(cell.id);
                setIsModalOpen(true);
              }}
            >
              <Code />
              <span>View JSON</span>
            </JsonViewButton>
          ) : (
            <TruncatedText text={String(value)} limit={cellWidth - 100} />
          )}
        </div>

        <div
          style={{
            display: "flex",
            justifyContent: "flex-start",
            marginTop: "8px",
          }}
        >
          <ActionButton
            className="edit"
            onClick={(e) => {
              e.stopPropagation();
              setEditingCell(cell);
              setIsEditing(true);
              setActiveCellId(cell.id);
            }}
          >
            <Edit3 />
          </ActionButton>
          <ActionButton
            className="approve"
            onClick={(e) => {
              e.stopPropagation();
              handleApprove(cell);
            }}
            disabled={Boolean(cell.approvedBy)}
          >
            <Check />
          </ActionButton>
          <ActionButton
            className="reject"
            onClick={(e) => {
              e.stopPropagation();
              handleReject(cell);
            }}
            disabled={Boolean(cell.rejectedBy)}
          >
            <X />
          </ActionButton>
        </div>
      </DataCell>
    );
  };

  const handleSave = (newValue: any) => {
    console.log("Handle save with newValue:", newValue);
    if (editingCell) {
      updateDatacell({
        variables: {
          datacellId: editingCell.id,
          editedData: { data: newValue },
        },
      })
        .then((response) => {
          const updatedCell = response.data?.editDatacell?.obj;
          if (updatedCell) {
            // Log the updated cell for debugging
            console.log("Updated Cell:", updatedCell);

            // Update the dataCells state
            setDataCells((prevCells) =>
              prevCells.map((cell) =>
                cell.id === updatedCell.id ? { ...cell, ...updatedCell } : cell
              )
            );
            toast.success("Cell updated successfully.");
            console.log("Updated Cell:", updatedCell);
            console.log("Updated dataCells:", dataCells);
          } else {
            toast.error("Failed to update cell.");
          }
        })
        .catch((error) => {
          toast.error("Error updating cell.");
          console.error(error);
        })
        .finally(() => {
          setIsEditing(false);
          setEditingCell(null);
        });
    }
  };

  console.log("Sample datacell:", dataCells[0]);

  return (
    <Container>
      <Dimmer.Dimmable
        as={TableContainer}
        dimmed={tryingApprove || tryingReject}
      >
        <Dimmer active={tryingApprove || tryingReject}>
          <Loader>
            {tryingApprove && "Approving..."}
            {tryingReject && "Rejecting..."}
          </Loader>
        </Dimmer>

        <Table>
          <thead>
            <tr>
              <TableHeader>Column</TableHeader>
              <TableHeader>Data</TableHeader>
            </tr>
          </thead>
          <tbody>
            {columns.map((column: ColumnType) => {
              const cell = lastCells.find(
                (c) => c && c.column && c.column.id === column.id
              );
              return (
                <React.Fragment key={column.id}>
                  <TableRow
                    isHovered={hoveredRow === column.id}
                    onMouseEnter={() => setHoveredRow(column.id)}
                    onMouseLeave={() => setHoveredRow(null)}
                  >
                    <TableCell>
                      <CellContent>
                        <div
                          style={{ display: "flex", flexDirection: "column" }}
                        >
                          <span>{column.name}</span>
                          {cell &&
                            cell.fullSourceList &&
                            cell.fullSourceList.length > 0 && (
                              <AnnotationShield
                                onClick={(e) => {
                                  e.stopPropagation();
                                  toggleAnnotationVisibility(cell.id);
                                }}
                              >
                                {annotationVisibility[cell.id] ? (
                                  <Eye />
                                ) : (
                                  <EyeOff />
                                )}
                                {cell.fullSourceList.length} Annotation
                                {cell.fullSourceList.length !== 1 ? "s" : ""}
                              </AnnotationShield>
                            )}
                        </div>
                        {cell && (
                          <CellStatus>
                            {cell.approvedBy && <Check color="green" />}
                            {cell.rejectedBy && <X color="red" />}
                            {cell.correctedData && <Code color="blue" />}
                          </CellStatus>
                        )}
                      </CellContent>
                    </TableCell>
                    <TableCell>
                      <CellContainer
                        ref={(el) => cell && (cellRefs.current[cell.id] = el!)}
                        style={{ position: "relative" }}
                      >
                        {cell ? renderCellValue(cell) : "-"}
                      </CellContainer>
                    </TableCell>
                  </TableRow>
                  {cell &&
                    cell.fullSourceList &&
                    cell.fullSourceList.length > 0 &&
                    annotationVisibility[cell.id] && (
                      <AnnotationRow>
                        <TableCell colSpan={2}>
                          <AnnotationsContainer>
                            {cell.fullSourceList.map((annotation) => (
                              <HighlightItem
                                key={annotation.id}
                                annotation={convertToServerAnnotation(
                                  annotation
                                )}
                                read_only={true}
                                relations={[]}
                                onSelect={(annotationId: string) => {
                                  onlyDisplayTheseAnnotations([annotation]);
                                  displayAnnotationOnAnnotatorLoad(annotation);
                                  showSelectedAnnotationOnly(false);
                                  showAnnotationBoundingBoxes(true);
                                  showStructuralAnnotations(true);
                                  showAnnotationLabels(
                                    LabelDisplayBehavior.ALWAYS
                                  );
                                }}
                              />
                            ))}
                          </AnnotationsContainer>
                        </TableCell>
                      </AnnotationRow>
                    )}
                </React.Fragment>
              );
            })}
          </tbody>
        </Table>
      </Dimmer.Dimmable>

      {isModalOpen && activeCell && (
        <ModalOverlay onClick={() => setIsModalOpen(false)}>
          <ModalContent onClick={(e) => e.stopPropagation()}>
            <CloseModalButton onClick={() => setIsModalOpen(false)}>
              &times;
            </CloseModalButton>
            <ModalHeader>JSON View</ModalHeader>
            <ReactJson
              src={
                activeCell.correctedData?.data || activeCell.data?.data || {}
              }
              theme="rjv-default"
              style={{ padding: "20px" }}
              enableClipboard={false}
              displayDataTypes={false}
              collapsed={2}
            />
          </ModalContent>
        </ModalOverlay>
      )}

      {isEditing && editingCell && (
        <CellEditor
          value={
            editingCell.correctedData?.data || editingCell.data?.data || ""
          }
          onSave={handleSave}
          onClose={() => {
            setIsEditing(false);
            setEditingCell(null);
          }}
          loading={updatingDatacell}
        />
      )}
    </Container>
  );
};

// Styled Components
const Container = styled.div`
  height: 100%;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.06);
  border: 1px solid rgba(0, 0, 0, 0.08);
  overflow: hidden;
  display: flex;
  flex-direction: column;
`;

const TableContainer = styled.div`
  flex: 1;
  overflow: auto;
  margin: 0;
  background: #fff;
`;

const Table = styled.table`
  width: 100%;
  border-collapse: collapse;
  font-size: 0.9rem;
  color: #1e293b;
  table-layout: fixed;
`;

const TableHeader = styled.th`
  position: sticky;
  top: 0;
  background: #f1f5f9;
  padding: 12px 16px;
  text-align: left;
  font-weight: 600;
  border-bottom: 2px solid #e2e8f0;
  z-index: 1;
  color: #0f172a;

  &:first-child {
    width: 200px;
  }
`;

const TableRow = styled.tr<{ isHovered: boolean }>`
  cursor: default;
  transition: background-color 0.2s ease;
  background-color: ${(props) => (props.isHovered ? "#f8fafc" : "#fff")};

  &:hover {
    background-color: #f1f5f9;
  }

  &:last-child td {
    border-bottom: none;
  }
`;

const TableCell = styled.td`
  padding: 0;
  border-bottom: 1px solid #e2e8f0;
  vertical-align: top;
`;

const CellContent = styled.div`
  display: flex;
  align-items: center;
  padding: 12px 16px;
  gap: 8px;
  min-height: 48px;
`;

interface DataCellProps {
  statusColor?: string;
}

// Update the DataCell styled component
const DataCell = styled(CellContent)<DataCellProps>`
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  justify-content: space-between;
  padding: 12px 16px;
  gap: 8px;
  min-height: 48px;
  background-color: ${(props) => props.statusColor || "transparent"};
  transition: background-color 0.2s ease;
`;

const JsonViewButton = styled.div`
  display: inline-flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  color: #3b82f6;
  font-size: 0.9rem;
  position: relative;
  padding: 4px 8px;
  border-radius: 4px;
  transition: background-color 0.2s ease;

  &:hover {
    background-color: rgba(59, 130, 246, 0.1);
  }

  svg {
    width: 16px;
    height: 16px;
  }
`;

const CellContainer = styled.div`
  position: relative;
  width: 100%;
  min-height: 50px;
  display: flex;
  align-items: center;
  padding: 8px 24px 8px 12px;
  font-size: 0.9rem;
  color: #334155;
  line-height: 1.5;
  background-color: inherit;
`;

const AnnotationRow = styled.tr`
  background-color: #f9fafb;
`;

const AnnotationsContainer = styled.div`
  padding: 8px 16px;
  background-color: #f9fafb;
`;

const CellStatus = styled.div`
  display: flex;
  align-items: center;
  gap: 4px;
`;

const ButtonContainer = styled.div`
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 12px;
  background: rgba(255, 255, 255, 0.99);
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(0, 0, 0, 0.04);
  z-index: 2000; // Ensure the button container is above other elements

  .buttons {
    display: flex;
    gap: 8px;
  }

  .status-message {
    font-size: 0.75rem;
    color: #64748b;
    text-align: center;
    margin-top: 4px;
    font-weight: 500;
  }

  .ui.button {
    margin: 0;
    transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
    border-radius: 8px;
    min-width: 32px;
    height: 32px;
    display: flex;
    align-items: center;
    justify-content: center;
    border: none;

    &:hover:not(:disabled) {
      transform: translateY(-2px);
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
    }

    &:active:not(:disabled) {
      transform: translateY(0);
    }

    &.green {
      background: linear-gradient(135deg, #22c55e, #16a34a);

      &:hover:not(:disabled) {
        background: linear-gradient(135deg, #16a34a, #15803d);
      }
    }

    &.red {
      background: linear-gradient(135deg, #ef4444, #dc2626);

      &:hover:not(:disabled) {
        background: linear-gradient(135deg, #dc2626, #b91c1c);
      }
    }
  }
`;

const ModalOverlay = styled.div`
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background-color: rgba(0, 0, 0, 0.5);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 1000;
`;

const ModalContent = styled.div`
  background-color: #fff;
  width: 80%;
  max-width: 600px;
  padding: 20px;
  border-radius: 8px;
  position: relative;
`;

const CloseModalButton = styled.button`
  position: absolute;
  top: 12px;
  right: 12px;
  background: none;
  border: none;
  font-size: 1.5rem;
  cursor: pointer;
`;

// Styled Button Component
const StyledButton = styled.button<{ color?: string; hoverColor?: string }>`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background-color: ${({ color }) => color || "#e5e7eb"};
  color: #fff;
  border: none;
  border-radius: 4px;
  padding: 6px 8px;
  cursor: pointer;
  font-size: 0.9rem;
  transition: background-color 0.2s ease;
  margin-right: 8px;

  &:hover {
    background-color: ${({ hoverColor }) => hoverColor || "#d1d5db"};
  }

  &:disabled {
    background-color: #e5e7eb;
    cursor: not-allowed;
    opacity: 0.6;
  }

  svg {
    margin-right: 4px;
  }
`;

// Annotation Shield Button
const AnnotationShield = styled.button`
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 16px;
  padding: 4px 8px;
  font-size: 0.75rem;
  color: #64748b;
  cursor: pointer;
  transition: all 0.2s ease;
  margin-top: 4px;

  &:hover {
    background: #f1f5f9;
    color: #475569;
  }

  svg {
    width: 14px;
    height: 14px;
  }
`;

const ActionButtonsWrapper = styled.div`
  position: absolute;
  top: -10px;
  right: 30px;
  z-index: 100;
  background: white;
  border: 1px solid #e5e7eb;
  border-radius: 4px;
  padding: 8px;
  box-shadow: 0px 2px 4px rgba(0, 0, 0, 0.1);
`;

const ModalHeader = styled.h2`
  color: black;
`;

// Styled component for Edit Icon
const EditIcon = styled.button`
  position: absolute;
  top: 8px;
  left: 20px;
  background: none;
  border: none;
  color: #3b82f6;
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
  transition: background-color 0.2s ease;

  &:hover {
    background-color: rgba(59, 130, 246, 0.1);
  }

  svg {
    width: 16px;
    height: 16px;
  }
`;

const ActionButton = styled.button`
  background: none;
  border: none;
  cursor: pointer;
  padding: 6px;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #64748b;
  transition: all 0.2s ease;
  margin-right: 4px;

  &:hover:not(:disabled) {
    background-color: #fff;
    color: #3b82f6;
  }

  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  &.approve:hover:not(:disabled) {
    color: #22c55e;
  }

  &.reject:hover:not(:disabled) {
    color: #ef4444;
  }

  &.edit:hover:not(:disabled) {
    color: #3b82f6;
  }

  svg {
    width: 16px;
    height: 16px;
  }
`;
