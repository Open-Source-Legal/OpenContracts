import React, { useState, useEffect } from "react";
import { Table, Popup, Modal, Button } from "semantic-ui-react";
import { Spinner } from "@os-legal/ui";
import { MoreVertical, Eye, ThumbsDown, ThumbsUp, Pencil } from "lucide-react";
import { useNavigate, useLocation } from "react-router-dom";
import {
  getDocumentUrl,
  updateAnnotationDisplayParams,
} from "../../../utils/navigationUtils";

import {
  DatacellType,
  LabelDisplayBehavior,
  ServerAnnotationType,
} from "../../../types/graphql-api";
import { JSONTree } from "react-json-tree";
import {
  onlyDisplayTheseAnnotations,
  selectedExtract,
  showAnnotationBoundingBoxes,
  showAnnotationLabels,
  showSelectedAnnotationOnly,
  showStructuralAnnotations,
} from "../../../graphql/cache";
import _ from "lodash";
import { useReactiveVar } from "@apollo/client";

interface ExtractDatacellProps {
  cellData: DatacellType;
  readOnly?: boolean;
  onApprove?: (id: string) => void;
  onReject?: (id: string) => void;
  onEdit?: (id: string, new_data: Record<any, any>) => void;
}

/**
 * ExtractDatacell Component
 *
 * This component is designed to display and interact with a single data cell in a table.
 * It uses Semantic UI React components for styling and layout.
 *
 * Features:
 * - Displays JSON data in a preview format, showing the first three lines with the ability to view the full content on hover.
 * - Includes a popup menu with three actions: thumbs up (approve), thumbs down (reject), and edit.
 * - Thumbs up button calls the onApprove handler with the cell's ID.
 * - Thumbs down button calls the onReject handler with the cell's ID.
 * - Edit button opens a modal allowing the user to edit the JSON data.
 * - The modal uses react-json-tree for an interactive JSON editing experience.
 * - The edit data is initialized with `correctedData` if available, otherwise with `data`.
 * - The component updates its state to reflect changes in the provided extract data.
 * - Upon saving changes in the modal, the onEdit handler is called with the new data.
 *
 * Props:
 * - cellData: The data cell object containing the data to be displayed and edited.
 * - readOnly: A flag indicating whether the cell is in view-only mode (disables actions).
 * - onApprove: Callback function to handle approval action.
 * - onReject: Callback function to handle rejection action.
 * - onEdit: Callback function to handle editing action.
 *
 * @param {ExtractDatacellProps} props - The properties object.
 * @returns {JSX.Element} The rendered component.
 */

export const ExtractDatacell = ({
  cellData,
  readOnly,
  onApprove,
  onReject,
  onEdit,
}: ExtractDatacellProps): JSX.Element => {
  const [color, setColor] = useState<string>("gray");
  const [modalOpen, setModalOpen] = useState(false);
  const [editData, setEditData] = useState<Record<string, any> | null>(null);
  const [viewSourceAnnotations, setViewSourceAnnotations] = useState<
    ServerAnnotationType[] | null
  >(null);
  const only_display_these_annotations = useReactiveVar(
    onlyDisplayTheseAnnotations
  );

  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    // console.log("DataCell - viewSourceAnnotations", viewSourceAnnotations);
    if (viewSourceAnnotations !== null) {
      onlyDisplayTheseAnnotations(viewSourceAnnotations);
      // Want to make sure that we see all annotatations *clearly*
      // Update display settings via URL - CentralRouteManager will set reactive vars
      updateAnnotationDisplayParams(location, navigate, {
        showSelectedOnly: false,
        showBoundingBoxes: true,
        showStructural: true,
        labelDisplay: LabelDisplayBehavior.ALWAYS,
      });
    }
  }, [viewSourceAnnotations, location, navigate]);

  useEffect(() => {
    console.log(
      "DataCell - display_annotation_on_annotator_load:",
      only_display_these_annotations
    );
    if (only_display_these_annotations) {
      const first = only_display_these_annotations[0]; // All sources share same doc & corpus
      if (first.document && first.corpus) {
        const url = getDocumentUrl(first.document, first.corpus);
        if (url !== "#") {
          navigate(`${url}?ann=${first.id}`);
        } else {
          console.warn("Cannot navigate - missing slugs:", first);
        }
      }
      setViewSourceAnnotations(null);
    }
  }, [only_display_these_annotations, navigate]);

  useEffect(() => {
    setEditData(cellData.correctedData ?? cellData.data ?? {});
  }, [cellData]);

  const handleCancel = () => {
    setEditData(null);
    setModalOpen(false);
  };

  useEffect(() => {
    let calculated_color = "light gray";
    if (cellData.failed) {
      calculated_color = "red";
    } else if (cellData.started && cellData.completed) {
      if (
        cellData.correctedData !== "{}" &&
        !_.isEmpty(cellData.correctedData)
      ) {
        calculated_color = "yellow";
      } else if (cellData.rejectedBy) {
        calculated_color = "red";
      } else if (cellData.approvedBy) {
        calculated_color = "green";
      }
    }
    setColor(calculated_color);
  }, [cellData]);

  const renderJsonPreview = (data: Record<string, any>) => {
    // Handle empty or invalid data
    if (!data || !data.data || Object.keys(data.data).length === 0) {
      return (
        <Popup
          trigger={<span>-</span>}
          content={<pre>{"{}"}</pre>}
          wide="very"
        />
      );
    }

    try {
      const jsonString = JSON.stringify(data.data, null, 2);
      const previewLines = jsonString.split("\n").slice(0, 3);
      const preview =
        previewLines.join("\n") +
        (jsonString.split("\n").length > 3 ? "\n..." : "");

      return (
        <Popup
          trigger={<span>{preview || "-"}</span>}
          content={<pre>{jsonString}</pre>}
          wide="very"
        />
      );
    } catch (e) {
      return (
        <Popup
          trigger={<span>-</span>}
          content={<pre>{"{}"}</pre>}
          wide="very"
        />
      );
    }
  };

  return (
    <>
      <Table.Cell key={cellData.id} style={{ backgroundColor: color }}>
        {cellData.started && !cellData.completed && !cellData.failed ? (
          <Spinner />
        ) : (
          <div style={{ position: "relative" }}>
            {renderJsonPreview(
              cellData?.data ? { data: cellData.data || {} } : { data: {} }
            )}
            {!readOnly && (
              <div style={{ position: "absolute", top: "5px", right: "5px" }}>
                <Popup
                  trigger={
                    <MoreVertical size={16} style={{ cursor: "pointer" }} />
                  }
                  content={
                    <Button.Group vertical>
                      <Button
                        primary
                        onClick={
                          cellData?.fullSourceList &&
                          cellData.fullSourceList !== undefined
                            ? () => {
                                selectedExtract(cellData.extract);
                                setViewSourceAnnotations(
                                  cellData.fullSourceList as ServerAnnotationType[]
                                );
                              }
                            : () => {}
                        }
                      >
                        <Eye size={14} />
                      </Button>
                      <Button
                        color="red"
                        onClick={() => onReject && onReject(cellData.id)}
                      >
                        <ThumbsDown size={14} />
                      </Button>
                      <Button
                        color="green"
                        onClick={() => onApprove && onApprove(cellData.id)}
                      >
                        <ThumbsUp size={14} />
                      </Button>
                      <Button color="grey" onClick={() => setModalOpen(true)}>
                        <Pencil size={14} />
                      </Button>
                    </Button.Group>
                  }
                  on="click"
                  position="top right"
                />
              </div>
            )}
          </div>
        )}
      </Table.Cell>
      <Modal open={modalOpen} onClose={handleCancel}>
        <Modal.Header>Edit Data</Modal.Header>
        <Modal.Content>
          {/**TODO - get data editor setup here*/}
          <JSONTree data={editData} hideRoot />
        </Modal.Content>
        <Modal.Actions>
          <Button onClick={handleCancel}>Cancel</Button>
          <Button
            disabled={Boolean(editData)}
            primary
            onClick={
              onEdit && editData
                ? () => onEdit(cellData.id, editData)
                : () => {}
            }
          >
            Save
          </Button>
        </Modal.Actions>
      </Modal>
    </>
  );
};
