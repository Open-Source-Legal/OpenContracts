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
import {
  showDeleteFolderModalAtom,
  activeFolderModalIdAtom,
  folderListAtom,
  folderMapAtom,
  selectedFolderIdAtom,
  closeAllFolderModalsAtom,
  folderCorpusIdAtom,
} from "../../../atoms/folderAtoms";
import {
  DELETE_CORPUS_FOLDER,
  DeleteCorpusFolderInputs,
  DeleteCorpusFolderOutputs,
} from "../../../graphql/queries/folders";
import { evictCorpusDocumentCaches } from "../../../graphql/cacheEvictions";
import { ErrorMessage } from "../../widgets/feedback";
import { OS_LEGAL_COLORS } from "../../../assets/configurations/osLegalStyles";

/**
 * DeleteFolderModal - Confirmation modal for deleting folders
 *
 * Features:
 * - Shows warning about subfolder and document counts
 * - Warns that the sub-tree is removed and its documents move to Trash
 * - Requires explicit confirmation
 * - Clears selection if deleted folder was selected
 * - Cache eviction drives the refetch (no optimistic local-state edit)
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

const FolderInfo = styled.div`
  padding: 12px;
  background: ${OS_LEGAL_COLORS.surfaceHover};
  border-radius: 6px;
  margin-bottom: 16px;
  font-size: 14px;
  color: ${OS_LEGAL_COLORS.textTertiary};

  strong {
    color: ${OS_LEGAL_COLORS.textPrimary};
    font-weight: 600;
  }
`;

export const DeleteFolderModal: React.FC = () => {
  const showModal = useAtomValue(showDeleteFolderModalAtom);
  const folderId = useAtomValue(activeFolderModalIdAtom);
  const folderMap = useAtomValue(folderMapAtom);
  const folderList = useAtomValue(folderListAtom);
  const selectedFolderId = useAtomValue(selectedFolderIdAtom);
  const corpusId = useAtomValue(folderCorpusIdAtom);
  const setSelectedFolderId = useSetAtom(selectedFolderIdAtom);
  const closeAllModals = useSetAtom(closeAllFolderModalsAtom);

  const folder = folderId ? folderMap.get(folderId) : null;

  const [deleteFolder, { loading, error }] = useMutation<
    DeleteCorpusFolderOutputs,
    DeleteCorpusFolderInputs
  >(DELETE_CORPUS_FOLDER, {
    // Deleting a folder now cascades: the whole sub-tree is removed and its
    // documents move to Trash. Evict the document list, folder tree (sidebar
    // counts), Select-All id list, and trash view so all refetch with fresh
    // data. Replaces the old single GET_CORPUS_FOLDERS refetch, which left the
    // document grid and trash stale.
    update: (cache) => evictCorpusDocumentCaches(cache),
    onCompleted: () => {
      // Deleting a folder now cascade-removes its entire sub-tree, so a local
      // ``folderList.filter(id !== folder.id)`` would only drop the top folder
      // and leave its (also-deleted) child folders lingering in the sidebar
      // until the refetch lands. Drop the optimistic local-state edit entirely
      // and let the ``corpusFolders`` cache eviction above re-drive the sidebar
      // from fresh server data.
      if (folder && selectedFolderId === folder.id) {
        // The selected folder was just deleted — clear the selection so we
        // don't keep pointing at a folder that no longer exists.
        setSelectedFolderId(null);
      }

      // Close modal
      handleClose();
    },
  });

  const handleClose = useCallback(() => {
    closeAllModals();
  }, [closeAllModals]);

  const handleConfirmDelete = useCallback(() => {
    if (!folder) return;

    deleteFolder({
      variables: {
        folderId: folder.id,
        // Cascade: remove the whole sub-tree and move its documents to Trash
        // (recoverable) instead of stranding sub-folders at the corpus root.
        deleteContents: true,
      },
    });
  }, [folder, deleteFolder]);

  if (!showModal || !folder) return null;

  const childCount = folderList.filter(
    (f) => f.parent?.id === folder.id
  ).length;
  const documentCount = folder.documentCount || 0;
  const descendantDocCount = folder.descendantDocumentCount || 0;

  return (
    <StyledModalWrapper>
      <Modal open={showModal} onClose={handleClose} size="sm">
        <OcModalHeader title="Delete Folder" onClose={handleClose} />

        <ModalBody>
          <WarningBox>
            <WarningIcon size={24} />
            <WarningContent>
              <h4>Delete folder and move its contents to Trash</h4>
              <p>
                You are about to delete the folder{" "}
                <strong>"{folder.name}"</strong> and all of its subfolders.
              </p>
              <ul>
                {childCount > 0 && (
                  <li>
                    <strong>{childCount}</strong> subfolder
                    {childCount !== 1 ? "s" : ""} (and any nested below) will be
                    removed
                  </li>
                )}
                {descendantDocCount > 0 ? (
                  <li>
                    <strong>{descendantDocCount}</strong> document
                    {descendantDocCount !== 1 ? "s" : ""} in this folder and its
                    subfolders will be moved to <strong>Trash</strong> — you can
                    restore them until you empty the trash
                  </li>
                ) : (
                  <li>The folder structure will be removed</li>
                )}
              </ul>
            </WarningContent>
          </WarningBox>

          <FolderInfo>
            <div style={{ marginBottom: "8px" }}>
              <strong>Folder:</strong> {folder.path || folder.name}
            </div>
            <div style={{ marginBottom: "8px" }}>
              <strong>Documents in folder:</strong> {documentCount}
            </div>
            <div style={{ marginBottom: "8px" }}>
              <strong>Subfolders:</strong> {childCount}
            </div>
            {descendantDocCount > 0 && (
              <div>
                <strong>Documents in subfolders:</strong> {descendantDocCount}
              </div>
            )}
          </FolderInfo>

          {error && (
            <ErrorMessage title="Error Deleting Folder">
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
            onClick={handleConfirmDelete}
            loading={loading}
            disabled={loading}
          >
            Delete Folder
          </Button>
        </ModalFooter>
      </Modal>
    </StyledModalWrapper>
  );
};
