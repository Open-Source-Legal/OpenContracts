import { useState, useRef, useEffect } from "react";
import { Button, Tab, Menu } from "semantic-ui-react";
import _ from "lodash";
import { toast } from "react-toastify";
import {
  ApolloError,
  useLazyQuery,
  useMutation,
  useQuery,
  useReactiveVar,
} from "@apollo/client";
import { useLocation, useParams, useNavigate } from "react-router-dom";
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
  Menu as LucideMenu,
  Search,
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
import { CorpusAnnotationCards } from "../components/annotations/CorpusAnnotationCards";
import { CorpusDocumentCards } from "../components/documents/CorpusDocumentCards";
import { CorpusAnalysesCards } from "../components/analyses/CorpusAnalysesCards";
import { FilterToAnalysesSelector } from "../components/widgets/model-filters/FilterToAnalysesSelector";
import useWindowDimensions from "../components/hooks/WindowDimensionHook";
import { SelectExportTypeModal } from "../components/widgets/modals/SelectExportTypeModal";
import { ViewQueryResultsModal } from "../components/widgets/modals/ViewQueryResultsModal";
import { FilterToCorpusActionOutputs } from "../components/widgets/model-filters/FilterToCorpusActionOutputs";
import { CorpusExtractCards } from "../components/extracts/CorpusExtractCards";
import { getPermissions } from "../utils/transform";
import { MOBILE_VIEW_BREAKPOINT } from "../assets/configurations/constants";
import { CorpusDashboard } from "../components/corpuses/CorpusDashboard";
import { useCorpusState } from "../components/annotator/context/CorpusAtom";
import { CorpusSettings } from "../components/corpuses/CorpusSettings";
import { CorpusChat } from "../components/corpuses/CorpusChat";
import { CorpusHome } from "../components/corpuses/CorpusHome";
import { CorpusDescriptionEditor } from "../components/corpuses/CorpusDescriptionEditor";

// Add these styled components near your other styled components
const DashboardContainer = styled.div`
  display: flex;
  flex-direction: column;
  flex: 1;
  position: relative;
  overflow: hidden;
  padding: 0;
  width: 100%;
`;

// TODO - need to drop this padding
const ContentWrapper = styled.div`
  display: flex;
  flex-direction: column;
  align-items: stretch;
  justify-content: flex-start;
  flex: 1;
  padding: 0;
  height: 100%;
  overflow: hidden;
  min-height: 0;
  position: relative;
`;

const ChatTransitionContainer = styled.div<{
  isExpanded: boolean;
  isSearchTransform?: boolean;
}>`
  display: flex;
  flex-direction: column;
  height: ${(props) =>
    props.isSearchTransform ? (props.isExpanded ? "100%" : "auto") : "100%"};
  transition: all 0.5s cubic-bezier(0.16, 1, 0.3, 1);
  background: white;
  border-radius: ${(props) => (props.isExpanded ? "0" : "16px")};
  box-shadow: ${(props) =>
    props.isExpanded ? "none" : "0 8px 24px rgba(0,0,0,0.12)"};
  overflow: hidden;
  position: relative;
  z-index: ${(props) => (props.isExpanded ? "10" : "1")};
`;

const SearchToConversationInput = styled.div<{ isExpanded: boolean }>`
  display: flex;
  align-items: center;
  padding: ${(props) => (props.isExpanded ? "1.25rem 1.5rem" : "1rem 1.25rem")};
  border-bottom: ${(props) =>
    props.isExpanded ? "1px solid rgba(226, 232, 240, 0.8)" : "none"};
  background: ${(props) =>
    props.isExpanded ? "rgba(255, 255, 255, 0.98)" : "transparent"};
  backdrop-filter: ${(props) => (props.isExpanded ? "blur(12px)" : "none")};
  box-shadow: ${(props) =>
    props.isExpanded ? "0 2px 8px rgba(0, 0, 0, 0.04)" : "none"};

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
  padding-left: 0.5rem;
  width: 96px;
  max-width: 720px;
  min-height: 44px;
  height: auto;
  transition: all 0.35s ease;
  margin: 0 auto;

  &:hover,
  &:focus-within {
    width: 100%;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
    border-color: #cbd5e1;
    align-items: flex-start;
    padding-top: 0.5rem;
    padding-bottom: 0.5rem;
    padding-right: 0.5rem;
  }

  @media (max-width: 768px) {
    width: 88px;
    max-width: calc(100vw - 2rem);
    min-height: 42px;

    &:active,
    &:hover,
    &:focus-within {
      width: 100%;
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
    width: calc(100% - 2rem); /* account for container padding */
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
      width: calc(100% - 1.5rem); /* less padding on mobile */
    }
  }
`;

const SearchActionsContainer = styled.div`
  display: flex;
  align-items: center;
  gap: 0.375rem; /* tighter gap */
  padding-right: 0.375rem; /* less padding */
  flex-shrink: 0; /* prevent icons from shrinking */
`;

const ActionButton = styled(motion.button)`
  width: 40px;
  height: 40px;
  border-radius: 8px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  color: #64748b;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s ease;

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
}: {
  opened_corpus: CorpusType | null;
  opened_corpus_id: string | null;
  setShowDescriptionEditor: (show: boolean) => void;
}) => {
  const [chatExpanded, setChatExpanded] = useState<boolean>(false);
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [isSearchMode, setIsSearchMode] = useState<boolean>(true);
  const show_query_view_state = useReactiveVar(showQueryViewState);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const { width } = useWindowDimensions();
  const isDesktop = width > MOBILE_VIEW_BREAKPOINT;

  // Focus the input when component mounts or when returning to search mode
  useEffect(() => {
    if (isSearchMode && inputRef.current) {
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [isSearchMode]);

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
                <MessageSquare size={18} />
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
            height: "100%",
            minHeight: 0,
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
          height: "100%",
          minHeight: 0,
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
            />
            <div
              style={{
                position: "absolute",
                bottom: "2rem",
                left: "50%",
                transform: "translateX(-50%)",
                display: "flex",
                flexDirection: "row",
                justifyContent: "center",
                alignItems: "center",
                padding: "0.5rem",
                width: "85%" /* give more room for expansion */,
                maxWidth: "760px" /* match the search container max */,
              }}
            >
              <FloatingSearchContainer
                style={{ padding: "0px" }}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, delay: 0.1 }}
              >
                <form
                  onSubmit={handleSearchSubmit}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    width: "100%",
                    gap: "0.5rem",
                  }}
                >
                  <EnhancedSearchInput
                    ref={inputRef}
                    placeholder="Ask a question about this corpus..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
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
                      <MessageSquare size={18} />
                    </ActionButton>
                    <ActionButton
                      type="submit"
                      className="primary"
                      disabled={!searchQuery.trim()}
                      whileHover={searchQuery.trim() ? { scale: 1.05 } : {}}
                      whileTap={searchQuery.trim() ? { scale: 0.95 } : {}}
                    >
                      <Search size={18} />
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
          height: "100%",
          display: "flex",
          flexDirection: "column",
          minHeight: 0,
        }}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.3 }}
      >
        {renderNavigationHeader()}

        <div style={{ flex: 1, overflow: "hidden" }}>
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
  flex-direction: column;
  height: 100%;
  width: 100%;
  position: relative;
  overflow: hidden;
  flex: 1;
`;

const NavigationSidebar = styled(motion.div)<{ isExpanded: boolean }>`
  position: absolute;
  left: 0;
  top: 0;
  height: 100%;
  width: ${(props) => (props.isExpanded ? "280px" : "72px")};
  background: white;
  border-right: 1px solid #e2e8f0;
  z-index: 100;
  transition: width 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  display: flex;
  flex-direction: column;
  overflow: hidden;

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    position: fixed;
    width: ${(props) => (props.isExpanded ? "280px" : "0")};
    box-shadow: ${(props) =>
      props.isExpanded ? "2px 0 8px rgba(0, 0, 0, 0.1)" : "none"};
  }
`;

const NavigationHeader = styled.div<{ isExpanded: boolean }>`
  padding: 1.5rem;
  border-bottom: 1px solid rgba(226, 232, 240, 0.6);
  display: flex;
  align-items: center;
  justify-content: ${(props) =>
    props.isExpanded ? "space-between" : "center"};
  min-height: 72px;
`;

const NavigationToggle = styled(motion.button)`
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  color: #4a5568;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s ease;

  &:hover {
    background: #e2e8f0;
    color: #2d3748;
  }

  svg {
    width: 20px;
    height: 20px;
  }
`;

const NavigationItems = styled.div`
  flex: 1;
  padding: 1rem 0;
  overflow-y: auto;

  &::-webkit-scrollbar {
    width: 6px;
  }

  &::-webkit-scrollbar-track {
    background: #f8fafc;
  }

  &::-webkit-scrollbar-thumb {
    background: #e2e8f0;
    border-radius: 3px;

    &:hover {
      background: #cbd5e1;
    }
  }
`;

const NavigationItem = styled(motion.button)<{
  isActive: boolean;
  isExpanded: boolean;
}>`
  width: 100%;
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: ${(props) => (props.isExpanded ? "0.875rem 1.5rem" : "0.875rem")};
  background: ${(props) => (props.isActive ? "#f0f7ff" : "transparent")};
  border: none;
  color: ${(props) => (props.isActive ? "#4a90e2" : "#64748b")};
  font-weight: ${(props) => (props.isActive ? "600" : "500")};
  font-size: 0.9375rem;
  cursor: pointer;
  transition: all 0.2s ease;
  position: relative;
  justify-content: ${(props) => (props.isExpanded ? "flex-start" : "center")};

  &::before {
    content: "";
    position: absolute;
    left: 0;
    top: 0;
    bottom: 0;
    width: 3px;
    background: #4a90e2;
    opacity: ${(props) => (props.isActive ? "1" : "0")};
    transition: opacity 0.2s ease;
  }

  &:hover {
    background: ${(props) => (props.isActive ? "#f0f7ff" : "#f8fafc")};
    color: ${(props) => (props.isActive ? "#4a90e2" : "#2d3748")};
  }

  svg {
    width: 20px;
    height: 20px;
    flex-shrink: 0;
  }

  span {
    white-space: nowrap;
    opacity: ${(props) => (props.isExpanded ? "1" : "0")};
    width: ${(props) => (props.isExpanded ? "auto" : "0")};
    overflow: hidden;
    transition: opacity 0.2s ease, width 0.2s ease;
  }
`;

const MainContentArea = styled.div<{ sidebarExpanded: boolean }>`
  flex: 1;
  margin-left: ${(props) => (props.sidebarExpanded ? "280px" : "72px")};
  transition: margin-left 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  height: 100%;
  overflow: hidden;
  position: relative;
  display: flex;
  flex-direction: column;
  min-height: 0;

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    margin-left: 0;
  }
`;

const MobileMenuBackdrop = styled(motion.div)`
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  z-index: 99;
  display: none;

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    display: block;
  }
`;

const MobileMenuToggle = styled(motion.button)`
  position: fixed;
  bottom: 2rem;
  right: 2rem;
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background: #4a90e2;
  color: white;
  border: none;
  box-shadow: 0 4px 12px rgba(74, 144, 226, 0.3);
  display: none;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  z-index: 101;

  svg {
    width: 24px;
    height: 24px;
  }

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    display: flex;
  }
`;

const NotificationBadge = styled.div`
  position: absolute;
  top: -4px;
  right: -4px;
  width: 20px;
  height: 20px;
  background: #ef4444;
  color: white;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.75rem;
  font-weight: 600;
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

  const { setCorpus } = useCorpusState();
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
  const { corpusId: routeCorpusId } = useParams();
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
  let corpus_variables: LooseObject = {};
  if (corpus_search_term) {
    corpus_variables["textSearch"] = corpus_search_term;
  }
  const {
    refetch: refetchCorpuses,
    loading: loading_corpuses,
    error: corpus_load_error,
    data: corpus_response,
    fetchMore: fetchMoreCorpusesOrig,
  } = useQuery<GetCorpusesOutputs, GetCorpusesInputs>(GET_CORPUSES, {
    variables: corpus_variables,
    fetchPolicy: "network-only",
    notifyOnNetworkStatusChange: true, // required to get loading signal on fetchMore
  });

  /* --------------------------------------------------------------------------------------------------
   * Deep-link support: if the user navigates directly to `/corpuses/:id` we may not have the corpus in
   * the paginated GET_CORPUSES response yet. We therefore lazily fetch the corpus metadata **by id**
   * and hydrate the `openedCorpus` reactive var as soon as it arrives.
   * -------------------------------------------------------------------------------------------------- */
  const [
    fetchCorpusById,
    { data: corpusByIdData, loading: corpusByIdLoading },
  ] = useLazyQuery<GetCorpusMetadataOutputs, GetCorpusMetadataInputs>(
    GET_CORPUS_METADATA,
    {
      fetchPolicy: "network-only",
    }
  );

  /* Trigger the lazy query when we have a route id but no opened corpus and the list query finished. */
  useEffect(() => {
    if (
      routeCorpusId &&
      !opened_corpus &&
      !loading_corpuses &&
      !corpusByIdLoading &&
      !corpusByIdData
    ) {
      fetchCorpusById({ variables: { metadataForCorpusId: routeCorpusId } });
    }
  }, [routeCorpusId, opened_corpus, loading_corpuses, fetchCorpusById]);

  /* When the single-corpus query returns, sync it with the global reactive var. */
  useEffect(() => {
    if (corpusByIdData?.corpus) {
      openedCorpus(corpusByIdData.corpus);
    }
  }, [corpusByIdData]);

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
  // If user logs in/out while on this page... refetch to get their authorized corpuses
  useEffect(() => {
    // Always refetch corpuses when auth state changes (login or logout)
    refetchCorpuses();
    if (auth_token) {
      refetchMetadata();
    } else {
      // Clear opened corpus when logged out
      openedCorpus(null);
      // Navigate to corpuses list if we were viewing a specific corpus
      if (routeCorpusId) {
        navigate("/corpuses");
      }
    }
  }, [auth_token]);

  useEffect(() => {
    // console.log("corpus_search_term");
    refetchCorpuses();
  }, [corpus_search_term]);

  // If we detech user navigated to this page, refetch
  useEffect(() => {
    if (location.pathname === "/corpuses") {
      refetchCorpuses();
    }
    showQueryViewState("ASK");
  }, [location]);

  useEffect(() => {
    console.log("Switched opened_corpus", opened_corpus);
    setCorpus({
      selectedCorpus: opened_corpus,
    });
    if (!opened_corpus || opened_corpus === null) {
      refetchCorpuses();
    } else {
      console.log("Fetch metdata for corpus id: ", opened_corpus_id);
      fetchMetadata({ variables: { metadataForCorpusId: opened_corpus.id } });
      refetchStats(); // Refresh stats when corpus changes
    }
  }, [opened_corpus]);

  useEffect(() => {
    console.log(
      "selected_metadata_id_to_filter_on changed",
      selected_metadata_id_to_filter_on
    );
    refetch_documents();
  }, [selected_metadata_id_to_filter_on]);

  // Fetch corpus stats
  const {
    data: statsData,
    loading: statsLoading,
    refetch: refetchStats,
  } = useQuery(GET_CORPUS_STATS, {
    variables: { corpusId: opened_corpus?.id },
    skip: !opened_corpus_id,
    pollInterval: 5000, // Poll every 5 seconds for real-time updates
    fetchPolicy: "cache-and-network", // Always fetch fresh data while showing cached
  });

  const stats = statsData?.corpusStats || {
    totalDocs: 0,
    totalAnnotations: 0,
    totalAnalyses: 0,
    totalExtracts: 0,
  };

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

      // Convert myPermissions from string[] to PermissionTypes[] if it exists
      if (node.myPermissions) {
        node.myPermissions = getPermissions(node.myPermissions);
      }

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
    if (import.meta.env.REACT_APP_ALLOW_IMPORTS && auth_token) {
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

  // Navigation items configuration
  const navigationItems = [
    {
      id: "home",
      label: "Home",
      icon: <Brain />,
      component: (
        <CorpusQueryView
          opened_corpus={opened_corpus}
          opened_corpus_id={opened_corpus_id}
          setShowDescriptionEditor={setShowDescriptionEditor}
        />
      ),
    },
    {
      id: "documents",
      label: "Documents",
      icon: <FileText />,
      badge: stats.totalDocs,
      component: <CorpusDocumentCards opened_corpus_id={opened_corpus_id} />,
    },
    {
      id: "annotations",
      label: "Annotations",
      icon: <MessageSquare />,
      badge: stats.totalAnnotations,
      component: <CorpusAnnotationCards opened_corpus_id={opened_corpus_id} />,
    },
    {
      id: "analyses",
      label: "Analyses",
      icon: <Factory />,
      badge: stats.totalAnalyses,
      component: <CorpusAnalysesCards />,
    },
    {
      id: "extracts",
      label: "Extracts",
      icon: <Table />,
      badge: stats.totalExtracts,
      component: <CorpusExtractCards />,
    },
    ...(opened_corpus &&
    getPermissions(opened_corpus.myPermissions || []).includes(
      PermissionTypes.CAN_UPDATE
    )
      ? [
          {
            id: "settings",
            label: "Settings",
            icon: <Settings />,
            component: opened_corpus?.title ? (
              <CorpusSettings
                corpus={{
                  id: opened_corpus.id,
                  title: opened_corpus.title,
                  description: opened_corpus.description || "",
                  allowComments: opened_corpus.allowComments || false,
                  preferredEmbedder: opened_corpus.preferredEmbedder,
                  creator: opened_corpus.creator,
                  created: opened_corpus.created,
                  modified: opened_corpus.modified,
                  isPublic: opened_corpus.isPublic,
                }}
              />
            ) : null,
          },
        ]
      : []),
  ];

  const currentView = navigationItems[active_tab];

  let content = <></>;
  if (
    (opened_corpus === null || opened_corpus === undefined) &&
    (opened_document === null || opened_document === undefined)
  ) {
    content = (
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
    );
  } else if (
    (opened_corpus !== null || opened_corpus !== undefined) &&
    (opened_document === null || opened_document === undefined)
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
          isExpanded={use_mobile_layout ? mobileSidebarOpen : sidebarExpanded}
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
          <NavigationHeader
            isExpanded={use_mobile_layout ? mobileSidebarOpen : sidebarExpanded}
          >
            {(use_mobile_layout ? mobileSidebarOpen : sidebarExpanded) && (
              <motion.h3
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                style={{
                  margin: 0,
                  fontSize: "1.125rem",
                  fontWeight: 600,
                  color: "#0f172a",
                }}
              >
                Navigation
              </motion.h3>
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
                isExpanded={
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
                    <span>{item.label}</span>
                    {item.badge && item.badge > 0 && (
                      <span
                        style={{
                          marginLeft: "auto",
                          fontSize: "0.875rem",
                          opacity: 0.7,
                          fontWeight: 600,
                        }}
                      >
                        {item.badge}
                      </span>
                    )}
                  </>
                )}
              </NavigationItem>
            ))}
          </NavigationItems>
        </NavigationSidebar>

        {/* Mobile menu toggle button */}
        {use_mobile_layout && (
          <MobileMenuToggle
            onClick={() => setMobileSidebarOpen(!mobileSidebarOpen)}
            whileHover={{ scale: 1.1 }}
            whileTap={{ scale: 0.9 }}
          >
            <LucideMenu />
          </MobileMenuToggle>
        )}

        {/* Main content area */}
        <MainContentArea
          id="main-corpus-content-area"
          sidebarExpanded={!use_mobile_layout && sidebarExpanded}
        >
          <div
            style={{
              flex: 1,
              overflow: "hidden",
              display: "flex",
              flexDirection: "column",
              minHeight: 0,
              justifyContent: "flex-start",
              height: "100%",
            }}
          >
            {currentView?.component}
          </div>
        </MainContentArea>
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

  // After corpus_items derived
  /* ------------------------------------------------------------------ */
  /* URL → open corpus                                                  */
  useEffect(() => {
    if (!routeCorpusId) return;
    if (opened_corpus && opened_corpus.id === routeCorpusId) return;

    // attempt to find in already fetched list
    const match = corpus_items.find((c) => c.id === routeCorpusId);
    if (match) {
      openedCorpus(match);
    } else {
      // not in current page; best effort: trigger refetch with search param to include id? skip for now
      // could call refetchCorpuses but we already fetch all pages lazily; leave.
    }
  }, [routeCorpusId, opened_corpus, corpus_items]);

  /* ------------------------------------------------------------------ */
  /* open corpus → URL                                                  */
  useEffect(() => {
    if (opened_corpus) {
      if (routeCorpusId !== opened_corpus.id) {
        navigate(`/corpuses/${opened_corpus.id}`, { replace: true });
      }
    } else {
      // Do not navigate away if we are on a corpus route and the data is still loading
      if (routeCorpusId && !loading_corpuses) {
        navigate(`/corpuses`, { replace: true });
      }
    }
  }, [opened_corpus, routeCorpusId, navigate, loading_corpuses]);

  return (
    <CardLayout
      Modals={
        <>
          {opened_corpus && showDescriptionEditor && (
            <CorpusDescriptionEditor
              corpusId={opened_corpus.id}
              isOpen={showDescriptionEditor}
              onClose={() => setShowDescriptionEditor(false)}
              onUpdate={() => {
                refetchMetadata();
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
        ) : currentView?.id === "home" || currentView?.id === "documents" ? (
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
