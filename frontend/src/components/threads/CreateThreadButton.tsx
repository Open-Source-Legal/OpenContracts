import React, { useState } from "react";
import styled from "styled-components";
import { Plus, MessageSquarePlus } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useReactiveVar } from "@apollo/client";
import { CreateThreadForm } from "./CreateThreadForm";
import { color } from "../../theme/colors";
import { spacing } from "../../theme/spacing";
import { openedCorpus } from "../../graphql/cache";
import { getCorpusThreadUrl } from "../../utils/navigationUtils";

const Button = styled.button<{ $variant?: "primary" | "secondary" }>`
  display: flex;
  align-items: center;
  gap: ${spacing.xs};
  padding: ${spacing.xs} ${spacing.md};
  border: ${(props) =>
    props.$variant === "primary" ? "none" : `1px solid ${color.B5}`};
  border-radius: 6px;
  background: ${(props) =>
    props.$variant === "primary" ? color.B5 : "transparent"};
  color: ${(props) => (props.$variant === "primary" ? color.N1 : color.B7)};
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;

  &:hover {
    background: ${(props) =>
      props.$variant === "primary" ? color.B6 : color.B1};
    transform: translateY(-1px);
    box-shadow: ${(props) =>
      props.$variant === "primary" ? "0 2px 8px rgba(0, 0, 0, 0.15)" : "none"};
  }

  &:active {
    transform: translateY(0);
  }

  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
    transform: none;
  }

  svg {
    width: 16px;
    height: 16px;
  }
`;

const FloatingActionButton = styled.button`
  position: fixed;
  bottom: ${spacing.xl};
  right: ${spacing.xl};
  width: 56px;
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 50%;
  background: ${color.B5};
  color: ${color.N1};
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
  cursor: pointer;
  transition: all 0.2s;
  z-index: 50;

  &:hover {
    background: ${color.B6};
    transform: scale(1.1);
    box-shadow: 0 6px 16px rgba(0, 0, 0, 0.25);
  }

  &:active {
    transform: scale(1.05);
  }

  svg {
    width: 24px;
    height: 24px;
  }

  @media (max-width: 640px) {
    bottom: ${spacing.lg};
    right: ${spacing.lg};
    width: 48px;
    height: 48px;

    svg {
      width: 20px;
      height: 20px;
    }
  }
`;

export interface CreateThreadButtonProps {
  /** ID of the corpus to create thread in */
  corpusId: string;
  /** Button variant: primary (filled) or secondary (outlined) */
  variant?: "primary" | "secondary";
  /** Display as floating action button (mobile-friendly) */
  floating?: boolean;
  /** Optional className for styling */
  className?: string;
  /** Disabled state */
  disabled?: boolean;
}

/**
 * Button to create a new discussion thread
 * Opens CreateThreadForm modal when clicked
 */
export function CreateThreadButton({
  corpusId,
  variant = "primary",
  floating = false,
  className,
  disabled = false,
}: CreateThreadButtonProps) {
  const [showModal, setShowModal] = useState(false);
  const navigate = useNavigate();
  const corpus = useReactiveVar(openedCorpus);

  const handleSuccess = (conversationId: string) => {
    setShowModal(false);
    // Navigate to the newly created thread using proper slug-based URL
    if (corpus) {
      const url = getCorpusThreadUrl(corpus, conversationId);
      if (url !== "#") {
        navigate(url);
      } else {
        console.warn(
          "[CreateThreadButton] Cannot navigate - corpus missing slug data"
        );
      }
    } else {
      console.warn("[CreateThreadButton] Cannot navigate - no corpus in state");
    }
  };

  const handleClose = () => {
    setShowModal(false);
  };

  if (floating) {
    return (
      <>
        <FloatingActionButton
          onClick={() => setShowModal(true)}
          disabled={disabled}
          aria-label="Start new discussion"
          className={className}
        >
          <Plus />
        </FloatingActionButton>

        {showModal && (
          <CreateThreadForm
            corpusId={corpusId}
            onSuccess={handleSuccess}
            onClose={handleClose}
          />
        )}
      </>
    );
  }

  return (
    <>
      <Button
        $variant={variant}
        onClick={() => setShowModal(true)}
        disabled={disabled}
        aria-label="Start new discussion"
        className={className}
      >
        <MessageSquarePlus />
        <span>New Discussion</span>
      </Button>

      {showModal && (
        <CreateThreadForm
          corpusId={corpusId}
          onSuccess={handleSuccess}
          onClose={handleClose}
        />
      )}
    </>
  );
}
