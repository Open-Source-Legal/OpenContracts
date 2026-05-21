import React from "react";
import styled from "styled-components";
import { AnimatePresence, motion } from "framer-motion";
import { X } from "lucide-react";
import { OS_LEGAL_COLORS } from "../../../../../assets/configurations/osLegalStyles";

export interface MobileSheetProps {
  open: boolean;
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}

const Scrim = styled(motion.div)`
  position: absolute;
  inset: 0;
  background: rgba(15, 23, 42, 0.32);
  z-index: 50;
`;

const Panel = styled(motion.div)`
  position: absolute;
  inset: 0;
  z-index: 51;
  display: flex;
  flex-direction: column;
  background: ${OS_LEGAL_COLORS.background};
`;

const Header = styled.div`
  flex-shrink: 0;
  height: 48px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 12px;
  border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
  background: white;
`;

const Title = styled.div`
  flex: 1;
  font-size: 15px;
  font-weight: 700;
  color: ${OS_LEGAL_COLORS.textPrimary};
`;

const CloseButton = styled.button`
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 8px;
  background: ${OS_LEGAL_COLORS.surfaceHover};
  color: ${OS_LEGAL_COLORS.textSecondary};
  cursor: pointer;
`;

const Body = styled.div`
  flex: 1;
  min-height: 0;
  overflow-y: auto;
`;

/** Full-height slide-up panel. One open/close animation, one close action.
 *  Deliberately not a draggable multi-snap sheet. */
export const MobileSheet: React.FC<MobileSheetProps> = ({
  open,
  title,
  onClose,
  children,
}) => (
  <AnimatePresence>
    {open && (
      <>
        <Scrim
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
        />
        <Panel
          initial={{ y: "100%" }}
          animate={{ y: 0 }}
          exit={{ y: "100%" }}
          transition={{ type: "tween", duration: 0.22 }}
        >
          <Header>
            <Title>{title}</Title>
            <CloseButton aria-label="Close" onClick={onClose}>
              <X size={18} />
            </CloseButton>
          </Header>
          <Body>{children}</Body>
        </Panel>
      </>
    )}
  </AnimatePresence>
);
