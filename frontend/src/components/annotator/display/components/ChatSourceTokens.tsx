/**
 * ChatSourceTokens.tsx - Token highlights (similar to SelectionTokens).
 */
import React, { FC, useEffect, useRef } from "react";
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

/**
 * Updated to use TokenId[] instead of string[]
 */
interface ChatSourceTokensProps {
  tokens: TokenId[];
  hidden: boolean;
  color?: string;
  highOpacity?: boolean;
  pageInfo: PDFPageInfo;
  scrollTo?: boolean;
}

const TokenDiv = styled.div<{
  $hidden: boolean;
  $color?: string;
  $highOpacity?: boolean;
}>`
  position: absolute;
  background-color: ${(props) => props.$color ?? "rgba(255, 255, 0, 0.3)"};
  opacity: ${(props) =>
    props.$hidden
      ? 0
      : props.$highOpacity
      ? TOKEN_OPACITY_HIGH
      : TOKEN_OPACITY_LOW};
  pointer-events: none;
  border-radius: ${ANNOTATION_TOKEN_RADIUS};
  box-shadow: ${(props) =>
    props.$hidden
      ? "none"
      : `0 0 ${TOKEN_SHADOW_BLUR}px ${TOKEN_SHADOW_SPREAD}px ${
          props.$color ?? "rgba(255, 255, 0, 0.15)"
        }`};
  transition: opacity 0.3s ease-in-out;
`;

export const ChatSourceTokens: FC<ChatSourceTokensProps> = ({
  tokens,
  hidden,
  color,
  highOpacity,
  pageInfo,
  scrollTo,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollTo && containerRef.current) {
      containerRef.current.scrollIntoView({
        behavior: "smooth",
        block: "center",
      });
    }
  }, [scrollTo]);

  return (
    <div ref={containerRef}>
      {tokens.map((token, i) => {
        const pageToken = pageInfo.tokens?.[token.tokenIndex];
        if (!pageToken) return null;

        // Scale the token bounds using pageInfo to maintain consistency with SearchResult and Selection rescaling
        const b = pageInfo.getScaledTokenBounds(pageToken);
        const style = {
          left: `${b.left - TOKEN_EXPANSION_PX}px`,
          top: `${b.top - TOKEN_EXPANSION_PX}px`,
          width: `${b.right - b.left + TOKEN_EXPANSION_PX * 2}px`,
          height: `${b.bottom - b.top + TOKEN_EXPANSION_PX * 2}px`,
        };

        return (
          <TokenDiv
            key={i}
            $hidden={hidden}
            $color={color}
            $highOpacity={highOpacity}
            style={style}
          />
        );
      })}
    </div>
  );
};
