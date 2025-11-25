import { useState, useRef, useEffect, useMemo } from "react";
import { Tab, Menu } from "semantic-ui-react";
import _ from "lodash";
import { toast } from "react-toastify";
import {
  ApolloError,
  useLazyQuery,
  useMutation,
  useQuery,
  useReactiveVar,
} from "@apollo/client";
import { useLocation, useNavigate } from "react-router-dom";
import {
  FileText,
  MessageSquare,
  Table,
  Factory,
  Brain,
  Settings,
  Home,
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  Search,
  AlignJustify,
  Send,
  History,
  Trophy,
  BarChart3,
} from "lucide-react";
import styled from "styled-components";
import { motion, AnimatePresence } from "framer-motion";

import { ConfirmModal } from "../components/widgets/modals/ConfirmModal";
import { CorpusCards } from "../components/corpuses/CorpusCards";
import {
  CreateAndSearchBar,
  DropdownActionProps,
} from "../components/layout/CreateAndSearchBar";
import { CRUDModal } from "../components/widgets/CRUD/CRUDModal";
import { CardLayout } from "../components/layout/CardLayout";
import { CorpusBreadcrumbs } from "../components/corpuses/CorpusBreadcrumbs";
import { LabelSetSelector } from "../components/widgets/CRUD/LabelSetSelector";
import { EmbedderSelector } from "../components/widgets/CRUD/EmbedderSelector";
import {
  newCorpusForm_Ui_Schema,
  newCorpusForm_Schema,
  editCorpusForm_Schema,
  editCorpusForm_Ui_Schema,
} from "../components/forms/schemas";

import {
  openedCorpus,
  selectedDocumentIds,
  corpusSearchTerm,
  deletingCorpus,
  showRemoveDocsFromCorpusModal,
  editingCorpus,
  viewingCorpus,
  documentSearchTerm,
  authToken,
  annotationContentSearchTerm,
  openedDocument,
  selectedMetaAnnotationId,
  filterToLabelId,
  analysisSearchTerm,
  exportingCorpus,
  showQueryViewState,
  openedQueryObj,
  showSelectCorpusAnalyzerOrFieldsetModal,
} from "../graphql/cache";
import {
  UPDATE_CORPUS,
  UpdateCorpusOutputs,
  UpdateCorpusInputs,
  CREATE_CORPUS,
  CreateCorpusOutputs,
  CreateCorpusInputs,
  DELETE_CORPUS,
  DeleteCorpusOutputs,
  DeleteCorpusInputs,
  REMOVE_DOCUMENTS_FROM_CORPUS,
  RemoveDocumentsFromCorpusOutputs,
  RemoveDocumentsFromCorpusInputs,
  StartImportCorpusExport,
  StartImportCorpusInputs,
  START_IMPORT_CORPUS,
} from "../graphql/mutations";
import {
  GetCorpusesInputs,
  GetCorpusesOutputs,
  GetCorpusMetadataInputs,
  GetCorpusMetadataOutputs,
  GET_CORPUSES,
  GET_CORPUS_METADATA,
  GET_CORPUS_STATS,
  RequestDocumentsInputs,
  RequestDocumentsOutputs,
  GET_DOCUMENTS,
} from "../graphql/queries";
import { CorpusType, LabelType } from "../types/graphql-api";
import { LooseObject, PermissionTypes } from "../components/types";
import { toBase64 } from "../utils/files";
import { FilterToLabelSelector } from "../components/widgets/model-filters/FilterToLabelSelector";
import { ensureValidCorpusId } from "../utils/graphqlGuards";
import { CorpusAnnotationCards } from "../components/annotations/CorpusAnnotationCards";
import { CorpusDocumentCards } from "../components/documents/CorpusDocumentCards";
import { FolderDocumentBrowser } from "../components/corpuses/folders/FolderDocumentBrowser";
import { CorpusAnalysesCards } from "../components/analyses/CorpusAnalysesCards";
import { FilterToAnalysesSelector } from "../components/widgets/model-filters/FilterToAnalysesSelector";
import useWindowDimensions from "../components/hooks/WindowDimensionHook";
import { SelectExportTypeModal } from "../components/widgets/modals/SelectExportTypeModal";
import { ViewQueryResultsModal } from "../components/widgets/modals/ViewQueryResultsModal";
import { FilterToCorpusActionOutputs } from "../components/widgets/model-filters/FilterToCorpusActionOutputs";
import { CorpusExtractCards } from "../components/extracts/CorpusExtractCards";
import { getPermissions } from "../utils/transform";
import { MOBILE_VIEW_BREAKPOINT } from "../assets/configurations/constants";
import { useEnv } from "../components/hooks/UseEnv";
import { CorpusDashboard } from "../components/corpuses/CorpusDashboard";
import { useCorpusState } from "../components/annotator/context/CorpusAtom";
import { CorpusSettings } from "../components/corpuses/CorpusSettings";
import { CorpusChat } from "../components/corpuses/CorpusChat";
import { CorpusHome } from "../components/corpuses/CorpusHome";
import { CorpusDescriptionEditor } from "../components/corpuses/CorpusDescriptionEditor";
import { CorpusDiscussionsView } from "../components/discussions/CorpusDiscussionsView";
import { BadgeManagement } from "../components/badges/BadgeManagement";
import { CorpusEngagementDashboard } from "../components/analytics/CorpusEngagementDashboard";

// Add these styled components near your other styled components
const DashboardContainer = styled.div`
  display: flex;
  flex-direction: column;
  flex: 1;
  position: relative;
  overflow: hidden;
  padding: 0;
  width: 100%;
  min-height: 0;
  max-height: 100%; /* Never exceed parent's height */
  height: 100%;
`;

const ContentWrapper = styled.div`
  display: flex;
  flex-direction: column;
  align-items: stretch;
  justify-content: flex-start;
  flex: 1;
  padding: 0;
  overflow: hidden;
  min-height: 0;
  max-height: 100%; /* Never exceed parent's height */
  height: 100%;
  position: relative;
`;

const ChatTransitionContainer = styled.div<{
  $isExpanded: boolean;
  $isSearchTransform?: boolean;
}>`
  display: flex;
  flex-direction: column;
  height: ${(props) =>
    props.$isSearchTransform ? (props.$isExpanded ? "100%" : "auto") : "100%"};
  transition: all 0.5s cubic-bezier(0.16, 1, 0.3, 1);
  background: white;
  border-radius: ${(props) => (props.$isExpanded ? "0" : "16px")};
  box-shadow: ${(props) =>
    props.$isExpanded ? "none" : "0 8px 24px rgba(0,0,0,0.12)"};
  overflow: hidden;
  position: relative;
  z-index: ${(props) => (props.$isExpanded ? "10" : "1")};
`;

const SearchToConversationInput = styled.div<{ $isExpanded: boolean }>`
  display: flex;
  align-items: center;
  padding: ${(props) =>
    props.$isExpanded ? "1.25rem 1.5rem" : "1rem 1.25rem"};
  border-bottom: ${(props) =>
    props.$isExpanded ? "1px solid rgba(226, 232, 240, 0.8)" : "none"};
  background: ${(props) =>
    props.$isExpanded ? "rgba(255, 255, 255, 0.98)" : "transparent"};
  backdrop-filter: ${(props) => (props.$isExpanded ? "blur(12px)" : "none")};
  box-shadow: ${(props) =>
    props.$isExpanded ? "0 2px 8px rgba(0, 0, 0, 0.04)" : "none"};

  input {
    flex: 1;
    border: none;
    outline: none;
    font-size: 1rem;
    background: transparent;
    color: #0f172a;

    &::placeholder {
      color: #94a3b8;
    }
  }

  .actions {
    display: flex;
    gap: 0.75rem;
  }

  .nav-button {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    color: #4a5568;
    font-weight: 500;
    background: transparent;
    border: none;
    padding: 0.625rem 0.875rem;
    cursor: pointer;
    transition: all 0.2s ease;
    border-radius: 8px;

    &:hover {
      background: rgba(0, 0, 0, 0.04);
      color: #2d3748;
    }

    .button-text {
      @media (max-width: 768px) {
        display: none;
      }
    }
  }
`;

// Add new styled components for enhanced UI
const FloatingSearchContainer = styled(motion.div)`
  background: white;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  border: 1px solid #e2e8f0;
  overflow: hidden;
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0.375rem;
  width: 100px;
  max-width: 720px;
  min-height: 42px;
  height: auto;
  transition: all 0.35s ease;
  margin: 0 auto;

  /* Add gap to form children only when expanded */
  & > form {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0;
    transition: gap 0.35s ease, justify-content 0.35s ease;
    width: 100%;
  }

  &:hover,
  &:focus-within {
    width: min(720px, 90%);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
    border-color: #cbd5e1;
    align-items: flex-start;
    justify-content: flex-start;
    padding: 0.75rem;

    & > form {
      gap: 0.75rem;
      justify-content: flex-start;
    }
  }

  @media (max-width: 768px) {
    width: clamp(80px, 20vw, 96px);
    max-width: calc(100vw - 2rem);
    min-height: 40px;
    padding: 0.375rem;

    &:active,
    &:hover,
    &:focus-within {
      width: 85%;
      max-width: 320px;
      padding: 0.5rem;

      & > form {
        gap: 0.5rem;
        justify-content: flex-start;
      }
    }
  }
`;

// Hide the input until hover/focus
const EnhancedSearchInput = styled.textarea`
  flex: 1;
  width: 0;
  opacity: 0;
  padding: 0;
  border: none;
  outline: none;
  font-size: 1rem;
  background: transparent;
  color: #0f172a;
  font-weight: 500;
  transition: all 0.35s ease; /* match container timing */
  resize: none;
  font-family: inherit;
  line-height: 1.5;
  min-height: 40px;
  max-height: 144px; /* ~6 lines at 1.5 line-height */
  overflow-y: auto;
  min-width: 0; /* ensure it can shrink properly */

  /* Custom scrollbar for textarea */
  &::-webkit-scrollbar {
    width: 6px;
  }

  &::-webkit-scrollbar-track {
    background: #f1f5f9;
    border-radius: 3px;
  }

  &::-webkit-scrollbar-thumb {
    background: #cbd5e1;
    border-radius: 3px;
  }

  &::placeholder {
    color: #94a3b8;
    font-weight: 400;
  }

  ${FloatingSearchContainer}:hover &,
  ${FloatingSearchContainer}:focus-within & {
    width: 100%;
    opacity: 1;
    padding: 0.75rem 1rem;
    min-height: 40px;
  }

  @media (max-width: 768px) {
    font-size: 0.875rem;
    max-height: 120px; /* ~5-6 lines on mobile */

    ${FloatingSearchContainer}:hover &,
    ${FloatingSearchContainer}:focus-within & {
      padding: 0.625rem 0.875rem;
      width: 100%;
    }
  }
`;

const SearchActionsContainer = styled.div`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-shrink: 0;

  @media (max-width: 768px) {
    gap: 0.375rem;
  }
`;

const ActionButton = styled(motion.button)`
  width: 38px;
  height: 38px;
  border-radius: 8px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  color: #64748b;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s ease;
  flex-shrink: 0;

  &:hover:not(:disabled) {
    background: #e2e8f0;
    color: #475569;
  }

  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  &.primary {
    background: #4a90e2;
    color: white;
    border-color: #4a90e2;

    &:hover:not(:disabled) {
      background: #357abd;
      border-color: #357abd;
    }
  }

  @media (max-width: 768px) {
    width: 36px;
    height: 36px;

    svg {
      width: 16px;
      height: 16px;
    }
  }
`;

const ChatNavigationHeader = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.5rem;
  background: white;
  border-bottom: 1px solid rgba(226, 232, 240, 0.8);
  position: sticky;
  top: 0;
  z-index: 10;
  backdrop-filter: blur(12px);
  background: rgba(255, 255, 255, 0.95);
`;

const NavigationTitle = styled.div`
  font-size: 1.125rem;
  font-weight: 600;
  color: #0f172a;
  flex: 1;
  text-align: center;
`;

const BackButton = styled(motion.button)`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  background: transparent;
  border: none;
  color: #64748b;
  font-weight: 500;
  cursor: pointer;
  border-radius: 8px;
  transition: all 0.2s ease;

  &:hover {
    background: #f8fafc;
    color: #475569;
  }

  @media (max-width: 768px) {
    padding: 0.5rem;

    span {
      display: none;
    }
  }
`;

// Create a component for the corpus query view with the new search-to-chat functionality
const CorpusQueryView = ({
  opened_corpus,
  opened_corpus_id,
  setShowDescriptionEditor,
  onNavigate,
  onBack,
  canUpdate,
  stats,
  statsLoading,
}: {
  opened_corpus: CorpusType | null;
  opened_corpus_id: string | null;
  setShowDescriptionEditor: (show: boolean) => void;
  onNavigate?: (tabIndex: number) => void;
  onBack?: () => void;
  canUpdate?: boolean;
  stats: {
    totalDocs: number;
    totalAnnotations: number;
    totalAnalyses: number;
    totalExtracts: number;
  };
  statsLoading: boolean;
}) => {
  const [chatExpanded, setChatExpanded] = useState<boolean>(false);
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [isSearchMode, setIsSearchMode] = useState<boolean>(true);
  const show_query_view_state = useReactiveVar(showQueryViewState);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const { width } = useWindowDimensions();
  const isDesktop = width > MOBILE_VIEW_BREAKPOINT;

  // Focus the input on initial mount (desktop only to avoid mobile keyboard issues)
  useEffect(() => {
    if (isDesktop && inputRef.current) {
      // Use longer timeout on mount to ensure DOM is ready
      setTimeout(() => inputRef.current?.focus(), 150);
    }
  }, []); // Empty deps = run only on mount

  // Focus the input when returning to search mode
  useEffect(() => {
    if (isSearchMode && inputRef.current && isDesktop) {
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [isSearchMode, isDesktop]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchQuery.trim()) {
      setChatExpanded(true);
      setIsSearchMode(false);
      // Ensure we stay in ASK mode rather than switching to VIEW
      showQueryViewState("ASK");
    }
  };

  const resetToSearch = () => {
    setChatExpanded(false);
    setIsSearchMode(true);
    setSearchQuery("");
    setTimeout(() => {
      if (inputRef.current) {
        inputRef.current.focus();
      }
    }, 100);
  };

  const openHistoryView = () => {
    showQueryViewState("VIEW");
  };

  if (!opened_corpus) {
    return <div>No corpus selected</div>;
  }

  // Render the navigation header consistently across all states
  const renderNavigationHeader = () => {
    if (chatExpanded || show_query_view_state === "VIEW") {
      // On mobile, CorpusChat renders its own header, so skip rendering here
      if (!isDesktop) {
        return null;
      }

      return (
        <ChatNavigationHeader>
          <BackButton
            onClick={
              show_query_view_state === "VIEW"
                ? () => showQueryViewState("ASK")
                : resetToSearch
            }
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
          >
            <ArrowLeft size={18} />
            <span>
              {show_query_view_state === "VIEW" ? "Back to Dashboard" : "Back"}
            </span>
          </BackButton>

          <NavigationTitle>
            {show_query_view_state === "VIEW" ? "Conversation History" : "Chat"}
          </NavigationTitle>

          <SearchActionsContainer>
            {show_query_view_state !== "VIEW" && (
              <ActionButton
                onClick={openHistoryView}
                title="View conversation history"
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
              >
                <History size={18} />
              </ActionButton>
            )}
            <ActionButton
              onClick={() => showQueryViewState("ASK")}
              title="Return to Dashboard"
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
            >
              <Home size={18} />
            </ActionButton>
          </SearchActionsContainer>
        </ChatNavigationHeader>
      );
    }

    return null;
  };

  if (show_query_view_state === "ASK") {
    // If we're in chat mode, render full-screen chat
    if (chatExpanded) {
      return (
        <motion.div
          id="corpus-chat-container-motion-div"
          style={{
            flex: 1,
            display: "flex",
            flexDirection: "column",
            overflow: "hidden",
            minHeight: 0,
            maxHeight: "99vh", // Never exceed 99vh regardless of content
            height: "100%",
          }}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.3 }}
        >
          {renderNavigationHeader()}
          <CorpusChat
            corpusId={opened_corpus.id}
            showLoad={false}
            initialQuery={searchQuery}
            setShowLoad={() => {}}
            onMessageSelect={() => {}}
            forceNewChat={true}
            onClose={resetToSearch}
          />
        </motion.div>
      );
    }

    // Otherwise, show the dashboard view with the search bar
    return (
      <motion.div
        style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
          minHeight: 0,
          maxHeight: "99vh", // Never exceed 99vh regardless of content
          height: "100%",
          width: "100%",
        }}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.3 }}
      >
        <DashboardContainer id="corpus-dashboard-container">
          <ContentWrapper
            id="corpus-dashboard-content-wrapper"
            style={{ position: "relative" }}
          >
            <CorpusHome
              corpus={opened_corpus as CorpusType}
              onEditDescription={() => setShowDescriptionEditor(true)}
              onNavigate={onNavigate}
              onBack={onBack}
              canUpdate={canUpdate}
              stats={stats}
              statsLoading={statsLoading}
            />
            <div
              style={{
                position: "absolute",
                bottom: width <= 768 ? "1rem" : "2rem",
                left: "50%",
                transform: "translateX(-50%)",
                display: "flex",
                flexDirection: "row",
                justifyContent: "center",
                alignItems: "center",
                padding: width <= 768 ? "0.25rem" : "0.5rem",
                width:
                  width <= 768
                    ? "95%"
                    : "85%" /* give more room for expansion on mobile */,
                maxWidth: "760px" /* match the search container max */,
              }}
            >
              <FloatingSearchContainer
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, delay: 0.1 }}
              >
                <form onSubmit={handleSearchSubmit}>
                  <EnhancedSearchInput
                    ref={inputRef}
                    placeholder="Ask a question about this corpus..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    autoFocus={isDesktop} // Auto-focus on desktop only to avoid mobile keyboard popup issues
                    onKeyDown={(e) => {
                      // Submit on Enter without Shift
                      if (
                        e.key === "Enter" &&
                        !e.shiftKey &&
                        searchQuery.trim()
                      ) {
                        e.preventDefault();
                        handleSearchSubmit(e);
                      }
                    }}
                    rows={1}
                  />
                  <SearchActionsContainer>
                    <ActionButton
                      type="button"
                      onClick={openHistoryView}
                      title="View conversation history"
                      whileHover={{ scale: 1.05 }}
                      whileTap={{ scale: 0.95 }}
                    >
                      <History size={18} />
                    </ActionButton>
                    <ActionButton
                      type="submit"
                      className="primary"
                      disabled={!searchQuery.trim()}
                      whileHover={searchQuery.trim() ? { scale: 1.05 } : {}}
                      whileTap={searchQuery.trim() ? { scale: 0.95 } : {}}
                    >
                      <Send size={18} />
                    </ActionButton>
                  </SearchActionsContainer>
                </form>
              </FloatingSearchContainer>
            </div>
          </ContentWrapper>
        </DashboardContainer>
      </motion.div>
    );
  } else {
    return (
      <motion.div
        style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          minHeight: 0,
          maxHeight: "99vh", // Never exceed 99vh regardless of content
          height: "100%",
        }}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.3 }}
      >
        {renderNavigationHeader()}

        <div
          style={{
            flex: 1,
            display: "flex",
            flexDirection: "column",
            overflow: "hidden",
            minHeight: 0,
            maxHeight: "100%",
            height: "100%",
          }}
        >
          <CorpusChat
            corpusId={opened_corpus.id}
            showLoad={true}
            setShowLoad={() => {}}
            onMessageSelect={() => {}}
          />
        </div>
      </motion.div>
    );
  }
};

// Add new styled components for the sidebar navigation
const CorpusViewContainer = styled.div`
  display: flex;
  flex-direction: row;
  width: 100%;
  position: relative;
  overflow: hidden;
  flex: 1;
  align-items: stretch;
  min-height: 0;
  max-height: 100vh;
  height: 100%;
`;

const NavigationSidebar = styled(motion.div)<{ $isExpanded: boolean }>`
  position: relative;
  width: ${(props) => (props.$isExpanded ? "280px" : "72px")};
  background: linear-gradient(180deg, #ffffff 0%, #fafbfc 50%, #f8f9fa 100%);
  backdrop-filter: blur(10px);
  border-right: 1px solid #e2e8f0;
  box-shadow: ${(props) =>
    props.$isExpanded
      ? "2px 0 8px rgba(0, 0, 0, 0.06)"
      : "2px 0 4px rgba(0, 0, 0, 0.04)"};
  z-index: 100;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  flex-shrink: 0;

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    position: fixed;
    left: 50%;
    bottom: 0;
    width: 100%;
    max-width: min(480px, 95vw);
    height: ${(props) => (props.$isExpanded ? "70vh" : "0")};
    max-height: min(600px, 70vh);
    border-right: none;
    border-top: 1px solid #e2e8f0;
    border-radius: 24px 24px 0 0;
    box-shadow: ${(props) =>
      props.$isExpanded ? "0 -8px 32px rgba(0, 0, 0, 0.12)" : "none"};
    transform: translate(
      -50%,
      ${(props) => (props.$isExpanded ? "0" : "100%")}
    );
    transition: transform 0.35s cubic-bezier(0.4, 0, 0.2, 1),
      height 0.35s cubic-bezier(0.4, 0, 0.2, 1);
    z-index: 200;
    background: linear-gradient(180deg, #ffffff 0%, #fafbfc 100%);
  }
`;

// Drag handle for bottom sheet
const BottomSheetHandle = styled.div`
  display: none;

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    display: flex;
    justify-content: center;
    padding: 0.75rem 0;
    cursor: grab;

    &::after {
      content: "";
      width: 40px;
      height: 4px;
      background: #cbd5e1;
      border-radius: 2px;
      transition: background 0.2s ease;
    }

    &:active {
      cursor: grabbing;

      &::after {
        background: #94a3b8;
      }
    }
  }
`;

const NavigationHeader = styled.div<{ $isExpanded: boolean }>`
  padding: 1.5rem;
  border-bottom: 1px solid #e2e8f0;
  background: white;
  display: flex;
  align-items: center;
  justify-content: ${(props) =>
    props.$isExpanded ? "space-between" : "center"};
  min-height: 72px;
  position: relative;
  gap: 0.75rem;

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    padding: 0 1.5rem 1rem;
    min-height: auto;
  }
`;

const NavigationToggle = styled(motion.button)`
  width: 40px;
  height: 40px;
  border-radius: 12px;
  background: linear-gradient(
    135deg,
    rgba(255, 255, 255, 0.9) 0%,
    rgba(248, 250, 252, 0.9) 100%
  );
  border: 1px solid rgba(226, 232, 240, 0.6);
  color: #64748b;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.04), 0 1px 2px rgba(0, 0, 0, 0.06);
  position: relative;
  overflow: hidden;

  /* Ripple effect base */
  &::before {
    content: "";
    position: absolute;
    top: 50%;
    left: 50%;
    width: 0;
    height: 0;
    border-radius: 50%;
    background: radial-gradient(
      circle,
      rgba(74, 144, 226, 0.2) 0%,
      transparent 70%
    );
    transform: translate(-50%, -50%);
    transition: width 0.4s, height 0.4s;
  }

  &:hover {
    background: linear-gradient(
      135deg,
      rgba(74, 144, 226, 0.1) 0%,
      rgba(99, 102, 241, 0.08) 100%
    );
    border-color: rgba(74, 144, 226, 0.3);
    color: #4a90e2;
    transform: translateY(-1px);
    box-shadow: 0 4px 6px rgba(74, 144, 226, 0.1), 0 2px 4px rgba(0, 0, 0, 0.06);

    &::before {
      width: 80px;
      height: 80px;
    }

    svg {
      transform: scale(1.1);
    }
  }

  &:active {
    transform: translateY(0);
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
  }

  svg {
    width: 20px;
    height: 20px;
    transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    z-index: 1;
  }
`;

const NavigationItems = styled.div`
  flex: 1;
  padding: 1rem 0;
  overflow-y: auto;
  overflow-x: hidden;
  position: relative;

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    padding: 0.5rem 0 2rem;
  }

  /* Fade effect at top and bottom */
  &::before,
  &::after {
    content: "";
    position: absolute;
    left: 0;
    right: 0;
    height: 20px;
    pointer-events: none;
    z-index: 1;
    opacity: 0;
    transition: opacity 0.3s ease;
  }

  &::before {
    top: 0;
    background: linear-gradient(
      180deg,
      rgba(255, 255, 255, 0.9) 0%,
      transparent 100%
    );
  }

  &::after {
    bottom: 0;
    background: linear-gradient(
      0deg,
      rgba(255, 255, 255, 0.9) 0%,
      transparent 100%
    );
  }

  /* Show fade when scrollable */
  &:hover::before,
  &:hover::after {
    opacity: 1;
  }

  /* Custom scrollbar styling */
  &::-webkit-scrollbar {
    width: 6px;
  }

  &::-webkit-scrollbar-track {
    background: transparent;
    margin: 8px 0;
  }

  &::-webkit-scrollbar-thumb {
    background: linear-gradient(
      180deg,
      rgba(226, 232, 240, 0.8) 0%,
      rgba(203, 213, 225, 0.8) 100%
    );
    border-radius: 3px;
    border: 1px solid rgba(255, 255, 255, 0.3);
    transition: all 0.2s ease;

    &:hover {
      background: linear-gradient(
        180deg,
        rgba(203, 213, 225, 0.9) 0%,
        rgba(148, 163, 184, 0.9) 100%
      );
      box-shadow: 0 0 0 1px rgba(74, 144, 226, 0.2);
    }

    &:active {
      background: linear-gradient(
        180deg,
        rgba(148, 163, 184, 1) 0%,
        rgba(100, 116, 139, 1) 100%
      );
    }
  }

  /* Firefox scrollbar support */
  scrollbar-width: thin;
  scrollbar-color: rgba(203, 213, 225, 0.8) transparent;
`;

// Badge for count display on navigation items
const NavItemBadge = styled.span<{ isActive: boolean }>`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 22px;
  height: 22px;
  padding: 0 6px;
  border-radius: 11px;
  font-size: 0.6875rem;
  font-weight: 600;
  margin-left: auto;
  background: ${(props) =>
    props.isActive
      ? "linear-gradient(135deg, #4a90e2 0%, #357abd 100%)"
      : "#e2e8f0"};
  color: ${(props) => (props.isActive ? "white" : "#64748b")};
  transition: all 0.2s ease;
  box-shadow: ${(props) =>
    props.isActive
      ? "0 2px 4px rgba(74, 144, 226, 0.3)"
      : "0 1px 2px rgba(0, 0, 0, 0.05)"};
`;

const NavigationItem = styled(motion.button)<{
  isActive: boolean;
  $isExpanded: boolean;
}>`
  width: 100%;
  display: flex;
  align-items: center;
  gap: ${(props) => (props.$isExpanded ? "0.75rem" : "0")};
  padding: ${(props) =>
    props.$isExpanded ? "0.875rem 1rem 0.875rem 1.5rem" : "0.875rem"};
  margin: ${(props) => (props.$isExpanded ? "0 0.5rem" : "0 0.25rem")};
  width: ${(props) =>
    props.$isExpanded ? "calc(100% - 1rem)" : "calc(100% - 0.5rem)"};
  border-radius: ${(props) => (props.$isExpanded ? "12px" : "10px")};
  background: ${(props) => {
    if (props.isActive) {
      return `linear-gradient(
        135deg,
        rgba(74, 144, 226, 0.12) 0%,
        rgba(99, 102, 241, 0.08) 100%
      )`;
    }
    return "transparent";
  }};
  border: 1px solid
    ${(props) => (props.isActive ? "rgba(74, 144, 226, 0.2)" : "transparent")};
  color: ${(props) => (props.isActive ? "#4a90e2" : "#64748b")};
  font-weight: ${(props) => (props.isActive ? "600" : "500")};
  font-size: 0.9375rem;
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  position: relative;
  justify-content: ${(props) => (props.$isExpanded ? "flex-start" : "center")};
  overflow: hidden;
  min-height: ${(props) => (props.$isExpanded ? "48px" : "44px")};

  /* Active indicator bar */
  &::before {
    content: "";
    position: absolute;
    left: ${(props) => (props.$isExpanded ? "-0.5rem" : "50%")};
    top: ${(props) => (props.$isExpanded ? "50%" : "0")};
    width: ${(props) => (props.$isExpanded ? "4px" : "60%")};
    height: ${(props) => (props.$isExpanded ? "60%" : "2px")};
    background: linear-gradient(
      ${(props) => (props.$isExpanded ? "180deg" : "90deg")},
      #4a90e2 0%,
      #6366f1 100%
    );
    opacity: ${(props) => (props.isActive ? "1" : "0")};
    transform: ${(props) =>
      props.$isExpanded ? "translateY(-50%)" : "translateX(-50%)"};
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    border-radius: 2px;
    box-shadow: ${(props) =>
      props.isActive ? "0 0 8px rgba(74, 144, 226, 0.5)" : "none"};
  }

  /* Hover background effect */
  &::after {
    content: "";
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: radial-gradient(
      circle at center,
      rgba(74, 144, 226, 0.08) 0%,
      transparent 70%
    );
    opacity: 0;
    transition: opacity 0.3s ease;
    pointer-events: none;
  }

  &:hover {
    background: ${(props) => {
      if (props.isActive) {
        return `linear-gradient(
          135deg,
          rgba(74, 144, 226, 0.16) 0%,
          rgba(99, 102, 241, 0.12) 100%
        )`;
      }
      return `linear-gradient(
        135deg,
        rgba(226, 232, 240, 0.3) 0%,
        rgba(241, 245, 249, 0.2) 100%
      )`;
    }};
    border-color: ${(props) =>
      props.isActive ? "rgba(74, 144, 226, 0.3)" : "rgba(226, 232, 240, 0.5)"};
    color: ${(props) => (props.isActive ? "#4a90e2" : "#475569")};
    transform: ${(props) =>
      props.$isExpanded ? "translateX(2px)" : "scale(1.05)"};

    &::after {
      opacity: 1;
    }

    svg {
      transform: ${(props) =>
        props.isActive ? "scale(1.15) rotate(-5deg)" : "scale(1.1)"};
      filter: ${(props) =>
        props.isActive
          ? "drop-shadow(0 2px 4px rgba(74, 144, 226, 0.3))"
          : "none"};
    }
  }

  &:active {
    transform: ${(props) =>
      props.$isExpanded ? "translateX(0)" : "scale(0.98)"};
  }

  svg {
    width: 20px;
    height: 20px;
    flex-shrink: 0;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    z-index: 1;
  }

  span {
    white-space: nowrap;
    opacity: ${(props) => (props.$isExpanded ? "1" : "0")};
    width: ${(props) => (props.$isExpanded ? "auto" : "0")};
    overflow: hidden;
    transition: opacity 0.3s ease, width 0.3s ease;
    z-index: 1;
  }

  /* Accessibility - focus visible */
  &:focus-visible {
    outline: 2px solid #4a90e2;
    outline-offset: 2px;
  }

  /* Respect reduced motion preferences */
  @media (prefers-reduced-motion: reduce) {
    transition: background-color 0.2s ease, color 0.2s ease;

    &:hover {
      transform: none;
    }

    svg {
      transition: none;
      transform: none !important;
    }
  }
`;

const MainContentArea = styled.div<{ $sidebarExpanded: boolean }>`
  flex: 1;
  overflow: hidden;
  position: relative;
  display: flex;
  flex-direction: column;
  min-height: 0;
  min-width: 0;
  max-height: 100%;
  height: 100%;

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    margin-left: 0;
    /* No extra padding needed - FAB is compact and positioned absolutely */
  }
`;

const MobileMenuBackdrop = styled(motion.div)`
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.4);
  backdrop-filter: blur(8px);
  z-index: 190;
  display: none;
  -webkit-tap-highlight-color: transparent;

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    display: block;
  }
`;

// Unified search bar wrapper with integrated back button
const SearchBarWithNav = styled.div`
  display: flex;
  align-items: stretch;
  width: 100%;
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
  transition: all 0.2s ease;

  &:focus-within {
    border-color: #cbd5e1;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.08);
  }
`;

// Integrated back button - no separate border, part of unified container
const MobileBackButton = styled.button`
  display: none;
  padding: 0 0.875rem;
  min-width: auto;
  background: transparent;
  border: none;
  border-right: 1px solid #e2e8f0;
  color: #64748b;
  transition: all 0.2s ease;
  cursor: pointer;
  flex-shrink: 0;

  &:hover {
    background: #f8fafc;
    color: #475569;
  }

  &:active {
    background: #f1f5f9;
  }

  svg {
    width: 20px;
    height: 20px;
  }

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    display: flex;
    align-items: center;
    justify-content: center;
  }
`;

// Mobile bottom navigation FAB - ultra sleek and compact
const BottomNavigationHandle = styled(motion.button)<{ isOpen?: boolean }>`
  display: none;
  position: fixed;
  bottom: 16px;
  right: 16px; /* Moved to bottom-right */
  width: 56px;
  height: 56px;
  background: linear-gradient(135deg, #4a90e2 0%, #357abd 100%);
  border: none;
  border-radius: 16px;
  cursor: pointer;
  z-index: 100;
  box-shadow: 0 8px 24px rgba(74, 144, 226, 0.4), 0 2px 8px rgba(0, 0, 0, 0.12);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  padding: 0;
  align-items: center;
  justify-content: center;
  color: white;

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    display: flex;
  }

  &:active {
    transform: scale(0.95);
  }

  &:hover {
    box-shadow: 0 12px 32px rgba(74, 144, 226, 0.5),
      0 4px 12px rgba(0, 0, 0, 0.15);
  }

  svg {
    width: 28px;
    height: 28px;
    filter: drop-shadow(0 1px 2px rgba(0, 0, 0, 0.2));
  }
`;

// Removed unused bottom handle components - now using simple FAB design

// Back navigation header for non-home tabs - CRISPY VERSION
const TabNavigationHeader = styled.div`
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.875rem 1.25rem;
  background: white;
  border-bottom: 1px solid #e2e8f0;
  flex-shrink: 0;
  min-height: 56px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    padding: 0.625rem 1rem;
    min-height: 48px;
  }
`;

const BackNavButton = styled(motion.button)`
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  color: #64748b;
  cursor: pointer;
  padding: 0;
  width: 36px;
  height: 36px;
  border-radius: 10px;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  flex-shrink: 0;

  &:hover {
    background: white;
    border-color: #4a90e2;
    color: #4a90e2;
    box-shadow: 0 2px 8px rgba(74, 144, 226, 0.15);
  }

  &:active {
    transform: scale(0.95);
  }

  svg {
    width: 20px;
    height: 20px;
    stroke-width: 2.5;
  }

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    width: 32px;
    height: 32px;

    svg {
      width: 18px;
      height: 18px;
    }
  }
`;

const TabTitle = styled.h2`
  font-size: 1.5rem;
  font-weight: 800;
  color: #0f172a;
  margin: 0;
  flex: 1;
  letter-spacing: -0.025em;
  line-height: 1;

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    font-size: 1.25rem;
  }
`;

const SearchBarContainer = styled.div`
  flex: 1;
  display: flex;
  min-width: 0; /* Allows flex item to shrink below its content size */

  /* Override CreateAndSearchBar's internal styles to remove duplicate borders */
  > div {
    width: 100%;
    border: none !important;
    box-shadow: none !important;
    border-radius: 0 !important;

    /* Override the SearchInputWrapper max-width on mobile */
    > div:first-child {
      @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
        max-width: none;
        flex: 1;
      }
    }
  }
`;

const NotificationBadge = styled.div`
  position: absolute;
  top: -6px;
  right: -6px;
  min-width: 20px;
  height: 20px;
  padding: 0 6px;
  background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
  color: white;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.7rem;
  font-weight: 700;
  box-shadow: 0 2px 4px rgba(239, 68, 68, 0.3),
    0 0 0 2px rgba(255, 255, 255, 0.9);
  animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
  z-index: 2;

  @keyframes pulse {
    0%,
    100% {
      opacity: 1;
      transform: scale(1);
    }
    50% {
      opacity: 0.9;
      transform: scale(1.05);
    }
  }

  /* Respect reduced motion preferences */
  @media (prefers-reduced-motion: reduce) {
    animation: none;
  }
`;

export const Corpuses = () => {
  const { width } = useWindowDimensions();

  const use_mobile_layout = width <= MOBILE_VIEW_BREAKPOINT;

  const show_remove_docs_from_corpus_modal = useReactiveVar(
    showRemoveDocsFromCorpusModal
  );
  const selected_metadata_id_to_filter_on = useReactiveVar(
    selectedMetaAnnotationId
  );

  // CRITICAL: Only call useCorpusState ONCE to avoid infinite re-renders
  // Calling it multiple times creates new object references each time
  const corpusState = useCorpusState();
  const {
    setCorpus,
    canUpdateCorpus,
    myPermissions: corpusAtomPermissions,
  } = corpusState;

  const selected_document_ids = useReactiveVar(selectedDocumentIds);
  const document_search_term = useReactiveVar(documentSearchTerm);
  const corpus_search_term = useReactiveVar(corpusSearchTerm);
  const analysis_search_term = useReactiveVar(analysisSearchTerm);
  const deleting_corpus = useReactiveVar(deletingCorpus);
  const corpus_to_edit = useReactiveVar(editingCorpus);
  const corpus_to_view = useReactiveVar(viewingCorpus);
  const opened_corpus = useReactiveVar(openedCorpus);

  const exporting_corpus = useReactiveVar(exportingCorpus);
  const opened_document = useReactiveVar(openedDocument);
  const filter_to_label_id = useReactiveVar(filterToLabelId);

  const auth_token = useReactiveVar(authToken);
  const annotation_search_term = useReactiveVar(annotationContentSearchTerm);
  const show_query_view_state = useReactiveVar(showQueryViewState);
  const opened_query_obj = useReactiveVar(openedQueryObj);

  const location = useLocation();
  const navigate = useNavigate();

  const corpusUploadRef = useRef() as React.MutableRefObject<HTMLInputElement>;

  const [show_multi_delete_confirm, setShowMultiDeleteConfirm] =
    useState<boolean>(false);
  const [show_new_corpus_modal, setShowNewCorpusModal] =
    useState<boolean>(false);
  const [active_tab, setActiveTab] = useState<number>(0);
  const [showDescriptionEditor, setShowDescriptionEditor] =
    useState<boolean>(false);
  const [sidebarExpanded, setSidebarExpanded] = useState<boolean>(
    () => width > MOBILE_VIEW_BREAKPOINT
  ); // Expanded by default on desktop
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState<boolean>(false);
  const { REACT_APP_ALLOW_IMPORTS } = useEnv();

  const [corpusSearchCache, setCorpusSearchCache] =
    useState<string>(corpus_search_term);
  const [analysesSearchCache, setAnalysesSearchCache] =
    useState<string>(analysis_search_term);
  const [documentSearchCache, setDocumentSearchCache] =
    useState<string>(document_search_term);
  const [annotationSearchCache, setAnnotationSearchCache] = useState<string>(
    annotation_search_term
  );

  const opened_corpus_id = opened_corpus?.id ? opened_corpus.id : null;
  let raw_permissions = opened_corpus?.myPermissions;
  if (opened_corpus && raw_permissions !== undefined) {
    raw_permissions = getPermissions(raw_permissions);
  }

  /**
   * Set up the debounced search handling for the two SearchBars (Corpus search is rendered first by this component,
   * but it will switch to doc search if you select a corpus, as this will navigate to show the corpus' docs)
   */
  const debouncedCorpusSearch = useRef(
    _.debounce((searchTerm) => {
      corpusSearchTerm(searchTerm);
    }, 1000)
  );

  const debouncedDocumentSearch = useRef(
    _.debounce((searchTerm) => {
      documentSearchTerm(searchTerm);
    }, 1000)
  );

  const debouncedAnnotationSearch = useRef(
    _.debounce((searchTerm) => {
      annotationContentSearchTerm(searchTerm);
    }, 1000)
  );

  const debouncedAnalysisSearch = useRef(
    _.debounce((searchTerm) => {
      analysisSearchTerm(searchTerm);
    }, 1000)
  );

  const handleCorpusSearchChange = (value: string) => {
    setCorpusSearchCache(value);
    debouncedCorpusSearch.current(value);
  };

  const handleDocumentSearchChange = (value: string) => {
    setDocumentSearchCache(value);
    debouncedDocumentSearch.current(value);
  };

  const handleAnnotationSearchChange = (value: string) => {
    setAnnotationSearchCache(value);
    debouncedAnnotationSearch.current(value);
  };

  const handleAnalysisSearchChange = (value: string) => {
    setAnalysesSearchCache(value);
    debouncedAnalysisSearch.current(value);
  };

  ///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
  // Setup document resolvers and mutations
  ///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
  const [startImportCorpus, {}] = useMutation<
    StartImportCorpusExport,
    StartImportCorpusInputs
  >(START_IMPORT_CORPUS, {
    onCompleted: () => {
      toast.success("SUCCESS!\vCorpus file upload and import has started.");
      // Note: Import is async, stats will update via polling
    },
    onError: (error: ApolloError) =>
      toast.error(`Could Not Start Import: ${error.message}`),
  });

  ///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
  // Query to get corpuses
  ///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
  // CRITICAL: Memoize corpus_variables to prevent infinite re-renders
  // Creating new object on every render causes Apollo to refetch → cache update → re-render → new object → LOOP
  const corpus_variables = useMemo(() => {
    const vars: LooseObject = {};
    if (corpus_search_term) {
      vars["textSearch"] = corpus_search_term;
    }
    return vars;
  }, [corpus_search_term]);

  // Now that auth is guaranteed to be ready before this component renders,
  // we can use a regular useQuery
  const {
    refetch: refetchCorpuses,
    loading: loading_corpuses,
    error: corpus_load_error,
    data: corpus_response,
    fetchMore: fetchMoreCorpusesOrig,
  } = useQuery<GetCorpusesOutputs, GetCorpusesInputs>(GET_CORPUSES, {
    variables: corpus_variables,
    // CHANGED from "network-only" to "cache-and-network" to prevent infinite refetch loops
    // "network-only" bypasses cache and refetches on EVERY render, causing infinite loops
    // "cache-and-network" uses cache immediately and fetches in background for updates
    fetchPolicy: "cache-and-network",
    notifyOnNetworkStatusChange: true, // required to get loading signal on fetchMore
  });

  /* --------------------------------------------------------------------------------------------------
   * Entity resolution is now handled by CentralRouteManager
   * - When user navigates to /c/:user/:corpus → CentralRouteManager fetches and sets openedCorpus
   * - This component just reads openedCorpus reactive var and displays appropriate view
   * -------------------------------------------------------------------------------------------------- */

  if (corpus_load_error) {
    console.log("Corpuses.tsx - corpus_load_error", corpus_load_error);
    toast.error("ERROR\nUnable to fetch corpuses.");
  }

  ///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
  // Query to get Metadata for Selected Corpus
  ///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
  const [
    fetchMetadata,
    {
      called: metadata_called,
      loading: metadata_loading,
      data: metadata_data,
      refetch: refetchMetadata,
    },
  ] = useLazyQuery<GetCorpusMetadataOutputs, GetCorpusMetadataInputs>(
    GET_CORPUS_METADATA
  );

  ///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
  // Query to refetch documents if dropdown action is used to delink a doc from corpus
  ///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
  const [
    fetchDocumentsLazily,
    { error: documents_error, refetch: refetch_documents },
  ] = useLazyQuery<RequestDocumentsOutputs, RequestDocumentsInputs>(
    GET_DOCUMENTS,
    {
      variables: {
        ...(opened_corpus_id
          ? {
              annotateDocLabels: true,
              includeMetadata: true,
              inCorpusWithId: opened_corpus_id,
            }
          : { annotateDocLabels: false, includeMetadata: false }),
        ...(filter_to_label_id ? { hasLabelWithId: filter_to_label_id } : {}),
        ...(selected_metadata_id_to_filter_on
          ? { hasAnnotationsWithIds: selected_metadata_id_to_filter_on }
          : {}),
        ...(document_search_term ? { textSearch: document_search_term } : {}),
      },
      notifyOnNetworkStatusChange: true, // necessary in order to trigger loading signal on fetchMore
    }
  );
  if (documents_error) {
    toast.error("ERROR\nCould not fetch documents for corpus.");
  }

  useEffect(() => {
    // console.log("Corpuses.tsx - Loading Corpuses changed...");
  }, [loading_corpuses]);

  const fetchMoreCorpuses = (args: any) => {
    // console.log("Corpuses.txt - fetchMoreCorpuses()");
    fetchMoreCorpusesOrig(args);
  };

  ///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
  // Effects to reload data on certain changes
  ///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
  // Handle metadata refetch when auth changes and corpus is open
  useEffect(() => {
    if (auth_token && metadata_called && opened_corpus?.id) {
      // Only refetch if we have previously called the query successfully
      if (metadata_data || metadata_loading) {
        refetchMetadata();
      } else {
        // Re-fetch with current corpus ID if we haven't fetched before
        const { id: validId, isValid } = ensureValidCorpusId(opened_corpus);
        if (isValid && validId) {
          fetchMetadata({ variables: { metadataForCorpusId: validId } });
        }
      }
    }
  }, [auth_token]); // Re-run when auth token changes

  // Search term effect - needed because fetchPolicy is "network-only"
  useEffect(() => {
    refetchCorpuses();
  }, [corpus_search_term]);

  // REMOVED: location-based refetch - was hammering server on every navigation
  // Component already refetches on mount and when search term changes

  // Sync opened_corpus to CorpusAtom and fetch metadata when corpus selected
  // CRITICAL: Use stable ID as dependency to avoid infinite loops
  // Apollo reactive vars return new object references even when data unchanged
  const openedCorpusId = opened_corpus?.id;

  useEffect(() => {
    if (opened_corpus) {
      const corpus_permissions = getPermissions(opened_corpus.myPermissions);
      setCorpus({
        selectedCorpus: opened_corpus,
        myPermissions: corpus_permissions,
      });

      // Fetch metadata when corpus is selected
      const { id: validId, isValid } = ensureValidCorpusId(opened_corpus);
      if (isValid && validId) {
        try {
          fetchMetadata({ variables: { metadataForCorpusId: validId } });
          refetchStats(); // Refresh stats when corpus changes
        } catch (error) {
          console.error("Error fetching corpus metadata:", error);
        }
      } else {
        console.warn(
          "Skipping metadata fetch - invalid corpus ID:",
          opened_corpus.id
        );
      }
    } else {
      setCorpus({
        selectedCorpus: opened_corpus,
        myPermissions: [],
      });
    }
    // REMOVED: refetchCorpuses on opened_corpus null - unnecessary, query already has data
  }, [openedCorpusId]); // Only depend on ID, not full object

  // Update CorpusAtom when metadata is fetched
  // IMPORTANT: Only depend on corpus ID, not the whole object, to avoid infinite loops
  // GraphQL returns new object references on every render even if data unchanged
  const metadataCorpusId = metadata_data?.corpus?.id;

  useEffect(() => {
    if (metadata_data?.corpus && metadataCorpusId) {
      const corpus = metadata_data.corpus;
      const corpus_permissions = getPermissions(corpus.myPermissions || []);
      setCorpus({
        selectedCorpus: corpus,
        myPermissions: corpus_permissions,
      });
    }
  }, [metadataCorpusId]); // Only depend on ID, not the full object

  useEffect(() => {
    refetch_documents();
  }, [selected_metadata_id_to_filter_on]);

  // Fetch corpus stats - with proper ID validation
  // Handle both string and number IDs, convert to string for GraphQL
  const validCorpusId = opened_corpus?.id
    ? String(opened_corpus.id)
    : undefined;

  const {
    data: statsData,
    loading: statsLoading,
    error: statsError,
    refetch: refetchStats,
  } = useQuery(GET_CORPUS_STATS, {
    variables: { corpusId: validCorpusId || "" }, // Provide empty string as fallback
    skip: !validCorpusId, // Skip if we don't have a valid ID
    // REMOVED pollInterval - was hammering server every 5 seconds
    // Stats are not real-time critical and will update when corpus changes
  });

  // Log stats errors for debugging
  useEffect(() => {
    if (statsError) {
      console.error("Error fetching corpus stats:", statsError);
    }
  }, [statsError]);

  // CRITICAL: Memoize stats object to prevent new object reference on every render
  // New object reference would cause navigationItems useMemo to re-run infinitely
  // Depend on primitive values, not the object itself, as Apollo returns new object refs
  const stats = useMemo(() => {
    return (
      statsData?.corpusStats || {
        totalDocs: 0,
        totalAnnotations: 0,
        totalAnalyses: 0,
        totalExtracts: 0,
        totalThreads: 0,
      }
    );
  }, [
    statsData?.corpusStats?.totalDocs,
    statsData?.corpusStats?.totalAnnotations,
    statsData?.corpusStats?.totalAnalyses,
    statsData?.corpusStats?.totalExtracts,
    statsData?.corpusStats?.totalThreads,
  ]);

  // When query is skipped (no valid corpus ID), treat as not loading
  const effectiveStatsLoading = validCorpusId ? statsLoading : false;

  // Debug logging for stats issues
  useEffect(() => {
    if (opened_corpus) {
      console.log("Corpus Stats Debug:", {
        corpusId: opened_corpus.id,
        validCorpusId,
        statsLoading,
        effectiveStatsLoading,
        hasStatsData: !!statsData?.corpusStats,
        stats,
      });
    }
  }, [
    opened_corpus?.id,
    validCorpusId,
    statsLoading,
    effectiveStatsLoading,
    statsData,
    stats,
  ]);

  ///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
  // Query to shape item data
  ///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
  const corpus_data = corpus_response?.corpuses?.edges
    ? corpus_response.corpuses.edges
    : [];
  const corpus_items = corpus_data
    .map((edge) => {
      if (!edge || !edge.node) return undefined;

      // Create a copy of the node
      const node = { ...edge.node };

      // Don't transform permissions here - let CorpusItem handle it
      // to avoid double transformation

      return node;
    })
    .filter((item): item is CorpusType => !!item);

  ///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
  // Query to mutate corpus
  ///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
  const [tryMutateCorpus, { loading: update_corpus_loading }] = useMutation<
    UpdateCorpusOutputs,
    UpdateCorpusInputs
  >(UPDATE_CORPUS, {
    onCompleted: (data) => {
      refetchCorpuses();
      refetchStats(); // Refresh stats after corpus update
      editingCorpus(null);
    },
  });

  ///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
  // Query to delete corpus
  ///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
  const [tryDeleteCorpus, { loading: delete_corpus_loading }] = useMutation<
    DeleteCorpusOutputs,
    DeleteCorpusInputs
  >(DELETE_CORPUS, {
    onCompleted: (data) => {
      refetchCorpuses();
    },
  });

  const [removeDocumentsFromCorpus, {}] = useMutation<
    RemoveDocumentsFromCorpusOutputs,
    RemoveDocumentsFromCorpusInputs
  >(REMOVE_DOCUMENTS_FROM_CORPUS, {
    onCompleted: () => {
      fetchDocumentsLazily();
      refetchStats(); // Refresh stats after removing documents
    },
  });

  ///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
  // Query to delete corpus
  ///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
  const [tryCreateCorpus, { loading: create_corpus_loading }] = useMutation<
    CreateCorpusOutputs,
    CreateCorpusInputs
  >(CREATE_CORPUS, {
    onCompleted: (data) => {
      refetchCorpuses();
      refetchStats(); // Refresh stats after corpus creation
      setShowNewCorpusModal(false);
    },
  });

  // When an import file is selected by user and change is detected in <input>,
  // read and convert file to base64string, then upload to the start import mutation.
  const onImportFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    if (event?.target?.files?.item(0)) {
      let reader = new FileReader();
      reader.onload = async (e) => {
        if (event?.target?.files?.item(0) != null) {
          var base64FileString = await toBase64(
            event.target.files.item(0) as File
          );
          if (
            typeof base64FileString === "string" ||
            base64FileString instanceof String
          ) {
            startImportCorpus({
              variables: { base64FileString: base64FileString.split(",")[1] },
            });
          }
        }
      };
      reader.readAsDataURL(event.target.files[0]);
    }
  };

  // TODO - Improve typing.
  const handleUpdateCorpus = (corpus_obj: any) => {
    tryMutateCorpus({ variables: corpus_obj });
  };

  // TODO - Improve typing.
  const handleDeleteCorpus = (corpus_id: string | undefined) => {
    if (corpus_id) {
      // console.log("handleDeleteCorpus", corpus_id)
      tryDeleteCorpus({ variables: { id: corpus_id } })
        .then((data) => {
          toast.success("SUCCESS! Deleted corpus.");
        })
        .catch((err) => {
          toast.error("ERROR! Could not delete corpus.");
        });
    }
  };

  const handleRemoveContracts = (delete_ids: string[]) => {
    // console.log("handleRemoveContracts", delete_ids);
    removeDocumentsFromCorpus({
      variables: {
        corpusId: opened_corpus?.id ? opened_corpus.id : "",
        documentIdsToRemove: delete_ids,
      },
    })
      .then(() => {
        selectedDocumentIds([]);
        toast.success("SUCCESS! Contracts removed.");
      })
      .catch(() => {
        selectedDocumentIds([]);
        toast.error("ERROR! Contract removal failed.");
      });
  };

  // TODO - Improve typing.
  const handleCreateNewCorpus = (corpus_json: Record<string, any>) => {
    tryCreateCorpus({ variables: corpus_json })
      .then((data) => {
        console.log("Data", data);
        if (data.data?.createCorpus.ok) {
          toast.success("SUCCESS. Created corpus.");
        } else {
          toast.error(`FAILED on server: ${data.data?.createCorpus.message}`);
        }
        refetchCorpuses();
        setShowNewCorpusModal(false);
      })
      .catch((err) => {
        toast.error("ERROR. Could not create corpus.");
      });
  };

  let corpus_actions: DropdownActionProps[] = [];
  if (auth_token) {
    corpus_actions = [
      ...corpus_actions,
      {
        icon: "plus",
        title: "Create Corpus",
        key: `Corpus_action_${0}`,
        color: "blue",
        action_function: () => setShowNewCorpusModal(true),
      },
    ];

    // Currently the import capability is enabled via an env variable in case we want it disabled
    // (which we'll probably do for the public demo to cut down on attack surface and load on server)
    if (REACT_APP_ALLOW_IMPORTS && auth_token) {
      corpus_actions.push({
        icon: "cloud upload",
        title: "Import Corpus",
        key: `Corpus_action_${1}`,
        color: "green",
        action_function: () => corpusUploadRef.current.click(),
      });
    }
  }

  let contract_actions: DropdownActionProps[] = [];
  if (selected_document_ids.length > 0 && auth_token) {
    contract_actions.push({
      icon: "remove circle",
      title: "Remove Contract(s)",
      key: `Corpus_action_${corpus_actions.length}`,
      color: "blue",
      action_function: () => setShowMultiDeleteConfirm(true),
    });
  }

  // Actions for analyzer pane (if user is signed in)
  if (
    auth_token &&
    raw_permissions?.includes(PermissionTypes.CAN_UPDATE) &&
    raw_permissions?.includes(PermissionTypes.CAN_READ)
  ) {
    corpus_actions.push({
      icon: "factory",
      title: "Start New Analysis",
      key: `Analysis_action_${corpus_actions.length}`,
      color: "blue",
      action_function: () => showSelectCorpusAnalyzerOrFieldsetModal(true),
    });
  }

  // NOTE: canUpdateCorpus and corpusAtomPermissions are already destructured above
  // Removed duplicate useCorpusState() call that was causing infinite re-renders

  // Navigation items configuration
  // Memoize to prevent recreating on every render
  const navigationItems = useMemo(() => {
    return [
      {
        id: "home",
        label: "Home",
        icon: <Brain />,
        component: (
          <CorpusQueryView
            opened_corpus={opened_corpus}
            opened_corpus_id={opened_corpus_id}
            setShowDescriptionEditor={setShowDescriptionEditor}
            onNavigate={(tabIndex) => setActiveTab(tabIndex)}
            onBack={() => navigate("/corpuses")}
            canUpdate={canUpdateCorpus}
            stats={stats}
            statsLoading={effectiveStatsLoading}
          />
        ),
      },
      {
        id: "documents",
        label: "Documents",
        icon: <FileText />,
        badge: stats.totalDocs,
        component: (
          <div
            style={{ display: "flex", flexDirection: "column", height: "100%" }}
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
              <TabTitle>Documents</TabTitle>
            </TabNavigationHeader>
            <div style={{ flex: 1, overflow: "hidden" }}>
              {opened_corpus_id && (
                <FolderDocumentBrowser corpusId={opened_corpus_id}>
                  <CorpusDocumentCards opened_corpus_id={opened_corpus_id} />
                </FolderDocumentBrowser>
              )}
            </div>
          </div>
        ),
      },
      {
        id: "annotations",
        label: "Annotations",
        icon: <MessageSquare />,
        badge: stats.totalAnnotations,
        component: (
          <div
            style={{ display: "flex", flexDirection: "column", height: "100%" }}
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
              <TabTitle>Annotations</TabTitle>
            </TabNavigationHeader>
            <div style={{ flex: 1, overflow: "hidden" }}>
              <CorpusAnnotationCards opened_corpus_id={opened_corpus_id} />
            </div>
          </div>
        ),
      },
      {
        id: "analyses",
        label: "Analyses",
        icon: <Factory />,
        badge: stats.totalAnalyses,
        component: (
          <div
            style={{ display: "flex", flexDirection: "column", height: "100%" }}
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
              <TabTitle>Analyses</TabTitle>
            </TabNavigationHeader>
            <div style={{ flex: 1, overflow: "hidden" }}>
              <CorpusAnalysesCards />
            </div>
          </div>
        ),
      },
      {
        id: "extracts",
        label: "Extracts",
        icon: <Table />,
        badge: stats.totalExtracts,
        component: (
          <div
            style={{ display: "flex", flexDirection: "column", height: "100%" }}
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
            </TabNavigationHeader>
            <div style={{ flex: 1, overflow: "hidden" }}>
              <CorpusExtractCards />
            </div>
          </div>
        ),
      },
      {
        id: "discussions",
        label: "Discussions",
        icon: <MessageSquare />,
        badge: stats.totalThreads || 0,
        component: opened_corpus?.id ? (
          <CorpusDiscussionsView corpusId={opened_corpus.id} />
        ) : null,
      },
      {
        id: "analytics",
        label: "Analytics",
        icon: <BarChart3 />,
        component: opened_corpus?.id ? (
          <CorpusEngagementDashboard corpusId={opened_corpus.id} />
        ) : null,
      },
      ...(opened_corpus && canUpdateCorpus
        ? [
            {
              id: "settings",
              label: "Settings",
              icon: <Settings />,
              component: opened_corpus?.title ? (
                <div
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    height: "100%",
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
                    <TabTitle>Settings</TabTitle>
                  </TabNavigationHeader>
                  <div style={{ flex: 1, overflow: "hidden" }}>
                    <CorpusSettings
                      corpus={{
                        id: opened_corpus.id,
                        title: opened_corpus.title,
                        description: opened_corpus.description || "",
                        allowComments: opened_corpus.allowComments || false,
                        preferredEmbedder: opened_corpus.preferredEmbedder,
                        slug: (opened_corpus as any).slug || null,
                        creator: opened_corpus.creator,
                        created: opened_corpus.created,
                        modified: opened_corpus.modified,
                        isPublic: opened_corpus.isPublic,
                        myPermissions: corpusAtomPermissions,
                      }}
                    />
                  </div>
                </div>
              ) : null,
            },
            {
              id: "badges",
              label: "Badges",
              icon: <Trophy />,
              component: opened_corpus?.id ? (
                <div
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    height: "100%",
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
                    <TabTitle>Badges</TabTitle>
                  </TabNavigationHeader>
                  <div style={{ flex: 1, overflow: "auto" }}>
                    <BadgeManagement corpusId={opened_corpus.id} />
                  </div>
                </div>
              ) : null,
            },
          ]
        : []),
    ];
  }, [
    openedCorpusId, // Use stable ID instead of full object
    opened_corpus_id,
    stats.totalDocs,
    stats.totalAnnotations,
    stats.totalAnalyses,
    stats.totalExtracts,
    canUpdateCorpus,
    // Note: corpusAtomPermissions is an array that changes, but canUpdateCorpus is derived from it
    // and is a stable boolean, so we don't need corpusAtomPermissions in deps
  ]);

  const currentView = navigationItems[active_tab];

  let content = <></>;
  if (
    (opened_corpus === null || opened_corpus === undefined) &&
    (opened_document === null || opened_document === undefined)
  ) {
    content = (
      <div
        style={{
          width: "100%",
          flex: 1,
          display: "flex",
          flexDirection: "column",
          padding: 0,
          margin: 0,
          overflow: "hidden",
          minHeight: 0,
        }}
      >
        <CorpusCards
          items={corpus_items}
          pageInfo={corpus_response?.corpuses?.pageInfo}
          loading={
            loading_corpuses ||
            delete_corpus_loading ||
            update_corpus_loading ||
            create_corpus_loading
          }
          loading_message="Loading Corpuses..."
          fetchMore={fetchMoreCorpuses}
        />
      </div>
    );
  } else if (
    opened_corpus && // Corpus selected
    !opened_document // No document selected
  ) {
    content = (
      <CorpusViewContainer id="corpus-view-container">
        {/* Mobile backdrop */}
        <AnimatePresence>
          {mobileSidebarOpen && (
            <MobileMenuBackdrop
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setMobileSidebarOpen(false)}
            />
          )}
        </AnimatePresence>

        {/* Navigation Sidebar */}
        <NavigationSidebar
          data-testid="navigation-sidebar"
          $isExpanded={use_mobile_layout ? mobileSidebarOpen : sidebarExpanded}
          initial={{
            width: use_mobile_layout ? "0" : sidebarExpanded ? "280px" : "72px",
          }}
          animate={{
            width: use_mobile_layout
              ? mobileSidebarOpen
                ? "280px"
                : "0"
              : sidebarExpanded
              ? "280px"
              : "72px",
          }}
          transition={{ duration: 0.3, ease: "easeInOut" }}
        >
          <BottomSheetHandle
            onClick={() => use_mobile_layout && setMobileSidebarOpen(false)}
          />
          <NavigationHeader
            $isExpanded={
              use_mobile_layout ? mobileSidebarOpen : sidebarExpanded
            }
          >
            {(use_mobile_layout ? mobileSidebarOpen : sidebarExpanded) && (
              <motion.div
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.3, delay: 0.1 }}
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: "0.25rem",
                  flex: 1,
                }}
              >
                <div
                  style={{
                    fontSize: "0.6875rem",
                    fontWeight: 500,
                    color: "#94a3b8",
                    textTransform: "uppercase",
                    letterSpacing: "0.05em",
                  }}
                >
                  {opened_corpus ? "Corpus" : "Navigation"}
                </div>
                <div
                  style={{
                    fontSize: "1rem",
                    fontWeight: 600,
                    color: "#0f172a",
                    letterSpacing: "-0.015em",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {opened_corpus ? opened_corpus.title : "Menu"}
                </div>
              </motion.div>
            )}
            {!use_mobile_layout && (
              <NavigationToggle
                data-testid="sidebar-toggle"
                onClick={() => setSidebarExpanded(!sidebarExpanded)}
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                style={{
                  marginLeft: sidebarExpanded ? "0" : "auto",
                  marginRight: sidebarExpanded ? "0" : "auto",
                }}
              >
                {sidebarExpanded ? <ChevronLeft /> : <ChevronRight />}
              </NavigationToggle>
            )}
          </NavigationHeader>

          <NavigationItems id="nav-items">
            {navigationItems.map((item, index) => (
              <NavigationItem
                data-item-id={item.id}
                key={item.id}
                isActive={active_tab === index}
                $isExpanded={
                  use_mobile_layout ? mobileSidebarOpen : sidebarExpanded
                }
                onClick={() => {
                  setActiveTab(index);
                  if (use_mobile_layout) {
                    setMobileSidebarOpen(false);
                  }
                  // Refresh stats when switching tabs
                  refetchStats();
                }}
                whileHover={{ x: 2 }}
                whileTap={{ scale: 0.98 }}
              >
                <div style={{ position: "relative" }}>
                  {item.icon}
                  {item.badge &&
                    item.badge > 0 &&
                    !sidebarExpanded &&
                    !use_mobile_layout && (
                      <NotificationBadge>{item.badge}</NotificationBadge>
                    )}
                </div>
                {(use_mobile_layout ? mobileSidebarOpen : sidebarExpanded) && (
                  <>
                    <span style={{ flex: "1", textAlign: "left" }}>
                      {item.label}
                    </span>
                    {item.badge !== undefined && item.badge > 0 && (
                      <NavItemBadge isActive={active_tab === index}>
                        {item.badge}
                      </NavItemBadge>
                    )}
                  </>
                )}
              </NavigationItem>
            ))}
          </NavigationItems>
        </NavigationSidebar>

        {/* Main content area */}
        <MainContentArea
          id="main-corpus-content-area"
          $sidebarExpanded={!use_mobile_layout && sidebarExpanded}
        >
          {currentView?.component}
        </MainContentArea>

        {/* Bottom Navigation FAB - Mobile Only (hidden on home page) */}
        <AnimatePresence>
          {use_mobile_layout &&
            opened_corpus &&
            !mobileSidebarOpen &&
            active_tab !== 0 && ( // Hide on home page (tab 0)
              <BottomNavigationHandle
                isOpen={mobileSidebarOpen}
                onClick={() => setMobileSidebarOpen(true)}
                initial={{ scale: 0, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                exit={{ scale: 0, opacity: 0 }}
                transition={{
                  type: "spring",
                  stiffness: 400,
                  damping: 25,
                }}
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
              >
                <AlignJustify />
              </BottomNavigationHandle>
            )}
        </AnimatePresence>
      </CorpusViewContainer>
    );
  } else if (
    opened_corpus !== null &&
    opened_corpus !== undefined &&
    opened_document !== null &&
    opened_document !== undefined
  ) {
    console.log("Show annotator");
    content = <></>;
  }

  /* ------------------------------------------------------------------ */
  /* Entity resolution is now handled by CentralRouteManager            */
  /* - /corpuses route → shows list (no entity)                         */
  /* - /c/:user/:corpus route → CentralRouteManager sets openedCorpus   */
  /* This component just reads openedCorpus and renders appropriately   */
  /* ------------------------------------------------------------------ */

  return (
    <CardLayout
      style={{
        flex: 1,
        display: "flex",
        flexDirection: "column",
        minHeight: 0,
      }}
      Modals={
        <>
          {opened_corpus && showDescriptionEditor && (
            <CorpusDescriptionEditor
              corpusId={opened_corpus.id}
              isOpen={showDescriptionEditor}
              onClose={() => setShowDescriptionEditor(false)}
              onUpdate={() => {
                const { id: validId, isValid } =
                  ensureValidCorpusId(opened_corpus);
                if (isValid && validId) {
                  fetchMetadata({
                    variables: { metadataForCorpusId: validId },
                  });
                }
                refetchStats(); // Refresh stats after description update
                setShowDescriptionEditor(false);
              }}
            />
          )}
          <ConfirmModal
            message={`Are you sure you want to delete corpus?`}
            yesAction={() => handleDeleteCorpus(deleting_corpus?.id)}
            noAction={() => deletingCorpus(null)}
            toggleModal={() => deletingCorpus(null)}
            visible={Boolean(deleting_corpus)}
          />
          <ConfirmModal
            message={"Remove selected contracts?"}
            yesAction={() => handleRemoveContracts(selected_document_ids)}
            noAction={() => setShowMultiDeleteConfirm(false)}
            toggleModal={() => setShowMultiDeleteConfirm(false)}
            visible={show_multi_delete_confirm}
          />
          <ConfirmModal
            message={`Are you sure you want to remove contract(s) from corpus?`}
            yesAction={() => handleRemoveContracts(selected_document_ids)}
            noAction={() =>
              showRemoveDocsFromCorpusModal(!show_remove_docs_from_corpus_modal)
            }
            toggleModal={() =>
              showRemoveDocsFromCorpusModal(!show_remove_docs_from_corpus_modal)
            }
            visible={show_remove_docs_from_corpus_modal}
          />
          <CRUDModal
            open={corpus_to_edit !== null}
            mode="EDIT"
            oldInstance={corpus_to_edit ?? {}}
            modelName="corpus"
            uiSchema={editCorpusForm_Ui_Schema}
            dataSchema={editCorpusForm_Schema}
            onSubmit={handleUpdateCorpus}
            onClose={() => editingCorpus(null)}
            hasFile={true}
            fileField={"icon"}
            fileLabel="Corpus Icon"
            fileIsImage={true}
            acceptedFileTypes="image/*"
            propertyWidgets={{
              labelSet: <LabelSetSelector />,
              preferredEmbedder: <EmbedderSelector />,
            }}
            loading={update_corpus_loading}
          />
          {exporting_corpus ? (
            <SelectExportTypeModal visible={Boolean(exportingCorpus)} />
          ) : (
            <></>
          )}
          {opened_query_obj ? (
            <ViewQueryResultsModal
              query_id={opened_query_obj.id}
              open={true}
              onClose={() => openedQueryObj(null)}
            />
          ) : (
            <></>
          )}
          {corpus_to_view !== null ? (
            <CRUDModal
              open={corpus_to_view !== null}
              mode="VIEW"
              oldInstance={corpus_to_view ? corpus_to_view : {}}
              modelName="corpus"
              uiSchema={editCorpusForm_Ui_Schema}
              dataSchema={editCorpusForm_Schema}
              onClose={() => viewingCorpus(null)}
              hasFile={true}
              fileField={"icon"}
              fileLabel="Corpus Icon"
              fileIsImage={true}
              acceptedFileTypes="image/*"
              propertyWidgets={{
                labelSet: <LabelSetSelector read_only={true} />,
                preferredEmbedder: <EmbedderSelector read_only={true} />,
              }}
            />
          ) : (
            <></>
          )}

          {show_new_corpus_modal ? (
            <CRUDModal
              open={show_new_corpus_modal}
              mode="CREATE"
              oldInstance={{ shared_with: [], is_public: false }}
              modelName="corpus"
              uiSchema={newCorpusForm_Ui_Schema}
              dataSchema={newCorpusForm_Schema}
              onSubmit={handleCreateNewCorpus}
              onClose={() => setShowNewCorpusModal(!show_new_corpus_modal)}
              hasFile={true}
              fileField={"icon"}
              fileLabel="Corpus Icon"
              fileIsImage={true}
              acceptedFileTypes="image/*"
              propertyWidgets={{
                labelSet: <LabelSetSelector />,
                preferredEmbedder: <EmbedderSelector />,
              }}
              loading={create_corpus_loading}
            />
          ) : (
            <></>
          )}
        </>
      }
      SearchBar={
        opened_corpus === null ? (
          <CreateAndSearchBar
            onChange={handleCorpusSearchChange}
            actions={corpus_actions}
            placeholder="Search for corpus..."
            value={corpusSearchCache}
          />
        ) : currentView?.id === "home" ? (
          // Home view uses floating chat search, no top search bar needed
          <></>
        ) : currentView?.id === "documents" ? (
          <SearchBarWithNav>
            <MobileBackButton
              onClick={() => {
                navigate("/corpuses"); // CentralRouteManager will clear openedCorpus
              }}
              title="Back to Corpuses"
            >
              <ArrowLeft />
            </MobileBackButton>
            <SearchBarContainer>
              <CreateAndSearchBar
                onChange={handleDocumentSearchChange}
                actions={contract_actions}
                placeholder="Search for document in corpus..."
                value={documentSearchCache}
                filters={
                  opened_corpus ? (
                    <>
                      {/* <FilterToMetadataSelector
                        selected_corpus_id={opened_corpus.id}
                      /> Temporarily disabled - not working and not really in-use*/}
                      <FilterToLabelSelector
                        only_labels_for_labelset_id={
                          opened_corpus.labelSet?.id
                            ? opened_corpus.labelSet.id
                            : ""
                        }
                        label_type={LabelType.DocTypeLabel}
                      />
                    </>
                  ) : (
                    <></>
                  )
                }
              />
            </SearchBarContainer>
          </SearchBarWithNav>
        ) : currentView?.id === "annotations" ? (
          <CreateAndSearchBar
            onChange={handleAnnotationSearchChange}
            actions={corpus_actions}
            placeholder="Search for annotated text in corpus..."
            value={annotationSearchCache}
            filters={
              opened_corpus ? (
                <>
                  <FilterToCorpusActionOutputs />
                  <FilterToAnalysesSelector corpus={opened_corpus} />
                  <FilterToLabelSelector
                    only_labels_for_labelset_id={
                      opened_corpus.labelSet?.id
                        ? opened_corpus.labelSet.id
                        : ""
                    }
                    label_type={LabelType.TokenLabel}
                  />
                </>
              ) : (
                <></>
              )
            }
          />
        ) : currentView?.id === "analyses" || currentView?.id === "extracts" ? (
          <SearchBarWithNav>
            <MobileBackButton
              onClick={() => {
                navigate("/corpuses"); // CentralRouteManager will clear openedCorpus
              }}
              title="Back to Corpuses"
            >
              <ArrowLeft />
            </MobileBackButton>
            <SearchBarContainer>
              <CreateAndSearchBar
                onChange={handleAnalysisSearchChange}
                actions={corpus_actions}
                placeholder="Search for analyses..."
                value={analysesSearchCache}
                filters={
                  <>
                    <FilterToCorpusActionOutputs />
                    <FilterToAnalysesSelector corpus={opened_corpus} />
                  </>
                }
              />
            </SearchBarContainer>
          </SearchBarWithNav>
        ) : (
          // Default search bar for any other views (like settings)
          <CreateAndSearchBar
            onChange={() => {}}
            actions={[]}
            placeholder="Search..."
            value=""
          />
        )
      }
      BreadCrumbs={opened_corpus !== null ? <CorpusBreadcrumbs /> : null}
    >
      <input
        ref={corpusUploadRef}
        id="uploadInputFile"
        hidden
        type="file"
        onChange={onImportFileChange}
      />
      {content}
    </CardLayout>
  );
};
