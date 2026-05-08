import { useCallback, useEffect, useRef, useState } from "react";
import _ from "lodash";
import { useReactiveVar } from "@apollo/client";
import { useLocation, useNavigate } from "react-router-dom";
import { ArrowLeft, MoreVertical } from "lucide-react";
import styled from "styled-components";
import { SearchBox, FilterTabs } from "@os-legal/ui";
import type { FilterTabItem } from "@os-legal/ui";

import { OS_LEGAL_COLORS } from "../assets/configurations/osLegalStyles";
import { DEBOUNCE } from "../assets/configurations/constants";
import { analysisSearchTerm, selectedExtractIds } from "../graphql/cache";
import { updateAnnotationSelectionParams } from "../utils/navigationUtils";
import { CorpusExtractCards } from "../components/extracts/CorpusExtractCards";
import { CorpusExtractDetail } from "../components/extracts/CorpusExtractDetail";
import {
  BackNavButton,
  MobileKebabButton,
  TabNavigationHeader,
  TabTitle,
} from "./Corpuses.styles";

// ===============================================
// PRIVATE STYLES
// ===============================================
// Split view container for extracts tab
const ExtractsSplitView = styled.div`
  display: flex;
  flex: 1;
  overflow: hidden;
  gap: 1px;
  background: ${OS_LEGAL_COLORS.border};
`;

const ExtractsListPane = styled.div<{ $hasSelection: boolean }>`
  flex: ${(props) => (props.$hasSelection ? "0 0 360px" : "1")};
  overflow: hidden;
  background: ${OS_LEGAL_COLORS.background};
  transition: flex 0.2s ease;

  @media (max-width: 1024px) {
    flex: ${(props) => (props.$hasSelection ? "0 0 280px" : "1")};
  }

  @media (max-width: 768px) {
    display: ${(props) => (props.$hasSelection ? "none" : "block")};
    flex: 1;
  }
`;

const ExtractsDetailPane = styled.div`
  flex: 1;
  overflow: hidden;
  background: white;

  @media (max-width: 768px) {
    position: absolute;
    inset: 0;
    z-index: 10;
  }
`;

// Search and filter container for extracts tab
const ExtractsToolbar = styled.div`
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px 20px;
  background: white;
  border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
  flex-shrink: 0;
`;

const ExtractsSearchRow = styled.div`
  max-width: 400px;
`;

// ===============================================
// COMPONENT
// ===============================================
interface ExtractsTabContentProps {
  setActiveTab: (tab: number) => void;
  onOpenMobileMenu?: () => void;
}

/**
 * ExtractsTabContent - Split view for corpus extracts tab.
 * Shows list on left, detail on right when an extract is selected.
 * Includes search and filter functionality matching standalone Extracts view.
 */
export const ExtractsTabContent: React.FC<ExtractsTabContentProps> = ({
  setActiveTab,
  onOpenMobileMenu,
}) => {
  const location = useLocation();
  const navigate = useNavigate();
  const selected_extract_ids = useReactiveVar(selectedExtractIds);
  const analysis_search_term = useReactiveVar(analysisSearchTerm);
  const selectedExtractId = selected_extract_ids[0] || null;

  // Local state for search and filter
  const [searchCache, setSearchCache] = useState(analysis_search_term);
  const [activeFilter, setActiveFilter] = useState("all");

  // Debounced search - updates the reactive var used by CorpusExtractCards
  const debouncedSearch = useRef(
    _.debounce((searchTerm: string) => {
      analysisSearchTerm(searchTerm);
    }, DEBOUNCE.EXTRACT_SEARCH_MS)
  );

  // Cleanup debounce on unmount
  useEffect(() => {
    return () => {
      debouncedSearch.current.cancel();
    };
  }, []);

  const handleSearchChange = useCallback((value: string) => {
    setSearchCache(value);
    debouncedSearch.current(value);
  }, []);

  const handleCloseDetail = useCallback(() => {
    // Clear extract selection via URL
    updateAnnotationSelectionParams(location, navigate, {
      extractIds: [],
    });
  }, [location, navigate]);

  // Filter tabs configuration
  const filterItems: FilterTabItem[] = [
    { id: "all", label: "All" },
    { id: "running", label: "Running" },
    { id: "completed", label: "Completed" },
    { id: "failed", label: "Failed" },
    { id: "not_started", label: "Not Started" },
  ];

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
        position: "relative",
      }}
    >
      <TabNavigationHeader>
        <BackNavButton
          onClick={() => setActiveTab(0)}
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
          title="Back to Home"
        >
          <ArrowLeft />
        </BackNavButton>
        <TabTitle>Extracts</TabTitle>
        {onOpenMobileMenu && (
          <MobileKebabButton
            onClick={onOpenMobileMenu}
            aria-label="Open navigation menu"
          >
            <MoreVertical />
          </MobileKebabButton>
        )}
      </TabNavigationHeader>

      {/* Search and Filter Toolbar */}
      <ExtractsToolbar>
        <ExtractsSearchRow>
          <SearchBox
            placeholder="Search extracts..."
            value={searchCache}
            onChange={(e) => handleSearchChange(e.target.value)}
            onSubmit={(value) => handleSearchChange(value)}
          />
        </ExtractsSearchRow>
        <FilterTabs
          items={filterItems}
          value={activeFilter}
          onChange={setActiveFilter}
        />
      </ExtractsToolbar>

      <ExtractsSplitView>
        <ExtractsListPane $hasSelection={Boolean(selectedExtractId)}>
          <CorpusExtractCards useInlineSelection activeFilter={activeFilter} />
        </ExtractsListPane>

        {selectedExtractId && (
          <ExtractsDetailPane>
            <CorpusExtractDetail
              extractId={selectedExtractId}
              onClose={handleCloseDetail}
            />
          </ExtractsDetailPane>
        )}
      </ExtractsSplitView>
    </div>
  );
};
