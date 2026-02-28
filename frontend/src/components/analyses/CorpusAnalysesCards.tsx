import { useEffect, useMemo } from "react";
import _ from "lodash";
import { toast } from "react-toastify";
import { useQuery, useReactiveVar } from "@apollo/client";
import { useLocation } from "react-router-dom";

import { AnalysesCards } from "./AnalysesCards";
import {
  analysisSearchTerm,
  authToken,
  openedCorpus,
  showCorpusActionOutputs,
} from "../../graphql/cache";
import { LooseObject } from "../types";
import {
  GetAnalysesInputs,
  GetAnalysesOutputs,
  GET_ANALYSES,
} from "../../graphql/queries";
import useWindowDimensions from "../hooks/WindowDimensionHook";

export const CorpusAnalysesCards = () => {
  /**
   * Similar to AnnotationCorpusCards, this component wraps the DocumentCards component
   * (which is a pure rendering component) with some query logic for a given corpus_id.
   * If the corpus_id is passed in, it will query and display the documents for
   * that corpus and let you browse them.
   */
  const opened_corpus = useReactiveVar(openedCorpus);
  const analysis_search_term = useReactiveVar(analysisSearchTerm);
  const auth_token = useReactiveVar(authToken);
  const show_corpus_action_outputs = useReactiveVar(showCorpusActionOutputs);

  const location = useLocation();
  const { width } = useWindowDimensions();

  //////////////////////////////////////////////////////////////////////
  // Craft the query variables obj based on current application state
  // CRITICAL: Memoize to prevent new object on every render (causes infinite Apollo refetch)
  const analyses_variables = useMemo(() => {
    const vars: LooseObject = {
      corpusId: opened_corpus?.id ? opened_corpus.id : "",
      analyzedCorpus_Isnull: !show_corpus_action_outputs,
    };
    if (analysis_search_term) {
      vars["searchText"] = analysis_search_term;
    }
    return vars;
  }, [opened_corpus?.id, show_corpus_action_outputs, analysis_search_term]);

  ///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
  // Setup document resolvers and mutations
  ///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
  const {
    refetch: refetchAnalyses,
    loading: loading_analyses,
    error: analyses_load_error,
    data: analyses_response,
    fetchMore: fetchMoreAnalyses,
  } = useQuery<GetAnalysesOutputs, GetAnalysesInputs>(GET_ANALYSES, {
    variables: analyses_variables,
    fetchPolicy: "network-only",
    notifyOnNetworkStatusChange: true,
    skip: !opened_corpus?.id, // CRITICAL: Don't query when no corpus selected!
  });
  if (analyses_load_error) {
    console.error("Corpus analysis fetch error", analyses_load_error);
    toast.error("ERROR\nCould not fetch analyses for corpus.");
  }

  ///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
  // Effects to reload data on certain changes
  ///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////

  useEffect(() => {
    refetchAnalyses();
  }, []);

  useEffect(() => {
    refetchAnalyses();
  }, [analysis_search_term]);

  // If user logs in while on this page... refetch to get their authorized corpuses
  useEffect(() => {
    // console.log("Auth token change", auth_token);
    if (auth_token && opened_corpus?.id) {
      refetchAnalyses();
    }
  }, [auth_token]);

  // Disabled: refetching on analysis_ids_to_display caused infinite refresh
  // because the dependency itself changes on every refetch.

  //If we detech user navigated to this page, refetch
  useEffect(() => {
    if (opened_corpus?.id && location.pathname === "/corpuses") {
      refetchAnalyses();
    }
  }, [location]);

  ///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
  // Query to shape item data
  ///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
  const analyses = analyses_response?.analyses?.edges
    ? analyses_response.analyses.edges.map((edge) => edge.node)
    : [];

  return (
    <AnalysesCards
      analyses={analyses}
      opened_corpus={opened_corpus}
      loading={loading_analyses}
      loading_message="Analyses Loading..."
      pageInfo={analyses_response?.analyses?.pageInfo}
      fetchMore={fetchMoreAnalyses}
      style={{
        minHeight: "70vh",
        overflowY: "unset",
        ...(width > 400 && width < 600 ? { paddingLeft: "2rem" } : {}),
      }}
    />
  );
};
