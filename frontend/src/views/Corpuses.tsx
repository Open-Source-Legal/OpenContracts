import { useState, useRef, useEffect, useMemo, useCallback } from "react";
import _ from "lodash";
import { toast } from "react-toastify";
import {
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
  Send,
  History,
  Trophy,
  BarChart3,
  MoreVertical,
  Link2,
} from "lucide-react";
import styled from "styled-components";
import {
  OS_LEGAL_COLORS,
  accentAlpha,
} from "../assets/configurations/osLegalStyles";
import { motion, AnimatePresence } from "framer-motion";
import { SearchBox, FilterTabs } from "@os-legal/ui";
import type { FilterTabItem } from "@os-legal/ui";

import { ConfirmModal } from "../components/widgets/modals/ConfirmModal";
import { CreateExtractModal } from "../components/widgets/modals/CreateExtractModal";
import {
  CreateAndSearchBar,
  DropdownActionProps,
} from "../components/layout/CreateAndSearchBar";
import { CardLayout } from "../components/layout/CardLayout";
import {
  CorpusModal,
  CorpusFormData,
} from "../components/corpuses/CorpusModal";
import { CorpusListView } from "../components/corpuses/CorpusListView";

import {
  openedCorpus,
  selectedDocumentIds,
  corpusSearchTerm,
  deletingCorpus,
  showRemoveDocsFromCorpusModal,
  editingCorpus,
  viewingCorpus,
  documentSearchTerm,
  userObj,
  annotationContentSearchTerm,
  openedDocument,
  selectedMetaAnnotationId,
  filterToLabelId,
  analysisSearchTerm,
  exportingCorpus,
  showQueryViewState,
  showSelectCorpusAnalyzerOrFieldsetModal,
  selectedTab,
  selectedExtractIds,
  selectedThreadId,
  corpusPowerUserMode,
  showCreateExtractModal,
  showImportCorpusModal,
  backendUserObj,
} from "../graphql/cache";
import {
  updateTabParam,
  updateAnnotationSelectionParams,
  updateModeParam,
} from "../utils/navigationUtils";
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
} from "../graphql/mutations";
import {
  GetCorpusesInputs,
  GetCorpusesOutputs,
  GetCorpusMetadataInputs,
  GetCorpusMetadataOutputs,
  GET_CORPUSES,
  GET_CORPUS_METADATA,
  GET_CORPUS_STATS,
  GET_CORPUS_FILTER_COUNTS,
  GetCorpusFilterCountsInputs,
  GetCorpusFilterCountsOutputs,
  RequestDocumentsInputs,
  RequestDocumentsOutputs,
  GET_DOCUMENTS,
} from "../graphql/queries";
import { CorpusType, LabelType } from "../types/graphql-api";
import { LooseObject, PermissionTypes } from "../components/types";
import { FilterToLabelSelector } from "../components/widgets/model-filters/FilterToLabelSelector";
import { ensureValidCorpusId } from "../utils/graphqlGuards";
import { CorpusAnnotationCards } from "../components/annotations/CorpusAnnotationCards";
import { CorpusDocumentCards } from "../components/documents/CorpusDocumentCards";
import {
  FolderDocumentBrowser,
  ViewMode,
} from "../components/corpuses/folders/FolderDocumentBrowser";
import { CorpusAnalysesCards } from "../components/analyses/CorpusAnalysesCards";
import { FilterToAnalysesSelector } from "../components/widgets/model-filters/FilterToAnalysesSelector";
import useWindowDimensions from "../components/hooks/WindowDimensionHook";
import { SelectExportTypeModal } from "../components/widgets/modals/SelectExportTypeModal";
import { ImportCorpusModal } from "../components/widgets/modals/ImportCorpusModal";
import { FilterToCorpusActionOutputs } from "../components/widgets/model-filters/FilterToCorpusActionOutputs";
import { CorpusExtractCards } from "../components/extracts/CorpusExtractCards";
import { CorpusExtractDetail } from "../components/extracts/CorpusExtractDetail";
import { getPermissions } from "../utils/transform";
import {
  MOBILE_VIEW_BREAKPOINT,
  DEBOUNCE,
} from "../assets/configurations/constants";
import { useEnv } from "../components/hooks/UseEnv";
import { CorpusDashboard } from "../components/corpuses/CorpusDashboard";
import { useCorpusState } from "../components/annotator/context/CorpusAtom";
import { CorpusSettings } from "../components/corpuses/CorpusSettings";
import { CorpusChat } from "../components/corpuses/CorpusChat";
import { ChatMessageSource } from "../components/annotator/context/ChatSourceAtom";
import {
  encodeTextBlock,
  textBlockFromSpan,
  textBlockFromTokensByPage,
} from "../utils/textBlockEncoding";
import { buildQueryParams } from "../utils/navigationUtils";
import { toGlobalId } from "../utils/idValidation";
import { CorpusHome } from "../components/corpuses/CorpusHome";
import { CorpusDescriptionEditor } from "../components/corpuses/CorpusDescriptionEditor";
import { CamlArticleEditor } from "../components/corpuses/CamlArticleEditor";
import { CorpusDiscussionsView } from "../components/discussions/CorpusDiscussionsView";
import { BadgeManagement } from "../components/badges/BadgeManagement";
import { CorpusEngagementDashboard } from "../components/analytics/CorpusEngagementDashboard";
import { CorpusDocumentRelationships } from "../components/corpuses/CorpusDocumentRelationships";
import {
  CORPUS_COLORS,
  CORPUS_RADII,
  CORPUS_SHADOWS,
  CORPUS_TRANSITIONS,
  mediaQuery as corpusMediaQuery,
} from "../components/corpuses/styles/corpusDesignTokens";

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
    color: ${OS_LEGAL_COLORS.textPrimary};

    &::placeholder {
      color: ${OS_LEGAL_COLORS.textMuted};
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
  background: ${OS_LEGAL_COLORS.surfaceHover};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  color: ${OS_LEGAL_COLORS.textSecondary};
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s ease;
  flex-shrink: 0;

  &:hover:not(:disabled) {
    background: ${OS_LEGAL_COLORS.border};
    color: ${OS_LEGAL_COLORS.textTertiary};
  }

  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  &.primary {
    background: ${OS_LEGAL_COLORS.primaryBlue};
    color: white;
    border-color: ${OS_LEGAL_COLORS.primaryBlue};

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
  color: ${OS_LEGAL_COLORS.textPrimary};
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
  color: ${OS_LEGAL_COLORS.textSecondary};
  font-weight: 500;
  cursor: pointer;
  border-radius: 8px;
  transition: all 0.2s ease;

  &:hover {
    background: ${OS_LEGAL_COLORS.surfaceHover};
    color: ${OS_LEGAL_COLORS.textTertiary};
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
  setShowArticleEditor,
  onNavigate,
  onBack,
  canUpdate,
  stats,
  statsLoading,
  onOpenMobileMenu,
  onSourceNavigate,
  onModeToggle,
  isPowerUserMode,
}: {
  opened_corpus: CorpusType | null;
  opened_corpus_id: string | null;
  setShowDescriptionEditor: (show: boolean) => void;
  setShowArticleEditor: (show: boolean) => void;
  onNavigate?: (tabIndex: number) => void;
  onBack?: () => void;
  canUpdate?: boolean;
  stats: {
    totalDocs: number;
    totalAnnotations: number;
    totalAnalyses: number;
    totalExtracts: number;
    totalThreads: number;
  };
  statsLoading: boolean;
  onOpenMobileMenu?: () => void;
  onSourceNavigate?: (source: ChatMessageSource) => void;
  onModeToggle?: () => void;
  isPowerUserMode?: boolean;
}) => {
  const [chatExpanded, setChatExpanded] = useState<boolean>(false);
  // Mirrors CorpusChat's internal conversation/list view-mode. When the
  // expanded chat is showing a conversation, the outer "Back / Chat" header is
  // suppressed so the inner CorpusChat header is the single source of back
  // navigation — clicking back in the conversation goes to the list, then the
  // outer header reappears so a second click on the same screen position
  // takes the user back to the search view.
  const [chatExpandedInConversation, setChatExpandedInConversation] =
    useState<boolean>(false);
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
      // forceNewChat=true mounts CorpusChat directly into the conversation
      // view, so pre-set this so the outer header is suppressed on the first
      // paint instead of flashing for one frame.
      setChatExpandedInConversation(true);
      setIsSearchMode(false);
      // Ensure we stay in ASK mode rather than switching to VIEW
      showQueryViewState("ASK");
    }
  };

  const resetToSearch = () => {
    setChatExpanded(false);
    setChatExpandedInConversation(false);
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

      // When the chat-expanded CorpusChat is showing a conversation, its inner
      // header already provides Back + Home, so suppress the outer one to keep
      // a single back button on screen at any time. The outer header re-appears
      // automatically once the user returns to the conversation list view.
      if (chatExpanded && chatExpandedInConversation) {
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
            onSourceNavigate={onSourceNavigate}
            forceNewChat={true}
            // forceNewChat=true means we came from the search bar — just reset back to it
            onNavigateHome={resetToSearch}
            onViewModeChange={setChatExpandedInConversation}
            // The outer header above renders only on desktop; on mobile the
            // inner list-view Back stays visible as the sole navigation.
            hideListBackButton={isDesktop}
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
              onEditArticle={() => setShowArticleEditor(true)}
              onNavigate={onNavigate}
              onBack={onBack}
              canUpdate={canUpdate}
              stats={stats}
              statsLoading={statsLoading}
              chatQuery={searchQuery}
              onChatQueryChange={setSearchQuery}
              onChatSubmit={(query) => {
                if (query.trim()) {
                  setSearchQuery(query);
                  setChatExpanded(true);
                  // Pre-set so the outer "Back / Chat" header doesn't flash
                  // before the inner CorpusChat header takes over.
                  setChatExpandedInConversation(true);
                  setIsSearchMode(false);
                  showQueryViewState("ASK");
                }
              }}
              onViewChatHistory={openHistoryView}
              onNavigateToCorpuses={onBack}
              onOpenMobileMenu={onOpenMobileMenu}
              onModeToggle={onModeToggle}
              isPowerUserMode={isPowerUserMode}
            />
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
            onSourceNavigate={onSourceNavigate}
            // showLoad=true means we're in conversation-list mode — reset search
            // AND explicitly switch to ASK state so the search bar is visible
            // (without this the view could stay in VIEW mode after navigating home)
            onNavigateHome={() => {
              resetToSearch();
              showQueryViewState("ASK");
            }}
            // VIEW state always renders the outer "Back to Dashboard /
            // Conversation History" header on desktop; suppress the inner
            // filter-bar Back there to avoid duplicate-back-button UX.
            hideListBackButton={isDesktop}
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
  max-height: 100dvh;
  height: 100%;
`;

const NavigationSidebar = styled(motion.div)<{ $isExpanded: boolean }>`
  position: relative;
  width: ${(props) => (props.$isExpanded ? "280px" : "80px")};
  background: linear-gradient(180deg, #ffffff 0%, #fafbfc 50%, #f8f9fa 100%);
  backdrop-filter: blur(10px);
  border-right: 1px solid ${OS_LEGAL_COLORS.border};
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
    border-top: 1px solid ${OS_LEGAL_COLORS.border};
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
      background: ${OS_LEGAL_COLORS.borderHover};
      border-radius: 2px;
      transition: background 0.2s ease;
    }

    &:active {
      cursor: grabbing;

      &::after {
        background: ${OS_LEGAL_COLORS.textMuted};
      }
    }
  }
`;

const NavigationHeader = styled.div<{ $isExpanded: boolean }>`
  padding: 1.5rem;
  border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
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
  color: ${OS_LEGAL_COLORS.textSecondary};
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
    color: ${OS_LEGAL_COLORS.primaryBlue};
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
const NavItemBadge = styled.span<{ isActive: boolean; $isZero?: boolean }>`
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
    props.$isZero
      ? "transparent"
      : props.isActive
      ? CORPUS_COLORS.teal[700]
      : CORPUS_COLORS.slate[200]};
  color: ${(props) =>
    props.$isZero
      ? CORPUS_COLORS.slate[400]
      : props.isActive
      ? CORPUS_COLORS.white
      : CORPUS_COLORS.slate[600]};
  border: ${(props) =>
    props.$isZero ? `1px dashed ${CORPUS_COLORS.slate[300]}` : "none"};
  transition: all ${CORPUS_TRANSITIONS.normal};
  box-shadow: ${(props) =>
    props.$isZero
      ? "none"
      : props.isActive
      ? `0 2px 4px ${accentAlpha(0.25)}`
      : CORPUS_SHADOWS.sm};
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
  color: ${(props) =>
    props.isActive
      ? OS_LEGAL_COLORS.primaryBlue
      : OS_LEGAL_COLORS.textSecondary};
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
    color: ${(props) =>
      props.isActive
        ? OS_LEGAL_COLORS.primaryBlue
        : OS_LEGAL_COLORS.textTertiary};
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
    outline: 2px solid ${OS_LEGAL_COLORS.primaryBlue};
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
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
  transition: all 0.2s ease;

  &:focus-within {
    border-color: ${OS_LEGAL_COLORS.borderHover};
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
  border-right: 1px solid ${OS_LEGAL_COLORS.border};
  color: ${OS_LEGAL_COLORS.textSecondary};
  transition: all 0.2s ease;
  cursor: pointer;
  flex-shrink: 0;

  &:hover {
    background: ${OS_LEGAL_COLORS.surfaceHover};
    color: ${OS_LEGAL_COLORS.textTertiary};
  }

  &:active {
    background: ${OS_LEGAL_COLORS.surfaceLight};
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

// Back navigation header for non-home tabs - CRISPY VERSION
const TabNavigationHeader = styled.div`
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.875rem 1.25rem;
  background: white;
  border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
  flex-shrink: 0;
  min-height: 56px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    padding: 0.625rem 1rem;
    min-height: 48px;
  }
`;

// Mobile kebab menu button for tab headers - only visible on mobile
const MobileKebabButton = styled.button`
  display: none;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  padding: 0;
  background: transparent;
  border: none;
  border-radius: 6px;
  color: ${OS_LEGAL_COLORS.textSecondary};
  cursor: pointer;
  transition: all 0.15s ease;
  flex-shrink: 0;
  margin-left: auto;

  &:hover {
    background: ${OS_LEGAL_COLORS.successSurface};
    color: ${OS_LEGAL_COLORS.accent};
  }

  &:active {
    transform: scale(0.95);
  }

  svg {
    width: 20px;
    height: 20px;
  }

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    display: flex;
  }
`;

const BackNavButton = styled(motion.button)`
  display: flex;
  align-items: center;
  justify-content: center;
  background: ${OS_LEGAL_COLORS.surfaceHover};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  color: ${OS_LEGAL_COLORS.textSecondary};
  cursor: pointer;
  padding: 0;
  width: 36px;
  height: 36px;
  border-radius: 10px;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  flex-shrink: 0;

  &:hover {
    background: white;
    border-color: ${OS_LEGAL_COLORS.primaryBlue};
    color: ${OS_LEGAL_COLORS.primaryBlue};
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
  color: ${OS_LEGAL_COLORS.textPrimary};
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
  background: linear-gradient(
    135deg,
    ${OS_LEGAL_COLORS.danger} 0%,
    ${OS_LEGAL_COLORS.danger} 100%
  );
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

// Compact badge for collapsed sidebar - slight overlap at corner.
// Teal (non-zero) / slate (zero) is intentional: these badges display entity
// counts (documents, annotations, analyses, etc.), not action-required items,
// so the teal design-token color is appropriate rather than a warning palette.
const CollapsedBadge = styled.div<{ $isZero: boolean }>`
  position: absolute;
  top: -4px;
  right: -12px;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  background: ${(props) =>
    props.$isZero ? CORPUS_COLORS.slate[400] : CORPUS_COLORS.teal[700]};
  color: ${CORPUS_COLORS.white};
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.6rem;
  font-weight: 700;
  z-index: 2;
  box-shadow: ${CORPUS_SHADOWS.sm};
`;

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

/**
 * ExtractsTabContent - Split view for corpus extracts tab
 * Shows list on left, detail on right when an extract is selected
 * Includes search and filter functionality matching standalone Extracts view
 */
const ExtractsTabContent: React.FC<{
  setActiveTab: (tab: number) => void;
  onOpenMobileMenu?: () => void;
}> = ({ setActiveTab, onOpenMobileMenu }) => {
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

// Container for the clean landing view (no sidebar).
// Does NOT scroll — LandingContainer (inside CorpusLandingView) handles scrolling
// via overflow-y: auto.  This wrapper only provides flex layout so that the
// LandingContainer child can fill the available height.
//
// Height model:
//   CardLayout → CleanViewContainer → LandingContainer
//   - height: 100% + min-height: 0  → fills the flex parent while allowing
//     shrink, giving LandingContainer a bounded block size.
//   - overflow: hidden              → prevents this container from scrolling;
//     all scrolling happens inside LandingContainer's overflow-y: auto.
//   - max-height: 100dvh was removed because the flex ancestor chain already
//     constrains height, and the extra cap conflicted with LandingContainer's
//     own scroll container.
const CleanViewContainer = styled.div`
  position: relative;
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  min-height: 0;
  overflow: hidden;
`;

// Wrapper for the "Simple View" exit button at the bottom of the sidebar
const ExitPowerUserWrapper = styled.div`
  padding: 0.75rem;
  border-top: 1px solid ${CORPUS_COLORS.slate[200]};
  flex-shrink: 0;
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

  const currentUser = useReactiveVar(userObj);
  const backendUser = useReactiveVar(backendUserObj);
  const annotation_search_term = useReactiveVar(annotationContentSearchTerm);
  const show_query_view_state = useReactiveVar(showQueryViewState);
  const show_create_extract_modal = useReactiveVar(showCreateExtractModal);

  const location = useLocation();
  const navigate = useNavigate();

  const [show_multi_delete_confirm, setShowMultiDeleteConfirm] =
    useState<boolean>(false);
  const [show_new_corpus_modal, setShowNewCorpusModal] =
    useState<boolean>(false);
  // Tab state is now URL-driven via CentralRouteManager
  const urlTab = useReactiveVar(selectedTab);
  const [showDescriptionEditor, setShowDescriptionEditor] =
    useState<boolean>(false);
  const [showArticleEditor, setShowArticleEditor] = useState<boolean>(false);
  const [sidebarExpanded, setSidebarExpanded] = useState<boolean>(false); // Collapsed by default, opens on hover
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState<boolean>(false);

  // Power user mode: URL-driven via CentralRouteManager (?mode=power)
  const isPowerUserMode = useReactiveVar(corpusPowerUserMode);
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

  // View mode state for the Documents tab
  const [documentsViewMode, setDocumentsViewMode] =
    useState<ViewMode>("modern-list");

  // Active tab on the Corpuses list view ("all" | "my" | "shared" | "public").
  // Lifted up here so it can drive the GET_CORPUSES query variables — the
  // server applies the tab filter and counts so pagination + badges stay
  // accurate regardless of how many pages have been loaded.
  const [corpusListActiveFilter, setCorpusListActiveFilter] =
    useState<string>("all");

  // Track whether CorpusChat is showing a conversation (vs the list view)
  // Used to hide parent navigation header when CorpusChat handles its own
  const [chatInConversation, setChatInConversation] = useState<boolean>(false);

  // Derive whether the discussions tab is showing a thread detail from URL state.
  // The ?thread= param is synced to selectedThreadId by CentralRouteManager.
  const currentSelectedThreadId = useReactiveVar(selectedThreadId);
  const discussionInThreadView = currentSelectedThreadId !== null;

  /**
   * Navigate to a source document with text block highlighting.
   * Called from CorpusChat when a user clicks a source citation.
   * Builds a deep link URL with ?tb= param and navigates to the document.
   *
   * Each silent-return path emits a console.warn so a user reporting "the
   * source link doesn't work" can immediately see which guard is firing in
   * DevTools instead of nothing happening on click.
   */
  const handleSourceNavigate = useCallback(
    (source: ChatMessageSource) => {
      if (!source.document_id) {
        console.warn(
          "[handleSourceNavigate] No-op: source has no document_id; backend payload may be missing it.",
          source
        );
        return;
      }
      if (!opened_corpus) {
        console.warn(
          "[handleSourceNavigate] No-op: opened_corpus is null; route resolution did not populate the openedCorpus reactive var."
        );
        return;
      }

      // Validate corpus has slug data. This should always be present when
      // viewing a corpus (resolved from a slug-based URL by CentralRouteManager).
      // Falling back to opened_corpus.id (a Relay global ID) would produce an
      // unresolvable URL like /d/user/Q29ycHVzVHlwZTo1/... that 404s.
      if (!opened_corpus.slug || !opened_corpus.creator?.slug) {
        console.warn(
          "[handleSourceNavigate] No-op: corpus missing slug data; cannot build canonical /d/<user-slug>/<corpus-slug>/<doc> URL.",
          {
            corpusSlug: opened_corpus.slug,
            creatorSlug: opened_corpus.creator?.slug,
            corpusId: opened_corpus.id,
          }
        );
        return;
      }

      // Build the text block encoding from source data.
      let textBlock: string | null = null;
      if (
        source.isTextBased &&
        typeof source.startIndex === "number" &&
        typeof source.endIndex === "number"
      ) {
        textBlock = encodeTextBlock(
          textBlockFromSpan(source.startIndex, source.endIndex)
        );
      } else if (
        source.tokensByPage &&
        Object.keys(source.tokensByPage).length > 0
      ) {
        textBlock = encodeTextBlock(
          textBlockFromTokensByPage(source.tokensByPage)
        );
      }

      // Build the navigation URL. We only have the document's raw DB id from
      // the WebSocket source, not its slug, so we use a Relay global ID for
      // the document segment. CentralRouteManager Phase 1 detects this as a
      // GraphQL ID and resolves it via resolveDocumentById, then redirects to
      // the canonical slug URL. The corpus segment uses validated slugs from
      // the already-resolved corpus.
      const docGraphQLId = toGlobalId("DocumentType", source.document_id);

      // Prefer the precise text-block highlight when we have one. If the
      // text-block could not be built (most often a PDF source whose multipage
      // annotation_json has page keys but empty tokensJsons arrays — we have
      // the annotation but not the per-token indices), fall back to selecting
      // the annotation by its global ID via the existing ?ann= URL convention.
      // Synthetic search-result annotations use negative IDs (see
      // search.py); those are not real Annotation rows, so skip the ?ann=
      // fallback and at least navigate to the document without a highlight
      // rather than silently doing nothing.
      const hasRealAnnotationId =
        typeof source.annotation_id === "number" && source.annotation_id > 0;

      let queryString: string;
      if (textBlock) {
        queryString = buildQueryParams({ textBlock });
      } else if (hasRealAnnotationId) {
        const annGlobalId = toGlobalId("AnnotationType", source.annotation_id);
        queryString = buildQueryParams({ annotationIds: [annGlobalId] });
        console.debug(
          "[handleSourceNavigate] No text-block reference available; falling back to ?ann= deep-link.",
          { annotationId: source.annotation_id, annGlobalId }
        );
      } else {
        // Last-ditch: open the document with no highlight rather than no-op.
        queryString = "";
        console.warn(
          "[handleSourceNavigate] No text-block AND no real annotation_id; navigating to document without a highlight.",
          {
            isTextBased: source.isTextBased,
            startIndex: source.startIndex,
            endIndex: source.endIndex,
            tokensByPageCounts: source.tokensByPage
              ? Object.fromEntries(
                  Object.entries(source.tokensByPage).map(([page, tokens]) => [
                    page,
                    tokens.length,
                  ])
                )
              : {},
            annotationId: source.annotation_id,
          }
        );
      }

      const targetUrl = `/d/${opened_corpus.creator.slug}/${opened_corpus.slug}/${docGraphQLId}${queryString}`;

      console.debug("[handleSourceNavigate] Navigating to source:", {
        targetUrl,
        documentId: source.document_id,
        annotationId: source.annotation_id,
      });

      navigate(targetUrl);
    },
    [opened_corpus, navigate]
  );

  const handleViewModeChange = useCallback((mode: ViewMode) => {
    setDocumentsViewMode(mode);
  }, []);

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
    }, DEBOUNCE.SEARCH_MS)
  );

  const debouncedDocumentSearch = useRef(
    _.debounce((searchTerm) => {
      documentSearchTerm(searchTerm);
    }, DEBOUNCE.SEARCH_MS)
  );

  const debouncedAnnotationSearch = useRef(
    _.debounce((searchTerm) => {
      annotationContentSearchTerm(searchTerm);
    }, DEBOUNCE.SEARCH_MS)
  );

  const debouncedAnalysisSearch = useRef(
    _.debounce((searchTerm) => {
      analysisSearchTerm(searchTerm);
    }, DEBOUNCE.SEARCH_MS)
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

  // Check for ?create=true query param to open the create corpus modal
  // This allows linking directly to corpus creation from other pages (e.g., Discover page)
  useEffect(() => {
    const searchParams = new URLSearchParams(location.search);
    if (searchParams.get("create") === "true") {
      setShowNewCorpusModal(true);
      // Strip the trigger param via React Router so the routing system stays
      // in sync (avoids bypassing CentralRouteManager's URL observer).
      searchParams.delete("create");
      const remaining = searchParams.toString();
      navigate(
        {
          pathname: location.pathname,
          search: remaining ? `?${remaining}` : "",
        },
        { replace: true }
      );
    }
  }, [location.search, location.pathname, navigate]);

  ///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
  // Query to get corpuses
  ///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
  // CRITICAL: Memoize corpus_variables to prevent infinite re-renders
  // Creating new object on every render causes Apollo to refetch → cache update → re-render → new object → LOOP
  const corpus_variables = useMemo<GetCorpusesInputs>(() => {
    const vars: GetCorpusesInputs = {};
    if (corpus_search_term) {
      vars.textSearch = corpus_search_term;
    }
    // Map active tab to backend filter args. Only one tab flag at a time —
    // "all" sends no flag so the server returns the full visible set.
    if (corpusListActiveFilter === "my") {
      vars.mine = true;
    } else if (corpusListActiveFilter === "shared") {
      vars.sharedWithMe = true;
    } else if (corpusListActiveFilter === "public") {
      vars.isPublic = true;
    }
    return vars;
  }, [corpus_search_term, corpusListActiveFilter]);

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

  // Tab counts for the Corpuses list view. Server-computed so they reflect
  // the user's actual visible set (and the current text search) without
  // needing every page paginated in.
  const corpus_filter_counts_variables = useMemo<GetCorpusFilterCountsInputs>(
    () => (corpus_search_term ? { textSearch: corpus_search_term } : {}),
    [corpus_search_term]
  );
  const {
    data: corpus_filter_counts_data,
    refetch: refetchCorpusFilterCounts,
  } = useQuery<GetCorpusFilterCountsOutputs, GetCorpusFilterCountsInputs>(
    GET_CORPUS_FILTER_COUNTS,
    {
      variables: corpus_filter_counts_variables,
      fetchPolicy: "cache-and-network",
    }
  );
  const corpus_filter_counts =
    corpus_filter_counts_data?.corpusFilterCounts ?? {
      all: 0,
      mine: 0,
      shared: 0,
      public: 0,
    };

  /* --------------------------------------------------------------------------------------------------
   * Entity resolution is now handled by CentralRouteManager
   * - When user navigates to /c/:user/:corpus → CentralRouteManager fetches and sets openedCorpus
   * - This component just reads openedCorpus reactive var and displays appropriate view
   * -------------------------------------------------------------------------------------------------- */

  if (corpus_load_error) {
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
              includeCaml: true,
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
    if (currentUser && metadata_called && opened_corpus?.id) {
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
  }, [currentUser]); // Re-run when user changes

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

  // NOTE: A previous version of this effect called ``refetch_documents()``
  // whenever ``selected_metadata_id_to_filter_on`` changed. ``refetch_documents``
  // is the ``refetch`` of a ``useLazyQuery`` that fires the query *immediately*
  // — including on mount, when the dependency starts as ``undefined``. That
  // produced a duplicate ``GET_DOCUMENTS`` network call on every corpus open
  // (with no ``inFolderId``), racing against the per-folder ``GET_DOCUMENTS``
  // already issued by ``CorpusDocumentCards``. The list there is authoritative
  // and re-runs on its own when ``selected_metadata_id_to_filter_on`` changes
  // (its variables include ``hasAnnotationsWithIds``), so this effect is
  // redundant — and the duplicate response merging into the same cache nodes
  // was contributing to the document-list reload loop.

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
        totalChats: 0,
        totalRelationships: 0,
      }
    );
  }, [
    statsData?.corpusStats?.totalDocs,
    statsData?.corpusStats?.totalAnnotations,
    statsData?.corpusStats?.totalAnalyses,
    statsData?.corpusStats?.totalExtracts,
    statsData?.corpusStats?.totalThreads,
    statsData?.corpusStats?.totalChats,
    statsData?.corpusStats?.totalRelationships,
  ]);

  // When query is skipped (no valid corpus ID), treat as not loading
  const effectiveStatsLoading = validCorpusId ? statsLoading : false;

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
      refetchCorpusFilterCounts();
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
    // Remove the deleted corpus from every cached connection (every tab,
    // every search term) so the list updates instantly without waiting on
    // the refetch round-trip.
    update: (cache, { data }, { variables }) => {
      if (!data?.deleteCorpus?.ok || !variables?.id) return;
      const cacheId = cache.identify({
        __typename: "CorpusType",
        id: variables.id,
      });
      if (cacheId) {
        cache.evict({ id: cacheId });
        cache.gc();
      }
    },
    onCompleted: () => {
      // cache.evict gives instant removal in every cached page; the refetch
      // is still load-bearing because deleting a corpus shifts every
      // server-side pagination cursor that comes after it, so subsequent
      // fetchMore calls would otherwise skip or duplicate items.
      refetchCorpuses();
      refetchCorpusFilterCounts();
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
      refetchCorpusFilterCounts();
      setShowNewCorpusModal(false);
    },
  });

  // Handle corpus update with properly typed form data
  const handleUpdateCorpus = (formData: CorpusFormData) => {
    const variables: UpdateCorpusInputs = {
      id: formData.id!,
    };

    // Only include changed fields
    if (formData.title !== undefined) variables.title = formData.title;
    if (formData.description !== undefined)
      variables.description = formData.description;
    if (formData.slug !== undefined) variables.slug = formData.slug;
    if (formData.labelSet !== undefined)
      variables.labelSet = formData.labelSet ?? undefined;
    if (formData.preferredEmbedder !== undefined)
      variables.preferredEmbedder = formData.preferredEmbedder ?? undefined;
    if (formData.icon !== undefined && formData.icon !== null) {
      variables.icon = formData.icon;
    }
    if (formData.categories !== undefined) {
      variables.categories = formData.categories;
    }
    if (formData.license !== undefined) {
      variables.license = formData.license;
    }
    if (formData.licenseLink !== undefined) {
      variables.licenseLink = formData.licenseLink;
    }

    tryMutateCorpus({ variables });
  };

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

  // Handle corpus creation with properly typed form data
  const handleCreateNewCorpus = (formData: CorpusFormData) => {
    // Runtime validation for required fields
    if (!formData.title || !formData.description) {
      toast.error("Title and description are required");
      return;
    }

    const variables: CreateCorpusInputs = {
      title: formData.title,
      description: formData.description,
    };

    // Include optional fields if provided
    if (formData.labelSet) variables.labelSet = formData.labelSet;
    if (formData.preferredEmbedder)
      variables.preferredEmbedder = formData.preferredEmbedder;
    if (formData.icon) {
      variables.icon = formData.icon;
    }
    if (formData.categories && formData.categories.length > 0) {
      variables.categories = formData.categories;
    }
    // Create path: only send license fields when non-empty (server defaults apply).
    // Update path (above) uses !== undefined to allow sending empty strings to clear values.
    if (formData.license) {
      variables.license = formData.license;
    }
    if (formData.licenseLink) {
      variables.licenseLink = formData.licenseLink;
    }

    tryCreateCorpus({ variables })
      .then((data) => {
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
  if (currentUser) {
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

    // Imports are gated by a global env kill-switch (used to disable for the
    // public demo) AND by the server-derived `canImportCorpus` permission on
    // the authenticated user. Mirrors the backend check in
    // UploadCorpusImportZip / ImportZipToCorpus.
    if (REACT_APP_ALLOW_IMPORTS && backendUser?.canImportCorpus) {
      corpus_actions.push({
        icon: "cloud upload",
        title: "Import Corpus",
        key: `Corpus_action_${1}`,
        color: "green",
        action_function: () => showImportCorpusModal(true),
      });
    }
  }

  let contract_actions: DropdownActionProps[] = [];
  if (selected_document_ids.length > 0 && currentUser) {
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
    currentUser &&
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

  // Tab IDs for URL-based navigation (order matches navigationItems array)
  const TAB_IDS = [
    "home",
    "documents",
    "annotations",
    "analyses",
    "extracts",
    "relationships",
    "discussions",
    "chats",
    "analytics",
    "settings",
    "badges",
  ] as const;

  // Helper to navigate to a tab by index or ID
  const setActiveTab = (tabIndexOrId: number | string) => {
    const tabId =
      typeof tabIndexOrId === "number" ? TAB_IDS[tabIndexOrId] : tabIndexOrId;
    // Use null for "home" to keep URLs clean (home is default)
    updateTabParam(location, navigate, tabId === "home" ? null : tabId);
    // Refresh stats on tab switch to ensure counts are up to date
    if (validCorpusId) {
      refetchStats();
    }
  };

  // Derive active tab index from URL
  const active_tab = useMemo(() => {
    if (!urlTab) return 0; // Default to home
    const index = TAB_IDS.indexOf(urlTab as (typeof TAB_IDS)[number]);
    if (index < 0) {
      console.warn(
        `[Corpuses] Invalid tab ID "${urlTab}" in URL, defaulting to home. Valid tabs: ${TAB_IDS.join(
          ", "
        )}`
      );
    }
    return index >= 0 ? index : 0;
  }, [urlTab]);

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
            setShowArticleEditor={setShowArticleEditor}
            onNavigate={(tabIndex) => setActiveTab(tabIndex)}
            onBack={() => navigate("/corpuses")}
            canUpdate={canUpdateCorpus}
            stats={stats}
            statsLoading={effectiveStatsLoading}
            onOpenMobileMenu={() => setMobileSidebarOpen(true)}
            onSourceNavigate={handleSourceNavigate}
            isPowerUserMode={isPowerUserMode}
            onModeToggle={
              currentUser
                ? () =>
                    updateModeParam(
                      location,
                      navigate,
                      isPowerUserMode ? null : "power"
                    )
                : undefined
            }
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
              <MobileKebabButton
                onClick={() => setMobileSidebarOpen(true)}
                aria-label="Open navigation menu"
              >
                <MoreVertical />
              </MobileKebabButton>
            </TabNavigationHeader>
            <div style={{ flex: 1, overflow: "hidden" }}>
              {opened_corpus_id && (
                <FolderDocumentBrowser
                  corpusId={opened_corpus_id}
                  viewMode={documentsViewMode}
                  onViewModeChange={handleViewModeChange}
                >
                  <CorpusDocumentCards
                    opened_corpus_id={opened_corpus_id}
                    viewMode={documentsViewMode}
                    onOpenArticleEditor={() => setShowArticleEditor(true)}
                    canUpdate={canUpdateCorpus}
                  />
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
              <MobileKebabButton
                onClick={() => setMobileSidebarOpen(true)}
                aria-label="Open navigation menu"
              >
                <MoreVertical />
              </MobileKebabButton>
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
              <MobileKebabButton
                onClick={() => setMobileSidebarOpen(true)}
                aria-label="Open navigation menu"
              >
                <MoreVertical />
              </MobileKebabButton>
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
          <ExtractsTabContent
            setActiveTab={setActiveTab}
            onOpenMobileMenu={() => setMobileSidebarOpen(true)}
          />
        ),
      },
      {
        id: "relationships",
        label: "Relationships",
        icon: <Link2 />,
        badge: stats.totalRelationships,
        component: opened_corpus?.id ? (
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
              <TabTitle>Document Relationships</TabTitle>
              <MobileKebabButton
                onClick={() => setMobileSidebarOpen(true)}
                aria-label="Open navigation menu"
              >
                <MoreVertical />
              </MobileKebabButton>
            </TabNavigationHeader>
            <div style={{ flex: 1, overflow: "hidden" }}>
              <CorpusDocumentRelationships corpusId={opened_corpus.id} />
            </div>
          </div>
        ) : null,
      },
      {
        id: "discussions",
        label: "Discussions",
        icon: <MessageSquare />,
        badge: stats.totalThreads || 0,
        component: opened_corpus?.id ? (
          <div
            style={{ display: "flex", flexDirection: "column", height: "100%" }}
          >
            {/* Only show parent header when viewing thread list */}
            {/* When viewing inline thread detail, CorpusDiscussionsView handles its own */}
            {!discussionInThreadView && (
              <TabNavigationHeader>
                <BackNavButton
                  onClick={() => setActiveTab(0)}
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                  title="Back to Home"
                >
                  <ArrowLeft />
                </BackNavButton>
                <TabTitle>Discussions</TabTitle>
                <MobileKebabButton
                  onClick={() => setMobileSidebarOpen(true)}
                  aria-label="Open navigation menu"
                >
                  <MoreVertical />
                </MobileKebabButton>
              </TabNavigationHeader>
            )}
            <div style={{ flex: 1, overflow: "hidden" }}>
              <CorpusDiscussionsView corpusId={opened_corpus.id} hideHeader />
            </div>
          </div>
        ) : null,
      },
      {
        id: "chats",
        label: "Chats",
        icon: <Brain />,
        badge: stats.totalChats,
        component: opened_corpus?.id ? (
          <div
            style={{ display: "flex", flexDirection: "column", height: "100%" }}
          >
            {/* Only show parent header when CorpusChat is in list view */}
            {/* When in conversation view, CorpusChat renders its own navigation */}
            {!chatInConversation && (
              <TabNavigationHeader>
                <BackNavButton
                  onClick={() => setActiveTab(0)}
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                  title="Back to Home"
                >
                  <ArrowLeft />
                </BackNavButton>
                <TabTitle>Chat History</TabTitle>
                <MobileKebabButton
                  onClick={() => setMobileSidebarOpen(true)}
                  aria-label="Open navigation menu"
                >
                  <MoreVertical />
                </MobileKebabButton>
              </TabNavigationHeader>
            )}
            <div style={{ flex: 1, overflow: "hidden" }}>
              <CorpusChat
                corpusId={opened_corpus.id}
                showLoad={true}
                onMessageSelect={() => {}}
                onSourceNavigate={handleSourceNavigate}
                setShowLoad={() => {}}
                onViewModeChange={setChatInConversation}
                onNavigateHome={() => setActiveTab(0)}
                // The chats tab's TabNavigationHeader (rendered above when in
                // list view) already provides Back navigation on every screen
                // size, so suppress the inner filter-bar Back to avoid the
                // duplicate-back-button UX bug.
                hideListBackButton
              />
            </div>
          </div>
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
                    <MobileKebabButton
                      onClick={() => setMobileSidebarOpen(true)}
                      aria-label="Open navigation menu"
                    >
                      <MoreVertical />
                    </MobileKebabButton>
                  </TabNavigationHeader>
                  <div style={{ flex: 1, overflow: "hidden" }}>
                    <CorpusSettings
                      corpus={{
                        id: opened_corpus.id,
                        title: opened_corpus.title,
                        description: opened_corpus.description || "",
                        mdDescription: opened_corpus.mdDescription,
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
                    <MobileKebabButton
                      onClick={() => setMobileSidebarOpen(true)}
                      aria-label="Open navigation menu"
                    >
                      <MoreVertical />
                    </MobileKebabButton>
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
    stats.totalThreads,
    stats.totalChats,
    stats.totalRelationships,
    canUpdateCorpus,
    documentsViewMode, // Required for view mode toggle to work
    chatInConversation, // Required for chat tab header visibility
    currentSelectedThreadId, // Required for discussions tab header visibility (URL-driven)
    isPowerUserMode, // Required for mode toggle button label and callback
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
      <CorpusListView
        corpuses={corpus_items}
        pageInfo={corpus_response?.corpuses?.pageInfo}
        loading={
          loading_corpuses ||
          delete_corpus_loading ||
          update_corpus_loading ||
          create_corpus_loading
        }
        fetchMore={fetchMoreCorpuses}
        onCreateCorpus={() => setShowNewCorpusModal(true)}
        onImportCorpus={() => showImportCorpusModal(true)}
        searchValue={corpusSearchCache}
        onSearchChange={handleCorpusSearchChange}
        allowImport={
          REACT_APP_ALLOW_IMPORTS && Boolean(backendUser?.canImportCorpus)
        }
        activeFilter={corpusListActiveFilter}
        onFilterChange={setCorpusListActiveFilter}
        filterCounts={corpus_filter_counts}
      />
    );
  } else if (
    opened_corpus && // Corpus selected
    !opened_document // No document selected
  ) {
    // Determine the content to display in the main area
    const mainContent = isPowerUserMode
      ? currentView?.component
      : navigationItems.find((item) => item.id === "home")?.component;

    content = isPowerUserMode ? (
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
            width: use_mobile_layout ? "0" : sidebarExpanded ? "280px" : "80px",
          }}
          animate={{
            width: use_mobile_layout
              ? mobileSidebarOpen
                ? "280px"
                : "0"
              : sidebarExpanded
              ? "280px"
              : "80px",
          }}
          transition={{ duration: 0.3, ease: "easeInOut" }}
          onMouseEnter={() => !use_mobile_layout && setSidebarExpanded(true)}
          onMouseLeave={() => !use_mobile_layout && setSidebarExpanded(false)}
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
                    color: OS_LEGAL_COLORS.textMuted,
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
                    color: OS_LEGAL_COLORS.textPrimary,
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
                  {item.badge !== undefined &&
                    !sidebarExpanded &&
                    !use_mobile_layout && (
                      <CollapsedBadge $isZero={item.badge === 0}>
                        {item.badge > 0 ? item.badge : "–"}
                      </CollapsedBadge>
                    )}
                </div>
                {(use_mobile_layout ? mobileSidebarOpen : sidebarExpanded) && (
                  <>
                    <span style={{ flex: "1", textAlign: "left" }}>
                      {item.label}
                    </span>
                    {item.badge !== undefined && (
                      <NavItemBadge
                        isActive={active_tab === index}
                        $isZero={item.badge === 0}
                      >
                        {item.badge > 0 ? item.badge : "–"}
                      </NavItemBadge>
                    )}
                  </>
                )}
              </NavigationItem>
            ))}
          </NavigationItems>

          {/* Exit to Explore mode button */}
          <ExitPowerUserWrapper>
            <NavigationItem
              isActive={false}
              $isExpanded={
                use_mobile_layout ? mobileSidebarOpen : sidebarExpanded
              }
              onClick={() => updateModeParam(location, navigate, null)}
              whileHover={{ x: 2 }}
              whileTap={{ scale: 0.98 }}
              data-testid="exit-power-user"
              style={{ opacity: 0.7 }}
            >
              <ArrowLeft />
              {(use_mobile_layout ? mobileSidebarOpen : sidebarExpanded) && (
                <span style={{ flex: "1", textAlign: "left" }}>Explore</span>
              )}
            </NavigationItem>
          </ExitPowerUserWrapper>
        </NavigationSidebar>

        {/* Main content area */}
        <MainContentArea
          id="main-corpus-content-area"
          $sidebarExpanded={!use_mobile_layout && sidebarExpanded}
        >
          {mainContent}
        </MainContentArea>
      </CorpusViewContainer>
    ) : (
      <CleanViewContainer id="corpus-clean-view">
        {mainContent}
      </CleanViewContainer>
    );
  } else if (
    opened_corpus !== null &&
    opened_corpus !== undefined &&
    opened_document !== null &&
    opened_document !== undefined
  ) {
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
          {opened_corpus && showArticleEditor && (
            <CamlArticleEditor
              corpusId={opened_corpus.id}
              isOpen={showArticleEditor}
              onClose={() => setShowArticleEditor(false)}
              onUpdate={() => {
                refetchStats();
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
          <CorpusModal
            open={corpus_to_edit !== null}
            mode="EDIT"
            corpus={corpus_to_edit}
            onSubmit={handleUpdateCorpus}
            onClose={() => editingCorpus(null)}
            loading={update_corpus_loading}
          />
          <SelectExportTypeModal
            open={exporting_corpus !== null}
            onClose={() => exportingCorpus(null)}
          />
          {corpus_to_view !== null ? (
            <CorpusModal
              open={corpus_to_view !== null}
              mode="VIEW"
              corpus={corpus_to_view}
              onClose={() => viewingCorpus(null)}
            />
          ) : (
            <></>
          )}

          {show_new_corpus_modal ? (
            <CorpusModal
              open={show_new_corpus_modal}
              mode="CREATE"
              onSubmit={handleCreateNewCorpus}
              onClose={() => setShowNewCorpusModal(false)}
              loading={create_corpus_loading}
            />
          ) : (
            <></>
          )}

          <CreateExtractModal
            open={show_create_extract_modal}
            onClose={() => showCreateExtractModal(false)}
            corpusId={opened_corpus?.id}
          />
        </>
      }
      SearchBar={
        opened_corpus === null ? (
          // Search is now embedded in CorpusListView component
          <></>
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
      BreadCrumbs={null}
    >
      <ImportCorpusModal />
      {content}
    </CardLayout>
  );
};
