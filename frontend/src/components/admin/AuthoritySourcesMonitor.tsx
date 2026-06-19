import React, { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useReactiveVar } from "@apollo/client";
import { useNavigate } from "react-router-dom";
import { Button, Table } from "@os-legal/ui";
import styled from "styled-components";
import { ArrowLeft, Play, RefreshCw, Scale, Search, X } from "lucide-react";
import { toast } from "react-toastify";

import {
  ErrorMessage,
  InfoMessage,
  LoadingState,
  WarningMessage,
} from "../widgets/feedback";
import { OS_LEGAL_COLORS } from "../../assets/configurations/osLegalStyles";
import {
  AUTHORITY_DISCOVERY_POLL_MS,
  AUTHORITY_DISCOVERY_POLL_WINDOW_MS,
  AUTHORITY_FRONTIER_PAGE_SIZE,
} from "../../assets/configurations/constants";
import { ScrollableTableWrapper } from "../layout/SharedSegments";
import { CORPUS_RADII } from "../corpuses/styles/corpusDesignTokens";
import { formatDateTime } from "../../utils/formatters";
import { backendUserObj } from "../../graphql/cache";
import {
  GET_AUTHORITY_FRONTIER,
  GET_AUTHORITY_FRONTIER_STATS,
  GetAuthorityFrontierInputs,
  GetAuthorityFrontierOutputs,
  GetAuthorityFrontierStatsInputs,
  GetAuthorityFrontierStatsOutputs,
  AuthorityFrontierRow,
} from "../../graphql/queries";
import {
  RUN_AUTHORITY_DISCOVERY,
  RunAuthorityDiscoveryInputs,
  RunAuthorityDiscoveryOutputs,
} from "../../graphql/mutations";

/**
 * AuthoritySourcesMonitor — global, read-only view of the AuthorityFrontier:
 * the instance-wide discovery/ingestion queue for cited law (one row per wanted
 * section-root key, aggregated across all corpora). Superuser-only.
 *
 * Two lenses over one table: clickable state-count chips (operational monitor —
 * what's queued / failed / blocked) and the default ``-mention_count`` order
 * (ingestion backlog — what's most-cited-but-not-ingested). Read-only:
 * triggering ingestion lives in the per-corpus /admin/enrichment runner.
 */

// ---- discovery_state display vocabulary -----------------------------------
type Tone = "info" | "success" | "warning" | "danger";
const STATE_ORDER = [
  "queued",
  "in_progress",
  "discovered",
  "pending_approval",
  "deferred_cap",
  "ingested",
  "resolved",
  "failed",
  "unsupported",
  "blocked_license",
  "unlocated",
];
const STATE_META: Record<string, { label: string; tone: Tone }> = {
  queued: { label: "Queued", tone: "info" },
  in_progress: { label: "In progress", tone: "info" },
  discovered: { label: "Discovered", tone: "info" },
  pending_approval: { label: "Pending approval", tone: "warning" },
  deferred_cap: { label: "Deferred (cap)", tone: "warning" },
  ingested: { label: "Ingested", tone: "success" },
  resolved: { label: "Resolved", tone: "success" },
  failed: { label: "Failed", tone: "danger" },
  unsupported: { label: "Unsupported", tone: "danger" },
  blocked_license: { label: "License-blocked", tone: "warning" },
  unlocated: { label: "Unlocated", tone: "warning" },
};
const stateLabel = (s: string): string => STATE_META[s]?.label ?? s;
const stateTone = (s: string): Tone => STATE_META[s]?.tone ?? "info";

const TONE_COLORS: Record<Tone, { fg: string; bg: string; border: string }> = {
  info: {
    fg: OS_LEGAL_COLORS.infoText,
    bg: OS_LEGAL_COLORS.infoSurface,
    border: OS_LEGAL_COLORS.infoBorder,
  },
  success: {
    fg: OS_LEGAL_COLORS.successText,
    bg: OS_LEGAL_COLORS.successSurface,
    border: OS_LEGAL_COLORS.successBorder,
  },
  warning: {
    fg: OS_LEGAL_COLORS.warningText,
    bg: OS_LEGAL_COLORS.warningSurface,
    border: OS_LEGAL_COLORS.warningBorder,
  },
  danger: {
    fg: OS_LEGAL_COLORS.dangerText,
    bg: OS_LEGAL_COLORS.dangerSurface,
    border: OS_LEGAL_COLORS.dangerBorder,
  },
};

/** "us-de" → "U.S. — DE"; "us-federal" → "U.S. Federal". */
function formatJurisdiction(j?: string | null): string {
  if (!j) return "—";
  if (j === "us-federal") return "U.S. Federal";
  const m = j.match(/^us-([a-z]{2})$/);
  if (m) return `U.S. — ${m[1].toUpperCase()}`;
  return j.toUpperCase();
}

const titleCase = (s?: string | null): string =>
  s ? s.charAt(0).toUpperCase() + s.slice(1).replace(/[_-]/g, " ") : "—";

// ---- styled shell (mirrors the Ingestion Monitor admin page) --------------
const Container = styled.div`
  max-width: 1200px;
  margin: 0 auto;
  padding: 2rem 1.5rem 3rem;
`;

const BackLink = styled.button`
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  border: none;
  background: none;
  padding: 0;
  margin-bottom: 1.25rem;
  font-size: 0.8125rem;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textSecondary};
  cursor: pointer;

  &:hover {
    color: ${OS_LEGAL_COLORS.primaryBlue};
  }
`;

const PageHeader = styled.div`
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
  margin-bottom: 1.25rem;
`;

const PageTitle = styled.h1`
  display: flex;
  align-items: center;
  gap: 0.6rem;
  margin: 0;
  font-size: 1.5rem;
  color: ${OS_LEGAL_COLORS.textPrimary};
`;

const PageSubtitle = styled.p`
  margin: 0.35rem 0 0;
  max-width: 46rem;
  font-size: 0.875rem;
  line-height: 1.5;
  color: ${OS_LEGAL_COLORS.textSecondary};
`;

const Chips = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-bottom: 1rem;
`;

const Chip = styled.button<{ $active: boolean; $tone: Tone }>`
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  padding: 0.34rem 0.7rem;
  border-radius: ${CORPUS_RADII.full};
  font-size: 0.78125rem;
  font-weight: 600;
  cursor: pointer;
  transition: filter 0.12s ease, box-shadow 0.12s ease;
  color: ${(p) => TONE_COLORS[p.$tone].fg};
  background: ${(p) => TONE_COLORS[p.$tone].bg};
  border: 1px solid
    ${(p) =>
      p.$active ? TONE_COLORS[p.$tone].fg : TONE_COLORS[p.$tone].border};
  box-shadow: ${(p) =>
    p.$active ? `inset 0 0 0 1px ${TONE_COLORS[p.$tone].fg}` : "none"};

  &:hover {
    filter: brightness(0.97);
  }

  .count {
    font-variant-numeric: tabular-nums;
    opacity: 0.85;
  }
`;

const AllChip = styled(Chip)`
  color: ${OS_LEGAL_COLORS.textSecondary};
  background: ${OS_LEGAL_COLORS.surfaceLight};
  border-color: ${(p) =>
    p.$active ? OS_LEGAL_COLORS.textSecondary : OS_LEGAL_COLORS.border};
  box-shadow: ${(p) =>
    p.$active ? `inset 0 0 0 1px ${OS_LEGAL_COLORS.textSecondary}` : "none"};
`;

const FilterBar = styled.div`
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.6rem;
  margin-bottom: 1rem;
`;

const SearchBox = styled.div`
  position: relative;
  display: flex;
  align-items: center;
  min-width: 220px;

  svg.lead {
    position: absolute;
    left: 0.55rem;
    width: 14px;
    height: 14px;
    color: ${OS_LEGAL_COLORS.textMuted};
    pointer-events: none;
  }

  input {
    width: 100%;
    padding: 0.45rem 1.6rem 0.45rem 1.8rem;
    font-size: 0.8125rem;
    color: ${OS_LEGAL_COLORS.textPrimary};
    background: ${OS_LEGAL_COLORS.surface};
    border: 1px solid ${OS_LEGAL_COLORS.border};
    border-radius: 8px;
    outline: none;

    &:focus {
      border-color: ${OS_LEGAL_COLORS.primaryBlue};
    }
  }

  button.clear {
    position: absolute;
    right: 0.4rem;
    display: inline-flex;
    border: none;
    background: none;
    color: ${OS_LEGAL_COLORS.textMuted};
    cursor: pointer;
    padding: 2px;

    &:hover {
      color: ${OS_LEGAL_COLORS.textSecondary};
    }

    svg {
      width: 13px;
      height: 13px;
    }
  }
`;

const Select = styled.select`
  padding: 0.45rem 0.6rem;
  font-size: 0.8125rem;
  color: ${OS_LEGAL_COLORS.textPrimary};
  background: ${OS_LEGAL_COLORS.surface};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 8px;
  cursor: pointer;

  &:focus {
    outline: none;
    border-color: ${OS_LEGAL_COLORS.primaryBlue};
  }
`;

const StateBadge = styled.span<{ $tone: Tone }>`
  display: inline-flex;
  align-items: center;
  padding: 0.1rem 0.5rem;
  border-radius: ${CORPUS_RADII.full};
  font-size: 0.71875rem;
  font-weight: 600;
  white-space: nowrap;
  color: ${(p) => TONE_COLORS[p.$tone].fg};
  background: ${(p) => TONE_COLORS[p.$tone].bg};
  border: 1px solid ${(p) => TONE_COLORS[p.$tone].border};
`;

const KeyCell = styled.span`
  font-family: "SFMono-Regular", "Menlo", "Consolas", monospace;
  font-size: 0.78125rem;
  color: ${OS_LEGAL_COLORS.textPrimary};
`;

const ErrorCell = styled.span`
  display: inline-block;
  max-width: 280px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: ${OS_LEGAL_COLORS.dangerText};
  font-size: 0.78125rem;
`;

const Muted = styled.span`
  color: ${OS_LEGAL_COLORS.textMuted};
`;

const LoadMoreRow = styled.div`
  display: flex;
  justify-content: center;
  padding: 1rem 0 0;
`;

const RowCheck = styled.input`
  cursor: pointer;
  width: 15px;
  height: 15px;
  accent-color: ${OS_LEGAL_COLORS.primaryBlue};
`;

const NoProviderTag = styled.span`
  font-size: 0.71875rem;
  color: ${OS_LEGAL_COLORS.dangerText};
`;

/** Sticky action bar shown when ≥1 frontier row is selected. */
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

const ActionInfo = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
`;

const ActionCount = styled.span`
  font-size: 0.875rem;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textPrimary};
`;

const ActionWarn = styled.span`
  font-size: 0.75rem;
  color: ${OS_LEGAL_COLORS.warningText};
`;

const ActionSpacer = styled.div`
  flex: 1;
`;

/** Trim the long registry suffix for compact display of a predicted provider. */
const shortProvider = (name: string): string =>
  name.replace(/AuthoritySourceProvider$/, "");

const FRONTIER_TABLE_MIN_WIDTH_PX = 980;

/** Distinct, sorted non-empty values of a row field — for the facet selects. */
function distinctValues(
  rows: AuthorityFrontierRow[],
  pick: (r: AuthorityFrontierRow) => string | null | undefined,
  alsoInclude?: string | null
): string[] {
  const set = new Set<string>();
  for (const r of rows) {
    const v = pick(r);
    if (v) set.add(v);
  }
  if (alsoInclude) set.add(alsoInclude);
  return [...set].sort();
}

export const AuthoritySourcesMonitor: React.FC = () => {
  const navigate = useNavigate();
  const currentUser = useReactiveVar(backendUserObj);
  const isSuperuser = currentUser?.isSuperuser === true;

  const [state, setState] = useState<string | null>(null);
  const [jurisdiction, setJurisdiction] = useState<string | null>(null);
  const [authorityType, setAuthorityType] = useState<string | null>(null);
  const [provider, setProvider] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  // The non-state facets shared by both queries (chips reflect these but NOT
  // the state filter, so they always show the full breakdown within facets).
  const facetVars: GetAuthorityFrontierStatsInputs = useMemo(
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
    variables: facetVars,
    skip: !isSuperuser,
    fetchPolicy: "network-only",
  });

  const frontierVars: GetAuthorityFrontierInputs = useMemo(
    () => ({
      ...facetVars,
      discoveryState: state || null,
      first: AUTHORITY_FRONTIER_PAGE_SIZE,
      after: null,
    }),
    [facetVars, state]
  );

  const frontierQuery = useQuery<
    GetAuthorityFrontierOutputs,
    GetAuthorityFrontierInputs
  >(GET_AUTHORITY_FRONTIER, {
    variables: frontierVars,
    skip: !isSuperuser,
    fetchPolicy: "network-only",
    notifyOnNetworkStatusChange: true,
  });

  const rows: AuthorityFrontierRow[] = useMemo(
    () =>
      (frontierQuery.data?.authorityFrontier?.edges ?? []).map((e) => e.node),
    [frontierQuery.data]
  );
  const pageInfo = frontierQuery.data?.authorityFrontier?.pageInfo;
  const stats = statsQuery.data?.authorityFrontierStats;

  // Facet options derived from the loaded rows (+ the current selection so a
  // server-narrowed page never drops the value you picked).
  const jurisdictionOptions = useMemo(
    () => distinctValues(rows, (r) => r.jurisdiction, jurisdiction),
    [rows, jurisdiction]
  );
  const typeOptions = useMemo(
    () => distinctValues(rows, (r) => r.authorityType, authorityType),
    [rows, authorityType]
  );
  const providerOptions = useMemo(
    () => distinctValues(rows, (r) => r.provider, provider),
    [rows, provider]
  );

  const chipStates = useMemo(() => {
    const byState = stats?.byState ?? [];
    const present = new Set(byState.map((s) => s.state));
    const counts = Object.fromEntries(byState.map((s) => [s.state, s.count]));
    return STATE_ORDER.filter((s) => present.has(s)).map((s) => ({
      state: s,
      count: counts[s] as number,
    }));
  }, [stats]);

  const handleRefresh = () => {
    statsQuery.refetch();
    frontierQuery.refetch();
  };

  const handleLoadMore = () => {
    if (!pageInfo?.hasNextPage) return;
    frontierQuery.fetchMore({
      variables: { ...frontierVars, after: pageInfo.endCursor },
      updateQuery: (prev, { fetchMoreResult }) => {
        if (!fetchMoreResult) return prev;
        return {
          authorityFrontier: {
            ...fetchMoreResult.authorityFrontier,
            edges: [
              ...prev.authorityFrontier.edges,
              ...fetchMoreResult.authorityFrontier.edges,
            ],
          },
        };
      },
    });
  };

  // --- subset discovery: selection + fire-and-forget trigger ---------------
  const [runDiscovery, { loading: running }] = useMutation<
    RunAuthorityDiscoveryOutputs,
    RunAuthorityDiscoveryInputs
  >(RUN_AUTHORITY_DISCOVERY);

  const pollTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Stop polling + clear the pause-timeout on unmount.
  useEffect(
    () => () => {
      if (pollTimeoutRef.current) clearTimeout(pollTimeoutRef.current);
      frontierQuery.stopPolling();
      statsQuery.stopPolling();
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    []
  );

  const toggleRow = (id: string) =>
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const allLoadedSelected =
    rows.length > 0 && rows.every((r) => selectedIds.has(r.id));

  const toggleAll = () =>
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (allLoadedSelected) rows.forEach((r) => next.delete(r.id));
      else rows.forEach((r) => next.add(r.id));
      return next;
    });

  // No-provider count among the loaded selected rows (drives the warning).
  const noProviderSelected = rows.filter(
    (r) => selectedIds.has(r.id) && r.ingestable === false
  ).length;

  // Poll both queries so rows + chips reflect state live while the run settles,
  // then pause after a bounded window (the background task keeps running).
  const startLiveUpdates = () => {
    frontierQuery.startPolling(AUTHORITY_DISCOVERY_POLL_MS);
    statsQuery.startPolling(AUTHORITY_DISCOVERY_POLL_MS);
    if (pollTimeoutRef.current) clearTimeout(pollTimeoutRef.current);
    pollTimeoutRef.current = setTimeout(() => {
      frontierQuery.stopPolling();
      statsQuery.stopPolling();
      pollTimeoutRef.current = null;
      toast.info("Live updates paused — hit Refresh for the latest state.");
    }, AUTHORITY_DISCOVERY_POLL_WINDOW_MS);
  };

  const handleRunSelected = async () => {
    const ids = [...selectedIds];
    if (ids.length === 0) return;
    try {
      const { data } = await runDiscovery({ variables: { frontierIds: ids } });
      const res = data?.runAuthorityDiscovery;
      if (res?.ok) {
        toast.success(
          res.message ?? `Discovery started for ${ids.length} authorities.`
        );
        setSelectedIds(new Set());
        startLiveUpdates();
      } else {
        toast.error(res?.message ?? "Could not start discovery.");
      }
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Could not start discovery."
      );
    }
  };

  // Null while the reactive var is still loading AND for anonymous users; wait
  // so the "Access Denied" warning never flashes for an admin mid-load (mirrors
  // IngestionMonitor).
  if (currentUser === null) {
    return null;
  }
  if (!isSuperuser) {
    return (
      <Container>
        <WarningMessage title="Access Denied">
          Only administrators can view the authority-sources monitor.
        </WarningMessage>
      </Container>
    );
  }

  const loading = frontierQuery.loading && rows.length === 0;

  return (
    <Container data-testid="authority-sources-monitor">
      <BackLink
        onClick={() => navigate("/admin/settings")}
        data-testid="authorities-back"
      >
        <ArrowLeft size={14} />
        Back to Admin Settings
      </BackLink>

      <PageHeader>
        <div>
          <PageTitle>
            <Scale size={26} color={OS_LEGAL_COLORS.folderIcon} />
            Authority Sources
          </PageTitle>
          <PageSubtitle>
            The global discovery queue for cited law: the crawl / ingestion
            state of every wanted statute &amp; regulation across all corpora,
            ranked by citation demand. Select rows and run discovery on them
            here, or trigger a full corpus crawl from the enrichment runner.
          </PageSubtitle>
        </div>
        <Button variant="secondary" onClick={handleRefresh}>
          <RefreshCw size={14} style={{ marginRight: 6 }} />
          Refresh
        </Button>
      </PageHeader>

      {/* State-count chips — the operational monitor entry point. */}
      <Chips data-testid="authorities-state-chips">
        <AllChip
          type="button"
          $active={state === null}
          $tone="info"
          onClick={() => setState(null)}
          data-testid="authorities-chip-all"
        >
          All
          {stats ? <span className="count">{stats.totalCount}</span> : null}
        </AllChip>
        {chipStates.map(({ state: s, count }) => (
          <Chip
            key={s}
            type="button"
            $active={state === s}
            $tone={stateTone(s)}
            onClick={() => setState(state === s ? null : s)}
            data-testid={`authorities-chip-${s}`}
          >
            {stateLabel(s)}
            <span className="count">{count}</span>
          </Chip>
        ))}
      </Chips>

      <FilterBar>
        <SearchBox>
          <Search className="lead" aria-hidden="true" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search key / authority…"
            aria-label="Search authority sources"
            data-testid="authorities-search"
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
          value={jurisdiction ?? ""}
          onChange={(e) => setJurisdiction(e.target.value || null)}
          aria-label="Filter by jurisdiction"
          data-testid="authorities-filter-jurisdiction"
        >
          <option value="">All jurisdictions</option>
          {jurisdictionOptions.map((j) => (
            <option key={j} value={j}>
              {formatJurisdiction(j)}
            </option>
          ))}
        </Select>
        <Select
          value={authorityType ?? ""}
          onChange={(e) => setAuthorityType(e.target.value || null)}
          aria-label="Filter by authority type"
          data-testid="authorities-filter-type"
        >
          <option value="">All types</option>
          {typeOptions.map((t) => (
            <option key={t} value={t}>
              {titleCase(t)}
            </option>
          ))}
        </Select>
        <Select
          value={provider ?? ""}
          onChange={(e) => setProvider(e.target.value || null)}
          aria-label="Filter by provider"
          data-testid="authorities-filter-provider"
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
        <LoadingState message="Loading authority sources…" />
      ) : frontierQuery.error ? (
        <ErrorMessage title="Error loading authority sources">
          {frontierQuery.error.message}
        </ErrorMessage>
      ) : rows.length === 0 ? (
        <InfoMessage title="No authority sources">
          {state || jurisdiction || authorityType || provider || search.trim()
            ? "No frontier entries match the current filters."
            : "No cited authorities have been queued for discovery yet. Map a corpus's reference web to seed the frontier."}
        </InfoMessage>
      ) : (
        <>
          <ScrollableTableWrapper
            $minWidth={`${FRONTIER_TABLE_MIN_WIDTH_PX}px`}
            data-testid="authorities-table-scroll"
          >
            <Table variant="minimal">
              <Table.Head>
                <Table.Row>
                  <Table.HeadCell>
                    <RowCheck
                      type="checkbox"
                      checked={allLoadedSelected}
                      onChange={toggleAll}
                      aria-label="Select all loaded rows"
                      data-testid="authorities-select-all"
                    />
                  </Table.HeadCell>
                  <Table.HeadCell>Key</Table.HeadCell>
                  <Table.HeadCell>State</Table.HeadCell>
                  <Table.HeadCell>Jurisdiction</Table.HeadCell>
                  <Table.HeadCell>Type</Table.HeadCell>
                  <Table.HeadCell>Provider</Table.HeadCell>
                  <Table.HeadCell>Cites</Table.HeadCell>
                  <Table.HeadCell>Corpora</Table.HeadCell>
                  <Table.HeadCell>Last attempt</Table.HeadCell>
                  <Table.HeadCell>Detail</Table.HeadCell>
                </Table.Row>
              </Table.Head>
              <Table.Body>
                {rows.map((r) => (
                  <Table.Row key={r.id} data-testid="authorities-row">
                    <Table.Cell>
                      <RowCheck
                        type="checkbox"
                        checked={selectedIds.has(r.id)}
                        onChange={() => toggleRow(r.id)}
                        aria-label={`Select ${r.canonicalKey}`}
                        data-testid="authorities-row-check"
                      />
                    </Table.Cell>
                    <Table.Cell>
                      <KeyCell>{r.canonicalKey}</KeyCell>
                    </Table.Cell>
                    <Table.Cell>
                      <StateBadge $tone={stateTone(r.discoveryState)}>
                        {stateLabel(r.discoveryState)}
                      </StateBadge>
                    </Table.Cell>
                    <Table.Cell>
                      {formatJurisdiction(r.jurisdiction)}
                    </Table.Cell>
                    <Table.Cell>{titleCase(r.authorityType)}</Table.Cell>
                    <Table.Cell>
                      {r.provider ? (
                        r.provider
                      ) : r.ingestable === false ? (
                        <NoProviderTag title="No source provider can handle this key">
                          no provider
                        </NoProviderTag>
                      ) : r.predictedProvider ? (
                        <Muted title={r.predictedProvider}>
                          {shortProvider(r.predictedProvider)}
                        </Muted>
                      ) : (
                        <Muted>—</Muted>
                      )}
                    </Table.Cell>
                    <Table.Cell>{r.mentionCount}</Table.Cell>
                    <Table.Cell>{r.distinctCorpusCount}</Table.Cell>
                    <Table.Cell>
                      {r.lastAttempt ? (
                        formatDateTime(r.lastAttempt)
                      ) : (
                        <Muted>never</Muted>
                      )}
                    </Table.Cell>
                    <Table.Cell>
                      {r.lastError ? (
                        <ErrorCell title={r.lastError}>{r.lastError}</ErrorCell>
                      ) : r.ingestedDocument ? (
                        <Muted title={r.ingestedDocument.title || ""}>
                          ✓ {r.ingestedDocument.title || "imported"}
                        </Muted>
                      ) : (
                        <Muted>—</Muted>
                      )}
                    </Table.Cell>
                  </Table.Row>
                ))}
              </Table.Body>
            </Table>
          </ScrollableTableWrapper>
          {pageInfo?.hasNextPage && (
            <LoadMoreRow>
              <Button
                variant="secondary"
                onClick={handleLoadMore}
                disabled={frontierQuery.loading}
                data-testid="authorities-load-more"
              >
                {frontierQuery.loading ? "Loading…" : "Load more"}
              </Button>
            </LoadMoreRow>
          )}

          {selectedIds.size > 0 && (
            <ActionBar data-testid="authorities-action-bar">
              <ActionInfo>
                <ActionCount data-testid="authorities-selected-count">
                  {selectedIds.size} selected
                </ActionCount>
                {noProviderSelected > 0 && (
                  <ActionWarn data-testid="authorities-noprovider-warning">
                    {noProviderSelected} of {selectedIds.size} have no provider
                    and will be recorded Unsupported.
                  </ActionWarn>
                )}
              </ActionInfo>
              <ActionSpacer />
              <Button
                variant="secondary"
                onClick={() => setSelectedIds(new Set())}
                data-testid="authorities-clear-selection"
              >
                Clear
              </Button>
              <Button
                variant="primary"
                onClick={handleRunSelected}
                disabled={running}
                data-testid="authorities-run-selected"
              >
                <Play size={14} style={{ marginRight: 6 }} />
                {running ? "Starting…" : "Run discovery"}
              </Button>
            </ActionBar>
          )}
        </>
      )}
    </Container>
  );
};

export default AuthoritySourcesMonitor;
