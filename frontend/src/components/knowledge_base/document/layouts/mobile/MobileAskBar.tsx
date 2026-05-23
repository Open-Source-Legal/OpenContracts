import React, { useState } from "react";
import styled from "styled-components";
import { History, Search, Send } from "lucide-react";
import { OS_LEGAL_COLORS } from "../../../../../assets/configurations/osLegalStyles";
import { MOBILE_FOCUS_RING, MOBILE_RADIUS, MOBILE_SHADOW } from "./mobileTheme";

export interface MobileAskBarProps {
  /** Fired when the user submits non-empty text. */
  onSubmit: (text: string) => void;
  /**
   * Optional handler that opens the conversation list. When provided, a small
   * history icon button is rendered between the input and the send button so
   * users can still reach prior conversations now that focusing the bar no
   * longer opens the chat sheet.
   */
  onOpenHistory?: () => void;
}

/**
 * A crisp white elevated input — reads as a premium tappable field, not a
 * banner. Teal is reserved for the focus ring and the send button.
 */
const Bar = styled.div`
  flex-shrink: 0;
  margin: 10px 12px;
  height: 46px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 6px 0 14px;
  border-radius: ${MOBILE_RADIUS.pill};
  background: ${OS_LEGAL_COLORS.surface};
  box-shadow: ${MOBILE_SHADOW.raised};
  transition: box-shadow 0.18s ease;

  &:focus-within {
    box-shadow: ${MOBILE_SHADOW.raised}, ${MOBILE_FOCUS_RING};
  }
`;

const Input = styled.input`
  flex: 1;
  min-width: 0;
  border: none;
  background: transparent;
  font-size: 14px;
  color: ${OS_LEGAL_COLORS.textPrimary};
  outline: none;
  &::placeholder {
    color: ${OS_LEGAL_COLORS.textSecondary};
  }
`;

const SendButton = styled.button`
  flex-shrink: 0;
  width: 34px;
  height: 34px;
  border: none;
  border-radius: ${MOBILE_RADIUS.pill};
  background: ${OS_LEGAL_COLORS.accent};
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  box-shadow: 0 2px 6px rgba(15, 118, 110, 0.32);
  -webkit-tap-highlight-color: transparent;
  transition: transform 0.12s ease, background 0.16s ease;

  &:active {
    transform: scale(0.9);
    background: ${OS_LEGAL_COLORS.accentHover};
  }
`;

const HistoryButton = styled.button`
  flex-shrink: 0;
  width: 34px;
  height: 34px;
  border: none;
  border-radius: ${MOBILE_RADIUS.pill};
  background: transparent;
  color: ${OS_LEGAL_COLORS.textSecondary};
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
  transition: background 0.16s ease, color 0.16s ease;

  &:hover {
    background: ${OS_LEGAL_COLORS.surfaceLight};
    color: ${OS_LEGAL_COLORS.textPrimary};
  }

  &:active {
    background: ${OS_LEGAL_COLORS.surfaceHover};
  }
`;

export const MobileAskBar: React.FC<MobileAskBarProps> = ({
  onSubmit,
  onOpenHistory,
}) => {
  const [text, setText] = useState("");
  const submit = () => {
    const trimmed = text.trim();
    if (!trimmed) return;
    onSubmit(trimmed);
    setText("");
  };
  return (
    <Bar data-testid="mobile-ask-bar">
      <Search size={16} color={OS_LEGAL_COLORS.textSecondary} />
      <Input
        placeholder="Ask anything about this document…"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") submit();
        }}
        data-testid="mobile-ask-bar-input"
      />
      {onOpenHistory && (
        <HistoryButton
          aria-label="Open conversation history"
          onClick={onOpenHistory}
          data-testid="mobile-ask-bar-history"
        >
          <History size={16} />
        </HistoryButton>
      )}
      <SendButton
        aria-label="Send"
        onClick={submit}
        data-testid="mobile-ask-bar-send"
      >
        <Send size={16} />
      </SendButton>
    </Bar>
  );
};
