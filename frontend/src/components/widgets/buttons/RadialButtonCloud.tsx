import React, { useState, useRef, useEffect } from "react";
import styled, { createGlobalStyle, keyframes } from "styled-components";
import {
  Button,
  Icon as SemanticIcon,
  SemanticICONS,
  ButtonProps,
  Modal,
} from "semantic-ui-react";
import { getLuminance } from "polished";
import useWindowDimensions from "../../hooks/WindowDimensionHook";
import { MOBILE_VIEW_BREAKPOINT } from "../../../assets/configurations/constants";

const pulse = keyframes`
  0% {
    box-shadow: 0 0 0 0 rgba(0, 255, 0, 0.7);
  }
  70% {
    box-shadow: 0 0 0 10px rgba(0, 255, 0, 0);
  }
  100% {
    box-shadow: 0 0 0 0 rgba(0, 255, 0, 0);
  }
`;

interface PulsingDotProps {
  $backgroundColor: string;
}

const PulsingDot = styled.div<PulsingDotProps>`
  width: 12px;
  height: 12px;
  background-color: ${(props) => props.$backgroundColor};
  border-radius: 50%;
  animation: ${pulse} 2s infinite;
  cursor: pointer;
  position: relative;

  &::before {
    content: "";
    position: absolute;
    top: -10px;
    left: -10px;
    right: -10px;
    bottom: -10px;
    border-radius: 50%;
  }
`;

const CloudContainer = styled.div`
  position: absolute;
  top: -60px;
  left: -60px;
  width: 120px;
  height: 120px;
  display: flex;
  align-items: center;
  justify-content: center;
  pointer-events: auto;
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

    // Calculate the next t value based on the desired arc length
    // The arc length of a spiral from 0 to t is approximately (a/2) * (t^2)
    // So, we solve for the next t that gives us an additional arc length of 'spacingAlong'
    const currentArcLength = (a / 2) * (t * t);
    const nextArcLength = currentArcLength + spacingAlong;
    t = Math.sqrt((2 * nextArcLength) / a);
  }

  // Return only the positions after skipping the specified number
  return positions.slice(skipCount);
}

interface CloudButtonProps extends ButtonProps {
  $delay: number;
  $position: ButtonPosition;
}

const moveOut = (props: CloudButtonProps) => keyframes`
    from {
      opacity: 0;
      transform: translate(0, 0);
    }
    to {
      opacity: 1;
      transform: translate(
        ${props.$position.x}px,
        ${props.$position.y}px
      );
    }
  `;

const CloudButton = styled(Button)<CloudButtonProps>`
  position: absolute;
  opacity: 0;
  animation: ${moveOut} 0.5s forwards;
  animation-delay: ${(props) => props.$delay}s;
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

  const { height, width } = useWindowDimensions();
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
    console.log("handleButtonClick", btn);
    if (btn.protected_message) {
      console.log("Should show confirm!");
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
  const a = 6; // Controls the growth rate of the spiral
  const spacingAlongPercent = width <= MOBILE_VIEW_BREAKPOINT ? 8 : 3; // 5% of the container height
  const spacingAlong = (height * spacingAlongPercent) / 100;
  const skipCount = 2; // Number of inner positions to skip

  // Calculate button positions
  const buttonPositions = calculateButtonPositions(
    numButtons,
    a,
    spacingAlong,
    skipCount
  );

  // Calculate dot color with good contrast
  /**
   * Returns an appropriate contrast color based on the background color.
   * The bgColor parameter must be in hex, rgb, rgba, hsl or hsla format.
   *
   * @param bgColor - A string representing the background color.
   * @returns A contrast color in hex format.
   */
  const getContrastColor = (bgColor: string): string => {
    // console.log("getContrastColor called with:", {
    //   value: bgColor,
    //   type: typeof bgColor,
    //   isNull: bgColor === null,
    //   isUndefined: bgColor === undefined,
    // });

    // Handle undefined, null, or empty string
    if (!bgColor) {
      // console.warn("No background color provided or empty value:", bgColor);
      return "#00ff00";
    }

    // If it looks like a hex color without the #, add it
    if (/^[A-Fa-f0-9]{3,6}$/.test(bgColor)) {
      bgColor = "#" + bgColor;
      // console.log("Added # prefix to hex color:", bgColor);
    }

    // Log the validation results for each format
    const validationResults = {
      hex: /^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$/.test(bgColor),
      rgb: /^rgb\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*\)$/.test(bgColor),
      rgba: /^rgba\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*,\s*[\d.]+\s*\)$/.test(
        bgColor
      ),
      hsl: /^hsl\(\s*\d+\s*,\s*\d+%?\s*,\s*\d+%?\s*\)$/.test(bgColor),
      hsla: /^hsla\(\s*\d+\s*,\s*\d+%?\s*,\s*\d+%?\s*,\s*[\d.]+\s*\)$/.test(
        bgColor
      ),
    };

    // If the color isn't in a valid format, return default
    if (!Object.values(validationResults).some((result) => result)) {
      // console.warn(`Invalid color format. Color string: "${bgColor}"`);
      // console.warn("Color string length:", bgColor.length);
      // console.warn(
      //   "Color string characters:",
      //   Array.from(bgColor).map((c) => `'${c}'(${c.charCodeAt(0)})`)
      // );
      return "#00ff00";
    }

    try {
      // console.log("Attempting to calculate luminance for color:", bgColor);
      const luminance = getLuminance(bgColor);
      // console.log("Calculated luminance:", luminance);
      return luminance > 0.5 ? "#00aa00" : "#00ff00";
    } catch (error: any) {
      // console.error("Luminance calculation error:", {
      //   color: bgColor,
      //   error: error.message,
      //   stack: error.stack,
      // });
      return "#00ff00";
    }
  };

  // console.log("Component render - Parent background color:", {
  //   value: parentBackgroundColor,
  //   type: typeof parentBackgroundColor,
  // });
  const dotColor = getContrastColor(parentBackgroundColor);
  // console.log("Final dot color:", dotColor);

  return (
    <div style={{ position: "relative", display: "inline-block" }}>
      <PulsingDot
        className="pulsing-dot"
        onMouseEnter={() => setCloudVisible(true)}
        $backgroundColor={dotColor}
      />
      <GlobalStyle />
      {cloudVisible && (
        <CloudContainer ref={cloudRef}>
          {buttonList.map((btn, index) => (
            <CloudButton
              key={index}
              color={btn.color as any}
              icon
              circular
              size="mini"
              onClick={(e: React.MouseEvent<HTMLButtonElement>) => {
                e.stopPropagation();
                handleButtonClick(btn);
              }}
              title={btn.tooltip}
              $delay={index * 0.1}
              $position={buttonPositions[index]}
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
