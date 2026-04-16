import React from "react";
import styled, { keyframes } from "styled-components";
import { motion, AnimatePresence } from "framer-motion";
import {
  FileText,
  Folder,
  Lock,
  Database,
  BookOpen,
  Archive,
} from "lucide-react";
import { color } from "../../theme/colors";
import {
  OS_LEGAL_COLORS,
  accentAlpha,
} from "../../assets/configurations/osLegalStyles";
import osLegalLogo from "../../assets/images/os_legal_FullColor.png";

interface ModernLoadingDisplayProps {
  type?: "document" | "corpus" | "extract" | "auth" | "default";
  message?: string;
  fullScreen?: boolean;
  size?: "small" | "medium" | "large";
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

const rotate = keyframes`
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
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

const Container = styled(motion.div)<{ $fullScreen?: boolean; $size?: string }>`
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: ${(props) => (props.$size === "small" ? "2rem" : "3rem")};
  position: fixed;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  z-index: 9999;
  ${(props) =>
    props.$fullScreen &&
    `
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    transform: none;
    background: linear-gradient(135deg, ${OS_LEGAL_COLORS.background} 0%, #f0fdfa 100%);
    backdrop-filter: blur(12px);
  `}
`;

const IconContainer = styled(motion.div)<{ $type?: string }>`
  position: relative;
  width: 100px;
  height: 100px;
  margin-bottom: 2rem;

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
const IconWrapper = styled(motion.div)<{ $type?: string }>`
  position: relative;
  width: 100px;
  height: 100px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(145deg, ${color.white} 0%, #f0fdfa 100%);
  /* Squircle-like border radius for more organic feel */
  border-radius: 28px;
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

  img {
    width: 68px;
    height: 68px;
    object-fit: contain;
    position: relative;
    z-index: 1;
  }

  svg {
    width: 40px;
    height: 40px;
    color: ${OS_LEGAL_COLORS.accent};
    position: relative;
    z-index: 1;
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

const getIcon = (type?: string, useOsLogo: boolean = true) => {
  if (useOsLogo) {
    return <img src={osLegalLogo} alt="OpenContracts" />;
  }

  switch (type) {
    case "document":
      return <FileText />;
    case "corpus":
      return <Archive />;
    case "extract":
      return <Database />;
    case "auth":
      return <Lock />;
    default:
      return <Database />;
  }
};

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
      return "Loading OpenContracts";
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
  fullScreen = false,
  size = "medium",
}) => {
  return (
    <AnimatePresence>
      <Container
        $fullScreen={fullScreen}
        $size={size}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.3 }}
      >
        <IconContainer $type={type}>
          <IconWrapper
            $type={type}
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            transition={{
              type: "spring",
              stiffness: 260,
              damping: 20,
              delay: 0.1,
            }}
          >
            {getIcon(type)}
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
