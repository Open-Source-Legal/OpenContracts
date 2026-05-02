import React, { useMemo, useState, useCallback } from "react";
import {
  Dropdown,
  DropdownOption,
  FilterTabs,
  Button,
  Input,
  Modal,
  ModalHeader,
  ModalBody,
  ModalFooter,
  Spinner,
} from "@os-legal/ui";
import type { FilterTabItem } from "@os-legal/ui";
import { Info, Settings, Cpu, FileText } from "lucide-react";
import styled from "styled-components";
import { useMutation, useQuery } from "@apollo/client";
import { InfoMessage } from "../widgets/feedback";
import { StyledTextArea } from "../widgets/modals/styled";
import { toast } from "react-toastify";
import _ from "lodash";
import { OS_LEGAL_COLORS } from "../../assets/configurations/osLegalStyles";
import {
  DEFAULT_DOCUMENT_AGENT_INSTRUCTIONS,
  DEFAULT_MODERATOR_INSTRUCTIONS,
} from "../../assets/configurations/constants";
import { InlineBadge } from "../agents/AgentBadges";
import { FormField } from "../widgets/form/FormField";

import {
  CREATE_CORPUS_ACTION,
  CreateCorpusActionInput,
  CreateCorpusActionOutput,
  UPDATE_CORPUS_ACTION,
  UpdateCorpusActionInput,
  UpdateCorpusActionOutput,
} from "../../graphql/mutations";
import {
  GET_FIELDSETS,
  GET_ANALYZERS,
  GET_AGENT_CONFIGURATIONS,
  GET_AVAILABLE_MODERATION_TOOLS,
  GET_AVAILABLE_DOCUMENT_TOOLS,
  GetFieldsetsInputs,
  GetFieldsetsOutputs,
  GetAnalyzersInputs,
  GetAnalyzersOutputs,
  GetAgentConfigurationsInput,
  GetAgentConfigurationsOutput,
  GetAvailableModerationToolsOutput,
  GetAvailableDocumentToolsOutput,
  AvailableTool,
} from "../../graphql/queries";

const StyledModal = styled(Modal)`
  &.oc-modal {
    max-width: 640px;
    width: 100%;
  }
`;

/**
 * Default moderation tools (fallback when backend query fails or returns no data).
 * These are pre-selected by default when creating inline moderator agents.
 */
const DEFAULT_MODERATION_TOOLS = [
  { name: "get_thread_context", description: "Get thread metadata and status" },
  { name: "get_thread_messages", description: "Retrieve recent messages" },
  { name: "get_message_content", description: "Get full message content" },
  { name: "add_thread_message", description: "Post an agent message" },
  { name: "lock_thread", description: "Lock thread to prevent new messages" },
  { name: "unlock_thread", description: "Unlock a previously locked thread" },
  { name: "delete_message", description: "Soft delete a message" },
  { name: "pin_thread", description: "Pin thread to top of list" },
  { name: "unpin_thread", description: "Unpin a pinned thread" },
] as const;

/**
 * Shape of an existing corpus action for editing
 */
export interface CorpusActionData {
  id: string;
  name: string;
  trigger: string;
  disabled: boolean;
  runOnAllCorpuses: boolean;
  fieldset?: { id: string; name: string } | null;
  analyzer?: { id: string; name: string } | null;
  agentConfig?: { id: string; name: string; description: string } | null;
  taskInstructions?: string;
  preAuthorizedTools?: string[];
}

interface CreateCorpusActionModalProps {
  corpusId: string;
  open: boolean;
  onClose: () => void;
  onSuccess: () => void;
  /** Optional action to edit - if provided, modal is in edit mode */
  actionToEdit?: CorpusActionData | null;
}

type ActionType = "fieldset" | "analyzer" | "agent";
type TriggerType =
  | "add_document"
  | "edit_document"
  | "new_thread"
  | "new_message";

export const CreateCorpusActionModal: React.FC<
  CreateCorpusActionModalProps
> = ({ corpusId, open, onClose, onSuccess, actionToEdit }) => {
  const isEditMode = !!actionToEdit;

  const [name, setName] = React.useState("");
  const [trigger, setTrigger] = React.useState<TriggerType>("add_document");
  const [actionType, setActionType] = React.useState<ActionType>("fieldset");
  const [selectedFieldsetId, setSelectedFieldsetId] = React.useState<
    string | null
  >(null);
  const [selectedAnalyzerId, setSelectedAnalyzerId] = React.useState<
    string | null
  >(null);
  const [selectedAgentConfigId, setSelectedAgentConfigId] = React.useState<
    string | null
  >(null);
  const [taskInstructions, setTaskInstructions] = React.useState("");
  const [preAuthorizedTools, setPreAuthorizedTools] = React.useState<string[]>(
    []
  );
  // Inline agent creation state (for thread/message triggers)
  const [useInlineAgent, setUseInlineAgent] = React.useState(true);
  const [inlineAgentName, setInlineAgentName] = React.useState("");
  const [inlineAgentDescription, setInlineAgentDescription] =
    React.useState("");
  // Initial trigger is "add_document" (a document trigger), so the default
  // instructions must match — otherwise the textarea opens with the moderator
  // copy that only applies to thread/message triggers. The dropdown's onChange
  // swaps this value when the trigger changes; this initialiser keeps the
  // pre-interaction state aligned with the default trigger.
  const [inlineAgentInstructions, setInlineAgentInstructions] = React.useState(
    DEFAULT_DOCUMENT_AGENT_INSTRUCTIONS
  );
  const [selectedModerationTools, setSelectedModerationTools] = React.useState<
    string[]
  >(DEFAULT_MODERATION_TOOLS.map((t) => t.name));
  const [selectedDocumentTools, setSelectedDocumentTools] = React.useState<
    string[]
  >([]);

  const [disabled, setDisabled] = React.useState(false);
  const [runOnAllCorpuses, setRunOnAllCorpuses] = React.useState(false);
  const [isSubmitting, setIsSubmitting] = React.useState(false);
  // Agent search state for server-side filtering
  const [agentSearchQuery, setAgentSearchQuery] = useState<string>("");

  const resetForm = () => {
    setName("");
    setTrigger("add_document");
    setActionType("fieldset");
    setSelectedFieldsetId(null);
    setSelectedAnalyzerId(null);
    setSelectedAgentConfigId(null);
    setTaskInstructions("");
    setPreAuthorizedTools([]);
    // Reset inline agent creation state
    setUseInlineAgent(true);
    setInlineAgentName("");
    setInlineAgentDescription("");
    // Reset to the default-trigger instructions; the trigger itself is reset to
    // "add_document" above, so the document-agent default is the matching pair.
    setInlineAgentInstructions(DEFAULT_DOCUMENT_AGENT_INSTRUCTIONS);
    setSelectedModerationTools(DEFAULT_MODERATION_TOOLS.map((t) => t.name));
    setSelectedDocumentTools([]);
    setDisabled(false);
    setRunOnAllCorpuses(false);
    setAgentSearchQuery("");
  };

  // Helper to normalize trigger value to lowercase format
  // (backend returns ADD_DOCUMENT but expects add_document)
  const normalizeTrigger = (trigger: string): TriggerType => {
    const lowered = trigger.toLowerCase();
    if (
      lowered === "add_document" ||
      lowered === "edit_document" ||
      lowered === "new_thread" ||
      lowered === "new_message"
    ) {
      return lowered as TriggerType;
    }
    return "add_document"; // Default fallback
  };

  // Populate form when editing an existing action
  React.useEffect(() => {
    if (actionToEdit && open) {
      setName(actionToEdit.name);
      setTrigger(normalizeTrigger(actionToEdit.trigger));
      setDisabled(actionToEdit.disabled);
      setRunOnAllCorpuses(actionToEdit.runOnAllCorpuses);

      // In edit mode, always use existing agent mode (not inline creation)
      // since the action already has an agent configuration
      setUseInlineAgent(false);

      // Determine action type and set appropriate selection
      if (actionToEdit.agentConfig) {
        setActionType("agent");
        setSelectedAgentConfigId(actionToEdit.agentConfig.id);
        setTaskInstructions(actionToEdit.taskInstructions || "");
        setPreAuthorizedTools(actionToEdit.preAuthorizedTools || []);
        setSelectedFieldsetId(null);
        setSelectedAnalyzerId(null);
      } else if (actionToEdit.analyzer) {
        setActionType("analyzer");
        setSelectedAnalyzerId(actionToEdit.analyzer.id);
        setSelectedFieldsetId(null);
        setSelectedAgentConfigId(null);
      } else if (actionToEdit.fieldset) {
        setActionType("fieldset");
        setSelectedFieldsetId(actionToEdit.fieldset.id);
        setSelectedAnalyzerId(null);
        setSelectedAgentConfigId(null);
      }
    } else if (!open) {
      // Reset form when modal closes
      resetForm();
    }
  }, [actionToEdit, open]);

  const [createCorpusAction] = useMutation<
    CreateCorpusActionOutput,
    CreateCorpusActionInput
  >(CREATE_CORPUS_ACTION, {
    onCompleted: (data) => {
      if (data.createCorpusAction.ok) {
        toast.success("Action created successfully");
        setIsSubmitting(false);
        resetForm();
        onSuccess();
        onClose();
      } else {
        toast.error(
          data.createCorpusAction.message || "Failed to create action"
        );
        setIsSubmitting(false);
      }
    },
    onError: (error) => {
      toast.error("Failed to create action");
      console.error("Error creating corpus action:", error);
      setIsSubmitting(false);
    },
  });

  const [updateCorpusAction] = useMutation<
    UpdateCorpusActionOutput,
    UpdateCorpusActionInput
  >(UPDATE_CORPUS_ACTION, {
    onCompleted: (data) => {
      if (data.updateCorpusAction.ok) {
        toast.success("Action updated successfully");
        setIsSubmitting(false);
        resetForm();
        onSuccess();
        onClose();
      } else {
        toast.error(
          data.updateCorpusAction.message || "Failed to update action"
        );
        setIsSubmitting(false);
      }
    },
    onError: (error) => {
      toast.error("Failed to update action");
      console.error("Error updating corpus action:", error);
      setIsSubmitting(false);
    },
  });

  const { data: fieldsetsData } = useQuery<
    GetFieldsetsOutputs,
    GetFieldsetsInputs
  >(GET_FIELDSETS);

  const { data: analyzersData } = useQuery<
    GetAnalyzersOutputs,
    GetAnalyzersInputs
  >(GET_ANALYZERS);

  const { data: agentConfigsData, loading: agentConfigsLoading } = useQuery<
    GetAgentConfigurationsOutput,
    GetAgentConfigurationsInput
  >(GET_AGENT_CONFIGURATIONS, {
    variables: {
      isActive: true,
      name_Contains: agentSearchQuery || undefined,
      first: 50, // Limit results for performance
    },
    fetchPolicy: "cache-and-network", // Refresh data on mount
  });

  // Debounced search handler for agent dropdown
  const debouncedSetAgentSearch = useCallback(
    _.debounce((query: string) => {
      setAgentSearchQuery(query);
    }, 300),
    []
  );

  const handleAgentSearchChange = (query: string) => {
    debouncedSetAgentSearch(query);
  };

  // Fetch moderation tools dynamically from backend
  // Only fetch when needed (thread/message triggers)
  const isThreadTrigger = trigger === "new_thread" || trigger === "new_message";
  const isDocTrigger =
    trigger === "add_document" || trigger === "edit_document";
  const { data: toolsData, loading: toolsLoading } =
    useQuery<GetAvailableModerationToolsOutput>(
      GET_AVAILABLE_MODERATION_TOOLS,
      {
        skip: !isThreadTrigger,
        fetchPolicy: "cache-first",
      }
    );

  const { data: documentToolsData, loading: documentToolsLoading } =
    useQuery<GetAvailableDocumentToolsOutput>(GET_AVAILABLE_DOCUMENT_TOOLS, {
      skip: !isDocTrigger,
      fetchPolicy: "cache-first",
    });

  const documentTools: AvailableTool[] =
    documentToolsData?.availableTools ?? [];

  // Auto-select all document tools when they load
  React.useEffect(() => {
    if (
      documentTools.length > 0 &&
      selectedDocumentTools.length === 0 &&
      isDocTrigger
    ) {
      setSelectedDocumentTools(documentTools.map((t) => t.name));
    }
  }, [documentTools, isDocTrigger]);

  // Create a memoized tools list that uses API data or falls back to defaults
  const moderationTools = useMemo(() => {
    if (toolsData?.availableTools && toolsData.availableTools.length > 0) {
      return toolsData.availableTools.map((tool) => ({
        name: tool.name,
        description: tool.description,
      }));
    }
    return DEFAULT_MODERATION_TOOLS;
  }, [toolsData]);

  // Get available tools from selected agent config
  const selectedAgentConfig = React.useMemo(() => {
    if (!selectedAgentConfigId || !agentConfigsData) return null;
    return agentConfigsData.agentConfigurations.edges.find(
      (edge) => edge.node.id === selectedAgentConfigId
    )?.node;
  }, [selectedAgentConfigId, agentConfigsData]);

  const handleSubmit = async () => {
    if (!name) {
      toast.error("Please enter a name for the action");
      return;
    }

    if (actionType === "fieldset" && !selectedFieldsetId) {
      toast.error("Please select a fieldset");
      return;
    }

    if (actionType === "analyzer" && !selectedAnalyzerId) {
      toast.error("Please select an analyzer");
      return;
    }

    if (actionType === "agent") {
      // Validation depends on whether we're using inline agent creation or existing agent
      if (useInlineAgent && !isEditMode) {
        // Inline agent creation mode (thread or document triggers)
        if (!inlineAgentName.trim()) {
          toast.error("Please enter a name for the agent");
          return;
        }
        if (!inlineAgentInstructions.trim()) {
          toast.error("Please enter system instructions for the agent");
          return;
        }
        if (!taskInstructions.trim()) {
          toast.error("Please enter task instructions for the agent");
          return;
        }
        const selectedTools = isThreadTrigger
          ? selectedModerationTools
          : selectedDocumentTools;
        if (selectedTools.length === 0) {
          toast.error("Please select at least one tool");
          return;
        }
      } else {
        // Existing agent mode
        if (!selectedAgentConfigId) {
          toast.error("Please select an agent configuration");
          return;
        }
        if (!taskInstructions.trim()) {
          toast.error("Please enter task instructions for the agent");
          return;
        }
      }
    }

    setIsSubmitting(true);

    try {
      if (isEditMode && actionToEdit) {
        // Update existing action (inline creation not supported in edit mode)
        await updateCorpusAction({
          variables: {
            id: actionToEdit.id,
            name,
            trigger,
            fieldsetId:
              actionType === "fieldset"
                ? selectedFieldsetId || undefined
                : undefined,
            analyzerId:
              actionType === "analyzer"
                ? selectedAnalyzerId || undefined
                : undefined,
            agentConfigId:
              actionType === "agent"
                ? selectedAgentConfigId || undefined
                : undefined,
            taskInstructions:
              actionType === "agent" ? taskInstructions : undefined,
            preAuthorizedTools:
              actionType === "agent" && preAuthorizedTools.length > 0
                ? preAuthorizedTools
                : undefined,
            disabled,
            runOnAllCorpuses,
          },
        });
      } else {
        // Create new action - handle inline agent creation if applicable
        const isInlineAgentCreation =
          actionType === "agent" && useInlineAgent && !isEditMode;

        await createCorpusAction({
          variables: {
            corpusId,
            name,
            trigger,
            fieldsetId:
              actionType === "fieldset"
                ? selectedFieldsetId || undefined
                : undefined,
            analyzerId:
              actionType === "analyzer"
                ? selectedAnalyzerId || undefined
                : undefined,
            // Use existing agent if not creating inline
            agentConfigId:
              actionType === "agent" && !isInlineAgentCreation
                ? selectedAgentConfigId || undefined
                : undefined,
            taskInstructions:
              actionType === "agent" ? taskInstructions : undefined,
            // For existing agents, use preAuthorizedTools; for inline, use trigger-appropriate tools
            preAuthorizedTools:
              actionType === "agent"
                ? isInlineAgentCreation
                  ? isThreadTrigger
                    ? selectedModerationTools
                    : selectedDocumentTools
                  : preAuthorizedTools.length > 0
                  ? preAuthorizedTools
                  : undefined
                : undefined,
            // Inline agent creation parameters
            createAgentInline: isInlineAgentCreation ? true : undefined,
            inlineAgentName: isInlineAgentCreation
              ? inlineAgentName
              : undefined,
            inlineAgentDescription: isInlineAgentCreation
              ? inlineAgentDescription || undefined
              : undefined,
            inlineAgentInstructions: isInlineAgentCreation
              ? inlineAgentInstructions
              : undefined,
            inlineAgentTools: isInlineAgentCreation
              ? isThreadTrigger
                ? selectedModerationTools
                : selectedDocumentTools
              : undefined,
            disabled,
            runOnAllCorpuses,
          },
        });
      }
    } catch (error) {
      // Error is handled by the mutation's onError callback
    }
  };

  const triggerOptions = [
    { value: "add_document", label: "On Document Add" },
    { value: "edit_document", label: "On Document Edit" },
    { value: "new_thread", label: "On New Thread" },
    { value: "new_message", label: "On New Message" },
  ];

  // Thread/message triggers only support agent-based actions
  // (isThreadTrigger is defined earlier with the useQuery hooks)

  const actionTypeOptions = [
    { value: "fieldset", label: "Fieldset (Extract data)" },
    { value: "analyzer", label: "Analyzer (Run analysis)" },
    { value: "agent", label: "Agent (AI-powered action)" },
  ];

  const fieldsetOptions: DropdownOption[] = React.useMemo(
    () =>
      fieldsetsData?.fieldsets.edges.map((fieldset) => ({
        value: fieldset.node.id,
        label: fieldset.node.name,
      })) || [],
    [fieldsetsData]
  );

  const analyzerOptions: DropdownOption[] = React.useMemo(
    () =>
      analyzersData?.analyzers.edges.map((analyzer) => ({
        value: analyzer.node.id,
        label: analyzer.node.analyzerId || analyzer.node.id,
      })) || [],
    [analyzersData]
  );

  const agentConfigOptions: DropdownOption[] = React.useMemo(
    () =>
      agentConfigsData?.agentConfigurations.edges.map((config) => ({
        value: config.node.id,
        label: `${config.node.name}${
          config.node.scope === "CORPUS" ? " (Corpus)" : " (Global)"
        }`,
      })) || [],
    [agentConfigsData]
  );

  const toolOptions: DropdownOption[] = React.useMemo(() => {
    if (!selectedAgentConfig?.availableTools) return [];
    return selectedAgentConfig.availableTools.map((tool) => ({
      value: tool,
      label: tool.replace(/_/g, " ").replace(/\b\w/g, (l) => l.toUpperCase()),
    }));
  }, [selectedAgentConfig]);

  return (
    <StyledModal open={open} onClose={onClose} size="md">
      <ModalHeader
        title={isEditMode ? "Edit Corpus Action" : "Create New Corpus Action"}
        onClose={onClose}
      />
      <ModalBody>
        <FormField>
          <label>Name</label>
          <Input
            fullWidth
            value={name}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
              setName(e.target.value)
            }
            placeholder="Enter action name"
          />
        </FormField>

        <FormField>
          <label>Trigger</label>
          <Dropdown
            mode="select"
            aria-label="Trigger"
            options={triggerOptions}
            value={trigger}
            onChange={(value) => {
              const newTrigger = value as
                | "add_document"
                | "edit_document"
                | "new_thread"
                | "new_message";
              setTrigger(newTrigger);
              // Thread/message triggers only support agent-based actions
              if (newTrigger === "new_thread" || newTrigger === "new_message") {
                setActionType("agent");
                setSelectedFieldsetId(null);
                setSelectedAnalyzerId(null);
                // Default to inline agent creation for thread triggers
                setUseInlineAgent(true);
                // Pre-fill inline agent name based on action name
                setInlineAgentName(`${name || "Moderator"} Agent`);
                setInlineAgentInstructions(DEFAULT_MODERATOR_INSTRUCTIONS);
                setSelectedModerationTools(
                  DEFAULT_MODERATION_TOOLS.map((t) => t.name)
                );
              } else {
                // For document triggers, default to inline agent mode
                setUseInlineAgent(true);
                setInlineAgentName("");
                setInlineAgentInstructions(DEFAULT_DOCUMENT_AGENT_INSTRUCTIONS);
                if (documentTools.length > 0) {
                  setSelectedDocumentTools(documentTools.map((t) => t.name));
                }
              }
            }}
          />
        </FormField>

        <FormField>
          <label>Action Type</label>
          <Dropdown
            mode="select"
            aria-label="Action Type"
            disabled={isThreadTrigger}
            options={actionTypeOptions}
            value={actionType}
            onChange={(value) => {
              setActionType(value as ActionType);
              // Clear selections when changing type
              setSelectedFieldsetId(null);
              setSelectedAnalyzerId(null);
              setSelectedAgentConfigId(null);
              setTaskInstructions("");
              setPreAuthorizedTools([]);
            }}
          />
          {isThreadTrigger && (
            <small
              style={{
                color: OS_LEGAL_COLORS.textSecondary,
                marginTop: "0.5em",
                display: "block",
              }}
            >
              Thread/message triggers only support agent-based actions.
            </small>
          )}
        </FormField>

        {actionType === "fieldset" && (
          <div
            style={{
              padding: "1rem",
              border: `1px solid ${OS_LEGAL_COLORS.border}`,
              borderRadius: "8px",
              background: OS_LEGAL_COLORS.surfaceHover,
            }}
          >
            <h4
              style={{
                display: "flex",
                alignItems: "center",
                gap: "0.5rem",
                margin: "0 0 0.5rem 0",
              }}
            >
              <FileText size={16} />
              Fieldset Configuration
            </h4>
            <InfoMessage style={{ marginBottom: "0.75rem" }}>
              Select a fieldset to automatically extract data from documents
              when they are {trigger === "add_document" ? "added" : "edited"}.
            </InfoMessage>
            <FormField>
              <label>Fieldset</label>
              <Dropdown
                mode="select"
                aria-label="Fieldset"
                clearable
                searchable="local"
                options={fieldsetOptions}
                value={selectedFieldsetId ?? null}
                onChange={(value) => setSelectedFieldsetId(value as string)}
                placeholder="Select fieldset"
              />
            </FormField>
          </div>
        )}

        {actionType === "analyzer" && (
          <div
            style={{
              padding: "1rem",
              border: `1px solid ${OS_LEGAL_COLORS.border}`,
              borderRadius: "8px",
              background: OS_LEGAL_COLORS.surfaceHover,
            }}
          >
            <h4
              style={{
                display: "flex",
                alignItems: "center",
                gap: "0.5rem",
                margin: "0 0 0.5rem 0",
              }}
            >
              <Settings size={16} />
              Analyzer Configuration
            </h4>
            <InfoMessage style={{ marginBottom: "0.75rem" }}>
              Select an analyzer to automatically run analysis on documents when
              they are {trigger === "add_document" ? "added" : "edited"}.
            </InfoMessage>
            <FormField>
              <label>Analyzer</label>
              <Dropdown
                mode="select"
                aria-label="Analyzer"
                clearable
                searchable="local"
                options={analyzerOptions}
                value={selectedAnalyzerId ?? null}
                onChange={(value) => setSelectedAnalyzerId(value as string)}
                placeholder="Select analyzer"
              />
            </FormField>
          </div>
        )}

        {actionType === "agent" && (
          <div
            style={{
              padding: "1rem",
              border: `1px solid ${OS_LEGAL_COLORS.border}`,
              borderRadius: "8px",
              background: OS_LEGAL_COLORS.surfaceHover,
            }}
          >
            <h4
              style={{
                display: "flex",
                alignItems: "center",
                gap: "0.5rem",
                margin: "0 0 0.5rem 0",
              }}
            >
              <Cpu size={16} />
              Agent Configuration
            </h4>

            {/* Create mode: Show mode toggle for inline vs existing agent */}
            {!isEditMode && (
              <>
                <InfoMessage style={{ marginBottom: "0.75rem" }}>
                  <>
                    <Info
                      size={14}
                      style={{
                        display: "inline",
                        verticalAlign: "middle",
                        marginRight: "0.5rem",
                      }}
                    />
                    Configure an AI agent for{" "}
                    <strong>
                      {isThreadTrigger
                        ? "automated moderation"
                        : "document processing"}
                    </strong>
                    . The agent will execute automatically when{" "}
                    {trigger === "new_thread"
                      ? "a new discussion thread is created"
                      : trigger === "new_message"
                      ? "a new message is posted to a thread"
                      : trigger === "add_document"
                      ? "a document is added to this corpus"
                      : "a document is edited in this corpus"}
                    .
                  </>
                </InfoMessage>

                <FilterTabs
                  items={
                    [
                      {
                        id: "inline",
                        label: isThreadTrigger
                          ? "Quick Create Moderator"
                          : "Quick Create Agent",
                      },
                      {
                        id: "existing",
                        label: "Use Existing Agent",
                      },
                    ] satisfies FilterTabItem[]
                  }
                  value={useInlineAgent ? "inline" : "existing"}
                  onChange={(id) => setUseInlineAgent(id === "inline")}
                  size="sm"
                />

                {/* Inline Agent Creation Mode */}
                {useInlineAgent && (
                  <>
                    <div
                      style={{
                        padding: "0.5rem 0.75rem",
                        background: OS_LEGAL_COLORS.successSurface,
                        border: `1px solid ${OS_LEGAL_COLORS.successBorder}`,
                        borderRadius: "6px",
                        color: OS_LEGAL_COLORS.successText,
                        fontSize: "0.875rem",
                        marginBottom: "0.75rem",
                      }}
                    >
                      <strong>Quick Create:</strong>{" "}
                      {isThreadTrigger
                        ? "Creates a new moderator agent with all moderation tools enabled."
                        : "Creates a new agent with document processing tools enabled."}
                    </div>

                    <FormField>
                      <label>Agent Name</label>
                      <Input
                        fullWidth
                        value={inlineAgentName}
                        onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                          setInlineAgentName(e.target.value)
                        }
                        placeholder={
                          isThreadTrigger
                            ? "e.g., Discussion Moderator"
                            : "e.g., Document Summarizer"
                        }
                      />
                    </FormField>

                    <FormField>
                      <label>
                        Agent Description <InlineBadge>Optional</InlineBadge>
                      </label>
                      <Input
                        fullWidth
                        value={inlineAgentDescription}
                        onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                          setInlineAgentDescription(e.target.value)
                        }
                        placeholder={
                          isThreadTrigger
                            ? "Brief description of this moderator's purpose"
                            : "Brief description of what this agent does"
                        }
                      />
                    </FormField>

                    <FormField>
                      <label>
                        {isThreadTrigger ? "System Instructions" : "Agent Role"}
                      </label>
                      <StyledTextArea
                        value={inlineAgentInstructions}
                        onChange={(e) =>
                          setInlineAgentInstructions(e.target.value)
                        }
                        placeholder={
                          isThreadTrigger
                            ? "Instructions that define the agent's behavior and policies"
                            : "Brief role description (e.g., 'You are a document summarizer')"
                        }
                        rows={isThreadTrigger ? 4 : 2}
                      />
                      <small
                        style={{
                          color: OS_LEGAL_COLORS.textSecondary,
                          marginTop: "0.5em",
                          display: "block",
                        }}
                      >
                        {isThreadTrigger
                          ? "These instructions define how the agent behaves and what moderation policies it follows."
                          : "Optional persona guidelines. The main instructions go in the Task Instructions field below."}
                      </small>
                    </FormField>

                    <FormField>
                      <label>Task Instructions</label>
                      <StyledTextArea
                        value={taskInstructions}
                        onChange={(e) => setTaskInstructions(e.target.value)}
                        placeholder={
                          isThreadTrigger
                            ? "e.g., 'Review this thread/message for policy compliance and take appropriate action'"
                            : "e.g., 'Summarize this document and update its description'"
                        }
                        rows={3}
                      />
                      <small
                        style={{
                          color: OS_LEGAL_COLORS.textSecondary,
                          marginTop: "0.5em",
                          display: "block",
                        }}
                      >
                        This prompt is sent to the agent each time the action
                        triggers.
                      </small>
                    </FormField>

                    <FormField>
                      <label>
                        {isThreadTrigger
                          ? "Moderation Tools"
                          : "Document Tools"}{" "}
                        <InlineBadge $variant="success">
                          {isThreadTrigger
                            ? selectedModerationTools.length
                            : selectedDocumentTools.length}{" "}
                          selected
                        </InlineBadge>
                        {(isThreadTrigger
                          ? toolsLoading
                          : documentToolsLoading) && <Spinner size="sm" />}
                      </label>
                      <div
                        style={{
                          background: OS_LEGAL_COLORS.gray50,
                          borderRadius: "8px",
                          padding: "1rem",
                          border: `1px solid ${OS_LEGAL_COLORS.gray200}`,
                        }}
                      >
                        {(isThreadTrigger
                          ? moderationTools
                          : documentTools
                        ).map((tool) => (
                          <div
                            key={tool.name}
                            style={{
                              display: "flex",
                              alignItems: "center",
                              padding: "0.5rem 0",
                              borderBottom: `1px solid ${OS_LEGAL_COLORS.gray200}`,
                            }}
                          >
                            <label
                              style={{
                                display: "flex",
                                alignItems: "center",
                                gap: "0.5rem",
                                fontWeight: 500,
                                cursor: "pointer",
                              }}
                            >
                              <input
                                type="checkbox"
                                checked={(isThreadTrigger
                                  ? selectedModerationTools
                                  : selectedDocumentTools
                                ).includes(tool.name)}
                                onChange={(e) => {
                                  const setter = isThreadTrigger
                                    ? setSelectedModerationTools
                                    : setSelectedDocumentTools;
                                  if (e.target.checked) {
                                    setter((prev) => [...prev, tool.name]);
                                  } else {
                                    setter((prev) =>
                                      prev.filter((t) => t !== tool.name)
                                    );
                                  }
                                }}
                              />
                              {tool.name.replace(/_/g, " ")}
                              <span
                                style={{
                                  color: OS_LEGAL_COLORS.textSecondary,
                                  fontWeight: 400,
                                  marginLeft: "0.5rem",
                                }}
                              >
                                - {tool.description}
                              </span>
                            </label>
                          </div>
                        ))}
                      </div>
                      <div style={{ marginTop: "0.5rem" }}>
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={() => {
                            const tools = isThreadTrigger
                              ? moderationTools
                              : documentTools;
                            const setter = isThreadTrigger
                              ? setSelectedModerationTools
                              : setSelectedDocumentTools;
                            setter(tools.map((t) => t.name));
                          }}
                        >
                          Select All
                        </Button>
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={() => {
                            const setter = isThreadTrigger
                              ? setSelectedModerationTools
                              : setSelectedDocumentTools;
                            setter([]);
                          }}
                        >
                          Clear All
                        </Button>
                      </div>
                    </FormField>
                  </>
                )}

                {/* Existing Agent Mode */}
                {!useInlineAgent && (
                  <>
                    <FormField>
                      <label>Agent</label>
                      <Dropdown
                        mode="select"
                        clearable
                        searchable="async"
                        options={agentConfigOptions}
                        value={selectedAgentConfigId ?? null}
                        onChange={(value) => {
                          setSelectedAgentConfigId(value as string);
                          setPreAuthorizedTools([]);
                        }}
                        onSearchChange={handleAgentSearchChange}
                        loading={agentConfigsLoading}
                        placeholder="Select agent configuration"
                      />
                    </FormField>

                    {selectedAgentConfig && (
                      <>
                        <div
                          style={{
                            padding: "0.75rem 1rem",
                            background: OS_LEGAL_COLORS.surfaceHover,
                            border: `1px solid ${OS_LEGAL_COLORS.border}`,
                            borderRadius: "6px",
                            marginBottom: "0.5em",
                          }}
                        >
                          <strong
                            style={{
                              display: "block",
                              marginBottom: "0.25rem",
                            }}
                          >
                            {selectedAgentConfig.name}
                          </strong>
                          <p>{selectedAgentConfig.description}</p>
                        </div>

                        <FormField>
                          <label>Task Instructions</label>
                          <StyledTextArea
                            value={taskInstructions}
                            onChange={(e) =>
                              setTaskInstructions(e.target.value)
                            }
                            placeholder="Enter the task prompt for the agent"
                            rows={4}
                          />
                        </FormField>

                        {toolOptions.length > 0 && (
                          <FormField>
                            <label>
                              Pre-authorized Tools{" "}
                              <InlineBadge $variant="info">
                                Optional
                              </InlineBadge>
                            </label>
                            <Dropdown
                              mode="multiselect"
                              searchable="local"
                              options={toolOptions}
                              value={preAuthorizedTools}
                              onChange={(value) =>
                                setPreAuthorizedTools(value as string[])
                              }
                              placeholder="Select tools to pre-authorize (optional)"
                            />
                          </FormField>
                        )}
                      </>
                    )}
                  </>
                )}
              </>
            )}

            {/* Edit mode: Show existing agent selection only */}
            {isEditMode && (
              <>
                <InfoMessage style={{ marginBottom: "0.5em" }}>
                  <>
                    Select an AI agent to perform custom actions on{" "}
                    <strong>individual documents</strong>. The agent will
                    execute automatically when documents are{" "}
                    {trigger === "add_document" ? "added" : "edited"}.
                    <br />
                    <span
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: "0.3em",
                        marginTop: "0.5em",
                      }}
                    >
                      <Info size={14} />
                      The agent will have access to document-scoped tools
                      (read/update description, summary, notes, annotations).
                    </span>
                  </>
                </InfoMessage>

                <FormField>
                  <label>Agent</label>
                  <Dropdown
                    mode="select"
                    clearable
                    searchable="async"
                    options={agentConfigOptions}
                    value={selectedAgentConfigId ?? null}
                    onChange={(value) => {
                      setSelectedAgentConfigId(value as string);
                      setPreAuthorizedTools([]);
                    }}
                    onSearchChange={handleAgentSearchChange}
                    loading={agentConfigsLoading}
                    placeholder="Select agent configuration"
                  />
                </FormField>

                {selectedAgentConfig && (
                  <>
                    <div
                      style={{
                        padding: "0.75rem 1rem",
                        background: OS_LEGAL_COLORS.surfaceHover,
                        border: `1px solid ${OS_LEGAL_COLORS.border}`,
                        borderRadius: "6px",
                        marginBottom: "0.5em",
                      }}
                    >
                      <strong
                        style={{ display: "block", marginBottom: "0.25rem" }}
                      >
                        {selectedAgentConfig.name}
                      </strong>
                      <p>{selectedAgentConfig.description}</p>
                    </div>

                    <FormField>
                      <label>Task Instructions</label>
                      <StyledTextArea
                        value={taskInstructions}
                        onChange={(e) => setTaskInstructions(e.target.value)}
                        placeholder="Enter the task prompt for the agent (e.g., 'Summarize this document and update its description')"
                        rows={4}
                      />
                    </FormField>

                    {toolOptions.length > 0 && (
                      <FormField>
                        <label>
                          Pre-authorized Tools{" "}
                          <InlineBadge $variant="info">Optional</InlineBadge>
                        </label>
                        <Dropdown
                          mode="multiselect"
                          searchable="local"
                          options={toolOptions}
                          value={preAuthorizedTools}
                          onChange={(value) =>
                            setPreAuthorizedTools(value as string[])
                          }
                          placeholder="Select tools to pre-authorize (optional)"
                        />
                        <small
                          style={{
                            color: OS_LEGAL_COLORS.textSecondary,
                            marginTop: "0.5em",
                            display: "block",
                          }}
                        >
                          Pre-authorized tools will execute without requiring
                          approval. Leave empty to use all available tools with
                          approval gates.
                        </small>
                      </FormField>
                    )}
                  </>
                )}
              </>
            )}
          </div>
        )}

        <FormField>
          <label
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.5em",
              cursor: "pointer",
            }}
          >
            <input
              type="checkbox"
              checked={disabled}
              onChange={(e) => setDisabled(e.target.checked)}
            />
            Initially Disabled
          </label>
        </FormField>

        <FormField>
          <label
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.5em",
              cursor: "pointer",
            }}
          >
            <input
              type="checkbox"
              checked={runOnAllCorpuses}
              onChange={(e) => setRunOnAllCorpuses(e.target.checked)}
            />
            Run on All Corpuses
          </label>
        </FormField>
      </ModalBody>
      <ModalFooter>
        <Button
          variant="secondary"
          onClick={() => {
            resetForm();
            onClose();
          }}
        >
          Cancel
        </Button>
        <Button variant="primary" onClick={handleSubmit} loading={isSubmitting}>
          {isEditMode ? "Update Action" : "Create Action"}
        </Button>
      </ModalFooter>
    </StyledModal>
  );
};
