import React, { useEffect } from "react";
import { Modal } from "@os-legal/ui";
import styled, { createGlobalStyle } from "styled-components";
import { OS_LEGAL_COLORS } from "../../../assets/configurations/osLegalStyles";

export const DOCUMENT_KB_CHILD_MODAL_OVERLAY_CLASS =
  "document-kb-child-modal-overlay";

// Minimal overrides for the fullscreen modal body — the native size="fullscreen"
// variant handles positioning, sizing, border-radius, and overlay padding.
// We override max-height because the base .oc-modal sets max-height: calc(100vh - 32px)
// which the fullscreen variant doesn't clear, and overflow: hidden to contain content.
// Injected unconditionally when FullScreenModal is mounted (even when closed),
// but scoped via DKB modal classes to prevent leakage.
const FullScreenModalBodyStyles = createGlobalStyle`
  html.document-kb-scroll-lock,
  body.document-kb-scroll-lock {
    height: var(--oc-visible-viewport-height, 100vh) !important;
    min-height: var(--oc-visible-viewport-height, 100vh) !important;
    max-height: var(--oc-visible-viewport-height, 100vh) !important;
    overflow: hidden !important;
    overscroll-behavior: none;
  }

  body.document-kb-scroll-lock {
    position: fixed !important;
    top: 0 !important;
    left: 0 !important;
    right: 0 !important;
    width: 100% !important;
  }

  html.document-kb-scroll-lock #root {
    height: var(--oc-visible-viewport-height, 100vh) !important;
    min-height: 0 !important;
    max-height: var(--oc-visible-viewport-height, 100vh) !important;
    overflow: hidden !important;
  }

  .fullscreen-modal-overlay {
    position: fixed !important;
    inset: 0 !important;
    align-items: stretch;
    justify-content: stretch;
    padding: 0 !important;
    z-index: var(--oc-app-modal-z-index, 3000);
    height: var(--oc-visible-viewport-height, 100vh) !important;
    max-height: var(--oc-visible-viewport-height, 100vh) !important;
    overflow: hidden !important;
    overscroll-behavior: none;
  }

  .fullscreen-modal {
    position: fixed !important;
    inset: 0 !important;
    background: ${OS_LEGAL_COLORS.gray50};
    width: 100vw !important;
    max-width: 100vw !important;
    height: var(--oc-visible-viewport-height, 100vh) !important;
    max-height: var(--oc-visible-viewport-height, 100vh) !important;
    margin: 0 !important;
    border-radius: 0 !important;
    overflow: hidden;
    min-height: 0;
  }

  .fullscreen-modal,
  .fullscreen-modal *,
  .fullscreen-modal *::before,
  .fullscreen-modal *::after {
    box-sizing: border-box;
  }

  .fullscreen-modal .oc-modal-body {
    overflow: hidden !important;
    padding: 0 !important;
    margin: 0 !important;
  }

  .oc-modal-overlay.${DOCUMENT_KB_CHILD_MODAL_OVERLAY_CLASS} {
    z-index: var(--oc-app-modal-child-z-index, 3100);
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
}) => {
  useEffect(() => {
    if (!open) return;

    const scrollY = window.scrollY;
    window.scrollTo(0, 0);
    document.documentElement.classList.add("document-kb-scroll-lock");
    document.body.classList.add("document-kb-scroll-lock");

    return () => {
      document.documentElement.classList.remove("document-kb-scroll-lock");
      document.body.classList.remove("document-kb-scroll-lock");
      window.scrollTo(0, scrollY);
    };
  }, [open]);

  return (
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
};

/* Indigo palette — no OS_LEGAL_COLORS tokens yet; add when indigo tokens are introduced */
export const SourceIndicator = styled.div`
  padding: 0.5rem;
  background: #eef2ff;
  border-left: 3px solid #818cf8;
  margin-bottom: 1rem;
  font-size: 0.875rem;
  color: #4338ca;
`;
