import { useQuery, useReactiveVar } from "@apollo/client";

import { Chip } from "@os-legal/ui";
import Select, { SelectOption } from "../../common/Select";
import { SingleValue, MultiValue } from "react-select";

import _ from "lodash";

import { filterToCorpus, userObj } from "../../../graphql/cache";
import {
  GetCorpusesOutputs,
  GetCorpusesInputs,
  GET_CORPUSES,
} from "../../../graphql/queries";
import { CorpusType } from "../../../types/graphql-api";
import { useEffect } from "react";
import { LooseObject } from "../../types";
import useWindowDimensions from "../../hooks/WindowDimensionHook";
import { MOBILE_VIEW_BREAKPOINT } from "../../../assets/configurations/constants";

interface FilterToCorpusSelector {
  style?: Record<string, any>;
  uses_labelset_id?: string | null;
}

export const FilterToCorpusSelector = ({
  style,
  uses_labelset_id,
}: FilterToCorpusSelector) => {
  const { width } = useWindowDimensions();
  const use_mobile_layout = width <= MOBILE_VIEW_BREAKPOINT;

  const filtered_to_corpus = useReactiveVar(filterToCorpus);
  const user_obj = useReactiveVar(userObj);

  let corpus_variables: LooseObject = [];
  if (uses_labelset_id) {
    corpus_variables["usesLabelsetId"] = uses_labelset_id;
  }

  const { refetch, loading, data, error } = useQuery<
    GetCorpusesOutputs,
    GetCorpusesInputs
  >(GET_CORPUSES, {
    variables: corpus_variables,
    notifyOnNetworkStatusChange: true, // required to get loading signal on fetchMore
  });

  useEffect(() => {
    refetch();
  }, []);

  useEffect(() => {
    refetch();
  }, [user_obj]);

  const corpus_edges = data?.corpuses?.edges ? data.corpuses.edges : [];
  const corpus_items = corpus_edges
    .map((edge) => (edge?.node ? edge.node : undefined))
    .filter((item): item is CorpusType => !!item);

  let label_options: SelectOption[] = [];
  if (corpus_items) {
    label_options = corpus_items
      .filter((item): item is CorpusType => !!item)
      .map((label) => ({
        value: label.id,
        label: label?.title ? label.title : "",
        ...(label.icon && { icon: label.icon }),
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
          background: "linear-gradient(135deg, #89f7fe 0%, #66a6ff 100%)",
          color: "white",
          fontWeight: "600",
          fontSize: "0.75rem",
          letterSpacing: "0.025em",
          textTransform: "uppercase",
          boxShadow: "0 2px 4px rgba(102, 166, 255, 0.2)",
        }}
      >
        Filter by Corpus
      </Chip>
      <div style={{ position: "relative", zIndex: 10 }}>
        <Select
          isClearable
          isSearchable
          isLoading={loading}
          options={label_options}
          onChange={(
            selectedOption: SingleValue<SelectOption> | MultiValue<SelectOption>
          ) => {
            // This is a single select, so we know it's SingleValue
            const singleValue = selectedOption as SingleValue<SelectOption>;
            if (!singleValue || Array.isArray(singleValue)) {
              filterToCorpus(null);
            } else {
              let matching_corpuses = corpus_items.filter(
                (item) => item.id === singleValue.value
              );
              if (matching_corpuses.length === 1) {
                filterToCorpus(matching_corpuses[0]);
              }
            }
          }}
          placeholder="Select a corpus to filter..."
          value={
            filtered_to_corpus
              ? label_options.find((opt) => opt.value === filtered_to_corpus.id)
              : null
          }
        />
      </div>
    </div>
  );
};
