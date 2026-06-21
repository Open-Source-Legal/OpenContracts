/**
 * Discovery Queue tab — the instance-wide AuthorityFrontier crawl/ingestion
 * queue, absorbed from the standalone AuthoritySourcesMonitor into the console.
 * State chips + jurisdiction/type/provider facets + search over the relay
 * connection, multi-select "Run discovery", and NEW per-row admin verbs
 * (requeue / reset / reroute / approve / delete) wired to the
 * AuthorityFrontierService action mutations. Reuses the shared console chrome +
 * FacetedStatsChips + useFacetedRelayList.
 */
import React, { useMemo, useState } from "react";
import { useMutation, useQuery } from "@apollo/client";
import { Button, Table } from "@os-legal/ui";
import styled from "styled-components";
import {
  Check,
  Play,
  RefreshCw,
  RotateCcw,
  Search,
  Shuffle,
  Trash2,
  X,
} from "lucide-react";
import { toast } from "react-toastify";

import {
  ErrorMessage,
  InfoMessage,
  LoadingState,
} from "../../widgets/feedback";
import { ScrollableTableWrapper } from "../../layout/SharedSegments";
import { OS_LEGAL_COLORS } from "../../../assets/configurations/osLegalStyles";
import { AUTHORITY_FRONTIER_PAGE_SIZE } from "../../../assets/configurations/constants";
import {
  AuthorityFrontierRow,
  GetAuthorityFrontierInputs,
  GetAuthorityFrontierStatsInputs,
  GetAuthorityFrontierStatsOutputs,
  GET_AUTHORITY_FRONTIER,
  GET_AUTHORITY_FRONTIER_STATS,
} from "../../../graphql/queries";
import {
  ApproveAuthorityFrontierOutputs,
  APPROVE_AUTHORITY_FRONTIER,
  DeleteAuthorityFrontierInputs,
  DeleteAuthorityFrontierOutputs,
  DELETE_AUTHORITY_FRONTIER,
  RequeueAuthorityFrontierOutputs,
  REQUEUE_AUTHORITY_FRONTIER,
  RerouteAuthorityFrontierInputs,
  RerouteAuthorityFrontierOutputs,
  REROUTE_AUTHORITY_FRONTIER,
  ResetAuthorityFrontierOutputs,
  RESET_AUTHORITY_FRONTIER,
  RunAuthorityDiscoveryInputs,
  RunAuthorityDiscoveryOutputs,
  RUN_AUTHORITY_DISCOVERY,
} from "../../../graphql/mutations";
import { FacetedStatsChips } from "./shared/FacetedStatsChips";
import {
  Badge,
  FilterBar,
  IconButton,
  KeyCell,
  LoadMoreRow,
  Muted,
  RowActions,
  SearchBox,
  Select,
} from "./shared/consoleChrome";
import { humanizeCode, stateTone } from "./shared/tones";
import { useFacetedRelayList } from "./hooks/useFacetedRelayList";

const QUEUE_TABLE_MIN_WIDTH_PX = 1040;

const ActionBar = styled.div`
  position: sticky;
  bottom: 0;
  z-index: 2;
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-top: 1rem;
  padding: 0.75rem 1rem;
  background: ${OS_LEGAL_COLORS.surface};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 10px;
  box-shadow: 0 -2px 12px rgba(0, 0, 0, 0.06);
`;

const ActionCount = styled.span`
  font-size: 0.875rem;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textPrimary};
`;

export const DiscoveryQueueTab: React.FC = () => {
  const [search, setSearch] = useState("");
  const [discoveryState, setDiscoveryState] = useState<string | null>(null);
  const [jurisdiction, setJurisdiction] = useState<string | null>(null);
  const [authorityType, setAuthorityType] = useState<string | null>(null);
  const [provider, setProvider] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const statsVars: GetAuthorityFrontierStatsInputs = useMemo(
    () => ({
      jurisdiction: jurisdiction || null,
      authorityType: authorityType || null,
      provider: provider || null,
      search: search.trim() || null,
    }),
    [jurisdiction, authorityType, provider, search]
  );
  const statsQuery = useQuery<
    GetAuthorityFrontierStatsOutputs,
    GetAuthorityFrontierStatsInputs
  >(GET_AUTHORITY_FRONTIER_STATS, {
    variables: statsVars,
    fetchPolicy: "network-only",
  });
  const stats = statsQuery.data?.authorityFrontierStats;

  const listVars: GetAuthorityFrontierInputs = useMemo(
    () => ({
      discoveryState: discoveryState || null,
      jurisdiction: jurisdiction || null,
      authorityType: authorityType || null,
      provider: provider || null,
      search: search.trim() || null,
      first: AUTHORITY_FRONTIER_PAGE_SIZE,
      after: null,
    }),
    [discoveryState, jurisdiction, authorityType, provider, search]
  );
  const list = useFacetedRelayList<
    AuthorityFrontierRow,
    GetAuthorityFrontierInputs
  >({
    query: GET_AUTHORITY_FRONTIER,
    variables: listVars,
    connectionKey: "authorityFrontier",
  });

  const [runDiscovery, { loading: running }] = useMutation<
    RunAuthorityDiscoveryOutputs,
    RunAuthorityDiscoveryInputs
  >(RUN_AUTHORITY_DISCOVERY);
  const [requeue] = useMutation<RequeueAuthorityFrontierOutputs>(
    REQUEUE_AUTHORITY_FRONTIER
  );
  const [reset] = useMutation<ResetAuthorityFrontierOutputs>(
    RESET_AUTHORITY_FRONTIER
  );
  const [approve] = useMutation<ApproveAuthorityFrontierOutputs>(
    APPROVE_AUTHORITY_FRONTIER
  );
  const [reroute] = useMutation<
    RerouteAuthorityFrontierOutputs,
    RerouteAuthorityFrontierInputs
  >(REROUTE_AUTHORITY_FRONTIER);
  const [deleteRows] = useMutation<
    DeleteAuthorityFrontierOutputs,
    DeleteAuthorityFrontierInputs
  >(DELETE_AUTHORITY_FRONTIER);

  const refetchAll = () => {
    statsQuery.refetch();
    list.refetch();
  };

  const toggleRow = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const handleRunSelected = async () => {
    if (selected.size === 0) return;
    try {
      const { data } = await runDiscovery({
        variables: { frontierIds: [...selected] },
      });
      const res = data?.runAuthorityDiscovery;
      if (res?.ok) {
        toast.success(res.message ?? `Discovery started on ${selected.size}.`);
        setSelected(new Set());
        setTimeout(refetchAll, 1500);
      } else {
        toast.error(res?.message ?? "Could not start discovery.");
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Run failed.");
    }
  };

  // Generic single-row verb runner: call the mutation, toast its message, refetch.
  const runVerb = async (
    label: string,
    fn: () => Promise<{ ok?: boolean; message?: string | null } | undefined>
  ) => {
    try {
      const out = await fn();
      if (out?.ok) {
        toast.success(
          out.message && out.message !== "SUCCESS" ? out.message : label
        );
        refetchAll();
      } else {
        toast.error(out?.message ?? `Could not ${label.toLowerCase()}.`);
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Action failed.");
    }
  };

  const handleRequeue = (id: string) =>
    runVerb(
      "Requeued",
      async () =>
        (await requeue({ variables: { id } })).data?.requeueAuthorityFrontier
    );
  const handleReset = (id: string) =>
    runVerb(
      "Reset",
      async () =>
        (await reset({ variables: { id } })).data?.resetAuthorityFrontier
    );
  const handleApprove = (id: string) =>
    runVerb(
      "Approved",
      async () =>
        (await approve({ variables: { id } })).data?.approveAuthorityFrontier
    );
  const handleReroute = (id: string) => {
    const target = window.prompt(
      "Re-route to which provider? (registry class name, e.g. USCodeAuthoritySourceProvider)"
    );
    if (!target) return;
    runVerb(
      "Rerouted",
      async () =>
        (await reroute({ variables: { id, provider: target.trim() } })).data
          ?.rerouteAuthorityFrontier
    );
  };
  const handleDeleteOne = (row: AuthorityFrontierRow) => {
    if (!window.confirm(`Delete frontier row ${row.canonicalKey}?`)) return;
    runVerb(
      "Deleted",
      async () =>
        (await deleteRows({ variables: { ids: [row.id] } })).data
          ?.deleteAuthorityFrontier
    );
  };
  const handleDeleteSelected = () => {
    if (selected.size === 0) return;
    if (!window.confirm(`Delete ${selected.size} frontier row(s)?`)) return;
    runVerb("Deleted", async () => {
      const out = (await deleteRows({ variables: { ids: [...selected] } })).data
        ?.deleteAuthorityFrontier;
      setSelected(new Set());
      return out;
    });
  };

  const providerOptions = useMemo(() => {
    const set = new Set<string>();
    for (const r of list.rows) if (r.provider) set.add(r.provider);
    return [...set].sort();
  }, [list.rows]);

  const loading = list.loading && list.rows.length === 0;
  const chips = (stats?.byState ?? []).map((s) => ({
    value: s.state,
    count: s.count,
  }));

  return (
    <div data-testid="authority-queue-tab">
      {stats ? (
        <FacetedStatsChips
          chips={chips}
          activeValue={discoveryState}
          onSelect={setDiscoveryState}
          getTone={stateTone}
          getLabel={humanizeCode}
          totalCount={stats.totalCount}
          testIdPrefix="queue-state"
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
            placeholder="Search key / authority…"
            aria-label="Search discovery queue"
            data-testid="queue-search"
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
          value={provider ?? ""}
          onChange={(e) => setProvider(e.target.value || null)}
          aria-label="Filter by provider"
          data-testid="queue-filter-provider"
        >
          <option value="">All providers</option>
          {providerOptions.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </Select>
      </FilterBar>

      {loading ? (
        <LoadingState message="Loading discovery queue…" />
      ) : list.error ? (
        <ErrorMessage title="Error loading discovery queue">
          {list.error.message}
        </ErrorMessage>
      ) : list.rows.length === 0 ? (
        <InfoMessage title="No frontier rows">
          {discoveryState || provider || search.trim()
            ? "No queue rows match the current filters."
            : "The discovery queue is empty. Seed it by running enrichment/crawl on a corpus."}
        </InfoMessage>
      ) : (
        <>
          <ScrollableTableWrapper
            $minWidth={`${QUEUE_TABLE_MIN_WIDTH_PX}px`}
            data-testid="queue-table-scroll"
          >
            <Table variant="minimal">
              <Table.Head>
                <Table.Row>
                  <Table.HeadCell> </Table.HeadCell>
                  <Table.HeadCell>Key</Table.HeadCell>
                  <Table.HeadCell>State</Table.HeadCell>
                  <Table.HeadCell>Provider</Table.HeadCell>
                  <Table.HeadCell>Mentions</Table.HeadCell>
                  <Table.HeadCell>Last error</Table.HeadCell>
                  <Table.HeadCell>Actions</Table.HeadCell>
                </Table.Row>
              </Table.Head>
              <Table.Body>
                {list.rows.map((r) => (
                  <Table.Row key={r.id} data-testid="queue-row">
                    <Table.Cell>
                      <input
                        type="checkbox"
                        checked={selected.has(r.id)}
                        onChange={() => toggleRow(r.id)}
                        aria-label={`Select ${r.canonicalKey}`}
                        data-testid={`queue-select-${r.canonicalKey}`}
                      />
                    </Table.Cell>
                    <Table.Cell>
                      <KeyCell>{r.canonicalKey}</KeyCell>
                    </Table.Cell>
                    <Table.Cell>
                      <Badge $tone={stateTone(r.discoveryState)}>
                        {humanizeCode(r.discoveryState)}
                      </Badge>
                    </Table.Cell>
                    <Table.Cell>
                      {r.provider ? r.provider : <Muted>—</Muted>}
                    </Table.Cell>
                    <Table.Cell>{r.mentionCount}</Table.Cell>
                    <Table.Cell>
                      {r.lastError ? (
                        <Muted title={r.lastError}>
                          {r.lastError.slice(0, 40)}
                        </Muted>
                      ) : (
                        <Muted>—</Muted>
                      )}
                    </Table.Cell>
                    <Table.Cell>
                      <RowActions>
                        <IconButton
                          type="button"
                          onClick={() => handleRequeue(r.id)}
                          title="Requeue"
                          aria-label={`Requeue ${r.canonicalKey}`}
                          data-testid="queue-requeue"
                        >
                          <RotateCcw />
                        </IconButton>
                        <IconButton
                          type="button"
                          onClick={() => handleReset(r.id)}
                          title="Reset (clear provider + doc)"
                          aria-label={`Reset ${r.canonicalKey}`}
                          data-testid="queue-reset"
                        >
                          <RefreshCw />
                        </IconButton>
                        <IconButton
                          type="button"
                          onClick={() => handleReroute(r.id)}
                          title="Re-route provider"
                          aria-label={`Reroute ${r.canonicalKey}`}
                          data-testid="queue-reroute"
                        >
                          <Shuffle />
                        </IconButton>
                        {r.discoveryState === "pending_approval" && (
                          <IconButton
                            type="button"
                            onClick={() => handleApprove(r.id)}
                            title="Approve"
                            aria-label={`Approve ${r.canonicalKey}`}
                            data-testid="queue-approve"
                          >
                            <Check />
                          </IconButton>
                        )}
                        <IconButton
                          type="button"
                          $danger
                          onClick={() => handleDeleteOne(r)}
                          title="Delete"
                          aria-label={`Delete ${r.canonicalKey}`}
                          data-testid="queue-delete"
                        >
                          <Trash2 />
                        </IconButton>
                      </RowActions>
                    </Table.Cell>
                  </Table.Row>
                ))}
              </Table.Body>
            </Table>
          </ScrollableTableWrapper>

          {list.hasNextPage && (
            <LoadMoreRow>
              <Button
                variant="secondary"
                onClick={list.loadMore}
                disabled={list.loading}
                data-testid="queue-load-more"
              >
                {list.loading ? "Loading…" : "Load more"}
              </Button>
            </LoadMoreRow>
          )}
        </>
      )}

      {selected.size > 0 && (
        <ActionBar data-testid="queue-action-bar">
          <ActionCount data-testid="queue-selected-count">
            {selected.size} selected
          </ActionCount>
          <div style={{ flex: 1 }} />
          <Button
            variant="secondary"
            onClick={() => setSelected(new Set())}
            data-testid="queue-clear-selection"
          >
            Clear
          </Button>
          <Button
            variant="secondary"
            onClick={handleDeleteSelected}
            data-testid="queue-delete-selected"
          >
            <Trash2 size={14} style={{ marginRight: 6 }} />
            Delete
          </Button>
          <Button
            variant="primary"
            onClick={handleRunSelected}
            disabled={running}
            data-testid="queue-run-selected"
          >
            <Play size={14} style={{ marginRight: 6 }} />
            {running ? "Starting…" : "Run discovery"}
          </Button>
        </ActionBar>
      )}
    </div>
  );
};
