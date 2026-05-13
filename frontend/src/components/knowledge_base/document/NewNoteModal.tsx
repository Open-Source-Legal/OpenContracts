import React, { useState } from "react";
import {
  Modal,
  ModalHeader,
  ModalBody,
  ModalFooter,
  Button,
  Input,
  Textarea,
} from "@os-legal/ui";
import { useMutation } from "@apollo/client";
import { toast } from "react-toastify";
import { CREATE_NOTE } from "../../../graphql/mutations/noteMutations";
import {
  CreateNoteMutation,
  CreateNoteMutationVariables,
} from "../../../graphql/types/NoteTypes";
import { OS_LEGAL_COLORS } from "../../../assets/configurations/osLegalStyles";

interface NewNoteModalProps {
  isOpen: boolean;
  onClose: () => void;
  documentId: string;
  corpusId?: string;
  onCreated?: () => void;
  overlayClassName?: string;
}

export const NewNoteModal: React.FC<NewNoteModalProps> = ({
  isOpen,
  onClose,
  documentId,
  corpusId,
  onCreated,
  overlayClassName,
}) => {
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");

  const [createNote, { loading }] = useMutation<
    CreateNoteMutation,
    CreateNoteMutationVariables
  >(CREATE_NOTE);

  const handleSubmit = async () => {
    if (!title.trim() || !content.trim()) {
      toast.error("Please provide both title and content");
      return;
    }

    try {
      const result = await createNote({
        variables: {
          documentId,
          corpusId,
          title: title.trim(),
          content: content.trim(),
        },
      });

      if (result.data?.createNote.ok) {
        toast.success("Note created successfully!");
        setTitle("");
        setContent("");
        onClose();
        onCreated?.();
      } else {
        toast.error(result.data?.createNote.message || "Failed to create note");
      }
    } catch (error) {
      console.error("Error creating note:", error);
      toast.error("Failed to create note");
    }
  };

  const handleClose = () => {
    setTitle("");
    setContent("");
    onClose();
  };

  return (
    <Modal
      open={isOpen}
      onClose={handleClose}
      size="md"
      overlayClassName={overlayClassName}
    >
      <ModalHeader title="Create New Note" onClose={handleClose} />
      <ModalBody>
        <div style={{ marginBottom: "1rem" }}>
          <label
            style={{ display: "block", marginBottom: "0.25rem" }}
            htmlFor="note-title"
          >
            Title <span style={{ color: OS_LEGAL_COLORS.danger }}>*</span>
          </label>
          <Input
            id="note-title"
            placeholder="Enter note title..."
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            disabled={loading}
          />
        </div>
        <div style={{ marginBottom: "1rem" }}>
          <label
            style={{ display: "block", marginBottom: "0.25rem" }}
            htmlFor="note-content"
          >
            Content (Markdown supported){" "}
            <span style={{ color: OS_LEGAL_COLORS.danger }}>*</span>
          </label>
          <Textarea
            id="note-content"
            placeholder="Write your note here..."
            value={content}
            onChange={(e) => setContent(e.target.value)}
            rows={6}
            disabled={loading}
            style={{ fontFamily: "monospace" }}
          />
        </div>
        <div
          style={{
            padding: "0.75rem",
            background: OS_LEGAL_COLORS.blueSurface,
            border: `1px solid ${OS_LEGAL_COLORS.infoBorder}`,
            borderRadius: "8px",
            fontSize: "0.85rem",
          }}
        >
          <strong>Markdown supported:</strong> **bold**, *italic*, # heading, -
          list, `code`
        </div>
      </ModalBody>
      <ModalFooter>
        <Button variant="secondary" onClick={handleClose} disabled={loading}>
          Cancel
        </Button>
        <Button
          variant="primary"
          onClick={handleSubmit}
          loading={loading}
          disabled={loading || !title.trim() || !content.trim()}
        >
          Create Note
        </Button>
      </ModalFooter>
    </Modal>
  );
};
