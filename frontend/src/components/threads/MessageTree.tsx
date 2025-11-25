import React from "react";
import { MessageNode } from "./utils";
import { MessageItem } from "./MessageItem";
import { ReplyForm } from "./ReplyForm";
import { UserBadgeType } from "../../types/graphql-api";

interface MessageTreeProps {
  messages: MessageNode[];
  highlightedMessageId?: string | null;
  onReply?: (messageId: string) => void;
  badgesByUser?: Map<string, UserBadgeType[]>;
  conversationId?: string;
  replyingToMessageId?: string | null;
  onCancelReply?: () => void;
}

/**
 * Recursive component for rendering hierarchical message tree
 * Handles nested replies with proper indentation
 */
export function MessageTree({
  messages,
  highlightedMessageId,
  onReply,
  badgesByUser = new Map(),
  conversationId,
  replyingToMessageId,
  onCancelReply,
}: MessageTreeProps) {
  if (!messages || messages.length === 0) {
    return null;
  }

  return (
    <>
      {messages.map((message) => {
        // Get badges for this message's creator
        const userBadges = badgesByUser.get(message.creator.id) || [];
        const isReplyingToThisMessage = replyingToMessageId === message.id;

        return (
          <React.Fragment key={message.id}>
            {/* Render current message */}
            <MessageItem
              message={message}
              isHighlighted={message.id === highlightedMessageId}
              onReply={onReply}
              userBadges={userBadges}
            />

            {/* Render reply form if replying to this message */}
            {isReplyingToThisMessage && conversationId && onCancelReply && (
              <div
                style={{
                  marginLeft: `${Math.min(message.depth * 24 + 24, 264)}px`,
                  marginBottom: "12px",
                }}
              >
                <ReplyForm
                  conversationId={conversationId}
                  parentMessageId={message.id}
                  replyingToUsername={
                    message.creator?.username || message.creator?.email
                  }
                  parentMessageContent={message.content || undefined}
                  onSuccess={() => {
                    onCancelReply();
                  }}
                  onCancel={onCancelReply}
                  autoFocus
                />
              </div>
            )}

            {/* Recursively render children */}
            {message.children && message.children.length > 0 && (
              <MessageTree
                messages={message.children}
                highlightedMessageId={highlightedMessageId}
                onReply={onReply}
                badgesByUser={badgesByUser}
                conversationId={conversationId}
                replyingToMessageId={replyingToMessageId}
                onCancelReply={onCancelReply}
              />
            )}
          </React.Fragment>
        );
      })}
    </>
  );
}
