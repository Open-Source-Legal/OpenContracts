import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import styled from "styled-components";
import { motion, AnimatePresence } from "framer-motion";
import { MessageSquare, Database, FileText, Plus, Search } from "lucide-react";
import { ThreadList } from "../components/threads/ThreadList";
import { CreateThreadButton } from "../components/threads/CreateThreadButton";
import { color } from "../theme/colors";
import { spacing } from "../theme/spacing";

// Styled components
const Container = styled.div`
  margin: 0 auto;
  padding: 2rem 4rem;
  height: 100%;
  overflow-y: auto;
  overflow-x: hidden;

  @media (max-width: 1400px) {
    padding: 2rem 3rem;
  }

  @media (max-width: 1024px) {
    padding: 1.5rem 2rem;
  }

  @media (max-width: 768px) {
    padding: 1rem;
  }
`;

const Header = styled.div`
  margin-bottom: 2rem;
`;

const TitleRow = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1.5rem;
`;

const Title = styled.h1`
  font-size: 2rem;
  font-weight: 800;
  color: ${color.N10};
  margin: 0;
  letter-spacing: -0.025em;

  @media (max-width: 768px) {
    font-size: 1.5rem;
  }
`;

const FilterBar = styled.div`
  display: flex;
  gap: 1rem;
  align-items: center;
  margin-bottom: 1.5rem;
  flex-wrap: wrap;
`;

const TabContainer = styled.div`
  display: flex;
  gap: 0.5rem;
  background: ${color.N2};
  padding: 0.375rem;
  border-radius: 12px;
  border: 1px solid ${color.N4};
`;

const Tab = styled(motion.button)<{ $isActive: boolean }>`
  padding: 0.625rem 1.25rem;
  border-radius: 8px;
  border: none;
  background: ${(props) => (props.$isActive ? "white" : "transparent")};
  color: ${(props) => (props.$isActive ? color.N10 : color.N7)};
  font-weight: ${(props) => (props.$isActive ? "600" : "500")};
  font-size: 0.9375rem;
  cursor: pointer;
  transition: all 0.2s ease;
  box-shadow: ${(props) =>
    props.$isActive ? "0 1px 3px rgba(0,0,0,0.1)" : "none"};
  display: flex;
  align-items: center;
  gap: 0.5rem;

  &:hover {
    background: ${(props) =>
      props.$isActive ? "white" : "rgba(255,255,255,0.6)"};
  }

  @media (max-width: 640px) {
    padding: 0.5rem 0.875rem;
    font-size: 0.875rem;
  }
`;

const SearchInputContainer = styled.div`
  flex: 1;
  min-width: 200px;
  max-width: 400px;
  position: relative;
`;

const SearchIcon = styled(Search)`
  position: absolute;
  left: 1rem;
  top: 50%;
  transform: translateY(-50%);
  color: ${color.N6};
  pointer-events: none;
`;

const SearchInput = styled.input`
  width: 100%;
  padding: 0.625rem 1rem 0.625rem 2.75rem;
  border: 1px solid ${color.N4};
  border-radius: 8px;
  font-size: 0.9375rem;
  color: ${color.N10};
  background: white;

  &:focus {
    outline: none;
    border-color: ${color.B5};
    box-shadow: 0 0 0 3px rgba(74, 144, 226, 0.1);
  }

  &::placeholder {
    color: ${color.N6};
  }
`;

const FAB = styled(motion.button)`
  position: fixed;
  bottom: 2rem;
  right: 2rem;
  width: 56px;
  height: 56px;
  border-radius: 16px;
  background: linear-gradient(135deg, ${color.B6} 0%, ${color.B7} 100%);
  border: none;
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  box-shadow: 0 8px 24px rgba(74, 144, 226, 0.4);
  z-index: 100;

  &:hover {
    box-shadow: 0 12px 32px rgba(74, 144, 226, 0.5);
  }

  @media (max-width: 768px) {
    bottom: 1rem;
    right: 1rem;
  }
`;

const SectionContainer = styled(motion.div)`
  margin-bottom: 2.5rem;
`;

const SectionHeader = styled.div`
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 1rem;
  padding-bottom: 0.75rem;
  border-bottom: 2px solid ${color.N4};
`;

const SectionIcon = styled.div<{ $color: string }>`
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: ${(props) => props.$color};
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  flex-shrink: 0;
`;

const SectionTitle = styled.h2`
  font-size: 1.25rem;
  font-weight: 700;
  color: ${color.N10};
  margin: 0;
`;

const SectionCount = styled.span`
  font-size: 0.875rem;
  color: ${color.N7};
  font-weight: 500;
  margin-left: auto;
`;

const EmptyState = styled.div`
  text-align: center;
  padding: 3rem 1rem;
  color: ${color.N7};
`;

type FilterTab = "all" | "corpus" | "document" | "general";

/**
 * Global Discussions View
 * Shows all platform discussions with tabbed filtering
 * Part of Issue #623
 */
export const GlobalDiscussions: React.FC = () => {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<FilterTab>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [showCreateModal, setShowCreateModal] = useState(false);

  // Filter logic for showing sections based on active tab
  const showCorpusSection = activeTab === "all" || activeTab === "corpus";
  const showDocumentSection = activeTab === "all" || activeTab === "document";
  const showGeneralSection = activeTab === "all" || activeTab === "general";

  return (
    <Container>
      <Header>
        <TitleRow>
          <Title>Discussions</Title>
        </TitleRow>

        <FilterBar>
          <TabContainer>
            <Tab
              $isActive={activeTab === "all"}
              onClick={() => setActiveTab("all")}
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
            >
              <MessageSquare size={16} />
              All
            </Tab>
            <Tab
              $isActive={activeTab === "corpus"}
              onClick={() => setActiveTab("corpus")}
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
            >
              <Database size={16} />
              Corpus
            </Tab>
            <Tab
              $isActive={activeTab === "document"}
              onClick={() => setActiveTab("document")}
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
            >
              <FileText size={16} />
              Document
            </Tab>
            <Tab
              $isActive={activeTab === "general"}
              onClick={() => setActiveTab("general")}
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
            >
              <MessageSquare size={16} />
              General
            </Tab>
          </TabContainer>

          <SearchInputContainer>
            <SearchIcon size={18} />
            <SearchInput
              placeholder="Search discussions..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </SearchInputContainer>
        </FilterBar>
      </Header>

      <AnimatePresence>
        {showCorpusSection && (
          <SectionContainer
            key="corpus-section"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            transition={{ duration: 0.3 }}
          >
            <SectionHeader>
              <SectionIcon $color="linear-gradient(135deg, #667eea 0%, #764ba2 100%)">
                <Database size={18} />
              </SectionIcon>
              <SectionTitle>Corpus Discussions</SectionTitle>
              <SectionCount>(Loading...)</SectionCount>
            </SectionHeader>

            {/* ThreadList will be filtered by corpus context */}
            <EmptyState>
              Corpus discussions will appear here
              <br />
              (Requires corpus-specific filtering in ThreadList)
            </EmptyState>
          </SectionContainer>
        )}

        {showDocumentSection && (
          <SectionContainer
            key="document-section"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            transition={{ duration: 0.3, delay: 0.1 }}
          >
            <SectionHeader>
              <SectionIcon $color="linear-gradient(135deg, #f093fb 0%, #f5576c 100%)">
                <FileText size={18} />
              </SectionIcon>
              <SectionTitle>Document Discussions</SectionTitle>
              <SectionCount>(Loading...)</SectionCount>
            </SectionHeader>

            {/* ThreadList will be filtered by document context */}
            <EmptyState>
              Document discussions will appear here
              <br />
              (Requires document-specific filtering in ThreadList)
            </EmptyState>
          </SectionContainer>
        )}

        {showGeneralSection && (
          <SectionContainer
            key="general-section"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            transition={{ duration: 0.3, delay: 0.2 }}
          >
            <SectionHeader>
              <SectionIcon $color="linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)">
                <MessageSquare size={18} />
              </SectionIcon>
              <SectionTitle>General Discussions</SectionTitle>
              <SectionCount>(Loading...)</SectionCount>
            </SectionHeader>

            {/* ThreadList for general conversations (no corpus/document) */}
            <EmptyState>
              General discussions will appear here
              <br />
              (Requires filtering for threads without corpus/document)
            </EmptyState>
          </SectionContainer>
        )}
      </AnimatePresence>

      <FAB
        onClick={() => setShowCreateModal(true)}
        whileHover={{ scale: 1.1 }}
        whileTap={{ scale: 0.9 }}
        aria-label="Create new discussion"
      >
        <Plus size={28} />
      </FAB>

      {/* TODO: Wire up CreateThreadButton modal */}
      {showCreateModal && <div>Create thread modal placeholder</div>}
    </Container>
  );
};
