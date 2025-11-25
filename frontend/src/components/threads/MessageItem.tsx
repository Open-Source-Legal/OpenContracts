import React, { useState } from "react";
import styled from "styled-components";
import { User, MoreVertical, Pin, ChevronDown, ChevronUp } from "lucide-react";
import { useSetAtom } from "jotai";
import { color } from "../../theme/colors";
import { spacing } from "../../theme/spacing";
import { MessageNode } from "./utils";
import { RelativeTime } from "./RelativeTime";
import { MessageBadges } from "../badges/MessageBadges";
import { MarkdownMessageRenderer } from "./MarkdownMessageRenderer";
import { formatUsername } from "./userUtils";
import { UserBadgeType } from "../../types/graphql-api";
import {
  mapWebSocketSourcesToChatMessageSources,
  ChatMessageSource,
  chatSourcesAtom,
} from "../annotator/context/ChatSourceAtom";
import { WebSocketSources } from "../knowledge_base/document/right_tray/ChatTray";

interface MessageItemProps {
  message: MessageNode;
  isHighlighted?: boolean;
  onReply?: (messageId: string) => void;
  userBadges?: UserBadgeType[];
}

const MessageContainer = styled.div<{
  $depth: number;
  $isHighlighted?: boolean;
  $isDeleted?: boolean;
}>`
  /* CRITICAL: Block-level display to prevent shrinking */
  display: block;

  /* Simple indentation for nested messages */
  margin-left: ${(props) => `${props.$depth * 40}px`};
  margin-right: 0;

  /* FORCE full width usage - no shrinking to content! */
  width: calc(100% - ${(props) => props.$depth * 40}px) !important;
  min-width: min(800px, calc(100% - ${(props) => props.$depth * 40}px));
  max-width: none;
  box-sizing: border-box;

  /* Generous padding for readability */
  padding: 1.5rem;

  background: ${(props) => {
    if (props.$isDeleted) return "#f3f4f6";
    if (props.$isHighlighted)
      return `linear-gradient(135deg, #e0f2fe 0%, #f0f9ff 100%)`;
    return "#ffffff";
  }};

  border: 1px solid
    ${(props) => {
      if (props.$isHighlighted) return "#3b82f6";
      return "#d1d5db";
    }};

  border-radius: 12px;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  margin-bottom: 1.5rem;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05), 0 1px 3px rgba(0, 0, 0, 0.08);
  position: relative;

  ${(props) =>
    props.$isHighlighted &&
    `
    &::before {
      content: '';
      position: absolute;
      left: 0;
      top: 0;
      bottom: 0;
      width: 4px;
      background: linear-gradient(180deg, ${color.B6} 0%, ${color.B5} 100%);
      border-radius: 16px 0 0 16px;
    }
  `}

  &:hover {
    box-shadow: 0 10px 25px rgba(0, 0, 0, 0.08), 0 4px 10px rgba(0, 0, 0, 0.05);
    transform: translateY(-1px);
    border-color: ${(props) => (props.$isHighlighted ? "#2563eb" : "#9ca3af")};
  }

  ${(props) =>
    props.$isDeleted &&
    `
    opacity: 0.7;
    background: #f3f4f6;
  `}

  /* Tablet adjustments */
  @media (max-width: 1024px) {
    margin-left: ${(props) => `${props.$depth * 30}px`};
    width: calc(100% - ${(props) => props.$depth * 30}px) !important;
    min-width: min(650px, calc(100% - ${(props) => props.$depth * 30}px));
    padding: 1.25rem;
  }

  /* Mobile adjustments */
  @media (max-width: 768px) {
    margin-left: ${(props) => `${props.$depth * 20}px`};
    width: calc(100% - ${(props) => props.$depth * 20}px) !important;
    min-width: min(450px, calc(100% - ${(props) => props.$depth * 20}px));
    padding: 1rem;
  }

  @media (max-width: 480px) {
    margin-left: ${(props) => `${Math.min(props.$depth * 16, 32)}px`};
    width: calc(
      100% - ${(props) => Math.min(props.$depth * 16, 32)}px
    ) !important;
    min-width: 280px;
    padding: 0.875rem;
    border-radius: 12px;
  }
`;

const MessageHeader = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 0.875rem;
  padding-bottom: 0.875rem;
  border-bottom: 1px solid #e5e7eb;
`;

const MessageHeaderLeft = styled.div`
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex: 1;
  min-width: 0;
`;

const UserAvatar = styled.div`
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-weight: 700;
  font-size: 16px;
  flex-shrink: 0;
  box-shadow: 0 4px 14px rgba(99, 102, 241, 0.3);
  transition: all 0.2s ease;

  &:hover {
    transform: scale(1.05);
    box-shadow: 0 6px 16px rgba(102, 126, 234, 0.35);
  }

  @media (max-width: 480px) {
    width: 36px;
    height: 36px;
    font-size: 14px;
  }
`;

const UserInfo = styled.div`
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
`;

const UsernameRow = styled.div`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
`;

const Username = styled.span`
  font-weight: 700;
  color: #111827;
  font-size: 15px;
  letter-spacing: -0.01em;
`;

const MessageTimestamp = styled.span`
  font-size: 13px;
  color: #6b7280;
  font-weight: 500;
`;

const MessageActions = styled.button`
  background: none;
  border: none;
  color: ${color.N6};
  cursor: pointer;
  padding: 4px;
  display: flex;
  align-items: center;
  border-radius: 4px;

  &:hover {
    background: ${color.N3};
    color: ${color.N9};
  }
`;

const MessageContent = styled.div<{ $isDeleted?: boolean }>`
  color: #1f2937;
  line-height: 1.65;
  margin-bottom: 1rem;
  font-size: 14px;
  word-wrap: break-word;

  ${(props) =>
    props.$isDeleted &&
    `
    font-style: italic;
    color: #6b7280;
  `}

  p {
    margin: 0 0 0.75rem 0;
    line-height: inherit;
    color: #1f2937;
  }

  code {
    background: #f3f4f6;
    border: 1px solid #e5e7eb;
    padding: 2px 6px;
    border-radius: 3px;
    font-size: 0.9em;
    font-family: monospace;
    color: #dc2626;
  }

  pre {
    background: #f9fafb;
    border: 1px solid #e5e7eb;
    padding: 0.75rem;
    border-radius: 4px;
    overflow-x: auto;
    margin: 0.75rem 0;
  }

  blockquote {
    border-left: 3px solid #3b82f6;
    padding-left: 1rem;
    margin: 0.75rem 0;
    color: #4b5563;
  }

  @media (max-width: 768px) {
    font-size: 14px;
    line-height: 1.55;
  }

  @media (max-width: 480px) {
    font-size: 13px;
    line-height: 1.5;
  }
`;

const MessageFooter = styled.div`
  display: flex;
  align-items: center;
  gap: ${spacing.md};

  @media (max-width: 640px) {
    flex-wrap: wrap;
    gap: ${spacing.xs};
  }
`;

const FooterButton = styled.button`
  background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
  border: 1px solid #93c5fd;
  color: #1e40af;
  cursor: pointer;
  font-size: 14px;
  font-weight: 600;
  padding: 8px 16px;
  border-radius: 8px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  flex-shrink: 0;

  &:hover {
    background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
    border-color: #2563eb;
    color: white;
    transform: translateY(-1px);
    box-shadow: 0 4px 14px rgba(59, 130, 246, 0.4);
  }

  &:active {
    transform: translateY(0);
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.15);
  }
`;

const ReplyCount = styled.span`
  font-size: 12px;
  color: ${color.N6};
  margin-left: auto;
`;

const SourcesContainer = styled.div`
  margin-top: ${spacing.sm};
  border-top: 1px solid ${color.N4};
  padding-top: ${spacing.sm};
`;

const SourcesHeader = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  cursor: pointer;
  padding: ${spacing.xs} 0;
  user-select: none;

  &:hover {
    opacity: 0.7;
  }
`;

const SourcesTitle = styled.div`
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 500;
  color: ${color.N7};
`;

const SourcesList = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${spacing.xs};
  margin-top: ${spacing.xs};
`;

const SourceItem = styled.div`
  padding: ${spacing.xs} ${spacing.sm};
  background: ${color.N2};
  border: 1px solid ${color.N4};
  border-radius: 4px;
  font-size: 13px;
  color: ${color.N8};
  cursor: pointer;
  transition: all 0.2s;

  &:hover {
    background: ${color.N3};
    border-color: ${color.B5};
  }
`;

/**
 * Individual message component with support for nested replies
 */
export function MessageItem({
  message,
  isHighlighted = false,
  onReply,
  userBadges = [],
}: MessageItemProps) {
  const isDeleted = !!message.deletedAt;
  const username = formatUsername(
    message.creator?.username,
    message.creator?.email
  );

  // State for sources expansion and selection
  const [sourcesExpanded, setSourcesExpanded] = useState(false);
  const [selectedSourceIndex, setSelectedSourceIndex] = useState<
    number | undefined
  >(undefined);
  const setChatState = useSetAtom(chatSourcesAtom);

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
      role="article"
      aria-label={`Message from ${username}`}
    >
      {/* Header */}
      <MessageHeader>
        <MessageHeaderLeft>
          <UserAvatar title={username}>
            <User size={16} />
          </UserAvatar>
          <UserInfo>
            <UsernameRow>
              <Username>{username}</Username>
              <MessageBadges
                message={message}
                userBadges={userBadges}
                maxBadges={3}
                showTooltip={true}
              />
            </UsernameRow>
            <MessageTimestamp>
              <RelativeTime date={message.created} />
            </MessageTimestamp>
          </UserInfo>
        </MessageHeaderLeft>

        <MessageActions
          aria-label="Message actions"
          onClick={(e) => e.stopPropagation()}
        >
          <MoreVertical size={16} />
        </MessageActions>
      </MessageHeader>

      {/* Content */}
      <MessageContent $isDeleted={isDeleted}>
        {isDeleted ? (
          <p>[This message has been deleted]</p>
        ) : (
          // Render markdown content with styled mentions (Issue #623)
          <MarkdownMessageRenderer content={message.content || ""} />
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
          {/* Vote buttons placeholder - will be added in #575 */}
          {/* <VoteButtons message={message} /> */}

          {/* Reply button */}
          <FooterButton
            onClick={handleReply}
            aria-label="Reply to this message"
          >
            Reply
          </FooterButton>

          {/* Reply count */}
          {message.children && message.children.length > 0 && (
            <ReplyCount>
              {message.children.length}{" "}
              {message.children.length === 1 ? "reply" : "replies"}
            </ReplyCount>
          )}
        </MessageFooter>
      )}
    </MessageContainer>
  );
}
