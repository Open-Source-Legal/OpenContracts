import React from "react";
import styled from "styled-components";
import { AnimatePresence, motion } from "framer-motion";
import { X } from "lucide-react";
import { OS_LEGAL_COLORS } from "../../../../../assets/configurations/osLegalStyles";
import {
  MOBILE_RADIUS,
  MOBILE_SHADOW,
  MOBILE_SURFACE_TINT,
} from "./mobileTheme";

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
  background: ${MOBILE_SURFACE_TINT};
`;

/** Header chrome: floats on a soft downward shadow instead of a hairline. */
const Header = styled.div`
  flex-shrink: 0;
  height: 56px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 14px;
  background: ${OS_LEGAL_COLORS.surface};
  box-shadow: ${MOBILE_SHADOW.header};
  z-index: 1;
`;

const Title = styled.div`
  flex: 1;
  font-size: 17px;
  font-weight: 700;
  letter-spacing: -0.01em;
  color: ${OS_LEGAL_COLORS.textPrimary};
`;

/** Clean ghost circular close button with press feedback. */
const CloseButton = styled.button`
  width: 34px;
  height: 34px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: ${MOBILE_RADIUS.pill};
  background: ${OS_LEGAL_COLORS.surfaceLight};
  color: ${OS_LEGAL_COLORS.textSecondary};
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
  transition: transform 0.12s ease, background 0.16s ease;

  &:active {
    transform: scale(0.9);
    background: ${OS_LEGAL_COLORS.border};
  }
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
