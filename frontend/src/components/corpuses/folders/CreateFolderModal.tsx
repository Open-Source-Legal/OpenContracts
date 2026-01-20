import React, { useCallback, useState } from "react";
import { useAtom, useAtomValue, useSetAtom } from "jotai";
import { useMutation } from "@apollo/client";
import { Modal } from "semantic-ui-react";
import { Alert, Button, Input, Textarea, FormField } from "@os-legal/ui";
import styled from "styled-components";
import { X } from "lucide-react";
import {
  showCreateFolderModalAtom,
  createFolderParentIdAtom,
  folderCorpusIdAtom,
  folderListAtom,
  closeAllFolderModalsAtom,
  selectAndExpandFolderAtom,
} from "../../../atoms/folderAtoms";
import {
  CREATE_CORPUS_FOLDER,
  CreateCorpusFolderInputs,
  CreateCorpusFolderOutputs,
  GET_CORPUS_FOLDERS,
} from "../../../graphql/queries/folders";

/**
 * CreateFolderModal - Modal for creating new folders
 *
 * Features:
 * - Create at root level (parentId = null) or under selected folder
 * - Form validation
 * - Color picker for folder color
 * - Icon selector
 * - Tag management
 * - Optimistic update + refetch
 * - Auto-select and expand newly created folder
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

export const CreateFolderModal: React.FC = () => {
  const [showModal, setShowModal] = useAtom(showCreateFolderModalAtom);
  const parentId = useAtomValue(createFolderParentIdAtom);
  const corpusId = useAtomValue(folderCorpusIdAtom);
  const folderList = useAtomValue(folderListAtom);
  const setFolderList = useSetAtom(folderListAtom);
  const closeAllModals = useSetAtom(closeAllFolderModalsAtom);
  const selectAndExpand = useSetAtom(selectAndExpandFolderAtom);

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [color, setColor] = useState("#05313d");
  const [icon, setIcon] = useState("folder");
  const [tags, setTags] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);

  const [createFolder, { loading, error }] = useMutation<
    CreateCorpusFolderOutputs,
    CreateCorpusFolderInputs
  >(CREATE_CORPUS_FOLDER, {
    onCompleted: (data) => {
      // Update local cache
      const newFolder = data.createCorpusFolder.folder;
      if (newFolder) {
        setFolderList([...folderList, newFolder]);

        // Select and expand the new folder
        selectAndExpand(newFolder.id);
      }

      // Close modal and reset form
      handleClose();
    },
    refetchQueries: [
      {
        query: GET_CORPUS_FOLDERS,
        variables: { corpusId },
      },
    ],
  });

  const handleClose = useCallback(() => {
    setName("");
    setDescription("");
    setColor("#05313d");
    setIcon("folder");
    setTags("");
    setValidationError(null);
    closeAllModals();
  }, [closeAllModals]);

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();

      // Validation
      if (!name.trim()) {
        setValidationError("Folder name is required");
        return;
      }

      if (name.length > 255) {
        setValidationError("Folder name must be 255 characters or less");
        return;
      }

      // Check for duplicate name at same level
      const siblings = parentId
        ? folderList.filter((f) => f.parent?.id === parentId)
        : folderList.filter((f) => !f.parent);

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

      createFolder({
        variables: {
          corpusId: corpusId!,
          name: name.trim(),
          parentId: parentId || undefined,
          description: description.trim(),
          color,
          icon,
          tags: parsedTags,
        },
      });
    },
    [
      name,
      description,
      color,
      icon,
      tags,
      corpusId,
      parentId,
      folderList,
      createFolder,
    ]
  );

  if (!showModal || !corpusId) return null;

  const parentFolder = parentId
    ? folderList.find((f) => f.id === parentId)
    : null;

  return (
    <StyledModal open={showModal} onClose={handleClose}>
      <ModalHeader>
        <span>Create New Folder</span>
        <CloseButton onClick={handleClose} aria-label="Close">
          <X size={20} />
        </CloseButton>
      </ModalHeader>

      <Modal.Content>
        <form onSubmit={handleSubmit}>
          {parentFolder && (
            <Alert variant="info">
              Creating folder inside: <strong>{parentFolder.name}</strong>
            </Alert>
          )}

          <FormField label="Folder Name" required>
            <Input
              placeholder="Enter folder name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoFocus
              maxLength={255}
              fullWidth
            />
          </FormField>

          <FormField label="Description">
            <Textarea
              placeholder="Optional description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              fullWidth
            />
          </FormField>

          <FormField label="Color">
            <ColorPickerWrapper>
              <ColorPreview
                $color={color}
                onClick={() => document.getElementById("color-picker")?.click()}
                title="Click to open color picker"
              />
              <input
                id="color-picker"
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
          </FormField>

          <FormField
            label="Icon"
            helperText="Use Lucide React icon names (e.g., folder, file-text, star)"
          >
            <Input
              placeholder="folder"
              value={icon}
              onChange={(e) => setIcon(e.target.value)}
              maxLength={50}
              fullWidth
            />
          </FormField>

          <FormField
            label="Tags"
            helperText="Comma-separated tags for organization"
          >
            <Input
              placeholder="tag1, tag2, tag3"
              value={tags}
              onChange={(e) => setTags(e.target.value)}
              fullWidth
            />
          </FormField>

          {validationError && (
            <Alert variant="error" title="Validation Error">
              {validationError}
            </Alert>
          )}

          {error && (
            <Alert variant="error" title="Error Creating Folder">
              {error.message}
            </Alert>
          )}
        </form>
      </Modal.Content>

      <Modal.Actions>
        <Button variant="secondary" onClick={handleClose} disabled={loading}>
          Cancel
        </Button>
        <Button
          variant="primary"
          onClick={handleSubmit}
          loading={loading}
          disabled={loading || !name.trim()}
        >
          Create Folder
        </Button>
      </Modal.Actions>
    </StyledModal>
  );
};
