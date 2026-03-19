import { useQuery, useReactiveVar } from "@apollo/client";
import { useEffect } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { toast } from "react-toastify";
import { Chip } from "@os-legal/ui";
import Select, { SelectOption } from "../../common/Select";
import { MultiValue, SingleValue } from "react-select";
import {
  authToken,
  selectedAnalyses,
  selectedAnalysesIds,
} from "../../../graphql/cache";
import {
  GetAnalysesInputs,
  GetAnalysesOutputs,
  GET_ANALYSES,
} from "../../../graphql/queries";
import { AnalysisType, CorpusType } from "../../../types/graphql-api";
import useWindowDimensions from "../../hooks/WindowDimensionHook";
import { MOBILE_VIEW_BREAKPOINT } from "../../../assets/configurations/constants";
import { updateAnnotationSelectionParams } from "../../../utils/navigationUtils";

interface FilterToAnalysesSelectorProps {
  corpus: CorpusType;
  style?: Record<string, any>;
}

export const FilterToAnalysesSelector = ({
  corpus,
  style,
}: FilterToAnalysesSelectorProps) => {
  const navigate = useNavigate();
  const location = useLocation();

  const { width } = useWindowDimensions();
  const use_mobile_layout = width <= MOBILE_VIEW_BREAKPOINT;

  const auth_token = useReactiveVar(authToken);
  const selected_analyses = useReactiveVar(selectedAnalyses);

  const analysis_ids_to_display = selected_analyses.map(
    (analysis) => analysis.id
  ) as string[];

  const handleChange = (
    selectedOptions: SingleValue<SelectOption> | MultiValue<SelectOption>
  ) => {
    // console.log("Handle analysis selection", selectedOptions);

    let selected_analyses: AnalysisType[] = [];

    // This is a multi-select, so we know it's MultiValue (array)
    if (
      selectedOptions &&
      Array.isArray(selectedOptions) &&
      selectedOptions.length > 0
    ) {
      for (let option of selectedOptions) {
        let analysis_to_add = analyses_response?.analyses.edges
          .filter((analysis_edge) => analysis_edge.node.id === option.value)
          .map((edge) => edge.node);

        if (analysis_to_add !== undefined) {
          selected_analyses = [...selected_analyses, ...analysis_to_add];
        }
      }
      console.log("Set selected analyses", selected_analyses);
      selectedAnalyses(selected_analyses);
      // Update URL - CentralRouteManager will set reactive var
      updateAnnotationSelectionParams(location, navigate, {
        analysisIds: selected_analyses.map((analysis) => analysis.id),
      });
    } else {
      selectedAnalyses([]);
      // Update URL - CentralRouteManager will set reactive var
      updateAnnotationSelectionParams(location, navigate, {
        analysisIds: [],
      });
    }
  };

  ///////////////////////////////////////////////////////////////////////////////
  const {
    refetch: refetchAnalyses,
    loading: loading_analyses,
    error: analyses_load_error,
    data: analyses_response,
    fetchMore: fetchMoreAnalyses,
  } = useQuery<GetAnalysesOutputs, GetAnalysesInputs>(GET_ANALYSES, {
    variables: {
      corpusId: corpus.id,
    },
    fetchPolicy: "network-only",
    notifyOnNetworkStatusChange: true,
  });
  if (analyses_load_error) {
    toast.error("ERROR\nCould not fetch analyses for multiselector.");
    console.error(analyses_load_error);
  }

  useEffect(() => {
    refetchAnalyses();
  }, [auth_token]);

  useEffect(() => {
    refetchAnalyses();
  }, [corpus]);

  ///////////////////////////////////////////////////////////////////////////////
  let analysis_options: SelectOption[] = [];
  if (analyses_response?.analyses?.edges) {
    analysis_options = analyses_response?.analyses?.edges.map((edge) => ({
      value: edge.node.id,
      label: `${edge.node.id}: ${edge.node.analyzer.analyzerId}`,
    }));
  }

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "0.375rem",
        width: "100%",
        position: "relative",
        ...style,
      }}
    >
      <Chip
        size="sm"
        variant="filled"
        style={{
          margin: "0",
          background: "linear-gradient(135deg, #f093fb 0%, #f5576c 100%)",
          color: "white",
          fontWeight: "600",
          fontSize: "0.75rem",
          letterSpacing: "0.025em",
          textTransform: "uppercase",
          boxShadow: "0 2px 4px rgba(245, 87, 108, 0.2)",
        }}
      >
        Created by Analysis
      </Chip>
      <div style={{ position: "relative", zIndex: 10 }}>
        <Select
          isMulti
          isClearable
          placeholder="Select analyses..."
          options={analysis_options}
          onChange={handleChange}
          value={analysis_options.filter((opt) =>
            analysis_ids_to_display.includes(opt.value)
          )}
        />
      </div>
    </div>
  );
};
