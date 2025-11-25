import React, { useCallback, useState, useMemo } from "react";
import { useAtomValue, useSetAtom } from "jotai";
import { useMutation } from "@apollo/client";
import { Modal, Button, Message, Dropdown } from "semantic-ui-react";
import styled from "styled-components";
import { X, Folder, Home } from "lucide-react";
import {
  showMoveFolderModalAtom,
  activeFolderModalIdAtom,
  folderListAtom,
  folderMapAtom,
  closeAllFolderModalsAtom,
  folderCorpusIdAtom,
} from "../../../atoms/folderAtoms";
import {
  MOVE_CORPUS_FOLDER,
  MoveCorpusFolderInputs,
  MoveCorpusFolderOutputs,
  GET_CORPUS_FOLDERS,
} from "../../../graphql/queries/folders";

/**
 * MoveFolderModal - Modal for moving folders to different parents
 *
 * Features:
 * - Select new parent folder (or root)
 * - Prevents circular moves (can't move folder into itself or its descendants)
 * - Shows current location
 * - Optimistic update + refetch
 */

const StyledModal = styled(Modal)`
  &.ui.modal {
    max-width: 500px;
  }
`;

const ModalHeader = styled(Modal.Header)`
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #f8fafc;
  border-bottom: 2px solid #e2e8f0;
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
  color: #64748b;
  transition: all 0.15s ease;

  &:hover {
    background: #e2e8f0;
    color: #1e293b;
  }
`;

const CurrentLocationBox = styled.div`
  padding: 12px;
  background: #f1f5f9;
  border-radius: 6px;
  margin-bottom: 16px;
  font-size: 14px;
  color: #475569;

  strong {
    color: #1e293b;
  }
`;

const FolderIcon = styled(Folder)`
  vertical-align: middle;
  margin-right: 6px;
  color: #64748b;
`;

const HomeIcon = styled(Home)`
  vertical-align: middle;
  margin-right: 6px;
  color: #64748b;
`;

export const MoveFolderModal: React.FC = () => {
  const showModal = useAtomValue(showMoveFolderModalAtom);
  const folderId = useAtomValue(activeFolderModalIdAtom);
  const folderMap = useAtomValue(folderMapAtom);
  const folderList = useAtomValue(folderListAtom);
  const corpusId = useAtomValue(folderCorpusIdAtom);
  const setFolderList = useSetAtom(folderListAtom);
  const closeAllModals = useSetAtom(closeAllFolderModalsAtom);

  const folder = folderId ? folderMap.get(folderId) : null;

  const [newParentId, setNewParentId] = useState<string>("__root__");
  const [validationError, setValidationError] = useState<string | null>(null);

  const [moveFolder, { loading, error }] = useMutation<
    MoveCorpusFolderOutputs,
    MoveCorpusFolderInputs
  >(MOVE_CORPUS_FOLDER, {
    onCompleted: (data) => {
      // Update local cache
      const movedFolder = data.moveCorpusFolder.folder;
      if (movedFolder) {
        setFolderList(
          folderList.map((f) => (f.id === movedFolder.id ? movedFolder : f))
        );
      }

      // Close modal
      handleClose();
    },
    refetchQueries: corpusId
      ? [
          {
            query: GET_CORPUS_FOLDERS,
            variables: { corpusId },
          },
        ]
      : [],
  });

  // Build list of valid destination folders (exclude self and descendants)
  const validDestinations = useMemo(() => {
    if (!folder) return [];

    // Get all descendant IDs
    const getDescendantIds = (parentId: string): Set<string> => {
      const descendants = new Set<string>([parentId]);
      const children = folderList.filter((f) => f.parent?.id === parentId);
      children.forEach((child) => {
        getDescendantIds(child.id).forEach((id) => descendants.add(id));
      });
      return descendants;
    };

    const excludedIds = getDescendantIds(folder.id);

    // Build dropdown options
    const options = [
      {
        key: "__root__",
        value: "__root__",
        text: "Corpus Root",
        icon: "home",
      },
    ];

    // Add valid folders
    folderList
      .filter((f) => !excludedIds.has(f.id))
      .sort((a, b) => (a.path || "").localeCompare(b.path || ""))
      .forEach((f) => {
        options.push({
          key: f.id,
          value: f.id,
          text: f.path || f.name,
          icon: "folder",
        });
      });

    return options;
  }, [folder, folderList]);

  const handleClose = useCallback(() => {
    setNewParentId("__root__");
    setValidationError(null);
    closeAllModals();
  }, [closeAllModals]);

  const handleSubmit = useCallback(() => {
    if (!folder) return;

    // Convert "__root__" to null for the mutation
    const targetParentId = newParentId === "__root__" ? null : newParentId;

    // Check if trying to move to same parent
    if (targetParentId === (folder.parent?.id || null)) {
      setValidationError("Folder is already in this location");
      return;
    }

    // Check for duplicate name at destination
    const siblings = targetParentId
      ? folderList.filter(
          (f) => f.parent?.id === targetParentId && f.id !== folder.id
        )
      : folderList.filter((f) => !f.parent && f.id !== folder.id);

    if (siblings.some((f) => f.name === folder.name)) {
      const destinationName = targetParentId
        ? folderMap.get(targetParentId)?.name || "Unknown"
        : "Corpus Root";
      setValidationError(
        `A folder named "${folder.name}" already exists in ${destinationName}`
      );
      return;
    }

    setValidationError(null);

    moveFolder({
      variables: {
        folderId: folder.id,
        newParentId: targetParentId,
      },
    });
  }, [folder, newParentId, folderList, folderMap, moveFolder]);

  if (!showModal || !folder) return null;

  const currentLocation = folder.parent ? folder.parent.name : "Corpus Root";

  return (
    <StyledModal open={showModal} onClose={handleClose}>
      <ModalHeader>
        <span>Move Folder</span>
        <CloseButton onClick={handleClose} aria-label="Close">
          <X size={20} />
        </CloseButton>
      </ModalHeader>

      <Modal.Content>
        <CurrentLocationBox>
          <div style={{ marginBottom: "8px" }}>
            <FolderIcon size={16} />
            <strong>{folder.name}</strong>
          </div>
          <div style={{ fontSize: "13px" }}>
            Current location:{" "}
            {folder.parent ? (
              <>
                <FolderIcon size={14} />
                {currentLocation}
              </>
            ) : (
              <>
                <HomeIcon size={14} />
                Corpus Root
              </>
            )}
          </div>
        </CurrentLocationBox>

        <div style={{ marginBottom: "16px" }}>
          <label
            style={{
              display: "block",
              marginBottom: "8px",
              fontWeight: 600,
              fontSize: "14px",
            }}
          >
            Move to:
          </label>
          <Dropdown
            placeholder="Select destination folder"
            fluid
            selection
            search
            options={validDestinations}
            value={newParentId}
            onChange={(_, data) => {
              setNewParentId(data.value as string);
              setValidationError(null);
            }}
          />
        </div>

        {validationError && (
          <Message error>
            <Message.Header>Cannot Move Folder</Message.Header>
            <p>{validationError}</p>
          </Message>
        )}

        {error && (
          <Message error>
            <Message.Header>Error Moving Folder</Message.Header>
            <p>{error.message}</p>
          </Message>
        )}
      </Modal.Content>

      <Modal.Actions>
        <Button onClick={handleClose} disabled={loading}>
          Cancel
        </Button>
        <Button
          primary
          onClick={handleSubmit}
          loading={loading}
          disabled={loading || newParentId === undefined}
        >
          Move Folder
        </Button>
      </Modal.Actions>
    </StyledModal>
  );
};
