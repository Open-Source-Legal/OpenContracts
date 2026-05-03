import React from "react";
import styled, { keyframes } from "styled-components";
import { Z_INDEX } from "../../assets/configurations/constants";

/* ============================================================================
 * Animations
 * ========================================================================== */

const spin = keyframes`
  0% {
    transform: rotate(0deg);
  }
  100% {
    transform: rotate(360deg);
  }
`;

const fadeIn = keyframes`
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
`;

/* ============================================================================
 * Styled Components
 * ========================================================================== */

const OverlayContainer = styled.div<{ $active: boolean; $inverted?: boolean }>`
  position: absolute;
  inset: 0;
  display: ${(props) => (props.$active ? "flex" : "none")};
  align-items: center;
  justify-content: center;
  background: ${(props) =>
    props.$inverted ? "rgba(0, 0, 0, 0.85)" : "rgba(255, 255, 255, 0.85)"};
  backdrop-filter: blur(4px);
  border-radius: inherit;
  overflow: hidden;
  z-index: ${Z_INDEX.OVERLAY};
  animation: ${fadeIn} 0.2s ease-in-out;
`;

const LoaderContainer = styled.div`
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1rem;
`;

const Spinner = styled.div<{
  $size?: "small" | "medium" | "large";
  $inverted?: boolean;
}>`
  width: ${(props) => {
    switch (props.$size) {
      case "small":
        return "2rem";
      case "large":
        return "4rem";
      default:
        return "3rem";
    }
  }};
  height: ${(props) => {
    switch (props.$size) {
      case "small":
        return "2rem";
      case "large":
        return "4rem";
      default:
        return "3rem";
    }
  }};
  border: 3px solid
    ${(props) =>
      props.$inverted ? "rgba(255, 255, 255, 0.2)" : "rgba(0, 0, 0, 0.1)"};
  border-top-color: ${(props) =>
    props.$inverted ? "rgba(255, 255, 255, 0.9)" : "rgba(0, 0, 0, 0.6)"};
  border-radius: 50%;
  animation: ${spin} 0.8s linear infinite;
`;

const LoaderText = styled.div<{ $inverted?: boolean }>`
  color: ${(props) =>
    props.$inverted ? "rgba(255, 255, 255, 0.95)" : "rgba(0, 0, 0, 0.87)"};
  font-size: 1rem;
  font-weight: 500;
  text-align: center;
  max-width: 300px;
`;

/* ============================================================================
 * Component
 * ========================================================================== */

interface LoadingOverlayProps {
  active: boolean;
  inverted?: boolean;
  size?: "small" | "medium" | "large";
  content?: string | React.ReactNode;
}

export const LoadingOverlay: React.FC<LoadingOverlayProps> = ({
  active,
  inverted = false,
  size = "medium",
  content,
}) => {
  return (
    <OverlayContainer $active={active} $inverted={inverted}>
      <LoaderContainer>
        <Spinner $size={size} $inverted={inverted} />
        {content && <LoaderText $inverted={inverted}>{content}</LoaderText>}
      </LoaderContainer>
    </OverlayContainer>
  );
};

export default LoadingOverlay;
