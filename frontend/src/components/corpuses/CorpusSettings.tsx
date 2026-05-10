/**
 * CorpusSettings - Main component for managing corpus settings and actions
 * Only visible to users with update permissions
 */
import React, { useEffect, useState } from "react";
import {
  Modal,
  ModalHeader,
  ModalBody,
  ModalFooter,
  Button,
} from "@os-legal/ui";
import { useQuery, useReactiveVar, useMutation } from "@apollo/client";
import { toast } from "react-toastify";
import { useNavigate } from "react-router-dom";

import { backendUserObj } from "../../graphql/cache";
import {
  GET_CORPUS_ACTIONS,
  GetCorpusActionsInput,
  GetCorpusActionsOutput,
} from "../../graphql/queries";
import {
  DELETE_CORPUS_ACTION,
  DeleteCorpusActionInput,
  DeleteCorpusActionOutput,
  UPDATE_CORPUS,
  UpdateCorpusInputs,
  UpdateCorpusOutputs,
  SET_CORPUS_VISIBILITY,
  SetCorpusVisibilityInputs,
  SetCorpusVisibilityOutputs,
} from "../../graphql/mutations";
import {
  CreateCorpusActionModal,
  CorpusActionData,
} from "./CreateCorpusActionModal";
import { RunCorpusActionModal } from "./RunCorpusActionModal";
import { CorpusMetadataSettings } from "./CorpusMetadataSettings";
import { CorpusAgentSettings } from "./CorpusAgentSettings";
import { CorpusAgentManagement } from "./CorpusAgentManagement";
import { ActionExecutionTrail } from "./ActionExecutionTrail";
import { PermissionTypes } from "../types";
import { getPermissions } from "../../utils/transform";
import { OS_LEGAL_COLORS } from "../../assets/configurations/osLegalStyles";
import { isOwnedBy } from "../../utils/userDisplay";

// Sub-components
import {
  CorpusHeader,
  CorpusInfoSection,
  VisibilitySlugSection,
  CategoriesSection,
  CorpusActionsSection,
  WorkerTokensSection,
} from "./settings";

// Shared styles
import {
  SettingsContainer,
  SettingsPageContainer,
  SettingsCard,
  SettingsCardHeader,
  SettingsCardTitle,
  SettingsCardContent,
  InfoNote,
} from "./styles/corpusSettingsStyles";

interface CorpusSettingsProps {
  corpus: {
    id: string;
    title: string;
    description: string;
    mdDescription?: string | null;
    allowComments: boolean;
    preferredEmbedder?: string | null;
    slug?: string | null;
    creator?: {
      id?: string;
      email: string;
      username?: string;
      slug?: string;
    };
    created?: string;
    modified?: string;
    isPublic?: boolean;
    myPermissions?: PermissionTypes[] | string[] | undefined;
    documents?: {
      totalCount: number;
    };
    annotations?: {
      totalCount: number;
    };
    categories?: {
      edges: Array<{
        node: {
          id: string;
          name: string;
        } | null;
      } | null>;
    };
  };
}

export const CorpusSettings: React.FC<CorpusSettingsProps> = ({ corpus }) => {
  const navigate = useNavigate();
  const currentUser = useReactiveVar(backendUserObj);

  // Check if myPermissions is already processed (array of PermissionTypes) or raw
  const permissions =
    Array.isArray(corpus.myPermissions) &&
    corpus.myPermissions.length > 0 &&
    typeof corpus.myPermissions[0] === "string" &&
    corpus.myPermissions[0].includes("CAN_")
      ? (corpus.myPermissions as PermissionTypes[]) // Already processed
      : getPermissions(corpus.myPermissions || []); // Need to process

  const canUpdate = permissions.includes(PermissionTypes.CAN_UPDATE);
  const canPermission = permissions.includes(PermissionTypes.CAN_PERMISSION);

  // Owner can always change visibility (matches backend SetCorpusVisibility
  // permission check). Compare by id only — the privacy contract redacts
  // non-self emails so email comparison is no longer reliable.
  const isOwnerByIdentity = isOwnedBy(corpus.creator, currentUser);

  // Fallback: If user has all core owner permissions, they're effectively the owner
  // This handles cases where currentUser isn't loaded yet but permissions are
  const hasFullOwnerPermissions =
    permissions.includes(PermissionTypes.CAN_CREATE) &&
    permissions.includes(PermissionTypes.CAN_UPDATE) &&
    permissions.includes(PermissionTypes.CAN_READ) &&
    permissions.includes(PermissionTypes.CAN_PUBLISH) &&
    permissions.includes(PermissionTypes.CAN_REMOVE);

  const isOwner = isOwnerByIdentity || hasFullOwnerPermissions;
  const canChangeVisibility = isOwner || canPermission;
  const isSuperuser = currentUser?.isSuperuser === true;

  // Form state
  const [slugDraft, setSlugDraft] = useState<string>("");
  const [publicDraft, setPublicDraft] = useState<boolean>(
    Boolean(corpus.isPublic)
  );
  const [originalSlug, setOriginalSlug] = useState<string>("");
  const [categoriesDraft, setCategoriesDraft] = useState<string[]>([]);
  const [originalCategories, setOriginalCategories] = useState<string[]>([]);

  useEffect(() => {
    setSlugDraft(corpus.slug || "");
    setOriginalSlug(corpus.slug || "");
    setPublicDraft(Boolean(corpus.isPublic));
    const categories =
      (corpus.categories?.edges
        ?.map((edge) => edge?.node?.id)
        .filter(Boolean) as string[]) || [];
    setCategoriesDraft(categories);
    setOriginalCategories(categories);
  }, [corpus]);

  // Update corpus mutation
  const [updateCorpusMutation, { loading: updatingCorpus }] = useMutation<
    UpdateCorpusOutputs,
    UpdateCorpusInputs
  >(UPDATE_CORPUS, {
    onCompleted: (data) => {
      if (data.updateCorpus?.ok) {
        toast.success("Updated corpus settings");
        setOriginalSlug(slugDraft);
        setOriginalCategories(categoriesDraft);

        // If slug was updated, navigate to the new URL
        if (slugDraft && slugDraft !== originalSlug && corpus.creator?.slug) {
          const newUrl = `/c/${corpus.creator.slug}/${slugDraft}`;
          navigate(newUrl, { replace: true });
        }
      } else {
        setSlugDraft(originalSlug);
        setCategoriesDraft(originalCategories);
        toast.error(data.updateCorpus?.message || "Failed to update corpus");
      }
    },
    onError: (err) => {
      setSlugDraft(originalSlug);
      setCategoriesDraft(originalCategories);
      toast.error(err.message);
    },
    update: (cache, { data }) => {
      if (data?.updateCorpus?.ok && corpus.id) {
        const cacheId = cache.identify({
          __typename: "CorpusType",
          id: corpus.id,
        });
        if (cacheId) {
          cache.modify({
            id: cacheId,
            fields: {
              slug: () => slugDraft || null,
            },
          });
        }
      }
    },
  });

  // Separate mutation for visibility changes (uses proper permission checks)
  const [setCorpusVisibility, { loading: settingVisibility }] = useMutation<
    SetCorpusVisibilityOutputs,
    SetCorpusVisibilityInputs
  >(SET_CORPUS_VISIBILITY, {
    onCompleted: (data) => {
      if (data.setCorpusVisibility?.ok) {
        toast.success(data.setCorpusVisibility.message);
      } else {
        setPublicDraft(Boolean(corpus.isPublic));
        toast.error(
          data.setCorpusVisibility?.message || "Failed to update visibility"
        );
      }
    },
    onError: (err) => {
      setPublicDraft(Boolean(corpus.isPublic));
      toast.error(err.message);
    },
    update: (cache, { data }) => {
      if (data?.setCorpusVisibility?.ok && corpus.id) {
        const cacheId = cache.identify({
          __typename: "CorpusType",
          id: corpus.id,
        });
        if (cacheId) {
          cache.modify({
            id: cacheId,
            fields: {
              isPublic: () => publicDraft,
            },
          });
        }
      }
    },
  });

  // Modal and action state
  const [isModalOpen, setIsModalOpen] = React.useState(false);
  const [actionToDelete, setActionToDelete] = React.useState<string | null>(
    null
  );
  const [actionToEdit, setActionToEdit] =
    React.useState<CorpusActionData | null>(null);
  const [actionToRun, setActionToRun] = useState<{
    id: string;
    name: string;
  } | null>(null);

  // Fetch corpus actions
  const { data: actionsData, refetch: refetchActions } = useQuery<
    GetCorpusActionsOutput,
    GetCorpusActionsInput
  >(GET_CORPUS_ACTIONS, {
    variables: { corpusId: corpus.id },
    fetchPolicy: "network-only",
  });

  // Refetch actions when component mounts
  useEffect(() => {
    refetchActions();
  }, []);

  // Delete action mutation
  const [deleteCorpusAction] = useMutation<
    DeleteCorpusActionOutput,
    DeleteCorpusActionInput
  >(DELETE_CORPUS_ACTION, {
    onCompleted: (data) => {
      if (data.deleteCorpusAction.ok) {
        toast.success("Action deleted successfully");
        refetchActions();
      } else {
        toast.error(
          `Failed to delete action: ${data.deleteCorpusAction.message}`
        );
      }
    },
    onError: (error) => {
      toast.error(`Error deleting action: ${error.message}`);
    },
  });

  const handleDelete = async (id: string) => {
    try {
      await deleteCorpusAction({
        variables: { id },
      });
    } catch (error) {
      // Error handled by onError callback
    } finally {
      setActionToDelete(null);
    }
  };

  // Handle visibility/slug save
  const handleVisibilitySlugSave = () => {
    const visibilityChanged = publicDraft !== Boolean(corpus.isPublic);
    const slugChanged = slugDraft !== originalSlug;

    if (canChangeVisibility && visibilityChanged) {
      setCorpusVisibility({
        variables: {
          corpusId: corpus.id,
          isPublic: publicDraft,
        },
      });
    }

    if (canUpdate && slugChanged) {
      updateCorpusMutation({
        variables: {
          id: corpus.id,
          slug: slugDraft || undefined,
        },
      });
    }

    if (!visibilityChanged && !slugChanged) {
      toast.info("No changes to save");
    }
  };

  // Handle categories save
  const handleCategoriesSave = () => {
    updateCorpusMutation({
      variables: {
        id: corpus.id,
        categories: categoriesDraft,
      },
    });
  };

  // Transform actions data for the component
  const actions =
    actionsData?.corpusActions?.edges.map(({ node }) => node) || [];

  return (
    <SettingsContainer>
      <SettingsPageContainer>
        <CorpusHeader corpus={corpus} />

        <CorpusInfoSection corpus={corpus} />

        <VisibilitySlugSection
          publicDraft={publicDraft}
          setPublicDraft={setPublicDraft}
          slugDraft={slugDraft}
          setSlugDraft={setSlugDraft}
          originalSlug={originalSlug}
          originalIsPublic={Boolean(corpus.isPublic)}
          canUpdate={canUpdate}
          canChangeVisibility={canChangeVisibility}
          onSave={handleVisibilitySlugSave}
          loading={updatingCorpus || settingVisibility}
        />

        <CategoriesSection
          categoriesDraft={categoriesDraft}
          setCategoriesDraft={setCategoriesDraft}
          originalCategories={originalCategories}
          canUpdate={canUpdate}
          onSave={handleCategoriesSave}
          loading={updatingCorpus}
        />

        <CorpusActionsSection
          corpusId={corpus.id}
          actions={actions}
          onAddAction={() => setIsModalOpen(true)}
          onEditAction={(action) => {
            setActionToEdit(action);
            setIsModalOpen(true);
          }}
          onDeleteAction={(id) => setActionToDelete(id)}
          onRunAction={(action) =>
            setActionToRun({ id: action.id, name: action.name })
          }
          onUpdate={() => refetchActions()}
          isSuperuser={isSuperuser}
        />

        {/* Action Execution History - Permission Gated to owner/admin/editor */}
        {(isOwner || canUpdate || canPermission) && (
          <SettingsCard id="action-execution-history-section">
            <SettingsCardHeader>
              <SettingsCardTitle>Action Execution History</SettingsCardTitle>
            </SettingsCardHeader>
            <SettingsCardContent>
              <InfoNote>
                This section shows the <strong>execution history</strong> of all
                corpus actions. You can see when actions were{" "}
                <span className="highlight">triggered</span>, their{" "}
                <span className="highlight">status</span>, and what{" "}
                <span className="highlight">
                  objects they created or modified
                </span>
                . Click on affected objects to navigate to them.
              </InfoNote>
              <ActionExecutionTrail corpusId={corpus.id} />
            </SettingsCardContent>
          </SettingsCard>
        )}

        <SettingsCard>
          <SettingsCardHeader>
            <SettingsCardTitle>Metadata Fields</SettingsCardTitle>
          </SettingsCardHeader>
          <SettingsCardContent>
            <CorpusMetadataSettings corpusId={corpus.id} />
          </SettingsCardContent>
        </SettingsCard>

        <SettingsCard>
          <SettingsCardHeader>
            <SettingsCardTitle>Agent Instructions</SettingsCardTitle>
          </SettingsCardHeader>
          <SettingsCardContent>
            <CorpusAgentSettings
              corpusId={corpus.id}
              corpusAgentInstructions={(corpus as any).corpusAgentInstructions}
              documentAgentInstructions={
                (corpus as any).documentAgentInstructions
              }
              canUpdate={canUpdate}
            />
          </SettingsCardContent>
        </SettingsCard>

        <SettingsCard>
          <SettingsCardHeader>
            <SettingsCardTitle>Corpus Agents</SettingsCardTitle>
          </SettingsCardHeader>
          <SettingsCardContent>
            <CorpusAgentManagement corpusId={corpus.id} canUpdate={canUpdate} />
          </SettingsCardContent>
        </SettingsCard>

        {(isSuperuser || isOwner) && (
          <WorkerTokensSection
            corpusId={corpus.id}
            isSuperuser={isSuperuser}
            isCreator={isOwner}
          />
        )}

        <CreateCorpusActionModal
          corpusId={corpus.id}
          open={isModalOpen}
          onClose={() => {
            setIsModalOpen(false);
            setActionToEdit(null);
          }}
          onSuccess={() => {
            setIsModalOpen(false);
            setActionToEdit(null);
            refetchActions();
          }}
          actionToEdit={actionToEdit}
        />

        {actionToRun && (
          <RunCorpusActionModal
            open={!!actionToRun}
            corpusId={corpus.id}
            actionId={actionToRun.id}
            actionName={actionToRun.name}
            onClose={() => setActionToRun(null)}
          />
        )}

        <Modal open={!!actionToDelete} onClose={() => setActionToDelete(null)}>
          <ModalHeader>Confirm Delete</ModalHeader>
          <ModalBody>
            Are you sure you want to delete this action? This cannot be undone.
          </ModalBody>
          <ModalFooter>
            <Button variant="secondary" onClick={() => setActionToDelete(null)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              onClick={() => actionToDelete && handleDelete(actionToDelete)}
            >
              Delete
            </Button>
          </ModalFooter>
        </Modal>
      </SettingsPageContainer>
    </SettingsContainer>
  );
};
