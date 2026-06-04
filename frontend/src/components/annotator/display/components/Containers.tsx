import React from "react";
import styled, { css } from "styled-components";
import { LabelDisplayBehavior } from "../../../../types/graphql-api";
import { getContrastColor } from "../../../../utils/transform";
import { ANNOTATION_BOUNDARY_RADIUS } from "../../../../assets/configurations/constants";
import { pulseGreen, pulseMaroon } from "../effects";

// ... (keep the existing interfaces)

export const SelectionContainer = styled.div<{
  color: string;
  showBoundingBox: boolean;
  selectionRef:
    | React.MutableRefObject<Record<string, HTMLElement | null>>
    | undefined;
}>`
  position: absolute;
  border-radius: ${ANNOTATION_BOUNDARY_RADIUS};
  box-shadow: 0 1px 6px rgba(0, 0, 0, 0.06);
  background-color: ${(props) =>
    props.showBoundingBox ? `${props.color}1a` : "transparent"};
  transition: background-color 0.4s ease;

  &:hover {
    background-color: ${(props) =>
      props.showBoundingBox ? `${props.color}33` : "transparent"};
  }
`;

// We use transform here because we need to translate the label upward
// to sit on top of the bounds as a function of *its own* height,
// not the height of it's parent.
interface SelectionInfoProps {
  $bounds: {
    left: number;
    right: number;
  };
  $color: string;
  $showBoundingBox: boolean;
  $approved?: boolean;
  $rejected?: boolean;
}

export const SelectionInfo = styled.div<SelectionInfoProps>`
  position: absolute;
  width: ${(props) => props.$bounds.right - props.$bounds.left}px;
  right: 0px;
  bottom: calc(100% - 2px);
  border-radius: ${ANNOTATION_BOUNDARY_RADIUS} ${ANNOTATION_BOUNDARY_RADIUS} 0 0;
  background: ${(props) =>
    props.$showBoundingBox ? props.$color : "transparent"};
  padding: 1px 8px;
  font-weight: bold;
  font-size: 12px;
  user-select: none;
  box-sizing: border-box;
  transition: all 0.4s ease-in-out;

  ${(props) =>
    props.$approved &&
    css`
      box-shadow: 0 -2px 10px 2px rgba(46, 204, 113, 0.12);
    `}

  ${(props) =>
    props.$rejected &&
    css`
      box-shadow: 0 -2px 10px 2px rgba(231, 76, 60, 0.12);
    `}

  * {
    vertical-align: middle;
  }
`;

export const SelectionInfoContainer = styled.div`
  position: relative;
  display: flex;
  flex-direction: row;
  justify-content: space-between;
  align-items: center;
  pointer-events: none; // Let hover events pass through to children

  /* Enable pointer events only on interactive elements */
  > * {
    pointer-events: auto;
  }
`;

export const LabelTagContainer = styled.div<{
  $hidden: boolean;
  $hovered: boolean;
  $color: string;
  $display_behavior: LabelDisplayBehavior;
}>`
  display: ${(props) => {
    if (props.$hidden) return "none";
    if (props.$display_behavior === LabelDisplayBehavior.HIDE) return "none";
    if (props.$display_behavior === LabelDisplayBehavior.ON_HOVER)
      return props.$hovered ? "flex" : "none";
    return "flex";
  }};
  align-items: center;
  background-color: ${(props) => props.$color};
  color: ${(props) => getContrastColor(props.$color)};
  padding: 2px 8px;
  border-radius: 5px;
  position: relative;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
`;
