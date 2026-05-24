import React from "react";
import {
  MessageSquare,
  MessagesSquare,
  Layers,
  Database,
  BarChart3,
  BookOpen,
} from "lucide-react";
import { AnalysisType, ExtractType } from "../../../../types/graphql-api";
import { ChatPanelWidthMode } from "../../../annotator/context/UISettingsAtom";
import { SidebarViewMode } from "../unified_feed";
import {
  SidebarTabsContainer,
  SidebarTab,
  TabBadge,
} from "../styled/SidebarTabs";

type ViewMode = SidebarViewMode["mode"];

export interface DesktopSidebarTabsProps {
  /** Currently selected sidebar view mode */
  sidebarViewMode: ViewMode;
  /** Set the sidebar view mode */
  setSidebarViewMode: (mode: ViewMode) => void;
  /** Set right panel visibility */
  setShowRightPanel: (open: boolean) => void;
  /** Set the chat panel width mode (for discussions tab) */
  setMode: (mode: ChatPanelWidthMode) => void;
  /** Currently selected analysis (controls visibility of Analysis tab) */
  selectedAnalysis: AnalysisType | null;
  /** Currently selected extract (controls visibility of Extract tab) */
  selectedExtract: ExtractType | null;
  /** Number of threads (rendered as discussions badge when > 0) */
  threadCount: number;
  /**
   * `false` → tabs anchored to the right edge (panel closed); clicking any tab
   * opens the panel.
   * `true`  → tabs anchored to the left edge of the open panel; clicking the
   * already-active tab closes the panel.
   */
  panelOpen: boolean;
  /**
   * When `true`, the tabs render without their own fixed/absolute positioning
   * so a parent (e.g. the unified `RightEdgeRail` in DesktopDocumentLayout)
   * can stack them in a coherent column with the document tool buttons. Only
   * meaningful when `panelOpen` is `false` (panel-open positioning anchors to
   * the panel's left edge regardless).
   */
  bareContainer?: boolean;
}

/**
 * Vertical sidebar tabs rendered either to the right of the document
 * (panel closed) or on the left edge of the open panel.
 *
 * The two contexts share the same tab list and active styling but differ in
 * click behavior — see `panelOpen` prop. Discussions always pins panel width
 * to "half" so the document remains visible.
 *
 * Each tab carries an accessible name via `aria-label` and a CSS-rendered
 * tooltip via `data-tooltip` (handled by the styled `SidebarTab`). The
 * `.tab-label` span is kept in the DOM for screen-reader announcement and
 * for tests that grep by visible text, but is visually hidden.
 */
export const DesktopSidebarTabs: React.FC<DesktopSidebarTabsProps> = ({
  panelOpen,
  sidebarViewMode,
  setSidebarViewMode,
  setShowRightPanel,
  setMode,
  selectedAnalysis,
  selectedExtract,
  threadCount,
  bareContainer = false,
}) => {
  /**
   * Click handler factory:
   * - panel closed → switch view + open panel
   * - panel open  → if tab is already active, close panel; otherwise switch view
   */
  const onTabClick = (mode: ViewMode, extra?: () => void) => () => {
    if (panelOpen) {
      if (sidebarViewMode === mode) {
        setShowRightPanel(false);
        return;
      }
      setSidebarViewMode(mode);
      extra?.();
      return;
    }
    setSidebarViewMode(mode);
    setShowRightPanel(true);
    extra?.();
  };

  return (
    <SidebarTabsContainer $panelOpen={panelOpen} $bare={bareContainer}>
      <SidebarTab
        $isActive={sidebarViewMode === "index"}
        $panelOpen={panelOpen}
        onClick={onTabClick("index")}
        whileHover={{ scale: 1.02 }}
        whileTap={{ scale: 0.98 }}
        data-testid="view-mode-index"
        data-tooltip="Index"
        aria-label="Document index"
      >
        <BookOpen />
        <span className="tab-label">Index</span>
      </SidebarTab>
      <SidebarTab
        $isActive={sidebarViewMode === "chat"}
        $panelOpen={panelOpen}
        onClick={onTabClick("chat")}
        whileHover={{ scale: 1.02 }}
        whileTap={{ scale: 0.98 }}
        data-testid="view-mode-chat"
        data-tooltip="Chat"
        aria-label="Chat with this document"
      >
        <MessageSquare />
        <span className="tab-label">Chat</span>
      </SidebarTab>
      <SidebarTab
        $isActive={sidebarViewMode === "feed"}
        $panelOpen={panelOpen}
        onClick={onTabClick("feed")}
        whileHover={{ scale: 1.02 }}
        whileTap={{ scale: 0.98 }}
        data-testid="view-mode-feed"
        data-tooltip="Feed"
        aria-label="Annotation feed"
      >
        <Layers />
        <span className="tab-label">Feed</span>
      </SidebarTab>
      {selectedExtract && (
        <SidebarTab
          $isActive={sidebarViewMode === "extract"}
          $panelOpen={panelOpen}
          onClick={onTabClick("extract")}
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          data-testid="view-mode-extract"
          data-tooltip="Extract"
          aria-label="Extract results"
        >
          <Database />
          <span className="tab-label">Extract</span>
        </SidebarTab>
      )}
      {selectedAnalysis && (
        <SidebarTab
          $isActive={sidebarViewMode === "analysis"}
          $panelOpen={panelOpen}
          onClick={onTabClick("analysis")}
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          data-testid="view-mode-analysis"
          data-tooltip="Analysis"
          aria-label="Analysis results"
        >
          <BarChart3 />
          <span className="tab-label">Analysis</span>
        </SidebarTab>
      )}
      <SidebarTab
        $isActive={sidebarViewMode === "discussions"}
        $panelOpen={panelOpen}
        onClick={onTabClick("discussions", () => setMode("half"))}
        whileHover={{ scale: 1.02 }}
        whileTap={{ scale: 0.98 }}
        data-testid="view-mode-discussions"
        data-tooltip={
          threadCount > 0 ? `Discussions (${threadCount})` : "Discussions"
        }
        aria-label={
          threadCount > 0
            ? `Document discussions, ${threadCount} ${
                threadCount === 1 ? "thread" : "threads"
              }`
            : "Document discussions"
        }
      >
        {threadCount > 0 && (
          <TabBadge $isActive={sidebarViewMode === "discussions"}>
            {threadCount}
          </TabBadge>
        )}
        <MessagesSquare />
        <span className="tab-label">Discussions</span>
      </SidebarTab>
    </SidebarTabsContainer>
  );
};
