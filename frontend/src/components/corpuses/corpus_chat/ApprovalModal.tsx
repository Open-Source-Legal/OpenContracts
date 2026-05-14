import React from "react";
import { AnimatePresence, motion } from "framer-motion";
import { AlertCircle, CheckCircle, X } from "lucide-react";
import { Button } from "@os-legal/ui";
import { OS_LEGAL_COLORS } from "../../../assets/configurations/osLegalStyles";
import type { PendingApproval } from "../../chat/types";
import { RequestingAgentAttribution } from "../../chat/RequestingAgentAttribution";

// `PendingApproval` is re-exported for backwards compatibility with the
// long-standing import path; new code should import from
// `components/chat/types`.
export type { PendingApproval };

interface ApprovalModalProps {
  /** The pending approval data (tool call info). Null if no approval is pending. */
  pendingApproval: PendingApproval | null;
  /** Whether the modal overlay should be visible. */
  show: boolean;
  /** Callback to hide the modal (e.g. clicking the X button). */
  onHide: () => void;
  /** Callback when the user approves or rejects the tool call. */
  onDecision: (approved: boolean) => void;
}

/**
 * ApprovalModal renders a centered overlay asking the user to approve or reject
 * an agent tool call. Mirrors the approval overlay previously inlined in CorpusChat.
 */
export const ApprovalModal: React.FC<ApprovalModalProps> = ({
  pendingApproval,
  show,
  onHide,
  onDecision,
}) => {
  if (!pendingApproval || !show) return null;

  return (
    <AnimatePresence>
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
            <AlertCircle
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
              }}
              onClick={onHide}
            >
              <X size={20} />
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
                <RequestingAgentAttribution
                  requestingAgent={pendingApproval.requestingAgent}
                  toolName={pendingApproval.toolCall.name}
                />
              ) : (
                <div style={{ fontWeight: 600, marginBottom: "0.5rem" }}>
                  Tool: {pendingApproval.toolCall.name}
                </div>
              )}
              {pendingApproval.toolCall.arguments &&
                Object.keys(pendingApproval.toolCall.arguments).length > 0 && (
                  <div>
                    <div style={{ fontWeight: 600, marginBottom: "0.25rem" }}>
                      Arguments:
                    </div>
                    <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>
                      {JSON.stringify(
                        pendingApproval.toolCall.arguments,
                        null,
                        2
                      )}
                    </pre>
                  </div>
                )}
            </div>
          </div>

          <div
            style={{
              display: "flex",
              gap: "1rem",
              justifyContent: "flex-end",
            }}
          >
            <Button
              variant="danger"
              size="md"
              onClick={() => onDecision(false)}
              leftIcon={<X size={16} />}
            >
              Reject
            </Button>
            <Button
              variant="primary"
              size="md"
              onClick={() => onDecision(true)}
              leftIcon={<CheckCircle size={16} />}
            >
              Approve
            </Button>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
};
