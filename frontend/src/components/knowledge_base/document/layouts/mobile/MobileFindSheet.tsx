import React, { useEffect } from "react";
import styled from "styled-components";
import { ChevronDown, ChevronUp, Search } from "lucide-react";

import { OS_LEGAL_COLORS } from "../../../../../assets/configurations/osLegalStyles";
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
  padding: 12px 16px;
  border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
`;

const InputShell = styled.div`
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  height: 40px;
  padding: 0 12px;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 10px;
  background: white;
`;

const Input = styled.input`
  flex: 1;
  border: none;
  outline: none;
  font-size: 14px;
  background: transparent;
  color: ${OS_LEGAL_COLORS.textPrimary};
`;

const StepButton = styled.button`
  width: 36px;
  height: 36px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 8px;
  background: white;
  color: ${OS_LEGAL_COLORS.textSecondary};
  cursor: pointer;

  &:disabled {
    opacity: 0.4;
    cursor: default;
  }
`;

const Status = styled.div`
  padding: 12px 16px;
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
            autoFocus={open}
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
