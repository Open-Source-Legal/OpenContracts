import React, { useCallback, useEffect, useState } from "react";
import { useQuery, useReactiveVar } from "@apollo/client";
import { Dropdown, DropdownOption } from "@os-legal/ui";
import {
  GET_CORPUSES,
  GetCorpusesInputs,
  GetCorpusesOutputs,
} from "../../../graphql/queries";
import { selectedCorpus } from "../../../graphql/cache";
import _ from "lodash";
import { CorpusType } from "../../../types/graphql-api";

/**
 * Props for the CorpusDropdown component.
 */
interface CorpusDropdownProps {
  /** Optional controlled value (corpus ID). */
  value?: string | null;
  /** Optional callback when the selection changes. If provided, the global state is not updated. */
  onChange?: (corpus: CorpusType | null) => void;
  /** Optional flag to allow clearing the selection. Defaults to true. */
  clearable?: boolean;
  /** Optional placeholder text. */
  placeholder?: string;
  /** Optional flag for fluid width. Defaults to true. */
  fluid?: boolean;
}

export const CorpusDropdown: React.FC<CorpusDropdownProps> = ({
  value,
  onChange,
  clearable = true,
  placeholder = "Select Corpus",
  fluid = true,
}) => {
  const [searchQuery, setSearchQuery] = useState<string>();
  // Use global selectedCorpus only if the component is not controlled
  const global_selected_corpus = useReactiveVar(selectedCorpus);

  const { loading, error, data, refetch } = useQuery<
    GetCorpusesOutputs,
    GetCorpusesInputs
  >(GET_CORPUSES, {
    variables: searchQuery
      ? {
          textSearch: searchQuery,
        }
      : {},
    fetchPolicy: "cache-and-network", // Ensure fresh data but use cache initially
  });

  // Refetch when search query changes
  useEffect(() => {
    // Debounce refetching on search query change if needed, but direct refetch is often fine here
    refetch({ textSearch: searchQuery });
  }, [searchQuery, refetch]);

  const corpuses = data?.corpuses.edges
    ? data.corpuses.edges
        .map((edge) => edge.node)
        .filter((c): c is CorpusType => !!c) // Ensure nodes are not null/undefined and type guard
    : [];

  const debouncedSetSearchQuery = useCallback(
    _.debounce((query: string) => {
      setSearchQuery(query);
    }, 300), // Slightly shorter debounce
    []
  );

  const handleSearchChange = (query: string) => {
    debouncedSetSearchQuery(query);
  };

  const handleSelectionChange = (value: string | string[] | null) => {
    // mode="select" always emits string | null, but the library types include string[]
    const id = Array.isArray(value) ? value[0] : value;
    const selected = id ? _.find(corpuses, { id }) : null;
    const resultCorpus = selected ? (selected as CorpusType) : null;

    // If onChange prop is provided, use it (controlled component behavior)
    if (onChange) {
      onChange(resultCorpus);
    } else {
      // Otherwise, update the global reactive variable (uncontrolled behavior)
      selectedCorpus(resultCorpus);
    }
  };

  const getDropdownOptions = (): DropdownOption[] => {
    return corpuses.map((node) => ({
      value: node.id,
      label: node.title ?? "Untitled Corpus", // Provide fallback for potentially null/undefined title
    }));
  };

  // Determine the value to display: controlled value first, then global state
  const displayValue =
    value !== undefined ? value : (global_selected_corpus?.id ?? null);

  if (error) {
    // Consider a more user-friendly error display, maybe a disabled dropdown with an error message
    console.error("Error loading corpuses:", error);
    return (
      <Dropdown
        mode="select"
        placeholder="Error loading corpuses"
        disabled
        options={[]}
      />
    );
  }

  return (
    <Dropdown
      mode="select"
      fluid={fluid}
      searchable="async"
      clearable={clearable}
      options={getDropdownOptions()}
      value={displayValue ?? null}
      placeholder={placeholder}
      onChange={handleSelectionChange}
      onSearchChange={handleSearchChange}
      loading={loading}
    />
  );
};
