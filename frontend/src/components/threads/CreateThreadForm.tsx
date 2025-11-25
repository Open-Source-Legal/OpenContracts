import React, { useState } from "react";
import { useMutation } from "@apollo/client";
import styled from "styled-components";
import { X } from "lucide-react";
import {
  CREATE_THREAD,
  CreateThreadInput,
  CreateThreadOutput,
} from "../../graphql/mutations";
import { GET_CONVERSATIONS } from "../../graphql/queries";
import { MessageComposer } from "./MessageComposer";
import { color } from "../../theme/colors";

const Overlay = styled.div`
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 16px;
`;

const Modal = styled.div`
  background: ${({ theme }) => color.N1};
  border-radius: 8px;
  width: 100%;
  max-width: 600px;
  max-height: 90vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.15);
`;

const Header = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid ${({ theme }) => color.N4};
`;

const Title = styled.h2`
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: ${({ theme }) => color.N10};
`;

const CloseButton = styled.button`
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: none;
  border-radius: 4px;
  background: transparent;
  color: ${({ theme }) => color.N7};
  cursor: pointer;
  transition: background 0.15s ease;

  &:hover {
    background: ${({ theme }) => color.N2};
  }

  svg {
    width: 20px;
    height: 20px;
  }
`;

const Content = styled.div`
  flex: 1;
  overflow-y: auto;
  padding: 20px;
`;

const Field = styled.div`
  margin-bottom: 20px;
`;

const Label = styled.label`
  display: block;
  margin-bottom: 6px;
  font-size: 14px;
  font-weight: 500;
  color: ${({ theme }) => color.N10};
`;

const Input = styled.input`
  width: 100%;
  padding: 10px 12px;
  border: 1px solid ${({ theme }) => color.N4};
  border-radius: 6px;
  background: ${({ theme }) => color.N1};
  color: ${({ theme }) => color.N10};
  font-size: 14px;
  font-family: inherit;
  transition: border-color 0.15s ease;

  &:focus {
    outline: none;
    border-color: ${({ theme }) => color.B5};
  }

  &::placeholder {
    color: ${({ theme }) => color.N6};
  }
`;

const TextArea = styled.textarea`
  width: 100%;
  min-height: 80px;
  padding: 10px 12px;
  border: 1px solid ${({ theme }) => color.N4};
  border-radius: 6px;
  background: ${({ theme }) => color.N1};
  color: ${({ theme }) => color.N10};
  font-size: 14px;
  font-family: inherit;
  resize: vertical;
  transition: border-color 0.15s ease;

  &:focus {
    outline: none;
    border-color: ${({ theme }) => color.B5};
  }

  &::placeholder {
    color: ${({ theme }) => color.N6};
  }
`;

const HelpText = styled.p`
  margin: 4px 0 0 0;
  font-size: 12px;
  color: ${({ theme }) => color.N6};
`;

const ErrorMessage = styled.div`
  padding: 12px;
  margin-bottom: 16px;
  background: ${({ theme }) => color.R7}15;
  border: 1px solid ${({ theme }) => color.R7}40;
  border-radius: 6px;
  color: ${({ theme }) => color.R7};
  font-size: 13px;
`;

export interface CreateThreadFormProps {
  /** ID of the corpus to create thread in */
  corpusId: string;
  /** Called when thread is created successfully */
  onSuccess: (conversationId: string) => void;
  /** Called when form is closed/cancelled */
  onClose: () => void;
  /** Initial message content (for testing) */
  initialMessage?: string;
}

export function CreateThreadForm({
  corpusId,
  onSuccess,
  onClose,
  initialMessage,
}: CreateThreadFormProps) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const [createThread, { loading }] = useMutation<
    CreateThreadOutput,
    CreateThreadInput
  >(CREATE_THREAD, {
    refetchQueries: [
      {
        query: GET_CONVERSATIONS,
        variables: { corpusId, conversationType: "THREAD" },
      },
    ],
    onCompleted: (data) => {
      if (data.createThread.ok && data.createThread.obj) {
        onSuccess(data.createThread.obj.id);
      } else {
        setError(
          data.createThread.message ||
            "Failed to create thread. Please try again."
        );
      }
    },
    onError: (err) => {
      console.error("Failed to create thread:", err);
      setError("An unexpected error occurred. Please try again.");
    },
  });

  const handleSubmit = async (content: string) => {
    setError("");

    // Validate
    if (!title.trim()) {
      setError("Please enter a title for your thread.");
      return;
    }

    if (!content.trim()) {
      setError("Please write a message to start the discussion.");
      return;
    }

    await createThread({
      variables: {
        corpusId,
        title: title.trim(),
        description: description.trim() || undefined,
        initialMessage: content,
      },
    });
  };

  const handleOverlayClick = (e: React.MouseEvent) => {
    // Close if clicking outside the modal
    if (e.target === e.currentTarget) {
      onClose();
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    // Close on Escape
    if (e.key === "Escape") {
      onClose();
    }
  };

  return (
    <Overlay onClick={handleOverlayClick} onKeyDown={handleKeyDown}>
      <Modal>
        <Header>
          <Title>Start New Discussion</Title>
          <CloseButton onClick={onClose} title="Close">
            <X />
          </CloseButton>
        </Header>

        <Content>
          {error && <ErrorMessage>{error}</ErrorMessage>}

          <Field>
            <Label htmlFor="thread-title">Title *</Label>
            <Input
              id="thread-title"
              type="text"
              placeholder="What would you like to discuss?"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              disabled={loading}
              maxLength={200}
              autoFocus
            />
            <HelpText>{title.length} / 200 characters</HelpText>
          </Field>

          <Field>
            <Label htmlFor="thread-description">Description (optional)</Label>
            <TextArea
              id="thread-description"
              placeholder="Add more context about this discussion..."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              disabled={loading}
              maxLength={1000}
            />
            <HelpText>{description.length} / 1000 characters</HelpText>
          </Field>

          <Field>
            <Label>Initial Message *</Label>
            <MessageComposer
              placeholder="Start the conversation..."
              onSubmit={handleSubmit}
              onChange={setMessage}
              disabled={loading}
              maxLength={10000}
              initialContent={initialMessage}
            />
            <HelpText>
              Tip: Use <strong>Cmd+Enter</strong> to send your message
            </HelpText>
          </Field>
        </Content>
      </Modal>
    </Overlay>
  );
}
