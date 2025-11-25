import React, { useState } from "react";
import { useQuery, useMutation } from "@apollo/client";
import {
  Button,
  Table,
  Header,
  Message,
  Dimmer,
  Loader,
  Segment,
  Icon,
  Modal,
  Form,
  Input,
  TextArea,
  Dropdown,
  Checkbox,
} from "semantic-ui-react";
import styled from "styled-components";
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

const Container = styled.div`
  padding: 2em;
`;

const StyledSegment = styled(Segment)`
  &.ui.segment {
    border-radius: 16px;
    background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
    border: 1px solid rgba(226, 232, 240, 0.8);
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
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
        <Dimmer active inverted>
          <Loader>Loading badges...</Loader>
        </Dimmer>
      </Container>
    );
  }

  if (error) {
    return (
      <Container>
        <Message negative>
          <Message.Header>Error loading badges</Message.Header>
          <p>{error.message}</p>
        </Message>
      </Container>
    );
  }

  const iconOptions = availableIcons.map((iconName) => ({
    key: iconName,
    text: iconName,
    value: iconName,
  }));

  return (
    <Container>
      <StyledSegment>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: "1em",
          }}
        >
          <Header as="h2">Badge Management</Header>
          <Button
            primary
            onClick={() => setShowCreateModal(true)}
            icon
            labelPosition="left"
          >
            <Icon name="plus" />
            Create Badge
          </Button>
        </div>

        <Table celled>
          <Table.Header>
            <Table.Row>
              <Table.HeaderCell>Badge</Table.HeaderCell>
              <Table.HeaderCell>Type</Table.HeaderCell>
              <Table.HeaderCell>Description</Table.HeaderCell>
              <Table.HeaderCell>Auto-Award</Table.HeaderCell>
              <Table.HeaderCell>Actions</Table.HeaderCell>
            </Table.Row>
          </Table.Header>
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
                    <Icon name="check" color="green" />
                  ) : (
                    <Icon name="close" color="red" />
                  )}
                </Table.Cell>
                <Table.Cell>
                  <Button
                    icon
                    negative
                    size="small"
                    onClick={() => {
                      setBadgeToDelete(badge);
                      setDeleteModalOpen(true);
                    }}
                  >
                    <Icon name="trash" />
                  </Button>
                </Table.Cell>
              </Table.Row>
            ))}
          </Table.Body>
        </Table>
      </StyledSegment>

      {/* Create Badge Modal */}
      <Modal
        open={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        size="small"
      >
        <Modal.Header>Create New Badge</Modal.Header>
        <Modal.Content>
          <Form>
            <Form.Field required>
              <label>Badge Name</label>
              <Input
                placeholder="e.g., First Post"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </Form.Field>

            <Form.Field required>
              <label>Description</label>
              <TextArea
                placeholder="Describe what this badge represents"
                value={description}
                onChange={(e) => setDescription(e.target.value as string)}
                rows={3}
              />
            </Form.Field>

            <Form.Field required>
              <label>Icon</label>
              <Dropdown
                fluid
                selection
                options={iconOptions}
                value={icon}
                onChange={(_, { value }) => setIcon(value as string)}
              />
            </Form.Field>

            <Form.Field required>
              <label>Color</label>
              <Input
                type="color"
                value={color}
                onChange={(e) => setColor(e.target.value)}
              />
            </Form.Field>

            <Form.Field required>
              <label>Badge Type</label>
              <Dropdown
                fluid
                selection
                options={[
                  { key: "global", text: "Global", value: "GLOBAL" },
                  {
                    key: "corpus",
                    text: "Corpus-Specific",
                    value: "CORPUS",
                    disabled: !corpusId,
                  },
                ]}
                value={badgeType}
                onChange={(_, { value }) =>
                  setBadgeType(value as "GLOBAL" | "CORPUS")
                }
              />
            </Form.Field>

            <Form.Field>
              <Checkbox
                label="Auto-award this badge"
                checked={isAutoAwarded}
                onChange={(_, { checked }) => {
                  setIsAutoAwarded(checked || false);
                  if (!checked) {
                    setCriteriaConfig(null);
                    setCriteriaValid(false);
                  }
                }}
              />
            </Form.Field>

            {/* Show criteria configuration when auto-award is enabled */}
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
          </Form>
        </Modal.Content>
        <Modal.Actions>
          <Button onClick={() => setShowCreateModal(false)}>Cancel</Button>
          <Button
            primary
            onClick={handleCreate}
            loading={creating}
            disabled={
              !name ||
              !description ||
              (isAutoAwarded && (!criteriaConfig || !criteriaValid))
            }
          >
            Create Badge
          </Button>
        </Modal.Actions>
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
