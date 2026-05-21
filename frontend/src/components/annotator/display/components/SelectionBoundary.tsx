import React, { useEffect, useRef } from "react";
import styled, { css } from "styled-components";
import { BoundingBox } from "../../../types";
import { hexToRgb } from "../../../../utils/transform";
import { computeAnnotationBoxShadow } from "../../../../utils/colorUtils";
import {
  APPROVED_RGB,
  REJECTED_RGB,
  ANNOTATION_BOUNDARY_RADIUS,
  BOUNDARY_OPACITY_SELECTED,
  BOUNDARY_OPACITY_UNSELECTED,
} from "../../../../assets/configurations/constants";
import { pulseGreen, pulseMaroon } from "../effects";
import { useAnnotationRefs } from "../../hooks/useAnnotationRefs";
import { useAtomValue } from "jotai";
import { isCreatingAnnotationAtom } from "../../context/UISettingsAtom";

interface SelectionBoundaryProps {
  id: string;
  hidden: boolean;
  showBoundingBox?: boolean;
  scrollIntoView?: boolean;
  color: string;
  bounds: BoundingBox;
  selected: boolean;
  children?: React.ReactNode;
  annotationId?: string;
  onHover?: (hovered: boolean) => void;
  onClick?: (event?: React.MouseEvent) => void;
  /**
   * When true, plain (non-shift) clicks also invoke ``onClick``. Used for
   * hyperlink-style annotations (OC_URL) where a single click should open
   * the link.  When false (default) the shift-click-to-select semantic is
   * preserved, so plain clicks fall through to canvas handlers and don't
   * interfere with creating a new annotation underneath.
   */
  clickThroughOnPlainClick?: boolean;
  approved?: boolean;
  rejected?: boolean;
}

const BoundarySpan = styled.span.attrs<{
  $width: number;
  $height: number;
  $rotateX: number;
  $rotateY: number;
  $bounds: BoundingBox;
  $backgroundColor: string;
  $boxShadow: string;
  $color: string;
  $hidden: boolean;
  $approved?: boolean;
  $rejected?: boolean;
}>((props) => ({
  style: {
    position: "absolute",
    left: `${props.$bounds.left}px`,
    top: `${props.$bounds.top}px`,
    width: `${Math.abs(props.$width)}px`,
    height: `${Math.abs(props.$height)}px`,
    transform: `rotateY(${props.$rotateY}deg) rotateX(${props.$rotateX}deg)`,
    backgroundColor: props.$backgroundColor,
    zIndex: 2,
    border: "none",
    boxShadow: props.$boxShadow,
    transformOrigin: "top left",
    transition:
      "background-color 0.4s ease, box-shadow 0.4s ease, opacity 0.4s ease",
  },
}))`
  border-radius: ${ANNOTATION_BOUNDARY_RADIUS};

  ${(props) =>
    props.$approved &&
    css`
      box-shadow: 0 0 12px 3px
          rgba(${APPROVED_RGB.r}, ${APPROVED_RGB.g}, ${APPROVED_RGB.b}, 0.18),
        0 0 4px 1px
          rgba(${APPROVED_RGB.r}, ${APPROVED_RGB.g}, ${APPROVED_RGB.b}, 0.12) !important;
      animation: ${pulseGreen} 2s infinite;
    `}

  ${(props) =>
    props.$rejected &&
    css`
      box-shadow: 0 0 12px 3px
          rgba(${REJECTED_RGB.r}, ${REJECTED_RGB.g}, ${REJECTED_RGB.b}, 0.18),
        0 0 4px 1px
          rgba(${REJECTED_RGB.r}, ${REJECTED_RGB.g}, ${REJECTED_RGB.b}, 0.12) !important;
      animation: ${pulseMaroon} 2s infinite;
    `}
`;

export const SelectionBoundary: React.FC<SelectionBoundaryProps> = ({
  id,
  hidden,
  showBoundingBox = false,
  scrollIntoView = false,
  color,
  bounds,
  children,
  onHover,
  onClick,
  clickThroughOnPlainClick = false,
  selected,
  approved,
  rejected,
}) => {
  const { registerRef, unregisterRef } = useAnnotationRefs();
  const boundaryRef = useRef<HTMLSpanElement | null>(null);
  const isCreatingAnnotation = useAtomValue(isCreatingAnnotationAtom);

  useEffect(() => {
    if (id) {
      registerRef("annotation", boundaryRef, id);
      return () => {
        unregisterRef("annotation", id);
      };
    }
  }, [id, registerRef, unregisterRef]);

  useEffect(() => {
    if (scrollIntoView && boundaryRef.current) {
      boundaryRef.current.scrollIntoView({
        behavior: "smooth",
        block: "center",
      });
    }
  }, [scrollIntoView]);

  const width = bounds.right - bounds.left;
  const height = bounds.bottom - bounds.top;
  const rotateY = width < 0 ? -180 : 0;
  const rotateX = height < 0 ? -180 : 0;
  const { r, g, b } = hexToRgb(color);
  // Fill ignores showBoundingBox so multi-line inter-row gaps don't stripe through as white.
  const opacity = hidden
    ? 0
    : selected
    ? BOUNDARY_OPACITY_SELECTED
    : BOUNDARY_OPACITY_UNSELECTED;
  const backgroundColor = `rgba(${r}, ${g}, ${b}, ${opacity})`;

  const boxShadow =
    showBoundingBox && !hidden
      ? computeAnnotationBoxShadow(r, g, b, selected)
      : "none";

  const handleClick = (e: React.MouseEvent) => {
    if (isCreatingAnnotation) return;
    if (!onClick) return;
    if (e.shiftKey || clickThroughOnPlainClick) {
      e.stopPropagation();
      onClick(e);
    }
  };

  const handleMouseDown = (e: React.MouseEvent) => {
    if (isCreatingAnnotation) return;
    if (!onClick) return;
    if (e.shiftKey || clickThroughOnPlainClick) {
      e.stopPropagation();
    }
  };

  return (
    <BoundarySpan
      id={`SELECTION_${id}`}
      ref={boundaryRef}
      onClick={handleClick}
      onMouseDown={handleMouseDown}
      onMouseEnter={
        onHover && !hidden && !isCreatingAnnotation
          ? () => onHover(true)
          : undefined
      }
      onMouseLeave={
        onHover && !hidden && !isCreatingAnnotation
          ? () => onHover(false)
          : undefined
      }
      $width={width}
      $height={height}
      $rotateX={rotateX}
      $rotateY={rotateY}
      $hidden={hidden}
      $boxShadow={boxShadow}
      $color={color}
      $backgroundColor={backgroundColor}
      $bounds={bounds}
      $approved={approved}
      $rejected={rejected}
      style={{
        pointerEvents: isCreatingAnnotation ? "none" : "auto",
        cursor: clickThroughOnPlainClick ? "pointer" : undefined,
      }}
    >
      {children || null}
    </BoundarySpan>
  );
};
