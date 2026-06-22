/**
 * Aliases & Relationships tab — the AuthorityKeyEquivalence registry (act-section
 * ↔ USC/CFR canonical-key bridges), absorbed from the standalone AuthorityMappings
 * panel into the console. Source chips + filter + search over the relay
 * connection, an inline create form, and per-row edit/delete for manual rows —
 * all via the shared KeyEquivalence editor primitives, so the detail's
 * Relationships section and this tab share one implementation.
 */
import React, { useMemo, useState } from "react";
import { useMutation, useQuery } from "@apollo/client";
import { Button } from "@os-legal/ui";
import { Search, X } from "lucide-react";
import { toast } from "react-toastify";

import {
  ErrorMessage,
  InfoMessage,
  LoadingState,
} from "../../widgets/feedback";
import { AUTHORITY_MAPPINGS_PAGE_SIZE } from "../../../assets/configurations/constants";
import {
  AuthorityKeyEquivalenceRow,
  GetAuthorityKeyEquivalencesInputs,
  GetAuthorityMappingStatsInputs,
  GetAuthorityMappingStatsOutputs,
  GET_AUTHORITY_KEY_EQUIVALENCES,
  GET_AUTHORITY_MAPPING_STATS,
} from "../../../graphql/queries";
import {
  CreateAuthorityKeyEquivalenceInputs,
  CreateAuthorityKeyEquivalenceOutputs,
  CREATE_AUTHORITY_KEY_EQUIVALENCE,
  DeleteAuthorityKeyEquivalenceInputs,
  DeleteAuthorityKeyEquivalenceOutputs,
  DELETE_AUTHORITY_KEY_EQUIVALENCE,
  UpdateAuthorityKeyEquivalenceInputs,
  UpdateAuthorityKeyEquivalenceOutputs,
  UPDATE_AUTHORITY_KEY_EQUIVALENCE,
} from "../../../graphql/mutations";
import { FacetedStatsChips } from "./shared/FacetedStatsChips";
import {
  FilterBar,
  LoadMoreRow,
  SearchBox,
  Select,
} from "./shared/consoleChrome";
import { SOURCE_ORDER, sourceLabel, sourceTone } from "./shared/tones";
import { useFacetedRelayList } from "./hooks/useFacetedRelayList";
import {
  KeyEquivalenceCreateForm,
  KeyEquivalenceTable,
} from "./shared/KeyEquivalenceEditor";

export const MappingsTab: React.FC = () => {
  const [search, setSearch] = useState("");
  const [source, setSource] = useState<string | null>(null);

  const statsVars: GetAuthorityMappingStatsInputs = useMemo(
    () => ({ search: search.trim() || null }),
    [search]
  );
  const statsQuery = useQuery<
    GetAuthorityMappingStatsOutputs,
    GetAuthorityMappingStatsInputs
  >(GET_AUTHORITY_MAPPING_STATS, {
    variables: statsVars,
    fetchPolicy: "network-only",
  });
  const stats = statsQuery.data?.authorityMappingStats;

  const listVars: GetAuthorityKeyEquivalencesInputs = useMemo(
    () => ({
      source: source || null,
      search: search.trim() || null,
      first: AUTHORITY_MAPPINGS_PAGE_SIZE,
      after: null,
    }),
    [source, search]
  );
  const list = useFacetedRelayList<
    AuthorityKeyEquivalenceRow,
    GetAuthorityKeyEquivalencesInputs
  >({
    query: GET_AUTHORITY_KEY_EQUIVALENCES,
    variables: listVars,
    connectionKey: "authorityKeyEquivalences",
  });

  const [createMapping, { loading: creating }] = useMutation<
    CreateAuthorityKeyEquivalenceOutputs,
    CreateAuthorityKeyEquivalenceInputs
  >(CREATE_AUTHORITY_KEY_EQUIVALENCE);
  const [updateMapping, { loading: updating }] = useMutation<
    UpdateAuthorityKeyEquivalenceOutputs,
    UpdateAuthorityKeyEquivalenceInputs
  >(UPDATE_AUTHORITY_KEY_EQUIVALENCE);
  const [deleteMapping, { loading: deleting }] = useMutation<
    DeleteAuthorityKeyEquivalenceOutputs,
    DeleteAuthorityKeyEquivalenceInputs
  >(DELETE_AUTHORITY_KEY_EQUIVALENCE);

  const refetchAll = () => {
    statsQuery.refetch();
    list.refetch();
  };

  const handleCreate = async (vals: {
    fromKey: string;
    toKey: string;
    note: string;
  }) => {
    try {
      const { data } = await createMapping({
        variables: { ...vals, note: vals.note || null },
      });
      const res = data?.createAuthorityKeyEquivalence;
      if (res?.ok) {
        toast.success(res.message ?? "Mapping created.");
        refetchAll();
      } else {
        toast.error(res?.message ?? "Could not create mapping.");
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Create failed.");
    }
  };

  const handleUpdate = async (
    id: string,
    vals: { fromKey: string; toKey: string; note: string }
  ) => {
    try {
      const { data } = await updateMapping({
        variables: { id, ...vals, note: vals.note || null },
      });
      const res = data?.updateAuthorityKeyEquivalence;
      if (res?.ok) {
        toast.success(res.message ?? "Mapping updated.");
        refetchAll();
      } else {
        toast.error(res?.message ?? "Could not update mapping.");
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Update failed.");
    }
  };

  const handleDelete = async (row: AuthorityKeyEquivalenceRow) => {
    if (
      !window.confirm(
        `Delete the mapping ${row.fromKey} → ${row.toKey}? This cannot be undone.`
      )
    ) {
      return;
    }
    try {
      const { data } = await deleteMapping({ variables: { id: row.id } });
      const res = data?.deleteAuthorityKeyEquivalence;
      if (res?.ok) {
        toast.success(res.message ?? "Mapping deleted.");
        refetchAll();
      } else {
        toast.error(res?.message ?? "Could not delete mapping.");
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Delete failed.");
    }
  };

  const busy = creating || updating || deleting;
  const loading = list.loading && list.rows.length === 0;
  const chips = (stats?.bySource ?? []).map((s) => ({
    value: s.source,
    count: s.count,
  }));

  return (
    <div data-testid="authority-mappings-tab">
      {stats ? (
        <FacetedStatsChips
          chips={chips}
          activeValue={source}
          onSelect={setSource}
          getTone={sourceTone}
          getLabel={sourceLabel}
          totalCount={stats.totalCount}
          testIdPrefix="mappings-source"
          hideEmptyValues={false}
        />
      ) : null}

      <FilterBar>
        <SearchBox>
          <Search className="lead" aria-hidden="true" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search from / to key…"
            aria-label="Search authority mappings"
            data-testid="mappings-search"
          />
          {search && (
            <button
              type="button"
              className="clear"
              onClick={() => setSearch("")}
              aria-label="Clear search"
            >
              <X />
            </button>
          )}
        </SearchBox>
        <Select
          value={source ?? ""}
          onChange={(e) => setSource(e.target.value || null)}
          aria-label="Filter by source"
          data-testid="mappings-filter-source"
        >
          <option value="">All sources</option>
          {SOURCE_ORDER.map((s) => (
            <option key={s} value={s}>
              {sourceLabel(s)}
            </option>
          ))}
        </Select>
      </FilterBar>

      <KeyEquivalenceCreateForm
        onCreate={handleCreate}
        creating={creating}
        testIdPrefix="mappings"
      />

      {loading ? (
        <LoadingState message="Loading authority mappings…" />
      ) : list.error ? (
        <ErrorMessage title="Error loading authority mappings">
          {list.error.message}
        </ErrorMessage>
      ) : list.rows.length === 0 ? (
        <InfoMessage title="No authority mappings">
          {source || search.trim()
            ? "No key equivalences match the current filters."
            : "No key equivalences have been loaded yet. Add a manual bridge above to map an act-section key onto its canonical USC/CFR key."}
        </InfoMessage>
      ) : (
        <>
          <KeyEquivalenceTable
            rows={list.rows}
            onUpdate={handleUpdate}
            onDelete={handleDelete}
            busy={busy}
            showProvenance
            testIdPrefix="mappings"
          />
          {list.hasNextPage && (
            <LoadMoreRow>
              <Button
                variant="secondary"
                onClick={list.loadMore}
                disabled={list.loading}
                data-testid="mappings-load-more"
              >
                {list.loading ? "Loading…" : "Load more"}
              </Button>
            </LoadMoreRow>
          )}
        </>
      )}
    </div>
  );
};
