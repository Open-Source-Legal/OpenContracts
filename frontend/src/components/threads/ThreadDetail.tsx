import { useCallback, useEffect, useMemo, useState } from "react";
import styled from "styled-components";
import { useQuery, useReactiveVar } from "@apollo/client";
import { useAtom } from "jotai";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  ArrowLeft,
  MessageCircle,
  FileText,
  Pin,
  Lock,
  Trash2,
  Users,
} from "lucide-react";
import {
  GET_THREAD_DETAIL,
  GetThreadDetailInput,
  GetThreadDetailOutput,
} from "../../graphql/queries";
import {
  CORPUS_COLORS,
  CORPUS_FONTS,
  CORPUS_RADII,
  CORPUS_SHADOWS,
  CORPUS_TRANSITIONS,
  mediaQuery,
} from "./styles/discussionStyles";
import { OS_LEGAL_COLORS } from "../../assets/configurations/osLegalStyles";
import {
  selectedMessageIdAtom,
  replyingToMessageIdAtom,
} from "../../atoms/threadAtoms";
import { buildMessageTree } from "./utils";
import { MessageTree } from "./MessageTree";
import { RelativeTime } from "./RelativeTime";
import {
  DiscussionTypeBadge,
  inferDiscussionCategory,
} from "./DiscussionTypeBadge";
import { ModernLoadingDisplay } from "../widgets/ModernLoadingDisplay";
import { ModernErrorDisplay } from "../widgets/ModernErrorDisplay";
import { PlaceholderCard } from "../placeholders/PlaceholderCard";
import { useMessageBadges } from "../../hooks/useMessageBadges";
import { openedCorpus, backendUserObj } from "../../graphql/cache";
import { ReplyForm } from "./ReplyForm";
import { getCreatorDisplay } from "../../utils/userDisplay";
import { getCorpusUrl } from "../../utils/navigationUtils";

interface ThreadDetailProps {
  conversationId: string;
  corpusId?: string;
  /** Compact mode for sidebar (narrower padding) */
  compact?: boolean;
  /**
   * Custom back handler. If provided, overrides default navigation behavior.
   * Used by sidebar to stay inline instead of navigating away.
   */
  onBack?: () => void;
}

const Container = styled.div`
  display: flex;
  flex-direction: column;
  height: 100%;
  background: ${OS_LEGAL_COLORS.background};
`;

const Header = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 0.5rem 2rem;
  background: ${CORPUS_COLORS.white};
  border-bottom: 1px solid ${CORPUS_COLORS.slate[200]};
  gap: 0.5rem;
  min-width: 0;

  ${mediaQuery.tablet} {
    padding: 0.75rem 1rem;
    flex-direction: column;
    gap: 0.5rem;
  }
`;

const HeaderLeft = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  flex: 1;
  min-width: 0;

  ${mediaQuery.tablet} {
    gap: 0.5rem;
    width: 100%;
  }
`;

const BackButton = styled.button`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0.25rem;
  border: none;
  border-radius: ${CORPUS_RADII.sm};
  background: transparent;
  color: ${CORPUS_COLORS.slate[400]};
  cursor: pointer;
  transition: all ${CORPUS_TRANSITIONS.fast};
  flex-shrink: 0;

  &:hover {
    background: ${CORPUS_COLORS.slate[100]};
    color: ${CORPUS_COLORS.teal[700]};
  }

  svg {
    width: 1.125rem;
    height: 1.125rem;
  }
`;

const ContextLink = styled.a`
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.25rem 0.5rem;
  background: ${CORPUS_COLORS.slate[50]};
  border: 1px solid ${CORPUS_COLORS.slate[200]};
  border-radius: ${CORPUS_RADII.sm};
  font-family: ${CORPUS_FONTS.sans};
  font-size: 0.75rem;
  font-weight: 500;
  color: ${CORPUS_COLORS.slate[600]};
  text-decoration: none;
  transition: all ${CORPUS_TRANSITIONS.fast};

  &:hover {
    border-color: ${CORPUS_COLORS.teal[300]};
    background: ${CORPUS_COLORS.teal[50]};
    color: ${CORPUS_COLORS.teal[700]};
  }

  svg {
    width: 0.75rem;
    height: 0.75rem;
  }
`;

const StatusBadge = styled.span<{ $variant: "pinned" | "locked" | "deleted" }>`
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.25rem 0.5rem;
  border-radius: ${CORPUS_RADII.full};
  font-family: ${CORPUS_FONTS.sans};
  font-size: 0.6875rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.03em;

  ${(props) =>
    props.$variant === "pinned" &&
    `
    background: ${CORPUS_COLORS.teal[50]};
    color: ${CORPUS_COLORS.teal[700]};
    border: 1px solid ${CORPUS_COLORS.teal[200]};
  `}

  ${(props) =>
    props.$variant === "locked" &&
    `
    background: #fef3c7;
    color: #92400e;
    border: 1px solid #fcd34d;
  `}

  ${(props) =>
    props.$variant === "deleted" &&
    `
    background: ${CORPUS_COLORS.slate[100]};
    color: ${CORPUS_COLORS.slate[500]};
    border: 1px solid ${CORPUS_COLORS.slate[300]};
  `}

  svg {
    width: 0.75rem;
    height: 0.75rem;
  }
`;

const TitleRow = styled.div`
  display: flex;
  align-items: baseline;
  gap: 0.375rem 0.5rem;
  min-width: 0;
  flex-wrap: wrap;
`;

const Title = styled.h1`
  font-family: "Georgia", "Times New Roman", serif;
  font-size: 1.25rem;
  font-weight: 400;
  color: ${OS_LEGAL_COLORS.textPrimary};
  margin: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;

  ${mediaQuery.tablet} {
    flex-basis: 100%;
    font-size: 1.0625rem;
    line-height: 1.3;
    white-space: normal;
    overflow: visible;
    word-break: break-word;
  }
`;

const Description = styled.span`
  font-family: ${CORPUS_FONTS.sans};
  font-size: 0.75rem;
  color: ${CORPUS_COLORS.slate[400]};
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
  flex: 1;

  ${mediaQuery.tablet} {
    flex: 1 1 100%;
    min-width: 0;
    white-space: normal;
    overflow-wrap: anywhere;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    line-height: 1.4;
  }
`;

const MetaRow = styled.div`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-family: ${CORPUS_FONTS.sans};
  font-size: 0.75rem;
  color: ${CORPUS_COLORS.slate[500]};
  flex-wrap: wrap;
  row-gap: 0.25rem;
  min-width: 0;
`;

const MetaItem = styled.span`
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;

  strong {
    color: ${CORPUS_COLORS.slate[700]};
    font-weight: 600;
  }

  svg {
    width: 0.875rem;
    height: 0.875rem;
    color: ${CORPUS_COLORS.teal[600]};
  }
`;

const MetaDot = styled.span`
  color: ${CORPUS_COLORS.slate[300]};
`;

const ContentArea = styled.div`
  flex: 1;
  overflow: auto;
  padding: 16px 24px;

  ${mediaQuery.tablet} {
    padding: 12px 16px;
  }
`;

const MessageListContainer = styled.div`
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: 900px;
  margin: 0 auto;
  width: 100%;
`;

const EmptyMessageState = styled.div`
  text-align: center;
  padding: 3rem;
  color: ${CORPUS_COLORS.slate[500]};
`;

const ReplyComposerArea = styled.div`
  padding: 0.5rem 2rem 0.75rem;
  background: ${CORPUS_COLORS.white};
  border-top: 1px solid ${CORPUS_COLORS.slate[200]};

  ${mediaQuery.tablet} {
    padding: 0.5rem 1rem 0.75rem;
  }
`;

const ReplyComposerInner = styled.div`
  max-width: 900px;
  margin: 0 auto;
`;

/**
 * Thread detail view - shows full thread with all messages
 * Supports deep linking to specific messages via ?message=id query param
 */
export function ThreadDetail({
  conversationId,
  corpusId,
  compact = false,
  onBack: customOnBack,
}: ThreadDetailProps) {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [selectedMessageId, setSelectedMessageId] = useAtom(
    selectedMessageIdAtom
  );
  const [replyingToMessageId, setReplyingToMessageId] = useAtom(
    replyingToMessageIdAtom
  );

  // Get current user for permission checking
  const currentUser = useReactiveVar(backendUserObj);

  // Fetch thread detail
  const { data, loading, error, refetch } = useQuery<
    GetThreadDetailOutput,
    GetThreadDetailInput
  >(GET_THREAD_DETAIL, {
    variables: { conversationId },
    fetchPolicy: "cache-and-network",
  });

  const thread = data?.conversation;

  /**
   * Determine if current user can moderate this thread.
   * Moderators can edit/delete any message in the thread.
   *
   * A user can moderate if they are:
   * 1. The thread creator
   * 2. The corpus owner (if thread is linked to a corpus)
   * 3. The document owner (if thread is linked to a document)
   */
  const canModerate = useMemo(() => {
    if (!currentUser || !thread) return false;

    // Thread creator can moderate
    if (thread.creator?.id === currentUser.id) return true;

    // Corpus owner can moderate
    if (thread.chatWithCorpus?.creator?.id === currentUser.id) return true;

    // Document owner can moderate
    if (thread.chatWithDocument?.creator?.id === currentUser.id) return true;

    return false;
  }, [currentUser, thread]);

  // Callback for message updates/deletes - refetch thread data
  const handleMessageChange = useCallback(() => {
    refetch();
  }, [refetch]);

  // Extract unique user IDs from messages
  const userIds = useMemo(() => {
    if (!thread?.allMessages) return [];
    const uniqueIds = new Set(
      thread.allMessages
        .filter((msg) => msg.msgType !== "AGENT") // Only fetch badges for human users
        .map((msg) => msg.creator.id)
    );
    return Array.from(uniqueIds);
  }, [thread?.allMessages]);

  // Fetch badges for all message creators
  const { badgesByUser } = useMessageBadges(userIds, corpusId);

  // Build message tree
  const messageTree = useMemo(() => {
    if (!thread?.allMessages) return [];
    return buildMessageTree(thread.allMessages);
  }, [thread?.allMessages]);

  // Handle deep linking to specific message
  useEffect(() => {
    const messageId = searchParams.get("message");

    if (messageId && thread?.allMessages) {
      // Wait for messages to render
      setTimeout(() => {
        const messageEl = document.getElementById(`message-${messageId}`);
        if (messageEl) {
          messageEl.scrollIntoView({ behavior: "smooth", block: "center" });
          setSelectedMessageId(messageId);

          // Remove highlight after 3 seconds
          setTimeout(() => setSelectedMessageId(null), 3000);
        }
      }, 100);
    }
  }, [searchParams, thread, setSelectedMessageId]);

  // Handle reply action
  const handleReply = (messageId: string) => {
    console.log("Reply to message:", messageId);
    setReplyingToMessageId(messageId);
  };

  // Handle back navigation
  const corpus = useReactiveVar(openedCorpus);
  const handleBack = () => {
    // If custom handler provided (e.g., sidebar), use that instead of navigation
    if (customOnBack) {
      customOnBack();
      return;
    }

    // Default: Navigate back to corpus discussions tab using utility
    if (corpus) {
      const url = getCorpusUrl(corpus, { tab: "discussions" });
      if (url !== "#") {
        navigate(url);
        return;
      }
    }
    // Fallback to browser history
    navigate(-1);
  };

  // Find the message being replied to (for bottom composer context)
  const replyTargetMessage = useMemo(() => {
    if (!replyingToMessageId || !thread?.allMessages) return null;
    return (
      thread.allMessages.find((msg) => msg.id === replyingToMessageId) || null
    );
  }, [replyingToMessageId, thread?.allMessages]);

  // Infer discussion category from title/description
  const discussionCategory = useMemo(() => {
    if (!thread) return "question";
    return inferDiscussionCategory(thread.title || "", thread.description);
  }, [thread]);

  // Loading state
  if (loading && !data) {
    return (
      <Container>
        <ModernLoadingDisplay
          type="default"
          message="Loading discussion..."
          size="medium"
        />
      </Container>
    );
  }

  // Error state
  if (error || !thread) {
    return (
      <Container>
        <ModernErrorDisplay
          type="generic"
          error={error?.message || "Thread not found"}
          onRetry={() => refetch()}
        />
      </Container>
    );
  }

  const isDeleted = !!thread.deletedAt;
  const messageCount = thread.allMessages?.length || 0;

  return (
    <Container>
      {/* Compact Header */}
      <Header data-testid="thread-header">
        <HeaderLeft>
          {/* Title row: Back + badge + title + status badges */}
          <TitleRow>
            {compact && (
              <BackButton onClick={handleBack} aria-label="Back to discussions">
                <ArrowLeft />
              </BackButton>
            )}
            <DiscussionTypeBadge category={discussionCategory} />
            <Title>{thread.title || "Untitled Discussion"}</Title>

            {thread.description && (
              <Description title={thread.description}>
                {thread.description}
              </Description>
            )}

            {thread.chatWithDocument && (
              <ContextLink
                href="#"
                title={`Linked to document: ${thread.chatWithDocument.title}`}
              >
                <FileText />
                {thread.chatWithDocument.title}
              </ContextLink>
            )}

            {thread.isPinned && (
              <StatusBadge $variant="pinned">
                <Pin />
                Pinned
              </StatusBadge>
            )}
            {thread.isLocked && (
              <StatusBadge $variant="locked">
                <Lock />
                Locked
              </StatusBadge>
            )}
            {isDeleted && (
              <StatusBadge $variant="deleted">
                <Trash2 />
                Deleted
              </StatusBadge>
            )}
          </TitleRow>

          {/* Meta row: Author + time + message count */}
          <MetaRow>
            <MetaItem>
              <Users />
              <strong>{getCreatorDisplay(thread.creator)}</strong>
            </MetaItem>
            <MetaDot>•</MetaDot>
            <MetaItem>
              <RelativeTime date={thread.createdAt} />
            </MetaItem>
            <MetaDot>•</MetaDot>
            <MetaItem>
              <MessageCircle />
              {messageCount} {messageCount === 1 ? "message" : "messages"}
            </MetaItem>
          </MetaRow>
        </HeaderLeft>
      </Header>

      {/* Messages area */}
      <ContentArea>
        {messageTree.length === 0 ? (
          <EmptyMessageState>
            <PlaceholderCard
              title="No messages yet"
              description="Be the first to post a message in this discussion."
              compact
            />
          </EmptyMessageState>
        ) : (
          <MessageListContainer role="list" aria-label="Discussion messages">
            <MessageTree
              messages={messageTree}
              highlightedMessageId={selectedMessageId}
              onReply={handleReply}
              badgesByUser={badgesByUser}
              conversationId={conversationId}
              currentUserId={currentUser?.id}
              canModerate={canModerate}
              corpusId={corpusId}
              onMessageUpdated={handleMessageChange}
              onMessageDeleted={handleMessageChange}
            />
          </MessageListContainer>
        )}
      </ContentArea>

      {/* Bottom composer — switches between top-level and reply mode */}
      {!thread.isLocked && (
        <ReplyComposerArea>
          <ReplyComposerInner>
            <ReplyForm
              conversationId={conversationId}
              parentMessageId={replyingToMessageId || undefined}
              replyingToUsername={
                replyTargetMessage
                  ? getCreatorDisplay(replyTargetMessage.creator)
                  : undefined
              }
              parentMessageContent={replyTargetMessage?.content || undefined}
              onSuccess={() => {
                setReplyingToMessageId(null);
              }}
              onCancel={() => {
                setReplyingToMessageId(null);
              }}
              autoFocus={false}
              corpusId={corpusId}
            />
          </ReplyComposerInner>
        </ReplyComposerArea>
      )}
    </Container>
  );
}
