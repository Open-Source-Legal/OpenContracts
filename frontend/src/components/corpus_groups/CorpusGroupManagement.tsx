import React, { useMemo, useState, useCallback } from "react";
import { useQuery, useMutation, useReactiveVar } from "@apollo/client";
import {
  Button,
  IconButton,
  Input,
  Modal,
  ModalHeader,
  ModalBody,
  ModalFooter,
  Switch,
  Table,
} from "@os-legal/ui";
import { Plus, Pencil, Trash2, Save, Layers, LogIn } from "lucide-react";
import { toast } from "react-toastify";
import styled from "styled-components";

import { authStatusVar, backendUserObj } from "../../graphql/cache";
import { StyledTextArea } from "../widgets/modals/styled";
import {
  ErrorMessage,
  LoadingState,
  WarningMessage,
} from "../widgets/feedback";
import { ConfirmModal } from "../widgets/modals/ConfirmModal";
import {
  GradientSegment as StyledSegment,
  PageHeader as BasePageHeader,
  ScrollableTableWrapper,
} from "../layout/SharedSegments";
import { OS_LEGAL_COLORS } from "../../assets/configurations/osLegalStyles";
import { MOBILE_VIEW_BREAKPOINT } from "../../assets/configurations/constants";
import {
  CorpusMultiSelect,
  CorpusOption,
} from "../widgets/selectors/CorpusMultiSelect";
import {
  AgentConfigurationSelect,
  AgentOption,
} from "../widgets/selectors/AgentConfigurationSelect";
import {
  CORPUS_GROUP_MEMBERSHIP_FETCH_LIMIT,
  GET_MY_CORPUS_GROUPS,
  CREATE_CORPUS_GROUP,
  UPDATE_CORPUS_GROUP,
  DELETE_CORPUS_GROUP,
  ManagedCorpusGroup,
  MyCorpusGroupsResult,
  MyCorpusGroupsInputs,
  CreateCorpusGroupInputs,
  CreateCorpusGroupOutput,
  UpdateCorpusGroupInputs,
  UpdateCorpusGroupOutput,
  DeleteCorpusGroupInputs,
  DeleteCorpusGroupOutput,
} from "./graphql";

const Container = styled.div`
  padding: 2rem;

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    padding: 1rem;
  }
`;

const PageHeader = styled(BasePageHeader)`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;

  h2 {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin: 0;
  }
`;

const HeaderText = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
`;

const SubLine = styled.p`
  margin: 0;
  font-size: 0.875rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
`;

const FormField = styled.div`
  margin-bottom: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
`;

const FormLabel = styled.label`
  font-weight: 600;
  font-size: 0.875rem;
  color: ${OS_LEGAL_COLORS.textPrimary};
`;

const HelperText = styled.span`
  font-size: 0.75rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
`;

const Centered = styled.div`
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  text-align: center;
  padding: 4rem 2rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
`;

const CorporaCell = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
`;

const CorporaTitles = styled.span`
  font-size: 0.75rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
`;

const Muted = styled.span`
  color: ${OS_LEGAL_COLORS.textTertiary};
`;

/**
 * How many member-corpus titles the table previews inline before eliding.
 * Purely cosmetic — the count beside them is always the full total.
 */
const CORPORA_TITLE_PREVIEW_COUNT = 3;

/** Django ``SlugField`` character class. Mirrors the server-side validator. */
const SLUG_RE = /^[-a-zA-Z0-9_]+$/;

/** Em-dash placeholder for "no default agent bound". */
const NO_VALUE = "—";

interface GroupFormState {
  title: string;
  slug: string;
  description: string;
  corpora: CorpusOption[];
  agent: AgentOption | null;
  isPublic: boolean;
}

const EMPTY_FORM: GroupFormState = {
  title: "",
  slug: "",
  description: "",
  corpora: [],
  agent: null,
  isPublic: false,
};

/**
 * Per-user management of corpus groups — the bundles of corpora an agent can
 * search across in one shot. Every authenticated user manages their own; there
 * is deliberately no superuser gate and no instance-wide listing.
 */
export const CorpusGroupManagement: React.FC = () => {
  const backendUser = useReactiveVar(backendUserObj);
  const authStatus = useReactiveVar(authStatusVar);

  // ``backendUserObj`` is populated by the GET_ME round-trip, which resolves
  // strictly *after* AuthGate releases its children. Deriving "anonymous"
  // from it alone would flash the sign-in prompt at every authenticated user
  // who hard-navigates here. ``authStatusVar`` flips to AUTHENTICATED as soon
  // as a bearer token exists, so it distinguishes "definitely anonymous" from
  // "identity still resolving".
  const isSignedIn = backendUser !== null;
  const identityResolving = authStatus === "AUTHENTICATED" && !isSignedIn;

  const { data, loading, error, refetch } = useQuery<
    MyCorpusGroupsResult,
    MyCorpusGroupsInputs
  >(GET_MY_CORPUS_GROUPS, {
    variables: {
      // Every group the viewer can see, not just the ones they created. A
      // group's whole purpose is to be named in a cross-corpus query, so a
      // public or shared group that only its creator can find is unusable by
      // the collaborators it exists for. Ownership still governs editing
      // (below) and the mutations are permission-gated server-side.
      mine: false,
      corporaLimit: CORPUS_GROUP_MEMBERSHIP_FETCH_LIMIT,
    },
    fetchPolicy: "cache-and-network",
    skip: !isSignedIn,
  });

  // Modal + form state
  const [showFormModal, setShowFormModal] = useState(false);
  const [editingGroup, setEditingGroup] = useState<ManagedCorpusGroup | null>(
    null
  );
  const [form, setForm] = useState<GroupFormState>(EMPTY_FORM);
  const [groupToDelete, setGroupToDelete] = useState<ManagedCorpusGroup | null>(
    null
  );

  const refetchAndToast = useCallback(
    (message: string) => {
      toast.success(message);
      setShowFormModal(false);
      setEditingGroup(null);
      refetch();
    },
    [refetch]
  );

  const [createGroup, { loading: creating }] = useMutation<
    CreateCorpusGroupOutput,
    CreateCorpusGroupInputs
  >(CREATE_CORPUS_GROUP, {
    onCompleted: (result) => {
      if (result.createCorpusGroup?.ok) {
        refetchAndToast("Corpus group created");
      } else {
        toast.error(
          result.createCorpusGroup?.message || "Failed to create corpus group"
        );
      }
    },
    onError: (err) =>
      toast.error(`Error creating corpus group: ${err.message}`),
  });

  const [updateGroup, { loading: updating }] = useMutation<
    UpdateCorpusGroupOutput,
    UpdateCorpusGroupInputs
  >(UPDATE_CORPUS_GROUP, {
    onCompleted: (result) => {
      if (result.updateCorpusGroup?.ok) {
        refetchAndToast("Corpus group updated");
      } else {
        toast.error(
          result.updateCorpusGroup?.message || "Failed to update corpus group"
        );
      }
    },
    onError: (err) =>
      toast.error(`Error updating corpus group: ${err.message}`),
  });

  const [deleteGroup, { loading: deleting }] = useMutation<
    DeleteCorpusGroupOutput,
    DeleteCorpusGroupInputs
  >(DELETE_CORPUS_GROUP, {
    // The confirm modal stays open (caller-closed) while the delete is
    // in-flight so its spinner is visible, so every outcome must clear the
    // pending group to dismiss it.
    onCompleted: (result) => {
      setGroupToDelete(null);
      if (result.deleteCorpusGroup?.ok) {
        toast.success("Corpus group deleted");
        refetch();
      } else {
        toast.error(
          result.deleteCorpusGroup?.message || "Failed to delete corpus group"
        );
      }
    },
    onError: (err) => {
      setGroupToDelete(null);
      toast.error(`Error deleting corpus group: ${err.message}`);
    },
  });

  const groups = useMemo<ManagedCorpusGroup[]>(
    () =>
      (data?.corpusGroups?.edges?.map((edge) => edge.node) || [])
        // The connection has no orderBy argument, so order client-side by
        // title to keep the table stable between refetches.
        .slice()
        .sort((a, b) => (a.title ?? "").localeCompare(b.title ?? "")),
    [data]
  );

  /** Server-side total; exceeds ``groups.length`` when the page is capped. */
  const totalGroupCount = data?.corpusGroups?.totalCount ?? groups.length;

  const openCreateModal = useCallback(() => {
    setEditingGroup(null);
    // Full reset — the modal is shared with edit mode, so leftover corpora
    // chips or a bound agent from a prior edit would otherwise leak in.
    setForm(EMPTY_FORM);
    setShowFormModal(true);
  }, []);

  const openEditModal = useCallback((group: ManagedCorpusGroup) => {
    setEditingGroup(group);
    setForm({
      title: group.title ?? "",
      slug: group.slug ?? "",
      description: group.description ?? "",
      // Seed the pickers from data we already hold so chips and the agent
      // render immediately, without waiting on a search round-trip.
      corpora: (group.corpora?.edges ?? []).map((edge) => ({
        id: edge.node.id,
        title: edge.node.title ?? "",
      })),
      agent: group.defaultAgent
        ? { id: group.defaultAgent.id, name: group.defaultAgent.name }
        : null,
      isPublic: group.isPublic ?? false,
    });
    setShowFormModal(true);
  }, []);

  const handleSubmit = useCallback(() => {
    const trimmedTitle = form.title.trim();
    if (!trimmedTitle) {
      toast.error("Group title is required");
      return;
    }
    const trimmedSlug = form.slug.trim();
    if (trimmedSlug && !SLUG_RE.test(trimmedSlug)) {
      toast.error(
        "Slug may only contain letters, numbers, hyphens and underscores"
      );
      return;
    }

    // The pickers already carry relay global IDs, which is exactly what the
    // mutations decode server-side — pass them through untouched.
    const corpusIds = form.corpora.map((corpus) => corpus.id);

    if (editingGroup) {
      // updateCorpusGroup REPLACES membership, and the form seeds itself from
      // the loaded `corpora` edges. If the server capped that page, submitting
      // would silently delete the members we never saw — refuse instead.
      const loadedMembers = editingGroup.corpora?.edges?.length ?? 0;
      const totalMembers = editingGroup.corpora?.totalCount ?? loadedMembers;
      if (totalMembers > loadedMembers) {
        toast.error(
          `This group has ${totalMembers} corpora but only ${loadedMembers} loaded. ` +
            "Saving now would drop the rest — reload the page and try again."
        );
        return;
      }

      const variables: UpdateCorpusGroupInputs = {
        corpusGroupId: editingGroup.id,
        title: trimmedTitle,
        description: form.description,
        // Membership is REPLACED, not merged — always send the full set.
        corpusIds,
        isPublic: form.isPublic,
        corporaLimit: CORPUS_GROUP_MEMBERSHIP_FETCH_LIMIT,
      };
      // Omit the slug argument entirely when the field is blank: sending ""
      // would blank an existing slug rather than leave it alone.
      if (trimmedSlug) {
        variables.slug = trimmedSlug;
      }
      // defaultAgentId and clearDefaultAgent are mutually exclusive: bind when
      // one is picked, otherwise unbind. The unbind is unconditional rather
      // than gated on ``editingGroup.defaultAgent`` because that field is
      // per-viewer gated — it also reads null when a bound agent has merely
      // become unreadable to the editor, and gating on it would make the
      // picker's clear button a silent no-op in exactly that case. Sending
      // clearDefaultAgent on an already-unbound group is a harmless no-op.
      if (form.agent) {
        variables.defaultAgentId = form.agent.id;
      } else {
        variables.clearDefaultAgent = true;
      }
      updateGroup({ variables });
    } else {
      const variables: CreateCorpusGroupInputs = {
        title: trimmedTitle,
        description: form.description,
        corpusIds,
        isPublic: form.isPublic,
        corporaLimit: CORPUS_GROUP_MEMBERSHIP_FETCH_LIMIT,
      };
      // Blank slug: omit so the backend auto-generates one from the title.
      if (trimmedSlug) {
        variables.slug = trimmedSlug;
      }
      if (form.agent) {
        variables.defaultAgentId = form.agent.id;
      }
      createGroup({ variables });
    }
  }, [form, editingGroup, createGroup, updateGroup]);

  const handleConfirmDelete = useCallback(() => {
    if (groupToDelete) {
      deleteGroup({ variables: { corpusGroupId: groupToDelete.id } });
    }
  }, [groupToDelete, deleteGroup]);

  // Signed in, but GET_ME has not landed yet — show the spinner rather than
  // briefly accusing an authenticated user of being logged out.
  if (identityResolving) {
    return (
      <Container>
        <LoadingState message="Loading corpus groups..." />
      </Container>
    );
  }

  // Anonymous viewers get a sign-in prompt rather than an empty table. The
  // query is skipped above, so nothing is fetched for them either.
  if (!isSignedIn) {
    return (
      <Container>
        <StyledSegment>
          <Centered>
            <LogIn size={40} color={OS_LEGAL_COLORS.textTertiary} />
            <h3>Sign in to manage corpus groups</h3>
            <p>
              Corpus groups let an agent search across several of your corpora
              at once. Sign in to create and manage your own.
            </p>
          </Centered>
        </StyledSegment>
      </Container>
    );
  }

  if (loading && groups.length === 0) {
    return (
      <Container>
        <LoadingState message="Loading corpus groups..." />
      </Container>
    );
  }

  // Mirrors the loading guard above: only take over the page when there is
  // nothing to show. A blip during a post-mutation refetch must not replace
  // rows the user is still working with — those stay on screen and the
  // failure surfaces non-destructively via the banner below the header.
  if (error && groups.length === 0) {
    return (
      <Container>
        <ErrorMessage title="Error loading corpus groups">
          {error.message}
        </ErrorMessage>
      </Container>
    );
  }

  return (
    <Container>
      <StyledSegment>
        <PageHeader>
          <HeaderText>
            <h2>
              <Layers size={22} />
              Corpus Groups
            </h2>
            <SubLine>
              Bundle several corpora together so an agent can search across all
              of them at once.
            </SubLine>
          </HeaderText>
          <Button
            variant="primary"
            leftIcon={<Plus size={14} />}
            onClick={openCreateModal}
            data-testid="new-corpus-group-button"
          >
            New Group
          </Button>
        </PageHeader>

        {/* Refetch failed but we still have rows — say so without discarding
            them (the full-page error branch above only fires on an empty list). */}
        {error && groups.length > 0 && (
          <WarningMessage title="Could not refresh corpus groups">
            Showing the last loaded list. {error.message}
          </WarningMessage>
        )}

        {/* The connection is server-capped, so a user with more groups than
            one page would otherwise see a silently truncated list. */}
        {totalGroupCount > groups.length && (
          <WarningMessage title="List truncated">
            Showing {groups.length} of {totalGroupCount} corpus groups.
          </WarningMessage>
        )}

        {groups.length === 0 ? (
          <Centered data-testid="corpus-groups-empty-state">
            <Layers size={40} color={OS_LEGAL_COLORS.textTertiary} />
            <h3>No corpus groups yet</h3>
            <p>
              Corpus groups let an agent search across several corpora at once.
              Create one to bundle related collections together.
            </p>
            <Button
              variant="primary"
              leftIcon={<Plus size={14} />}
              onClick={openCreateModal}
            >
              Create your first group
            </Button>
          </Centered>
        ) : (
          <ScrollableTableWrapper $minWidth="880px">
            <Table variant="bordered" data-testid="corpus-groups-table">
              <Table.Head>
                <Table.Row>
                  <Table.HeadCell>Title</Table.HeadCell>
                  <Table.HeadCell>Slug</Table.HeadCell>
                  <Table.HeadCell>Corpora</Table.HeadCell>
                  <Table.HeadCell>Default Agent</Table.HeadCell>
                  <Table.HeadCell>Visibility</Table.HeadCell>
                  <Table.HeadCell>Owner</Table.HeadCell>
                  <Table.HeadCell>Actions</Table.HeadCell>
                </Table.Row>
              </Table.Head>
              <Table.Body>
                {groups.map((group) => {
                  const memberTitles = (group.corpora?.edges ?? []).map(
                    (edge) => edge.node.title ?? ""
                  );
                  const memberCount =
                    group.corpora?.totalCount ?? memberTitles.length;
                  const previewTitles = memberTitles
                    .slice(0, CORPORA_TITLE_PREVIEW_COUNT)
                    .join(", ");
                  const elided =
                    memberCount > CORPORA_TITLE_PREVIEW_COUNT ? "…" : "";
                  const isOwner =
                    !!backendUser?.id && group.creator?.id === backendUser.id;
                  return (
                    <Table.Row key={group.id} data-testid="corpus-group-row">
                      <Table.Cell>{group.title}</Table.Cell>
                      <Table.Cell>{group.slug}</Table.Cell>
                      <Table.Cell>
                        <CorporaCell>
                          <span>{memberCount}</span>
                          {previewTitles ? (
                            <CorporaTitles>
                              {previewTitles}
                              {elided}
                            </CorporaTitles>
                          ) : null}
                        </CorporaCell>
                      </Table.Cell>
                      <Table.Cell>
                        {group.defaultAgent ? (
                          group.defaultAgent.name
                        ) : (
                          <Muted>{NO_VALUE}</Muted>
                        )}
                      </Table.Cell>
                      <Table.Cell>
                        {group.isPublic ? "Public" : "Private"}
                      </Table.Cell>
                      <Table.Cell>
                        {group.creator?.displayName ?? (
                          <Muted>{NO_VALUE}</Muted>
                        )}
                      </Table.Cell>
                      <Table.Cell>
                        {isOwner ? (
                          <>
                            <IconButton
                              aria-label={`Edit ${group.title}`}
                              onClick={() => openEditModal(group)}
                            >
                              <Pencil size={16} />
                            </IconButton>
                            <IconButton
                              aria-label={`Delete ${group.title}`}
                              onClick={() => setGroupToDelete(group)}
                            >
                              <Trash2
                                size={16}
                                color={OS_LEGAL_COLORS.danger}
                              />
                            </IconButton>
                          </>
                        ) : (
                          <Muted>Read-only</Muted>
                        )}
                      </Table.Cell>
                    </Table.Row>
                  );
                })}
              </Table.Body>
            </Table>
          </ScrollableTableWrapper>
        )}
      </StyledSegment>

      {/* Create / Edit Modal — one modal, mode derived from editingGroup */}
      <Modal
        open={showFormModal}
        onClose={() => setShowFormModal(false)}
        size="md"
        data-testid="corpus-group-form-modal"
      >
        <ModalHeader
          title={editingGroup ? "Edit Corpus Group" : "New Corpus Group"}
          onClose={() => setShowFormModal(false)}
        />
        <ModalBody>
          <FormField>
            <FormLabel htmlFor="corpus-group-title">Title</FormLabel>
            <Input
              id="corpus-group-title"
              data-testid="corpus-group-title-input"
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
              placeholder="e.g. Vendor Agreements"
              fullWidth
            />
          </FormField>

          <FormField>
            <FormLabel htmlFor="corpus-group-slug">Slug</FormLabel>
            <Input
              id="corpus-group-slug"
              data-testid="corpus-group-slug-input"
              value={form.slug}
              onChange={(e) => setForm({ ...form, slug: e.target.value })}
              placeholder="e.g. vendor-agreements"
              fullWidth
            />
            <HelperText>
              Leave blank to auto-generate one from the title.
            </HelperText>
          </FormField>

          <FormField>
            <FormLabel htmlFor="corpus-group-description">
              Description
            </FormLabel>
            <StyledTextArea
              id="corpus-group-description"
              value={form.description}
              onChange={(e) =>
                setForm({ ...form, description: e.target.value })
              }
              placeholder="What this group is for"
              rows={3}
            />
          </FormField>

          <FormField>
            <FormLabel htmlFor="corpus-group-corpora">Member corpora</FormLabel>
            <CorpusMultiSelect
              id="corpus-group-corpora"
              value={form.corpora}
              onChange={(next) => setForm({ ...form, corpora: next })}
            />
            <HelperText>
              Every corpus added here is searched together by the group's agent.
            </HelperText>
          </FormField>

          <FormField>
            <FormLabel htmlFor="corpus-group-agent">Default agent</FormLabel>
            <AgentConfigurationSelect
              id="corpus-group-agent"
              value={form.agent}
              onChange={(next) => setForm({ ...form, agent: next })}
            />
            <HelperText>
              Optional. Clear the selection to unbind the current agent.
            </HelperText>
          </FormField>

          <FormField>
            <Switch
              id="corpus-group-public"
              label="Public group"
              checked={form.isPublic}
              onChange={(e) => setForm({ ...form, isPublic: e.target.checked })}
            />
            <HelperText>
              A public group is visible to everyone on this instance. Private
              groups are visible only to you and anyone you share them with.
            </HelperText>
          </FormField>
        </ModalBody>
        <ModalFooter>
          <Button variant="secondary" onClick={() => setShowFormModal(false)}>
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={handleSubmit}
            loading={creating || updating}
            leftIcon={<Save size={16} />}
            data-testid="corpus-group-submit-button"
          >
            {editingGroup ? "Save Changes" : "Create Group"}
          </Button>
        </ModalFooter>
      </Modal>

      {/* Delete Confirmation */}
      <ConfirmModal
        visible={groupToDelete !== null}
        message={
          groupToDelete
            ? `Delete the "${groupToDelete.title}" group? The corpora in it are not deleted, only the group. This cannot be undone.`
            : ""
        }
        yesAction={handleConfirmDelete}
        // noAction is a no-op: cancelling (or overlay/escape) closes the dialog
        // via toggleModal, which clears the pending group.
        noAction={() => {}}
        toggleModal={() => setGroupToDelete(null)}
        confirmLabel="Delete"
        // Supplying this opts the modal into caller-controlled close so the
        // spinner stays visible until the mutation settles (see the delete
        // mutation's onCompleted/onError, which clear the pending group).
        confirmLoading={deleting}
      />
    </Container>
  );
};

export default CorpusGroupManagement;
