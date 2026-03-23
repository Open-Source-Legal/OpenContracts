import styled, { DefaultTheme } from "styled-components";
import _ from "lodash";
import {
  ANNOTATION_TOKEN_RADIUS,
  TOKEN_EXPANSION_PX,
  TOKEN_OPACITY_HIGH,
  TOKEN_OPACITY_LOW,
  TOKEN_SHADOW_BLUR,
  TOKEN_SHADOW_SPREAD,
} from "../../../../assets/configurations/constants";

/**
 * Narrow theme interface containing only the colour tokens this
 * module needs.  This avoids a global theme augmentation while
 * remaining fully type-safe.
 */
// Remove ColorTheme interface
// interface ColorTheme extends DefaultTheme {
//   color: {
//     B3: string;
//     // Add further colour keys here as needed
//     [key: string]: string;
//   };
// }

interface TokenSpanProps {
  hidden?: boolean;
  color?: string;
  isSelected?: boolean;
  highOpacity?: boolean;
}

export const TokenSpan = styled.span.attrs<
  TokenSpanProps & { theme: DefaultTheme }
>((props) => {
  const bg = props.isSelected
    ? props.color
      ? props.color.toUpperCase()
      : props.theme.color.B3
    : "none";
  return {
    style: {
      background: bg,
      opacity: props.hidden
        ? 0.0
        : props.highOpacity
        ? TOKEN_OPACITY_HIGH
        : TOKEN_OPACITY_LOW,
      boxShadow:
        props.isSelected && !props.hidden
          ? `0 0 ${TOKEN_SHADOW_BLUR}px ${TOKEN_SHADOW_SPREAD}px ${bg}`
          : "none",
    },
  };
})`
  position: absolute;
  border-radius: ${ANNOTATION_TOKEN_RADIUS};
  transition: opacity 0.3s ease-in-out;
`;

interface SelectionTokenSpanProps
  extends React.HTMLAttributes<HTMLSpanElement> {
  top: number;
  bottom: number;
  left: number;
  right: number;
  pointerEvents?: React.CSSProperties["pointerEvents"];
  hidden?: boolean;
  color?: string;
  isSelected?: boolean;
  highOpacity?: boolean;
}

/* ------------------------------------------------------------------ */
/* SelectionTokenSpan                                                 */
/* ------------------------------------------------------------------ */
interface SelectionTokenSpanThemeProps extends SelectionTokenSpanProps {
  theme: DefaultTheme;
}

export const SelectionTokenSpan = styled.span.attrs<SelectionTokenSpanThemeProps>(
  (props) => {
    const bg = props.isSelected
      ? props.color
        ? props.color.toUpperCase()
        : props.theme.color.B3
      : "none";
    return {
      id: props.id,
      style: {
        background: bg,
        opacity: props.hidden
          ? 0.0
          : props.highOpacity
          ? TOKEN_OPACITY_HIGH
          : TOKEN_OPACITY_LOW,
        left: `${props.left - TOKEN_EXPANSION_PX}px`,
        top: `${props.top - TOKEN_EXPANSION_PX}px`,
        width: `${props.right - props.left + TOKEN_EXPANSION_PX * 2}px`,
        height: `${props.bottom - props.top + TOKEN_EXPANSION_PX * 2}px`,
        pointerEvents: props.pointerEvents,
        boxShadow:
          props.isSelected && !props.hidden
            ? `0 0 ${TOKEN_SHADOW_BLUR}px ${TOKEN_SHADOW_SPREAD}px ${bg}`
            : "none",
      },
    };
  }
)`
  position: absolute;
  border-radius: ${ANNOTATION_TOKEN_RADIUS};
  transition: opacity 0.3s ease-in-out;
`;
