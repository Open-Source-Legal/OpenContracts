import React, { useState, useEffect, useRef } from "react";
import _ from "lodash";
import styled from "styled-components";

import { Pencil, Trash2 } from "lucide-react";

import { VerticallyJustifiedEndDiv } from "../../sidebar/common";

import { annotationSelectedViaRelationship } from "../../utils";

import { PermissionTypes } from "../../../types";
import { SelectionBoundary } from "./SelectionBoundary";
import {
  LabelTagContainer,
  SelectionInfo,
  SelectionInfoContainer,
} from "./Containers";
import { getContrastColor } from "../../../../utils/transform";
import RadialButtonCloud, {
  CloudButtonItem,
} from "../../../widgets/buttons/RadialButtonCloud";
import { SelectionTokenGroup } from "./SelectionTokenGroup";
import { EditLabelModal } from "../../components/modals/EditLabelModal";
import { useReactiveVar } from "@apollo/client";
import { authToken } from "../../../../graphql/cache";
import { PDFPageInfo } from "../../types/pdf";
import { ServerTokenAnnotation } from "../../types/annotations";
import {
  useApproveAnnotation,
  useDeleteAnnotation,
  usePdfAnnotations,
  useRejectAnnotation,
} from "../../hooks/AnnotationHooks";
import {
  useAnnotationDisplay,
  useAnnotationSelection,
} from "../../context/UISettingsAtom";

interface SelectionProps {
  selected: boolean;
  pageInfo: PDFPageInfo;
  annotation: ServerTokenAnnotation;
  showInfo?: boolean;
  children?: React.ReactNode;
  approved?: boolean;
  rejected?: boolean;
  actions?: CloudButtonItem[];
  allowFeedback?: boolean;
  scrollIntoView?: boolean;
}

const RelationshipIndicator = styled.div<{ $type: string; $color: string }>`
  position: absolute;
  left: -24px;
  top: 50%;
  transform: translateY(-50%);
  display: flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: ${
    (props) =>
      props.$type === "SOURCE"
        ? "rgba(25, 118, 210, 0.95)" // Blue for source
        : "rgba(230, 74, 25, 0.95)" // Orange-red for target
  };
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
  cursor: help;
  z-index: 1; // Ensure it's above other elements

  /* Create tooltip */
  &::before {
    content: "${(props) => props.$type}";
    position: absolute;
    left: -8px;
    transform: translateX(-100%);
    background: rgba(0, 0, 0, 0.8);
    color: white;
    padding: 2px 6px;
    border-radius: 3px;
    font-size: 0.75rem;
    white-space: nowrap;
    opacity: 0;
    pointer-events: none; // Prevent tooltip from interfering with hover
    transition: opacity 0.2s ease;
  }

  &::after {
    content: "";
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: white;
    animation: ${(props) =>
      props.$type === "SOURCE"
        ? "sourcePulse 2s infinite"
        : "targetPulse 2s infinite"};
    pointer-events: none;
  }

  /* Show tooltip on hover */
  &:hover::before {
    opacity: 1;
  }
`;

export const Selection: React.FC<SelectionProps> = ({
  selected,
  pageInfo,
  annotation,
  children,
  approved,
  rejected,
  allowFeedback,
  scrollIntoView = false,
  showInfo = true,
}) => {
  const auth_token = useReactiveVar(authToken);
  const [hovered, setHovered] = useState(false);
  const [isEditLabelModalVisible, setIsEditLabelModalVisible] = useState(false);
  const [cloudVisible, setCloudVisible] = useState(false);
  const [hidden, setHidden] = useState(false);
  const cloudRef = useRef<HTMLDivElement | null>(null);

  const { showBoundingBoxes, showSelectedOnly, showLabels } =
    useAnnotationDisplay();
  const { hideLabels } = useAnnotationDisplay();
  const { pdfAnnotations } = usePdfAnnotations();
  const { selectedAnnotations, setSelectedAnnotations, selectedRelations } =
    useAnnotationSelection();
  const approveAnnotation = useApproveAnnotation();
  const rejectAnnotation = useRejectAnnotation();
  const deleteAnnotation = useDeleteAnnotation();

  useEffect(() => {
    setHidden(showSelectedOnly && !selected);
  }, [showSelectedOnly, selected]);

  const label = annotation.annotationLabel;
  const color = label?.color || "#616a6b"; // grey as the default

  let actions: CloudButtonItem[] = [];

  if (auth_token) {
    if (allowFeedback) {
      if (!approved) {
        actions.push({
          name: "thumbs up",
          color: "green",
          tooltip: "Upvote Annotation",
          onClick: () => {
            approveAnnotation(annotation.id);
          },
        });
      }
      if (!rejected) {
        actions.push({
          name: "thumbs down",
          color: "red",
          tooltip: "Downvote Annotation",
          onClick: () => {
            rejectAnnotation(annotation.id);
          },
        });
      }
    }
  } else {
    actions.push({
      name: "question",
      color: "blue",
      tooltip: "Login to see available actions!",
      onClick: () => {
        window.alert("Login to leave feedback and see other actions!");
      },
    });
  }

  if (
    annotation.myPermissions.includes(PermissionTypes.CAN_REMOVE) &&
    !annotation.annotationLabel.readonly
  ) {
    actions.push({
      name: "trash alternate outline",
      color: "red",
      tooltip: "Delete Annotation",
      onClick: () => {
        console.log("Delete clicked");
      },
      protected_message: "Are you sure you want to delete this annotation?",
    });
  }

  if (
    annotation.myPermissions.includes(PermissionTypes.CAN_UPDATE) &&
    !annotation.annotationLabel.readonly
  ) {
    actions.push({
      name: "pencil",
      color: "blue",
      tooltip: "Edit Annotation",
      onClick: () => {
        console.log("Edit clicked");
      },
    });
  }

  const bounds = pageInfo.getScaledBounds(
    annotation.json[pageInfo.page.pageNumber - 1].bounds
  );

  const removeAnnotation = () => {
    deleteAnnotation(annotation.id);
  };

  const onShiftClick = () => {
    const current = selectedAnnotations.slice(0);
    if (current.some((other) => other === annotation.id)) {
      const next = current.filter((other) => other !== annotation.id);
      setSelectedAnnotations(next);
    } else {
      current.push(annotation.id);
      setSelectedAnnotations(current);
    }
  };

  const handleClickOutside = (event: Event): void => {
    if (
      cloudRef.current &&
      !cloudRef.current.contains(event.target as Node) &&
      !(event.target as Element).closest(".pulsing-dot")
    ) {
      setCloudVisible(false);
    }
  };

  useEffect(() => {
    if (cloudVisible) {
      document.addEventListener("mousedown", handleClickOutside);
      document.addEventListener("touchstart", handleClickOutside);
    } else {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("touchstart", handleClickOutside);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("touchstart", handleClickOutside);
    };
  }, [cloudVisible]);

  let relationship_type = "";
  if (selected && selectedRelations.length > 0) {
    relationship_type = annotationSelectedViaRelationship(
      annotation,
      pdfAnnotations.annotations,
      selectedRelations[0]
    );
  }

  const handleMouseEnter = () => {
    setHovered(true);
  };

  const handleMouseLeave = () => {
    setHovered(false);
  };

  return (
    <>
      <SelectionBoundary
        id={annotation.id}
        hidden={hidden}
        showBoundingBox={showBoundingBoxes}
        color={color}
        bounds={bounds}
        onHover={setHovered}
        onClick={onShiftClick}
        approved={approved}
        rejected={rejected}
        selected={selected}
        scrollIntoView={scrollIntoView}
      >
        {showInfo && !hideLabels && (
          <SelectionInfo
            id="SelectionInfo"
            $bounds={bounds}
            className={`selection_${annotation.id}`}
            $color={color}
            $showBoundingBox={showBoundingBoxes}
            $approved={approved}
            $rejected={rejected}
            onMouseEnter={handleMouseEnter}
            onMouseLeave={handleMouseLeave}
          >
            <SelectionInfoContainer id="SelectionInfoContainer">
              {relationship_type && (
                <RelationshipIndicator
                  $type={relationship_type}
                  $color={color}
                />
              )}
              <VerticallyJustifiedEndDiv>
                <LabelTagContainer
                  $hidden={hidden}
                  $hovered={hovered}
                  $color={color}
                  $display_behavior={showLabels}
                >
                  <div
                    style={{
                      position: "relative",
                      display: "flex",
                      alignItems: "center",
                    }}
                  >
                    <RadialButtonCloud
                      parentBackgroundColor={color}
                      actions={actions}
                    />
                    <div
                      style={{
                        whiteSpace: "nowrap",
                        overflowX: "visible",
                        marginLeft: "8px",
                      }}
                    >
                      <span>{label.text}</span>
                    </div>
                    {annotation.myPermissions.includes(
                      PermissionTypes.CAN_UPDATE
                    ) &&
                      !annotation.annotationLabel.readonly && (
                        <Pencil
                          size={14}
                          style={{
                            marginLeft: ".25rem",
                            marginRight: ".125rem",
                            cursor: "pointer",
                          }}
                          onClick={(e: React.MouseEvent) => {
                            e.stopPropagation();
                            setIsEditLabelModalVisible(true);
                          }}
                          onMouseDown={(e: React.MouseEvent) => {
                            e.stopPropagation();
                          }}
                        />
                      )}
                    {annotation.myPermissions.includes(
                      PermissionTypes.CAN_REMOVE
                    ) &&
                      !annotation.annotationLabel.readonly && (
                        <Trash2
                          size={14}
                          style={{
                            marginLeft: ".125rem",
                            marginRight: ".25rem",
                            cursor: "pointer",
                          }}
                          onClick={(e: React.MouseEvent) => {
                            e.stopPropagation();
                            removeAnnotation();
                          }}
                          // We have to prevent the default behaviour for
                          // the pdf canvas here, in order to be able to capture
                          // the click event.
                          onMouseDown={(e: React.MouseEvent) => {
                            e.stopPropagation();
                          }}
                        />
                      )}
                  </div>
                </LabelTagContainer>
              </VerticallyJustifiedEndDiv>
            </SelectionInfoContainer>
          </SelectionInfo>
        )}
        <div
          style={{
            width: "100%",
            height: "0px",
            position: "relative",
            top: "0",
            left: "0",
          }}
        >
          {children}
        </div>
      </SelectionBoundary>
      {
        // NOTE: It's important that the parent element of the tokens
        // is the PDF canvas, because we need their absolute position
        // to be relative to that and not another absolute/relatively
        // positioned element. This is why SelectionTokens are not inside
        // SelectionBoundary.
        annotation.json[pageInfo.page.pageNumber - 1].tokensJsons && (
          <SelectionTokenGroup
            id={`SELECTION_TOKEN_${annotation.id}`}
            color={annotation.annotationLabel.color}
            highOpacity={!showBoundingBoxes}
            hidden={hidden}
            pageInfo={pageInfo}
            tokens={annotation.json[pageInfo.page.pageNumber - 1].tokensJsons}
          />
        )
      }
      {isEditLabelModalVisible && (
        <EditLabelModal
          annotation={annotation}
          visible={isEditLabelModalVisible}
          onHide={() => setIsEditLabelModalVisible(false)}
        />
      )}
    </>
  );
};
