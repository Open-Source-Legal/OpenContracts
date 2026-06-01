import React, { useCallback, useEffect, useRef, useState } from "react";
import _ from "lodash";
import { useReactiveVar } from "@apollo/client";
import { ArrowLeft, MoreVertical, Sparkles } from "lucide-react";
import styled from "styled-components";
import { SearchBox, FilterTabs, Button } from "@os-legal/ui";
import type { FilterTabItem } from "@os-legal/ui";

import { OS_LEGAL_COLORS } from "../assets/configurations/osLegalStyles";
import { DEBOUNCE } from "../assets/configurations/constants";
import { openedCorpus, researchSearchTerm } from "../graphql/cache";
import { CorpusResearchReportCards } from "../components/research/CorpusResearchReportCards";
import { StartResearchModal } from "../components/widgets/modals/StartResearchModal";
import {
  BackNavButton,
  MobileKebabButton,
  TabNavigationHeader,
  TabTitle,
} from "./Corpuses.styles";

const Toolbar = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 16px 20px;
  background: ${OS_LEGAL_COLORS.surface};
  border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
  flex-shrink: 0;
  flex-wrap: wrap;
`;

const ToolbarLeft = styled.div`
  display: flex;
  flex-direction: column;
  gap: 12px;
  flex: 1;
  min-width: 240px;
`;

const SearchRow = styled.div`
  max-width: 400px;
`;

const FILTER_ITEMS: FilterTabItem[] = [
  { id: "all", label: "All" },
  { id: "queued", label: "Queued" },
  { id: "running", label: "Running" },
  { id: "completed", label: "Completed" },
  { id: "failed", label: "Failed" },
  { id: "cancelled", label: "Cancelled" },
];

interface ResearchTabContentProps {
  setActiveTab: (tab: number | string) => void;
  onOpenMobileMenu?: () => void;
}

/**
 * ResearchTabContent - corpus "Research" tab. List-only: cards link to the
 * standalone /research/:slug detail page. The primary way to start research is
 * the corpus chat agent; the "Start research" button here is a secondary
 * explicit affordance.
 */
export const ResearchTabContent: React.FC<ResearchTabContentProps> = ({
  setActiveTab,
  onOpenMobileMenu,
}) => {
  const opened_corpus = useReactiveVar(openedCorpus);
  const research_search_term = useReactiveVar(researchSearchTerm);

  const [searchCache, setSearchCache] = useState(research_search_term);
  const [activeFilter, setActiveFilter] = useState("all");
  const [showStartModal, setShowStartModal] = useState(false);

  const debouncedSearch = useRef(
    _.debounce((term: string) => {
      researchSearchTerm(term);
    }, DEBOUNCE.LIST_SEARCH_MS)
  );

  useEffect(() => {
    const debounced = debouncedSearch.current;
    return () => {
      // Cancel any in-flight debounced update and clear the shared search term
      // so a stale query doesn't persist into the next visit to this tab.
      debounced.cancel();
      researchSearchTerm("");
    };
  }, []);

  const handleSearchChange = useCallback((value: string) => {
    setSearchCache(value);
    debouncedSearch.current(value);
  }, []);

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
        <TabTitle>Research</TabTitle>
        {onOpenMobileMenu && (
          <MobileKebabButton
            onClick={onOpenMobileMenu}
            aria-label="Open navigation menu"
          >
            <MoreVertical />
          </MobileKebabButton>
        )}
      </TabNavigationHeader>

      <Toolbar>
        <ToolbarLeft>
          <SearchRow>
            <SearchBox
              placeholder="Search research..."
              value={searchCache}
              onChange={(e) => handleSearchChange(e.target.value)}
              onSubmit={(value) => handleSearchChange(value)}
            />
          </SearchRow>
          <FilterTabs
            items={FILTER_ITEMS}
            value={activeFilter}
            onChange={setActiveFilter}
          />
        </ToolbarLeft>
        <Button
          variant="primary"
          size="sm"
          leftIcon={<Sparkles size={16} />}
          onClick={() => setShowStartModal(true)}
          disabled={!opened_corpus?.id}
        >
          Start research
        </Button>
      </Toolbar>

      <CorpusResearchReportCards activeFilter={activeFilter} />

      {showStartModal && opened_corpus?.id && (
        <StartResearchModal
          corpusId={opened_corpus.id}
          open={showStartModal}
          onClose={() => setShowStartModal(false)}
        />
      )}
    </div>
  );
};

export default ResearchTabContent;
