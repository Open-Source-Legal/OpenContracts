import { motion } from "framer-motion";
import styled from "styled-components";
import {
  OS_LEGAL_COLORS,
  accentAlpha,
} from "../../../assets/configurations/osLegalStyles";
import {
  FOCUS_RING,
  RADIUS,
  SHADOW,
} from "../../../assets/configurations/designTokens";

/**
 * The conversation-list header. Hosts the "Chat" title and the inline filter
 * controls in a single anchored row — no stray right-floating icon band.
 * A soft downward shadow replaces the old hairline border.
 */
export const FilterContainer = styled.div`
  position: sticky;
  top: 0;
  z-index: 10;
  background: rgba(255, 255, 255, 0.96);
  backdrop-filter: blur(10px);
  padding: 0.875rem 1.125rem;
  box-shadow: 0 1px 8px rgba(15, 23, 42, 0.05);
  display: flex;
  align-items: center;
  gap: 0.5rem;
  width: 100%;
`;

/** "Chat" title — anchors the header so the controls have a sibling. */
export const FilterTitle = styled.h2`
  margin: 0;
  flex: 1;
  min-width: 0;
  font-size: 1rem;
  font-weight: 650;
  letter-spacing: -0.01em;
  color: ${OS_LEGAL_COLORS.textPrimary};
`;

export const IconButton = styled(motion.button)<{ $isActive?: boolean }>`
  width: 36px;
  height: 36px;
  border-radius: ${RADIUS.sm};
  border: none;
  background: ${(props) =>
    props.$isActive
      ? OS_LEGAL_COLORS.accentSurface
      : OS_LEGAL_COLORS.surfaceHover};
  color: ${(props) =>
    props.$isActive ? OS_LEGAL_COLORS.accent : OS_LEGAL_COLORS.textTertiary};
  box-shadow: ${(props) =>
    props.$isActive
      ? `inset 0 0 0 1px ${accentAlpha(0.25)}`
      : "inset 0 0 0 1px rgba(15, 23, 42, 0.05)"};
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  flex-shrink: 0;
  transition: background 0.18s ease, color 0.18s ease, box-shadow 0.18s ease;

  &:hover {
    background: ${(props) =>
      props.$isActive ? OS_LEGAL_COLORS.accentSurface : "white"};
    color: ${(props) =>
      props.$isActive ? OS_LEGAL_COLORS.accentHover : OS_LEGAL_COLORS.accent};
    box-shadow: ${(props) =>
      props.$isActive
        ? `inset 0 0 0 1px ${accentAlpha(0.35)}, ${SHADOW.subtle}`
        : `inset 0 0 0 1px rgba(15, 23, 42, 0.1), ${SHADOW.subtle}`};
  }

  &:active {
    box-shadow: ${(props) =>
      props.$isActive
        ? `inset 0 0 0 1px ${accentAlpha(0.35)}`
        : "inset 0 0 0 1px rgba(15, 23, 42, 0.1)"};
  }

  svg {
    width: 18px;
    height: 18px;
    stroke-width: 2;
  }
`;

export const ExpandingInput = styled(motion.div)`
  position: relative;
  overflow: hidden;
  flex: 1 1 0;
  min-width: 0;

  input {
    width: 100%;
    box-sizing: border-box;
    padding: 0.5rem 0.875rem;
    border: none;
    border-radius: ${RADIUS.sm};
    font-size: 0.875rem;
    font-family: inherit;
    color: ${OS_LEGAL_COLORS.textPrimary};
    background: ${OS_LEGAL_COLORS.surfaceHover};
    box-shadow: inset 0 0 0 1px rgba(15, 23, 42, 0.06);
    transition: background 0.18s ease, box-shadow 0.18s ease;

    &:focus {
      outline: none;
      background: white;
      box-shadow: inset 0 0 0 1px ${OS_LEGAL_COLORS.accent}, ${FOCUS_RING};
    }

    &::placeholder {
      color: ${OS_LEGAL_COLORS.textMuted};
    }
  }
`;

export const DatePickerExpanded = styled(motion.div)`
  position: absolute;
  top: 100%;
  right: 0;
  margin-top: 0.5rem;
  background: white;
  border-radius: ${RADIUS.md};
  box-shadow: ${SHADOW.menu};
  padding: 1rem;
  z-index: 20;
  display: flex;
  flex-direction: column;
  gap: 1rem;

  input {
    padding: 0.5rem 0.625rem;
    border: none;
    border-radius: 8px;
    font-size: 0.875rem;
    font-family: inherit;
    color: ${OS_LEGAL_COLORS.textPrimary};
    background: ${OS_LEGAL_COLORS.surfaceHover};
    box-shadow: inset 0 0 0 1px rgba(15, 23, 42, 0.06);
    transition: box-shadow 0.18s ease;

    &:focus {
      outline: none;
      background: white;
      box-shadow: inset 0 0 0 1px ${OS_LEGAL_COLORS.accent}, ${FOCUS_RING};
    }
  }

  .date-inputs {
    display: flex;
    gap: 1rem;
  }

  .date-actions {
    display: flex;
    justify-content: flex-end;
    gap: 0.5rem;

    button {
      padding: 0.5rem 1rem;
      border-radius: 8px;
      border: none;
      font-size: 0.875rem;
      cursor: pointer;
      transition: all 0.2s ease;

      &.cancel {
        background: ${OS_LEGAL_COLORS.surfaceLight};
        color: ${OS_LEGAL_COLORS.textTertiary};

        &:hover {
          background: ${OS_LEGAL_COLORS.border};
        }
      }

      &.apply {
        background: ${OS_LEGAL_COLORS.accent};
        color: white;

        &:hover {
          background: ${OS_LEGAL_COLORS.accentHover};
        }
      }
    }
  }
`;
