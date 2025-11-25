import React, { useCallback, useState, useEffect } from "react";
import { useAtomValue, useSetAtom } from "jotai";
import { useMutation } from "@apollo/client";
import { Modal, Form, Button, Message } from "semantic-ui-react";
import styled from "styled-components";
import { X } from "lucide-react";
import {
  showEditFolderModalAtom,
  activeFolderModalIdAtom,
  folderListAtom,
  folderMapAtom,
  closeAllFolderModalsAtom,
  folderCorpusIdAtom,
} from "../../../atoms/folderAtoms";
import {
  UPDATE_CORPUS_FOLDER,
  UpdateCorpusFolderInputs,
  UpdateCorpusFolderOutputs,
  GET_CORPUS_FOLDERS,
  parseCorpusFolderTags,
} from "../../../graphql/queries/folders";

/**
 * EditFolderModal - Modal for editing existing folders
 *
 * Features:
 * - Pre-populate form with current folder data
 * - Update name, description, color, icon, tags
 * - Form validation (no duplicate names at same level)
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

const ColorPickerWrapper = styled.div`
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 8px;
`;

const ColorPreview = styled.div<{ $color: string }>`
  width: 40px;
  height: 40px;
  border-radius: 8px;
  background-color: ${(props) => props.$color};
  border: 2px solid #e2e8f0;
  cursor: pointer;
  transition: all 0.15s ease;

  &:hover {
    transform: scale(1.05);
    border-color: #cbd5e1;
  }
`;

const ColorInput = styled.input`
  flex: 1;
  padding: 8px 12px;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  font-size: 14px;
  font-family: monospace;

  &:focus {
    outline: none;
    border-color: #3b82f6;
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
  }
`;

export const EditFolderModal: React.FC = () => {
  const showModal = useAtomValue(showEditFolderModalAtom);
  const folderId = useAtomValue(activeFolderModalIdAtom);
  const folderMap = useAtomValue(folderMapAtom);
  const folderList = useAtomValue(folderListAtom);
  const corpusId = useAtomValue(folderCorpusIdAtom);
  const setFolderList = useSetAtom(folderListAtom);
  const closeAllModals = useSetAtom(closeAllFolderModalsAtom);

  const folder = folderId ? folderMap.get(folderId) : null;

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [color, setColor] = useState("#05313d");
  const [icon, setIcon] = useState("folder");
  const [tags, setTags] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);

  // Pre-populate form when folder ID changes (not on every render)
  useEffect(() => {
    if (folder) {
      const parsedFolder = parseCorpusFolderTags(folder);
      setName(parsedFolder.name);
      setDescription(parsedFolder.description || "");
      setColor(parsedFolder.color || "#05313d");
      setIcon(parsedFolder.icon || "folder");
      setTags(parsedFolder.tags.join(", "));
      setValidationError(null);
    }
  }, [folderId, folder]);

  const [updateFolder, { loading, error }] = useMutation<
    UpdateCorpusFolderOutputs,
    UpdateCorpusFolderInputs
  >(UPDATE_CORPUS_FOLDER, {
    onCompleted: (data) => {
      // Update local cache
      const updatedFolder = data.updateCorpusFolder.folder;
      if (updatedFolder) {
        setFolderList(
          folderList.map((f) => (f.id === updatedFolder.id ? updatedFolder : f))
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

  const handleClose = useCallback(() => {
    closeAllModals();
  }, [closeAllModals]);

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();

      if (!folder) return;

      // Validation
      if (!name.trim()) {
        setValidationError("Folder name is required");
        return;
      }

      if (name.length > 255) {
        setValidationError("Folder name must be 255 characters or less");
        return;
      }

      // Check for duplicate name at same level (excluding current folder)
      const siblings = folder.parent
        ? folderList.filter(
            (f) => f.parent?.id === folder.parent?.id && f.id !== folder.id
          )
        : folderList.filter((f) => !f.parent && f.id !== folder.id);

      if (siblings.some((f) => f.name === name.trim())) {
        setValidationError(
          `A folder named "${name.trim()}" already exists at this level`
        );
        return;
      }

      setValidationError(null);

      // Parse tags
      const parsedTags = tags
        .split(",")
        .map((t) => t.trim())
        .filter((t) => t.length > 0);

      updateFolder({
        variables: {
          folderId: folder.id,
          name: name.trim(),
          description: description.trim(),
          color,
          icon,
          tags: parsedTags,
        },
      });
    },
    [name, description, color, icon, tags, folder, folderList, updateFolder]
  );

  if (!showModal || !folder) return null;

  return (
    <StyledModal open={showModal} onClose={handleClose}>
      <ModalHeader>
        <span>Edit Folder</span>
        <CloseButton onClick={handleClose} aria-label="Close">
          <X size={20} />
        </CloseButton>
      </ModalHeader>

      <Modal.Content>
        <Form onSubmit={handleSubmit} error={!!validationError || !!error}>
          <Form.Field required>
            <label>Folder Name</label>
            <Form.Input
              placeholder="Enter folder name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoFocus
              maxLength={255}
            />
          </Form.Field>

          <Form.Field>
            <label>Description</label>
            <Form.TextArea
              placeholder="Optional description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
            />
          </Form.Field>

          <Form.Field>
            <label>Color</label>
            <ColorPickerWrapper>
              <ColorPreview
                $color={color}
                onClick={() =>
                  document.getElementById("edit-color-picker")?.click()
                }
                title="Click to open color picker"
              />
              <input
                id="edit-color-picker"
                type="color"
                value={color}
                onChange={(e) => setColor(e.target.value)}
                style={{ display: "none" }}
              />
              <ColorInput
                type="text"
                value={color}
                onChange={(e) => setColor(e.target.value)}
                placeholder="#05313d"
                maxLength={7}
              />
            </ColorPickerWrapper>
          </Form.Field>

          <Form.Field>
            <label>Icon</label>
            <Form.Input
              placeholder="folder"
              value={icon}
              onChange={(e) => setIcon(e.target.value)}
              maxLength={50}
            />
            <div
              style={{ fontSize: "12px", color: "#64748b", marginTop: "4px" }}
            >
              Use Lucide React icon names (e.g., folder, file-text, star)
            </div>
          </Form.Field>

          <Form.Field>
            <label>Tags</label>
            <Form.Input
              placeholder="tag1, tag2, tag3"
              value={tags}
              onChange={(e) => setTags(e.target.value)}
            />
            <div
              style={{ fontSize: "12px", color: "#64748b", marginTop: "4px" }}
            >
              Comma-separated tags for organization
            </div>
          </Form.Field>

          {validationError && (
            <Message error>
              <Message.Header>Validation Error</Message.Header>
              <p>{validationError}</p>
            </Message>
          )}

          {error && (
            <Message error>
              <Message.Header>Error Updating Folder</Message.Header>
              <p>{error.message}</p>
            </Message>
          )}
        </Form>
      </Modal.Content>

      <Modal.Actions>
        <Button onClick={handleClose} disabled={loading}>
          Cancel
        </Button>
        <Button
          primary
          onClick={handleSubmit}
          loading={loading}
          disabled={loading || !name.trim()}
        >
          Save Changes
        </Button>
      </Modal.Actions>
    </StyledModal>
  );
};
