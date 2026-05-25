import React from "react";
import styled, { keyframes } from "styled-components";
import { motion, AnimatePresence } from "framer-motion";
import { color } from "../../theme/colors";
import {
  OS_LEGAL_COLORS,
  accentAlpha,
} from "../../assets/configurations/osLegalStyles";
import { SMALL_MOBILE_BREAKPOINT } from "../../assets/configurations/constants";
import { CiteMark } from "../brand/CiteMark";

interface ModernLoadingDisplayProps {
  type?: "document" | "corpus" | "extract" | "auth" | "default";
  message?: string;
  size?: "small" | "medium" | "large";
  /**
   * When true, the loader renders in normal flow inside its parent
   * (no full-viewport overlay or background). Use this for loading states
   * embedded in a panel or section. Default is an overlay that covers the
   * full viewport with the cite paper-tinted backdrop — this is what
   * route-level loaders and the AuthGate need so the underlying app chrome
   * (especially on mobile) doesn't bleed through.
   */
  inline?: boolean;
}

const pulse = keyframes`
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0.5;
  }
`;

const glowPulse = keyframes`
  0%, 100% {
    opacity: 0.15;
    transform: scale(1);
  }
  50% {
    opacity: 0.25;
    transform: scale(1.05);
  }
`;

const shimmer = keyframes`
  0% {
    background-position: -200% 0;
  }
  100% {
    background-position: 200% 0;
  }
`;

const float = keyframes`
  0%, 100% {
    transform: translateY(0px);
  }
  50% {
    transform: translateY(-8px);
  }
`;

const Container = styled(motion.div)<{ $inline?: boolean; $size?: string }>`
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: ${(props) =>
    props.$inline
      ? props.$size === "small"
        ? "1.5rem 1rem"
        : "2rem 1rem"
      : props.$size === "small"
      ? "2rem"
      : "3rem"};

  ${(props) =>
    props.$inline
      ? `
    position: relative;
    width: 100%;
  `
      : `
    position: fixed;
    inset: 0;
    z-index: 9999;
    background: linear-gradient(135deg, ${OS_LEGAL_COLORS.background} 0%, #f0fdfa 100%);
    backdrop-filter: blur(12px);
    /* Belt-and-suspenders fallback for mobile browsers where
       backdrop-filter is unsupported — keep the layer fully opaque so
       the app chrome underneath never shows through. */
    @supports not (backdrop-filter: blur(12px)) {
      background: ${OS_LEGAL_COLORS.background};
    }
  `}
`;

const IconContainer = styled(motion.div)<{ $size?: string }>`
  position: relative;
  width: ${(props) => (props.$size === "small" ? "72px" : "100px")};
  height: ${(props) => (props.$size === "small" ? "72px" : "100px")};
  margin-bottom: ${(props) => (props.$size === "small" ? "1.25rem" : "2rem")};

  /* Outer glow - teal radial gradient */
  &::before {
    content: "";
    position: absolute;
    inset: -35px;
    background: radial-gradient(
      circle,
      ${OS_LEGAL_COLORS.accent} 0%,
      ${accentAlpha(0.4)} 40%,
      transparent 70%
    );
    border-radius: 50%;
    opacity: 0.15;
    animation: ${glowPulse} 3s ease-in-out infinite;
    filter: blur(20px);
  }
`;

/* Squircle shape using clip-path for a more interesting container */
const IconWrapper = styled(motion.div)<{ $size?: string }>`
  position: relative;
  width: ${(props) => (props.$size === "small" ? "72px" : "100px")};
  height: ${(props) => (props.$size === "small" ? "72px" : "100px")};
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(145deg, ${color.white} 0%, #f0fdfa 100%);
  /* Squircle-like border radius for more organic feel */
  border-radius: ${(props) => (props.$size === "small" ? "20px" : "28px")};
  box-shadow: 0 12px 40px ${accentAlpha(0.12)}, 0 4px 12px ${accentAlpha(0.06)},
    inset 0 1px 0 rgba(255, 255, 255, 0.8);
  animation: ${float} 3.5s ease-in-out infinite;
  border: 1px solid ${accentAlpha(0.12)};
  overflow: hidden;

  /* Subtle inner highlight */
  &::before {
    content: "";
    position: absolute;
    inset: 0;
    border-radius: 28px;
    background: linear-gradient(
      135deg,
      rgba(255, 255, 255, 0.5) 0%,
      transparent 50%
    );
    pointer-events: none;
  }

  svg {
    width: ${(props) => (props.$size === "small" ? "44px" : "60px")};
    height: ${(props) => (props.$size === "small" ? "44px" : "60px")};
    position: relative;
    z-index: 1;
  }

  /* On very narrow mobile widths shrink even the medium/large icon so the
     overlay still feels comfortable inside small viewports. */
  @media (max-width: ${SMALL_MOBILE_BREAKPOINT}px) {
    width: ${(props) => (props.$size === "small" ? "64px" : "84px")};
    height: ${(props) => (props.$size === "small" ? "64px" : "84px")};
    border-radius: ${(props) => (props.$size === "small" ? "18px" : "24px")};

    svg {
      width: ${(props) => (props.$size === "small" ? "40px" : "52px")};
      height: ${(props) => (props.$size === "small" ? "40px" : "52px")};
    }
  }
`;

const LoadingDots = styled.div`
  display: flex;
  gap: 8px;
  margin-top: 1rem;
`;

const Dot = styled(motion.div)<{ $delay: number }>`
  width: 6px;
  height: 6px;
  background: ${OS_LEGAL_COLORS.accent};
  border-radius: 50%;
  animation: ${pulse} 1.4s ease-in-out infinite;
  animation-delay: ${(props) => props.$delay}s;
`;

const Message = styled(motion.h3)`
  font-size: 1.125rem;
  font-weight: 600;
  color: ${color.N10};
  margin: 0;
  margin-top: 0.5rem;
  text-align: center;
  letter-spacing: -0.01em;
`;

const SubMessage = styled(motion.p)`
  font-size: 0.875rem;
  color: ${color.N7};
  margin-top: 0.5rem;
  text-align: center;
  letter-spacing: 0.01em;
`;

const ProgressBar = styled(motion.div)`
  width: 200px;
  height: 3px;
  background: ${color.N3};
  border-radius: 100px;
  overflow: hidden;
  margin-top: 1.5rem;
`;

const ProgressFill = styled(motion.div)`
  height: 100%;
  background: linear-gradient(
    90deg,
    transparent,
    ${OS_LEGAL_COLORS.accent},
    transparent
  );
  background-size: 200% 100%;
  animation: ${shimmer} 1.5s ease-in-out infinite;
`;

const renderBrandMark = (size?: "small" | "medium" | "large") => (
  <CiteMark
    size={size === "small" ? 44 : 60}
    bracketColor={color.N10}
    nodeColor={OS_LEGAL_COLORS.accent}
    ariaLabel="cite"
  />
);

const getMessage = (type?: string, customMessage?: string) => {
  if (customMessage) return customMessage;

  switch (type) {
    case "document":
      return "Opening Document";
    case "corpus":
      return "Loading Corpus";
    case "extract":
      return "Loading Extract";
    case "auth":
      return "Securing Your Session";
    default:
      return "Loading cite";
  }
};

const getSubMessage = (type?: string) => {
  switch (type) {
    case "document":
      return "Retrieving document and annotations";
    case "corpus":
      return "Organizing your document collection";
    case "extract":
      return "Loading extracted data";
    case "auth":
      return "Verifying credentials";
    default:
      return "Preparing your workspace";
  }
};

export const ModernLoadingDisplay: React.FC<ModernLoadingDisplayProps> = ({
  type = "default",
  message,
  size = "medium",
  inline = false,
}) => {
  return (
    <AnimatePresence>
      <Container
        $inline={inline}
        $size={size}
        role="status"
        aria-live="polite"
        aria-busy="true"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.3 }}
      >
        <IconContainer $size={size}>
          <IconWrapper
            $size={size}
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            transition={{
              type: "spring",
              stiffness: 260,
              damping: 20,
              delay: 0.1,
            }}
          >
            {renderBrandMark(size)}
          </IconWrapper>
        </IconContainer>

        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
        >
          <Message>{getMessage(type, message)}</Message>
          <SubMessage>{getSubMessage(type)}</SubMessage>
        </motion.div>

        <ProgressBar
          initial={{ opacity: 0, scaleX: 0 }}
          animate={{ opacity: 1, scaleX: 1 }}
          transition={{ delay: 0.3 }}
        >
          <ProgressFill />
        </ProgressBar>

        <LoadingDots>
          <Dot $delay={0} />
          <Dot $delay={0.2} />
          <Dot $delay={0.4} />
        </LoadingDots>
      </Container>
    </AnimatePresence>
  );
};
