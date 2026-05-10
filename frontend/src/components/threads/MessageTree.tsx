import React, { useCallback } from "react";
import { MessageNode } from "./utils";
import { MessageItem } from "./MessageItem";
import { UserBadgeType } from "../../types/graphql-api";
import { PermissionTypes } from "../types";
import { getCreatorDisplay } from "../../utils/userDisplay";

/**
 * Props for the MessageTree component.
 */
interface MessageTreeProps {
  messages: MessageNode[];
  highlightedMessageId?: string | null;
  onReply?: (messageId: string) => void;
  badgesByUser?: Map<string, UserBadgeType[]>;
  conversationId?: string;
  /** Current user ID for permission checking */
  currentUserId?: string;
  /** Whether current user can moderate this thread */
  canModerate?: boolean;
  /** Corpus ID for mention context in edit modal */
  corpusId?: string;
  /** Callback after successful message update */
  onMessageUpdated?: () => void;
  /** Callback after successful message deletion */
  onMessageDeleted?: () => void;
  /** Parent message author for "Replying to" display (for nested messages) */
  parentAuthor?: string;
}

/**
 * Recursive component for rendering hierarchical message tree.
 * Handles nested replies with proper indentation.
 * Memoized to prevent unnecessary re-renders when sibling threads update.
 */
export const MessageTree = React.memo(function MessageTree({
  messages,
  highlightedMessageId,
  onReply,
  badgesByUser = new Map(),
  conversationId,
  currentUserId,
  canModerate = false,
  corpusId,
  onMessageUpdated,
  onMessageDeleted,
  parentAuthor,
}: MessageTreeProps) {
  /**
   * Determines if a user can edit/delete a message.
   * Avoids N+1 queries by using pre-fetched myPermissions from the message object.
   *
   * A user can edit/delete a message if:
   * 1. They are the message creator (have CRUD permissions), OR
   * 2. They are a moderator of the thread (corpus/document owner)
   */
  const getMessagePermissions = useCallback(
    (message: MessageNode) => {
      // Moderators can always edit/delete
      if (canModerate) {
        return { canEdit: true, canDelete: true };
      }

      // Check if user is the message creator
      const isCreator = currentUserId && message.creator?.id === currentUserId;

      // Check if user has CRUD permissions from myPermissions
      // Cast to string to handle both enum values and raw Django permission strings
      const hasCrudPermission = message.myPermissions?.some(
        (perm) =>
          perm === PermissionTypes.CAN_UPDATE ||
          (perm as string) === "update_chatmessage" ||
          (perm as string) === "crud_chatmessage"
      );

      const hasDeletePermission = message.myPermissions?.some(
        (perm) =>
          perm === PermissionTypes.CAN_REMOVE ||
          (perm as string) === "delete_chatmessage" ||
          (perm as string) === "remove_chatmessage" ||
          (perm as string) === "crud_chatmessage"
      );

      return {
        canEdit: isCreator || hasCrudPermission || false,
        canDelete: isCreator || hasDeletePermission || false,
      };
    },
    [canModerate, currentUserId]
  );

  if (!messages || messages.length === 0) {
    return null;
  }

  return (
    <>
      {messages.map((message) => {
        // Get badges for this message's creator
        const userBadges = badgesByUser.get(message.creator.id) || [];
        // Compute permissions for this message
        const { canEdit, canDelete } = getMessagePermissions(message);

        return (
          <React.Fragment key={message.id}>
            {/* Render current message */}
            <MessageItem
              message={message}
              isHighlighted={message.id === highlightedMessageId}
              onReply={onReply}
              userBadges={userBadges}
              canEdit={canEdit}
              canDelete={canDelete}
              corpusId={corpusId}
              conversationId={conversationId}
              onMessageUpdated={onMessageUpdated}
              onMessageDeleted={onMessageDeleted}
              currentUserId={currentUserId}
              parentAuthor={parentAuthor}
            />

            {/* Recursively render children */}
            {message.children && message.children.length > 0 && (
              <MessageTree
                messages={message.children}
                highlightedMessageId={highlightedMessageId}
                onReply={onReply}
                badgesByUser={badgesByUser}
                conversationId={conversationId}
                currentUserId={currentUserId}
                canModerate={canModerate}
                corpusId={corpusId}
                onMessageUpdated={onMessageUpdated}
                onMessageDeleted={onMessageDeleted}
                parentAuthor={getCreatorDisplay(message.creator)}
              />
            )}
          </React.Fragment>
        );
      })}
    </>
  );
});
