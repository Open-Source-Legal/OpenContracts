import { useCallback, useState } from "react";

interface SelectedAgent {
  slug: string;
  name: string;
  url: string;
}

export interface AgentMentionTriggerState {
  isOpen: boolean;
  fragment: string;
  /** Call from textarea onChange / onSelectionChange. */
  onValueChange: (value: string, caret: number) => void;
  /** User picked an agent from the popover. Returns the patched value+caret. */
  onSelect: (agent: SelectedAgent) => { value: string; caretPos: number };
  /** User pressed Escape / clicked outside. */
  onDismiss: () => void;
}

export function useAgentMentionTrigger(): AgentMentionTriggerState {
  const [isOpen, setIsOpen] = useState(false);
  const [fragment, setFragment] = useState("");
  const [caretPos, setCaretPos] = useState(0);
  const [triggerStart, setTriggerStart] = useState<number | null>(null);
  const [currentValue, setCurrentValue] = useState("");

  const onValueChange = useCallback((value: string, caret: number) => {
    setCurrentValue(value);
    setCaretPos(caret);
    // Walk back from caret to find an @ that begins a "word"
    let start = caret - 1;
    while (start >= 0) {
      const ch = value[start];
      if (ch === "@") {
        const before = start > 0 ? value[start - 1] : "";
        // Valid trigger only when @ is at start-of-text or follows whitespace
        if (before === "" || /\s/.test(before)) {
          const frag = value.slice(start + 1, caret);
          // Fragment is empty (just typed @) or pure word-chars
          if (frag.length === 0 || /^[A-Za-z0-9_-]+$/.test(frag)) {
            setIsOpen(true);
            setFragment(frag);
            setTriggerStart(start);
            return;
          }
        }
        break;
      }
      if (/\s/.test(ch)) break;
      start--;
    }
    setIsOpen(false);
    setFragment("");
    setTriggerStart(null);
  }, []);

  const onSelect = useCallback(
    (agent: SelectedAgent) => {
      if (triggerStart == null) {
        return { value: currentValue, caretPos };
      }
      const link = `[@${agent.slug}](${agent.url}) `;
      const next =
        currentValue.slice(0, triggerStart) +
        link +
        currentValue.slice(caretPos);
      const newCaret = triggerStart + link.length;
      setIsOpen(false);
      setFragment("");
      setTriggerStart(null);
      setCurrentValue(next);
      setCaretPos(newCaret);
      return { value: next, caretPos: newCaret };
    },
    [triggerStart, currentValue, caretPos]
  );

  const onDismiss = useCallback(() => {
    setIsOpen(false);
    setFragment("");
    setTriggerStart(null);
  }, []);

  return { isOpen, fragment, onValueChange, onSelect, onDismiss };
}
