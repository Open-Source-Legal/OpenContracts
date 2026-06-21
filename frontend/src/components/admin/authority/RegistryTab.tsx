/**
 * Registry tab — the master list of AuthorityNamespace rows (bodies of law).
 *
 * Faceted scope chips + jurisdiction / authority-type selects + search over the
 * relay connection, an inline "new authority" create form, and a table whose
 * display-name links into the single-authority detail view. Reuses the shared
 * console chrome + FacetedStatsChips + useFacetedRelayList so it matches the
 * existing admin panels exactly.
 */
import React, { useMemo, useState } from "react";
import { useMutation, useQuery } from "@apollo/client";
import { Button, Table } from "@os-legal/ui";
import styled from "styled-components";
import { ChevronDown, Plus, Search, X } from "lucide-react";
import { toast } from "react-toastify";

import {
  ErrorMessage,
  InfoMessage,
  LoadingState,
} from "../../widgets/feedback";
import { ScrollableTableWrapper } from "../../layout/SharedSegments";
import { OS_LEGAL_COLORS } from "../../../assets/configurations/osLegalStyles";
import {
  AuthorityNamespaceNode,
  GetAuthorityNamespaceStatsInputs,
  GetAuthorityNamespaceStatsOutputs,
  GetAuthorityNamespacesInputs,
  GET_AUTHORITY_NAMESPACES,
  GET_AUTHORITY_NAMESPACE_STATS,
} from "../../../graphql/queries";
import {
  CreateAuthorityNamespaceInputs,
  CreateAuthorityNamespaceOutputs,
  CREATE_AUTHORITY_NAMESPACE,
} from "../../../graphql/mutations";
import { FacetedStatsChips } from "./shared/FacetedStatsChips";
import {
  Badge,
  ClickableRowName,
  FieldLabel,
  FilterBar,
  KeyCell,
  KeyInput,
  LoadMoreRow,
  Muted,
  SearchBox,
  Select,
  TextInput,
} from "./shared/consoleChrome";
import { sourceTone, humanizeCode } from "./shared/tones";
import {
  AUTHORITY_TYPE_OPTIONS,
  REGISTRY_PAGE_SIZE,
  scopeLabel,
  scopeTone,
} from "./shared/authorityVocab";
import { useFacetedRelayList } from "./hooks/useFacetedRelayList";
import { AuthorityDetailView } from "./AuthorityDetailView";

const REGISTRY_TABLE_MIN_WIDTH_PX = 900;

const Toolbar = styled.div`
  display: flex;
  justify-content: flex-end;
  margin-bottom: 0.75rem;
`;

const CreateForm = styled.form`
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
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
  flex: 1 1 150px;
`;

interface RegistryTabProps {
  selectedPrefix: string | null;
  onOpenAuthority: (prefix: string) => void;
  onCloseAuthority: () => void;
}

export const RegistryTab: React.FC<RegistryTabProps> = ({
  selectedPrefix,
  onOpenAuthority,
  onCloseAuthority,
}) => {
  const [search, setSearch] = useState("");
  const [jurisdiction, setJurisdiction] = useState<string | null>(null);
  const [authorityType, setAuthorityType] = useState<string | null>(null);
  const [scope, setScope] = useState<string | null>(null);

  const [showCreate, setShowCreate] = useState(false);
  const [newPrefix, setNewPrefix] = useState("");
  const [newName, setNewName] = useState("");
  const [newJurisdiction, setNewJurisdiction] = useState("");
  const [newType, setNewType] = useState("");
  const [newAliases, setNewAliases] = useState("");

  const statsVars: GetAuthorityNamespaceStatsInputs = useMemo(
    () => ({ search: search.trim() || null }),
    [search]
  );
  const statsQuery = useQuery<
    GetAuthorityNamespaceStatsOutputs,
    GetAuthorityNamespaceStatsInputs
  >(GET_AUTHORITY_NAMESPACE_STATS, {
    variables: statsVars,
    fetchPolicy: "network-only",
  });
  const stats = statsQuery.data?.authorityNamespaceStats;

  const listVars: GetAuthorityNamespacesInputs = useMemo(
    () => ({
      jurisdiction: jurisdiction || null,
      authorityType: authorityType || null,
      scope: scope || null,
      search: search.trim() || null,
      first: REGISTRY_PAGE_SIZE,
      after: null,
    }),
    [jurisdiction, authorityType, scope, search]
  );

  const list = useFacetedRelayList<
    AuthorityNamespaceNode,
    GetAuthorityNamespacesInputs
  >({
    query: GET_AUTHORITY_NAMESPACES,
    variables: listVars,
    connectionKey: "authorityNamespaces",
  });

  const [createNamespace, { loading: creating }] = useMutation<
    CreateAuthorityNamespaceOutputs,
    CreateAuthorityNamespaceInputs
  >(CREATE_AUTHORITY_NAMESPACE);

  const refetchAll = () => {
    statsQuery.refetch();
    list.refetch();
  };

  // Single-authority detail takes over the tab when a prefix is selected.
  if (selectedPrefix) {
    return (
      <AuthorityDetailView
        prefix={selectedPrefix}
        onClose={onCloseAuthority}
        onChanged={refetchAll}
      />
    );
  }

  const jurisdictionOptions = (stats?.byJurisdiction ?? [])
    .map((f) => f.value)
    .filter((v) => v !== "");

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    const prefix = newPrefix.trim();
    const displayName = newName.trim();
    if (!prefix || !displayName) return;
    const aliases = newAliases
      .split(",")
      .map((a) => a.trim())
      .filter(Boolean);
    try {
      const { data } = await createNamespace({
        variables: {
          prefix,
          displayName,
          jurisdiction: newJurisdiction.trim() || null,
          authorityType: newType || null,
          aliases,
          isGlobal: true,
        },
      });
      const res = data?.createAuthorityNamespace;
      if (res?.ok) {
        toast.success(
          res.message && res.message !== "SUCCESS"
            ? res.message
            : "Authority created."
        );
        setNewPrefix("");
        setNewName("");
        setNewJurisdiction("");
        setNewType("");
        setNewAliases("");
        setShowCreate(false);
        refetchAll();
        onOpenAuthority(prefix);
      } else {
        toast.error(res?.message ?? "Could not create authority.");
      }
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Could not create authority."
      );
    }
  };

  const loading = list.loading && list.rows.length === 0;

  return (
    <div data-testid="authority-registry-tab">
      {stats ? (
        <FacetedStatsChips
          chips={stats.byScope}
          activeValue={scope}
          onSelect={setScope}
          getTone={scopeTone}
          getLabel={scopeLabel}
          totalCount={stats.totalCount}
          testIdPrefix="registry-scope"
        />
      ) : null}

      <FilterBar>
        <SearchBox>
          <Search className="lead" aria-hidden="true" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search prefix / name / alias…"
            aria-label="Search authorities"
            data-testid="registry-search"
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
          data-testid="registry-filter-jurisdiction"
        >
          <option value="">All jurisdictions</option>
          {jurisdictionOptions.map((j) => (
            <option key={j} value={j}>
              {j}
            </option>
          ))}
        </Select>
        <Select
          value={authorityType ?? ""}
          onChange={(e) => setAuthorityType(e.target.value || null)}
          aria-label="Filter by authority type"
          data-testid="registry-filter-type"
        >
          <option value="">All types</option>
          {AUTHORITY_TYPE_OPTIONS.map((t) => (
            <option key={t} value={t}>
              {humanizeCode(t)}
            </option>
          ))}
        </Select>
      </FilterBar>

      <Toolbar>
        <Button
          variant={showCreate ? "secondary" : "primary"}
          onClick={() => setShowCreate((s) => !s)}
          data-testid="registry-new-toggle"
        >
          {showCreate ? (
            <ChevronDown size={14} style={{ marginRight: 6 }} />
          ) : (
            <Plus size={14} style={{ marginRight: 6 }} />
          )}
          {showCreate ? "Hide form" : "New authority"}
        </Button>
      </Toolbar>

      {showCreate && (
        <CreateForm onSubmit={handleCreate} data-testid="registry-create-form">
          <CreateField>
            <FieldLabel htmlFor="ns-new-prefix">Prefix</FieldLabel>
            <KeyInput
              id="ns-new-prefix"
              value={newPrefix}
              onChange={(e) => setNewPrefix(e.target.value)}
              placeholder="e.g. cal-corp"
              data-testid="registry-new-prefix"
            />
          </CreateField>
          <CreateField style={{ flex: "2 1 200px" }}>
            <FieldLabel htmlFor="ns-new-name">Display name</FieldLabel>
            <TextInput
              id="ns-new-name"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="e.g. California Corporations Code"
              data-testid="registry-new-name"
            />
          </CreateField>
          <CreateField>
            <FieldLabel htmlFor="ns-new-juris">Jurisdiction</FieldLabel>
            <TextInput
              id="ns-new-juris"
              value={newJurisdiction}
              onChange={(e) => setNewJurisdiction(e.target.value)}
              placeholder="e.g. us-ca"
              data-testid="registry-new-jurisdiction"
            />
          </CreateField>
          <CreateField>
            <FieldLabel htmlFor="ns-new-type">Authority type</FieldLabel>
            <Select
              id="ns-new-type"
              value={newType}
              onChange={(e) => setNewType(e.target.value)}
              data-testid="registry-new-type"
            >
              <option value="">—</option>
              {AUTHORITY_TYPE_OPTIONS.map((t) => (
                <option key={t} value={t}>
                  {humanizeCode(t)}
                </option>
              ))}
            </Select>
          </CreateField>
          <CreateField style={{ flex: "2 1 220px" }}>
            <FieldLabel htmlFor="ns-new-aliases">
              Aliases (comma-separated)
            </FieldLabel>
            <TextInput
              id="ns-new-aliases"
              value={newAliases}
              onChange={(e) => setNewAliases(e.target.value)}
              placeholder="e.g. Cal. Corp. Code, California Corporations Code"
              data-testid="registry-new-aliases"
            />
          </CreateField>
          <Button
            variant="primary"
            type="submit"
            disabled={creating || !newPrefix.trim() || !newName.trim()}
            data-testid="registry-create-submit"
          >
            <Plus size={14} style={{ marginRight: 6 }} />
            {creating ? "Adding…" : "Add authority"}
          </Button>
        </CreateForm>
      )}

      {loading ? (
        <LoadingState message="Loading authorities…" />
      ) : list.error ? (
        <ErrorMessage title="Error loading authorities">
          {list.error.message}
        </ErrorMessage>
      ) : list.rows.length === 0 ? (
        <InfoMessage title="No authorities">
          {search.trim() || jurisdiction || authorityType || scope
            ? "No bodies of law match the current filters."
            : "No authority namespaces exist yet. Add one above."}
        </InfoMessage>
      ) : (
        <>
          <ScrollableTableWrapper
            $minWidth={`${REGISTRY_TABLE_MIN_WIDTH_PX}px`}
            data-testid="registry-table-scroll"
          >
            <Table variant="minimal">
              <Table.Head>
                <Table.Row>
                  <Table.HeadCell>Prefix</Table.HeadCell>
                  <Table.HeadCell>Body of law</Table.HeadCell>
                  <Table.HeadCell>Jurisdiction</Table.HeadCell>
                  <Table.HeadCell>Type</Table.HeadCell>
                  <Table.HeadCell>Scope</Table.HeadCell>
                  <Table.HeadCell>Source</Table.HeadCell>
                  <Table.HeadCell>Aliases</Table.HeadCell>
                  <Table.HeadCell>Refs</Table.HeadCell>
                </Table.Row>
              </Table.Head>
              <Table.Body>
                {list.rows.map((r) => (
                  <Table.Row key={r.id} data-testid="registry-row">
                    <Table.Cell>
                      <KeyCell>{r.prefix}</KeyCell>
                    </Table.Cell>
                    <Table.Cell>
                      <ClickableRowName
                        type="button"
                        onClick={() => onOpenAuthority(r.prefix)}
                        data-testid={`registry-open-${r.prefix}`}
                      >
                        {r.displayName}
                      </ClickableRowName>
                    </Table.Cell>
                    <Table.Cell>
                      {r.jurisdiction ? r.jurisdiction : <Muted>—</Muted>}
                    </Table.Cell>
                    <Table.Cell>
                      {r.authorityType ? (
                        humanizeCode(r.authorityType)
                      ) : (
                        <Muted>—</Muted>
                      )}
                    </Table.Cell>
                    <Table.Cell>
                      <Badge $tone={scopeTone(r.scope)}>
                        {scopeLabel(r.scope)}
                      </Badge>
                    </Table.Cell>
                    <Table.Cell>
                      <Badge $tone={sourceTone(r.source)}>
                        {humanizeCode(r.source)}
                      </Badge>
                    </Table.Cell>
                    <Table.Cell>{r.aliases?.length ?? 0}</Table.Cell>
                    <Table.Cell>{r.referenceCount ?? 0}</Table.Cell>
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
                data-testid="registry-load-more"
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
