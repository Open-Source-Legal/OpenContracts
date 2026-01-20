import { useQuery, useReactiveVar } from "@apollo/client";

import Select, { SelectOption } from "../../common/Select";
import { SingleValue, MultiValue } from "react-select";
import styled from "styled-components";

import _ from "lodash";

const FilterLabel = styled.span`
  display: inline-block;
  background: linear-gradient(135deg, #fa709a 0%, #fee140 100%);
  color: white;
  font-weight: 600;
  font-size: 0.75rem;
  padding: 0.375rem 0.625rem;
  border-radius: 8px;
  letter-spacing: 0.025em;
  text-transform: uppercase;
  box-shadow: 0 2px 4px rgba(250, 112, 154, 0.2);
`;

import { filterToLabelsetId, userObj } from "../../../graphql/cache";
import {
  GetLabelsetOutputs,
  GetLabelsetInputs,
  GET_LABELSETS,
} from "../../../graphql/queries";
import { LabelSetType } from "../../../types/graphql-api";
import { useEffect } from "react";
import { LooseObject } from "../../types";
import useWindowDimensions from "../../hooks/WindowDimensionHook";
import { MOBILE_VIEW_BREAKPOINT } from "../../../assets/configurations/constants";

interface FilterToLabelsetSelectorProps {
  style?: Record<string, any>;
  fixed_labelset_id?: string;
}

export const FilterToLabelsetSelector = ({
  style,
  fixed_labelset_id,
}: FilterToLabelsetSelectorProps) => {
  const { width } = useWindowDimensions();
  const use_mobile_layout = width <= MOBILE_VIEW_BREAKPOINT;

  const filtered_to_labelset_id = useReactiveVar(filterToLabelsetId);
  const user_obj = useReactiveVar(userObj);

  let labelset_variables: LooseObject = {};
  if (fixed_labelset_id) {
    labelset_variables["labelsetId"] = fixed_labelset_id;
  }

  const { refetch, loading, data, error } = useQuery<
    GetLabelsetOutputs,
    GetLabelsetInputs
  >(GET_LABELSETS, {
    variables: labelset_variables,
    notifyOnNetworkStatusChange: true, // required to get loading signal on fetchMore
  });

  useEffect(() => {
    refetch();
  }, []);

  useEffect(() => {
    if (!fixed_labelset_id) {
      refetch();
    }
  }, [filtered_to_labelset_id]);

  useEffect(() => {
    refetch();
  }, [fixed_labelset_id]);

  useEffect(() => {
    refetch();
  }, [user_obj]);

  const labelset_edges = data?.labelsets?.edges ? data.labelsets.edges : [];
  const labelset_items = labelset_edges
    .map((edge) => (edge?.node ? edge.node : undefined))
    .filter((item): item is LabelSetType => !!item);

  let label_options: SelectOption[] = [];
  if (labelset_items) {
    label_options = labelset_items
      .filter((item): item is LabelSetType => !!item)
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
      <FilterLabel>Filter by Labelset</FilterLabel>
      <div style={{ position: "relative", zIndex: 10 }}>
        <Select
          isClearable
          isSearchable
          isLoading={loading}
          isDisabled={Boolean(fixed_labelset_id)}
          options={label_options}
          onChange={(
            selectedOption: SingleValue<SelectOption> | MultiValue<SelectOption>
          ) => {
            // This is a single select, so we know it's SingleValue
            const singleValue = selectedOption as SingleValue<SelectOption>;
            filterToLabelsetId(
              singleValue && !Array.isArray(singleValue)
                ? String(singleValue.value)
                : ""
            );
          }}
          placeholder="Select a labelset to filter..."
          value={
            fixed_labelset_id || filtered_to_labelset_id
              ? label_options.find(
                  (opt) =>
                    opt.value === (fixed_labelset_id || filtered_to_labelset_id)
                )
              : null
          }
          customStyles={{
            control: (base) => ({
              ...base,
              opacity: fixed_labelset_id ? 0.7 : 1,
            }),
          }}
        />
      </div>
    </div>
  );
};
