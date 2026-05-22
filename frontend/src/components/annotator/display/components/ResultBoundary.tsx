import React, { useRef, useEffect } from "react";
import _ from "lodash";
import { BoundingBox } from "../../../types";
import { hexToRgb } from "../../../../utils/transform";
import { computeAnnotationBoxShadow } from "../../../../utils/colorUtils";
import {
  ANNOTATION_BOUNDARY_RADIUS,
  BOUNDARY_OPACITY_SELECTED,
  BOUNDARY_OPACITY_UNSELECTED,
} from "../../../../assets/configurations/constants";
import { useAnnotationRefs } from "../../hooks/useAnnotationRefs";

interface ResultBoundaryProps {
  id?: number | string;
  hidden: boolean;
  showBoundingBox?: boolean;
  scrollIntoView?: boolean;
  color: string;
  bounds: BoundingBox;
  selected: boolean;
  children?: React.ReactNode;
  annotationId?: string;
  onHover?: (hovered: boolean) => void;
  onClick?: () => void;
}

/**
 * ResultBoundary Component
 *
 * A boundary box component used to highlight search results or annotations.
 * It manages its ref internally and registers it with the annotation refs atom.
 */
export const ResultBoundary = ({
  id,
  hidden,
  showBoundingBox = true,
  scrollIntoView = false,
  color,
  bounds,
  children,
  onHover,
  onClick,
  selected,
}: ResultBoundaryProps) => {
  const { registerRef, unregisterRef } = useAnnotationRefs();

  const boundaryRef = useRef<HTMLSpanElement | null>(null);

  // Register and unregister the ref using useEffect
  useEffect(() => {
    if (id !== undefined) {
      registerRef("search", boundaryRef, id);
      return () => {
        unregisterRef("search", id);
      };
    }
  }, [id, registerRef, unregisterRef]);

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

  const boxShadow =
    showBoundingBox && !hidden
      ? computeAnnotationBoxShadow(r, g, b, selected)
      : "none";

  // Handle scrolling into view if needed
  useEffect(() => {
    if (scrollIntoView && boundaryRef.current) {
      boundaryRef.current.scrollIntoView({
        behavior: "smooth",
        block: "center",
      });
    }
  }, [scrollIntoView]);

  // Some guidance on refs here: https://stackoverflow.com/questions/61489857/why-i-cant-call-useref-inside-callback
  return (
    <span
      ref={boundaryRef}
      id={id ? id.toString() : undefined}
      onClick={(e) => {
        // Here we are preventing the default PdfAnnotationsContainer
        // behaviour of drawing a new bounding box if the shift key
        // is pressed in order to allow users to select multiple
        // annotations and associate them together with a relation.
        if (e.shiftKey && onClick) {
          e.stopPropagation();
          onClick();
        }
      }}
      onMouseDown={(e) => {
        if (e.shiftKey && onClick) {
          e.stopPropagation();
        }
      }}
      onMouseEnter={
        onHover && !hidden
          ? () => {
              onHover(true);
            }
          : undefined
      }
      onMouseLeave={
        onHover && !hidden
          ? () => {
              onHover(false);
            }
          : undefined
      }
      style={{
        position: "absolute",
        left: `${bounds.left}px`,
        top: `${bounds.top}px`,
        width: `${Math.abs(width)}px`,
        height: `${Math.abs(height)}px`,
        transform: `rotateY(${rotateY}deg) rotateX(${rotateX}deg)`,
        transformOrigin: "top left",
        border: "none",
        borderRadius: ANNOTATION_BOUNDARY_RADIUS,
        boxShadow,
        background: `rgba(${r}, ${g}, ${b}, ${opacity})`,
        transition:
          "background 0.3s ease, box-shadow 0.3s ease, opacity 0.3s ease",
      }}
    >
      {children || null}
    </span>
  );
};
