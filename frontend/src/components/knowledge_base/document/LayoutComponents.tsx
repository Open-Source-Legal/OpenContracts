import React from "react";
import { Modal } from "@os-legal/ui";
import styled, { createGlobalStyle } from "styled-components";
import { OS_LEGAL_COLORS } from "../../../assets/configurations/osLegalStyles";

// Minimal overrides for the fullscreen modal body — the native size="fullscreen"
// variant handles positioning, sizing, border-radius, and overlay padding.
// We override max-height because the base .oc-modal sets max-height: calc(100vh - 32px)
// which the fullscreen variant doesn't clear, and overflow: hidden to contain content.
// Injected unconditionally when FullScreenModal is mounted (even when closed),
// but scoped via .fullscreen-modal class to prevent leakage.
const FullScreenModalBodyStyles = createGlobalStyle`
  .fullscreen-modal-overlay {
    align-items: stretch;
    justify-content: stretch;
    padding: 0 !important;
    z-index: var(--oc-app-modal-z-index, 3000);
  }

  .fullscreen-modal {
    background: ${OS_LEGAL_COLORS.gray50};
    width: 100vw !important;
    max-width: 100vw !important;
    height: var(--oc-visible-viewport-height, 100vh) !important;
    max-height: var(--oc-visible-viewport-height, 100vh) !important;
    border-radius: 0 !important;
    overflow: hidden;
    min-height: 0;
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
      overlayClassName="fullscreen-modal-overlay"
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
