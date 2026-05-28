import React from "react";
import { useMutation } from "@apollo/client";
import {
  Button,
  Modal,
  ModalHeader,
  ModalBody,
  ModalFooter,
} from "@os-legal/ui";
import styled from "styled-components";
import { toast } from "react-toastify";
import { AlertTriangle, Layers } from "lucide-react";

import {
  START_CORPUS_ACTION_BATCH_RUN,
  StartCorpusActionBatchRunInput,
  StartCorpusActionBatchRunOutput,
} from "../../graphql/mutations";
import { OS_LEGAL_COLORS } from "../../assets/configurations/osLegalStyles";

const StyledModalWrapper = styled.div`
  .oc-modal {
    max-width: 520px;
    width: 100%;
  }
`;

const InfoLine = styled.p`
  margin: 0.5rem 0;
  font-size: 0.875rem;
  line-height: 1.5;
`;

const WarningRow = styled.div`
  display: flex;
  gap: 0.5rem;
  align-items: flex-start;
  padding: 0.75rem;
  background: ${OS_LEGAL_COLORS.warningSurface};
  border: 1px solid ${OS_LEGAL_COLORS.warningBorder};
  border-radius: 6px;
  color: ${OS_LEGAL_COLORS.warningText};
  font-size: 0.8125rem;
  margin-top: 0.75rem;
`;

interface BatchRunCorpusActionModalProps {
  open: boolean;
  actionId: string;
  actionName: string;
  onClose: () => void;
  onQueued?: () => void;
}

/**
 * Confirmation modal for batch-running an agent-based corpus action across
 * every eligible document in the corpus. Eligible = active doc with no
 * queued / running / completed execution for this action; failed executions
 * are intentionally re-queued so the button doubles as a retry path.
 *
 * Counts are reported by the server in the mutation response — we do not
 * pre-fetch a preview, since the eligible-doc computation is exactly what
 * the mutation does, and the response surfaces the numbers anyway.
 */
export const BatchRunCorpusActionModal: React.FC<
  BatchRunCorpusActionModalProps
> = ({ open, actionId, actionName, onClose, onQueued }) => {
  const [startBatchRun, { loading: running }] = useMutation<
    StartCorpusActionBatchRunOutput,
    StartCorpusActionBatchRunInput
  >(START_CORPUS_ACTION_BATCH_RUN);

  const handleRun = async () => {
    try {
      const { data } = await startBatchRun({
        variables: { corpusActionId: actionId },
      });
      const payload = data?.startCorpusActionBatchRun;
      if (payload?.ok) {
        toast.success(payload.message);
        onQueued?.();
        onClose();
      } else {
        toast.error(payload?.message ?? "Failed to queue batch run.");
      }
    } catch {
      toast.error("Failed to queue batch run.");
    }
  };

  return (
    <StyledModalWrapper>
      <Modal open={open} onClose={onClose} size="sm">
        <ModalHeader
          title={
            <span style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <Layers size={18} />
              Run on every document
            </span>
          }
          onClose={onClose}
        />
        <ModalBody>
          <InfoLine>
            <strong>{actionName}</strong> will run against every active
            document in this corpus that hasn&rsquo;t already been processed
            by this action.
          </InfoLine>
          <InfoLine>
            Failed runs will be retried. Documents that already have a queued,
            running, or completed execution for this action are skipped &mdash;
            press this button again later to pick up new documents as they
            arrive.
          </InfoLine>
          <WarningRow>
            <AlertTriangle size={16} style={{ flexShrink: 0, marginTop: 2 }} />
            <span>
              This dispatches one agent run per document. Larger corpuses
              may take several minutes; watch the Action Execution History
              section for progress.
            </span>
          </WarningRow>
        </ModalBody>
        <ModalFooter>
          <Button variant="secondary" onClick={onClose} disabled={running}>
            Cancel
          </Button>
          <Button
            variant="primary"
            loading={running}
            disabled={running}
            onClick={handleRun}
          >
            Run on all documents
          </Button>
        </ModalFooter>
      </Modal>
    </StyledModalWrapper>
  );
};
