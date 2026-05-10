import React, {
  useState,
  useRef,
  useEffect,
  useCallback,
  useMemo,
} from "react";
import styled from "styled-components";
import {
  User,
  Bot,
  MoreVertical,
  Pin,
  ChevronDown,
  ChevronUp,
  Edit2,
  Trash2,
  CornerDownRight,
} from "lucide-react";
import { useSetAtom } from "jotai";
import { useMutation } from "@apollo/client";
import {
  CORPUS_COLORS,
  CORPUS_FONTS,
  CORPUS_RADII,
  CORPUS_SHADOWS,
  CORPUS_TRANSITIONS,
  mediaQuery,
} from "./styles/discussionStyles";
import { spacing } from "../../theme/spacing";
import { MessageNode } from "./utils";
import { RelativeTime } from "./RelativeTime";
import { MessageBadges } from "../badges/MessageBadges";
import { MarkdownMessageRenderer } from "./MarkdownMessageRenderer";
import { getCreatorDisplay } from "../../utils/userDisplay";
import { VoteButtons } from "./VoteButtons";
import { UserBadgeType, AgentConfigurationType } from "../../types/graphql-api";
import {
  mapWebSocketSourcesToChatMessageSources,
  ChatMessageSource,
  chatSourcesAtom,
} from "../annotator/context/ChatSourceAtom";
import { WebSocketSources } from "../chat/types";
import { EditMessageModal } from "./EditMessageModal";
import {
  DELETE_MESSAGE,
  DeleteMessageInput,
  DeleteMessageOutput,
} from "../../graphql/mutations";
import { DEFAULT_AGENT_COLOR } from "../../assets/configurations/constants";
import { hexToRgba, isValidHexColor } from "../../utils/colorUtils";
import { OS_LEGAL_COLORS } from "../../assets/configurations/osLegalStyles";

/**
 * Validates that a value is a string
 */
function isString(value: unknown): value is string {
  return typeof value === "string";
}

/**
 * Helper to extract agent display data from configuration.
 * Performs runtime validation of badgeConfig fields to ensure type safety
 * since badgeConfig is a GenericScalar (essentially 'any') from GraphQL.
 */
interface AgentDisplayData {
  name: string;
  color: string;
}

export function getAgentDisplayData(
  agentConfig: AgentConfigurationType | null | undefined
): AgentDisplayData | null {
  if (!agentConfig) return null;

  // Runtime validation: badgeConfig could be any shape from the database
  const badgeConfig = agentConfig.badgeConfig;
  let color = DEFAULT_AGENT_COLOR;

  // Validate badgeConfig is an object and color is a valid hex string
  if (
    badgeConfig &&
    typeof badgeConfig === "object" &&
    !Array.isArray(badgeConfig)
  ) {
    const configColor = (badgeConfig as Record<string, unknown>).color;
    if (isString(configColor) && isValidHexColor(configColor)) {
      color = configColor;
    }
  }

  return {
    name: agentConfig.name,
    color,
  };
}

interface MessageItemProps {
  message: MessageNode;
  isHighlighted?: boolean;
  onReply?: (messageId: string) => void;
  userBadges?: UserBadgeType[];
  /** Whether the current user can edit this message */
  canEdit?: boolean;
  /** Whether the current user can delete this message */
  canDelete?: boolean;
  /** Corpus ID for mention context in edit modal */
  corpusId?: string;
  /** Conversation ID for cache update after edit/delete */
  conversationId?: string;
  /** Callback after successful message update */
  onMessageUpdated?: () => void;
  /** Callback after successful message deletion */
  onMessageDeleted?: () => void;
  /** Current user ID for voting */
  currentUserId?: string;
  /** Parent message author for "Replying to" display */
  parentAuthor?: string;
}

/**
 * Pre-computed agent color values to avoid recalculation in styled-components
 */
interface AgentColorProps {
  $agentColor?: string;
  $agentBgStart?: string;
  $agentBgEnd?: string;
  $agentShadow?: string;
  $agentShadowHover?: string;
}

const MessageContainer = styled.div<
  {
    $depth: number;
    $isHighlighted?: boolean;
    $isDeleted?: boolean;
    $isAgent?: boolean;
  } & AgentColorProps
>`
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 1.25rem 1.5rem;
  background: ${(props) => {
    if (props.$isDeleted) return OS_LEGAL_COLORS.surfaceHover;
    if (props.$isHighlighted) return "#f0fdfa";
    if (props.$isAgent && props.$agentBgStart && props.$agentBgEnd) {
      return `linear-gradient(135deg, ${props.$agentBgStart} 0%, ${props.$agentBgEnd} 100%)`;
    }
    return "transparent";
  }};
  border: none;
  border-radius: 0;
  transition: all 0.2s ease;
  position: relative;

  /* Subtle left accent for nested replies */
  ${(props) =>
    props.$depth > 0 &&
    `
    margin-left: ${Math.min(props.$depth * 1.5, 4)}rem;
    padding-left: 1rem;
    border-left: 2px solid ${OS_LEGAL_COLORS.border};
  `}

  /* Accent strip for highlighted messages */
  ${(props) =>
    props.$isHighlighted &&
    `
    background: #f0fdfa;
    border-left: 3px solid ${OS_LEGAL_COLORS.accent};
  `}

  /* Accent strip for agent messages */
  ${(props) =>
    props.$isAgent &&
    !props.$isHighlighted &&
    `
    border-left: 3px solid ${props.$agentColor || OS_LEGAL_COLORS.accent};
    background: ${props.$agentBgStart || "transparent"};
  `}

  /* Show actions on hover */
  &:hover {
    background: ${(props) => {
      if (props.$isHighlighted) return "#f0fdfa";
      if (props.$isAgent)
        return props.$agentBgStart || OS_LEGAL_COLORS.background;
      return OS_LEGAL_COLORS.background;
    }};
  }

  /* Reveal footer actions on hover */
  &:hover .message-footer-actions {
    opacity: 1;
  }

  ${(props) =>
    props.$isDeleted &&
    `
    opacity: 0.6;
  `}

  ${mediaQuery.mobile} {
    padding: 1rem;

    /* Always show actions on mobile (no hover) */
    .message-footer-actions {
      opacity: 1;
    }
  }
`;

const ContentColumn = styled.div`
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
`;

const MessageHeader = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
`;

const MessageHeaderLeft = styled.div`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex: 1;
  min-width: 0;
`;

const UserAvatar = styled.div<{ $isAgent?: boolean } & AgentColorProps>`
  width: 1.5rem;
  height: 1.5rem;
  border-radius: 50%;
  background: ${(props) =>
    props.$isAgent
      ? `linear-gradient(135deg, ${
          props.$agentColor || OS_LEGAL_COLORS.primaryBlue
        } 0%, ${props.$agentColor || OS_LEGAL_COLORS.primaryBlue}dd 100%)`
      : `linear-gradient(135deg, ${CORPUS_COLORS.teal[600]} 0%, ${CORPUS_COLORS.teal[700]} 100%)`};
  display: flex;
  align-items: center;
  justify-content: center;
  color: ${CORPUS_COLORS.white};
  flex-shrink: 0;

  svg {
    width: 0.75rem;
    height: 0.75rem;
  }

  ${mediaQuery.mobile} {
    width: 1.25rem;
    height: 1.25rem;

    svg {
      width: 0.625rem;
      height: 0.625rem;
    }
  }
`;

const ReplyIndicator = styled.div`
  display: flex;
  align-items: center;
  gap: 0.25rem;
  font-family: ${CORPUS_FONTS.sans};
  font-size: 0.6875rem;
  color: ${CORPUS_COLORS.slate[500]};
  padding: 0.25rem 0.5rem;
  background: ${CORPUS_COLORS.slate[50]};
  border-radius: ${CORPUS_RADII.sm};
  margin-bottom: 0.25rem;

  svg {
    width: 0.75rem;
    height: 0.75rem;
    color: ${CORPUS_COLORS.teal[500]};
  }

  strong {
    color: ${CORPUS_COLORS.teal[700]};
    font-weight: 600;
  }
`;

const UserInfo = styled.div`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  min-width: 0;
  flex-wrap: wrap;
`;

const Username = styled.span`
  font-family: "Inter", -apple-system, BlinkMacSystemFont, sans-serif;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textPrimary};
  font-size: 15px;
`;

const MessageTimestamp = styled.span`
  font-family: ${CORPUS_FONTS.sans};
  font-size: 0.75rem;
  color: ${CORPUS_COLORS.slate[400]};
`;

const MessageActionsContainer = styled.div`
  position: relative;
`;

const MessageActionsButton = styled.button`
  background: none;
  border: none;
  color: ${CORPUS_COLORS.slate[400]};
  cursor: pointer;
  padding: 0.25rem;
  display: flex;
  align-items: center;
  border-radius: ${CORPUS_RADII.sm};
  transition: all ${CORPUS_TRANSITIONS.fast};

  /* Larger touch target on mobile */
  ${mediaQuery.mobile} {
    width: 2.5rem;
    height: 2.5rem;
    justify-content: center;
  }

  &:hover {
    background: ${CORPUS_COLORS.slate[100]};
    color: ${CORPUS_COLORS.slate[700]};
  }

  &:active {
    background: ${CORPUS_COLORS.slate[200]};
  }
`;

const ActionsDropdown = styled.div<{ $isOpen: boolean }>`
  position: absolute;
  top: 100%;
  right: 0;
  margin-top: 0.25rem;
  min-width: 10rem;
  background: ${CORPUS_COLORS.white};
  border: 1px solid ${CORPUS_COLORS.slate[200]};
  border-radius: ${CORPUS_RADII.md};
  box-shadow: ${CORPUS_SHADOWS.lg};
  z-index: 100;
  opacity: ${(props) => (props.$isOpen ? 1 : 0)};
  visibility: ${(props) => (props.$isOpen ? "visible" : "hidden")};
  transform: ${(props) =>
    props.$isOpen ? "translateY(0)" : "translateY(-8px)"};
  transition: all ${CORPUS_TRANSITIONS.fast};

  /* Mobile: Bottom sheet style */
  ${mediaQuery.mobile} {
    position: fixed;
    top: auto;
    left: 0;
    right: 0;
    bottom: 0;
    margin: 0;
    border-radius: ${CORPUS_RADII.xl} ${CORPUS_RADII.xl} 0 0;
    min-width: unset;
    transform: ${(props) =>
      props.$isOpen ? "translateY(0)" : "translateY(100%)"};
    /* Safe area for bottom */
    padding-bottom: env(safe-area-inset-bottom);
  }
`;

const DropdownBackdrop = styled.div<{ $isOpen: boolean }>`
  display: none;

  /* Mobile: Show backdrop for bottom sheet */
  ${mediaQuery.mobile} {
    display: ${(props) => (props.$isOpen ? "block" : "none")};
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.4);
    z-index: 99;
  }
`;

const DropdownItem = styled.button<{ $variant?: "danger" }>`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  width: 100%;
  padding: 0.5rem 0.75rem;
  border: none;
  background: transparent;
  font-family: ${CORPUS_FONTS.sans};
  color: ${(props) =>
    props.$variant === "danger"
      ? OS_LEGAL_COLORS.danger
      : CORPUS_COLORS.slate[700]};
  font-size: 0.875rem;
  text-align: left;
  cursor: pointer;
  transition: background ${CORPUS_TRANSITIONS.fast};

  /* Larger touch targets on mobile */
  ${mediaQuery.mobile} {
    padding: 0.875rem 1rem;
    min-height: 3.25rem;
    font-size: 1rem;
  }

  &:first-child {
    border-radius: ${CORPUS_RADII.md} ${CORPUS_RADII.md} 0 0;
  }

  &:last-child {
    border-radius: 0 0 ${CORPUS_RADII.md} ${CORPUS_RADII.md};
  }

  &:only-child {
    border-radius: ${CORPUS_RADII.md};
  }

  &:hover {
    background: ${(props) =>
      props.$variant === "danger"
        ? OS_LEGAL_COLORS.dangerSurfaceHover
        : CORPUS_COLORS.teal[50]};
    color: ${(props) =>
      props.$variant === "danger"
        ? OS_LEGAL_COLORS.danger
        : CORPUS_COLORS.teal[700]};
  }

  svg {
    flex-shrink: 0;
  }
`;

const DropdownDivider = styled.div`
  height: 1px;
  background: ${CORPUS_COLORS.slate[200]};
  margin: 0.25rem 0;
`;

const MobileDropdownHeader = styled.div`
  display: none;

  ${mediaQuery.mobile} {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0.75rem;
    border-bottom: 1px solid ${CORPUS_COLORS.slate[200]};

    &::before {
      content: "";
      width: 2.5rem;
      height: 0.25rem;
      background: ${CORPUS_COLORS.slate[300]};
      border-radius: 0.125rem;
    }
  }
`;

const DeleteConfirmation = styled.div`
  padding: 1rem;
  text-align: center;
`;

const DeleteConfirmText = styled.p`
  margin: 0 0 1rem 0;
  font-family: ${CORPUS_FONTS.sans};
  color: ${CORPUS_COLORS.slate[700]};
  font-size: 0.875rem;
`;

const DeleteConfirmButtons = styled.div`
  display: flex;
  gap: 0.5rem;
  justify-content: center;

  ${mediaQuery.mobile} {
    flex-direction: column-reverse;
  }
`;

const ConfirmButton = styled.button<{ $variant: "cancel" | "delete" }>`
  padding: 0.5rem 1rem;
  border-radius: ${CORPUS_RADII.md};
  font-family: ${CORPUS_FONTS.sans};
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
  transition: all ${CORPUS_TRANSITIONS.fast};

  ${mediaQuery.mobile} {
    padding: 0.75rem;
    width: 100%;
  }

  &:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  ${(props) =>
    props.$variant === "cancel" &&
    `
    background: ${CORPUS_COLORS.white};
    border: 1px solid ${CORPUS_COLORS.slate[200]};
    color: ${CORPUS_COLORS.slate[700]};

    &:hover:not(:disabled) {
      background: ${CORPUS_COLORS.slate[50]};
    }
  `}

  ${(props) =>
    props.$variant === "delete" &&
    `
    background: ${OS_LEGAL_COLORS.danger};
    border: none;
    color: white;

    &:hover:not(:disabled) {
      background: ${OS_LEGAL_COLORS.dangerHover};
    }
  `}
`;

const MessageContent = styled.div<{ $isDeleted?: boolean }>`
  font-family: "Inter", -apple-system, BlinkMacSystemFont, sans-serif;
  color: ${OS_LEGAL_COLORS.textTertiary};
  line-height: 1.7;
  font-size: 16px;
  word-wrap: break-word;

  ${(props) =>
    props.$isDeleted &&
    `
    font-style: italic;
    color: ${OS_LEGAL_COLORS.textMuted};
  `}

  p {
    margin: 0 0 12px 0;
    line-height: inherit;

    &:last-child {
      margin-bottom: 0;
    }
  }

  code {
    background: ${OS_LEGAL_COLORS.surfaceLight};
    border: 1px solid ${OS_LEGAL_COLORS.border};
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 0.9em;
    font-family: "SF Mono", Monaco, monospace;
    color: ${OS_LEGAL_COLORS.accent};
  }

  pre {
    background: ${OS_LEGAL_COLORS.surfaceHover};
    border: 1px solid ${OS_LEGAL_COLORS.border};
    padding: 16px;
    border-radius: 8px;
    overflow-x: auto;
    margin: 12px 0;
  }

  blockquote {
    border-left: 3px solid #5eead4;
    padding-left: 16px;
    margin: 12px 0;
    color: ${OS_LEGAL_COLORS.textTertiary};
  }
`;

const MessageFooter = styled.div`
  display: flex;
  align-items: center;
  gap: 0.25rem;
  margin-top: 0.25rem;
`;

const FooterActions = styled.div`
  display: flex;
  align-items: center;
  gap: 0.125rem;
  opacity: 0;
  transition: opacity 0.15s ease;
`;

const FooterButton = styled.button`
  background: transparent;
  border: none;
  color: ${OS_LEGAL_COLORS.textMuted};
  cursor: pointer;
  font-family: "Inter", -apple-system, BlinkMacSystemFont, sans-serif;
  font-size: 0.8125rem;
  font-weight: 500;
  padding: 0.375rem 0.625rem;
  border-radius: 6px;
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  transition: all 0.15s ease;

  &:hover {
    background: #f0fdfa;
    color: ${OS_LEGAL_COLORS.accent};
  }

  svg {
    width: 0.875rem;
    height: 0.875rem;
  }
`;

const FooterDivider = styled.span`
  width: 1px;
  height: 1rem;
  background: ${OS_LEGAL_COLORS.border};
  margin: 0 0.25rem;
`;

const ReplyCount = styled.span`
  font-family: ${CORPUS_FONTS.sans};
  font-size: 0.75rem;
  color: ${CORPUS_COLORS.slate[400]};
  margin-left: auto;
`;

const SourcesContainer = styled.div`
  margin-top: 0.75rem;
  border-top: 1px solid ${CORPUS_COLORS.slate[200]};
  padding-top: 0.75rem;
`;

const SourcesHeader = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  cursor: pointer;
  padding: 0.25rem 0;
  user-select: none;

  &:hover {
    opacity: 0.7;
  }
`;

const SourcesTitle = styled.div`
  display: flex;
  align-items: center;
  gap: 0.375rem;
  font-family: ${CORPUS_FONTS.sans};
  font-size: 0.8125rem;
  font-weight: 500;
  color: ${CORPUS_COLORS.slate[600]};

  svg {
    color: ${CORPUS_COLORS.teal[600]};
  }
`;

const SourcesList = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  margin-top: 0.375rem;
`;

const SourceItem = styled.div`
  padding: 0.375rem 0.625rem;
  background: ${CORPUS_COLORS.slate[50]};
  border: 1px solid ${CORPUS_COLORS.slate[200]};
  border-radius: ${CORPUS_RADII.sm};
  font-family: ${CORPUS_FONTS.sans};
  font-size: 0.8125rem;
  color: ${CORPUS_COLORS.slate[700]};
  cursor: pointer;
  transition: all ${CORPUS_TRANSITIONS.fast};

  &:hover {
    background: ${CORPUS_COLORS.teal[50]};
    border-color: ${CORPUS_COLORS.teal[300]};
    color: ${CORPUS_COLORS.teal[700]};
  }
`;

/**
 * Individual message component with support for nested replies.
 * Memoized to prevent unnecessary re-renders when parent thread updates.
 *
 * Part of Issue #686 - Mobile UI improvements for message actions and edit modal.
 */
export const MessageItem = React.memo(function MessageItem({
  message,
  isHighlighted = false,
  onReply,
  userBadges = [],
  canEdit = false,
  canDelete = false,
  corpusId,
  conversationId,
  onMessageUpdated,
  onMessageDeleted,
  currentUserId,
  parentAuthor,
}: MessageItemProps) {
  const isDeleted = !!message.deletedAt;
  const username = getCreatorDisplay(message.creator);

  // Detect if message is from an agent (Issue #688)
  const agentData = useMemo(
    () => getAgentDisplayData(message.agentConfiguration),
    [message.agentConfiguration]
  );
  const isAgent = agentData !== null;

  // Memoize RGBA color values to avoid recalculation in styled-components
  const agentColors = useMemo(() => {
    if (!agentData) return undefined;
    return {
      color: agentData.color,
      bgStart: hexToRgba(agentData.color, 0.08),
      bgEnd: hexToRgba(agentData.color, 0.03),
      shadow: hexToRgba(agentData.color, 0.4),
      shadowHover: hexToRgba(agentData.color, 0.5),
    };
  }, [agentData]);

  // State for sources expansion and selection
  const [sourcesExpanded, setSourcesExpanded] = useState(false);
  const [selectedSourceIndex, setSelectedSourceIndex] = useState<
    number | undefined
  >(undefined);
  const setChatState = useSetAtom(chatSourcesAtom);

  // State for message actions dropdown
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Delete mutation
  const [deleteMessage, { loading: isDeleting }] = useMutation<
    DeleteMessageOutput,
    DeleteMessageInput
  >(DELETE_MESSAGE);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node)
      ) {
        setIsDropdownOpen(false);
        setShowDeleteConfirm(false);
      }
    };

    if (isDropdownOpen) {
      document.addEventListener("mousedown", handleClickOutside);
      return () => {
        document.removeEventListener("mousedown", handleClickOutside);
      };
    }
  }, [isDropdownOpen]);

  // Handle escape key to close dropdown
  useEffect(() => {
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setIsDropdownOpen(false);
        setShowDeleteConfirm(false);
      }
    };

    if (isDropdownOpen) {
      document.addEventListener("keydown", handleEscape);
      return () => {
        document.removeEventListener("keydown", handleEscape);
      };
    }
  }, [isDropdownOpen]);

  const toggleDropdown = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    setIsDropdownOpen((prev) => !prev);
    setShowDeleteConfirm(false);
  }, []);

  const handleEdit = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    setIsDropdownOpen(false);
    setIsEditModalOpen(true);
  }, []);

  const handleDeleteClick = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    setShowDeleteConfirm(true);
  }, []);

  const handleCancelDelete = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    setShowDeleteConfirm(false);
  }, []);

  const handleConfirmDelete = useCallback(
    async (e: React.MouseEvent) => {
      e.stopPropagation();
      try {
        const result = await deleteMessage({
          variables: { messageId: message.id },
        });
        if (result.data?.deleteMessage.ok) {
          setIsDropdownOpen(false);
          setShowDeleteConfirm(false);
          onMessageDeleted?.();
        }
      } catch (err) {
        console.error("Error deleting message:", err);
      }
    },
    [deleteMessage, message.id, onMessageDeleted]
  );

  const closeBackdrop = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    setIsDropdownOpen(false);
    setShowDeleteConfirm(false);
  }, []);

  const hasActions = canEdit || canDelete;

  // Extract and map sources from message.data
  const sources: ChatMessageSource[] = React.useMemo(() => {
    if (!message.data?.sources) return [];
    const mappedSources = mapWebSocketSourcesToChatMessageSources(
      message.data.sources as WebSocketSources[],
      message.id
    );
    // Update chat sources atom when sources change
    if (mappedSources.length > 0) {
      setChatState((prev) => ({
        ...prev,
        messages: [
          ...prev.messages.filter((m) => m.messageId !== message.id),
          {
            messageId: message.id,
            content: message.content || "",
            timestamp: message.created || "",
            sources: mappedSources,
          },
        ],
      }));
    }
    return mappedSources;
  }, [
    message.data?.sources,
    message.id,
    message.content,
    message.created,
    setChatState,
  ]);

  const hasSources = sources.length > 0;

  const handleReply = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (onReply) {
      onReply(message.id);
    }
  };

  const toggleSources = (e: React.MouseEvent) => {
    e.stopPropagation();
    setSourcesExpanded(!sourcesExpanded);
  };

  const handleSourceClick = (index: number) => (e: React.MouseEvent) => {
    e.stopPropagation();
    setSelectedSourceIndex(index === selectedSourceIndex ? undefined : index);
    setChatState((prev) => ({
      ...prev,
      selectedMessageId: message.id,
      selectedSourceIndex: index === prev.selectedSourceIndex ? null : index,
    }));
  };

  return (
    <MessageContainer
      id={`message-${message.id}`}
      $depth={message.depth}
      $isHighlighted={isHighlighted}
      $isDeleted={isDeleted}
      $isAgent={isAgent}
      $agentColor={agentColors?.color}
      $agentBgStart={agentColors?.bgStart}
      $agentBgEnd={agentColors?.bgEnd}
      role="article"
      aria-label={`Message from ${
        isAgent ? `${agentData.name} (AI Agent)` : username
      }`}
    >
      {/* Content Column */}
      <ContentColumn>
        {/* Header */}
        <MessageHeader>
          <MessageHeaderLeft>
            <UserAvatar
              title={isAgent ? `${agentData.name} (AI Agent)` : username}
              $isAgent={isAgent}
              $agentColor={agentColors?.color}
              $agentShadow={agentColors?.shadow}
              $agentShadowHover={agentColors?.shadowHover}
            >
              {isAgent ? <Bot /> : <User />}
            </UserAvatar>
            <UserInfo>
              <Username>{username}</Username>
              <MessageBadges
                message={message}
                userBadges={userBadges}
                maxBadges={2}
                showTooltip={true}
              />
              <MessageTimestamp>
                <RelativeTime date={message.created} />
              </MessageTimestamp>
            </UserInfo>
          </MessageHeaderLeft>

          {/* Message Actions Dropdown */}
          {hasActions && !isDeleted && (
            <>
              <DropdownBackdrop
                $isOpen={isDropdownOpen}
                onClick={closeBackdrop}
              />
              <MessageActionsContainer ref={dropdownRef}>
                <MessageActionsButton
                  aria-label="Message actions"
                  aria-expanded={isDropdownOpen}
                  aria-haspopup="menu"
                  onClick={toggleDropdown}
                >
                  <MoreVertical size={16} />
                </MessageActionsButton>

                <ActionsDropdown $isOpen={isDropdownOpen} role="menu">
                  <MobileDropdownHeader />
                  {showDeleteConfirm ? (
                    <DeleteConfirmation>
                      <DeleteConfirmText>
                        Are you sure you want to delete this message?
                      </DeleteConfirmText>
                      <DeleteConfirmButtons>
                        <ConfirmButton
                          $variant="cancel"
                          onClick={handleCancelDelete}
                          disabled={isDeleting}
                        >
                          Cancel
                        </ConfirmButton>
                        <ConfirmButton
                          $variant="delete"
                          onClick={handleConfirmDelete}
                          disabled={isDeleting}
                        >
                          {isDeleting ? "Deleting..." : "Delete"}
                        </ConfirmButton>
                      </DeleteConfirmButtons>
                    </DeleteConfirmation>
                  ) : (
                    <>
                      {canEdit && (
                        <DropdownItem onClick={handleEdit} role="menuitem">
                          <Edit2 size={16} />
                          Edit message
                        </DropdownItem>
                      )}
                      {canEdit && canDelete && <DropdownDivider />}
                      {canDelete && (
                        <DropdownItem
                          onClick={handleDeleteClick}
                          $variant="danger"
                          role="menuitem"
                        >
                          <Trash2 size={16} />
                          Delete message
                        </DropdownItem>
                      )}
                    </>
                  )}
                </ActionsDropdown>
              </MessageActionsContainer>
            </>
          )}
        </MessageHeader>

        {/* Edit Message Modal */}
        <EditMessageModal
          isOpen={isEditModalOpen}
          onClose={() => setIsEditModalOpen(false)}
          messageId={message.id}
          initialContent={message.content || ""}
          corpusId={corpusId}
          conversationId={conversationId}
          onSuccess={onMessageUpdated}
        />

        {/* Reply indicator */}
        {message.depth > 0 && parentAuthor && (
          <ReplyIndicator>
            <CornerDownRight />
            Replying to <strong>@{parentAuthor}</strong>
          </ReplyIndicator>
        )}

        {/* Content */}
        <MessageContent $isDeleted={isDeleted}>
          {isDeleted ? (
            <p>[This message has been deleted]</p>
          ) : (
            <MarkdownMessageRenderer
              content={message.content || ""}
              mentionedResources={message.mentionedResources ?? undefined}
            />
          )}
        </MessageContent>

        {/* PDF Annotation Sources */}
        {!isDeleted && hasSources && (
          <SourcesContainer className="source-preview-container">
            <SourcesHeader onClick={toggleSources}>
              <SourcesTitle>
                <Pin size={14} />
                {sources.length} {sources.length === 1 ? "Source" : "Sources"}
              </SourcesTitle>
              {sourcesExpanded ? (
                <ChevronUp size={14} />
              ) : (
                <ChevronDown size={14} />
              )}
            </SourcesHeader>
            {sourcesExpanded && (
              <SourcesList>
                {sources.map((source, index) => (
                  <SourceItem
                    key={source.id}
                    className="source-chip"
                    onClick={handleSourceClick(index)}
                  >
                    {source.rawText || `Source ${index + 1}`}
                  </SourceItem>
                ))}
              </SourcesList>
            )}
          </SourcesContainer>
        )}

        {/* Footer */}
        {!isDeleted && (
          <MessageFooter>
            <FooterActions className="message-footer-actions">
              <VoteButtons
                messageId={message.id}
                upvoteCount={message.upvoteCount ?? 0}
                downvoteCount={message.downvoteCount ?? 0}
                userVote={message.userVote}
                senderId={message.creator?.id || ""}
                currentUserId={currentUserId}
                disabled={isDeleted}
                compact
              />
              <FooterDivider />
              <FooterButton
                onClick={handleReply}
                aria-label="Reply to this message"
              >
                <CornerDownRight />
                Reply
              </FooterButton>
            </FooterActions>

            {message.children && message.children.length > 0 && (
              <ReplyCount>
                {message.children.length}{" "}
                {message.children.length === 1 ? "reply" : "replies"}
              </ReplyCount>
            )}
          </MessageFooter>
        )}
      </ContentColumn>
    </MessageContainer>
  );
});
