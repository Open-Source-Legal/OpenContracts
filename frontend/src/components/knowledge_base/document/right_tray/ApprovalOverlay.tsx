/**
 * ReopenApprovalButton
 *
 * Small button displayed in the chat header when the approval modal has been
 * dismissed but a tool call is still awaiting a decision. The approval overlay
 * itself lives in `components/chat/ApprovalDialog` (shared with CorpusChat).
 */

import React from "react";
import { Button } from "@os-legal/ui";
import { OS_LEGAL_COLORS } from "../../../../assets/configurations/osLegalStyles";
import type { ChatMessageProps } from "../../../widgets/chat/ChatMessage";
import type { PendingApproval } from "../../../chat/types";

export interface ReopenApprovalButtonProps {
  pendingApproval: PendingApproval | null;
  showApprovalModal: boolean;
  setShowApprovalModal: React.Dispatch<React.SetStateAction<boolean>>;
  combinedMessages: ChatMessageProps[];
  setPendingApproval: React.Dispatch<
    React.SetStateAction<PendingApproval | null>
  >;
}

export const ReopenApprovalButton: React.FC<ReopenApprovalButtonProps> = ({
  pendingApproval,
  showApprovalModal,
  setShowApprovalModal,
  combinedMessages,
  setPendingApproval,
}) => {
  if (!pendingApproval || showApprovalModal) return null;

  const messageStillAwaiting = combinedMessages.some(
    (msg) =>
      msg.messageId === pendingApproval.messageId &&
      msg.approvalStatus === "awaiting"
  );

  if (!messageStillAwaiting) {
    setPendingApproval(null);
    return null;
  }

  return (
    <Button
      size="sm"
      variant="secondary"
      onClick={() => setShowApprovalModal(true)}
      style={{
        background: OS_LEGAL_COLORS.folderIcon,
        color: "white",
        marginLeft: "1rem",
      }}
    >
      Pending Approval
    </Button>
  );
};
