import React, { useState } from "react";
import { useQuery, useMutation } from "@apollo/client";
import { Plus, Check, X, Trash2 } from "lucide-react";
import {
  Button,
  Dropdown,
  IconButton,
  Input,
  Modal,
  ModalHeader,
  ModalBody,
  ModalFooter,
  Table,
} from "@os-legal/ui";
import styled from "styled-components";
import { StyledTextArea } from "../widgets/modals/styled";
import { ErrorMessage, LoadingState } from "../widgets/feedback";
import { Badge } from "./Badge";
import { BadgeCriteriaConfig } from "./BadgeCriteriaConfig";
import {
  GET_BADGES,
  GetBadgesInput,
  GetBadgesOutput,
  BadgeNode,
} from "../../graphql/queries";
import {
  CREATE_BADGE,
  DELETE_BADGE,
  CreateBadgeInput,
  CreateBadgeOutput,
  DeleteBadgeInput,
  DeleteBadgeOutput,
} from "../../graphql/mutations";
import { ConfirmModal } from "../widgets/modals/ConfirmModal";
import * as LucideIcons from "lucide-react";
import { OS_LEGAL_COLORS } from "../../assets/configurations/osLegalStyles";
import {
  MOBILE_VIEW_BREAKPOINT,
  BADGE_TABLE_MIN_WIDTH_PX,
} from "../../assets/configurations/constants";
import {
  GradientSegment as StyledSegment,
  PageHeader as BasePageHeader,
  ScrollableTableWrapper,
} from "../layout/SharedSegments";

const Container = styled.div`
  padding: 2rem;

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    padding: 1rem;
  }
`;

const PageHeader = styled(BasePageHeader)`
  margin-bottom: 1em;

  h2 {
    margin: 0;
  }
`;

// Get list of available lucide icons for dropdown
const availableIcons = [
  "Trophy",
  "Award",
  "Star",
  "Crown",
  "Medal",
  "Target",
  "Zap",
  "Heart",
  "ThumbsUp",
  "Flame",
  "MessageSquare",
  "MessageCircle",
  "Users",
  "UserCheck",
  "Sparkles",
];

interface BadgeManagementProps {
  corpusId?: string;
}

export const BadgeManagement: React.FC<BadgeManagementProps> = ({
  corpusId,
}) => {
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [badgeToDelete, setBadgeToDelete] = useState<BadgeNode | null>(null);

  // Form state for creating badge
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [icon, setIcon] = useState("Trophy");
  const [color, setColor] = useState("#05313d");
  const [badgeType, setBadgeType] = useState<"GLOBAL" | "CORPUS">("GLOBAL");
  const [isAutoAwarded, setIsAutoAwarded] = useState(false);
  const [criteriaConfig, setCriteriaConfig] = useState<any>(null);
  const [criteriaValid, setCriteriaValid] = useState<boolean>(false);

  const { loading, error, data, refetch } = useQuery<
    GetBadgesOutput,
    GetBadgesInput
  >(GET_BADGES, {
    variables: {
      corpusId,
      limit: 100,
    },
  });

  const [createBadge, { loading: creating }] = useMutation<
    CreateBadgeOutput,
    CreateBadgeInput
  >(CREATE_BADGE, {
    onCompleted: () => {
      setShowCreateModal(false);
      resetForm();
      refetch();
    },
  });

  const [deleteBadge] = useMutation<DeleteBadgeOutput, DeleteBadgeInput>(
    DELETE_BADGE,
    {
      onCompleted: () => {
        setDeleteModalOpen(false);
        setBadgeToDelete(null);
        refetch();
      },
    }
  );

  const resetForm = () => {
    setName("");
    setDescription("");
    setIcon("Trophy");
    setColor("#05313d");
    setBadgeType("GLOBAL");
    setIsAutoAwarded(false);
    setCriteriaConfig(null);
    setCriteriaValid(false);
  };

  const handleCreate = () => {
    createBadge({
      variables: {
        name,
        description,
        icon,
        badgeType,
        color,
        corpusId: badgeType === "CORPUS" ? corpusId : undefined,
        isAutoAwarded,
        criteriaConfig: isAutoAwarded
          ? JSON.stringify(criteriaConfig)
          : undefined,
      },
    });
  };

  const handleDelete = () => {
    if (badgeToDelete) {
      deleteBadge({
        variables: {
          badgeId: badgeToDelete.id,
        },
      });
    }
  };

  const badges = data?.badges?.edges?.map((edge) => edge.node) || [];

  if (loading) {
    return (
      <Container>
        <LoadingState message="Loading badges..." />
      </Container>
    );
  }

  if (error) {
    return (
      <Container>
        <ErrorMessage title="Error loading badges">
          {error.message}
        </ErrorMessage>
      </Container>
    );
  }

  const iconOptions = availableIcons.map((iconName) => ({
    value: iconName,
    label: iconName,
  }));

  return (
    <Container>
      <StyledSegment>
        <PageHeader>
          <h2>Badge Management</h2>
          <Button
            variant="primary"
            leftIcon={<Plus size={14} />}
            onClick={() => setShowCreateModal(true)}
          >
            Create Badge
          </Button>
        </PageHeader>

        <ScrollableTableWrapper
          $minWidth={`${BADGE_TABLE_MIN_WIDTH_PX}px`}
          data-testid="badge-management-table-scroll"
        >
          <Table variant="bordered">
            <Table.Head>
              <Table.Row>
                <Table.HeadCell>Badge</Table.HeadCell>
                <Table.HeadCell>Type</Table.HeadCell>
                <Table.HeadCell>Description</Table.HeadCell>
                <Table.HeadCell>Auto-Award</Table.HeadCell>
                <Table.HeadCell>Actions</Table.HeadCell>
              </Table.Row>
            </Table.Head>
            <Table.Body>
              {badges.map((badge) => (
                <Table.Row key={badge.id}>
                  <Table.Cell>
                    <Badge
                      badge={{
                        id: badge.id,
                        name: badge.name,
                        description: badge.description,
                        icon: badge.icon,
                        color: badge.color,
                        badgeType: badge.badgeType,
                      }}
                      showTooltip={false}
                    />
                  </Table.Cell>
                  <Table.Cell>{badge.badgeType}</Table.Cell>
                  <Table.Cell>{badge.description}</Table.Cell>
                  <Table.Cell>
                    {badge.isAutoAwarded ? (
                      <Check size={16} color={OS_LEGAL_COLORS.success} />
                    ) : (
                      <X size={16} color={OS_LEGAL_COLORS.danger} />
                    )}
                  </Table.Cell>
                  <Table.Cell>
                    <IconButton
                      variant="ghost"
                      size="sm"
                      aria-label="Delete badge"
                      onClick={() => {
                        setBadgeToDelete(badge);
                        setDeleteModalOpen(true);
                      }}
                    >
                      <Trash2 size={14} color={OS_LEGAL_COLORS.danger} />
                    </IconButton>
                  </Table.Cell>
                </Table.Row>
              ))}
            </Table.Body>
          </Table>
        </ScrollableTableWrapper>
      </StyledSegment>

      {/* Create Badge Modal */}
      <Modal
        open={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        size="sm"
      >
        <ModalHeader
          title="Create New Badge"
          onClose={() => setShowCreateModal(false)}
        />
        <ModalBody>
          <div>
            <div style={{ marginBottom: "1rem" }}>
              <label>
                Badge Name{" "}
                <span style={{ color: OS_LEGAL_COLORS.danger }}>*</span>
              </label>
              <Input
                fullWidth
                placeholder="e.g., First Post"
                value={name}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                  setName(e.target.value)
                }
              />
            </div>

            <div style={{ marginBottom: "1rem" }}>
              <label>
                Description{" "}
                <span style={{ color: OS_LEGAL_COLORS.danger }}>*</span>
              </label>
              <StyledTextArea
                placeholder="Describe what this badge represents"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={3}
              />
            </div>

            <div style={{ marginBottom: "1rem" }}>
              <label>
                Icon <span style={{ color: OS_LEGAL_COLORS.danger }}>*</span>
              </label>
              <Dropdown
                mode="select"
                fluid
                options={iconOptions}
                value={icon}
                onChange={(value) => setIcon(value as string)}
              />
            </div>

            <div style={{ marginBottom: "1rem" }}>
              <label>
                Color <span style={{ color: OS_LEGAL_COLORS.danger }}>*</span>
              </label>
              <input
                type="color"
                value={color}
                onChange={(e) => setColor(e.target.value)}
              />
            </div>

            <div style={{ marginBottom: "1rem" }}>
              <label>
                Badge Type{" "}
                <span style={{ color: OS_LEGAL_COLORS.danger }}>*</span>
              </label>
              <Dropdown
                mode="select"
                fluid
                options={[
                  { value: "GLOBAL", label: "Global" },
                  {
                    value: "CORPUS",
                    label: "Corpus-Specific",
                    disabled: !corpusId,
                  },
                ]}
                value={badgeType}
                onChange={(value) => setBadgeType(value as "GLOBAL" | "CORPUS")}
              />
            </div>

            <div style={{ marginBottom: "1rem" }}>
              <label
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "0.5rem",
                  cursor: "pointer",
                }}
              >
                <input
                  type="checkbox"
                  checked={isAutoAwarded}
                  onChange={(e) => {
                    setIsAutoAwarded(e.target.checked);
                    if (!e.target.checked) {
                      setCriteriaConfig(null);
                      setCriteriaValid(false);
                    }
                  }}
                />
                Auto-award this badge
              </label>
            </div>

            {isAutoAwarded && (
              <BadgeCriteriaConfig
                badgeType={badgeType}
                criteriaConfig={criteriaConfig}
                onChange={(data) => {
                  setCriteriaConfig(data.config);
                  setCriteriaValid(data.isValid);
                }}
              />
            )}
          </div>
        </ModalBody>
        <ModalFooter>
          <Button variant="secondary" onClick={() => setShowCreateModal(false)}>
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={handleCreate}
            loading={creating}
            disabled={
              !name ||
              !description ||
              creating ||
              (isAutoAwarded && (!criteriaConfig || !criteriaValid))
            }
          >
            Create Badge
          </Button>
        </ModalFooter>
      </Modal>

      {/* Delete Confirmation Modal */}
      <ConfirmModal
        visible={deleteModalOpen}
        message={`Are you sure you want to delete the badge "${badgeToDelete?.name}"? This action cannot be undone.`}
        yesAction={handleDelete}
        noAction={() => {}}
        toggleModal={() => setDeleteModalOpen(false)}
      />
    </Container>
  );
};
