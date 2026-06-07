import React, { useCallback } from "react";
import { useMutation } from "@apollo/client";
import styled from "styled-components";
import { AlertTriangle } from "lucide-react";
import {
  Button,
  Modal,
  ModalHeader as OcModalHeader,
  ModalBody,
  ModalFooter,
} from "@os-legal/ui";
import { toast } from "react-toastify";
import { OS_LEGAL_COLORS } from "../../../assets/configurations/osLegalStyles";
import {
  EMPTY_CORPUS,
  EmptyCorpusInput,
  EmptyCorpusOutput,
} from "../../../graphql/mutations";
import { selectedDocumentIds as selectedDocumentIdsReactiveVar } from "../../../graphql/cache";
import { evictCorpusDocumentCaches } from "../../../graphql/cacheEvictions";
import { ErrorMessage } from "../../widgets/feedback";

/**
 * EmptyCorpusModal - confirmation for the "empty everything" action.
 *
 * Moves EVERY document in the corpus to Trash and removes ALL folders in one
 * step. Documents stay recoverable from the Trash until it is emptied; the
 * folder tree is removed. This addresses "no easy way to empty everything"
 * and the orphaned-sub-folder problem (deleting folders one-by-one left
 * sub-folders stranded at the root).
 */

const StyledModalWrapper = styled.div`
  .oc-modal {
    max-width: 520px;
    width: 100%;
  }
`;

const WarningBox = styled.div`
  display: flex;
  gap: 12px;
  padding: 16px;
  background: ${OS_LEGAL_COLORS.dangerSurface};
  border: 1px solid ${OS_LEGAL_COLORS.dangerBorder};
  border-radius: 8px;
  margin-bottom: 16px;
  color: ${OS_LEGAL_COLORS.dangerText};
`;

const WarningContent = styled.div`
  flex: 1;

  h4 {
    margin: 0 0 8px 0;
    font-size: 16px;
    font-weight: 600;
  }

  p {
    margin: 0 0 8px 0;
    font-size: 14px;
    line-height: 1.5;
  }

  ul {
    margin: 8px 0 0 0;
    padding-left: 20px;
    font-size: 14px;

    li {
      margin-bottom: 4px;
    }
  }
`;

interface EmptyCorpusModalProps {
  open: boolean;
  onClose: () => void;
  corpusId: string;
}

export const EmptyCorpusModal: React.FC<EmptyCorpusModalProps> = ({
  open,
  onClose,
  corpusId,
}) => {
  const [emptyCorpus, { loading, error }] = useMutation<
    EmptyCorpusOutput,
    EmptyCorpusInput
  >(EMPTY_CORPUS, {
    // Refresh the document list, folder tree (sidebar counts), Select-All id
    // list, and trash view once everything has been moved to trash.
    update: (cache) => evictCorpusDocumentCaches(cache),
    onCompleted: (data) => {
      if (data.emptyCorpus.ok) {
        toast.success(data.emptyCorpus.message);
        selectedDocumentIdsReactiveVar([]);
        onClose();
      } else {
        toast.error(data.emptyCorpus.message || "Failed to empty corpus");
      }
    },
    onError: (err) => {
      toast.error(`Error emptying corpus: ${err.message}`);
    },
  });

  const handleConfirm = useCallback(() => {
    if (!corpusId) return;
    emptyCorpus({ variables: { corpusId } });
  }, [corpusId, emptyCorpus]);

  const handleClose = useCallback(() => {
    if (!loading) onClose();
  }, [loading, onClose]);

  // Eager unmount when closed (rather than relying solely on `<Modal open>` to
  // hide it): this tears down the subtree and the useMutation state so each open
  // starts from a clean slate, with no lingering loading/result from a prior run.
  if (!open) return null;

  return (
    <StyledModalWrapper>
      <Modal open={open} onClose={handleClose} size="sm">
        <OcModalHeader title="Empty Corpus" onClose={handleClose} />
        <ModalBody>
          <WarningBox>
            <AlertTriangle size={24} style={{ flexShrink: 0, marginTop: 2 }} />
            <WarningContent>
              <h4>Move everything to Trash?</h4>
              <p>
                This will move <strong>every document in this corpus</strong>{" "}
                (across all folders) to the Trash and remove{" "}
                <strong>all folders</strong>.
              </p>
              <ul>
                <li>
                  Documents are recoverable from the Trash until you empty it.
                </li>
                <li>The folder structure is removed and cannot be restored.</li>
              </ul>
            </WarningContent>
          </WarningBox>

          {error && (
            <ErrorMessage title="Error Emptying Corpus">
              {error.message}
            </ErrorMessage>
          )}
        </ModalBody>
        <ModalFooter>
          <Button variant="secondary" onClick={handleClose} disabled={loading}>
            Cancel
          </Button>
          <Button
            variant="danger"
            onClick={handleConfirm}
            loading={loading}
            disabled={loading}
          >
            Move Everything to Trash
          </Button>
        </ModalFooter>
      </Modal>
    </StyledModalWrapper>
  );
};
