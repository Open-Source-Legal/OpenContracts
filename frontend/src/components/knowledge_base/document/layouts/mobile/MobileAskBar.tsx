import React, { useState } from "react";
import styled from "styled-components";
import { Search, Send } from "lucide-react";
import { OS_LEGAL_COLORS } from "../../../../../assets/configurations/osLegalStyles";

export interface MobileAskBarProps {
  /** Fired when the user focuses the bar — the layout opens the Chat sheet. */
  onActivate: () => void;
  /** Fired when the user submits non-empty text. */
  onSubmit: (text: string) => void;
}

const Bar = styled.div`
  flex-shrink: 0;
  margin: 8px 12px;
  height: 40px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 6px 0 12px;
  border: 1.5px solid ${OS_LEGAL_COLORS.accent};
  border-radius: 20px;
  background: ${OS_LEGAL_COLORS.successSurface};
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
    color: ${OS_LEGAL_COLORS.accent};
  }
`;

const SendButton = styled.button`
  flex-shrink: 0;
  width: 30px;
  height: 30px;
  border: none;
  border-radius: 50%;
  background: ${OS_LEGAL_COLORS.accent};
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
`;

export const MobileAskBar: React.FC<MobileAskBarProps> = ({
  onActivate,
  onSubmit,
}) => {
  const [text, setText] = useState("");
  const submit = () => {
    const trimmed = text.trim();
    if (!trimmed) return;
    onSubmit(trimmed);
    setText("");
  };
  return (
    <Bar>
      <Search size={16} color={OS_LEGAL_COLORS.accent} />
      <Input
        placeholder="Ask anything about this document…"
        value={text}
        onFocus={onActivate}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") submit();
        }}
      />
      <SendButton aria-label="Send" onClick={submit}>
        <Send size={15} />
      </SendButton>
    </Bar>
  );
};
