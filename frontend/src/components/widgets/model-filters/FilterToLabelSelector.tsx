import { useEffect } from "react";
import { useQuery, useReactiveVar } from "@apollo/client";
import { Chip } from "@os-legal/ui";
import Select, { SelectOption } from "../../common/Select";
import { SingleValue, MultiValue } from "react-select";

import _ from "lodash";

import {
  filterToLabelId,
  filterToLabelsetId,
  userObj,
} from "../../../graphql/cache";
import {
  GetAnnotationLabelsInput,
  GetAnnotationLabelsOutput,
  GET_ANNOTATION_LABELS,
} from "../../../graphql/queries";
import { AnnotationLabelType, LabelType } from "../../../types/graphql-api";
import { LooseObject } from "../../types";
import { toast } from "react-toastify";
import useWindowDimensions from "../../hooks/WindowDimensionHook";
import { MOBILE_VIEW_BREAKPOINT } from "../../../assets/configurations/constants";

interface FilterToLabelSelectorProps {
  style?: Record<string, any>;
  label_type?: LabelType;
  only_labels_for_corpus_id?: string;
  only_labels_for_labelset_id?: string;
}

export const FilterToLabelSelector = ({
  style,
  label_type,
  only_labels_for_corpus_id,
  only_labels_for_labelset_id,
}: FilterToLabelSelectorProps) => {
  const { width } = useWindowDimensions();
  const use_mobile_layout = width <= MOBILE_VIEW_BREAKPOINT;

  const filtered_to_label_id = useReactiveVar(filterToLabelId);
  const filtered_to_labelset_id = useReactiveVar(filterToLabelsetId);
  const user_obj = useReactiveVar(userObj);

  let annotations_variables: LooseObject = {};
  if (label_type) {
    annotations_variables["labelType"] = label_type;
  }
  if (only_labels_for_corpus_id) {
    annotations_variables["corpusId"] = only_labels_for_corpus_id;
  }
  if (only_labels_for_labelset_id) {
    annotations_variables["labelsetId"] = only_labels_for_labelset_id;
  }

  const {
    refetch: refetch_labels,
    loading: annotation_labels_loading,
    data: annotation_labels_data,
    error: annotation_labels_loading_error,
  } = useQuery<GetAnnotationLabelsOutput, GetAnnotationLabelsInput>(
    GET_ANNOTATION_LABELS,
    {
      variables: annotations_variables,
      notifyOnNetworkStatusChange: true,
    }
  );

  if (annotation_labels_loading_error) {
    toast.error("ERROR\nCould not fetch available labels for filtering.");
  }

  useEffect(() => {
    refetch_labels();
    return function clearSelectedLabelOnUnmount() {
      filterToLabelId("");
    };
  }, []);

  useEffect(() => {
    // console.log("only_labels_for_corpus_id");
    refetch_labels();
  }, [only_labels_for_corpus_id]);

  useEffect(() => {
    // console.log("only_labels_for_labelset_id");
    if (!only_labels_for_corpus_id && !only_labels_for_labelset_id) {
      filterToLabelId("");
    } else {
      refetch_labels();
    }
  }, [only_labels_for_labelset_id]);

  useEffect(() => {
    // console.log("filtered_to_labelset_id");
    refetch_labels();
  }, [filtered_to_labelset_id]);

  useEffect(() => {
    // console.log("label_type");
    refetch_labels();
  }, [label_type]);

  useEffect(() => {
    // console.log("user_obj");
    refetch_labels();
  }, [user_obj]);

  // console.log("Annotation label selector data", annotation_labels_data);

  const labels = annotation_labels_data?.annotationLabels
    ? annotation_labels_data.annotationLabels.edges
        .map((edge) => (edge ? edge.node : null))
        .filter((edge) => edge != null)
    : [];
  // console.log("Labels", labels);

  let label_options: SelectOption[] = [];
  if (labels) {
    label_options = labels
      .filter((item): item is AnnotationLabelType => !!item)
      .map((label) => ({
        value: label.id,
        label: label.text || "",
        ...(label.icon && { icon: label.icon }),
        ...(label.description && { subheader: label.description }),
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
          background: "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
          color: "white",
          fontWeight: "600",
          fontSize: "0.75rem",
          letterSpacing: "0.025em",
          textTransform: "uppercase",
          boxShadow: "0 2px 4px rgba(102, 126, 234, 0.2)",
        }}
      >
        Filter by Label
      </Chip>
      <div style={{ position: "relative", zIndex: 10 }}>
        <Select
          isClearable
          isSearchable
          isLoading={annotation_labels_loading}
          options={label_options}
          onChange={(
            selectedOption: SingleValue<SelectOption> | MultiValue<SelectOption>
          ) => {
            // console.log("Set filter label id", selectedOption);
            // This is a single select, so we know it's SingleValue
            const singleValue = selectedOption as SingleValue<SelectOption>;
            filterToLabelId(
              singleValue && !Array.isArray(singleValue)
                ? String(singleValue.value)
                : ""
            );
          }}
          placeholder="Select a label to filter..."
          value={
            filtered_to_label_id
              ? label_options.find((opt) => opt.value === filtered_to_label_id)
              : null
          }
        />
      </div>
    </div>
  );
};
