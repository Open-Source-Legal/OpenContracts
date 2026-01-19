import styled, { css } from "styled-components";
import { LabelDisplayBehavior } from "../../../../types/graphql-api";
import { getContrastColor } from "../../../../utils/transform";

// ... (keep the existing interfaces)

export const SelectionContainer = styled.div<{
  color: string;
  showBoundingBox: boolean;
  selectionRef:
    | React.MutableRefObject<Record<string, HTMLElement | null>>
    | undefined;
}>`
  position: absolute;
  border-radius: 4px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  background-color: ${(props) =>
    props.showBoundingBox ? `${props.color}33` : "transparent"};
  transition: background-color 0.2s ease;

  &:hover {
    background-color: ${(props) =>
      props.showBoundingBox ? `${props.color}66` : "transparent"};
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
  $border: number;
  $color: string;
  $showBoundingBox: boolean;
  $approved?: boolean;
  $rejected?: boolean;
}

export const SelectionInfo = styled.div<SelectionInfoProps>`
  position: absolute;
  width: ${(props) => props.$bounds.right - props.$bounds.left}px;
  right: -${(props) => props.$border + ((props?.$approved ? 1 : props?.$rejected) ? -1 : 0)}px;
  bottom: calc(100% - 2px);
  border-radius: 4px 4px 0 0;
  background: ${(props) =>
    props.$showBoundingBox ? props.$color : "rgba(255, 255, 255, 0.9)"};
  padding: 1px 8px;
  font-weight: bold;
  font-size: 12px;
  user-select: none;
  box-sizing: border-box;
  transition: all 0.2s ease-in-out;

  ${(props) =>
    props.$approved &&
    css`
      border-top: 2px solid #2ecc71;
      border-left: 2px solid #2ecc71;
      border-right: 2px solid #2ecc71;
      box-shadow: 0 0 8px rgba(46, 204, 113, 0.2);
    `}

  ${(props) =>
    props.$rejected &&
    css`
      border-top: 2px solid #e74c3c;
      border-left: 2px solid #e74c3c;
      border-right: 2px solid #e74c3c;
      box-shadow: 0 0 8px rgba(231, 76, 60, 0.2);
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
  padding: 2px 6px;
  border-radius: 3px;
  position: relative;
`;
