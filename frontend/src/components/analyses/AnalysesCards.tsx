import { useNavigate, useLocation } from "react-router-dom";
import styled from "styled-components";

import _ from "lodash";

import { AnalysisItem } from "./AnalysisItem";
import { LoadingOverlay } from "../common/LoadingOverlay";
import { PlaceholderCard } from "../placeholders/PlaceholderCard";
import { FetchMoreOnVisible } from "../widgets/infinite_scroll/FetchMoreOnVisible";
import { AnalysisType, CorpusType, PageInfo } from "../../types/graphql-api";
import { useReactiveVar } from "@apollo/client";
import { selectedAnalyses, selectedAnalysesIds } from "../../graphql/cache";
import useWindowDimensions from "../hooks/WindowDimensionHook";
import { determineCardColCount } from "../../utils/layout";
import { MOBILE_VIEW_BREAKPOINT } from "../../assets/configurations/constants";
import { updateAnnotationSelectionParams } from "../../utils/navigationUtils";

const CardGroup = styled.div<{ $cols: number }>`
  display: grid;
  grid-template-columns: repeat(${(props) => props.$cols}, 1fr);
  gap: 1rem;

  @media (max-width: 768px) {
    grid-template-columns: 1fr;
  }
`;

interface AnalysesCardsProps {
  style?: Record<string, any>;
  read_only?: boolean;
  analyses: AnalysisType[];
  opened_corpus: CorpusType | null;
  pageInfo: PageInfo | undefined | null;
  loading: boolean;
  loading_message: string;
  fetchMore: (args?: any) => void | any;
}

export const AnalysesCards = ({
  style,
  read_only,
  analyses,
  opened_corpus,
  pageInfo,
  loading_message,
  loading,
  fetchMore,
}: AnalysesCardsProps) => {
  const navigate = useNavigate();
  const location = useLocation();

  // Let's figure out the viewport so we can size the cards appropriately.
  const { width } = useWindowDimensions();
  const card_cols = determineCardColCount(width);
  const use_mobile_layout = width <= MOBILE_VIEW_BREAKPOINT;

  //////////////////////////////////////////////////////////////////////
  // Global State Vars in Apollo Cache
  // Use selectedAnalysesIds (URL-driven state) instead of selectedAnalyses
  const analysis_ids_to_display = useReactiveVar(selectedAnalysesIds);

  //////////////////////////////////////////////////////////////////////
  const toggleAnalysis = (selected_analysis: AnalysisType) => {
    if (analysis_ids_to_display.includes(selected_analysis.id)) {
      // Remove from selection
      const cleaned_ids = analysis_ids_to_display.filter(
        (id) => id !== selected_analysis.id
      );
      // Update URL - CentralRouteManager will set reactive var
      updateAnnotationSelectionParams(location, navigate, {
        analysisIds: cleaned_ids,
      });

      // Also update legacy selectedAnalyses for backward compatibility
      const cleaned_analyses = analyses.filter((a) =>
        cleaned_ids.includes(a.id)
      );
      selectedAnalyses(cleaned_analyses);
    } else {
      // Add to selection
      const new_ids = [...analysis_ids_to_display, selected_analysis.id];
      // Update URL - CentralRouteManager will set reactive var
      updateAnnotationSelectionParams(location, navigate, {
        analysisIds: new_ids,
      });

      // Also update legacy selectedAnalyses for backward compatibility
      const new_analyses = analyses.filter((a) => new_ids.includes(a.id));
      selectedAnalyses(new_analyses);
    }
  };

  const handleUpdate = () => {
    if (!loading && pageInfo?.hasNextPage) {
      console.log("Fetching more annotation cards...");
      fetchMore({
        variables: {
          limit: 20,
          cursor: pageInfo.endCursor,
        },
      });
    }
  };

  const analysis_items =
    analyses.length > 0 && opened_corpus ? (
      analyses.map((analysis) => (
        <AnalysisItem
          key={analysis.id}
          analysis={analysis}
          corpus={opened_corpus}
          selected={analysis_ids_to_display.includes(analysis.id)}
          read_only={read_only}
          onSelect={() => toggleAnalysis(analysis)}
        />
      ))
    ) : (
      <PlaceholderCard
        style={{
          padding: ".5em",
          margin: ".75em",
          minWidth: "300px",
        }}
        key="no_analyses_available_placeholder"
        title="No Analyses Available..."
        description="If you have sufficient privileges, try running a new analysis from the corpus page (right click on the corpus)."
      />
    );

  let comp_style = {
    padding: "1rem",
    paddingBottom: "6rem",
    ...(use_mobile_layout
      ? {
          paddingLeft: "0px",
          paddingRight: "0px",
        }
      : {}),
  };

  return (
    <div
      className="AnalysisCards"
      style={{
        width: "100%",
        height: "100%",
        overflowY: "scroll",
        display: "flex",
        flexDirection: "column",
        justifyContent: "flex-start",
        position: "relative",
        ...style,
      }}
    >
      <LoadingOverlay active={loading} content={loading_message} />
      <CardGroup $cols={card_cols} style={comp_style}>
        {analysis_items}
      </CardGroup>
      <FetchMoreOnVisible fetchNextPage={handleUpdate} />
    </div>
  );
};
