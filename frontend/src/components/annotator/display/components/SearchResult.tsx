import { useState, useMemo } from "react";
import styled from "styled-components";
import _ from "lodash";
import { VerticallyJustifiedEndDiv } from "../../sidebar/common";

import { ResultBoundary } from "./ResultBoundary";
import { BoundingBox, TextSearchTokenResult } from "../../../types";

import { SearchSelectionTokens } from "./SelectionTokens";
import { LabelTagContainer } from "./Containers";
import { PDFPageInfo } from "../../types/pdf";
import { useAnnotationDisplay } from "../../context/UISettingsAtom";
import { ANNOTATION_BOUNDARY_RADIUS } from "../../../../assets/configurations/constants";

interface SearchResultProps {
  total_results: number;
  showBoundingBox: boolean;
  hidden: boolean;
  pageInfo: PDFPageInfo;
  match: TextSearchTokenResult;
  showInfo?: boolean;
  scrollIntoView?: boolean;
}

export const SearchResult: React.FC<SearchResultProps> = ({
  total_results,
  showBoundingBox,
  hidden,
  pageInfo,
  match,
  showInfo = true,
  scrollIntoView = false,
}) => {
  const { showLabels, hideLabels } = useAnnotationDisplay();

  const color = "#ffff00";
  const [hovered, setHovered] = useState(false);

  const pageIdx = pageInfo.page.pageNumber - 1;

  /* Compute the (scaled) bbox only when we really need it */
  const scaledBounds = useMemo<BoundingBox | null>(() => {
    const tokensOnPage = match.tokens[pageIdx];
    if (!tokensOnPage?.length) return null;

    // lazily fill match.bounds so future renders are faster
    if (!match.bounds) match.bounds = {};
    if (!match.bounds[pageIdx]) {
      const raw = pageInfo.getBoundsForTokens(tokensOnPage);
      if (raw) match.bounds[pageIdx] = raw;
    }

    return match.bounds
      ? pageInfo.getScaledBounds(match.bounds[pageIdx])
      : null;
  }, [match, pageIdx, pageInfo]);

  if (!scaledBounds) return null;

  return (
    <>
      <ResultBoundary
        id={`SEARCH_RESULT_${match.id}`}
        hidden={hidden}
        showBoundingBox={showBoundingBox}
        color={color}
        bounds={scaledBounds}
        selected={false}
        onHover={setHovered}
        scrollIntoView={Boolean(scrollIntoView)}
      >
        {showInfo && !hideLabels ? (
          <SelectionInfo
            bounds={scaledBounds}
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
                      Search Result {match.id} of {total_results}
                    </span>
                  </div>
                </LabelTagContainer>
              </VerticallyJustifiedEndDiv>
            </SelectionInfoContainer>
          </SelectionInfo>
        ) : null}
      </ResultBoundary>
      {
        // NOTE: It's important that the parent element of the tokens
        // is the PDF canvas, because we need their absolute position
        // to be relative to that and not another absolute/relatively
        // positioned element. This is why SelectionTokens are not inside
        // SelectionBoundary.
        match.tokens[pageInfo.page.pageNumber - 1] !== undefined ? (
          <SearchSelectionTokens
            color={color}
            highOpacity={!showBoundingBox}
            hidden={hidden}
            pageInfo={pageInfo}
            tokens={match.tokens[pageInfo.page.pageNumber - 1]}
          />
        ) : null
      }
    </>
  );
};

// We use transform here because we need to translate the label upward
// to sit on top of the bounds as a function of *its own* height,
// not the height of its parent.
interface SelectionInfoProps {
  bounds: BoundingBox;
  color: string;
  showBoundingBox: boolean;
}

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

const SelectionInfoContainer = styled.div`
  display: flex;
  flex-direction: row;
  justify-content: space-between;
`;
