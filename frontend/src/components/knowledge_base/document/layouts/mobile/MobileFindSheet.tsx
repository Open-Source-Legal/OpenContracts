import React, { useEffect, useRef } from "react";
import styled from "styled-components";
import { ChevronDown, ChevronUp, Search } from "lucide-react";

import { OS_LEGAL_COLORS } from "../../../../../assets/configurations/osLegalStyles";
import { MOBILE_FIND_MAX_VISIBLE_RESULTS } from "../../../../../assets/configurations/constants";
import { MOBILE_FOCUS_RING, MOBILE_RADIUS, MOBILE_SHADOW } from "./mobileTheme";
import {
  useSearchText,
  useTextSearchState,
} from "../../../../annotator/context/DocumentAtom";
import { useAnnotationRefs } from "../../../../annotator/hooks/useAnnotationRefs";
import { TextSearchSpanResult, TextSearchTokenResult } from "../../../../types";

export interface MobileFindSheetProps {
  /** Whether the sheet is open — used to focus the input on open. */
  open: boolean;
  /**
   * Fired when the user taps a result row. The sheet closes so the document
   * viewer is visible and the selected match scrolls into view. Optional so
   * the chevron-only flow (which keeps the sheet open) still works for
   * callers that don't want the auto-close behavior.
   */
  onClose?: () => void;
}

/**
 * Sheet body wrapper. `height: 100%` requires the parent (`MobileSheet`'s
 * content area) to give us a bounded height; without that the inner
 * `ResultsList`'s `flex: 1` + `overflow-y: auto` won't scroll. The
 * `MobileSheet` shell satisfies that today via its own flex column.
 */
const Wrap = styled.div`
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
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
  padding: 6px 18px 10px;
  font-size: 13px;
  color: ${OS_LEGAL_COLORS.textSecondary};
`;

const ResultsList = styled.ul`
  list-style: none;
  margin: 0;
  padding: 0 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow-y: auto;
  flex: 1;
  min-height: 0;
`;

const ResultListItem = styled.li`
  list-style: none;
`;

const ResultRow = styled.button<{ $selected: boolean }>`
  text-align: left;
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 12px 14px;
  border: none;
  border-radius: ${MOBILE_RADIUS.md};
  background: ${(props) =>
    props.$selected ? OS_LEGAL_COLORS.blueSurface : OS_LEGAL_COLORS.surface};
  box-shadow: ${MOBILE_SHADOW.subtle};
  color: ${OS_LEGAL_COLORS.textPrimary};
  cursor: pointer;
  font: inherit;
  -webkit-tap-highlight-color: transparent;
  transition: transform 0.12s ease, background 0.16s ease;

  &:active {
    transform: scale(0.99);
  }
`;

const ResultMeta = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
  color: ${OS_LEGAL_COLORS.textSecondary};
`;

const ResultIndex = styled.span`
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.primaryBlue};
`;

const ResultSnippet = styled.div`
  font-size: 14px;
  line-height: 1.45;
  color: ${OS_LEGAL_COLORS.textPrimary};
  word-break: break-word;

  /* The shared 'fullContext' ReactElement highlights the match span via
     <mark>; keep that distinctive but mobile-soft. */
  mark {
    background: ${OS_LEGAL_COLORS.accent};
    color: white;
    padding: 0 2px;
    border-radius: 3px;
  }
`;

/** Snippet rendered when a token result's fullContext is null upstream. */
const SnippetPlaceholder = styled.span`
  font-style: italic;
  color: ${OS_LEGAL_COLORS.textMuted};
`;

/** Notice rendered at the end of the list when results are capped. */
const OverflowNotice = styled.li`
  list-style: none;
  padding: 8px 14px 4px;
  font-size: 12px;
  color: ${OS_LEGAL_COLORS.textSecondary};
  text-align: center;
`;

function isTokenResult(
  result: TextSearchTokenResult | TextSearchSpanResult
): result is TextSearchTokenResult {
  return "tokens" in result;
}

/**
 * Body for the Document → Find sheet.
 *
 * A thin wrapper over the existing in-document text-search system: typing
 * drives the `searchText` atom (consumed by `useTextSearch`, mounted by
 * DocumentKnowledgeBase, which computes matches); the prev/next controls step
 * `selectedTextSearchMatchIndex` and scroll the corresponding match element
 * into view — the same primitive `FloatingDocumentInput` uses on desktop.
 *
 * On mobile we also surface every match as a tappable row. Tapping a row
 * selects that match and closes the sheet (via the optional `onClose`
 * callback) so the viewer is immediately visible with the match scrolled in.
 * Search text + match results live on Jotai atoms, so reopening the sheet
 * restores the same query, list, and selection without extra plumbing.
 */
export const MobileFindSheet: React.FC<MobileFindSheetProps> = ({
  open,
  onClose,
}) => {
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

  const handleSelectResult = (index: number) => {
    setSelectedTextSearchMatchIndex(index);
    onClose?.();
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
            data-testid="mobile-find-input"
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
      {matchCount > 0 && (
        <ResultsList data-testid="mobile-find-results">
          {textSearchMatches
            .slice(0, MOBILE_FIND_MAX_VISIBLE_RESULTS)
            .map((result, index) => {
              const pageLabel = isTokenResult(result)
                ? result.start_page === result.end_page
                  ? `Page ${result.start_page + 1}`
                  : `Pages ${result.start_page + 1}–${result.end_page + 1}`
                : "Text match";
              const snippetNode = result.fullContext;
              // Token results don't carry a raw-text fallback in their shape,
              // so render an explicit placeholder when fullContext is null
              // (an upstream context-builder failure) instead of an empty
              // row.
              const fallback = isTokenResult(result) ? (
                <SnippetPlaceholder>
                  Match preview unavailable
                </SnippetPlaceholder>
              ) : (
                result.text
              );
              return (
                <ResultListItem key={result.id}>
                  <ResultRow
                    type="button"
                    $selected={index === selectedTextSearchMatchIndex}
                    onClick={() => handleSelectResult(index)}
                    data-testid={`mobile-find-result-${index}`}
                  >
                    <ResultMeta>
                      <ResultIndex>Match {index + 1}</ResultIndex>
                      <span>{pageLabel}</span>
                    </ResultMeta>
                    <ResultSnippet>{snippetNode ?? fallback}</ResultSnippet>
                  </ResultRow>
                </ResultListItem>
              );
            })}
          {matchCount > MOBILE_FIND_MAX_VISIBLE_RESULTS && (
            <OverflowNotice data-testid="mobile-find-overflow-notice">
              Showing first {MOBILE_FIND_MAX_VISIBLE_RESULTS} of {matchCount}{" "}
              matches — use the chevrons to step through the rest.
            </OverflowNotice>
          )}
        </ResultsList>
      )}
    </Wrap>
  );
};
