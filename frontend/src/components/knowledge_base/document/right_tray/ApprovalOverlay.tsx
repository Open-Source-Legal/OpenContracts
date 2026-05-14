/**
 * ApprovalOverlay & ReopenApprovalButton
 *
 * Modal overlay asking the user to approve or reject a pending tool call,
 * plus a small button to reopen the modal after it has been dismissed.
 */

import React from "react";
import { motion } from "framer-motion";
import { AlertTriangle, CheckCircle, XCircle } from "lucide-react";
import styled from "styled-components";
import { Button } from "@os-legal/ui";
import { OS_LEGAL_COLORS } from "../../../../assets/configurations/osLegalStyles";
import type { ChatMessageProps } from "../../../widgets/chat/ChatMessage";

/** Shape of the pending approval state passed from ChatTray. */
export interface PendingApproval {
  messageId: string;
  toolCall: {
    name: string;
    arguments: any;
    tool_call_id?: string;
  };
  /**
   * Rich-mention agent delegation (Task 14): set when the approval was
   * raised inside a sub-agent's tool call. The modal surfaces an
   * ``@<slug>`` attribution chip so the user understands which agent is
   * asking, not just which tool is being invoked.
   */
  requestingAgent?: {
    id: string;
    slug: string;
    name: string;
  } | null;
}

/**
 * Attribution chip surfaced in the approval modal when ``requestingAgent``
 * is populated. Palette intentionally mirrors the bubble-header chip in
 * ``ChatMessage.styles.ts`` and the inline ``@agent`` chip in
 * ``MarkdownMessageRenderer`` so users see a consistent "agent identity"
 * cue across attribution surfaces.
 */
const AgentChip = styled.span`
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.125rem 0.5rem;
  border-radius: 0.625rem;
  font-size: 0.8125rem;
  font-weight: 500;
  line-height: 1.2;
  background: linear-gradient(135deg, #8b5cf615 0%, #6366f115 100%);
  border: 1px solid #8b5cf660;
  color: #7c3aed;
  letter-spacing: -0.01em;
  white-space: nowrap;

  & > [aria-hidden="true"] {
    opacity: 0.75;
    font-weight: 600;
  }
`;

const RequestingAgentLine = styled.div`
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.4rem;
  margin-bottom: 0.5rem;
  font-weight: 600;
`;

/* ------------------------------------------------------------------ */
/* ApprovalOverlay                                                    */
/* ------------------------------------------------------------------ */

export interface ApprovalOverlayProps {
  pendingApproval: PendingApproval | null;
  showApprovalModal: boolean;
  setShowApprovalModal: React.Dispatch<React.SetStateAction<boolean>>;
  sendApprovalDecision: (approved: boolean) => void;
}

/**
 * Full-screen overlay presenting tool-call details with Approve / Reject buttons.
 * Returns `null` when there is no pending approval or the modal has been dismissed.
 */
export const ApprovalOverlay: React.FC<ApprovalOverlayProps> = ({
  pendingApproval,
  showApprovalModal,
  setShowApprovalModal,
  sendApprovalDecision,
}) => {
  if (!pendingApproval || !showApprovalModal) return null;

  return (
    <motion.div
      style={{
        position: "absolute",
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: "rgba(0, 0, 0, 0.5)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
        padding: "1rem",
      }}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
    >
      <motion.div
        style={{
          backgroundColor: "white",
          borderRadius: "12px",
          padding: "2rem",
          maxWidth: "500px",
          width: "100%",
          boxShadow:
            "0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)",
        }}
        initial={{ scale: 0.9, y: 20 }}
        animate={{ scale: 1, y: 0 }}
        exit={{ scale: 0.9, y: 20 }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "0.75rem",
            marginBottom: "1.5rem",
          }}
        >
          <AlertTriangle
            size={24}
            style={{ color: OS_LEGAL_COLORS.folderIcon }}
          />
          <h3 style={{ margin: 0, fontSize: "1.25rem", fontWeight: 600 }}>
            Tool Approval Required
          </h3>
          <button
            style={{
              marginLeft: "auto",
              background: "transparent",
              border: "none",
              cursor: "pointer",
              fontSize: "1.25rem",
              color: "#6b7280",
              padding: "0.25rem",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
            onClick={() => setShowApprovalModal(false)}
            aria-label="Close approval modal"
          >
            {"\u2715"}
          </button>
        </div>

        <div style={{ marginBottom: "1.5rem" }}>
          <p
            style={{
              margin: "0 0 1rem 0",
              color: OS_LEGAL_COLORS.textTertiary,
            }}
          >
            The assistant wants to execute the following tool:
          </p>
          <div
            style={{
              backgroundColor: OS_LEGAL_COLORS.surfaceLight,
              padding: "1rem",
              borderRadius: "8px",
              fontFamily: "monospace",
              fontSize: "0.875rem",
            }}
          >
            {pendingApproval.requestingAgent ? (
              <RequestingAgentLine data-testid="approval-requesting-agent">
                <AgentChip
                  role="note"
                  aria-label={`Requested by agent ${pendingApproval.requestingAgent.name}`}
                  title={`Requested by agent ${pendingApproval.requestingAgent.name}`}
                >
                  <span aria-hidden="true">@</span>
                  {pendingApproval.requestingAgent.slug}
                </AgentChip>
                <span>is asking to run</span>
                <span>{pendingApproval.toolCall.name}</span>
              </RequestingAgentLine>
            ) : (
              <div style={{ fontWeight: 600, marginBottom: "0.5rem" }}>
                Tool: {pendingApproval.toolCall.name}
              </div>
            )}
            {Object.keys(pendingApproval.toolCall.arguments).length > 0 && (
              <div>
                <div style={{ fontWeight: 600, marginBottom: "0.25rem" }}>
                  Arguments:
                </div>
                <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>
                  {JSON.stringify(pendingApproval.toolCall.arguments, null, 2)}
                </pre>
              </div>
            )}
          </div>
        </div>

        <div
          style={{ display: "flex", gap: "1rem", justifyContent: "flex-end" }}
        >
          <Button
            size="md"
            variant="danger"
            leftIcon={<XCircle size={16} />}
            onClick={() => sendApprovalDecision(false)}
          >
            Reject
          </Button>
          <Button
            size="md"
            variant="primary"
            leftIcon={<CheckCircle size={16} />}
            onClick={() => sendApprovalDecision(true)}
          >
            Approve
          </Button>
        </div>
      </motion.div>
    </motion.div>
  );
};

/* ------------------------------------------------------------------ */
/* ReopenApprovalButton                                               */
/* ------------------------------------------------------------------ */

export interface ReopenApprovalButtonProps {
  pendingApproval: PendingApproval | null;
  showApprovalModal: boolean;
  setShowApprovalModal: React.Dispatch<React.SetStateAction<boolean>>;
  combinedMessages: ChatMessageProps[];
  setPendingApproval: React.Dispatch<
    React.SetStateAction<PendingApproval | null>
  >;
}

/**
 * Small button displayed in the chat header when the approval modal has been
 * dismissed but a tool call is still awaiting a decision.
 */
export const ReopenApprovalButton: React.FC<ReopenApprovalButtonProps> = ({
  pendingApproval,
  showApprovalModal,
  setShowApprovalModal,
  combinedMessages,
  setPendingApproval,
}) => {
  if (!pendingApproval || showApprovalModal) return null;

  // Check if the message is actually still awaiting approval
  const messageStillAwaiting = combinedMessages.some(
    (msg) =>
      msg.messageId === pendingApproval.messageId &&
      msg.approvalStatus === "awaiting"
  );

  if (!messageStillAwaiting) {
    // Clear pendingApproval if the message is no longer awaiting
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
