import { useEffect } from "react";
import { useQuery, useReactiveVar } from "@apollo/client";
import { Dropdown } from "@os-legal/ui";
import styled from "styled-components";
import _ from "lodash";
import { OS_LEGAL_COLORS } from "../../../assets/configurations/osLegalStyles";
import { labelsetSearchTerm } from "../../../graphql/cache";
import { LoadingOverlay } from "../../common/LoadingOverlay";
import {
  GetLabelsetInputs,
  GetLabelsetOutputs,
  GET_LABELSETS,
} from "../../../graphql/queries";
import { LabelSetType } from "../../../types/graphql-api";

// Mobile-responsive wrapper for LabelSetSelector
const MobileFriendlyWrapper = styled.div`
  width: 100%;

  @media (max-width: 768px) {
    /* Add padding for better mobile spacing */
    > div:last-child {
      padding: 1rem;
    }
  }
`;

interface LabelSetSelectorProps {
  read_only?: boolean;
  labelSet?: LabelSetType;
  style?: Record<string, any>;
  onChange?: (values: {
    labelSet: string | null;
    labelSetObj?: LabelSetType;
  }) => void;
  /** Open dropdown upward (useful when near bottom of container) */
  upward?: boolean;
}

/**
 * If the user picks the same labelSet or hasn't changed it, we won't fire onChange.
 * If the user clears the dropdown, we explicitly set labelSet: null.
 */
export const LabelSetSelector = ({
  onChange,
  read_only,
  style,
  labelSet,
  upward = false,
}: LabelSetSelectorProps) => {
  const search_term = useReactiveVar(labelsetSearchTerm);
  const { refetch, loading, error, data, fetchMore } = useQuery<
    GetLabelsetOutputs,
    GetLabelsetInputs
  >(GET_LABELSETS, {
    variables: {
      description: search_term,
    },
    notifyOnNetworkStatusChange: true,
  });

  useEffect(() => {
    refetch();
  }, [search_term, refetch]);

  const items = data?.labelsets?.edges ?? [];

  const handleChange = (value: string | null) => {
    // If user has not actually changed the labelSet, do nothing:
    if (value === labelSet?.id) return;

    // If user explicitly clears, value === null => labelSet null
    // Otherwise labelSet is new value (the new labelSet.id).
    const selectedLabelSet = value
      ? items.find((edge) => edge.node.id === value)?.node
      : undefined;
    onChange?.({
      labelSet: value ?? null,
      labelSetObj: selectedLabelSet,
    });
  };

  const options = items.map((labelsetEdge) => {
    const node = labelsetEdge.node;
    return {
      value: node.id,
      label: node.title || "",
      description: node.description || undefined,
      icon: node.icon || undefined,
    };
  });

  return (
    <MobileFriendlyWrapper>
      <h5
        style={{
          margin: 0,
          padding: "0.75rem 1rem",
          background: OS_LEGAL_COLORS.gray50,
          border: "1px solid rgba(34,36,38,.15)",
          borderBottom: "none",
          borderRadius: "4px 4px 0 0",
          fontSize: "0.9rem",
          fontWeight: 600,
        }}
      >
        Label Set:
      </h5>
      <div
        style={{
          padding: "1rem",
          border: "1px solid rgba(34,36,38,.15)",
          borderRadius: "0 0 4px 4px",
          position: "relative",
        }}
      >
        <LoadingOverlay active={loading} content="Loading Label Sets..." />
        <Dropdown
          mode="select"
          disabled={read_only}
          clearable
          searchable="async"
          fluid
          upward={upward}
          options={options}
          style={{ ...style }}
          onChange={(value) => handleChange(value as string | null)}
          onSearchChange={(query) => labelsetSearchTerm(query)}
          loading={loading}
          placeholder="Choose a label set"
          value={labelSet?.id ?? null}
        />
      </div>
    </MobileFriendlyWrapper>
  );
};
