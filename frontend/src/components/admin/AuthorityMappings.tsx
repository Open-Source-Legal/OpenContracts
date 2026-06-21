import React, { useMemo, useState } from "react";
import { useMutation, useQuery, useReactiveVar } from "@apollo/client";
import { useNavigate } from "react-router-dom";
import { Button, Table } from "@os-legal/ui";
import styled from "styled-components";
import {
  ArrowLeft,
  Check,
  GitBranch,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  Trash2,
  X,
} from "lucide-react";
import { toast } from "react-toastify";

import {
  ErrorMessage,
  InfoMessage,
  LoadingState,
  WarningMessage,
} from "../widgets/feedback";
import { OS_LEGAL_COLORS } from "../../assets/configurations/osLegalStyles";
import { AUTHORITY_MAPPINGS_PAGE_SIZE } from "../../assets/configurations/constants";
import { ScrollableTableWrapper } from "../layout/SharedSegments";
import { CORPUS_RADII } from "../corpuses/styles/corpusDesignTokens";
import { formatDateTime } from "../../utils/formatters";
import { backendUserObj } from "../../graphql/cache";
import {
  GET_AUTHORITY_KEY_EQUIVALENCES,
  GET_AUTHORITY_MAPPING_STATS,
  GetAuthorityKeyEquivalencesInputs,
  GetAuthorityKeyEquivalencesOutputs,
  GetAuthorityMappingStatsInputs,
  GetAuthorityMappingStatsOutputs,
  AuthorityKeyEquivalenceRow,
} from "../../graphql/queries";
import {
  CREATE_AUTHORITY_KEY_EQUIVALENCE,
  CreateAuthorityKeyEquivalenceInputs,
  CreateAuthorityKeyEquivalenceOutputs,
  DELETE_AUTHORITY_KEY_EQUIVALENCE,
  DeleteAuthorityKeyEquivalenceInputs,
  DeleteAuthorityKeyEquivalenceOutputs,
  UPDATE_AUTHORITY_KEY_EQUIVALENCE,
  UpdateAuthorityKeyEquivalenceInputs,
  UpdateAuthorityKeyEquivalenceOutputs,
} from "../../graphql/mutations";

/**
 * AuthorityMappings — global, superuser-only view of the authority
 * key-equivalence table: the act-section ↔ USC/CFR canonical-key bridges that
 * let the reference web resolve a popular-name / USLM citation onto the
 * canonical key its provider can ingest. Mirrors AuthoritySourcesMonitor.
 *
 * Two lenses over one table: clickable per-``source`` count chips (baseline /
 * popular_name / uslm / manual) and the connection itself. Unlike the
 * read-only sources monitor this panel is editable — but only for ``manual``
 * rows: an inline create form seeds new bridges and each manual row exposes
 * inline edit + delete. The bundled mappings (baseline/popular_name/uslm) are
 * shown read-only.
 */

// ---- source display vocabulary --------------------------------------------
type Tone = "info" | "success" | "warning" | "neutral";
const SOURCE_ORDER = ["manual", "popular_name", "uslm", "baseline"];
const SOURCE_META: Record<string, { label: string; tone: Tone }> = {
  manual: { label: "Manual", tone: "success" },
  popular_name: { label: "Popular name", tone: "info" },
  uslm: { label: "USLM", tone: "info" },
  baseline: { label: "Baseline", tone: "neutral" },
};
const sourceLabel = (s: string): string => SOURCE_META[s]?.label ?? s;
const sourceTone = (s: string): Tone => SOURCE_META[s]?.tone ?? "neutral";

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
  neutral: {
    fg: OS_LEGAL_COLORS.textSecondary,
    bg: OS_LEGAL_COLORS.surfaceLight,
    border: OS_LEGAL_COLORS.border,
  },
};

// ---- styled shell (mirrors AuthoritySourcesMonitor) -----------------------
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

const SourceBadge = styled.span<{ $tone: Tone }>`
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

const NoteCell = styled.span`
  display: inline-block;
  max-width: 280px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.78125rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
`;

const Muted = styled.span`
  color: ${OS_LEGAL_COLORS.textMuted};
`;

const LoadMoreRow = styled.div`
  display: flex;
  justify-content: center;
  padding: 1rem 0 0;
`;

const RowActions = styled.div`
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
`;

const IconButton = styled.button<{ $danger?: boolean }>`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  background: ${OS_LEGAL_COLORS.surface};
  border-radius: 6px;
  padding: 0.28rem;
  cursor: pointer;
  color: ${(p) =>
    p.$danger ? OS_LEGAL_COLORS.dangerText : OS_LEGAL_COLORS.textSecondary};
  transition: background 0.12s ease, border-color 0.12s ease;

  &:hover {
    background: ${OS_LEGAL_COLORS.surfaceLight};
    border-color: ${(p) =>
      p.$danger ? OS_LEGAL_COLORS.dangerBorder : OS_LEGAL_COLORS.borderHover};
  }

  &:disabled {
    opacity: 0.5;
    cursor: default;
  }

  svg {
    width: 14px;
    height: 14px;
  }
`;

/** Compact key input used both inline (edit row) and in the create form. */
const KeyInput = styled.input`
  width: 100%;
  min-width: 120px;
  padding: 0.35rem 0.5rem;
  font-family: "SFMono-Regular", "Menlo", "Consolas", monospace;
  font-size: 0.78125rem;
  color: ${OS_LEGAL_COLORS.textPrimary};
  background: ${OS_LEGAL_COLORS.surface};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 6px;
  outline: none;

  &:focus {
    border-color: ${OS_LEGAL_COLORS.primaryBlue};
  }
`;

const NoteInput = styled.input`
  width: 100%;
  min-width: 140px;
  padding: 0.35rem 0.5rem;
  font-size: 0.78125rem;
  color: ${OS_LEGAL_COLORS.textPrimary};
  background: ${OS_LEGAL_COLORS.surface};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 6px;
  outline: none;

  &:focus {
    border-color: ${OS_LEGAL_COLORS.primaryBlue};
  }
`;

/** Inline "add a manual mapping" form rendered above the table. */
const CreateForm = styled.form`
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.6rem;
  margin-bottom: 1rem;
  padding: 0.85rem 1rem;
  background: ${OS_LEGAL_COLORS.surface};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 10px;
`;

const CreateField = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  flex: 1 1 160px;

  label {
    font-size: 0.6875rem;
    font-weight: 600;
    letter-spacing: 0.02em;
    text-transform: uppercase;
    color: ${OS_LEGAL_COLORS.textMuted};
  }
`;

const MAPPINGS_TABLE_MIN_WIDTH_PX = 860;

/** Distinct sources present in the loaded rows (+ current selection) — used so
 * a server-narrowed page never drops the source you filtered on. */
function presentSources(
  rows: AuthorityKeyEquivalenceRow[],
  alsoInclude?: string | null
): string[] {
  const set = new Set<string>();
  for (const r of rows) if (r.source) set.add(r.source);
  if (alsoInclude) set.add(alsoInclude);
  // Keep the canonical SOURCE_ORDER, then any stragglers alphabetically.
  const ordered = SOURCE_ORDER.filter((s) => set.has(s));
  const extra = [...set].filter((s) => !SOURCE_ORDER.includes(s)).sort();
  return [...ordered, ...extra];
}

export const AuthorityMappings: React.FC = () => {
  const navigate = useNavigate();
  const currentUser = useReactiveVar(backendUserObj);
  const isSuperuser = currentUser?.isSuperuser === true;

  const [source, setSource] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  // Inline create-form fields.
  const [newFromKey, setNewFromKey] = useState("");
  const [newToKey, setNewToKey] = useState("");
  const [newNote, setNewNote] = useState("");

  // Inline edit state (the row currently being edited + its draft fields).
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editFromKey, setEditFromKey] = useState("");
  const [editToKey, setEditToKey] = useState("");
  const [editNote, setEditNote] = useState("");

  // The non-source facet shared by both queries: the stats query omits the
  // source filter (so chips always show the full per-source breakdown), while
  // the connection query layers the source filter on top.
  const statsVars: GetAuthorityMappingStatsInputs = useMemo(
    () => ({ search: search.trim() || null }),
    [search]
  );

  const statsQuery = useQuery<
    GetAuthorityMappingStatsOutputs,
    GetAuthorityMappingStatsInputs
  >(GET_AUTHORITY_MAPPING_STATS, {
    variables: statsVars,
    skip: !isSuperuser,
    fetchPolicy: "network-only",
  });

  const listVars: GetAuthorityKeyEquivalencesInputs = useMemo(
    () => ({
      source: source || null,
      search: search.trim() || null,
      first: AUTHORITY_MAPPINGS_PAGE_SIZE,
      after: null,
    }),
    [source, search]
  );

  const listQuery = useQuery<
    GetAuthorityKeyEquivalencesOutputs,
    GetAuthorityKeyEquivalencesInputs
  >(GET_AUTHORITY_KEY_EQUIVALENCES, {
    variables: listVars,
    skip: !isSuperuser,
    fetchPolicy: "network-only",
    notifyOnNetworkStatusChange: true,
  });

  const rows: AuthorityKeyEquivalenceRow[] = useMemo(
    () =>
      (listQuery.data?.authorityKeyEquivalences?.edges ?? []).map(
        (e) => e.node
      ),
    [listQuery.data]
  );
  const pageInfo = listQuery.data?.authorityKeyEquivalences?.pageInfo;
  const stats = statsQuery.data?.authorityMappingStats;

  const chipSources = useMemo(() => {
    const bySource = stats?.bySource ?? [];
    const present = new Set(bySource.map((s) => s.source));
    const counts = Object.fromEntries(bySource.map((s) => [s.source, s.count]));
    const ordered = SOURCE_ORDER.filter((s) => present.has(s));
    const extra = bySource
      .map((s) => s.source)
      .filter((s) => !SOURCE_ORDER.includes(s));
    return [...ordered, ...extra].map((s) => ({
      source: s,
      count: counts[s] as number,
    }));
  }, [stats]);

  const sourceOptions = useMemo(
    () => presentSources(rows, source),
    [rows, source]
  );

  // After any successful mutation, refetch the connection + the chips.
  const refetchAll = () => {
    statsQuery.refetch();
    listQuery.refetch();
  };

  const handleRefresh = () => {
    refetchAll();
  };

  const handleLoadMore = () => {
    if (!pageInfo?.hasNextPage) return;
    listQuery.fetchMore({
      variables: { ...listVars, after: pageInfo.endCursor },
      updateQuery: (prev, { fetchMoreResult }) => {
        if (!fetchMoreResult) return prev;
        return {
          authorityKeyEquivalences: {
            ...fetchMoreResult.authorityKeyEquivalences,
            edges: [
              ...prev.authorityKeyEquivalences.edges,
              ...fetchMoreResult.authorityKeyEquivalences.edges,
            ],
          },
        };
      },
    });
  };

  // --- create / update / delete -------------------------------------------
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

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    const fromKey = newFromKey.trim();
    const toKey = newToKey.trim();
    if (!fromKey || !toKey) return;
    try {
      const { data } = await createMapping({
        variables: { fromKey, toKey, note: newNote.trim() || null },
      });
      const res = data?.createAuthorityKeyEquivalence;
      if (res?.ok) {
        toast.success(res.message ?? "Mapping created.");
        setNewFromKey("");
        setNewToKey("");
        setNewNote("");
        refetchAll();
      } else {
        toast.error(res?.message ?? "Could not create mapping.");
      }
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Could not create mapping."
      );
    }
  };

  const startEdit = (r: AuthorityKeyEquivalenceRow) => {
    setEditingId(r.id);
    setEditFromKey(r.fromKey);
    setEditToKey(r.toKey);
    setEditNote(r.note ?? "");
  };

  const cancelEdit = () => {
    setEditingId(null);
    setEditFromKey("");
    setEditToKey("");
    setEditNote("");
  };

  const handleUpdate = async (id: string) => {
    const fromKey = editFromKey.trim();
    const toKey = editToKey.trim();
    if (!fromKey || !toKey) return;
    try {
      const { data } = await updateMapping({
        variables: { id, fromKey, toKey, note: editNote.trim() || null },
      });
      const res = data?.updateAuthorityKeyEquivalence;
      if (res?.ok) {
        toast.success(res.message ?? "Mapping updated.");
        cancelEdit();
        refetchAll();
      } else {
        toast.error(res?.message ?? "Could not update mapping.");
      }
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Could not update mapping."
      );
    }
  };

  const handleDelete = async (r: AuthorityKeyEquivalenceRow) => {
    if (
      !window.confirm(
        `Delete the mapping ${r.fromKey} → ${r.toKey}? This cannot be undone.`
      )
    ) {
      return;
    }
    try {
      const { data } = await deleteMapping({ variables: { id: r.id } });
      const res = data?.deleteAuthorityKeyEquivalence;
      if (res?.ok) {
        toast.success(res.message ?? "Mapping deleted.");
        if (editingId === r.id) cancelEdit();
        refetchAll();
      } else {
        toast.error(res?.message ?? "Could not delete mapping.");
      }
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Could not delete mapping."
      );
    }
  };

  const mutating = creating || updating || deleting;

  // Null while the reactive var is still loading AND for anonymous users; wait
  // so the "Access Denied" warning never flashes for an admin mid-load (mirrors
  // AuthoritySourcesMonitor).
  if (currentUser === null) {
    return null;
  }
  if (!isSuperuser) {
    return (
      <Container>
        <WarningMessage title="Access Denied">
          Only administrators can view the authority mappings.
        </WarningMessage>
      </Container>
    );
  }

  const loading = listQuery.loading && rows.length === 0;

  return (
    <Container data-testid="authority-mappings-panel">
      <BackLink
        onClick={() => navigate("/admin/settings")}
        data-testid="mappings-back"
      >
        <ArrowLeft size={14} />
        Back to Admin Settings
      </BackLink>

      <PageHeader>
        <div>
          <PageTitle>
            <GitBranch size={26} color={OS_LEGAL_COLORS.folderIcon} />
            Authority Mappings
          </PageTitle>
          <PageSubtitle>
            The act-section ↔ USC/CFR canonical-key equivalences that bridge
            citations across namespaces, so the reference web can resolve a
            popular-name or USLM citation onto the canonical key its provider
            ingests. Bundled mappings are read-only; add your own manual bridges
            below.
          </PageSubtitle>
        </div>
        <Button variant="secondary" onClick={handleRefresh}>
          <RefreshCw size={14} style={{ marginRight: 6 }} />
          Refresh
        </Button>
      </PageHeader>

      {/* Per-source count chips — full breakdown within the current search. */}
      <Chips data-testid="mappings-source-chips">
        <AllChip
          type="button"
          $active={source === null}
          $tone="neutral"
          onClick={() => setSource(null)}
          data-testid="mappings-chip-all"
        >
          All
          {stats ? <span className="count">{stats.totalCount}</span> : null}
        </AllChip>
        {chipSources.map(({ source: s, count }) => (
          <Chip
            key={s}
            type="button"
            $active={source === s}
            $tone={sourceTone(s)}
            onClick={() => setSource(source === s ? null : s)}
            data-testid={`mappings-chip-${s}`}
          >
            {sourceLabel(s)}
            <span className="count">{count}</span>
          </Chip>
        ))}
      </Chips>

      {/* Inline create form — seeds a new manual bridge. */}
      <CreateForm onSubmit={handleCreate} data-testid="mappings-create-form">
        <CreateField>
          <label htmlFor="mappings-new-from">From key</label>
          <KeyInput
            id="mappings-new-from"
            value={newFromKey}
            onChange={(e) => setNewFromKey(e.target.value)}
            placeholder="e.g. securities-act:5"
            data-testid="mappings-new-from"
          />
        </CreateField>
        <CreateField>
          <label htmlFor="mappings-new-to">To key (canonical)</label>
          <KeyInput
            id="mappings-new-to"
            value={newToKey}
            onChange={(e) => setNewToKey(e.target.value)}
            placeholder="e.g. usc-15:77e"
            data-testid="mappings-new-to"
          />
        </CreateField>
        <CreateField style={{ flex: "2 1 220px" }}>
          <label htmlFor="mappings-new-note">Note (optional)</label>
          <NoteInput
            id="mappings-new-note"
            value={newNote}
            onChange={(e) => setNewNote(e.target.value)}
            placeholder="Why this bridge exists"
            data-testid="mappings-new-note"
          />
        </CreateField>
        <Button
          variant="primary"
          type="submit"
          disabled={creating || !newFromKey.trim() || !newToKey.trim()}
          data-testid="mappings-create-submit"
        >
          <Plus size={14} style={{ marginRight: 6 }} />
          {creating ? "Adding…" : "Add mapping"}
        </Button>
      </CreateForm>

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
          {sourceOptions.map((s) => (
            <option key={s} value={s}>
              {sourceLabel(s)}
            </option>
          ))}
        </Select>
      </FilterBar>

      {loading ? (
        <LoadingState message="Loading authority mappings…" />
      ) : listQuery.error ? (
        <ErrorMessage title="Error loading authority mappings">
          {listQuery.error.message}
        </ErrorMessage>
      ) : rows.length === 0 ? (
        <InfoMessage title="No authority mappings">
          {source || search.trim()
            ? "No key equivalences match the current filters."
            : "No key equivalences have been loaded yet. Add a manual bridge above to map an act-section key onto its canonical USC/CFR key."}
        </InfoMessage>
      ) : (
        <>
          <ScrollableTableWrapper
            $minWidth={`${MAPPINGS_TABLE_MIN_WIDTH_PX}px`}
            data-testid="mappings-table-scroll"
          >
            <Table variant="minimal">
              <Table.Head>
                <Table.Row>
                  <Table.HeadCell>From key</Table.HeadCell>
                  <Table.HeadCell>To key</Table.HeadCell>
                  <Table.HeadCell>Source</Table.HeadCell>
                  <Table.HeadCell>Note</Table.HeadCell>
                  <Table.HeadCell>Added by</Table.HeadCell>
                  <Table.HeadCell>Modified</Table.HeadCell>
                  <Table.HeadCell>Actions</Table.HeadCell>
                </Table.Row>
              </Table.Head>
              <Table.Body>
                {rows.map((r) => {
                  const isEditing = editingId === r.id;
                  return (
                    <Table.Row key={r.id} data-testid="mappings-row">
                      <Table.Cell>
                        {isEditing ? (
                          <KeyInput
                            value={editFromKey}
                            onChange={(e) => setEditFromKey(e.target.value)}
                            aria-label="Edit from key"
                            data-testid="mappings-edit-from"
                          />
                        ) : (
                          <KeyCell>{r.fromKey}</KeyCell>
                        )}
                      </Table.Cell>
                      <Table.Cell>
                        {isEditing ? (
                          <KeyInput
                            value={editToKey}
                            onChange={(e) => setEditToKey(e.target.value)}
                            aria-label="Edit to key"
                            data-testid="mappings-edit-to"
                          />
                        ) : (
                          <KeyCell>{r.toKey}</KeyCell>
                        )}
                      </Table.Cell>
                      <Table.Cell>
                        <SourceBadge $tone={sourceTone(r.source)}>
                          {sourceLabel(r.source)}
                        </SourceBadge>
                      </Table.Cell>
                      <Table.Cell>
                        {isEditing ? (
                          <NoteInput
                            value={editNote}
                            onChange={(e) => setEditNote(e.target.value)}
                            aria-label="Edit note"
                            data-testid="mappings-edit-note"
                          />
                        ) : r.note ? (
                          <NoteCell title={r.note}>{r.note}</NoteCell>
                        ) : (
                          <Muted>—</Muted>
                        )}
                      </Table.Cell>
                      <Table.Cell>
                        {r.createdByUsername ? (
                          r.createdByUsername
                        ) : (
                          <Muted>—</Muted>
                        )}
                      </Table.Cell>
                      <Table.Cell>
                        {r.modified ? (
                          formatDateTime(r.modified)
                        ) : (
                          <Muted>—</Muted>
                        )}
                      </Table.Cell>
                      <Table.Cell>
                        {r.editable ? (
                          isEditing ? (
                            <RowActions>
                              <IconButton
                                type="button"
                                onClick={() => handleUpdate(r.id)}
                                disabled={
                                  updating ||
                                  !editFromKey.trim() ||
                                  !editToKey.trim()
                                }
                                aria-label="Save mapping"
                                title="Save"
                                data-testid="mappings-save"
                              >
                                <Check />
                              </IconButton>
                              <IconButton
                                type="button"
                                onClick={cancelEdit}
                                aria-label="Cancel edit"
                                title="Cancel"
                                data-testid="mappings-cancel"
                              >
                                <X />
                              </IconButton>
                            </RowActions>
                          ) : (
                            <RowActions>
                              <IconButton
                                type="button"
                                onClick={() => startEdit(r)}
                                disabled={mutating}
                                aria-label={`Edit ${r.fromKey}`}
                                title="Edit"
                                data-testid="mappings-edit"
                              >
                                <Pencil />
                              </IconButton>
                              <IconButton
                                type="button"
                                $danger
                                onClick={() => handleDelete(r)}
                                disabled={mutating}
                                aria-label={`Delete ${r.fromKey}`}
                                title="Delete"
                                data-testid="mappings-delete"
                              >
                                <Trash2 />
                              </IconButton>
                            </RowActions>
                          )
                        ) : (
                          <Muted title="Bundled mappings are read-only">
                            read-only
                          </Muted>
                        )}
                      </Table.Cell>
                    </Table.Row>
                  );
                })}
              </Table.Body>
            </Table>
          </ScrollableTableWrapper>
          {pageInfo?.hasNextPage && (
            <LoadMoreRow>
              <Button
                variant="secondary"
                onClick={handleLoadMore}
                disabled={listQuery.loading}
                data-testid="mappings-load-more"
              >
                {listQuery.loading ? "Loading…" : "Load more"}
              </Button>
            </LoadMoreRow>
          )}
        </>
      )}
    </Container>
  );
};

export default AuthorityMappings;
