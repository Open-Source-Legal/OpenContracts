import React, { useEffect, useRef } from "react";
import styled from "styled-components";
import { ChevronDown, ChevronUp, Search } from "lucide-react";

import { OS_LEGAL_COLORS } from "../../../../../assets/configurations/osLegalStyles";
import { MOBILE_FOCUS_RING, MOBILE_RADIUS, MOBILE_SHADOW } from "./mobileTheme";
import {
  useSearchText,
  useTextSearchState,
} from "../../../../annotator/context/DocumentAtom";
import { useAnnotationRefs } from "../../../../annotator/hooks/useAnnotationRefs";

export interface MobileFindSheetProps {
  /** Whether the sheet is open — used to focus the input on open. */
  open: boolean;
}

const Wrap = styled.div`
  display: flex;
  flex-direction: column;
`;

const SearchRow = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 16px 14px 10px;
`;

/** Crisp white elevated input — teal reserved for the focus ring. */
const InputShell = styled.div`
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  height: 44px;
  padding: 0 14px;
  border-radius: ${MOBILE_RADIUS.md};
  background: ${OS_LEGAL_COLORS.surface};
  box-shadow: ${MOBILE_SHADOW.subtle};
  transition: box-shadow 0.18s ease;

  &:focus-within {
    box-shadow: ${MOBILE_SHADOW.subtle}, ${MOBILE_FOCUS_RING};
  }
`;

const Input = styled.input`
  flex: 1;
  border: none;
  outline: none;
  font-size: 14px;
  background: transparent;
  color: ${OS_LEGAL_COLORS.textPrimary};

  &::placeholder {
    color: ${OS_LEGAL_COLORS.textMuted};
  }
`;

const StepButton = styled.button`
  width: 40px;
  height: 44px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: ${MOBILE_RADIUS.md};
  background: ${OS_LEGAL_COLORS.surface};
  box-shadow: ${MOBILE_SHADOW.subtle};
  color: ${OS_LEGAL_COLORS.textSecondary};
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
  transition: transform 0.12s ease, box-shadow 0.16s ease;

  &:active:not(:disabled) {
    transform: scale(0.92);
  }

  &:disabled {
    opacity: 0.4;
    cursor: default;
  }
`;

const Status = styled.div`
  padding: 6px 18px 16px;
  font-size: 13px;
  color: ${OS_LEGAL_COLORS.textSecondary};
`;

/**
 * Body for the Document → Find sheet.
 *
 * A thin wrapper over the existing in-document text-search system: typing
 * drives the `searchText` atom (consumed by `useTextSearch`, mounted by
 * DocumentKnowledgeBase, which computes matches); the prev/next controls step
 * `selectedTextSearchMatchIndex` and scroll the corresponding match element
 * into view — the same primitive `FloatingDocumentInput` uses on desktop.
 */
export const MobileFindSheet: React.FC<MobileFindSheetProps> = ({ open }) => {
  const { searchText, setSearchText } = useSearchText();
  const {
    textSearchMatches,
    selectedTextSearchMatchIndex,
    setSelectedTextSearchMatchIndex,
  } = useTextSearchState();
  const annotationRefs = useAnnotationRefs();

  const matchCount = textSearchMatches.length;

  // Focus the input each time the sheet opens. `autoFocus` only fires on the
  // initial mount, so it would not re-focus when the sheet is closed and
  // reopened while this component stays mounted.
  const inputRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  // Scroll the selected match into view whenever the selection changes.
  useEffect(() => {
    if (matchCount === 0) return;
    const target =
      annotationRefs.textSearchElementRefs.current[
        selectedTextSearchMatchIndex
      ];
    target?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [
    selectedTextSearchMatchIndex,
    matchCount,
    annotationRefs.textSearchElementRefs,
  ]);

  const step = (delta: number) => {
    if (matchCount === 0) return;
    const next =
      (selectedTextSearchMatchIndex + delta + matchCount) % matchCount;
    setSelectedTextSearchMatchIndex(next);
  };

  return (
    <Wrap data-testid="mobile-find-sheet">
      <SearchRow>
        <InputShell>
          <Search size={15} color={OS_LEGAL_COLORS.textSecondary} />
          <Input
            ref={inputRef}
            placeholder="Find in document"
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
          />
        </InputShell>
        <StepButton
          aria-label="Previous match"
          disabled={matchCount === 0}
          onClick={() => step(-1)}
        >
          <ChevronUp size={16} />
        </StepButton>
        <StepButton
          aria-label="Next match"
          disabled={matchCount === 0}
          onClick={() => step(1)}
        >
          <ChevronDown size={16} />
        </StepButton>
      </SearchRow>
      <Status data-testid="mobile-find-status">
        {searchText.trim() === ""
          ? "Type to search the document text."
          : matchCount === 0
          ? "No matches."
          : `${selectedTextSearchMatchIndex + 1} of ${matchCount} matches`}
      </Status>
    </Wrap>
  );
};
