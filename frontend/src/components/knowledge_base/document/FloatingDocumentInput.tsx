import React, { useState, useRef, useEffect, useMemo } from "react";
import styled, { css } from "styled-components";
import { motion, AnimatePresence } from "framer-motion";
import { Search, MessageSquare, Send, X, ChevronUp } from "lucide-react";
import { Form } from "semantic-ui-react";
import _ from "lodash";
import {
  useSearchText,
  useTextSearchState,
} from "../../annotator/context/DocumentAtom";
import { useAnnotationRefs } from "../../annotator/hooks/useAnnotationRefs";

interface FloatingDocumentInputProps {
  /** Whether the input should be rendered */
  visible?: boolean;

  /** Callback when a chat message is submitted. */
  onChatSubmit?: (message: string) => void;

  /** Optional callback triggered when the component programmatically opens the chat sidebar. */
  onToggleChat?: () => void;

  /** Width in pixels of the right-hand sliding panel (0 when hidden). */
  panelOffset?: number;

  /**
   * Render using `position: fixed` (default) or allow the parent wrapper to
   * control positioning.  When `false` the component behaves like a normal
   * inline element so it can be centred with flexbox, etc.
   */
  fixed?: boolean;

  /** When true, the input is read-only and chat mode is disabled */
  readOnly?: boolean;
}

const FloatingContainer = styled(motion.div)<{
  $isExpanded: boolean;
  $mode: "search" | "chat";
  $panelOffset: number;
  $fixed: boolean;
}>`
  ${(props) =>
    props.$fixed
      ? css`
          position: fixed;
          bottom: 2rem;
          left: calc(50% - ${props.$panelOffset / 2}px);
          transform: translateX(-50%);
          /* Prevent overflow under the sliding panel */
          max-width: calc(100vw - ${props.$panelOffset}px - 2rem);
        `
      : css`
          position: relative;
          /* In wrapper-mode the parent handles centring & right offset. */
          max-width: 100%;
        `}

  background: white;
  border-radius: ${(props) => (props.$isExpanded ? "16px" : "28px")};
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.08), 0 1px 2px rgba(0, 0, 0, 0.04);
  border: 1px solid #e2e8f0;
  overflow: hidden;
  z-index: 1000;
  pointer-events: auto;
  display: flex;
  align-items: ${(props) =>
    props.$isExpanded && props.$mode === "chat" ? "flex-end" : "center"};
  padding: ${(props) => (props.$isExpanded ? "0.75rem" : "0.5rem")};
  width: ${(props) => (props.$isExpanded ? "600px" : "120px")};

  min-height: ${(props) =>
    props.$isExpanded ? (props.$mode === "chat" ? "auto" : "56px") : "56px"};
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

  &:hover {
    box-shadow: 0 6px 32px rgba(0, 0, 0, 0.12);
    border-color: #cbd5e1;
  }

  @media (max-width: 768px) {
    /* Always use fixed positioning on mobile to place under zoom controls */
    position: fixed;
    top: 240px; /* 180px (zoom controls) + 60px gap */
    left: 1rem;
    transform: none;

    /* Size - collapsed shows just the toggle buttons, expanded shows full width */
    width: ${(props) => (props.$isExpanded ? "calc(100vw - 2rem)" : "auto")};
    max-width: calc(100vw - 2rem);

    /* Keep original rounded rectangle shape */
    border-radius: ${(props) => (props.$isExpanded ? "16px" : "28px")};

    /* Ensure proper padding */
    padding: ${(props) => (props.$isExpanded ? "0.75rem" : "0.5rem")};

    /* Ensure content is visible when expanded */
    ${(props) =>
      props.$isExpanded &&
      css`
        min-height: 56px;
        display: flex;
        align-items: center;
        gap: 0.5rem;
      `}

    /* Smooth expansion */
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

    /* Ensure it's above other elements */
    z-index: 1100;
  }
`;

const ToggleGroup = styled.div<{ $isExpanded?: boolean }>`
  display: flex;
  gap: 0.25rem;
  margin-right: 0.75rem;
  flex-shrink: 0;

  @media (max-width: 768px) {
    margin-right: ${(props) => (props.$isExpanded ? "0.5rem" : "0")};
    justify-content: center;
    width: ${(props) => (props.$isExpanded ? "auto" : "100%")};
  }
`;

const ToggleButton = styled(motion.button)<{ $isActive: boolean }>`
  width: 40px;
  height: 40px;
  border-radius: 12px;
  border: none;
  background: ${(props) => (props.$isActive ? "#eff6ff" : "transparent")};
  color: ${(props) => (props.$isActive ? "#3b82f6" : "#64748b")};
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;

  svg {
    width: 20px;
    height: 20px;
  }

  &:hover {
    background: ${(props) => (props.$isActive ? "#dbeafe" : "#f8fafc")};
    color: ${(props) => (props.$isActive ? "#3b82f6" : "#475569")};
  }

  @media (max-width: 768px) {
    width: 28px;
    height: 28px;
    border-radius: 14px;

    svg {
      width: 16px;
      height: 16px;
    }
  }
`;

const InputWrapper = styled.div`
  flex: 1;
  display: flex;
  align-items: flex-end;
  gap: 0.5rem;
  min-width: 0;

  @media (max-width: 768px) {
    min-width: 0; /* Allow shrinking */
    flex: 1 1 auto;
    max-width: calc(100% - 120px); /* Account for buttons */
  }
`;

const StyledInput = styled.input`
  flex: 1;
  border: none;
  background: none;
  outline: none;
  font-size: 0.9375rem;
  color: #1e293b;
  padding: 0.5rem 0;

  &::placeholder {
    color: #94a3b8;
  }
`;

const StyledTextarea = styled.textarea`
  flex: 1;
  border: none;
  background: none;
  outline: none;
  font-size: 0.9375rem;
  color: #1e293b;
  padding: 0.5rem 0;
  resize: none;
  min-height: 24px;
  max-height: 120px;
  line-height: 1.5;
  font-family: inherit;

  &::placeholder {
    color: #94a3b8;
  }
`;

const ActionButton = styled(motion.button)`
  width: 40px;
  height: 40px;
  border-radius: 12px;
  border: none;
  background: #3b82f6;
  color: white;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;

  svg {
    width: 20px;
    height: 20px;
  }

  &:hover {
    background: #2563eb;
  }

  &:disabled {
    background: #e2e8f0;
    color: #94a3b8;
    cursor: not-allowed;
  }

  @media (max-width: 768px) {
    width: 36px;
    height: 36px;

    svg {
      width: 18px;
      height: 18px;
    }
  }
`;

const CloseButton = styled(motion.button)`
  width: 32px;
  height: 32px;
  border-radius: 8px;
  border: none;
  background: transparent;
  color: #64748b;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-left: 0.5rem;

  svg {
    width: 18px;
    height: 18px;
  }

  &:hover {
    background: #f1f5f9;
    color: #475569;
  }

  @media (max-width: 768px) {
    width: 28px;
    height: 28px;
    margin-left: 0.25rem;

    svg {
      width: 16px;
      height: 16px;
    }
  }
`;

const SearchStatus = styled.div`
  font-size: 0.75rem;
  color: #64748b;
  margin-right: 0.5rem;
  white-space: nowrap;
`;

const ModeIndicator = styled(motion.div)<{ $mode: "search" | "chat" }>`
  position: absolute;
  top: -24px;
  left: 50%;
  transform: translateX(-50%);
  background: ${(props) => (props.$mode === "search" ? "#3b82f6" : "#8b5cf6")};
  color: white;
  padding: 0.25rem 0.75rem;
  border-radius: 9999px;
  font-size: 0.75rem;
  font-weight: 600;
  white-space: nowrap;
  pointer-events: none;

  @media (max-width: 768px) {
    display: none;
  }
`;

export const FloatingDocumentInput: React.FC<FloatingDocumentInputProps> = ({
  visible = true,
  onChatSubmit,
  onToggleChat,
  panelOffset = 0,
  fixed = true,
  readOnly = false,
}) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const [mode, setMode] = useState<"search" | "chat">("search");
  const [localInput, setLocalInput] = useState("");
  const [showModeIndicator, setShowModeIndicator] = useState(false);

  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Search functionality
  const annotationRefs = useAnnotationRefs();
  const { searchText, setSearchText } = useSearchText();
  const {
    textSearchMatches,
    selectedTextSearchMatchIndex,
    setSelectedTextSearchMatchIndex,
  } = useTextSearchState();

  // Debounced search
  const debouncedSetSearchText = useMemo(
    () =>
      _.debounce((value: string) => {
        if (value.trim() === "") {
          setSearchText("");
          return;
        }
        setSearchText(value);
      }, 800),
    [setSearchText]
  );

  // Handle clicks outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        containerRef.current &&
        !containerRef.current.contains(event.target as Node)
      ) {
        setIsExpanded(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      debouncedSetSearchText.cancel();
    };
  }, [debouncedSetSearchText]);

  // Sync search text
  useEffect(() => {
    if (mode === "search") {
      setLocalInput(searchText || "");
    }
  }, [searchText, mode]);

  // Scroll to search result
  useEffect(() => {
    if (mode === "search") {
      const currentRef =
        annotationRefs.textSearchElementRefs.current[
          selectedTextSearchMatchIndex
        ];
      if (currentRef) {
        currentRef.scrollIntoView({
          behavior: "smooth",
          block: "center",
        });
      }
    }
  }, [
    selectedTextSearchMatchIndex,
    annotationRefs.textSearchElementRefs,
    mode,
  ]);

  // Auto-resize textarea
  const adjustTextareaHeight = () => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = "auto";
      textarea.style.height = `${Math.min(textarea.scrollHeight, 120)}px`;
    }
  };

  useEffect(() => {
    if (mode === "chat" && isExpanded) {
      adjustTextareaHeight();
    }
  }, [localInput, mode, isExpanded]);

  // Focus input when expanded
  useEffect(() => {
    if (isExpanded) {
      setTimeout(() => {
        if (mode === "search" && inputRef.current) {
          inputRef.current.focus();
        } else if (mode === "chat" && textareaRef.current) {
          textareaRef.current.focus();
        }
      }, 100);
    }
  }, [isExpanded, mode]);

  /**
   * Handle click on a mode toggle button. If the clicked mode is already
   * active we treat the click as a *toggle* – collapsing the widget when it
   * is currently expanded, or expanding it when collapsed.
   *
   * If a *different* mode is clicked we switch modes and ensure the widget is
   * expanded.
   */
  const handleModeButtonClick = (clickedMode: "search" | "chat") => {
    // Prevent switching to chat mode in readOnly
    if (readOnly && clickedMode === "chat") {
      return;
    }

    if (clickedMode === mode) {
      // Same mode clicked → toggle expand/collapse
      if (isExpanded) {
        handleClose();
      } else {
        setIsExpanded(true);
      }
    } else {
      // Switch modes; ensure expanded
      setMode(clickedMode);
      setLocalInput("");
      setShowModeIndicator(true);
      setTimeout(() => setShowModeIndicator(false), 2000);

      if (clickedMode === "search") {
        debouncedSetSearchText.cancel();
        setSearchText("");
      }

      if (!isExpanded) {
        setIsExpanded(true);
      }
    }
  };

  const handleClose = () => {
    setIsExpanded(false);
    setLocalInput("");
    if (mode === "search") {
      debouncedSetSearchText.cancel();
      setSearchText("");
    }
  };

  const handleInputChange = (value: string) => {
    setLocalInput(value);
    if (mode === "search") {
      debouncedSetSearchText(value);
    }
  };

  const handleSearchKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && mode === "search") {
      e.preventDefault();
      if (localInput.trim() === searchText.trim()) {
        // Move to next result
        if (textSearchMatches.length > 0) {
          const nextIndex =
            (selectedTextSearchMatchIndex + 1) % textSearchMatches.length;
          setSelectedTextSearchMatchIndex(nextIndex);
        }
      } else {
        // New search
        debouncedSetSearchText.cancel();
        setSearchText(localInput);
      }
    }
  };

  const handleChatSubmit = () => {
    if (mode === "chat" && localInput.trim()) {
      onChatSubmit?.(localInput.trim());
      setLocalInput("");
      setIsExpanded(false);
      onToggleChat?.(); // Open chat panel if provided
    }
  };

  const handleChatKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleChatSubmit();
    }
  };

  const matchIndicator = useMemo(() => {
    if (mode === "search" && textSearchMatches.length > 0) {
      return `${selectedTextSearchMatchIndex + 1} of ${
        textSearchMatches.length
      }`;
    }
    return "";
  }, [mode, textSearchMatches, selectedTextSearchMatchIndex]);

  if (!visible) return null;

  return (
    <FloatingContainer
      ref={containerRef}
      $isExpanded={isExpanded}
      $mode={mode}
      $panelOffset={panelOffset}
      $fixed={fixed}
      initial={{ y: 100, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      exit={{ y: 100, opacity: 0 }}
      transition={{ type: "spring", damping: 25, stiffness: 300 }}
      onMouseDown={(e) => e.stopPropagation()}
      onMouseUp={(e) => e.stopPropagation()}
      onMouseMove={(e) => e.stopPropagation()}
    >
      <AnimatePresence>
        {showModeIndicator && (
          <ModeIndicator
            $mode={mode}
            initial={{ opacity: 0, y: 5 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -5 }}
          >
            {mode === "search" ? "Search Mode" : "Chat Mode"}
          </ModeIndicator>
        )}
      </AnimatePresence>

      <ToggleGroup $isExpanded={isExpanded}>
        <ToggleButton
          $isActive={mode === "search"}
          onClick={() => handleModeButtonClick("search")}
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
        >
          <Search />
        </ToggleButton>
        {!readOnly && (
          <ToggleButton
            $isActive={mode === "chat"}
            onClick={() => handleModeButtonClick("chat")}
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
          >
            <MessageSquare />
          </ToggleButton>
        )}
      </ToggleGroup>

      {isExpanded && (
        <>
          <InputWrapper>
            {mode === "search" ? (
              <>
                <StyledInput
                  ref={inputRef}
                  placeholder="Search document..."
                  value={localInput}
                  onChange={(e) => handleInputChange(e.target.value)}
                  onKeyDown={handleSearchKeyDown}
                />
                {matchIndicator && (
                  <SearchStatus>{matchIndicator}</SearchStatus>
                )}
              </>
            ) : (
              <StyledTextarea
                ref={textareaRef}
                placeholder="Ask a question..."
                value={localInput}
                onChange={(e) => handleInputChange(e.target.value)}
                onKeyDown={handleChatKeyDown}
                rows={1}
              />
            )}
          </InputWrapper>

          {mode === "chat" && (
            <ActionButton
              onClick={handleChatSubmit}
              disabled={!localInput.trim()}
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
            >
              <Send />
            </ActionButton>
          )}

          <CloseButton
            onClick={handleClose}
            whileHover={{ scale: 1.1 }}
            whileTap={{ scale: 0.9 }}
          >
            <X />
          </CloseButton>
        </>
      )}
    </FloatingContainer>
  );
};
