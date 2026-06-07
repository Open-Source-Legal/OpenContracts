import React, { useCallback } from "react";
import { useAtomValue, useSetAtom } from "jotai";
import { useMutation } from "@apollo/client";
import styled from "styled-components";
import { X, AlertTriangle } from "lucide-react";
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
  showRemoveDocumentsModalAtom,
  removeDocumentsIdsAtom,
  closeRemoveDocumentsModalAtom,
  folderCorpusIdAtom,
} from "../../../atoms/folderAtoms";
import {
  REMOVE_DOCUMENTS_FROM_CORPUS,
  RemoveDocumentsFromCorpusInputs,
  RemoveDocumentsFromCorpusOutputs,
} from "../../../graphql/mutations";
import { selectedDocumentIds as selectedDocumentIdsReactiveVar } from "../../../graphql/cache";
import { evictCorpusDocumentCaches } from "../../../graphql/cacheEvictions";
import { ErrorMessage } from "../../widgets/feedback";

/**
 * RemoveDocumentsModal - Confirmation modal for bulk removing documents from corpus
 *
 * Features:
 * - Shows count of documents to be removed
 * - Requires explicit confirmation
 * - Clears selection after successful removal
 * - Shows loading and error states
 */

const StyledModalWrapper = styled.div`
  .oc-modal {
    max-width: 500px;
    width: 100%;
  }
`;

const CloseButton = styled.button`
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  padding: 0;
  background: none;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  color: ${OS_LEGAL_COLORS.danger};
  transition: all 0.15s ease;

  &:hover {
    background: ${OS_LEGAL_COLORS.dangerBorder};
    color: ${OS_LEGAL_COLORS.dangerText};
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

const WarningIcon = styled(AlertTriangle)`
  flex-shrink: 0;
  margin-top: 2px;
`;

const WarningContent = styled.div`
  flex: 1;

  h4 {
    margin: 0 0 8px 0;
    font-size: 16px;
    font-weight: 600;
  }

  p {
    margin: 0;
    font-size: 14px;
    line-height: 1.5;
  }
`;

const InfoBox = styled.div`
  padding: 12px;
  background: ${OS_LEGAL_COLORS.surfaceHover};
  border-radius: 6px;
  font-size: 14px;
  color: ${OS_LEGAL_COLORS.textTertiary};

  strong {
    color: ${OS_LEGAL_COLORS.textPrimary};
    font-weight: 600;
  }
`;

export const RemoveDocumentsModal: React.FC = () => {
  const showModal = useAtomValue(showRemoveDocumentsModalAtom);
  const documentIds = useAtomValue(removeDocumentsIdsAtom);
  const corpusId = useAtomValue(folderCorpusIdAtom);
  const closeModal = useSetAtom(closeRemoveDocumentsModalAtom);

  const [removeDocuments, { loading, error }] = useMutation<
    RemoveDocumentsFromCorpusOutputs,
    RemoveDocumentsFromCorpusInputs
  >(REMOVE_DOCUMENTS_FROM_CORPUS, {
    // Evict the document list, folder tree (sidebar doc counts), Select-All id
    // list, and trash view so all of them refetch with fresh data.
    update: (cache) => evictCorpusDocumentCaches(cache),
    onCompleted: (data) => {
      if (data.removeDocumentsFromCorpus.ok) {
        const count = documentIds.length;
        toast.success(
          `Successfully removed ${count} document${
            count !== 1 ? "s" : ""
          } from corpus`
        );
        // Clear selection after successful removal
        selectedDocumentIdsReactiveVar([]);
        closeModal();
      } else {
        toast.error(
          data.removeDocumentsFromCorpus.message ||
            "Failed to remove documents from corpus"
        );
      }
    },
    onError: (error) => {
      toast.error(`Error removing documents: ${error.message}`);
    },
  });

  const handleClose = useCallback(() => {
    if (!loading) {
      closeModal();
    }
  }, [closeModal, loading]);

  const handleConfirmRemove = useCallback(() => {
    if (!corpusId || documentIds.length === 0) return;

    removeDocuments({
      variables: {
        corpusId,
        documentIdsToRemove: documentIds,
      },
    });
  }, [corpusId, documentIds, removeDocuments]);

  if (!showModal || documentIds.length === 0) return null;

  const count = documentIds.length;

  return (
    <StyledModalWrapper>
      <Modal open={showModal} onClose={handleClose} size="sm">
        <OcModalHeader
          title="Remove Documents from Corpus"
          onClose={handleClose}
        />

        <ModalBody>
          <WarningBox>
            <WarningIcon size={24} />
            <WarningContent>
              <h4>Confirm Removal</h4>
              <p>
                You are about to remove{" "}
                <strong>
                  {count} document{count !== 1 ? "s" : ""}
                </strong>{" "}
                from this corpus. The documents will remain in your library but
                will no longer be associated with this corpus.
              </p>
            </WarningContent>
          </WarningBox>

          <InfoBox>
            <strong>Documents to remove:</strong> {count}
          </InfoBox>

          {error && (
            <ErrorMessage
              title="Error Removing Documents"
              style={{ marginTop: "16px" }}
            >
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
            onClick={handleConfirmRemove}
            loading={loading}
            disabled={loading}
          >
            Remove {count} Document{count !== 1 ? "s" : ""}
          </Button>
        </ModalFooter>
      </Modal>
    </StyledModalWrapper>
  );
};
