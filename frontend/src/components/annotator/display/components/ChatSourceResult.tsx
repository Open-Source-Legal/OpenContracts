import { useState, useEffect, useRef } from "react";
import styled from "styled-components";
import { VerticallyJustifiedEndDiv } from "../../sidebar/common";
import { ResultBoundary } from "./ResultBoundary";
import { ChatMessageSource } from "../../context/ChatSourceAtom";
import { ChatSourceTokens } from "./ChatSourceTokens";
import { PDFPageInfo } from "../../types/pdf";
import { useAnnotationDisplay } from "../../context/UISettingsAtom";
import { BoundingBox } from "../../../types";
import { useAnnotationRefs } from "../../hooks/useAnnotationRefs";
import { LabelDisplayBehavior } from "../../../../types/graphql-api";
import { ANNOTATION_BOUNDARY_RADIUS } from "../../../../assets/configurations/constants";

/**
 * Props for rendering a chat message source on a PDF page.
 */
export interface ChatSourceResultProps {
  /** Unique key used to register this chat source element e.g. `${messageId}.${index}` */
  refKey: string;
  /** Total number of chat sources available in the current message. */
  total_results: number;
  /** Whether to show a bounding box around the source. */
  showBoundingBox: boolean;
  /** Whether the chat source should be hidden (e.g. not selected). */
  hidden: boolean;
  /** The page-specific information (viewport, scaling, etc.) for rendering. */
  pageInfo: PDFPageInfo;
  /** The chat message source to render. */
  source: ChatMessageSource;
  /** Whether to show label information. */
  showInfo?: boolean;
  /** If true, scroll the element into view when rendered. */
  scrollIntoView?: boolean;
  /** If true, render with a selected style. */
  selected?: boolean;
}

/**
 * Renders a chat message source following the same pattern as search results.
 * It scales the source bounds, computes the border width, and renders a boundary
 * with an overlaid label and token highlights.
 */
export const ChatSourceResult = ({
  refKey,
  total_results,
  showBoundingBox,
  hidden,
  pageInfo,
  source,
  showInfo = true,
  scrollIntoView = false,
  selected = false,
}: ChatSourceResultProps) => {
  // Register the DOM node of this chat source with the annotation refs
  const { registerRef, unregisterRef } = useAnnotationRefs();
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (containerRef.current) {
      registerRef("chatSource", containerRef, refKey);
    }
    return () => {
      unregisterRef("chatSource", refKey);
    };
  }, [refKey, registerRef, unregisterRef]);

  const { showLabels, hideLabels } = useAnnotationDisplay();
  const color = "#5C7C9D";
  const [hovered, setHovered] = useState(false);

  const currentPage = pageInfo.page.pageNumber - 1;
  const boundsData = source.boundsByPage[currentPage];
  // If no bounds available for this page, do not render anything.
  if (!boundsData) return null;

  const bounds = pageInfo.getScaledBounds(boundsData);

  return (
    <div ref={containerRef}>
      <ResultBoundary
        id={`CHAT_SOURCE_${refKey}`}
        hidden={hidden}
        showBoundingBox={showBoundingBox}
        color={color}
        bounds={bounds}
        selected={selected}
        onHover={setHovered}
        scrollIntoView={Boolean(scrollIntoView)}
      >
        {showInfo && !hideLabels ? (
          <SelectionInfo
            bounds={bounds}
            color={color}
            showBoundingBox={showBoundingBox}
          >
            <SelectionInfoContainer>
              <VerticallyJustifiedEndDiv>
                <LabelTagContainer
                  $hidden={false}
                  $hovered={hovered}
                  $color={color}
                  $display_behavior={showLabels}
                >
                  <div style={{ whiteSpace: "nowrap", overflowX: "visible" }}>
                    <span>
                      Chat Source {source.label} of {total_results}
                    </span>
                  </div>
                </LabelTagContainer>
              </VerticallyJustifiedEndDiv>
            </SelectionInfoContainer>
          </SelectionInfo>
        ) : null}
      </ResultBoundary>
      {source.tokensByPage[currentPage] !== undefined ? (
        <ChatSourceTokens
          color={color}
          highOpacity={!showBoundingBox}
          hidden={hidden}
          pageInfo={pageInfo}
          tokens={source.tokensByPage[currentPage] || []}
        />
      ) : null}
    </div>
  );
};

/**
 * Props for the selection info overlay that displays label details.
 */
interface SelectionInfoProps {
  bounds: BoundingBox;
  color: string;
  showBoundingBox: boolean;
}

// Styled component for the overlay info that appears above the boundary.
const SelectionInfo = styled.div.attrs<SelectionInfoProps>(
  ({ bounds, color, showBoundingBox }) => ({
    style: {
      position: "absolute",
      width: `${bounds.right - bounds.left}px`,
      right: "0px",
      transform: "translateY(-100%)",
      border: "none",
      borderRadius: `${ANNOTATION_BOUNDARY_RADIUS} ${ANNOTATION_BOUNDARY_RADIUS} 0 0`,
      background: showBoundingBox ? color : "rgba(255, 255, 255, 0.0)",
      fontWeight: "bold",
      fontSize: "12px",
      userSelect: "none",
      transition: "all 0.3s ease",
    },
  })
)`
  * {
    vertical-align: middle;
  }
`;

// Container to hold the selection info content.
const SelectionInfoContainer = styled.div`
  display: flex;
  flex-direction: row;
  justify-content: space-between;
`;

// Styled container for the label tag.
const LabelTagContainer = styled.div<{
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
  padding: 2px 4px;
  background-color: ${({ $color }) => $color};
  color: #000;
  border-radius: 4px;
`;
