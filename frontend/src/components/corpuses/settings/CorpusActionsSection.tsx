/**
 * CorpusActionsSection - Corpus actions list with add/edit/delete functionality
 * and integrated template library picker.
 */
import React, { useState, useRef, useEffect, useCallback } from "react";
import { createPortal } from "react-dom";
import { Button, IconButton } from "@os-legal/ui";
import { useQuery, useMutation } from "@apollo/client";
import styled from "styled-components";
import { toast } from "react-toastify";
import {
  Plus,
  Play,
  Pause,
  Edit,
  Trash2,
  Cpu,
  Table,
  Settings,
  User,
  Calendar,
  CheckCircle,
  Library,
} from "lucide-react";
import { CorpusActionData } from "../CreateCorpusActionModal";
import {
  SettingsCard,
  SettingsCardHeader,
  SettingsCardTitle,
  SettingsCardContent,
  ActionFlow,
  ActionCard,
  TriggerBadge,
  ActionStatusBadge,
  AgentPromptBox,
  InfoNote,
} from "../styles/corpusSettingsStyles";
import {
  ADD_TEMPLATE_TO_CORPUS,
  AddTemplateToCorpusInput,
  AddTemplateToCorpusOutput,
} from "../../../graphql/mutations";
import {
  GET_CORPUS_ACTION_TEMPLATES,
  GetCorpusActionTemplatesInput,
  GetCorpusActionTemplatesOutput,
} from "../../../graphql/queries";
import {
  OS_LEGAL_COLORS,
  OS_LEGAL_TYPOGRAPHY,
} from "../../../assets/configurations/osLegalStyles";
import {
  TRIGGER_LABELS,
  Z_INDEX,
  PICKER_DROPDOWN_WIDTH,
  PICKER_DROPDOWN_VIEWPORT_PADDING,
} from "../../../assets/configurations/constants";
import { getCreatorDisplay } from "../../../utils/userDisplay";

// ============================================================================
// Types
// ============================================================================

interface CorpusAction {
  id: string;
  name: string;
  trigger: string;
  disabled: boolean;
  runOnAllCorpuses?: boolean;
  analyzer?: { id: string; name: string } | null;
  fieldset?: { id: string; name: string } | null;
  agentConfig?: { id: string; name: string; description?: string } | null;
  taskInstructions?: string | null;
  preAuthorizedTools?: string[] | null;
  // ``username`` is redacted to ``null`` for non-self viewers per the
  // user privacy contract — only ``id`` and ``slug`` are guaranteed.
  creator: {
    id?: string | null;
    slug?: string | null;
    username?: string | null;
  };
  created: string;
  sourceTemplate?: { id: string; name: string } | null;
}

interface CorpusActionsSectionProps {
  corpusId: string;
  actions: CorpusAction[];
  onAddAction: () => void;
  onEditAction: (action: CorpusActionData) => void;
  onDeleteAction: (id: string) => void;
  onRunAction?: (action: CorpusAction) => void;
  onUpdate?: () => void;
  isSuperuser?: boolean;
}

// ============================================================================
// Styled components for template picker dropdown
// ============================================================================

const PickerContainer = styled.div`
  position: relative;
  display: inline-block;
`;

const PickerDropdown = styled.div`
  position: fixed;
  width: ${PICKER_DROPDOWN_WIDTH}px;
  max-height: 320px;
  overflow-y: auto;
  background: ${OS_LEGAL_COLORS.surface};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
  z-index: ${Z_INDEX.MODAL};
  padding: 0.5rem;
`;

const PickerItem = styled.button<{ disabled?: boolean }>`
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.625rem 0.75rem;
  border: none;
  background: transparent;
  width: 100%;
  text-align: left;
  border-radius: 6px;
  cursor: ${({ disabled }) => (disabled ? "not-allowed" : "pointer")};
  opacity: ${({ disabled }) => (disabled ? 0.5 : 1)};
  pointer-events: ${({ disabled }) => (disabled ? "none" : "auto")};
  transition: background 0.15s ease, opacity 0.15s ease;

  &:hover {
    background: ${({ disabled }) =>
      disabled ? "transparent" : OS_LEGAL_COLORS.surfaceHover};
  }
`;

const PickerItemInfo = styled.div`
  flex: 1;
  min-width: 0;
`;

const PickerItemName = styled.div`
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
  font-size: 0.875rem;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textPrimary};
`;

const PickerItemDesc = styled.div`
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
  font-size: 0.75rem;
  color: ${OS_LEGAL_COLORS.textMuted};
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
`;

const PickerEmpty = styled.div`
  padding: 1rem;
  text-align: center;
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
  font-size: 0.875rem;
  color: ${OS_LEGAL_COLORS.textMuted};
`;

const TemplateBadge = styled.span`
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.125rem 0.5rem;
  border-radius: 100px;
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySans};
  font-size: 0.6875rem;
  font-weight: 500;
  background: ${OS_LEGAL_COLORS.accentLight};
  color: ${OS_LEGAL_COLORS.accent};
  margin-left: 0.5rem;
`;

const HeaderButtonRow = styled.div`
  display: flex;
  gap: 0.5rem;
`;

// ============================================================================
// Component
// ============================================================================

export const CorpusActionsSection: React.FC<CorpusActionsSectionProps> = ({
  corpusId,
  actions,
  onAddAction,
  onEditAction,
  onDeleteAction,
  onRunAction,
  onUpdate,
  isSuperuser,
}) => {
  const [pickerOpen, setPickerOpen] = useState(false);
  const pickerContainerRef = useRef<HTMLDivElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const [dropdownPos, setDropdownPos] = useState<{
    top: number;
    left: number;
  } | null>(null);

  // Compute dropdown position from the button's bounding rect
  const updateDropdownPosition = useCallback(() => {
    if (!pickerContainerRef.current) return;
    const rect = pickerContainerRef.current.getBoundingClientRect();
    setDropdownPos({
      top: rect.bottom + 4,
      left: Math.max(
        PICKER_DROPDOWN_VIEWPORT_PADDING,
        rect.right - PICKER_DROPDOWN_WIDTH
      ),
    });
  }, []);

  // Close dropdown on outside click
  useEffect(() => {
    if (!pickerOpen) return;

    updateDropdownPosition();

    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as Node;
      if (
        pickerContainerRef.current &&
        !pickerContainerRef.current.contains(target) &&
        dropdownRef.current &&
        !dropdownRef.current.contains(target)
      ) {
        setPickerOpen(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    window.addEventListener("scroll", updateDropdownPosition, true);
    window.addEventListener("resize", updateDropdownPosition);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      window.removeEventListener("scroll", updateDropdownPosition, true);
      window.removeEventListener("resize", updateDropdownPosition);
    };
  }, [pickerOpen, updateDropdownPosition]);

  // Fetch available templates only when picker is open
  const { data: templatesData, loading: templatesLoading } = useQuery<
    GetCorpusActionTemplatesOutput,
    GetCorpusActionTemplatesInput
  >(GET_CORPUS_ACTION_TEMPLATES, {
    variables: { isActive: true },
    skip: !pickerOpen,
  });

  const [addTemplate, { loading: addingTemplate }] = useMutation<
    AddTemplateToCorpusOutput,
    AddTemplateToCorpusInput
  >(ADD_TEMPLATE_TO_CORPUS);

  const templates =
    templatesData?.corpusActionTemplates?.edges.map((e) => e.node) || [];

  // Filter out templates already added to the corpus
  const addedTemplateIds = new Set(
    actions.filter((a) => a.sourceTemplate?.id).map((a) => a.sourceTemplate!.id)
  );
  const availableTemplates = templates.filter(
    (t) => !addedTemplateIds.has(t.id)
  );

  const handleAddTemplate = async (templateId: string) => {
    try {
      const { data } = await addTemplate({
        variables: { templateId, corpusId },
      });
      if (data?.addTemplateToCorpus?.ok) {
        toast.success("Action added to corpus");
        onUpdate?.();
      } else {
        toast.error(
          data?.addTemplateToCorpus?.message || "Failed to add template"
        );
      }
    } catch (error: unknown) {
      const msg =
        error instanceof Error ? error.message : "Failed to add template";
      toast.error(msg);
    }
    setPickerOpen(false);
  };

  const getTriggerType = (trigger: string): "add" | "edit" | "chat" => {
    const t = trigger.toLowerCase();
    if (t.includes("add")) return "add";
    if (t.includes("thread") || t.includes("message")) return "chat";
    return "edit";
  };

  const getTriggerLabel = (trigger: string): string => {
    return TRIGGER_LABELS[trigger] || trigger;
  };

  const getActionTypeInfo = (action: CorpusAction) => {
    if (action.agentConfig) {
      return {
        icon: <Cpu size={16} />,
        label: `Agent: ${action.agentConfig.name}`,
      };
    }
    if (action.fieldset) {
      return {
        icon: <Table size={16} />,
        label: `Fieldset: ${action.fieldset.name}`,
      };
    }
    return {
      icon: <Settings size={16} />,
      label: `Analyzer: ${action.analyzer?.name || "Unknown"}`,
    };
  };

  return (
    <SettingsCard>
      <SettingsCardHeader>
        <SettingsCardTitle>Corpus Actions</SettingsCardTitle>
        <HeaderButtonRow>
          <PickerContainer ref={pickerContainerRef}>
            <Button
              size="sm"
              onClick={() => {
                if (!pickerOpen) {
                  updateDropdownPosition();
                }
                setPickerOpen(!pickerOpen);
              }}
              leftIcon={<Library size={14} />}
            >
              Add from Library
            </Button>
            {pickerOpen &&
              dropdownPos &&
              createPortal(
                <PickerDropdown
                  ref={dropdownRef}
                  style={{ top: dropdownPos.top, left: dropdownPos.left }}
                >
                  {templatesLoading ? (
                    <PickerEmpty>Loading templates…</PickerEmpty>
                  ) : availableTemplates.length === 0 ? (
                    <PickerEmpty>All templates have been added</PickerEmpty>
                  ) : (
                    availableTemplates.map((template) => (
                      <PickerItem
                        key={template.id}
                        disabled={addingTemplate}
                        onClick={() => handleAddTemplate(template.id)}
                      >
                        <Cpu
                          size={16}
                          style={{
                            color: OS_LEGAL_COLORS.accent,
                            flexShrink: 0,
                          }}
                        />
                        <PickerItemInfo>
                          <PickerItemName>{template.name}</PickerItemName>
                          {template.description && (
                            <PickerItemDesc>
                              {template.description}
                            </PickerItemDesc>
                          )}
                        </PickerItemInfo>
                        <TriggerBadge type={getTriggerType(template.trigger)}>
                          {getTriggerLabel(template.trigger)}
                        </TriggerBadge>
                      </PickerItem>
                    ))
                  )}
                </PickerDropdown>,
                document.body
              )}
          </PickerContainer>
          <Button
            variant="primary"
            size="sm"
            onClick={onAddAction}
            leftIcon={<Plus size={14} />}
          >
            Add Action
          </Button>
        </HeaderButtonRow>
      </SettingsCardHeader>

      <SettingsCardContent>
        <InfoNote>
          This system allows you to <strong>automate actions</strong> when
          documents are <span className="highlight">added</span> or{" "}
          <span className="highlight">edited</span> in a corpus. You can run
          extractions via <strong>fieldsets</strong>, analyses via{" "}
          <strong>analyzers</strong>, or AI-powered tasks via{" "}
          <strong>agents</strong>.
        </InfoNote>

        <ActionFlow>
          {actions.map((action) => {
            const actionType = getActionTypeInfo(action);
            const triggerType = getTriggerType(action.trigger);

            return (
              <ActionCard key={action.id}>
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "flex-start",
                    gap: "1rem",
                    flexWrap: "wrap",
                  }}
                >
                  <div style={{ flex: 1, minWidth: "200px" }}>
                    <div
                      style={{
                        display: "flex",
                        gap: "0.75rem",
                        alignItems: "center",
                        marginBottom: "0.75rem",
                        flexWrap: "wrap",
                      }}
                    >
                      <h3
                        style={{
                          margin: 0,
                          color: OS_LEGAL_COLORS.textPrimary,
                          fontSize: "1.125rem",
                          fontWeight: 600,
                        }}
                      >
                        {action.name}
                      </h3>
                      {action.sourceTemplate && (
                        <TemplateBadge>
                          <Library size={10} />
                          Template
                        </TemplateBadge>
                      )}
                      <TriggerBadge type={triggerType}>
                        {getTriggerLabel(action.trigger)}
                      </TriggerBadge>
                    </div>

                    <div
                      style={{
                        display: "flex",
                        gap: "1.5rem",
                        color: OS_LEGAL_COLORS.textSecondary,
                        fontSize: "0.9rem",
                        flexWrap: "wrap",
                      }}
                    >
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: "0.375rem",
                        }}
                      >
                        {actionType.icon}
                        {actionType.label}
                      </div>
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: "0.375rem",
                        }}
                      >
                        <User size={16} />
                        {getCreatorDisplay(action.creator)}
                      </div>
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: "0.375rem",
                        }}
                      >
                        <Calendar size={16} />
                        {new Date(action.created).toLocaleDateString()}
                      </div>
                    </div>

                    {action.taskInstructions && (
                      <AgentPromptBox>
                        <div className="prompt-label">Task Instructions:</div>
                        <div className="prompt-text">
                          "
                          {action.taskInstructions.length > 100
                            ? `${action.taskInstructions.substring(0, 100)}...`
                            : action.taskInstructions}
                          "
                        </div>
                        {action.preAuthorizedTools &&
                          action.preAuthorizedTools.length > 0 && (
                            <div className="pre-auth-tools">
                              <CheckCircle
                                size={14}
                                style={{
                                  marginRight: "0.25rem",
                                  color: OS_LEGAL_COLORS.success,
                                }}
                              />
                              Pre-authorized tools:{" "}
                              {action.preAuthorizedTools.join(", ")}
                            </div>
                          )}
                      </AgentPromptBox>
                    )}
                  </div>

                  <div
                    style={{
                      display: "flex",
                      gap: "0.5rem",
                      alignItems: "center",
                      flexShrink: 0,
                    }}
                  >
                    <ActionStatusBadge active={!action.disabled}>
                      {action.disabled ? (
                        <Pause size={14} />
                      ) : (
                        <Play size={14} />
                      )}
                      {action.disabled ? "Disabled" : "Active"}
                    </ActionStatusBadge>

                    {isSuperuser && (
                      <IconButton
                        size="sm"
                        disabled={!!action.fieldset || !!action.analyzer}
                        aria-label={
                          action.fieldset || action.analyzer
                            ? "Only agent actions can be manually triggered"
                            : "Run this action on a document"
                        }
                        title={
                          action.fieldset || action.analyzer
                            ? "Only agent actions can be manually triggered"
                            : "Run this action on a document"
                        }
                        onClick={() => onRunAction?.(action)}
                      >
                        <Play size={14} />
                      </IconButton>
                    )}

                    <IconButton
                      size="sm"
                      onClick={() =>
                        onEditAction(action as unknown as CorpusActionData)
                      }
                      aria-label="Edit action"
                      title="Edit action"
                    >
                      <Edit size={14} />
                    </IconButton>

                    <IconButton
                      size="sm"
                      onClick={() => onDeleteAction(action.id)}
                      aria-label="Delete action"
                      title="Delete action"
                      style={{ color: OS_LEGAL_COLORS.danger }}
                    >
                      <Trash2 size={14} />
                    </IconButton>
                  </div>
                </div>
              </ActionCard>
            );
          })}
        </ActionFlow>
      </SettingsCardContent>
    </SettingsCard>
  );
};
