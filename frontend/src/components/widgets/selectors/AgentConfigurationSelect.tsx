import React, { useMemo, useState } from "react";
import { useQuery } from "@apollo/client";
import _ from "lodash";
import { MultiValue, SingleValue } from "react-select";

import Select, { SelectOption } from "../../common/Select";
import {
  GET_AGENT_CONFIGURATIONS,
  GetAgentConfigurationsInput,
  GetAgentConfigurationsOutput,
} from "../../../graphql/queries";
import { DEBOUNCE } from "../../../assets/configurations/constants";

/**
 * Maximum number of agent configurations requested per search. Mirrors the
 * limit the corpus-action modal has always used for this query.
 */
const AGENT_SEARCH_RESULT_LIMIT = 50;

/**
 * A single agent configuration as carried by this widget. Full object
 * (id + name) rather than a bare id, so an edit form can seed the selection
 * from data it already has, without waiting on a search.
 */
export interface AgentOption {
  id: string;
  name: string;
}

export interface AgentConfigurationSelectProps {
  value: AgentOption | null;
  onChange: (next: AgentOption | null) => void;
  disabled?: boolean;
  placeholder?: string;
  id?: string;
}

/**
 * Debounced, server-searched single-select over active agent configurations.
 *
 * Controlled and clearable: clearing emits ``onChange(null)``, which consumers
 * translate into whatever "unbind the agent" looks like for their mutation.
 *
 * As with ``CorpusMultiSelect``, the rendered selection is derived from the
 * ``value`` prop and never from the search results, so a seeded agent shows up
 * immediately on mount even though it may not appear in the first page of
 * unfiltered results.
 */
export const AgentConfigurationSelect: React.FC<
  AgentConfigurationSelectProps
> = ({
  value,
  onChange,
  disabled = false,
  placeholder = "Search agents...",
  id,
}) => {
  const [searchQuery, setSearchQuery] = useState<string>("");

  const { data, loading } = useQuery<
    GetAgentConfigurationsOutput,
    GetAgentConfigurationsInput
  >(GET_AGENT_CONFIGURATIONS, {
    variables: {
      isActive: true,
      name_Contains: searchQuery || undefined,
      first: AGENT_SEARCH_RESULT_LIMIT,
    },
    fetchPolicy: "cache-and-network",
  });

  const debouncedSetSearchQuery = useMemo(
    () =>
      _.debounce((query: string) => {
        setSearchQuery(query);
      }, DEBOUNCE.CORPUS_SEARCH_MS),
    []
  );

  /** Menu options: search results only. */
  const options: SelectOption[] = useMemo(() => {
    const edges = data?.agentConfigurations?.edges ?? [];
    return edges.map((edge) => ({
      value: edge.node.id,
      label: edge.node.name,
    }));
  }, [data]);

  /** Selected value comes from ``value`` alone — see the component docstring. */
  const selectedOption: SelectOption | null = useMemo(
    () => (value ? { value: value.id, label: value.name } : null),
    [value]
  );

  const handleChange = (
    next: SingleValue<SelectOption> | MultiValue<SelectOption>
  ) => {
    // Single-select, so react-select emits SingleValue; the union comes from
    // the shared Select wrapper being typed for both modes.
    const option = Array.isArray(next)
      ? (next as readonly SelectOption[])[0] ?? null
      : (next as SelectOption | null);
    onChange(option ? { id: option.value, name: option.label } : null);
  };

  const handleInputChange = (
    input: string,
    actionMeta: { action: string }
  ): void => {
    if (actionMeta.action === "input-change") {
      debouncedSetSearchQuery(input);
      return;
    }
    // react-select clears its own (uncontrolled) input on set-value and
    // menu-close; mirror that so the menu is never filtered by a term the
    // user can no longer see. See CorpusMultiSelect for the same handling.
    if (
      actionMeta.action === "set-value" ||
      actionMeta.action === "menu-close"
    ) {
      debouncedSetSearchQuery.cancel();
      setSearchQuery("");
    }
  };

  return (
    <div data-testid="agent-configuration-select">
      <Select
        inputId={id}
        isClearable
        isDisabled={disabled}
        isLoading={loading}
        placeholder={placeholder}
        options={options}
        // Search is server-side via ``name_Contains``; react-select's
        // client-side label filter would only second-guess the server.
        filterOption={null}
        value={selectedOption}
        onChange={handleChange}
        onInputChange={handleInputChange}
      />
    </div>
  );
};

export default AgentConfigurationSelect;
