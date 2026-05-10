import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Spinner } from "@os-legal/ui";
import Fuse from "fuse.js";
import { useQuery, useMutation, useReactiveVar } from "@apollo/client";
import {
  GetLabelsetWithLabelsInputs,
  GetLabelsetWithLabelsOutputs,
  GET_LABELSET_WITH_ALL_LABELS,
} from "../../graphql/queries";
import {
  DeleteMultipleAnnotationLabelOutputs,
  DeleteMultipleAnnotationLabelInputs,
  DELETE_MULTIPLE_ANNOTATION_LABELS,
  CreateAnnotationLabelForLabelsetOutputs,
  CreateAnnotationLabelForLabelsetInputs,
  CREATE_ANNOTATION_LABEL_FOR_LABELSET,
  DeleteLabelsetInputs,
  DeleteLabelsetOutputs,
  DELETE_LABELSET,
  UpdateAnnotationLabelInputs,
  UpdateAnnotationLabelOutputs,
  UPDATE_ANNOTATION_LABEL,
} from "../../graphql/mutations";
import { ConfirmModal } from "../widgets/modals/ConfirmModal";
import { openedLabelset } from "../../graphql/cache";
import { AnnotationLabelType, LabelType } from "../../types/graphql-api";
import { toast } from "react-toastify";
import { getPermissions } from "../../utils/transform";
import { getCreatorDisplay } from "../../utils/userDisplay";
import { PermissionTypes } from "../types";
import { OS_LEGAL_COLORS } from "../../assets/configurations/osLegalStyles";

// Import extracted components from detail folder
import {
  // Icons
  ChevronLeftIcon,
  OverviewIcon,
  DocLabelIcon,
  SpanLabelIcon,
  TextLabelIcon,
  RelationshipIcon,
  ShareIcon,
  EditIcon,
  TrashIcon,
  DownloadIcon,
  SaveIcon,
  CloseIcon,
  GripIcon,
  SearchIcon,
  PlusIcon,
  LabelSetIcon,
  // Styled Components
  PageContainer,
  PageLayout,
  Sidebar,
  SidebarHeader,
  BackLink,
  SidebarNav,
  NavItem,
  SidebarFooter,
  MobileNav,
  MobileNavTabs,
  MobileNavTab,
  EditDetailsButton,
  MainContainer,
  MainHeader,
  MobileBackLink,
  HeaderRow,
  HeaderContent,
  TitleRow,
  Title,
  Badge,
  Meta,
  MetaSep,
  HeaderActions,
  ShareButton,
  MainContent,
  ContentInner,
  OverviewSection,
  OverviewHero,
  OverviewIconBox,
  OverviewDetails,
  OverviewDescription,
  OverviewStats,
  StatCard,
  StatValue,
  StatLabel,
  OverviewActions,
  ActionButton,
  LabelsSection,
  SearchContainer,
  SearchInput,
  SearchIconWrapper,
  LabelsList,
  LabelItem,
  LabelGrip,
  LabelColor,
  LabelContent,
  LabelName,
  LabelDescription,
  LabelActions,
  LabelActionButton,
  LabelEditForm,
  LabelEditRow,
  LabelEditInput,
  LabelEditTextarea,
  LabelEditLabel,
  ColorInput,
  LabelEditActions,
  AddLabelButton,
  EmptyState,
  EmptyStateIcon,
  EmptyStateTitle,
  EmptyStateDescription,
  LoadingContainer,
  // Color constants
  DEFAULT_LABEL_COLOR,
  PRIMARY_LABEL_COLOR,
} from "./detail";

const fuse_options = {
  includeScore: false,
  findAllMatches: true,
  threshold: 0.3, // Stricter matching (0 = exact, 1 = match anything)
  keys: ["text", "description"],
};

// ═══════════════════════════════════════════════════════════════════════════════
// TYPES
// ═══════════════════════════════════════════════════════════════════════════════

type TabType =
  | "overview"
  | "text_labels"
  | "doc_labels"
  | "relationship_labels"
  | "span_labels"
  | "sharing";

interface LabelSetDetailPageProps {
  onClose?: () => void;
}

// ═══════════════════════════════════════════════════════════════════════════════
// COLOR UTILITIES
// ═══════════════════════════════════════════════════════════════════════════════

/**
 * Validates if a string is a valid hex color (3 or 6 character format)
 * Accepts with or without leading #
 */
const isValidHexColor = (color: string): boolean => {
  return /^#?([0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})$/.test(color);
};

/**
 * Expands a 3-character hex color to 6-character format
 * e.g., "abc" becomes "aabbcc"
 */
const expandHexColor = (color: string): string => {
  if (color.length === 3) {
    return color
      .split("")
      .map((c) => c + c)
      .join("");
  }
  return color;
};

/**
 * Sanitizes a color value, returning the fallback if invalid
 * Strips leading #, validates format, and expands 3-char to 6-char
 */
const sanitizeColor = (
  color: string | null | undefined,
  fallback: string = DEFAULT_LABEL_COLOR
): string => {
  if (!color) return fallback;
  const cleaned = color.replace("#", "");
  if (!isValidHexColor(cleaned)) return fallback;
  return expandHexColor(cleaned);
};

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export const LabelSetDetailPage: React.FC<LabelSetDetailPageProps> = ({
  onClose,
}) => {
  const navigate = useNavigate();
  const opened_labelset = useReactiveVar(openedLabelset);

  const [activeTab, setActiveTab] = useState<TabType>("overview");
  const [searchTerm, setSearchTerm] = useState<string>("");
  const [showDeleteConfirm, setShowDeleteConfirm] = useState<boolean>(false);
  const [editingLabelId, setEditingLabelId] = useState<string | null>(null);
  const [creatingLabelType, setCreatingLabelType] = useState<LabelType | null>(
    null
  );
  const [editForm, setEditForm] = useState<{
    text: string;
    description: string;
    color: string;
  }>({ text: "", description: "", color: "" });

  const my_permissions = getPermissions(
    opened_labelset?.myPermissions ? opened_labelset.myPermissions : []
  );
  const canUpdate = my_permissions.includes(PermissionTypes.CAN_UPDATE);
  const canRemove = my_permissions.includes(PermissionTypes.CAN_REMOVE);

  // Mutations with loading states to prevent race conditions
  const [createAnnotationLabelForLabelset, { loading: createLoading }] =
    useMutation<
      CreateAnnotationLabelForLabelsetOutputs,
      CreateAnnotationLabelForLabelsetInputs
    >(CREATE_ANNOTATION_LABEL_FOR_LABELSET);

  const [deleteMultipleLabels, { loading: deleteLabelsLoading }] = useMutation<
    DeleteMultipleAnnotationLabelOutputs,
    DeleteMultipleAnnotationLabelInputs
  >(DELETE_MULTIPLE_ANNOTATION_LABELS);

  const [updateAnnotationLabel, { loading: updateLoading }] = useMutation<
    UpdateAnnotationLabelOutputs,
    UpdateAnnotationLabelInputs
  >(UPDATE_ANNOTATION_LABEL);

  const [deleteLabelset, { loading: delete_loading }] = useMutation<
    DeleteLabelsetOutputs,
    DeleteLabelsetInputs
  >(DELETE_LABELSET);

  // Combined loading state for any mutation in progress
  const isMutating =
    createLoading || deleteLabelsLoading || updateLoading || delete_loading;

  // Query
  const {
    refetch,
    loading: label_set_loading,
    error: label_set_fetch_error,
    data: label_set_data,
  } = useQuery<GetLabelsetWithLabelsOutputs, GetLabelsetWithLabelsInputs>(
    GET_LABELSET_WITH_ALL_LABELS,
    {
      variables: {
        id: opened_labelset?.id ? opened_labelset.id : "",
      },
      skip: !opened_labelset?.id,
      notifyOnNetworkStatusChange: true,
    }
  );

  // Handlers
  const handleBack = () => {
    if (onClose) {
      onClose();
    } else {
      // CentralRouteManager Phase 1 clears openedLabelset on browse routes.
      navigate("/label_sets");
    }
  };

  const handleDeleteLabel = (labels: AnnotationLabelType[]) => {
    if (!labels || labels.length === 0) {
      toast.error("No labels selected for deletion");
      return;
    }

    if (!canRemove) {
      toast.error("You don't have permission to delete labels");
      return;
    }

    if (isMutating) {
      toast.warning("Please wait for current operation to complete");
      return;
    }

    deleteMultipleLabels({
      variables: {
        annotationLabelIdsToDelete: labels.map((label) => label.id),
      },
    })
      .then((result) => {
        if (result.data?.deleteMultipleAnnotationLabels?.ok) {
          refetch();
          toast.success("Label deleted successfully");
        } else {
          toast.error(
            result.data?.deleteMultipleAnnotationLabels?.message ||
              "Failed to delete label"
          );
        }
      })
      .catch((err) => {
        console.error("Error deleting label", err);
        toast.error("Failed to delete label");
      });
  };

  const handleStartEdit = (label: AnnotationLabelType) => {
    if (isMutating) {
      toast.warning("Please wait for current operation to complete");
      return;
    }
    setEditingLabelId(label.id);
    setCreatingLabelType(null); // Cancel any create in progress
    setEditForm({
      text: label.text || "",
      description: label.description || "",
      color: label.color || DEFAULT_LABEL_COLOR,
    });
  };

  const handleCancelEdit = () => {
    setEditingLabelId(null);
    setCreatingLabelType(null);
    setEditForm({ text: "", description: "", color: "" });
  };

  const handleSaveEdit = () => {
    if (!canUpdate) {
      toast.error("You don't have permission to edit labels");
      return;
    }

    if (!editingLabelId) return;

    if (isMutating) {
      return; // Already submitting, prevent double-click
    }

    updateAnnotationLabel({
      variables: {
        id: editingLabelId,
        text: editForm.text,
        description: editForm.description,
        color: sanitizeColor(editForm.color),
      },
    })
      .then((result) => {
        if (result.data?.updateAnnotationLabel?.ok) {
          refetch();
          toast.success("Label updated successfully");
          handleCancelEdit();
        } else {
          toast.error(
            result.data?.updateAnnotationLabel?.message ||
              "Failed to update label"
          );
        }
      })
      .catch((err) => {
        console.error("Error updating label", err);
        toast.error("Failed to update label");
      });
  };

  const handleStartCreate = (labelType: LabelType) => {
    if (isMutating) {
      toast.warning("Please wait for current operation to complete");
      return;
    }
    // Cancel any existing edit
    setEditingLabelId(null);
    // Start creating a new label
    setCreatingLabelType(labelType);
    setEditForm({
      text: "",
      description: "",
      color: PRIMARY_LABEL_COLOR,
    });
  };

  const handleSaveCreate = () => {
    if (!canUpdate) {
      toast.error("You don't have permission to create labels");
      return;
    }

    if (!creatingLabelType || !editForm.text.trim()) {
      toast.error("Please enter a label name");
      return;
    }

    if (isMutating) {
      return; // Already submitting, prevent double-click
    }

    createAnnotationLabelForLabelset({
      variables: {
        color: sanitizeColor(editForm.color, PRIMARY_LABEL_COLOR),
        description: editForm.description,
        icon: "tag",
        text: editForm.text,
        labelType: creatingLabelType,
        labelsetId: opened_labelset?.id ? opened_labelset.id : "",
      },
    })
      .then(() => {
        toast.success("Label created successfully");
        refetch();
        handleCancelEdit();
      })
      .catch((err) => {
        toast.error("Failed to create label");
        console.error("Error creating label:", err);
      });
  };

  const handleExportJSON = () => {
    if (!label_set_data?.labelset) return;
    const exportData = {
      title: label_set_data.labelset.title,
      description: label_set_data.labelset.description,
      labels: label_set_data.labelset.allAnnotationLabels?.map((label) => ({
        text: label?.text,
        description: label?.description,
        color: label?.color,
        icon: label?.icon,
        labelType: label?.labelType,
      })),
    };
    const blob = new Blob([JSON.stringify(exportData, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${label_set_data.labelset.title || "labelset"}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    toast.success("Label set exported successfully");
  };

  const handleDelete = () => {
    if (!canRemove) {
      toast.error("You don't have permission to delete this labelset");
      return;
    }

    if (!opened_labelset?.id) return;

    deleteLabelset({
      variables: { id: opened_labelset.id },
    })
      .then((result) => {
        if (result.data?.deleteLabelset?.ok) {
          toast.success("Label set deleted successfully");
          // CentralRouteManager Phase 1 clears openedLabelset on browse routes.
          navigate("/label_sets");
        } else {
          toast.error(
            result.data?.deleteLabelset?.message || "Failed to delete label set"
          );
        }
      })
      .catch((err) => {
        console.error("Error deleting labelset:", err);
        toast.error("Failed to delete label set");
      });
    setShowDeleteConfirm(false);
  };

  const handleShare = () => {
    toast.info("Share functionality coming soon");
  };

  const handleEditDetails = () => {
    toast.info("Edit details functionality coming soon");
  };

  // Loading state
  if (label_set_loading && !label_set_data) {
    return (
      <PageContainer>
        <LoadingContainer>
          <Spinner size="lg" />
          <div
            style={{ marginTop: "1rem", color: OS_LEGAL_COLORS.textSecondary }}
          >
            Loading label set...
          </div>
        </LoadingContainer>
      </PageContainer>
    );
  }

  // Error state
  if (label_set_fetch_error) {
    return (
      <PageContainer>
        <MainContent>
          <div
            style={{
              padding: "1rem 1.5rem",
              borderRadius: "8px",
              background: OS_LEGAL_COLORS.dangerSurfaceHover,
              border: "1px solid #fca5a5",
              color: OS_LEGAL_COLORS.dangerText,
            }}
          >
            <strong>Error loading label set</strong>
            <p>{label_set_fetch_error.message}</p>
          </div>
        </MainContent>
      </PageContainer>
    );
  }

  // Get labels from data
  const labels: AnnotationLabelType[] = label_set_data?.labelset
    ?.allAnnotationLabels
    ? (label_set_data.labelset.allAnnotationLabels.filter(
        (item) => item!!
      ) as AnnotationLabelType[])
    : [];

  // Filter labels by type
  const text_labels = labels.filter(
    (label) => label.labelType === LabelType.TokenLabel
  );
  const doc_type_labels = labels.filter(
    (label) => label.labelType === LabelType.DocTypeLabel
  );
  const relationship_labels = labels.filter(
    (label) => label.labelType === LabelType.RelationshipLabel
  );
  const span_labels = labels.filter(
    (label) => label.labelType === LabelType.SpanLabel
  );

  // Setup fuzzy search
  // Note: Not using useMemo here as it causes React error #310 in Playwright component tests
  // This is a known issue with Playwright CT and certain hook usage patterns
  const text_label_fuse = new Fuse(text_labels, fuse_options);
  const doc_label_fuse = new Fuse(doc_type_labels, fuse_options);
  const relationship_label_fuse = new Fuse(relationship_labels, fuse_options);
  const span_label_fuse = new Fuse(span_labels, fuse_options);

  // Apply search filter
  const filterLabels = (
    labels: AnnotationLabelType[],
    fuse: Fuse<AnnotationLabelType>
  ) => {
    if (searchTerm.length > 0) {
      return fuse.search(searchTerm).map((item) => item.item);
    }
    return labels;
  };

  const text_label_results = filterLabels(text_labels, text_label_fuse);
  const doc_label_results = filterLabels(doc_type_labels, doc_label_fuse);
  const relationship_label_results = filterLabels(
    relationship_labels,
    relationship_label_fuse
  );
  const span_label_results = filterLabels(span_labels, span_label_fuse);

  const totalLabels =
    (label_set_data?.labelset?.docLabelCount || 0) +
    (label_set_data?.labelset?.spanLabelCount || 0) +
    (label_set_data?.labelset?.tokenLabelCount || 0);

  const labelset = label_set_data?.labelset || opened_labelset;

  // Render label list
  const renderLabelsList = (
    labels: AnnotationLabelType[],
    labelType: LabelType,
    labelTypeName: string
  ) => {
    if (labels.length === 0 && !searchTerm) {
      // If we're creating, show the form instead of empty state
      if (creatingLabelType === labelType) {
        return (
          <LabelEditForm>
            <LabelEditRow>
              <LabelEditLabel>Name</LabelEditLabel>
              <LabelEditInput
                type="text"
                value={editForm.text}
                onChange={(e) =>
                  setEditForm({ ...editForm, text: e.target.value })
                }
                placeholder="Enter label name"
                autoFocus
              />
            </LabelEditRow>
            <LabelEditRow>
              <LabelEditLabel>Description</LabelEditLabel>
              <LabelEditTextarea
                value={editForm.description}
                onChange={(e) =>
                  setEditForm({ ...editForm, description: e.target.value })
                }
                placeholder="Describe what this label is used for"
              />
            </LabelEditRow>
            <LabelEditRow>
              <LabelEditLabel>Color</LabelEditLabel>
              <ColorInput
                type="color"
                value={`#${editForm.color}`}
                onChange={(e) =>
                  setEditForm({
                    ...editForm,
                    color: e.target.value.replace("#", ""),
                  })
                }
              />
              <LabelColor $color={`#${editForm.color}`} />
            </LabelEditRow>
            <LabelEditActions>
              <LabelActionButton
                className="danger"
                title="Cancel"
                onClick={handleCancelEdit}
              >
                <CloseIcon />
              </LabelActionButton>
              <LabelActionButton
                className="success"
                title="Create"
                onClick={handleSaveCreate}
              >
                <SaveIcon />
              </LabelActionButton>
            </LabelEditActions>
          </LabelEditForm>
        );
      }

      return (
        <EmptyState>
          <EmptyStateIcon>
            <LabelSetIcon />
          </EmptyStateIcon>
          <EmptyStateTitle>
            No {labelTypeName.toLowerCase()} yet
          </EmptyStateTitle>
          <EmptyStateDescription>
            {labelTypeName} are used to categorize and annotate your documents.
          </EmptyStateDescription>
          {canUpdate && (
            <AddLabelButton onClick={() => handleStartCreate(labelType)}>
              <PlusIcon /> Add First Label
            </AddLabelButton>
          )}
        </EmptyState>
      );
    }

    if (labels.length === 0 && searchTerm) {
      return (
        <EmptyState>
          <EmptyStateTitle>No labels match "{searchTerm}"</EmptyStateTitle>
          <EmptyStateDescription>
            Try a different search term or add a new label.
          </EmptyStateDescription>
        </EmptyState>
      );
    }

    // Check if we're creating a new label of this type
    const isCreating = creatingLabelType === labelType;

    return (
      <>
        {/* Create form at top when adding new label */}
        {isCreating && (
          <LabelEditForm>
            <LabelEditRow>
              <LabelEditLabel>Name</LabelEditLabel>
              <LabelEditInput
                type="text"
                value={editForm.text}
                onChange={(e) =>
                  setEditForm({ ...editForm, text: e.target.value })
                }
                placeholder="Enter label name"
                autoFocus
              />
            </LabelEditRow>
            <LabelEditRow>
              <LabelEditLabel>Description</LabelEditLabel>
              <LabelEditTextarea
                value={editForm.description}
                onChange={(e) =>
                  setEditForm({ ...editForm, description: e.target.value })
                }
                placeholder="Describe what this label is used for"
              />
            </LabelEditRow>
            <LabelEditRow>
              <LabelEditLabel>Color</LabelEditLabel>
              <ColorInput
                type="color"
                value={`#${editForm.color}`}
                onChange={(e) =>
                  setEditForm({
                    ...editForm,
                    color: e.target.value.replace("#", ""),
                  })
                }
              />
              <LabelColor $color={`#${editForm.color}`} />
            </LabelEditRow>
            <LabelEditActions>
              <LabelActionButton
                className="danger"
                title="Cancel"
                onClick={handleCancelEdit}
              >
                <CloseIcon />
              </LabelActionButton>
              <LabelActionButton
                className="success"
                title="Create"
                onClick={handleSaveCreate}
              >
                <SaveIcon />
              </LabelActionButton>
            </LabelEditActions>
          </LabelEditForm>
        )}

        {/* Existing labels list */}
        <LabelsList>
          {labels.map((label) =>
            editingLabelId === label.id ? (
              <LabelEditForm key={label.id}>
                <LabelEditRow>
                  <LabelEditLabel>Name</LabelEditLabel>
                  <LabelEditInput
                    type="text"
                    value={editForm.text}
                    onChange={(e) =>
                      setEditForm({ ...editForm, text: e.target.value })
                    }
                    placeholder="Label name"
                  />
                </LabelEditRow>
                <LabelEditRow>
                  <LabelEditLabel>Description</LabelEditLabel>
                  <LabelEditTextarea
                    value={editForm.description}
                    onChange={(e) =>
                      setEditForm({ ...editForm, description: e.target.value })
                    }
                    placeholder="Label description"
                  />
                </LabelEditRow>
                <LabelEditRow>
                  <LabelEditLabel>Color</LabelEditLabel>
                  <ColorInput
                    type="color"
                    value={`#${editForm.color}`}
                    onChange={(e) =>
                      setEditForm({
                        ...editForm,
                        color: e.target.value.replace("#", ""),
                      })
                    }
                  />
                  <LabelColor $color={`#${editForm.color}`} />
                </LabelEditRow>
                <LabelEditActions>
                  <LabelActionButton
                    className="danger"
                    title="Cancel"
                    onClick={handleCancelEdit}
                  >
                    <CloseIcon />
                  </LabelActionButton>
                  <LabelActionButton
                    className="success"
                    title="Save"
                    onClick={handleSaveEdit}
                  >
                    <SaveIcon />
                  </LabelActionButton>
                </LabelEditActions>
              </LabelEditForm>
            ) : (
              <LabelItem key={label.id}>
                <LabelGrip>
                  <GripIcon />
                </LabelGrip>
                <LabelColor $color={`#${label.color || DEFAULT_LABEL_COLOR}`} />
                <LabelContent>
                  <LabelName>{label.text}</LabelName>
                  <LabelDescription>{label.description}</LabelDescription>
                </LabelContent>
                <LabelActions className="label-actions">
                  {canUpdate && (
                    <LabelActionButton
                      title="Edit"
                      onClick={() => handleStartEdit(label)}
                    >
                      <EditIcon />
                    </LabelActionButton>
                  )}
                  {canUpdate && (
                    <LabelActionButton
                      className="danger"
                      title="Delete"
                      onClick={() => handleDeleteLabel([label])}
                    >
                      <TrashIcon />
                    </LabelActionButton>
                  )}
                </LabelActions>
              </LabelItem>
            )
          )}
        </LabelsList>

        {/* Add button - hidden when already creating */}
        {canUpdate && !isCreating && (
          <AddLabelButton onClick={() => handleStartCreate(labelType)}>
            <PlusIcon /> Add Label
          </AddLabelButton>
        )}
      </>
    );
  };

  // Render content based on active tab
  const renderContent = () => {
    switch (activeTab) {
      case "overview":
        return (
          <OverviewSection>
            <OverviewHero>
              <OverviewIconBox>
                {labelset?.icon ? (
                  <img src={labelset.icon} alt="Label set icon" />
                ) : (
                  <LabelSetIcon />
                )}
              </OverviewIconBox>
              <OverviewDetails>
                <OverviewDescription>
                  {labelset?.description || "No description provided."}
                </OverviewDescription>

                <OverviewStats>
                  <StatCard>
                    <StatValue>{totalLabels}</StatValue>
                    <StatLabel>Total Labels</StatLabel>
                  </StatCard>
                  <StatCard>
                    <StatValue>
                      {label_set_data?.labelset?.docLabelCount || 0}
                    </StatValue>
                    <StatLabel>Doc Labels</StatLabel>
                  </StatCard>
                  <StatCard>
                    <StatValue>
                      {label_set_data?.labelset?.spanLabelCount || 0}
                    </StatValue>
                    <StatLabel>Span Labels</StatLabel>
                  </StatCard>
                </OverviewStats>

                <OverviewActions>
                  <ActionButton onClick={handleExportJSON}>
                    <DownloadIcon />
                    Export JSON
                  </ActionButton>
                  {canRemove && (
                    <ActionButton
                      className="danger"
                      onClick={() => setShowDeleteConfirm(true)}
                    >
                      <TrashIcon />
                      Delete
                    </ActionButton>
                  )}
                </OverviewActions>
              </OverviewDetails>
            </OverviewHero>
          </OverviewSection>
        );

      case "text_labels":
        return (
          <LabelsSection>
            <SearchContainer>
              <SearchIconWrapper>
                <SearchIcon />
              </SearchIconWrapper>
              <SearchInput
                type="text"
                placeholder="Search text labels..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
              />
            </SearchContainer>
            {renderLabelsList(
              text_label_results,
              LabelType.TokenLabel,
              "Text Labels"
            )}
          </LabelsSection>
        );

      case "doc_labels":
        return (
          <LabelsSection>
            <SearchContainer>
              <SearchIconWrapper>
                <SearchIcon />
              </SearchIconWrapper>
              <SearchInput
                type="text"
                placeholder="Search doc labels..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
              />
            </SearchContainer>
            {renderLabelsList(
              doc_label_results,
              LabelType.DocTypeLabel,
              "Doc Labels"
            )}
          </LabelsSection>
        );

      case "relationship_labels":
        return (
          <LabelsSection>
            <SearchContainer>
              <SearchIconWrapper>
                <SearchIcon />
              </SearchIconWrapper>
              <SearchInput
                type="text"
                placeholder="Search relationship labels..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
              />
            </SearchContainer>
            {renderLabelsList(
              relationship_label_results,
              LabelType.RelationshipLabel,
              "Relationship Labels"
            )}
          </LabelsSection>
        );

      case "span_labels":
        return (
          <LabelsSection>
            <SearchContainer>
              <SearchIconWrapper>
                <SearchIcon />
              </SearchIconWrapper>
              <SearchInput
                type="text"
                placeholder="Search labels..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
              />
            </SearchContainer>
            {renderLabelsList(
              span_label_results,
              LabelType.SpanLabel,
              "Span Labels"
            )}
          </LabelsSection>
        );

      case "sharing":
        return (
          <div
            style={{
              padding: "1rem 1.5rem",
              borderRadius: "8px",
              background: OS_LEGAL_COLORS.blueSurface,
              border: `1px solid ${OS_LEGAL_COLORS.blueBorder}`,
              color: OS_LEGAL_COLORS.blueDark,
            }}
          >
            <strong>Sharing Settings</strong>
            <p>Sharing configuration will be available here.</p>
          </div>
        );

      default:
        return null;
    }
  };

  return (
    <PageContainer>
      {(label_set_loading || delete_loading) && (
        <div
          style={{
            position: "absolute",
            inset: 0,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            background: "rgba(255, 255, 255, 0.85)",
            zIndex: 100,
          }}
        >
          <Spinner size="lg" />
          <div
            style={{ marginTop: "1rem", color: OS_LEGAL_COLORS.textSecondary }}
          >
            {delete_loading ? "Deleting..." : "Loading..."}
          </div>
        </div>
      )}

      <PageLayout>
        <Sidebar>
          <SidebarHeader>
            <BackLink onClick={handleBack}>
              <ChevronLeftIcon />
              Label Sets
            </BackLink>
          </SidebarHeader>

          <SidebarNav>
            <NavItem
              $active={activeTab === "overview"}
              onClick={() => setActiveTab("overview")}
            >
              <span className="nav-icon">
                <OverviewIcon />
              </span>
              Overview
            </NavItem>
            <NavItem
              $active={activeTab === "text_labels"}
              onClick={() => setActiveTab("text_labels")}
            >
              <span className="nav-icon">
                <TextLabelIcon />
              </span>
              Text Labels
              <span className="nav-badge">{text_labels.length}</span>
            </NavItem>
            <NavItem
              $active={activeTab === "doc_labels"}
              onClick={() => setActiveTab("doc_labels")}
            >
              <span className="nav-icon">
                <DocLabelIcon />
              </span>
              Doc Labels
              <span className="nav-badge">{doc_type_labels.length}</span>
            </NavItem>
            <NavItem
              $active={activeTab === "relationship_labels"}
              onClick={() => setActiveTab("relationship_labels")}
            >
              <span className="nav-icon">
                <RelationshipIcon />
              </span>
              Relationships
              <span className="nav-badge">{relationship_labels.length}</span>
            </NavItem>
            <NavItem
              $active={activeTab === "span_labels"}
              onClick={() => setActiveTab("span_labels")}
            >
              <span className="nav-icon">
                <SpanLabelIcon />
              </span>
              Span Labels
              <span className="nav-badge">{span_labels.length}</span>
            </NavItem>
            <NavItem
              $active={activeTab === "sharing"}
              onClick={() => setActiveTab("sharing")}
            >
              <span className="nav-icon">
                <ShareIcon />
              </span>
              Sharing
            </NavItem>
          </SidebarNav>

          {canUpdate && (
            <SidebarFooter>
              <EditDetailsButton onClick={handleEditDetails}>
                <EditIcon />
                Edit Details
              </EditDetailsButton>
            </SidebarFooter>
          )}
        </Sidebar>

        <MainContainer>
          <MainHeader>
            <MobileBackLink onClick={handleBack}>
              <ChevronLeftIcon />
              Label Sets
            </MobileBackLink>
            <HeaderRow>
              <HeaderContent>
                <TitleRow>
                  <Title>{labelset?.title || "Untitled Label Set"}</Title>
                  <Badge>{labelset?.isPublic ? "Public" : "Private"}</Badge>
                </TitleRow>
                <Meta>
                  <span>Created by {getCreatorDisplay(labelset?.creator)}</span>
                  <MetaSep>·</MetaSep>
                  <span>
                    {totalLabels} {totalLabels === 1 ? "label" : "labels"}
                  </span>
                </Meta>
              </HeaderContent>
              <HeaderActions>
                <ShareButton onClick={handleShare}>
                  <ShareIcon />
                  Share
                </ShareButton>
              </HeaderActions>
            </HeaderRow>
          </MainHeader>

          {/* Mobile Navigation */}
          <MobileNav>
            <MobileNavTabs>
              <MobileNavTab
                $active={activeTab === "overview"}
                onClick={() => setActiveTab("overview")}
              >
                <span className="nav-icon">
                  <OverviewIcon />
                </span>
                Overview
              </MobileNavTab>
              <MobileNavTab
                $active={activeTab === "text_labels"}
                onClick={() => setActiveTab("text_labels")}
              >
                <span className="nav-icon">
                  <TextLabelIcon />
                </span>
                Text Labels
                <span className="nav-badge">{text_labels.length}</span>
              </MobileNavTab>
              <MobileNavTab
                $active={activeTab === "doc_labels"}
                onClick={() => setActiveTab("doc_labels")}
              >
                <span className="nav-icon">
                  <DocLabelIcon />
                </span>
                Doc Labels
                <span className="nav-badge">{doc_type_labels.length}</span>
              </MobileNavTab>
              <MobileNavTab
                $active={activeTab === "relationship_labels"}
                onClick={() => setActiveTab("relationship_labels")}
              >
                <span className="nav-icon">
                  <RelationshipIcon />
                </span>
                Relationships
                <span className="nav-badge">{relationship_labels.length}</span>
              </MobileNavTab>
              <MobileNavTab
                $active={activeTab === "span_labels"}
                onClick={() => setActiveTab("span_labels")}
              >
                <span className="nav-icon">
                  <SpanLabelIcon />
                </span>
                Span Labels
                <span className="nav-badge">{span_labels.length}</span>
              </MobileNavTab>
              <MobileNavTab
                $active={activeTab === "sharing"}
                onClick={() => setActiveTab("sharing")}
              >
                <span className="nav-icon">
                  <ShareIcon />
                </span>
                Sharing
              </MobileNavTab>
            </MobileNavTabs>
          </MobileNav>

          <MainContent>
            <ContentInner>{renderContent()}</ContentInner>
          </MainContent>
        </MainContainer>
      </PageLayout>

      {/* Delete Confirmation Modal */}
      <ConfirmModal
        message={`Are you sure you want to delete "${
          labelset?.title || "this label set"
        }"? This action cannot be undone.`}
        visible={showDeleteConfirm}
        yesAction={handleDelete}
        noAction={() => setShowDeleteConfirm(false)}
        toggleModal={() => setShowDeleteConfirm(false)}
      />
    </PageContainer>
  );
};

export default LabelSetDetailPage;
