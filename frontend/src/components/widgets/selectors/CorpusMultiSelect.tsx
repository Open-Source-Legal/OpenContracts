import React, { useMemo, useState } from "react";
import { useQuery } from "@apollo/client";
import _ from "lodash";
import { MultiValue, SingleValue } from "react-select";

import Select, { SelectOption } from "../../common/Select";
import {
  GET_CORPUSES,
  GetCorpusesInputs,
  GetCorpusesOutputs,
} from "../../../graphql/queries";
import { DEBOUNCE } from "../../../assets/configurations/constants";

/**
 * Maximum number of corpuses requested per search. Keeps the menu responsive
 * on instances with very large corpus counts — the debounced server-side
 * ``textSearch`` is the mechanism for reaching anything beyond this window.
 */
const CORPUS_SEARCH_RESULT_LIMIT = 50;

/**
 * A single corpus as carried by this widget. Deliberately the full object
 * (id + title) rather than a bare id, so a consumer editing an existing record
 * can seed the chips from data it already has, without waiting on a search.
 */
export interface CorpusOption {
  id: string;
  title: string;
}

export interface CorpusMultiSelectProps {
  value: CorpusOption[];
  onChange: (next: CorpusOption[]) => void;
  disabled?: boolean;
  placeholder?: string;
  id?: string;
}

/**
 * Debounced, server-searched multi-select over corpuses.
 *
 * Controlled: the rendered chips are derived from the ``value`` prop, never
 * from the search results. Search results only ever populate the *menu*. That
 * split is what lets an edit form render its existing membership immediately
 * on mount (the seeded corpuses will typically not be in the first, unfiltered
 * page of results, and would otherwise silently disappear).
 */
export const CorpusMultiSelect: React.FC<CorpusMultiSelectProps> = ({
  value,
  onChange,
  disabled = false,
  placeholder = "Search corpuses...",
  id,
}) => {
  const [searchQuery, setSearchQuery] = useState<string>("");

  const { data, loading } = useQuery<GetCorpusesOutputs, GetCorpusesInputs>(
    GET_CORPUSES,
    {
      variables: {
        textSearch: searchQuery || undefined,
        limit: CORPUS_SEARCH_RESULT_LIMIT,
      },
      fetchPolicy: "cache-and-network",
    }
  );

  const debouncedSetSearchQuery = useMemo(
    () =>
      _.debounce((query: string) => {
        setSearchQuery(query);
      }, DEBOUNCE.CORPUS_SEARCH_MS),
    []
  );

  /**
   * Menu options: the search results verbatim. Already-selected corpuses are
   * not filtered out here — react-select's ``hideSelectedOptions`` (on by
   * default for ``isMulti``) does that by value-equality at render time.
   */
  const options: SelectOption[] = useMemo(() => {
    const edges = data?.corpuses?.edges ?? [];
    return edges
      .map((edge) => edge?.node)
      .filter((node): node is NonNullable<typeof node> => Boolean(node))
      .map((node) => ({
        value: node.id,
        label: node.title ?? "Untitled Corpus",
      }));
  }, [data]);

  /** Chips come from ``value`` alone — see the component docstring. */
  const selectedOptions: SelectOption[] = useMemo(
    () => value.map((corpus) => ({ value: corpus.id, label: corpus.title })),
    [value]
  );

  const handleChange = (
    next: SingleValue<SelectOption> | MultiValue<SelectOption>
  ) => {
    // isMulti guarantees MultiValue (an array) here; the union comes from the
    // shared Select wrapper being typed for both modes.
    const selected = Array.isArray(next)
      ? (next as readonly SelectOption[])
      : [];
    onChange(
      selected.map((option) => ({ id: option.value, title: option.label }))
    );
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
    // menu-close. Mirror that here — otherwise the visible box reads empty
    // while the menu stays filtered by the previous term, which looks like
    // missing results when reopening the dropdown to pick a second item.
    if (
      actionMeta.action === "set-value" ||
      actionMeta.action === "menu-close"
    ) {
      debouncedSetSearchQuery.cancel();
      setSearchQuery("");
    }
  };

  return (
    <div data-testid="corpus-multi-select">
      <Select
        inputId={id}
        isMulti
        isClearable
        isDisabled={disabled}
        isLoading={loading}
        placeholder={placeholder}
        options={options}
        // Search is server-side (``textSearch`` matches title OR description).
        // Disable react-select's client-side label filter, which would
        // otherwise drop results the server matched on description alone.
        filterOption={null}
        value={selectedOptions}
        onChange={handleChange}
        onInputChange={handleInputChange}
      />
    </div>
  );
};

export default CorpusMultiSelect;
