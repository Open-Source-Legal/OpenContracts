import React, { useEffect, useState } from "react";
import styled from "styled-components";

import { OS_LEGAL_COLORS } from "../../../../assets/configurations/osLegalStyles";
import { MOBILE_SURFACE_TINT } from "./mobile/mobileTheme";
import { useAnnotationSelection } from "../../../annotator/context/UISettingsAtom";
import { useChatSourceState } from "../../../annotator/context/ChatSourceAtom";
import { FullScreenModal } from "../LayoutComponents";
import { ErrorMessage } from "../../../widgets/feedback";
import { HeaderBar } from "../document_kb/HeaderBar";
import { RightPanelContent } from "../document_kb/RightPanelContent";
import { MobileAnnotationDetail } from "./mobile/MobileAnnotationDetail";
import { MobileAskBar } from "./mobile/MobileAskBar";
import { MobileDocToolbar } from "./mobile/MobileDocToolbar";
import { MobileFindSheet } from "./mobile/MobileFindSheet";
import { MobileMoreSheet } from "./mobile/MobileMoreSheet";
import { MobileSectionsSheet } from "./mobile/MobileSectionsSheet";
import { MobileSheet } from "./mobile/MobileSheet";
import { MobileTabBar, MobileTabId } from "./mobile/MobileTabBar";
import { useMobileFitToWidth } from "./mobile/useMobileFitToWidth";
import { DocumentLayoutProps } from "./types";
import UnifiedKnowledgeLayer from "../layers/UnifiedKnowledgeLayer";

/**
 * Root flex column: chrome (header / ask bar / tab bar) stays fixed while
 * only the surface area scrolls.
 *
 * Sits inside {@link FullScreenModal} (a `position: fixed`, genuinely
 * viewport-sized container), so `height: 100%` resolves to the real viewport
 * height — the bottom chrome pins to the viewport bottom and the `flex: 1`
 * surface gets real height to fill.
 */
const Root = styled.div`
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  /* Warm-neutral surface tint so white cards and chrome visibly float. */
  background: ${MOBILE_SURFACE_TINT};
  position: relative;
  overflow: hidden;
`;

/** Scrollable surface area — swaps content based on the active tab. */
const Surface = styled.div`
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  position: relative;
`;

/**
 * Document surface: a fixed toolbar on top, the viewer fills the rest.
 * The viewer itself owns its internal scrolling, so this column does not
 * scroll — it just sizes the viewer to the available space.
 */
const DocumentSurface = styled.div`
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
`;

const ViewerArea = styled.div`
  flex: 1;
  min-height: 0;
  position: relative;
  overflow: hidden;
`;

/**
 * Summary surface wrapper: fills the scrollable {@link Surface} so the
 * {@link UnifiedKnowledgeLayer} (`height: 100%`) sizes correctly.
 */
const SummarySurface = styled.div`
  height: 100%;
  min-height: 0;
`;

/**
 * Annotations surface wrapper: fills the {@link Surface} so the unified feed's
 * `AutoSizer` (which needs a measured parent) and `height: 100%` panels size
 * correctly. The feed owns its own internal scrolling.
 *
 * Must be a flex column: {@link RightPanelContent} renders the feed inside a
 * `FlexColumnPanel` (`flex: 1`), which collapses to zero height — taking the
 * feed's virtualized `AutoSizer` with it — unless its parent establishes a
 * flex context.
 */
const AnnotationsSurface = styled.div`
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
`;

/**
 * Chat sheet wrapper: fills the {@link MobileSheet} body so the chat content
 * ({@link RightPanelContent} in `chat` mode → `FlexColumnPanel` → `ChatTray`,
 * all `height: 100%`) sizes correctly. The chat owns its own scrolling, so
 * this wrapper does not scroll.
 */
const ChatSurface = styled.div`
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
`;

/** Empty state shown on the Summary tab when the document has no corpus. */
const SummaryEmptyState = styled.div`
  padding: 24px 16px;
  font-size: 14px;
  color: ${OS_LEGAL_COLORS.textSecondary};
  text-align: center;
`;

/** Centered padded container for the GraphQL load-failure message. */
const ErrorSurface = styled.div`
  padding: 32px 16px;
  text-align: center;
`;

/**
 * Mobile layout for the DocumentKnowledgeBase.
 *
 * Owns only local UI state (the active {@link MobileTabId} and which sheets
 * are open); every other value is threaded in via
 * {@link DocumentLayoutProps} — the same interface the desktop layout
 * consumes. The two layouts are alternative presentations of identical
 * data/state.
 *
 * The Document surface renders the real document viewer
 * ({@link DocumentLayoutProps.viewerContent}) below a
 * {@link MobileDocToolbar}, defaulting to fit-to-width so the document is
 * readable on mount. Sections and Find open {@link MobileSheet}s over the
 * existing structural-annotation and text-search systems. The Summary surface
 * embeds the {@link UnifiedKnowledgeLayer}.
 *
 * The Annotations surface renders the existing unified annotation feed
 * full-screen ({@link RightPanelContent} in `feed` mode). Selecting an
 * annotation — from a feed row or from a highlight in the Document-tab viewer —
 * opens the shared "Annotation" {@link MobileSheet} with the existing
 * single-annotation detail card.
 *
 * The {@link MobileAskBar} opens the AI chat in a dedicated "Chat"
 * {@link MobileSheet}: focusing the bar opens an empty conversation, submitting
 * text opens the sheet and threads the query through as `pendingChatMessage`.
 * The sheet reuses {@link RightPanelContent} in `chat` mode (the same component
 * the desktop right tray renders). When a chat source citation is clicked it
 * sets a non-null `selectedSourceIndex` on the shared chat-source atom; an
 * effect watches that transition, closes the Chat sheet, and switches the
 * active tab to `document` so the cited annotation scrolls into view in the
 * viewer.
 *
 * The More tab opens a "More" {@link MobileSheet} hosting {@link MobileMoreSheet}
 * — a tappable list of the Tier-2 surfaces (Discussions, Notes, Document info &
 * versions). That component swaps its own body between the menu and the chosen
 * surface with a back affordance, so exactly one sheet is open at a time.
 */
export const MobileDocumentLayout: React.FC<DocumentLayoutProps> = (props) => {
  const {
    documentId,
    corpusId,
    readOnly,
    metadata,
    hasCorpus,
    viewerContent,
    zoomLevel,
    setZoomLevel,
    handleClose,
    setShowAddToCorpusModal,
    setActiveLayer,
    setSidebarViewMode,
    setPendingChatMessage,
    sidebarViewMode,
    feedFilters,
    setFeedFilters,
    feedSortBy,
    setFeedSortBy,
    searchText,
    selectedAnalysis,
    selectedExtract,
    dataCells,
    columns,
    notes,
    loading,
    queryError,
    setSelectedNote,
    pendingChatMessage,
  } = props;

  const [activeTab, setActiveTab] = useState<MobileTabId>("document");
  const [moreSheetOpen, setMoreSheetOpen] = useState(false);
  const [sectionsSheetOpen, setSectionsSheetOpen] = useState(false);
  const [findSheetOpen, setFindSheetOpen] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);

  const { selectedAnnotations, setSelectedAnnotations } =
    useAnnotationSelection();

  // A chat source citation click sets a non-null `selectedSourceIndex` on the
  // shared chat-source atom (see ChatTray's per-source `onClick`). When that
  // happens while the Chat sheet is open, dismiss the sheet and switch to the
  // Document tab so the cited annotation scrolls into view in the viewer.
  const { selectedSourceIndex } = useChatSourceState();
  useEffect(() => {
    if (selectedSourceIndex != null && chatOpen) {
      setChatOpen(false);
      setActiveLayer("document");
      setActiveTab("document");
    }
  }, [selectedSourceIndex, chatOpen, setActiveLayer]);

  // Fit-to-width: default the document to a readable zoom on mount and back
  // the toolbar's "Fit width" chip. Gated on the Document tab being active.
  const { fitToWidth } = useMobileFitToWidth({
    active: activeTab === "document",
    setZoomLevel,
  });

  const handleSelectTab = (tab: MobileTabId) => {
    switch (tab) {
      case "document":
        setActiveLayer("document");
        setActiveTab("document");
        break;
      case "summary":
        setActiveLayer("knowledge");
        setActiveTab("summary");
        break;
      case "annotations":
        setActiveLayer("document");
        setSidebarViewMode("feed");
        setActiveTab("annotations");
        break;
      case "more":
        setMoreSheetOpen(true);
        break;
    }
  };

  return (
    <FullScreenModal
      id="mobile-knowledge-base-modal"
      open={true}
      onClose={handleClose}
    >
      <Root>
        <HeaderBar
          metadata={metadata}
          documentId={documentId}
          corpusId={corpusId}
          hasCorpus={Boolean(hasCorpus)}
          readOnly={readOnly}
          onAddToCorpus={() => setShowAddToCorpusModal(true)}
          onClose={handleClose}
        />

        <Surface>
          {queryError && (
            <ErrorSurface data-testid="mobile-surface-error">
              <ErrorMessage title="Error loading document">
                {queryError.message}
              </ErrorMessage>
            </ErrorSurface>
          )}
          {!queryError && activeTab === "document" && (
            <DocumentSurface data-testid="mobile-surface-document">
              <MobileDocToolbar
                zoomPercent={zoomLevel * 100}
                onFitWidth={fitToWidth}
                onSections={() => setSectionsSheetOpen(true)}
                onFind={() => setFindSheetOpen(true)}
              />
              <ViewerArea>{viewerContent}</ViewerArea>
            </DocumentSurface>
          )}
          {!queryError && activeTab === "summary" && (
            <SummarySurface data-testid="mobile-surface-summary">
              {corpusId ? (
                <UnifiedKnowledgeLayer
                  documentId={documentId}
                  corpusId={corpusId}
                  metadata={metadata}
                  parentLoading={loading}
                  readOnly={readOnly}
                />
              ) : (
                <SummaryEmptyState>
                  Add this document to a corpus to view its summary.
                </SummaryEmptyState>
              )}
            </SummarySurface>
          )}
          {!queryError && activeTab === "annotations" && (
            <AnnotationsSurface data-testid="mobile-surface-annotations">
              <RightPanelContent
                compact
                showRightPanel={true}
                sidebarViewMode="feed"
                setSidebarViewMode={setSidebarViewMode}
                feedFilters={feedFilters}
                setFeedFilters={setFeedFilters}
                feedSortBy={feedSortBy}
                setFeedSortBy={setFeedSortBy}
                searchText={searchText}
                selectedAnalysis={selectedAnalysis}
                selectedExtract={selectedExtract}
                dataCells={dataCells}
                columns={columns}
                notes={notes}
                loading={loading}
                readOnly={readOnly}
                documentId={documentId}
                corpusId={corpusId}
                setActiveLayer={setActiveLayer}
                setSelectedNote={setSelectedNote}
                pendingChatMessage={pendingChatMessage}
              />
            </AnnotationsSurface>
          )}
        </Surface>

        <MobileAskBar
          onActivate={() => {
            setSidebarViewMode("chat");
            setChatOpen(true);
          }}
          onSubmit={(text) => {
            setPendingChatMessage(text);
            setSidebarViewMode("chat");
            setChatOpen(true);
          }}
        />

        {/* While the More sheet is open the underlying surface is unchanged
          (the sheet is an overlay, not a tab surface), so `activeTab` keeps
          its real value. Derive the tab bar's selected state so the More tab
          still reads as selected — and reverts on close — without disturbing
          the surface or needing previous-tab restore logic. */}
        <MobileTabBar
          active={moreSheetOpen ? "more" : activeTab}
          onSelect={handleSelectTab}
        />

        <MobileSheet
          open={sectionsSheetOpen}
          title="Sections"
          onClose={() => setSectionsSheetOpen(false)}
        >
          <MobileSectionsSheet
            open={sectionsSheetOpen}
            onNavigate={(annotationId) => {
              setSelectedAnnotations([annotationId]);
              setSectionsSheetOpen(false);
            }}
          />
        </MobileSheet>

        <MobileSheet
          open={findSheetOpen}
          title="Find in document"
          onClose={() => setFindSheetOpen(false)}
        >
          <MobileFindSheet open={findSheetOpen} />
        </MobileSheet>

        {/* More sheet — a tappable list of the Tier-2 surfaces (Discussions,
          Notes, Document info & versions). MobileMoreSheet swaps its own body
          between the menu list and the chosen surface with a back affordance,
          so only one sheet is ever open. Discussions and Notes reuse
          RightPanelContent; the info view is a read-only render of `metadata`. */}
        <MobileSheet
          open={moreSheetOpen}
          title="More"
          onClose={() => setMoreSheetOpen(false)}
        >
          <MobileMoreSheet
            metadata={metadata}
            setSidebarViewMode={setSidebarViewMode}
            feedFilters={feedFilters}
            setFeedFilters={setFeedFilters}
            feedSortBy={feedSortBy}
            setFeedSortBy={setFeedSortBy}
            searchText={searchText}
            selectedAnalysis={selectedAnalysis}
            selectedExtract={selectedExtract}
            dataCells={dataCells}
            columns={columns}
            notes={notes}
            loading={loading}
            readOnly={readOnly}
            documentId={documentId}
            corpusId={corpusId}
            setActiveLayer={setActiveLayer}
            setSelectedNote={setSelectedNote}
          />
        </MobileSheet>

        {/* Chat sheet — the persistent Ask bar opens the AI chat full-screen.
          Reuses RightPanelContent in `chat` mode (the same ChatTray-backed
          component the desktop right tray renders), with `showRightPanel`
          forced true so the content is never gated off. `pendingChatMessage`
          is threaded straight through to ChatTray's `initialMessage`. */}
        <MobileSheet
          open={chatOpen}
          title="Chat"
          onClose={() => setChatOpen(false)}
        >
          <ChatSurface data-testid="mobile-surface-chat">
            <RightPanelContent
              showRightPanel={true}
              sidebarViewMode="chat"
              setSidebarViewMode={setSidebarViewMode}
              feedFilters={feedFilters}
              setFeedFilters={setFeedFilters}
              feedSortBy={feedSortBy}
              setFeedSortBy={setFeedSortBy}
              searchText={searchText}
              selectedAnalysis={selectedAnalysis}
              selectedExtract={selectedExtract}
              dataCells={dataCells}
              columns={columns}
              notes={notes}
              loading={loading}
              readOnly={readOnly}
              documentId={documentId}
              corpusId={corpusId}
              setActiveLayer={setActiveLayer}
              setSelectedNote={setSelectedNote}
              pendingChatMessage={pendingChatMessage}
            />
          </ChatSurface>
        </MobileSheet>

        {/* Annotation detail sheet — single rendering site for both open paths:
          tapping a feed row in the Annotations surface and tapping a highlight
          in the Document-tab viewer. Both set the shared `selectedAnnotations`
          selection; closing the sheet clears it. */}
        <MobileSheet
          open={selectedAnnotations.length > 0}
          title="Annotation"
          onClose={() => setSelectedAnnotations([])}
        >
          <MobileAnnotationDetail readOnly={readOnly} />
        </MobileSheet>
      </Root>
    </FullScreenModal>
  );
};
