/**
 * Single-authority detail — everything about one body of law in one place.
 *
 * Joins the namespace + its aliases (editable) + in/out key-equivalences +
 * discovery-frontier rows + reference demand, all string-joined server-side by
 * AuthorityNamespaceService.detail. Phase 1 makes the header + aliases editable;
 * relationships, frontier rows and references are read-only here (relationship
 * editing lands in the Aliases & Relationships tab; frontier actions in the
 * Discovery Queue tab — both in later phases).
 */
import React, { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery } from "@apollo/client";
import { Button, Table } from "@os-legal/ui";
import styled from "styled-components";
import { ArrowLeft, Check, Pencil, Plus, Trash2, X } from "lucide-react";
import { toast } from "react-toastify";

import {
  ErrorMessage,
  InfoMessage,
  LoadingState,
} from "../../widgets/feedback";
import { ScrollableTableWrapper } from "../../layout/SharedSegments";
import { OS_LEGAL_COLORS } from "../../../assets/configurations/osLegalStyles";
import { CORPUS_RADII } from "../../corpuses/styles/corpusDesignTokens";
import {
  GetAuthorityNamespaceDetailInputs,
  GetAuthorityNamespaceDetailOutputs,
  GET_AUTHORITY_NAMESPACE_DETAIL,
} from "../../../graphql/queries";
import {
  DeleteAuthorityNamespaceInputs,
  DeleteAuthorityNamespaceOutputs,
  DELETE_AUTHORITY_NAMESPACE,
  SetAuthorityNamespaceAliasesInputs,
  SetAuthorityNamespaceAliasesOutputs,
  SET_AUTHORITY_NAMESPACE_ALIASES,
  UpdateAuthorityNamespaceInputs,
  UpdateAuthorityNamespaceOutputs,
  UPDATE_AUTHORITY_NAMESPACE,
} from "../../../graphql/mutations";
import {
  Badge,
  BackLink,
  FieldLabel,
  IconButton,
  KeyCell,
  Muted,
  Select,
  TextInput,
} from "./shared/consoleChrome";
import { sourceTone, stateTone, humanizeCode } from "./shared/tones";
import {
  AUTHORITY_TYPE_OPTIONS,
  scopeLabel,
  scopeTone,
} from "./shared/authorityVocab";

const DETAIL_TABLE_MIN_WIDTH_PX = 720;

const Section = styled.section`
  margin-bottom: 1.5rem;
  padding: 1.25rem 1.35rem;
  background: ${OS_LEGAL_COLORS.surface};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 12px;
`;

const SectionHead = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1rem;
`;

const SectionTitle = styled.h3`
  margin: 0;
  font-size: 1rem;
  color: ${OS_LEGAL_COLORS.textPrimary};
`;

const SectionNote = styled.p`
  margin: 0 0 0.85rem;
  font-size: 0.78rem;
  line-height: 1.45;
  color: ${OS_LEGAL_COLORS.textMuted};
`;

const TitleRow = styled.div`
  display: flex;
  align-items: center;
  gap: 0.6rem;
  flex-wrap: wrap;
  margin-bottom: 0.4rem;
`;

const DetailTitle = styled.h2`
  margin: 0;
  font-size: 1.35rem;
  color: ${OS_LEGAL_COLORS.textPrimary};
`;

const FieldGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 0.85rem 1.1rem;
`;

const Field = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
`;

const FieldValue = styled.span`
  font-size: 0.875rem;
  color: ${OS_LEGAL_COLORS.textPrimary};
`;

const AdvisoryTag = styled.span`
  font-size: 0.65rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  color: ${OS_LEGAL_COLORS.warningText};
`;

const AliasRow = styled.div`
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.45rem;
`;

const AliasChip = styled.span`
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.2rem 0.55rem;
  border-radius: ${CORPUS_RADII.full};
  font-size: 0.78rem;
  color: ${OS_LEGAL_COLORS.textPrimary};
  background: ${OS_LEGAL_COLORS.surfaceLight};
  border: 1px solid ${OS_LEGAL_COLORS.border};

  button {
    display: inline-flex;
    border: none;
    background: none;
    padding: 0;
    cursor: pointer;
    color: ${OS_LEGAL_COLORS.textMuted};
    &:hover {
      color: ${OS_LEGAL_COLORS.dangerText};
    }
    svg {
      width: 12px;
      height: 12px;
    }
  }
`;

const AliasAdder = styled.div`
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
`;

const Header = styled.div`
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
`;

const Actions = styled.div`
  display: inline-flex;
  gap: 0.5rem;
`;

const DangerZone = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
  margin-top: 0.5rem;
`;

const StatPills = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  margin-bottom: 0.85rem;
`;

interface AuthorityDetailViewProps {
  prefix: string;
  onClose: () => void;
  onChanged: () => void;
}

export const AuthorityDetailView: React.FC<AuthorityDetailViewProps> = ({
  prefix,
  onClose,
  onChanged,
}) => {
  const { data, loading, error, refetch } = useQuery<
    GetAuthorityNamespaceDetailOutputs,
    GetAuthorityNamespaceDetailInputs
  >(GET_AUTHORITY_NAMESPACE_DETAIL, {
    variables: { prefix },
    fetchPolicy: "network-only",
  });
  const detail = data?.authorityNamespaceDetail ?? null;
  const ns = detail?.namespace ?? null;

  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState({
    displayName: "",
    jurisdiction: "",
    authorityType: "",
    provider: "",
    sourceRootUrl: "",
    license: "",
  });
  const [aliasDraft, setAliasDraft] = useState<string[]>([]);
  const [newAlias, setNewAlias] = useState("");

  // Re-seed the editable drafts whenever the loaded namespace changes.
  useEffect(() => {
    if (ns) {
      setDraft({
        displayName: ns.displayName ?? "",
        jurisdiction: ns.jurisdiction ?? "",
        authorityType: ns.authorityType ?? "",
        provider: ns.provider ?? "",
        sourceRootUrl: ns.sourceRootUrl ?? "",
        license: ns.license ?? "",
      });
      setAliasDraft(ns.aliases ?? []);
    }
  }, [ns]);

  const [updateNamespace, { loading: saving }] = useMutation<
    UpdateAuthorityNamespaceOutputs,
    UpdateAuthorityNamespaceInputs
  >(UPDATE_AUTHORITY_NAMESPACE);
  const [setAliases, { loading: savingAliases }] = useMutation<
    SetAuthorityNamespaceAliasesOutputs,
    SetAuthorityNamespaceAliasesInputs
  >(SET_AUTHORITY_NAMESPACE_ALIASES);
  const [deleteNamespace, { loading: deleting }] = useMutation<
    DeleteAuthorityNamespaceOutputs,
    DeleteAuthorityNamespaceInputs
  >(DELETE_AUTHORITY_NAMESPACE);

  const aliasesDirty = useMemo(() => {
    const a = [...(ns?.aliases ?? [])].sort();
    const b = [...aliasDraft].sort();
    return a.length !== b.length || a.some((v, i) => v !== b[i]);
  }, [ns, aliasDraft]);

  if (loading && !detail) {
    return <LoadingState message="Loading authority…" />;
  }
  if (error) {
    return (
      <ErrorMessage title="Error loading authority">
        {error.message}
      </ErrorMessage>
    );
  }
  if (!detail || !ns) {
    return (
      <div>
        <BackLink onClick={onClose} data-testid="detail-back">
          <ArrowLeft size={14} />
          All authorities
        </BackLink>
        <InfoMessage title="Authority not found">
          No authority with prefix “{prefix}” exists (it may have been deleted).
        </InfoMessage>
      </div>
    );
  }

  const afterMutation = () => {
    refetch();
    onChanged();
  };

  const handleSaveHeader = async () => {
    if (!draft.displayName.trim()) {
      toast.error("Display name is required.");
      return;
    }
    try {
      const { data: res } = await updateNamespace({
        variables: {
          id: ns.id,
          displayName: draft.displayName.trim(),
          jurisdiction: draft.jurisdiction.trim(),
          authorityType: draft.authorityType,
          provider: draft.provider.trim(),
          sourceRootUrl: draft.sourceRootUrl.trim(),
          license: draft.license.trim(),
        },
      });
      const out = res?.updateAuthorityNamespace;
      if (out?.ok) {
        toast.success("Authority updated.");
        setEditing(false);
        afterMutation();
      } else {
        toast.error(out?.message ?? "Could not update authority.");
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Update failed.");
    }
  };

  const handleSaveAliases = async () => {
    try {
      const { data: res } = await setAliases({
        variables: { id: ns.id, aliases: aliasDraft },
      });
      const out = res?.setAuthorityNamespaceAliases;
      if (out?.ok) {
        toast.success("Aliases saved.");
        afterMutation();
      } else {
        toast.error(out?.message ?? "Could not save aliases.");
      }
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Saving aliases failed."
      );
    }
  };

  const addAlias = () => {
    const a = newAlias.trim().toLowerCase();
    if (a && !aliasDraft.includes(a)) {
      setAliasDraft((prev) => [...prev, a].sort());
    }
    setNewAlias("");
  };

  const handleDelete = async () => {
    if (
      !window.confirm(
        `Delete the authority “${ns.displayName}” (${ns.prefix})? ` +
          "This cannot be undone."
      )
    ) {
      return;
    }
    try {
      const { data: res } = await deleteNamespace({ variables: { id: ns.id } });
      const out = res?.deleteAuthorityNamespace;
      if (out?.ok) {
        toast.success("Authority deleted.");
        onChanged();
        onClose();
      } else {
        toast.error(out?.message ?? "Could not delete authority.");
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Delete failed.");
    }
  };

  const equivalences = [...detail.equivalencesOut, ...detail.equivalencesIn];

  return (
    <div data-testid="authority-detail">
      <BackLink onClick={onClose} data-testid="detail-back">
        <ArrowLeft size={14} />
        All authorities
      </BackLink>

      {/* ---- header / metadata ---- */}
      <Section>
        <Header>
          <div>
            <TitleRow>
              <DetailTitle data-testid="detail-title">
                {ns.displayName}
              </DetailTitle>
              <Badge $tone={scopeTone(ns.scope)}>{scopeLabel(ns.scope)}</Badge>
              <Badge $tone={sourceTone(ns.source)}>
                {humanizeCode(ns.source)}
              </Badge>
            </TitleRow>
            <KeyCell>{ns.prefix}</KeyCell>
          </div>
          <Actions>
            {editing ? (
              <>
                <Button
                  variant="primary"
                  onClick={handleSaveHeader}
                  disabled={saving}
                  data-testid="detail-save"
                >
                  <Check size={14} style={{ marginRight: 6 }} />
                  {saving ? "Saving…" : "Save"}
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => setEditing(false)}
                  data-testid="detail-cancel"
                >
                  Cancel
                </Button>
              </>
            ) : (
              <Button
                variant="secondary"
                onClick={() => setEditing(true)}
                data-testid="detail-edit"
              >
                <Pencil size={14} style={{ marginRight: 6 }} />
                Edit
              </Button>
            )}
          </Actions>
        </Header>

        <div style={{ marginTop: "1.1rem" }}>
          <FieldGrid>
            <Field>
              <FieldLabel>Display name</FieldLabel>
              {editing ? (
                <TextInput
                  value={draft.displayName}
                  onChange={(e) =>
                    setDraft((d) => ({ ...d, displayName: e.target.value }))
                  }
                  data-testid="detail-displayname"
                />
              ) : (
                <FieldValue>{ns.displayName}</FieldValue>
              )}
            </Field>
            <Field>
              <FieldLabel>Jurisdiction</FieldLabel>
              {editing ? (
                <TextInput
                  value={draft.jurisdiction}
                  onChange={(e) =>
                    setDraft((d) => ({ ...d, jurisdiction: e.target.value }))
                  }
                  placeholder="e.g. us-ca"
                  data-testid="detail-jurisdiction"
                />
              ) : (
                <FieldValue>{ns.jurisdiction || <Muted>—</Muted>}</FieldValue>
              )}
            </Field>
            <Field>
              <FieldLabel>Authority type</FieldLabel>
              {editing ? (
                <Select
                  value={draft.authorityType}
                  onChange={(e) =>
                    setDraft((d) => ({ ...d, authorityType: e.target.value }))
                  }
                  data-testid="detail-type"
                >
                  <option value="">—</option>
                  {AUTHORITY_TYPE_OPTIONS.map((t) => (
                    <option key={t} value={t}>
                      {humanizeCode(t)}
                    </option>
                  ))}
                </Select>
              ) : (
                <FieldValue>
                  {ns.authorityType ? (
                    humanizeCode(ns.authorityType)
                  ) : (
                    <Muted>—</Muted>
                  )}
                </FieldValue>
              )}
            </Field>
            <Field>
              <FieldLabel>
                Provider <AdvisoryTag>advisory</AdvisoryTag>
              </FieldLabel>
              {editing ? (
                <TextInput
                  value={draft.provider}
                  onChange={(e) =>
                    setDraft((d) => ({ ...d, provider: e.target.value }))
                  }
                  data-testid="detail-provider"
                />
              ) : (
                <FieldValue>{ns.provider || <Muted>—</Muted>}</FieldValue>
              )}
            </Field>
            <Field>
              <FieldLabel>
                Source root URL <AdvisoryTag>advisory</AdvisoryTag>
              </FieldLabel>
              {editing ? (
                <TextInput
                  value={draft.sourceRootUrl}
                  onChange={(e) =>
                    setDraft((d) => ({ ...d, sourceRootUrl: e.target.value }))
                  }
                  data-testid="detail-sourceurl"
                />
              ) : (
                <FieldValue>{ns.sourceRootUrl || <Muted>—</Muted>}</FieldValue>
              )}
            </Field>
            <Field>
              <FieldLabel>
                License <AdvisoryTag>advisory</AdvisoryTag>
              </FieldLabel>
              {editing ? (
                <TextInput
                  value={draft.license}
                  onChange={(e) =>
                    setDraft((d) => ({ ...d, license: e.target.value }))
                  }
                  data-testid="detail-license"
                />
              ) : (
                <FieldValue>{ns.license || <Muted>—</Muted>}</FieldValue>
              )}
            </Field>
            <Field>
              <FieldLabel>Effective provider (routing)</FieldLabel>
              <FieldValue data-testid="detail-effective-provider">
                {detail.effectiveProvider || <Muted>none</Muted>}
              </FieldValue>
            </Field>
          </FieldGrid>
          <SectionNote style={{ marginTop: "0.75rem", marginBottom: 0 }}>
            Provider / source URL / license are <strong>advisory</strong>{" "}
            provenance only — discovery routing is decided by the registry’s
            <code> can_handle()</code> / priority (shown as “effective
            provider”), not these fields.
          </SectionNote>
        </div>
      </Section>

      {/* ---- aliases ---- */}
      <Section>
        <SectionHead>
          <SectionTitle>Aliases ({aliasDraft.length})</SectionTitle>
          {aliasesDirty && (
            <Button
              variant="primary"
              onClick={handleSaveAliases}
              disabled={savingAliases}
              data-testid="detail-save-aliases"
            >
              <Check size={14} style={{ marginRight: 6 }} />
              {savingAliases ? "Saving…" : "Save aliases"}
            </Button>
          )}
        </SectionHead>
        <SectionNote>
          Surface forms (lowercased) that drive Tier-1 citation extraction.
          Editing aliases does not retro-rewrite references already detected.
        </SectionNote>
        <AliasRow>
          {aliasDraft.map((a) => (
            <AliasChip key={a} data-testid={`detail-alias-${a}`}>
              {a}
              <button
                type="button"
                aria-label={`Remove alias ${a}`}
                onClick={() =>
                  setAliasDraft((prev) => prev.filter((x) => x !== a))
                }
              >
                <X />
              </button>
            </AliasChip>
          ))}
          {aliasDraft.length === 0 && <Muted>No aliases.</Muted>}
          <AliasAdder>
            <TextInput
              value={newAlias}
              onChange={(e) => setNewAlias(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  addAlias();
                }
              }}
              placeholder="Add alias…"
              style={{ minWidth: 160 }}
              data-testid="detail-new-alias"
            />
            <IconButton
              type="button"
              onClick={addAlias}
              aria-label="Add alias"
              data-testid="detail-add-alias"
            >
              <Plus />
            </IconButton>
          </AliasAdder>
        </AliasRow>
      </Section>

      {/* ---- relationships (read-only in Phase 1) ---- */}
      <Section>
        <SectionTitle>Relationships ({equivalences.length})</SectionTitle>
        <SectionNote>
          Canonical-key equivalences that bridge this body of law to others.
          Editing lives in the Aliases &amp; Relationships tab.
        </SectionNote>
        {equivalences.length === 0 ? (
          <Muted>No key-equivalences reference this authority.</Muted>
        ) : (
          <ScrollableTableWrapper $minWidth={`${DETAIL_TABLE_MIN_WIDTH_PX}px`}>
            <Table variant="minimal">
              <Table.Head>
                <Table.Row>
                  <Table.HeadCell>From key</Table.HeadCell>
                  <Table.HeadCell>To key</Table.HeadCell>
                  <Table.HeadCell>Source</Table.HeadCell>
                  <Table.HeadCell>Note</Table.HeadCell>
                </Table.Row>
              </Table.Head>
              <Table.Body>
                {equivalences.map((eq) => (
                  <Table.Row key={eq.id} data-testid="detail-equivalence-row">
                    <Table.Cell>
                      <KeyCell>{eq.fromKey}</KeyCell>
                    </Table.Cell>
                    <Table.Cell>
                      <KeyCell>{eq.toKey}</KeyCell>
                    </Table.Cell>
                    <Table.Cell>
                      <Badge $tone={sourceTone(eq.source)}>
                        {humanizeCode(eq.source)}
                      </Badge>
                    </Table.Cell>
                    <Table.Cell>
                      {eq.note ? eq.note : <Muted>—</Muted>}
                    </Table.Cell>
                  </Table.Row>
                ))}
              </Table.Body>
            </Table>
          </ScrollableTableWrapper>
        )}
      </Section>

      {/* ---- discovery frontier (read-only in Phase 1) ---- */}
      <Section>
        <SectionTitle>
          Discovery queue ({detail.frontierRows.length})
        </SectionTitle>
        <SectionNote>
          Wanted section-roots for this authority and their ingestion state.
          Per-row actions live in the Discovery Queue tab.
        </SectionNote>
        {detail.frontierStateCounts.length > 0 && (
          <StatPills>
            {detail.frontierStateCounts.map((s) => (
              <Badge key={s.state} $tone={stateTone(s.state)}>
                {humanizeCode(s.state)} {s.count}
              </Badge>
            ))}
          </StatPills>
        )}
        {detail.frontierRows.length === 0 ? (
          <Muted>No frontier rows for this authority.</Muted>
        ) : (
          <ScrollableTableWrapper $minWidth={`${DETAIL_TABLE_MIN_WIDTH_PX}px`}>
            <Table variant="minimal">
              <Table.Head>
                <Table.Row>
                  <Table.HeadCell>Key</Table.HeadCell>
                  <Table.HeadCell>State</Table.HeadCell>
                  <Table.HeadCell>Mentions</Table.HeadCell>
                  <Table.HeadCell>Provider</Table.HeadCell>
                </Table.Row>
              </Table.Head>
              <Table.Body>
                {detail.frontierRows.map((f) => (
                  <Table.Row key={f.id} data-testid="detail-frontier-row">
                    <Table.Cell>
                      <KeyCell>{f.canonicalKey}</KeyCell>
                    </Table.Cell>
                    <Table.Cell>
                      <Badge $tone={stateTone(f.discoveryState)}>
                        {humanizeCode(f.discoveryState)}
                      </Badge>
                    </Table.Cell>
                    <Table.Cell>{f.mentionCount}</Table.Cell>
                    <Table.Cell>
                      {f.provider ? f.provider : <Muted>—</Muted>}
                    </Table.Cell>
                  </Table.Row>
                ))}
              </Table.Body>
            </Table>
          </ScrollableTableWrapper>
        )}
      </Section>

      {/* ---- references (read-only by design) ---- */}
      <Section>
        <SectionTitle>References ({detail.referenceTotal})</SectionTitle>
        <SectionNote>
          Citations across all corpora that resolve under this prefix. Read-only
          (machine-populated by enrichment).
        </SectionNote>
        {detail.referenceStatusCounts.length > 0 ? (
          <StatPills>
            {detail.referenceStatusCounts.map((s) => (
              <Badge key={s.status} $tone="neutral">
                {humanizeCode(s.status)} {s.count}
              </Badge>
            ))}
          </StatPills>
        ) : (
          <Muted>No references resolve under this prefix yet.</Muted>
        )}
      </Section>

      {/* ---- danger zone ---- */}
      <Section>
        <DangerZone>
          <div>
            <SectionTitle>Delete authority</SectionTitle>
            <SectionNote style={{ marginBottom: 0 }}>
              Allowed only when no equivalences, frontier rows or references
              still reference this prefix.
            </SectionNote>
          </div>
          <Button
            variant="danger"
            onClick={handleDelete}
            disabled={deleting}
            data-testid="detail-delete"
          >
            <Trash2 size={14} style={{ marginRight: 6 }} />
            {deleting ? "Deleting…" : "Delete"}
          </Button>
        </DangerZone>
      </Section>
    </div>
  );
};
