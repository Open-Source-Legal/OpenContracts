import React, { useState } from "react";
import styled from "styled-components";
import { Pin, Lock, Trash2, RotateCcw } from "lucide-react";
import { useMutation } from "@apollo/client";
import { color } from "../../theme/colors";
import {
  PIN_THREAD,
  UNPIN_THREAD,
  LOCK_THREAD,
  UNLOCK_THREAD,
  DELETE_THREAD,
  RESTORE_THREAD,
  PinThreadInput,
  PinThreadOutput,
  UnpinThreadInput,
  UnpinThreadOutput,
  LockThreadInput,
  LockThreadOutput,
  UnlockThreadInput,
  UnlockThreadOutput,
  DeleteThreadInput,
  DeleteThreadOutput,
  RestoreThreadInput,
  RestoreThreadOutput,
} from "../../graphql/mutations";
import { GET_CONVERSATIONS, GET_THREAD_DETAIL } from "../../graphql/queries";

const Container = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  background: ${({ theme }) => color.N2};
  border: 1px solid ${({ theme }) => color.N4};
  border-radius: 6px;
`;

const ModerationButton = styled.button<{
  $variant?: "danger" | "warning" | "primary";
}>`
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border: 1px solid;
  border-radius: 4px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;

  ${({ $variant, theme }) => {
    switch ($variant) {
      case "danger":
        return `
          background: ${color.R7}10;
          border-color: ${color.R7}40;
          color: ${color.R7};
          &:hover:not(:disabled) {
            background: ${color.R7}20;
            border-color: ${color.R7};
          }
        `;
      case "warning":
        return `
          background: ${color.Y6}10;
          border-color: ${color.Y6}40;
          color: ${color.Y6};
          &:hover:not(:disabled) {
            background: ${color.Y6}20;
            border-color: ${color.Y6};
          }
        `;
      default:
        return `
          background: ${color.B5}10;
          border-color: ${color.B5}40;
          color: ${color.B5};
          &:hover:not(:disabled) {
            background: ${color.B5}20;
            border-color: ${color.B5};
          }
        `;
    }
  }}

  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  svg {
    width: 14px;
    height: 14px;
  }
`;

const ConfirmDialog = styled.div`
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 16px;
`;

const ConfirmBox = styled.div`
  background: ${({ theme }) => color.N1};
  border-radius: 8px;
  padding: 24px;
  max-width: 400px;
  width: 100%;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.15);
`;

const ConfirmTitle = styled.h3`
  margin: 0 0 12px 0;
  font-size: 18px;
  font-weight: 600;
  color: ${({ theme }) => color.N10};
`;

const ConfirmMessage = styled.p`
  margin: 0 0 20px 0;
  font-size: 14px;
  color: ${({ theme }) => color.N7};
  line-height: 1.5;
`;

const ConfirmActions = styled.div`
  display: flex;
  gap: 8px;
  justify-content: flex-end;
`;

const ConfirmButton = styled.button<{ $primary?: boolean }>`
  padding: 8px 16px;
  border: none;
  border-radius: 4px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: opacity 0.15s ease;

  ${({ $primary, theme }) =>
    $primary
      ? `
    background: ${color.R7};
    color: white;
    &:hover:not(:disabled) {
      opacity: 0.9;
    }
  `
      : `
    background: ${color.N3};
    color: ${color.N10};
    &:hover:not(:disabled) {
      background: ${color.N2};
    }
  `}

  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
`;

const ErrorMessage = styled.div`
  padding: 8px 12px;
  background: ${({ theme }) => color.R7}15;
  color: ${({ theme }) => color.R7};
  font-size: 13px;
  border-radius: 4px;
  margin-top: 8px;
`;

export interface ModerationControlsProps {
  /** ID of the conversation/thread */
  conversationId: string;
  /** Current pinned state */
  isPinned: boolean;
  /** Current locked state */
  isLocked: boolean;
  /** Current deleted state */
  isDeleted: boolean;
  /** Corpus ID for refetching */
  corpusId?: string;
  /** Callback when moderation action succeeds */
  onSuccess?: () => void;
}

export function ModerationControls({
  conversationId,
  isPinned,
  isLocked,
  isDeleted,
  corpusId,
  onSuccess,
}: ModerationControlsProps) {
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refetchQueries = corpusId
    ? [
        {
          query: GET_CONVERSATIONS,
          variables: { corpusId, conversationType: "THREAD" },
        },
        {
          query: GET_THREAD_DETAIL,
          variables: { conversationId },
        },
      ]
    : [
        {
          query: GET_THREAD_DETAIL,
          variables: { conversationId },
        },
      ];

  const [pinThread, { loading: pinning }] = useMutation<
    PinThreadOutput,
    PinThreadInput
  >(PIN_THREAD, {
    refetchQueries,
    onCompleted: (data) => {
      if (data.pinThread.ok) {
        onSuccess?.();
      } else {
        setError(data.pinThread.message || "Failed to pin thread");
      }
    },
    onError: (err) => {
      setError("An error occurred while pinning the thread");
      console.error(err);
    },
  });

  const [unpinThread, { loading: unpinning }] = useMutation<
    UnpinThreadOutput,
    UnpinThreadInput
  >(UNPIN_THREAD, {
    refetchQueries,
    onCompleted: (data) => {
      if (data.unpinThread.ok) {
        onSuccess?.();
      } else {
        setError(data.unpinThread.message || "Failed to unpin thread");
      }
    },
    onError: (err) => {
      setError("An error occurred while unpinning the thread");
      console.error(err);
    },
  });

  const [lockThread, { loading: locking }] = useMutation<
    LockThreadOutput,
    LockThreadInput
  >(LOCK_THREAD, {
    refetchQueries,
    onCompleted: (data) => {
      if (data.lockThread.ok) {
        onSuccess?.();
      } else {
        setError(data.lockThread.message || "Failed to lock thread");
      }
    },
    onError: (err) => {
      setError("An error occurred while locking the thread");
      console.error(err);
    },
  });

  const [unlockThread, { loading: unlocking }] = useMutation<
    UnlockThreadOutput,
    UnlockThreadInput
  >(UNLOCK_THREAD, {
    refetchQueries,
    onCompleted: (data) => {
      if (data.unlockThread.ok) {
        onSuccess?.();
      } else {
        setError(data.unlockThread.message || "Failed to unlock thread");
      }
    },
    onError: (err) => {
      setError("An error occurred while unlocking the thread");
      console.error(err);
    },
  });

  const [deleteThread, { loading: deleting }] = useMutation<
    DeleteThreadOutput,
    DeleteThreadInput
  >(DELETE_THREAD, {
    refetchQueries,
    onCompleted: (data) => {
      if (data.deleteThread.ok) {
        setShowDeleteConfirm(false);
        onSuccess?.();
      } else {
        setError(data.deleteThread.message || "Failed to delete thread");
      }
    },
    onError: (err) => {
      setError("An error occurred while deleting the thread");
      console.error(err);
    },
  });

  const [restoreThread, { loading: restoring }] = useMutation<
    RestoreThreadOutput,
    RestoreThreadInput
  >(RESTORE_THREAD, {
    refetchQueries,
    onCompleted: (data) => {
      if (data.restoreThread.ok) {
        onSuccess?.();
      } else {
        setError(data.restoreThread.message || "Failed to restore thread");
      }
    },
    onError: (err) => {
      setError("An error occurred while restoring the thread");
      console.error(err);
    },
  });

  const loading =
    pinning || unpinning || locking || unlocking || deleting || restoring;

  const handlePinToggle = () => {
    setError(null);
    if (isPinned) {
      unpinThread({ variables: { conversationId } });
    } else {
      pinThread({ variables: { conversationId } });
    }
  };

  const handleLockToggle = () => {
    setError(null);
    if (isLocked) {
      unlockThread({ variables: { conversationId } });
    } else {
      lockThread({ variables: { conversationId } });
    }
  };

  const handleDeleteClick = () => {
    setError(null);
    setShowDeleteConfirm(true);
  };

  const handleDeleteConfirm = () => {
    deleteThread({ variables: { conversationId } });
  };

  const handleRestore = () => {
    setError(null);
    restoreThread({ variables: { conversationId } });
  };

  return (
    <>
      <Container>
        <ModerationButton
          onClick={handlePinToggle}
          disabled={loading || isDeleted}
          title={isPinned ? "Unpin thread" : "Pin thread"}
          aria-label={isPinned ? "Unpin thread" : "Pin thread"}
        >
          <Pin />
          {isPinned ? "Unpin" : "Pin"}
        </ModerationButton>

        <ModerationButton
          onClick={handleLockToggle}
          disabled={loading || isDeleted}
          $variant="warning"
          title={isLocked ? "Unlock thread" : "Lock thread"}
          aria-label={isLocked ? "Unlock thread" : "Lock thread"}
        >
          <Lock />
          {isLocked ? "Unlock" : "Lock"}
        </ModerationButton>

        {!isDeleted ? (
          <ModerationButton
            onClick={handleDeleteClick}
            disabled={loading}
            $variant="danger"
            title="Delete thread"
            aria-label="Delete thread"
          >
            <Trash2 />
            Delete
          </ModerationButton>
        ) : (
          <ModerationButton
            onClick={handleRestore}
            disabled={loading}
            title="Restore thread"
            aria-label="Restore thread"
          >
            <RotateCcw />
            Restore
          </ModerationButton>
        )}

        {error && <ErrorMessage>{error}</ErrorMessage>}
      </Container>

      {showDeleteConfirm && (
        <ConfirmDialog onClick={() => setShowDeleteConfirm(false)}>
          <ConfirmBox onClick={(e) => e.stopPropagation()}>
            <ConfirmTitle>Delete Thread?</ConfirmTitle>
            <ConfirmMessage>
              Are you sure you want to delete this thread? This is a soft delete
              and can be reversed by moderators.
            </ConfirmMessage>
            <ConfirmActions>
              <ConfirmButton
                onClick={() => setShowDeleteConfirm(false)}
                disabled={deleting}
              >
                Cancel
              </ConfirmButton>
              <ConfirmButton
                $primary
                onClick={handleDeleteConfirm}
                disabled={deleting}
              >
                {deleting ? "Deleting..." : "Delete Thread"}
              </ConfirmButton>
            </ConfirmActions>
          </ConfirmBox>
        </ConfirmDialog>
      )}
    </>
  );
}
