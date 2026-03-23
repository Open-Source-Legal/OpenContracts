import { useEffect, useRef } from "react";

import uniqueId from "lodash/uniqueId";
import styled from "styled-components";
import { PDFPageInfo } from "../../types/pdf";
import { TokenId } from "../../types/annotations";
import {
  ANNOTATION_TOKEN_RADIUS,
  TOKEN_EXPANSION_PX,
  TOKEN_OPACITY_HIGH,
  TOKEN_OPACITY_LOW,
  TOKEN_SHADOW_BLUR,
  TOKEN_SHADOW_SPREAD,
} from "../../../../assets/configurations/constants";

// Add interface for the custom props
interface SelectionBoxProps {
  $highOpacity?: boolean;
  $color?: string;
  $left?: number;
  $right?: number;
  $top?: number;
  $bottom?: number;
  $hidden?: boolean;
}

// Highlighter-pen effect: generous rounding, low opacity, and a soft
// same-colour blur that feathers the edges into the page.
const SelectionBox = styled.span.attrs<SelectionBoxProps>((props) => ({
  style: {
    left: `${(props.$left ?? 0) - TOKEN_EXPANSION_PX}px`,
    top: `${(props.$top ?? 0) - TOKEN_EXPANSION_PX}px`,
    width: `${
      props.$right && props.$left
        ? props.$right - props.$left + TOKEN_EXPANSION_PX * 2
        : 0
    }px`,
    height: `${
      props.$bottom && props.$top
        ? props.$bottom - props.$top + TOKEN_EXPANSION_PX * 2
        : 0
    }px`,
    backgroundColor: props.$color || "yellow",
    opacity: props.$highOpacity ? TOKEN_OPACITY_HIGH : TOKEN_OPACITY_LOW,
    display: props.$hidden ? "none" : "block",
    boxShadow: props.$hidden
      ? "none"
      : `0 0 ${TOKEN_SHADOW_BLUR}px ${TOKEN_SHADOW_SPREAD}px ${
          props.$color || "rgba(255,255,0,0.15)"
        }`,
  },
}))<SelectionBoxProps>`
  position: absolute;
  pointer-events: none;
  border-radius: ${ANNOTATION_TOKEN_RADIUS};
  transition: opacity 0.3s ease-in-out;
`;

export interface SelectionTokenGroupProps {
  id?: string;
  color?: string;
  className?: string;
  hidden?: boolean;
  pageInfo: PDFPageInfo;
  highOpacity?: boolean;
  tokens: TokenId[] | null;
  scrollTo?: boolean;
}

export const SelectionTokenGroup = ({
  id,
  color,
  className,
  hidden,
  pageInfo,
  highOpacity,
  tokens,
  scrollTo,
}: SelectionTokenGroupProps) => {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollTo) {
      if (containerRef.current !== undefined && containerRef.current !== null) {
        containerRef.current.scrollIntoView({
          behavior: "smooth",
          block: "center",
        });
      }
    }
  }, [scrollTo]);

  return (
    <div ref={containerRef} id={`SelectionTokenWrapper_${uniqueId()}`}>
      {tokens ? (
        tokens.map((t, i) => {
          const b = pageInfo.getScaledTokenBounds(
            pageInfo.tokens[t.tokenIndex]
          );
          return (
            <SelectionBox
              id={`${uniqueId()}`}
              $hidden={hidden}
              key={i}
              className={className}
              $highOpacity={highOpacity}
              $color={color ? color : undefined}
              $left={b.left}
              $right={b.right}
              $top={b.top}
              $bottom={b.bottom}
            />
          );
        })
      ) : (
        <></>
      )}
    </div>
  );
};
