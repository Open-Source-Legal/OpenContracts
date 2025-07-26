import styled, { keyframes, css } from "styled-components";
import { getLuminance } from "polished";

// Helper function to ensure valid hex color
const ensureValidHexColor = (color: string): string => {
  // If it's already a valid hex color, return it
  if (/^#[0-9A-Fa-f]{6}$/.test(color)) {
    return color;
  }

  // If it's a hex without #, add it
  if (/^[0-9A-Fa-f]{6}$/.test(color)) {
    return `#${color}`;
  }

  // If it's a 3-digit hex, convert to 6-digit
  if (/^#?[0-9A-Fa-f]{3}$/.test(color)) {
    const stripped = color.replace("#", "");
    return `#${stripped[0]}${stripped[0]}${stripped[1]}${stripped[1]}${stripped[2]}${stripped[2]}`;
  }

  // Default fallback color
  return "#cccccc";
};

// Define keyframes for label animations
export const spiralOut = keyframes`
  from {
    opacity: 0;
    transform: translate(0, 0) scale(0.5);
  }
  to {
    opacity: 1;
    transform: translate(var(--x), var(--y)) scale(1);
  }
`;

// Enhanced version of the existing fadeInSlide animation
const fadeInSlide = keyframes`
  from {
    opacity: 0;
    transform: translateX(-10px) scale(0.95);
  }
  to {
    opacity: 1;
    transform: translateX(0) scale(1);
  }
`;

// Add a subtle hover animation
const pulseGlow = keyframes`
  0% {
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  }
  50% {
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  }
  100% {
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  }
`;

// Label Components
export const LabelContainer = styled.div.attrs<{
  color: string;
  "data-testid"?: string;
}>((props) => ({
  "data-testid": props["data-testid"],
}))<{ color: string }>`
  position: absolute;
  display: flex;
  align-items: center;
  gap: 8px;
  z-index: 10000;
  transform-origin: left center;
  transition: all 0.2s ease;
  padding: 4px;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.95);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  backdrop-filter: blur(4px);

  &::before {
    content: "";
    position: absolute;
    left: -12px;
    top: 50%;
    transform: translateY(-50%);
    width: 12px;
    height: 2px;
    background-color: ${(props) => ensureValidHexColor(props.color)};
    opacity: 0.8;
    transition: all 0.2s ease;
  }

  &:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);

    &::before {
      width: 16px;
      opacity: 1;
    }
  }

  /* Action button cloud is always visible but transforms on hover */
  & > div:last-child {
    opacity: 0.85;
    transform: scale(0.9);
    transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  }

  &:hover > div:last-child {
    opacity: 1;
    transform: scale(1);
  }
`;

export const Label = styled.span.attrs<{
  color: string;
  $index: number;
  "data-testid"?: string;
}>((props) => ({
  "data-testid": props["data-testid"],
}))<{ color: string; $index: number }>`
  font-size: 0.85rem;
  font-weight: 500;
  padding: 4px 8px;
  border-radius: 3px;
  background-color: ${(props) => ensureValidHexColor(props.color)};
  color: ${(props) => {
    const validColor = ensureValidHexColor(props.color);
    try {
      const luminance = getLuminance(validColor);
      return luminance > 0.5 ? "#000000" : "#FFFFFF";
    } catch (error) {
      console.warn("Error calculating luminance:", error);
      return "#000000";
    }
  }};
  white-space: nowrap;
  cursor: pointer;
  user-select: none;
  animation: ${fadeInSlide} 0.3s ease forwards;
  animation-delay: ${(props) => props.$index * 0.05}s;
  box-shadow: inset 0 0 0 1px rgba(0, 0, 0, 0.1);
  transition: all 0.2s ease;

  &:hover {
    filter: brightness(1.05);
    transform: translateY(-1px);
  }

  &:active {
    transform: translateY(0);
    filter: brightness(0.95);
  }
`;

// Styled container for the text
interface PaperContainerProps {
  maxWidth?: string;
  maxHeight?: string;
}

export const PaperContainer = styled.div<PaperContainerProps>`
  background: white;
  border-radius: 8px;
  padding: 24px 24px 96px 24px; /* Extra bottom padding for floating UI */
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
  position: relative;
  transition: all 0.2s ease;
  max-width: ${(props) => props.maxWidth || "none"};
  max-height: ${(props) => props.maxHeight || "none"};
  overflow: auto;

  /* Text rendering improvements */
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica,
    Arial, sans-serif;
  font-size: 16px;
  line-height: 1.6;
  color: #2c3e50;

  /* Proper text spacing */
  letter-spacing: -0.011em;
  word-spacing: 0.01em;

  /* Paragraph spacing */
  p {
    margin: 0 0 1.2em 0;
    &:last-child {
      margin-bottom: 0;
    }
  }

  /* Preserve whitespace but wrap text */
  white-space: pre-wrap;
  word-break: normal;

  /* Smooth scrolling */
  scroll-behavior: smooth;

  /* Better text rendering */
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  text-rendering: optimizeLegibility;

  &:hover {
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
  }
`;
