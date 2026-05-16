import React, { useRef, useEffect } from "react";
import { Send, History, Sparkles, Search, MessageSquare } from "lucide-react";
import {
  ChatBarContainer,
  ChatBarWrapper,
  ChatInput,
  ChatActions,
  ChatButton,
  QuickActions,
  QuickActionChip,
} from "./styles";
import { useChatMentionPicker } from "../../../hooks/useChatMentionPicker";

export interface InlineChatBarProps {
  /** Current query value */
  value: string;
  /** Callback when query changes */
  onChange: (value: string) => void;
  /** Callback when form is submitted */
  onSubmit: (query: string) => void;
  /** Callback to view conversation history */
  onViewHistory: () => void;
  /** Placeholder text */
  placeholder?: string;
  /** Whether to auto-focus the input */
  autoFocus?: boolean;
  /** Whether to show quick action chips */
  showQuickActions?: boolean;
  /** Test ID for the component */
  testId?: string;
  /**
   * Optional corpus the bar is bound to. When provided, typing ``@`` opens
   * the rich-mention agent picker (same wiring as ChatTray / CorpusChat)
   * scoped to global agents + this corpus's agents. Omit for chat bars
   * that aren't anchored to a corpus context.
   */
  corpusId?: string;
}

/**
 * InlineChatBar - An inline chat input bar for querying the corpus
 *
 * Features:
 * - Expandable textarea for multi-line queries
 * - Send and History action buttons
 * - Optional quick action chips for common queries
 * - Keyboard shortcuts (Enter to submit, Shift+Enter for newline)
 */
export const InlineChatBar: React.FC<InlineChatBarProps> = ({
  value,
  onChange,
  onSubmit,
  onViewHistory,
  placeholder = "Ask a question about this corpus...",
  autoFocus = false,
  showQuickActions = true,
  testId = "inline-chat-bar",
  corpusId,
}) => {
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Rich-mention agent delegation: share the same wiring as ChatTray and
  // CorpusChat so users can ``@<agent>`` from the corpus landing bar. The
  // hook is a no-op when ``corpusId`` is undefined (no @ trigger fires
  // because the popover gate also needs ``mention.isOpen``, but the
  // agent search runs harmlessly with no results), so callers that don't
  // pass a corpus don't pay a UX cost.
  const {
    handleValueChange: handleMentionValueChange,
    popoverNode: mentionPopover,
  } = useChatMentionPicker({
    textareaRef: inputRef,
    corpusId,
    onValueChange: onChange,
  });

  useEffect(() => {
    if (autoFocus && inputRef.current) {
      // Delay focus to ensure DOM is ready
      setTimeout(() => inputRef.current?.focus(), 150);
    }
  }, [autoFocus]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (value.trim()) {
      onSubmit(value.trim());
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Submit on Enter without Shift
    if (e.key === "Enter" && !e.shiftKey && value.trim()) {
      e.preventDefault();
      onSubmit(value.trim());
    }
  };

  const handleQuickAction = (query: string) => {
    onChange(query);
    // Focus the input after setting the query
    setTimeout(() => inputRef.current?.focus(), 50);
  };

  const quickActions = [
    {
      label: "Summarize",
      query: "Summarize the key points of this corpus",
      icon: Sparkles,
    },
    { label: "Search", query: "Find documents related to ", icon: Search },
    {
      label: "Analyze",
      query: "What are the main themes in this corpus?",
      icon: MessageSquare,
    },
  ];

  return (
    <ChatBarContainer
      data-testid={testId}
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: 0.2 }}
    >
      <form onSubmit={handleSubmit}>
        {mentionPopover}
        <ChatBarWrapper>
          <ChatInput
            ref={inputRef}
            value={value}
            onChange={(e) => {
              const next = e.target.value;
              onChange(next);
              // Forward caret + value to the mention trigger so ``@<word>``
              // can open the agent picker. The hook is a no-op without an
              // active trigger fragment, so non-mention typing is free.
              const caret = e.target.selectionStart ?? next.length;
              handleMentionValueChange(next, caret);
            }}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            rows={1}
            data-testid={`${testId}-input`}
          />
          <ChatActions>
            <ChatButton
              type="button"
              onClick={onViewHistory}
              title="View conversation history"
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              data-testid={`${testId}-history-btn`}
            >
              <History />
            </ChatButton>
            <ChatButton
              type="submit"
              $primary
              disabled={!value.trim()}
              title="Send message"
              whileHover={value.trim() ? { scale: 1.05 } : {}}
              whileTap={value.trim() ? { scale: 0.95 } : {}}
              data-testid={`${testId}-send-btn`}
            >
              <Send />
            </ChatButton>
          </ChatActions>
        </ChatBarWrapper>
      </form>

      {showQuickActions && (
        <QuickActions data-testid={`${testId}-quick-actions`}>
          {quickActions.map((action) => (
            <QuickActionChip
              key={action.label}
              type="button"
              onClick={() => handleQuickAction(action.query)}
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
            >
              <action.icon size={14} />
              {action.label}
            </QuickActionChip>
          ))}
        </QuickActions>
      )}
    </ChatBarContainer>
  );
};
