import React, { useState, useEffect, useRef } from "react";
import { Button, Popup, Icon, Modal } from "semantic-ui-react";
import { CellStatus } from "../../../types/extract-grid";
import styled from "styled-components";
import { JSONSchema7 } from "json-schema";
import { ExtractCellEditor } from "./ExtractCellEditor";
import ReactJson from "react-json-view";
import { TruncatedText } from "../../widgets/data-display/TruncatedText";
import { useReactiveVar } from "@apollo/client";
import {
  displayAnnotationOnAnnotatorLoad,
  onlyDisplayTheseAnnotations,
  selectedExtract,
  showAnnotationBoundingBoxes,
  showAnnotationLabels,
  showSelectedAnnotationOnly,
  showStructuralAnnotations,
} from "../../../graphql/cache";
import {
  DatacellType,
  ExtractType,
  ServerAnnotationType,
  LabelDisplayBehavior,
} from "../../../types/graphql-api";
import { useNavigate } from "react-router-dom";

const StatusDot = styled.div<{ statusColor: string }>`
  width: 12px;
  height: 12px;
  background-color: ${(props) => props.statusColor};
  border-radius: 50%;
  cursor: pointer;
  position: absolute;
  top: 8px;
  right: 8px;
  transition: all 0.2s ease;
  box-shadow: ${(props) => {
    switch (props.statusColor) {
      case "#10b981":
        return "0 0 0 3px rgba(16, 185, 129, 0.15)";
      case "#ef4444":
        return "0 0 0 3px rgba(239, 68, 68, 0.15)";
      case "#f59e0b":
        return "0 0 0 3px rgba(245, 158, 11, 0.15)";
      default:
        return "0 0 0 3px rgba(148, 163, 184, 0.15)";
    }
  }};

  &:hover {
    transform: scale(1.2);
    box-shadow: ${(props) => {
      switch (props.statusColor) {
        case "#10b981":
          return "0 0 0 4px rgba(16, 185, 129, 0.25)";
        case "#ef4444":
          return "0 0 0 4px rgba(239, 68, 68, 0.25)";
        case "#f59e0b":
          return "0 0 0 4px rgba(245, 158, 11, 0.25)";
        default:
          return "0 0 0 4px rgba(148, 163, 184, 0.25)";
      }
    }};
  }
`;

const ButtonContainer = styled.div`
  padding: 8px;

  .buttons {
    display: flex;
    gap: 8px;

    button {
      border-radius: 8px !important;
      transition: all 0.15s ease !important;

      &:hover:not(:disabled) {
        transform: translateY(-1px);
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
      }
    }
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

    &:disabled {
      opacity: 0.5;
      cursor: not-allowed;
      filter: grayscale(40%);
    }

    i.icon {
      margin: 0 !important;
      font-size: 0.9em;
    }
  }
`;

const CellContainer = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.75rem;
  height: 100%;
  min-height: 45px;
  position: relative;
  transition: background-color 0.15s ease;

  .cell-loader {
    position: absolute;
    top: 2px;
    right: 2px;
    font-size: 10px;
    color: #64748b;
    font-style: italic;
  }

  &:hover {
    background-color: rgba(59, 130, 246, 0.05);
  }
`;

interface ExtractCellFormatterProps {
  value: any;
  cellStatus: CellStatus | null;
  cellId: string;
  onApprove: () => void;
  onReject: () => void;
  onEdit: (cellId: string, editedData: any) => void;
  readOnly: boolean;
  isExtractComplete: boolean;
  schema: JSONSchema7;
  extractIsList: boolean;
  row: any;
  column: any;
  cell?: DatacellType;
  extract?: ExtractType;
}

/**
 * ExtractCellFormatter component displays the content of a cell in the extract data grid.
 * It handles displaying the value, editing, approving, and rejecting the cell.
 * If the cell has correctedData, it displays that instead of the original data.
 * It also provides a control to view the original value when correctedData is present.
 */
export const ExtractCellFormatter: React.FC<ExtractCellFormatterProps> = ({
  value,
  cellStatus,
  cellId,
  onApprove,
  onReject,
  onEdit,
  readOnly,
  isExtractComplete,
  schema,
  extractIsList,
  row,
  column,
  cell,
  extract,
}) => {
  const [isPopupOpen, setIsPopupOpen] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isOriginalModalOpen, setIsOriginalModalOpen] = useState(false);

  const [viewSourceAnnotations, setViewSourceAnnotations] = useState<
    ServerAnnotationType[] | null
  >(null);

  const only_display_these_annotations = useReactiveVar(
    onlyDisplayTheseAnnotations
  );

  const cellRef = useRef<HTMLDivElement>(null);
  const [cellWidth, setCellWidth] = useState<number>(0);

  const navigate = useNavigate();

  useEffect(() => {
    if (cellRef.current) {
      const computedStyle = getComputedStyle(cellRef.current);
      const padding =
        parseFloat(computedStyle.paddingLeft) +
        parseFloat(computedStyle.paddingRight);
      setCellWidth(cellRef.current.offsetWidth - padding);
    }
  }, [cellRef]);

  const statusColor = () => {
    if (cellStatus?.isApproved) return "#10b981"; // Modern green
    if (cellStatus?.isRejected) return "#ef4444"; // Modern red
    if (cellStatus?.isEdited) return "#f59e0b"; // Modern amber
    return "#94a3b8"; // Modern gray
  };

  const getCellBackground = () => {
    if (cellStatus?.isLoading) return "rgba(59, 130, 246, 0.05)"; // Light blue
    if (cellStatus?.isApproved) return "rgba(16, 185, 129, 0.05)"; // Light green
    if (cellStatus?.isRejected) return "rgba(239, 68, 68, 0.05)"; // Light red
    if (cellStatus?.isEdited) return "rgba(245, 158, 11, 0.05)"; // Light amber
    return "transparent";
  };

  const openViewer = () => {
    setIsModalOpen(true);
  };

  const closeModal = () => {
    setIsModalOpen(false);
  };

  const openOriginalViewer = () => {
    setIsOriginalModalOpen(true);
  };

  const closeOriginalModal = () => {
    setIsOriginalModalOpen(false);
  };

  const handleJsonEdit = (edit: any) => {
    const updatedValue = edit.updated_src;
    onEdit(cellId, updatedValue);
  };

  const displayedValue =
    cellStatus?.correctedData != null ? cellStatus.correctedData : value;

  const displayValue = () => {
    if (typeof displayedValue === "object" && displayedValue !== null) {
      return (
        <div
          onClick={openViewer}
          style={{
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
          }}
        >
          <Icon name="code" />
          <span style={{ marginLeft: "5px" }}>View/Edit JSON</span>
        </div>
      );
    } else {
      return <TruncatedText text={String(displayedValue)} limit={cellWidth} />;
    }
  };

  useEffect(() => {
    if (viewSourceAnnotations !== null) {
      onlyDisplayTheseAnnotations(viewSourceAnnotations);
      displayAnnotationOnAnnotatorLoad(viewSourceAnnotations[0]);
      showSelectedAnnotationOnly(false);
      showAnnotationBoundingBoxes(true);
      showStructuralAnnotations(true);
      showAnnotationLabels(LabelDisplayBehavior.ALWAYS);
    }
  }, [viewSourceAnnotations]);

  useEffect(() => {
    if (
      only_display_these_annotations &&
      only_display_these_annotations.length > 0
    ) {
      const first = only_display_these_annotations[0];
      if (first.document && first.corpus) {
        navigate(
          `/corpus/${first.corpus.id}/document/${first.document.id}?ann=${first.id}`
        );
      }
      setViewSourceAnnotations(null);
    }
  }, [only_display_these_annotations, navigate]);

  return (
    <CellContainer ref={cellRef} style={{ background: getCellBackground() }}>
      {displayValue()}
      {cellStatus?.isLoading && <div className="cell-loader">Loading...</div>}
      {!cellStatus?.isLoading && isExtractComplete && (
        <>
          <Popup
            trigger={<StatusDot statusColor={statusColor()} />}
            on="click"
            position="top right"
            open={isPopupOpen}
            onOpen={() => setIsPopupOpen(true)}
            onClose={() => setIsPopupOpen(false)}
            mouseLeaveDelay={300}
            content={
              <ButtonContainer>
                <div className="buttons">
                  <Button
                    icon="check"
                    color="green"
                    size="tiny"
                    onClick={() => {
                      onApprove();
                      setIsPopupOpen(false);
                    }}
                    disabled={
                      cellStatus?.isApproved || readOnly || !isExtractComplete
                    }
                    title="Approve"
                  />
                  <Button
                    icon="edit"
                    color="grey"
                    size="tiny"
                    onClick={() => {
                      if (
                        typeof displayedValue === "object" &&
                        displayedValue !== null
                      ) {
                        openViewer();
                      } else {
                        setIsEditing(true);
                      }
                      setIsPopupOpen(false);
                    }}
                    disabled={readOnly || !isExtractComplete}
                    title="Edit"
                  />
                  <Button
                    icon="eye"
                    color="blue"
                    size="tiny"
                    onClick={() => {
                      if (
                        cell?.fullSourceList &&
                        cell.fullSourceList.length > 0
                      ) {
                        selectedExtract(extract);
                        setViewSourceAnnotations(
                          cell.fullSourceList as ServerAnnotationType[]
                        );
                      }
                      setIsPopupOpen(false);
                    }}
                    disabled={
                      !cell?.fullSourceList || cell.fullSourceList.length === 0
                    }
                    title="View Sources"
                  />
                  <Button
                    icon="close"
                    color="red"
                    size="tiny"
                    onClick={() => {
                      onReject();
                      setIsPopupOpen(false);
                    }}
                    disabled={
                      cellStatus?.isRejected || readOnly || !isExtractComplete
                    }
                    title="Reject"
                  />
                </div>
                {cellStatus?.isApproved && (
                  <div className="status-message">
                    Cell is currently approved
                  </div>
                )}
                {cellStatus?.isRejected && (
                  <div className="status-message">
                    Cell is currently rejected
                  </div>
                )}
                {cellStatus?.isEdited && !cellStatus?.isApproved && (
                  <div className="status-message">Cell has been edited</div>
                )}
              </ButtonContainer>
            }
          />
          {isEditing && (
            <Modal
              open={isEditing}
              onClose={() => setIsEditing(false)}
              size="small"
            >
              <Modal.Header>Edit {column.name}</Modal.Header>
              <Modal.Content>
                <ExtractCellEditor
                  row={row}
                  column={column}
                  onRowChange={(updatedRow: any, commitChanges?: boolean) => {
                    if (commitChanges) {
                      onEdit(cellId, updatedRow[column.key]);
                    }
                  }}
                  onClose={() => setIsEditing(false)}
                  schema={schema}
                  extractIsList={extractIsList}
                />
              </Modal.Content>
            </Modal>
          )}
          <Modal open={isModalOpen} onClose={closeModal} size="large">
            <Modal.Header>Edit JSON Data</Modal.Header>
            <Modal.Content>
              <ReactJson
                src={displayedValue}
                onEdit={handleJsonEdit}
                onAdd={handleJsonEdit}
                onDelete={handleJsonEdit}
                theme="rjv-default"
                style={{ padding: "20px" }}
                enableClipboard={false}
                displayDataTypes={false}
              />
            </Modal.Content>
            <Modal.Actions>
              <Button onClick={closeModal}>Close</Button>
            </Modal.Actions>
          </Modal>
          <Modal
            open={isOriginalModalOpen}
            onClose={closeOriginalModal}
            size="large"
          >
            <Modal.Header>Original Value</Modal.Header>
            <Modal.Content>
              {typeof value === "object" && value !== null ? (
                <ReactJson
                  src={value}
                  theme="rjv-default"
                  style={{ padding: "20px" }}
                  enableClipboard={false}
                  displayDataTypes={false}
                />
              ) : (
                <div style={{ padding: "20px" }}>{String(value)}</div>
              )}
            </Modal.Content>
            <Modal.Actions>
              <Button onClick={closeOriginalModal}>Close</Button>
            </Modal.Actions>
          </Modal>
        </>
      )}
    </CellContainer>
  );
};
