import React, { useState } from "react";
import { useMutation } from "@apollo/client";
import styled from "styled-components";
import { ChevronUp, ChevronDown } from "lucide-react";
import { color } from "../../theme/colors";
import {
  UPVOTE_MESSAGE,
  DOWNVOTE_MESSAGE,
  REMOVE_VOTE,
  UpvoteMessageInput,
  UpvoteMessageOutput,
  DownvoteMessageInput,
  DownvoteMessageOutput,
  RemoveVoteInput,
  RemoveVoteOutput,
} from "../../graphql/mutations";

const Container = styled.div`
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
`;

const VoteButton = styled.button<{
  $isActive?: boolean;
  $variant?: "up" | "down";
}>`
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: none;
  border-radius: 4px;
  background: ${({ $isActive, $variant, theme }) => {
    if ($isActive && $variant === "up") return theme.color.success + "20";
    if ($isActive && $variant === "down") return color.R7 + "20";
    return "transparent";
  }};
  color: ${({ $isActive, $variant, theme }) => {
    if ($isActive && $variant === "up") return theme.color.success;
    if ($isActive && $variant === "down") return color.R7;
    return color.N7;
  }};
  cursor: pointer;
  transition: all 0.15s ease;

  &:hover:not(:disabled) {
    background: ${({ $variant, theme }) => {
      if ($variant === "up") return theme.color.success + "15";
      if ($variant === "down") return color.R7 + "15";
      return color.N2;
    }};
    color: ${({ $variant, theme }) => {
      if ($variant === "up") return theme.color.success;
      if ($variant === "down") return color.R7;
      return color.N10;
    }};
  }

  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  svg {
    width: 20px;
    height: 20px;
  }
`;

const VoteCount = styled.div<{ $score: number }>`
  font-size: 14px;
  font-weight: 600;
  color: ${({ $score, theme }) => {
    if ($score > 0) return theme.color.success;
    if ($score < 0) return color.R7;
    return color.N7;
  }};
  padding: 2px 0;
  min-width: 24px;
  text-align: center;
`;

const ErrorMessage = styled.div`
  position: absolute;
  top: 100%;
  left: 50%;
  transform: translateX(-50%);
  margin-top: 4px;
  padding: 6px 10px;
  background: ${({ theme }) => color.R7};
  color: white;
  font-size: 12px;
  border-radius: 4px;
  white-space: nowrap;
  z-index: 10;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);

  &::before {
    content: "";
    position: absolute;
    bottom: 100%;
    left: 50%;
    transform: translateX(-50%);
    border: 4px solid transparent;
    border-bottom-color: ${({ theme }) => color.R7};
  }
`;

const Wrapper = styled.div`
  position: relative;
`;

export interface VoteButtonsProps {
  /** ID of the message to vote on */
  messageId: string;
  /** Current upvote count */
  upvoteCount: number;
  /** Current downvote count */
  downvoteCount: number;
  /** Current user's vote state ("UPVOTE", "DOWNVOTE", or null) */
  userVote?: string | null;
  /** ID of the message sender */
  senderId: string;
  /** ID of the current user */
  currentUserId?: string;
  /** Disable voting (e.g., message deleted) */
  disabled?: boolean;
  /** Optional callback when vote changes */
  onVoteChange?: (newScore: number) => void;
}

export function VoteButtons({
  messageId,
  upvoteCount,
  downvoteCount,
  userVote,
  senderId,
  currentUserId,
  disabled = false,
  onVoteChange,
}: VoteButtonsProps) {
  const [error, setError] = useState<string | null>(null);
  const [optimisticVote, setOptimisticVote] = useState<string | null>(null);

  // Calculate net score
  const score = upvoteCount - downvoteCount;

  // Determine if user owns this message
  const isOwnMessage = currentUserId && currentUserId === senderId;

  // Current vote state (optimistic or actual)
  const currentVote = optimisticVote !== null ? optimisticVote : userVote;

  const [upvoteMutation, { loading: upvoting }] = useMutation<
    UpvoteMessageOutput,
    UpvoteMessageInput
  >(UPVOTE_MESSAGE, {
    onCompleted: (data) => {
      if (data.upvoteMessage.ok) {
        setOptimisticVote(null);
        if (data.upvoteMessage.chatMessage) {
          const newScore =
            data.upvoteMessage.chatMessage.upvoteCount -
            data.upvoteMessage.chatMessage.downvoteCount;
          onVoteChange?.(newScore);
        }
      } else {
        setOptimisticVote(null);
        setError(data.upvoteMessage.message || "Failed to upvote");
        setTimeout(() => setError(null), 3000);
      }
    },
    onError: (err) => {
      console.error("Upvote error:", err);
      setOptimisticVote(null);
      setError("An error occurred. Please try again.");
      setTimeout(() => setError(null), 3000);
    },
  });

  const [downvoteMutation, { loading: downvoting }] = useMutation<
    DownvoteMessageOutput,
    DownvoteMessageInput
  >(DOWNVOTE_MESSAGE, {
    onCompleted: (data) => {
      if (data.downvoteMessage.ok) {
        setOptimisticVote(null);
        if (data.downvoteMessage.chatMessage) {
          const newScore =
            data.downvoteMessage.chatMessage.upvoteCount -
            data.downvoteMessage.chatMessage.downvoteCount;
          onVoteChange?.(newScore);
        }
      } else {
        setOptimisticVote(null);
        setError(data.downvoteMessage.message || "Failed to downvote");
        setTimeout(() => setError(null), 3000);
      }
    },
    onError: (err) => {
      console.error("Downvote error:", err);
      setOptimisticVote(null);
      setError("An error occurred. Please try again.");
      setTimeout(() => setError(null), 3000);
    },
  });

  const [removeVoteMutation, { loading: removing }] = useMutation<
    RemoveVoteOutput,
    RemoveVoteInput
  >(REMOVE_VOTE, {
    onCompleted: (data) => {
      if (data.removeVote.ok) {
        setOptimisticVote(null);
        if (data.removeVote.chatMessage) {
          const newScore =
            data.removeVote.chatMessage.upvoteCount -
            data.removeVote.chatMessage.downvoteCount;
          onVoteChange?.(newScore);
        }
      } else {
        setOptimisticVote(null);
        setError(data.removeVote.message || "Failed to remove vote");
        setTimeout(() => setError(null), 3000);
      }
    },
    onError: (err) => {
      console.error("Remove vote error:", err);
      setOptimisticVote(null);
      setError("An error occurred. Please try again.");
      setTimeout(() => setError(null), 3000);
    },
  });

  const loading = upvoting || downvoting || removing;

  const handleUpvote = async () => {
    if (isOwnMessage) {
      setError("You cannot vote on your own messages");
      setTimeout(() => setError(null), 3000);
      return;
    }

    setError(null);

    // If already upvoted, remove vote
    if (currentVote === "UPVOTE") {
      setOptimisticVote(null);
      await removeVoteMutation({ variables: { messageId } });
    } else {
      setOptimisticVote("UPVOTE");
      await upvoteMutation({ variables: { messageId } });
    }
  };

  const handleDownvote = async () => {
    if (isOwnMessage) {
      setError("You cannot vote on your own messages");
      setTimeout(() => setError(null), 3000);
      return;
    }

    setError(null);

    // If already downvoted, remove vote
    if (currentVote === "DOWNVOTE") {
      setOptimisticVote(null);
      await removeVoteMutation({ variables: { messageId } });
    } else {
      setOptimisticVote("DOWNVOTE");
      await downvoteMutation({ variables: { messageId } });
    }
  };

  // Calculate optimistic score
  let displayScore = score;
  if (optimisticVote === "UPVOTE" && userVote !== "UPVOTE") {
    displayScore += userVote === "DOWNVOTE" ? 2 : 1;
  } else if (optimisticVote === "DOWNVOTE" && userVote !== "DOWNVOTE") {
    displayScore -= userVote === "UPVOTE" ? 2 : 1;
  } else if (optimisticVote === null && userVote === "UPVOTE") {
    displayScore -= 1;
  } else if (optimisticVote === null && userVote === "DOWNVOTE") {
    displayScore += 1;
  }

  return (
    <Wrapper>
      <Container>
        <VoteButton
          $variant="up"
          $isActive={currentVote === "UPVOTE"}
          onClick={handleUpvote}
          disabled={disabled || loading}
          title={isOwnMessage ? "Cannot vote on own message" : "Upvote"}
          aria-label="Upvote"
        >
          <ChevronUp />
        </VoteButton>

        <VoteCount $score={displayScore}>{displayScore}</VoteCount>

        <VoteButton
          $variant="down"
          $isActive={currentVote === "DOWNVOTE"}
          onClick={handleDownvote}
          disabled={disabled || loading}
          title={isOwnMessage ? "Cannot vote on own message" : "Downvote"}
          aria-label="Downvote"
        >
          <ChevronDown />
        </VoteButton>
      </Container>

      {error && <ErrorMessage>{error}</ErrorMessage>}
    </Wrapper>
  );
}
