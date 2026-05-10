import React, { useEffect, useMemo } from "react";
import { toast } from "react-toastify";
import { useQuery, useReactiveVar } from "@apollo/client";
import { useLocation } from "react-router-dom";
import { ExtractCards } from "./ExtractCards";
import {
  openedCorpus,
  analysisSearchTerm,
  authToken,
  showCorpusActionOutputs,
} from "../../graphql/cache";
import { LooseObject } from "../types";
import {
  GetExtractsOutput,
  GetExtractsInput,
  GET_EXTRACTS,
} from "../../graphql/queries";

interface CorpusExtractCardsProps {
  /** If true, clicking selects via URL params instead of navigating away */
  useInlineSelection?: boolean;
  /** Filter extracts by status: all, running, completed, failed, not_started */
  activeFilter?: string;
}

export const CorpusExtractCards: React.FC<CorpusExtractCardsProps> = ({
  useInlineSelection = false,
  activeFilter = "all",
}) => {
  const show_corpus_action_outputs = useReactiveVar(showCorpusActionOutputs);
  const opened_corpus = useReactiveVar(openedCorpus);
  const analysis_search_term = useReactiveVar(analysisSearchTerm);
  const auth_token = useReactiveVar(authToken);
  const location = useLocation();

  // CRITICAL: Memoize to prevent new object on every render (causes infinite Apollo refetch)
  const extract_variables = useMemo(() => {
    const vars: LooseObject = {
      corpusId: opened_corpus?.id ? opened_corpus.id : "",
      corpusAction_Isnull: show_corpus_action_outputs,
    };
    if (analysis_search_term) {
      vars["searchText"] = analysis_search_term;
    }
    return vars;
  }, [opened_corpus?.id, show_corpus_action_outputs, analysis_search_term]);

  const {
    refetch: refetchExtracts,
    loading: loading_extracts,
    networkStatus: extracts_network_status,
    error: extracts_load_error,
    data: extracts_response,
    fetchMore: fetchMoreExtracts,
  } = useQuery<GetExtractsOutput, GetExtractsInput>(GET_EXTRACTS, {
    variables: extract_variables,
    fetchPolicy: "network-only",
    notifyOnNetworkStatusChange: true,
    skip: !opened_corpus?.id, // CRITICAL: Don't query when no corpus selected!
  });

  if (extracts_load_error) {
    toast.error("ERROR\nCould not fetch extracts for corpus.");
  }

  useEffect(() => {
    refetchExtracts();
  }, [analysis_search_term, show_corpus_action_outputs]);

  useEffect(() => {
    if (auth_token && opened_corpus?.id) {
      refetchExtracts();
    }
  }, [auth_token]);

  useEffect(() => {
    if (opened_corpus?.id && location.pathname === "/corpuses") {
      refetchExtracts();
    }
  }, [location]);

  const extracts = extracts_response?.extracts?.edges
    ? extracts_response.extracts.edges.map((edge) => edge.node)
    : [];

  return (
    <ExtractCards
      extracts={extracts}
      opened_corpus={opened_corpus}
      loading={loading_extracts}
      networkStatus={extracts_network_status}
      loading_message="Extracts Loading..."
      pageInfo={extracts_response?.extracts?.pageInfo}
      fetchMore={fetchMoreExtracts}
      useInlineSelection={useInlineSelection}
      activeFilter={activeFilter}
    />
  );
};
