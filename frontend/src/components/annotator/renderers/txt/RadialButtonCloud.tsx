// src/RadialButtonCloud.tsx
import React, { useState, useRef, useEffect } from "react";
import styled, { createGlobalStyle, css, keyframes } from "styled-components";
import {
  Button,
  Icon as SemanticIcon,
  SemanticICONS,
  Modal,
} from "semantic-ui-react";
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
  return "#00b5ad"; // Teal as default
};

// Calculate dot color with good contrast
const getContrastColor = (bgColor: string): string => {
  const validColor = ensureValidHexColor(bgColor);
  try {
    const luminance = getLuminance(validColor);
    return luminance > 0.5 ? "#000000" : "#ffffff";
  } catch (error) {
    console.warn(`Error calculating contrast color:`, error);
    return "#000000"; // fallback to black
  }
};

const pulse = keyframes`
  0% {
    box-shadow: 0 0 0 0 rgba(0, 176, 155, 0.4);
    transform: scale(1);
  }
  50% {
    box-shadow: 0 0 0 8px rgba(0, 176, 155, 0);
    transform: scale(1.1);
  }
  100% {
    box-shadow: 0 0 0 0 rgba(0, 176, 155, 0);
    transform: scale(1);
  }
`;

interface PulsingDotProps {
  backgroundColor: string;
  isVisible: boolean;
}

const PulsingDot = styled.div<PulsingDotProps>`
  width: 16px;
  height: 16px;
  background-color: ${(props) => ensureValidHexColor(props.backgroundColor)};
  border-radius: 50%;
  cursor: pointer;
  position: relative;
  opacity: ${(props) => (props.isVisible ? 0.9 : 0.4)};
  transform-origin: center;
  transition: all 0.2s ease;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);

  &:hover {
    animation: ${pulse} 2s infinite;
    opacity: 1;
    transform: scale(1.1);
  }

  &::before {
    content: "";
    position: absolute;
    top: -6px;
    left: -6px;
    right: -6px;
    bottom: -6px;
    border-radius: 50%;
    background: radial-gradient(
      circle at center,
      rgba(255, 255, 255, 0.8) 0%,
      rgba(255, 255, 255, 0) 70%
    );
    opacity: 0;
    transition: opacity 0.2s ease;
  }

  &:hover::before {
    opacity: 1;
  }
`;

const CloudContainer = styled.div`
  position: absolute;
  top: -70px;
  left: -70px;
  width: 140px;
  height: 140px;
  display: flex;
  align-items: center;
  justify-content: center;
  pointer-events: auto;
  z-index: 10001;
`;

interface ButtonPosition {
  x: number;
  y: number;
}

function calculateButtonPositions(
  n: number,
  a: number,
  spacingAlong: number,
  skipCount: number = 2
): ButtonPosition[] {
  const positions: ButtonPosition[] = [];
  let t = 0;

  for (let i = 0; i < n + skipCount; i++) {
    const r = a * t;
    positions.push({
      x: r * Math.cos(t),
      y: r * Math.sin(t),
    });

    const currentArcLength = (a / 2) * (t * t);
    const nextArcLength = currentArcLength + spacingAlong;
    t = Math.sqrt((2 * nextArcLength) / a);
  }

  return positions.slice(skipCount);
}

interface CloudButtonProps {
  delay: number;
  position: ButtonPosition;
  backgroundColor: string;
}

const moveOut = keyframes`
  from {
    opacity: 0;
    transform: translate(0, 0) scale(0.8);
  }
  to {
    opacity: 1;
    transform: translate(var(--x), var(--y)) scale(1);
  }
`;

const CloudButton = styled(Button).attrs<CloudButtonProps>((props) => {
  const validColor = ensureValidHexColor(props.backgroundColor);
  return {
    style: {
      position: "absolute",
      opacity: 0,
      "--x": `${props.position.x}px`,
      "--y": `${props.position.y}px`,
      backgroundColor: validColor,
      color: getContrastColor(validColor),
    },
  };
})<CloudButtonProps>`
  ${(props) => css`
    animation: ${moveOut} 0.4s cubic-bezier(0.4, 0, 0.2, 1) forwards;
    animation-delay: ${props.delay}s;
  `}
  padding: 8px !important;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15) !important;
  transition: all 0.2s ease !important;

  &:hover {
    transform: translate(var(--x), var(--y)) scale(1.1) !important;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2) !important;
  }

  &:active {
    transform: translate(var(--x), var(--y)) scale(0.95) !important;
  }

  i.icon {
    margin: 0 !important;
    font-size: 1rem !important;
  }
`;

const GlobalStyle = createGlobalStyle`
  .confirm-modal-container.ui.page.modals.dimmer.transition.visible.active {
    z-index: 20000 !important;
  }

  #ConfirmModal {
    z-index: 20001 !important;
  }
`;

export interface CloudButtonItem {
  name: SemanticICONS;
  color: string;
  tooltip: string;
  protected_message?: string | null;
  onClick: () => void;
}

interface RadialButtonCloudProps {
  parentBackgroundColor: string;
  actions: CloudButtonItem[];
}

const RadialButtonCloud: React.FC<RadialButtonCloudProps> = ({
  parentBackgroundColor,
  actions: buttonList,
}) => {
  const [cloudVisible, setCloudVisible] = useState(false);
  const [confirmModal, setConfirmModal] = useState<{
    open: boolean;
    message: string;
    onConfirm: () => void;
  }>({ open: false, message: "", onConfirm: () => {} });

  const cloudRef = useRef<HTMLDivElement | null>(null);

  const handleClickOutside = (event: MouseEvent) => {
    if (
      cloudRef.current &&
      !cloudRef.current.contains(event.target as Node) &&
      !(event.target as Element).closest(".pulsing-dot")
    ) {
      setCloudVisible(false);
    }
  };

  const handleButtonClick = (btn: CloudButtonItem) => {
    if (btn.protected_message) {
      setConfirmModal({
        open: true,
        message: btn.protected_message,
        onConfirm: () => {
          btn.onClick();
          setCloudVisible(false);
        },
      });
    } else {
      btn.onClick();
      setCloudVisible(false);
    }
  };

  useEffect(() => {
    if (cloudVisible) {
      document.addEventListener("mousedown", handleClickOutside);
    } else {
      document.removeEventListener("mousedown", handleClickOutside);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [cloudVisible]);

  const numButtons = buttonList.length;
  const a = 6;
  const spacingAlong = 50;
  const skipCount = 2;

  const buttonPositions = calculateButtonPositions(
    numButtons,
    a,
    spacingAlong,
    skipCount
  );

  const dotColor = ensureValidHexColor(parentBackgroundColor);

  const buttonColors = [
    "#00B5AD", // Teal
    "#2185D0", // Blue
    "#21BA45", // Green
    "#DB2828", // Red
    "#A333C8", // Purple
  ];

  return (
    <div style={{ position: "relative", display: "inline-block" }}>
      <PulsingDot
        className="pulsing-dot"
        onMouseEnter={() => setCloudVisible(true)}
        backgroundColor={dotColor}
        isVisible={cloudVisible}
      />
      <GlobalStyle />
      {cloudVisible && (
        <CloudContainer ref={cloudRef}>
          {buttonList.map((btn, index) => (
            <CloudButton
              key={index}
              icon
              circular
              size="small"
              onClick={(e: React.MouseEvent<HTMLButtonElement>) => {
                e.stopPropagation();
                handleButtonClick(btn);
              }}
              title={btn.tooltip}
              delay={index * 0.1}
              position={buttonPositions[index]}
              backgroundColor={buttonColors[index % buttonColors.length]}
            >
              <SemanticIcon name={btn.name} />
            </CloudButton>
          ))}
        </CloudContainer>
      )}
      <Modal
        id="ConfirmModal"
        size="mini"
        className="confirm-modal-container"
        open={confirmModal.open}
        onClose={() => setConfirmModal({ ...confirmModal, open: false })}
      >
        <Modal.Content>
          <p>{confirmModal.message}</p>
        </Modal.Content>
        <Modal.Actions>
          <Button
            negative
            onClick={() => {
              setConfirmModal({ ...confirmModal, open: false });
              setCloudVisible(false);
            }}
          >
            No
          </Button>
          <Button
            positive
            onClick={() => {
              confirmModal.onConfirm();
              setConfirmModal({ ...confirmModal, open: false });
            }}
          >
            Yes
          </Button>
        </Modal.Actions>
      </Modal>
    </div>
  );
};

export default RadialButtonCloud;
