import React from "react";
import { Modal } from "@os-legal/ui";
import styled, { createGlobalStyle } from "styled-components";
import { OS_LEGAL_COLORS } from "../../../assets/configurations/osLegalStyles";

// Minimal overrides for the fullscreen modal body — the native size="fullscreen"
// variant handles positioning, sizing, border-radius, and overlay padding.
// We only need to customize background color and body padding/overflow.
const FullScreenModalBodyStyles = createGlobalStyle`
  .fullscreen-modal {
    background: ${OS_LEGAL_COLORS.gray50};
  }

  .fullscreen-modal .oc-modal-body {
    overflow: hidden !important;
    padding: 0 !important;
    margin: 0 !important;
  }
`;

interface FullScreenModalProps {
  id?: string;
  open: boolean;
  onClose: () => void;
  children: React.ReactNode;
}

export const FullScreenModal: React.FC<FullScreenModalProps> = ({
  id,
  open,
  onClose,
  children,
}) => (
  <>
    <FullScreenModalBodyStyles />
    <Modal
      id={id}
      open={open}
      onClose={onClose}
      size="fullscreen"
      className="fullscreen-modal"
      closeOnEscape={false}
      closeOnOverlay={false}
    >
      {children}
    </Modal>
  </>
);

/* Indigo palette — no OS_LEGAL_COLORS tokens yet; add when indigo tokens are introduced */
export const SourceIndicator = styled.div`
  padding: 0.5rem;
  background: #eef2ff;
  border-left: 3px solid #818cf8;
  margin-bottom: 1rem;
  font-size: 0.875rem;
  color: #4338ca;
`;
