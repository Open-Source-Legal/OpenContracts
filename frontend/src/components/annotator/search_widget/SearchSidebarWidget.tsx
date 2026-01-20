import React, { useEffect, useMemo, useState } from "react";
import { Alert, SearchInput } from "@os-legal/ui";
import styled from "styled-components";
import _ from "lodash";
import "./SearchWidgetStyles.css";
import { TextSearchSpanResult, TextSearchTokenResult } from "../../types";
import { TruncatedText } from "../../widgets/data-display/TruncatedText";
import { useAnnotationRefs } from "../hooks/useAnnotationRefs";
import { useSearchText, useTextSearchState } from "../context/DocumentAtom";

const SearchInputSection = styled.div`
  background-color: #ffffff;
  border-bottom: 1px solid #e0e0e0;
  padding: 1rem;
`;

const ResultsSection = styled.div`
  height: 100%;
  overflow-y: auto;
  background-color: #ffffff;
  border: none;
  box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.1);
  padding: 1rem;
`;

const SearchResultCardContainer = styled.div`
  cursor: pointer;
  transition: all 0.3s ease;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.12), 0 1px 2px rgba(0, 0, 0, 0.24);
  margin-right: 0.5vw;
  margin-bottom: 0.75rem;
  padding: 1rem;
  background: #fff;
  border: 1px solid rgba(34, 36, 38, 0.15);
  border-radius: 0.28571429rem;

  &:hover {
    box-shadow: 0 3px 6px rgba(0, 0, 0, 0.16), 0 3px 6px rgba(0, 0, 0, 0.23);
    transform: translateY(-1px);
  }
`;

const SearchResultHeader = styled.div`
  font-weight: 700;
  margin-bottom: 0.5rem;
`;

const SearchResultContent = styled.div`
  margin-top: 10px;
  padding: 10px;
  background-color: #f8f8f8;
  border-radius: 5px;
  font-size: 0.9em;
  line-height: 1.4;
`;

const SmallHeaderText = styled.h4`
  font-size: 1rem;
  font-weight: 600;
  color: #1e293b;
  margin: 0;
`;

const TinyHeaderText = styled.h5`
  font-size: 0.875rem;
  font-weight: 500;
  color: #64748b;
  margin: 0;
`;

/**
 * Displays the page header based on the type of search result.
 */
const PageHeaderDisplay: React.FC<{
  result: TextSearchTokenResult | TextSearchSpanResult;
}> = ({ result }) => {
  if ("start_page" in result && "end_page" in result) {
    // TextSearchTokenResult
    return result.start_page === result.end_page ? (
      <SmallHeaderText>Page {result.end_page}</SmallHeaderText>
    ) : (
      <SmallHeaderText>
        Page {result.start_page} to Page {result.end_page}
      </SmallHeaderText>
    );
  } else {
    // TextSearchSpanResult
    return <SmallHeaderText>Text Match</SmallHeaderText>;
  }
};

/**
 * Placeholder card displayed when there are no search results.
 */
const PlaceholderSearchResultCard: React.FC = () => (
  <Alert variant="warning" title="No Matching Results">
    Try changing your query. Also be aware that OCR quality issues may cause
    slight changes to the characters in the PDF text layer.
  </Alert>
);

/**
 * Card that renders a single search result.
 */
const SearchResultCard: React.FC<{
  index: number;
  onResultClick: (index: number) => void;
  res: TextSearchTokenResult | TextSearchSpanResult;
  totalMatches: number;
}> = ({ index, res, totalMatches, onResultClick }) => {
  const isTokenResult = "tokens" in res;

  return (
    <SearchResultCardContainer
      key={index}
      onClick={() => {
        console.log("Clicked on result", index);
        onResultClick(index);
      }}
      className="hover-effect"
    >
      <SearchResultHeader>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <PageHeaderDisplay result={res} />
          <TinyHeaderText>
            {index + 1} of {totalMatches}
          </TinyHeaderText>
        </div>
      </SearchResultHeader>
      <SearchResultContent>
        {isTokenResult ? (
          res.fullContext
        ) : (
          <TruncatedText text={res.text} limit={64} />
        )}
      </SearchResultContent>
    </SearchResultCardContainer>
  );
};

/**
 * SearchSidebarWidget component displays the search input and search
 * result cards. The search input is debounced to limit the number of state updates.
 *
 * We store localInput in a separate state so the text field updates immediately,
 * while the actual global search text is updated only after a 1-second delay.
 */
export const SearchSidebarWidget: React.FC = () => {
  const annotationRefs = useAnnotationRefs();
  const {
    textSearchMatches: searchResults,
    selectedTextSearchMatchIndex,
    setSelectedTextSearchMatchIndex,
  } = useTextSearchState();
  const { searchText, setSearchText } = useSearchText();

  /**
   * Local state to show the user immediate typing feedback.
   * After 1s the global search text is updated, triggering a search.
   */
  const [localInput, setLocalInput] = useState<string>(searchText || "");

  // Sync localInput whenever global searchText changes (e.g. user clears or resets).
  useEffect(() => {
    setLocalInput(searchText || "");
  }, [searchText]);

  /**
   * Create a debounced version of the setter that calls setSearchText
   * after a 1s delay.
   */
  const debouncedSetSearchText = useMemo(
    () =>
      _.debounce((value: string) => {
        setSearchText(value);
      }, 1000),
    [setSearchText]
  );

  // Cleanup the debounced call when the component unmounts.
  useEffect(() => {
    return () => {
      debouncedSetSearchText.cancel();
    };
  }, [debouncedSetSearchText]);

  useEffect(() => {
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
  }, [selectedTextSearchMatchIndex, annotationRefs.textSearchElementRefs]);

  const onResultClick = (index: number) => {
    console.log("SearchSidebar: Result clicked", {
      clickedIndex: index,
      previousIndex: selectedTextSearchMatchIndex,
    });
    setSelectedTextSearchMatchIndex(index);
  };

  return (
    <div
      style={{
        height: "100%",
        display: "flex",
        flexDirection: "column",
        justifyContent: "flex-start",
        backgroundColor: "#f0f2f5",
      }}
    >
      <SearchInputSection>
        <SearchInput
          placeholder="Search document..."
          onChange={(e) => {
            setLocalInput(e.target.value);
            debouncedSetSearchText(e.target.value);
          }}
          value={localInput}
          onClear={
            searchText
              ? () => {
                  debouncedSetSearchText.cancel();
                  setSearchText("");
                }
              : undefined
          }
        />
      </SearchInputSection>
      <ResultsSection>
        <div style={{ overflowY: "auto", height: "100%" }}>
          {searchResults.length > 0 ? (
            searchResults.map(
              (
                res: TextSearchTokenResult | TextSearchSpanResult,
                index: number
              ) => (
                <SearchResultCard
                  key={`SearchResultCard_${index}`}
                  index={index}
                  totalMatches={searchResults.length}
                  res={res}
                  onResultClick={onResultClick}
                />
              )
            )
          ) : (
            <PlaceholderSearchResultCard />
          )}
        </div>
      </ResultsSection>
    </div>
  );
};
