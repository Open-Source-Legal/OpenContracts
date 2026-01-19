import { useEffect } from "react";
import { useQuery, useReactiveVar } from "@apollo/client";
import { Header, Dropdown } from "semantic-ui-react";
import styled from "styled-components";
import _ from "lodash";
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

  /* Fix Issue #5: Mobile responsive styles */
  @media (max-width: 768px) {
    /* Ensure dropdown has adequate touch target size */
    .ui.dropdown {
      min-height: 44px; /* iOS minimum touch target */
      font-size: 16px; /* Prevents iOS zoom on focus */
    }

    /* Make header text readable on mobile */
    h5.ui.header {
      font-size: 1rem;
      padding: 0.75rem 1rem;
    }

    /* Ensure dropdown options are large enough to tap */
    .ui.dropdown .menu > .item {
      padding: 0.875rem 1rem !important;
      min-height: 44px;
    }
  }
`;

const AttachedContainer = styled.div`
  padding: 1rem;
  background: #fff;
  border: 1px solid rgba(34, 36, 38, 0.15);
  border-top: none;
  border-radius: 0 0 0.28571429rem 0.28571429rem;
  position: relative;
`;

interface LabelSetSelectorProps {
  read_only?: boolean;
  labelSet?: LabelSetType;
  style?: Record<string, any>;
  onChange?: (values: any) => void;
  /** Open dropdown upward (useful when near bottom of container) */
  upward?: boolean;
  /** Enable scrolling within the dropdown menu */
  scrolling?: boolean;
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
  scrolling = true,
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

  const handleChange = (_e: any, { value }: any) => {
    // If user has not actually changed the labelSet, do nothing:
    if (value === labelSet?.id) return;

    // If user explicitly clears, value === undefined => labelSet null
    // Otherwise labelSet is new value (the new labelSet.id).
    onChange?.({ labelSet: value ?? null });
  };

  let items = data?.labelsets?.edges ? data.labelsets.edges : [];
  let options = items.map((labelsetEdge, index) => {
    const node = labelsetEdge.node;
    return {
      key: node.id,
      text: node.title,
      value: node.id,
      content: (
        <Header
          key={index}
          image={node.icon}
          content={node.title}
          subheader={node.description}
        />
      ),
    };
  });

  return (
    <MobileFriendlyWrapper>
      <Header as="h5" attached="top">
        Label Set:
      </Header>
      <AttachedContainer>
        <LoadingOverlay active={loading} content="Loading Label Sets..." />
        <Dropdown
          disabled={read_only}
          selection
          clearable
          fluid
          upward={upward}
          scrolling={scrolling}
          options={options}
          style={{ ...style }}
          onChange={handleChange}
          placeholder="Choose a label set"
          value={labelSet?.id}
        />
      </AttachedContainer>
    </MobileFriendlyWrapper>
  );
};
