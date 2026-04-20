import React, { useState } from "react";
import { useQuery, useMutation } from "@apollo/client";
import styled from "styled-components";
import { toast } from "react-toastify";
import { Plus, Edit, Trash2, Cpu } from "lucide-react";
import {
  Button,
  IconButton,
  Input,
  Modal,
  ModalHeader,
  ModalBody,
  ModalFooter,
  Spinner,
  Table,
} from "@os-legal/ui";
import { ConfirmModal } from "../widgets/modals/ConfirmModal";
import { BadgeConfigurator, BadgeConfig } from "../agents/BadgeConfigurator";
import { ErrorMessage, InfoMessage, LoadingState } from "../widgets/feedback";
import { StatusBadge, ToolBadge, ToolsList } from "../agents/AgentBadges";
import { StyledTextArea } from "../widgets/modals/styled";
import { OS_LEGAL_COLORS } from "../../assets/configurations/osLegalStyles";
import { GET_CORPUS_AGENTS, GET_AVAILABLE_TOOLS } from "../../graphql/queries";
import {
  CREATE_AGENT_CONFIGURATION,
  UPDATE_AGENT_CONFIGURATION,
  DELETE_AGENT_CONFIGURATION,
} from "../../graphql/mutations";

const Container = styled.div`
  padding: 1.5rem;
  background: white;
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
`;

const SectionHeader = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.5rem;
`;

const SectionTitle = styled.h3`
  margin: 0;
  color: ${OS_LEGAL_COLORS.textPrimary};
  font-size: 1.25rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
`;

const HelperText = styled.p`
  color: ${OS_LEGAL_COLORS.textSecondary};
  font-size: 0.875rem;
  margin: 0.5rem 0 1.5rem 0;
  line-height: 1.5;
`;

const EmptyState = styled.div`
  text-align: center;
  padding: 3rem 1.5rem;
  background: ${OS_LEGAL_COLORS.surfaceHover};
  border-radius: 8px;
  border: 1px dashed ${OS_LEGAL_COLORS.border};
`;

const EmptyStateIcon = styled.div`
  width: 64px;
  height: 64px;
  margin: 0 auto 1rem;
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
  border-radius: 16px;
  display: flex;
  align-items: center;
  justify-content: center;

  svg,
  i.icon {
    color: white;
    margin: 0;
  }
`;

const EmptyStateTitle = styled.h3`
  font-size: 1.125rem;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textPrimary};
  margin: 0 0 0.5rem 0;
`;

const EmptyStateDescription = styled.p`
  font-size: 0.875rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
  margin: 0 0 1.5rem 0;
  max-width: 400px;
  margin-left: auto;
  margin-right: auto;
`;

// Tool Selection UI Components
const ToolSelectionContainer = styled.div`
  margin-top: 0.5rem;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 8px;
  max-height: 300px;
  overflow-y: auto;
`;

const ToolCategoryHeader = styled.div`
  background: ${OS_LEGAL_COLORS.surfaceHover};
  padding: 0.5rem 1rem;
  font-weight: 600;
  font-size: 0.8rem;
  color: ${OS_LEGAL_COLORS.textTertiary};
  text-transform: uppercase;
  letter-spacing: 0.5px;
  border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
  position: sticky;
  top: 0;
  z-index: 1;
`;

const ToolItem = styled.div<{ $selected: boolean }>`
  display: flex;
  align-items: flex-start;
  padding: 0.75rem 1rem;
  border-bottom: 1px solid ${OS_LEGAL_COLORS.surfaceLight};
  cursor: pointer;
  transition: background 0.15s ease;
  background: ${(props) =>
    props.$selected ? OS_LEGAL_COLORS.blueSurface : "transparent"};

  &:hover {
    background: ${(props) =>
      props.$selected
        ? OS_LEGAL_COLORS.blueBorder
        : OS_LEGAL_COLORS.surfaceHover};
  }

  &:last-child {
    border-bottom: none;
  }
`;

const ToolCheckbox = styled.div<{ $checked: boolean }>`
  width: 18px;
  height: 18px;
  border: 2px solid
    ${(props) =>
      props.$checked
        ? OS_LEGAL_COLORS.primaryBlue
        : OS_LEGAL_COLORS.borderHover};
  border-radius: 4px;
  margin-right: 0.75rem;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: ${(props) =>
    props.$checked ? OS_LEGAL_COLORS.primaryBlue : "white"};
  transition: all 0.15s ease;

  &::after {
    content: "${(props) => (props.$checked ? "✓" : "")}";
    color: white;
    font-size: 12px;
    font-weight: bold;
  }
`;

const ToolInfo = styled.div`
  flex: 1;
  min-width: 0;
`;

const ToolName = styled.div`
  font-weight: 500;
  color: ${OS_LEGAL_COLORS.textPrimary};
  font-size: 0.875rem;
  font-family: monospace;
  display: flex;
  align-items: center;
  gap: 0.5rem;
`;

const ToolDescription = styled.div`
  font-size: 0.8rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
  margin-top: 0.25rem;
  line-height: 1.4;
`;

const ToolBadges = styled.div`
  display: flex;
  gap: 0.25rem;
  margin-left: auto;
  flex-shrink: 0;
`;

const ApprovalBadge = styled.span`
  font-size: 0.65rem;
  padding: 0.125rem 0.375rem;
  border-radius: 4px;
  background: #fef3c7;
  color: #92400e;
  font-weight: 500;
`;

const CorpusBadge = styled.span`
  font-size: 0.65rem;
  padding: 0.125rem 0.375rem;
  border-radius: 4px;
  background: ${OS_LEGAL_COLORS.blueBorder};
  color: ${OS_LEGAL_COLORS.blueDark};
  font-weight: 500;
`;

const SelectedToolsPreview = styled.div`
  margin-top: 0.5rem;
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem;
`;

const SelectedToolPill = styled.span`
  font-size: 0.75rem;
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  background: #e0e7ff;
  color: #3730a3;
  font-family: monospace;
`;

const ToolHelpText = styled.small`
  display: block;
  color: ${OS_LEGAL_COLORS.textSecondary};
  margin-top: 0.5rem;
`;

interface CorpusAgentManagementProps {
  corpusId: string;
  canUpdate: boolean;
}

interface AvailableTool {
  name: string;
  description: string;
  category: string;
  requiresCorpus: boolean;
  requiresApproval: boolean;
}

interface AgentNode {
  id: string;
  name: string;
  slug?: string;
  description?: string;
  systemInstructions: string;
  availableTools?: string[];
  permissionRequiredTools?: string[];
  badgeConfig?: Record<string, any>;
  avatarUrl?: string;
  scope: string;
  isActive: boolean;
  isPublic?: boolean;
  creator: { id: string; username: string };
  created: string;
  modified: string;
}

interface FormState {
  name: string;
  slug: string;
  description: string;
  systemInstructions: string;
  availableTools: string[];
  permissionRequiredTools: string[];
  badgeConfig: BadgeConfig;
  avatarUrl: string;
  isPublic: boolean;
  isActive: boolean;
}

const defaultBadgeConfig: BadgeConfig = {
  icon: "bot",
  color: "#8b5cf6",
  label: "AI",
};

const initialFormState: FormState = {
  name: "",
  slug: "",
  description: "",
  systemInstructions: "",
  availableTools: [],
  permissionRequiredTools: [],
  badgeConfig: defaultBadgeConfig,
  avatarUrl: "",
  isPublic: false,
  isActive: true,
};

export const CorpusAgentManagement: React.FC<CorpusAgentManagementProps> = ({
  corpusId,
  canUpdate,
}) => {
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [agentToDelete, setAgentToDelete] = useState<AgentNode | null>(null);
  const [agentToEdit, setAgentToEdit] = useState<AgentNode | null>(null);
  const [formState, setFormState] = useState<FormState>(initialFormState);

  const { loading, error, data, refetch } = useQuery(GET_CORPUS_AGENTS, {
    variables: { corpusId },
  });

  // Fetch available tools for the selection UI
  const { data: toolsData, loading: toolsLoading } =
    useQuery(GET_AVAILABLE_TOOLS);

  const [createAgent, { loading: creating }] = useMutation(
    CREATE_AGENT_CONFIGURATION,
    {
      onCompleted: (data) => {
        if (data.createAgentConfiguration.ok) {
          toast.success("Agent created successfully");
          setShowCreateModal(false);
          setFormState(initialFormState);
          refetch();
        } else {
          toast.error(data.createAgentConfiguration.message);
        }
      },
      onError: (err) => toast.error(err.message),
    }
  );

  const [updateAgent, { loading: updating }] = useMutation(
    UPDATE_AGENT_CONFIGURATION,
    {
      onCompleted: (data) => {
        if (data.updateAgentConfiguration.ok) {
          toast.success("Agent updated successfully");
          setShowEditModal(false);
          setAgentToEdit(null);
          refetch();
        } else {
          toast.error(data.updateAgentConfiguration.message);
        }
      },
      onError: (err) => toast.error(err.message),
    }
  );

  const [deleteAgent, { loading: deleting }] = useMutation(
    DELETE_AGENT_CONFIGURATION,
    {
      onCompleted: (data) => {
        if (data.deleteAgentConfiguration.ok) {
          toast.success("Agent deleted successfully");
          setDeleteModalOpen(false);
          setAgentToDelete(null);
          refetch();
        } else {
          toast.error(data.deleteAgentConfiguration.message);
        }
      },
      onError: (err) => toast.error(err.message),
    }
  );

  const handleCreate = () => {
    createAgent({
      variables: {
        name: formState.name,
        slug: formState.slug || null, // null triggers auto-generation
        description: formState.description,
        systemInstructions: formState.systemInstructions,
        availableTools:
          formState.availableTools.length > 0 ? formState.availableTools : null,
        permissionRequiredTools:
          formState.permissionRequiredTools.length > 0
            ? formState.permissionRequiredTools
            : null,
        badgeConfig: formState.badgeConfig,
        avatarUrl: formState.avatarUrl || null,
        scope: "CORPUS",
        corpusId: corpusId,
        isPublic: formState.isPublic,
      },
    });
  };

  const handleUpdate = () => {
    if (!agentToEdit) return;

    updateAgent({
      variables: {
        agentId: agentToEdit.id,
        name: formState.name,
        slug: formState.slug || null,
        description: formState.description,
        systemInstructions: formState.systemInstructions,
        availableTools: formState.availableTools,
        permissionRequiredTools: formState.permissionRequiredTools,
        badgeConfig: formState.badgeConfig,
        avatarUrl: formState.avatarUrl || null,
        isActive: formState.isActive,
        isPublic: formState.isPublic,
      },
    });
  };

  // Toggle a tool in the available tools list
  const toggleAvailableTool = (toolName: string) => {
    setFormState((prev) => ({
      ...prev,
      availableTools: prev.availableTools.includes(toolName)
        ? prev.availableTools.filter((t) => t !== toolName)
        : [...prev.availableTools, toolName],
    }));
  };

  // Toggle a tool in the permission-required tools list
  const togglePermissionTool = (toolName: string) => {
    setFormState((prev) => ({
      ...prev,
      permissionRequiredTools: prev.permissionRequiredTools.includes(toolName)
        ? prev.permissionRequiredTools.filter((t) => t !== toolName)
        : [...prev.permissionRequiredTools, toolName],
    }));
  };

  // Group tools by category for display
  const groupedTools = React.useMemo(() => {
    const tools: AvailableTool[] = toolsData?.availableTools || [];
    const groups: Record<string, AvailableTool[]> = {};
    for (const tool of tools) {
      if (!groups[tool.category]) {
        groups[tool.category] = [];
      }
      groups[tool.category].push(tool);
    }
    return groups;
  }, [toolsData?.availableTools]);

  const openEditModal = (agent: AgentNode) => {
    setAgentToEdit(agent);
    // Parse badge config from API or use defaults
    const parsedBadgeConfig: BadgeConfig = {
      icon: agent.badgeConfig?.icon || defaultBadgeConfig.icon,
      color: agent.badgeConfig?.color || defaultBadgeConfig.color,
      label: agent.badgeConfig?.label || defaultBadgeConfig.label,
    };
    setFormState({
      name: agent.name,
      slug: agent.slug || "",
      description: agent.description || "",
      systemInstructions: agent.systemInstructions,
      availableTools: Array.isArray(agent.availableTools)
        ? agent.availableTools
        : [],
      permissionRequiredTools: Array.isArray(agent.permissionRequiredTools)
        ? agent.permissionRequiredTools
        : [],
      badgeConfig: parsedBadgeConfig,
      avatarUrl: agent.avatarUrl || "",
      isPublic: agent.isPublic ?? false,
      isActive: agent.isActive,
    });
    setShowEditModal(true);
  };

  if (!canUpdate) {
    return (
      <Container>
        <InfoMessage>
          You do not have permission to manage agents for this corpus.
        </InfoMessage>
      </Container>
    );
  }

  if (loading) {
    return (
      <Container>
        <LoadingState message="Loading agents..." />
      </Container>
    );
  }

  if (error) {
    return (
      <Container>
        <ErrorMessage title="Error loading agents">
          {error.message}
        </ErrorMessage>
      </Container>
    );
  }

  const agents: AgentNode[] =
    data?.agentConfigurations?.edges?.map((e: any) => e.node) || [];

  return (
    <Container>
      <SectionHeader>
        <SectionTitle>
          <Cpu size={18} /> Agent Configurations
        </SectionTitle>
        <Button
          variant="primary"
          size="sm"
          leftIcon={<Plus size={14} />}
          onClick={() => {
            setFormState(initialFormState);
            setShowCreateModal(true);
          }}
        >
          Create Agent
        </Button>
      </SectionHeader>

      <HelperText>
        Create agent configurations for this corpus. These define the AI's
        capabilities, instructions, and available tools. The same configuration
        can be used in different contexts:
        <ul style={{ margin: "0.5rem 0 0 1.25rem", padding: 0 }}>
          <li>
            <strong>Corpus Actions</strong> — Agent operates on{" "}
            <em>individual documents</em> when triggered by add/edit events
          </li>
          <li>
            <strong>Corpus Chat</strong> — Agent can access the{" "}
            <em>entire corpus</em> for research and analysis
          </li>
          <li>
            <strong>Document Chat</strong> — Agent focuses on a{" "}
            <em>single document</em> for detailed Q&A
          </li>
        </ul>
      </HelperText>

      {agents.length === 0 ? (
        <EmptyState>
          <EmptyStateIcon>
            <Cpu size={28} color="white" />
          </EmptyStateIcon>
          <EmptyStateTitle>No Agent Configurations</EmptyStateTitle>
          <EmptyStateDescription>
            Create an agent configuration to enable AI-powered actions, chat,
            and document analysis for this corpus.
          </EmptyStateDescription>
          <Button
            variant="primary"
            leftIcon={<Plus size={14} />}
            onClick={() => {
              setFormState(initialFormState);
              setShowCreateModal(true);
            }}
          >
            Create Agent
          </Button>
        </EmptyState>
      ) : (
        <Table variant="minimal" size="sm">
          <Table.Head>
            <Table.Row>
              <Table.HeadCell>Name</Table.HeadCell>
              <Table.HeadCell>Description</Table.HeadCell>
              <Table.HeadCell>Tools</Table.HeadCell>
              <Table.HeadCell>Status</Table.HeadCell>
              <Table.HeadCell>Actions</Table.HeadCell>
            </Table.Row>
          </Table.Head>
          <Table.Body>
            {agents.map((agent) => (
              <Table.Row key={agent.id}>
                <Table.Cell>
                  <strong>{agent.name}</strong>
                  {agent.slug && (
                    <div
                      style={{
                        fontSize: "0.75rem",
                        color: OS_LEGAL_COLORS.textSecondary,
                      }}
                    >
                      <code>{agent.slug}</code>
                    </div>
                  )}
                </Table.Cell>
                <Table.Cell>
                  <span style={{ fontSize: "0.875rem" }}>
                    {agent.description?.substring(0, 80)}
                    {(agent.description?.length || 0) > 80 ? "..." : ""}
                  </span>
                </Table.Cell>
                <Table.Cell>
                  <ToolsList>
                    {(Array.isArray(agent.availableTools)
                      ? agent.availableTools
                      : []
                    )
                      .slice(0, 2)
                      .map((tool) => (
                        <ToolBadge key={tool}>{tool}</ToolBadge>
                      ))}
                    {(Array.isArray(agent.availableTools)
                      ? agent.availableTools
                      : []
                    ).length > 2 && (
                      <ToolBadge>
                        +
                        {(Array.isArray(agent.availableTools)
                          ? agent.availableTools
                          : []
                        ).length - 2}
                      </ToolBadge>
                    )}
                  </ToolsList>
                </Table.Cell>
                <Table.Cell>
                  <StatusBadge $active={agent.isActive}>
                    {agent.isActive ? "Active" : "Inactive"}
                  </StatusBadge>
                </Table.Cell>
                <Table.Cell>
                  <IconButton
                    size="sm"
                    aria-label="Edit agent"
                    onClick={() => openEditModal(agent)}
                  >
                    <Edit size={14} />
                  </IconButton>
                  <IconButton
                    size="sm"
                    variant="danger"
                    aria-label="Delete agent"
                    onClick={() => {
                      setAgentToDelete(agent);
                      setDeleteModalOpen(true);
                    }}
                  >
                    <Trash2 size={14} />
                  </IconButton>
                </Table.Cell>
              </Table.Row>
            ))}
          </Table.Body>
        </Table>
      )}

      {/* Create Modal */}
      <Modal
        open={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        size="xl"
      >
        <ModalHeader
          title="Create Agent Configuration"
          onClose={() => setShowCreateModal(false)}
        />
        <ModalBody>
          <InfoMessage
            title="How Agent Scope Works"
            style={{ marginBottom: "1rem" }}
          >
            <>
              This configuration defines the agent&apos;s capabilities. When
              used:
              <ul style={{ margin: "0.25rem 0 0 1rem", padding: 0 }}>
                <li>
                  In <strong>Corpus Actions</strong>: Agent processes individual
                  documents automatically
                </li>
                <li>
                  In <strong>Chat</strong>: Agent scope depends on the
                  conversation context (document or corpus)
                </li>
              </ul>
            </>
          </InfoMessage>
          <div>
            <div style={{ marginBottom: "1rem" }}>
              <Input
                label="Name"
                fullWidth
                placeholder="Agent name"
                value={formState.name}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                  setFormState({ ...formState, name: e.target.value })
                }
              />
            </div>
            <div style={{ marginBottom: "1rem" }}>
              <Input
                label="Slug (for @mentions)"
                fullWidth
                placeholder="my-agent (auto-generated from name if empty)"
                value={formState.slug}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                  setFormState({ ...formState, slug: e.target.value })
                }
                helperText="URL-friendly identifier used in @mentions (e.g., @agent:my-agent)"
              />
            </div>
            <div style={{ marginBottom: "1rem" }}>
              <label
                style={{
                  display: "block",
                  fontWeight: 500,
                  fontSize: "0.875rem",
                  marginBottom: "0.25rem",
                }}
              >
                Description
              </label>
              <StyledTextArea
                placeholder="Brief description of what this agent does"
                value={formState.description}
                onChange={(e) =>
                  setFormState({ ...formState, description: e.target.value })
                }
                rows={2}
              />
            </div>
            <div style={{ marginBottom: "1rem" }}>
              <label
                style={{
                  display: "block",
                  fontWeight: 500,
                  fontSize: "0.875rem",
                  marginBottom: "0.25rem",
                }}
              >
                System Instructions
              </label>
              <StyledTextArea
                placeholder="System prompt for the agent..."
                value={formState.systemInstructions}
                onChange={(e) =>
                  setFormState({
                    ...formState,
                    systemInstructions: e.target.value,
                  })
                }
                rows={6}
                style={{ fontFamily: "monospace" }}
              />
            </div>
            <div style={{ marginBottom: "1rem" }}>
              <label
                style={{
                  display: "block",
                  fontWeight: 500,
                  fontSize: "0.875rem",
                  marginBottom: "0.25rem",
                }}
              >
                Available Tools
              </label>
              {toolsLoading ? (
                <Spinner size="sm" />
              ) : (
                <>
                  <ToolSelectionContainer>
                    {Object.entries(groupedTools).map(([category, tools]) => (
                      <React.Fragment key={category}>
                        <ToolCategoryHeader>
                          {category.replace(/_/g, " ")}
                        </ToolCategoryHeader>
                        {tools.map((tool) => (
                          <ToolItem
                            key={tool.name}
                            $selected={formState.availableTools.includes(
                              tool.name
                            )}
                            onClick={() => toggleAvailableTool(tool.name)}
                          >
                            <ToolCheckbox
                              $checked={formState.availableTools.includes(
                                tool.name
                              )}
                            />
                            <ToolInfo>
                              <ToolName>{tool.name}</ToolName>
                              <ToolDescription>
                                {tool.description}
                              </ToolDescription>
                            </ToolInfo>
                            <ToolBadges>
                              {tool.requiresApproval && (
                                <ApprovalBadge>Needs Approval</ApprovalBadge>
                              )}
                              {tool.requiresCorpus && (
                                <CorpusBadge>Corpus</CorpusBadge>
                              )}
                            </ToolBadges>
                          </ToolItem>
                        ))}
                      </React.Fragment>
                    ))}
                  </ToolSelectionContainer>
                  {formState.availableTools.length > 0 && (
                    <SelectedToolsPreview>
                      {formState.availableTools.map((tool) => (
                        <SelectedToolPill key={tool}>{tool}</SelectedToolPill>
                      ))}
                    </SelectedToolsPreview>
                  )}
                  <ToolHelpText>
                    Select the tools this agent can use. Tools marked "Needs
                    Approval" will prompt users before execution.
                  </ToolHelpText>
                </>
              )}
            </div>
            <div style={{ marginBottom: "1rem" }}>
              <label
                style={{
                  display: "block",
                  fontWeight: 500,
                  fontSize: "0.875rem",
                  marginBottom: "0.25rem",
                }}
              >
                Permission Required Tools
              </label>
              <ToolHelpText style={{ marginTop: 0, marginBottom: "0.5rem" }}>
                Select tools that should require explicit user permission before
                the agent can use them. Only tools selected above can be marked
                as permission-required.
              </ToolHelpText>
              {formState.availableTools.length === 0 ? (
                <InfoMessage>
                  Select available tools first to configure permission
                  requirements.
                </InfoMessage>
              ) : (
                <ToolSelectionContainer style={{ maxHeight: "150px" }}>
                  {formState.availableTools.map((toolName) => {
                    const tool = toolsData?.availableTools?.find(
                      (t: AvailableTool) => t.name === toolName
                    );
                    return (
                      <ToolItem
                        key={toolName}
                        $selected={formState.permissionRequiredTools.includes(
                          toolName
                        )}
                        onClick={() => togglePermissionTool(toolName)}
                      >
                        <ToolCheckbox
                          $checked={formState.permissionRequiredTools.includes(
                            toolName
                          )}
                        />
                        <ToolInfo>
                          <ToolName>{toolName}</ToolName>
                          {tool?.description && (
                            <ToolDescription>
                              {tool.description.substring(0, 80)}...
                            </ToolDescription>
                          )}
                        </ToolInfo>
                      </ToolItem>
                    );
                  })}
                </ToolSelectionContainer>
              )}
            </div>
            <div style={{ marginBottom: "1rem" }}>
              <label
                style={{
                  display: "block",
                  fontWeight: 500,
                  fontSize: "0.875rem",
                  marginBottom: "0.25rem",
                }}
              >
                Badge Appearance
              </label>
              <BadgeConfigurator
                value={formState.badgeConfig}
                onChange={(config) =>
                  setFormState({ ...formState, badgeConfig: config })
                }
              />
            </div>
            <div style={{ marginBottom: "1rem" }}>
              <Input
                label="Avatar URL (optional)"
                fullWidth
                placeholder="https://example.com/avatar.png"
                value={formState.avatarUrl}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                  setFormState({ ...formState, avatarUrl: e.target.value })
                }
                helperText="Custom avatar image URL. If not provided, the badge icon will be used."
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
                  checked={formState.isPublic}
                  onChange={(e) =>
                    setFormState({ ...formState, isPublic: e.target.checked })
                  }
                />
                Publicly visible (visible to users with corpus access)
              </label>
            </div>
          </div>
        </ModalBody>
        <ModalFooter>
          <Button variant="secondary" onClick={() => setShowCreateModal(false)}>
            Cancel
          </Button>
          <Button
            variant="primary"
            loading={creating}
            disabled={
              !formState.name ||
              !formState.description ||
              !formState.systemInstructions
            }
            onClick={handleCreate}
          >
            Create Agent
          </Button>
        </ModalFooter>
      </Modal>

      {/* Edit Modal */}
      <Modal
        open={showEditModal}
        onClose={() => setShowEditModal(false)}
        size="xl"
      >
        <ModalHeader
          title={`Edit Agent Configuration: ${agentToEdit?.name}`}
          onClose={() => setShowEditModal(false)}
        />
        <ModalBody>
          <div>
            <div style={{ marginBottom: "1rem" }}>
              <Input
                label="Name"
                fullWidth
                placeholder="Agent name"
                value={formState.name}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                  setFormState({ ...formState, name: e.target.value })
                }
              />
            </div>
            <div style={{ marginBottom: "1rem" }}>
              <Input
                label="Slug (for @mentions)"
                fullWidth
                placeholder="my-agent"
                value={formState.slug}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                  setFormState({ ...formState, slug: e.target.value })
                }
                helperText="URL-friendly identifier used in @mentions (e.g., @agent:my-agent)"
              />
            </div>
            <div style={{ marginBottom: "1rem" }}>
              <label
                style={{
                  display: "block",
                  fontWeight: 500,
                  fontSize: "0.875rem",
                  marginBottom: "0.25rem",
                }}
              >
                Description
              </label>
              <StyledTextArea
                placeholder="Brief description of what this agent does"
                value={formState.description}
                onChange={(e) =>
                  setFormState({ ...formState, description: e.target.value })
                }
                rows={2}
              />
            </div>
            <div style={{ marginBottom: "1rem" }}>
              <label
                style={{
                  display: "block",
                  fontWeight: 500,
                  fontSize: "0.875rem",
                  marginBottom: "0.25rem",
                }}
              >
                System Instructions
              </label>
              <StyledTextArea
                placeholder="System prompt for the agent..."
                value={formState.systemInstructions}
                onChange={(e) =>
                  setFormState({
                    ...formState,
                    systemInstructions: e.target.value,
                  })
                }
                rows={6}
                style={{ fontFamily: "monospace" }}
              />
            </div>
            <div style={{ marginBottom: "1rem" }}>
              <label
                style={{
                  display: "block",
                  fontWeight: 500,
                  fontSize: "0.875rem",
                  marginBottom: "0.25rem",
                }}
              >
                Available Tools
              </label>
              {toolsLoading ? (
                <Spinner size="sm" />
              ) : (
                <>
                  <ToolSelectionContainer>
                    {Object.entries(groupedTools).map(([category, tools]) => (
                      <React.Fragment key={category}>
                        <ToolCategoryHeader>
                          {category.replace(/_/g, " ")}
                        </ToolCategoryHeader>
                        {tools.map((tool) => (
                          <ToolItem
                            key={tool.name}
                            $selected={formState.availableTools.includes(
                              tool.name
                            )}
                            onClick={() => toggleAvailableTool(tool.name)}
                          >
                            <ToolCheckbox
                              $checked={formState.availableTools.includes(
                                tool.name
                              )}
                            />
                            <ToolInfo>
                              <ToolName>{tool.name}</ToolName>
                              <ToolDescription>
                                {tool.description}
                              </ToolDescription>
                            </ToolInfo>
                            <ToolBadges>
                              {tool.requiresApproval && (
                                <ApprovalBadge>Needs Approval</ApprovalBadge>
                              )}
                              {tool.requiresCorpus && (
                                <CorpusBadge>Corpus</CorpusBadge>
                              )}
                            </ToolBadges>
                          </ToolItem>
                        ))}
                      </React.Fragment>
                    ))}
                  </ToolSelectionContainer>
                  {formState.availableTools.length > 0 && (
                    <SelectedToolsPreview>
                      {formState.availableTools.map((tool) => (
                        <SelectedToolPill key={tool}>{tool}</SelectedToolPill>
                      ))}
                    </SelectedToolsPreview>
                  )}
                  <ToolHelpText>
                    Select the tools this agent can use. Tools marked "Needs
                    Approval" will prompt users before execution.
                  </ToolHelpText>
                </>
              )}
            </div>
            <div style={{ marginBottom: "1rem" }}>
              <label
                style={{
                  display: "block",
                  fontWeight: 500,
                  fontSize: "0.875rem",
                  marginBottom: "0.25rem",
                }}
              >
                Permission Required Tools
              </label>
              <ToolHelpText style={{ marginTop: 0, marginBottom: "0.5rem" }}>
                Select tools that should require explicit user permission before
                the agent can use them. Only tools selected above can be marked
                as permission-required.
              </ToolHelpText>
              {formState.availableTools.length === 0 ? (
                <InfoMessage>
                  Select available tools first to configure permission
                  requirements.
                </InfoMessage>
              ) : (
                <ToolSelectionContainer style={{ maxHeight: "150px" }}>
                  {formState.availableTools.map((toolName) => {
                    const tool = toolsData?.availableTools?.find(
                      (t: AvailableTool) => t.name === toolName
                    );
                    return (
                      <ToolItem
                        key={toolName}
                        $selected={formState.permissionRequiredTools.includes(
                          toolName
                        )}
                        onClick={() => togglePermissionTool(toolName)}
                      >
                        <ToolCheckbox
                          $checked={formState.permissionRequiredTools.includes(
                            toolName
                          )}
                        />
                        <ToolInfo>
                          <ToolName>{toolName}</ToolName>
                          {tool?.description && (
                            <ToolDescription>
                              {tool.description.substring(0, 80)}...
                            </ToolDescription>
                          )}
                        </ToolInfo>
                      </ToolItem>
                    );
                  })}
                </ToolSelectionContainer>
              )}
            </div>
            <div style={{ marginBottom: "1rem" }}>
              <label
                style={{
                  display: "block",
                  fontWeight: 500,
                  fontSize: "0.875rem",
                  marginBottom: "0.25rem",
                }}
              >
                Badge Appearance
              </label>
              <BadgeConfigurator
                value={formState.badgeConfig}
                onChange={(config) =>
                  setFormState({ ...formState, badgeConfig: config })
                }
              />
            </div>
            <div style={{ marginBottom: "1rem" }}>
              <Input
                label="Avatar URL (optional)"
                fullWidth
                placeholder="https://example.com/avatar.png"
                value={formState.avatarUrl}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                  setFormState({ ...formState, avatarUrl: e.target.value })
                }
                helperText="Custom avatar image URL. If not provided, the badge icon will be used."
              />
            </div>
            <div
              style={{ display: "flex", gap: "1.5rem", marginBottom: "1rem" }}
            >
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
                  checked={formState.isActive}
                  onChange={(e) =>
                    setFormState({ ...formState, isActive: e.target.checked })
                  }
                />
                Active
              </label>
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
                  checked={formState.isPublic}
                  onChange={(e) =>
                    setFormState({ ...formState, isPublic: e.target.checked })
                  }
                />
                Publicly visible
              </label>
            </div>
          </div>
        </ModalBody>
        <ModalFooter>
          <Button variant="secondary" onClick={() => setShowEditModal(false)}>
            Cancel
          </Button>
          <Button
            variant="primary"
            loading={updating}
            disabled={
              !formState.name ||
              !formState.description ||
              !formState.systemInstructions
            }
            onClick={handleUpdate}
          >
            Save Changes
          </Button>
        </ModalFooter>
      </Modal>

      {/* Delete Confirmation */}
      <ConfirmModal
        visible={deleteModalOpen}
        message={`Are you sure you want to delete the agent "${agentToDelete?.name}"? This action cannot be undone.`}
        yesAction={() => {
          if (agentToDelete) {
            deleteAgent({ variables: { agentId: agentToDelete.id } });
          }
        }}
        noAction={() => {
          setDeleteModalOpen(false);
          setAgentToDelete(null);
        }}
        toggleModal={() => setDeleteModalOpen(false)}
      />
    </Container>
  );
};

export default CorpusAgentManagement;
