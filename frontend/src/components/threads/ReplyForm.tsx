import React, { useState } from "react";
import { useMutation } from "@apollo/client";
import styled from "styled-components";
import { X, Quote } from "lucide-react";
import {
  CREATE_THREAD_MESSAGE,
  REPLY_TO_MESSAGE,
  CreateThreadMessageInput,
  CreateThreadMessageOutput,
  ReplyToMessageInput,
  ReplyToMessageOutput,
} from "../../graphql/mutations";
import { GET_THREAD_DETAIL } from "../../graphql/queries";
import { MessageComposer } from "./MessageComposer";
import { color } from "../../theme/colors";
import { spacing } from "../../theme/spacing";

const Container = styled.div`
  border: 1px solid ${({ theme }) => color.N4};
  border-radius: 8px;
  background: ${({ theme }) => color.N2};
  padding: 12px;
`;

const Header = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
`;

const ReplyingTo = styled.div`
  font-size: 13px;
  color: ${({ theme }) => color.N7};

  strong {
    color: ${({ theme }) => color.N10};
    font-weight: 500;
  }
`;

const CancelButton = styled.button`
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: ${({ theme }) => color.N7};
  font-size: 13px;
  cursor: pointer;
  transition: background 0.15s ease;

  &:hover {
    background: ${({ theme }) => color.N3};
  }

  svg {
    width: 14px;
    height: 14px;
  }
`;

const ErrorMessage = styled.div`
  padding: 8px 12px;
  margin-bottom: 12px;
  background: ${({ theme }) => color.R7}15;
  border: 1px solid ${({ theme }) => color.R7}40;
  border-radius: 6px;
  color: ${({ theme }) => color.R7};
  font-size: 13px;
`;

const QuoteButton = styled.button`
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  border: 1px solid ${({ theme }) => color.N4};
  border-radius: 4px;
  background: ${({ theme }) => color.N1};
  color: ${({ theme }) => color.N7};
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s ease;
  margin-left: auto;

  &:hover {
    background: ${({ theme }) => color.N2};
    border-color: ${({ theme }) => color.B5};
    color: ${({ theme }) => color.B7};
  }

  svg {
    width: 14px;
    height: 14px;
  }
`;

const QuotedMessage = styled.div`
  padding: ${spacing.sm};
  margin-bottom: ${spacing.sm};
  border-left: 3px solid ${({ theme }) => color.B5};
  background: ${({ theme }) => color.N2};
  border-radius: 4px;
  font-size: 13px;
  color: ${({ theme }) => color.N7};
  font-style: italic;

  &::before {
    content: "Quoting:";
    display: block;
    font-weight: 600;
    font-style: normal;
    margin-bottom: 4px;
    color: ${({ theme }) => color.N10};
  }
`;

export interface ReplyFormProps {
  /** ID of the conversation (required for top-level messages) */
  conversationId?: string;
  /** ID of the parent message (for nested replies) */
  parentMessageId?: string;
  /** Username of the person being replied to */
  replyingToUsername?: string;
  /** Parent message content to quote */
  parentMessageContent?: string;
  /** Called when reply is submitted successfully */
  onSuccess?: () => void;
  /** Called when reply is cancelled */
  onCancel: () => void;
  /** Auto-focus on mount */
  autoFocus?: boolean;
  /** Initial content (for testing) */
  initialContent?: string;
}

export function ReplyForm({
  conversationId,
  parentMessageId,
  replyingToUsername,
  parentMessageContent,
  onSuccess,
  onCancel,
  autoFocus = true,
  initialContent,
}: ReplyFormProps) {
  const [error, setError] = useState("");
  const [showQuote, setShowQuote] = useState(false);

  // Determine which mutation to use
  const isTopLevel = !parentMessageId && conversationId;
  const isNestedReply = !!parentMessageId;

  // Top-level message mutation
  const [createMessage, { loading: createLoading }] = useMutation<
    CreateThreadMessageOutput,
    CreateThreadMessageInput
  >(CREATE_THREAD_MESSAGE, {
    refetchQueries: conversationId
      ? [
          {
            query: GET_THREAD_DETAIL,
            variables: { conversationId },
          },
        ]
      : [],
    onCompleted: (data) => {
      if (data.createThreadMessage.ok) {
        onSuccess?.();
      } else {
        setError(
          data.createThreadMessage.message ||
            "Failed to post message. Please try again."
        );
      }
    },
    onError: (err) => {
      console.error("Failed to create message:", err);
      setError("An unexpected error occurred. Please try again.");
    },
  });

  // Nested reply mutation
  const [replyToMessage, { loading: replyLoading }] = useMutation<
    ReplyToMessageOutput,
    ReplyToMessageInput
  >(REPLY_TO_MESSAGE, {
    refetchQueries:
      conversationId && parentMessageId
        ? [
            {
              query: GET_THREAD_DETAIL,
              variables: { conversationId },
            },
          ]
        : [],
    onCompleted: (data) => {
      if (data.replyToMessage.ok) {
        onSuccess?.();
      } else {
        setError(
          data.replyToMessage.message ||
            "Failed to post reply. Please try again."
        );
      }
    },
    onError: (err) => {
      console.error("Failed to create reply:", err);
      setError("An unexpected error occurred. Please try again.");
    },
  });

  const loading = createLoading || replyLoading;

  const handleSubmit = async (content: string) => {
    setError("");

    if (!content.trim()) {
      setError("Please write a message.");
      return;
    }

    try {
      if (isTopLevel && conversationId) {
        await createMessage({
          variables: {
            conversationId,
            content,
          },
        });
      } else if (isNestedReply && parentMessageId) {
        await replyToMessage({
          variables: {
            parentMessageId,
            content,
          },
        });
      } else {
        setError("Invalid reply configuration.");
      }
    } catch (err) {
      // Error already handled in mutation callbacks
    }
  };

  const handleToggleQuote = () => {
    setShowQuote(!showQuote);
  };

  // Extract plain text from HTML content for quote
  const getPlainTextFromHTML = (html: string) => {
    const div = document.createElement("div");
    div.innerHTML = html;
    return div.textContent || div.innerText || "";
  };

  const quotedText = parentMessageContent
    ? getPlainTextFromHTML(parentMessageContent)
    : "";

  return (
    <Container>
      {replyingToUsername && (
        <Header>
          <ReplyingTo>
            Replying to <strong>@{replyingToUsername}</strong>
          </ReplyingTo>
          <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
            {parentMessageContent && (
              <QuoteButton
                onClick={handleToggleQuote}
                title="Quote parent message"
              >
                <Quote />
                {showQuote ? "Hide Quote" : "Quote"}
              </QuoteButton>
            )}
            <CancelButton onClick={onCancel} title="Cancel">
              <X />
              Cancel
            </CancelButton>
          </div>
        </Header>
      )}

      {error && <ErrorMessage>{error}</ErrorMessage>}

      {showQuote && quotedText && (
        <QuotedMessage>
          {quotedText.length > 200
            ? quotedText.substring(0, 200) + "..."
            : quotedText}
        </QuotedMessage>
      )}

      <MessageComposer
        placeholder={
          replyingToUsername
            ? `Reply to @${replyingToUsername}...`
            : "Write your message..."
        }
        onSubmit={handleSubmit}
        disabled={loading}
        error={error}
        autoFocus={autoFocus}
        maxLength={10000}
        initialContent={initialContent}
      />
    </Container>
  );
}
