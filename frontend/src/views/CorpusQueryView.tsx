import { useEffect, useRef, useState } from "react";
import { useReactiveVar } from "@apollo/client";
import { ArrowLeft, History, Home } from "lucide-react";
import styled from "styled-components";
import { motion } from "framer-motion";

import { OS_LEGAL_COLORS } from "../assets/configurations/osLegalStyles";
import { MOBILE_VIEW_BREAKPOINT } from "../assets/configurations/constants";
import { showQueryViewState } from "../graphql/cache";
import { CorpusType } from "../types/graphql-api";
import { CorpusChat } from "../components/corpuses/CorpusChat";
import { CorpusHome } from "../components/corpuses/CorpusHome";
import { ChatMessageSource } from "../components/annotator/context/ChatSourceAtom";
import useWindowDimensions from "../components/hooks/WindowDimensionHook";

// ===============================================
// LOCAL CONSTANTS
// ===============================================
// Cap on motion-wrapper height so the composer never overflows the viewport
// when child rendering reports unusually tall content (e.g. virtualized chat
// transcripts during a layout shift).
// Height for the home-tab views (chat-expanded, dashboard, conversation list).
// Matches the available viewport area below the App-shell navbar so the chat
// input stays pinned at the bottom of the viewport instead of being pushed
// below it. Override via the --oc-navbar-height CSS variable when the navbar
// height changes (defaults to 4.5rem, ~72px, which matches the @os-legal/ui
// .oc-navbar default).
const COMPOSER_MAX_HEIGHT = "calc(100dvh - var(--oc-navbar-height, 4.5rem))";
// Delay (ms) before focusing the search input on initial desktop mount —
// the longer wait gives the textarea time to mount inside CorpusHome.
const MOUNT_FOCUS_DELAY_MS = 150;
// Delay (ms) before refocusing the search input when returning to search mode
// (after a chat is dismissed). Shorter than the mount delay because the
// textarea is already mounted at this point.
const RETURN_FOCUS_DELAY_MS = 100;

// ===============================================
// PRIVATE STYLES
// ===============================================
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

const SearchActionsContainer = styled.div`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-shrink: 0;

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
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
      background: ${OS_LEGAL_COLORS.primaryBlueHover};
      border-color: ${OS_LEGAL_COLORS.primaryBlueHover};
    }
  }

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
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

  @media (max-width: ${MOBILE_VIEW_BREAKPOINT}px) {
    padding: 0.5rem;

    span {
      display: none;
    }
  }
`;

// ===============================================
// COMPONENT
// ===============================================
interface CorpusQueryViewProps {
  opened_corpus: CorpusType | null;
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
  navigateBackLabel?: string;
}

/**
 * CorpusQueryView - The corpus dashboard / chat composer rendered inside the
 * "Home" tab of {@link Corpuses}. Owns the local search-input ↔ expanded-chat
 * transition and forwards all permission, navigation, and stats props through
 * to {@link CorpusHome} / {@link CorpusChat}.
 */
export const CorpusQueryView = ({
  opened_corpus,
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
  navigateBackLabel,
}: CorpusQueryViewProps) => {
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
    if (!isDesktop || !inputRef.current) return;
    const id = setTimeout(
      () => inputRef.current?.focus(),
      MOUNT_FOCUS_DELAY_MS
    );
    return () => clearTimeout(id);
    // intentional: mount-only; isDesktop is read once to avoid re-firing on
    // viewport resize (which would pop the mobile keyboard mid-session).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Focus the input when returning to search mode
  useEffect(() => {
    if (!isSearchMode || !inputRef.current || !isDesktop) return;
    const id = setTimeout(
      () => inputRef.current?.focus(),
      RETURN_FOCUS_DELAY_MS
    );
    return () => clearTimeout(id);
  }, [isSearchMode, isDesktop]);

  const resetToSearch = () => {
    setChatExpanded(false);
    setChatExpandedInConversation(false);
    setIsSearchMode(true);
    setSearchQuery("");
    // Focus is scheduled by the `isSearchMode` effect above. Calling
    // `setIsSearchMode(true)` from a non-search mode triggers the effect,
    // which owns the focus timer + cleanup. Don't double-schedule a focus
    // here — a stale ref-owned timer cannot be cancelled by the effect's
    // cleanup, so a second source could fire against an unmounted input.
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
              data-testid="corpus-query-view-home-btn"
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
            height: COMPOSER_MAX_HEIGHT,
            maxHeight: COMPOSER_MAX_HEIGHT,
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
          height: COMPOSER_MAX_HEIGHT,
          maxHeight: COMPOSER_MAX_HEIGHT,
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
              corpus={opened_corpus}
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
              navigateBackLabel={navigateBackLabel}
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
          height: COMPOSER_MAX_HEIGHT,
          maxHeight: COMPOSER_MAX_HEIGHT,
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
