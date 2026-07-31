/**
 * "Save to My Documents" control for a single chat message.
 *
 * A chat answer is otherwise unsaved. Unlike a research report it leaves no
 * durable artifact, so once the thread scrolls away the analysis is only
 * recoverable by re-reading the conversation. This files the message into the
 * caller's personal workspace corpus as a markdown document — optionally
 * inside a folder — via the ``saveMessageToWorkspace`` mutation.
 */
import React, { useState } from "react";
import { useMutation } from "@apollo/client";
import { FolderPlus, Loader2 } from "lucide-react";
import { toast } from "react-toastify";
import styled from "styled-components";

import {
  SAVE_MESSAGE_TO_WORKSPACE,
  SaveMessageToWorkspaceInput,
  SaveMessageToWorkspaceOutput,
} from "../../../graphql/mutations";

const Wrapper = styled.div`
  position: relative;
  display: inline-flex;
`;

const TriggerButton = styled.button`
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.15rem 0.5rem;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: #64748b;
  font-size: 0.75rem;
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease;

  &:hover:not(:disabled) {
    background: rgba(100, 116, 139, 0.12);
    color: #334155;
  }

  &:disabled {
    opacity: 0.6;
    cursor: default;
  }
`;

const Popover = styled.div`
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  z-index: 40;
  width: 268px;
  padding: 0.85rem;
  border-radius: 10px;
  background: #ffffff;
  border: 1px solid rgba(148, 163, 184, 0.4);
  box-shadow: 0 12px 28px rgba(15, 23, 42, 0.16);
  display: flex;
  flex-direction: column;
  gap: 0.55rem;
`;

const FieldLabel = styled.label`
  font-size: 0.7rem;
  font-weight: 600;
  color: #475569;
  text-transform: uppercase;
  letter-spacing: 0.02em;
`;

const TextInput = styled.input`
  width: 100%;
  padding: 0.4rem 0.55rem;
  border-radius: 6px;
  border: 1px solid rgba(148, 163, 184, 0.55);
  font-size: 0.8rem;

  &:focus {
    outline: none;
    border-color: #0ea5e9;
  }
`;

const Hint = styled.span`
  font-size: 0.68rem;
  color: #94a3b8;
  line-height: 1.35;
`;

const Actions = styled.div`
  display: flex;
  justify-content: flex-end;
  gap: 0.4rem;
  margin-top: 0.15rem;
`;

const SmallButton = styled.button<{ $primary?: boolean }>`
  padding: 0.3rem 0.7rem;
  border-radius: 6px;
  font-size: 0.75rem;
  cursor: pointer;
  border: 1px solid
    ${(props) => (props.$primary ? "transparent" : "rgba(148,163,184,0.55)")};
  background: ${(props) => (props.$primary ? "#0f766e" : "#ffffff")};
  color: ${(props) => (props.$primary ? "#ffffff" : "#475569")};

  &:disabled {
    opacity: 0.6;
    cursor: default;
  }
`;

export interface SaveMessageToWorkspaceProps {
  messageId: string;
  /** Pre-fills the folder field; the user can clear or change it. */
  defaultFolderName?: string;
}

export const SaveMessageToWorkspace: React.FC<SaveMessageToWorkspaceProps> = ({
  messageId,
  defaultFolderName = "Saved Answers",
}) => {
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [folderName, setFolderName] = useState(defaultFolderName);

  const [saveMessage, { loading }] = useMutation<
    SaveMessageToWorkspaceOutput,
    SaveMessageToWorkspaceInput
  >(SAVE_MESSAGE_TO_WORKSPACE);

  const handleSave = async () => {
    try {
      const { data } = await saveMessage({
        variables: {
          messageId,
          // Blank means "derive it" / "corpus root" server-side; sending "" would
          // otherwise be taken as an explicit empty title or folder.
          title: title.trim() || undefined,
          folderName: folderName.trim() || undefined,
        },
      });
      const payload = data?.saveMessageToWorkspace;
      if (payload?.ok) {
        toast.success(payload.message ?? "Saved to My Documents.");
        setOpen(false);
        setTitle("");
      } else {
        toast.error(
          payload?.message ?? "Could not save this message to My Documents."
        );
      }
    } catch (error) {
      toast.error(
        `Could not save this message to My Documents: ${
          error instanceof Error ? error.message : String(error)
        }`
      );
    }
  };

  return (
    <Wrapper>
      <TriggerButton
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        disabled={loading}
        aria-expanded={open}
        aria-label="Save this message to My Documents"
        title="Save this message to My Documents"
        data-testid="save-message-to-workspace-trigger"
      >
        {loading ? <Loader2 size={13} /> : <FolderPlus size={13} />}
        Save
      </TriggerButton>

      {open && (
        <Popover
          role="dialog"
          aria-label="Save message to My Documents"
          data-testid="save-message-to-workspace-popover"
        >
          <FieldLabel htmlFor={`save-title-${messageId}`}>Title</FieldLabel>
          <TextInput
            id={`save-title-${messageId}`}
            value={title}
            placeholder="Defaults to the message's first line"
            onChange={(event) => setTitle(event.target.value)}
            data-testid="save-message-title-input"
          />

          <FieldLabel htmlFor={`save-folder-${messageId}`}>Folder</FieldLabel>
          <TextInput
            id={`save-folder-${messageId}`}
            value={folderName}
            placeholder="Leave blank for the workspace root"
            onChange={(event) => setFolderName(event.target.value)}
            data-testid="save-message-folder-input"
          />
          <Hint>
            Saved to your private My Documents corpus. Saving again updates the
            same file as a new version.
          </Hint>

          <Actions>
            <SmallButton type="button" onClick={() => setOpen(false)}>
              Cancel
            </SmallButton>
            <SmallButton
              type="button"
              $primary
              onClick={handleSave}
              disabled={loading}
              data-testid="save-message-confirm"
            >
              {loading ? "Saving…" : "Save"}
            </SmallButton>
          </Actions>
        </Popover>
      )}
    </Wrapper>
  );
};
