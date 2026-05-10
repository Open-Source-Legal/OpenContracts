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
  MobileTabBar,
  MobileTab,
} from "../styled/SidebarTabs";

type ViewMode = SidebarViewMode["mode"];

interface CommonProps {
  /** Currently selected sidebar view mode */
  sidebarViewMode: ViewMode;
  /** Set the sidebar view mode */
  setSidebarViewMode: (mode: ViewMode) => void;
  /** Whether the right panel is visible (used by mobile bar) */
  showRightPanel: boolean;
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
}

export interface DesktopSidebarTabsProps
  extends Omit<CommonProps, "showRightPanel"> {
  /**
   * `false` → tabs anchored to the right edge (panel closed); clicking any tab
   * opens the panel.
   * `true`  → tabs anchored to the left edge of the open panel; clicking the
   * already-active tab closes the panel.
   */
  panelOpen: boolean;
}

/**
 * Vertical sidebar tabs rendered either to the right of the document
 * (panel closed) or on the left edge of the open panel.
 *
 * The two contexts share the same tab list and active styling but differ in
 * click behavior — see `panelOpen` prop. Discussions always pins panel width
 * to "half" so the document remains visible.
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
    <SidebarTabsContainer $panelOpen={panelOpen}>
      <SidebarTab
        $isActive={sidebarViewMode === "index"}
        $panelOpen={panelOpen}
        onClick={onTabClick("index")}
        whileHover={{ scale: 1.02 }}
        whileTap={{ scale: 0.98 }}
        data-testid="view-mode-index"
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
        aria-label="Document discussions"
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

export type MobileSidebarTabsProps = CommonProps;

/**
 * Horizontal tab bar shown at the top of the open right panel on mobile only
 * (CSS-driven via `MobileTabBar` styled component). Tap behavior:
 * - inactive tab → switch view
 * - active tab → toggle panel closed (Discussions toggles panel state)
 *
 * Discussions on mobile pins the panel to "full" width so the conversation
 * thread has room to breathe on small screens.
 */
export const MobileSidebarTabs: React.FC<MobileSidebarTabsProps> = ({
  sidebarViewMode,
  setSidebarViewMode,
  showRightPanel,
  setShowRightPanel,
  setMode,
  selectedAnalysis,
  selectedExtract,
  threadCount,
}) => {
  const onTabClick =
    (mode: ViewMode, extra?: () => void, toggleOnActive = false) =>
    () => {
      if (sidebarViewMode === mode) {
        setShowRightPanel(toggleOnActive ? !showRightPanel : false);
        return;
      }
      setSidebarViewMode(mode);
      extra?.();
    };

  return (
    <MobileTabBar>
      <MobileTab
        $active={sidebarViewMode === "index"}
        onClick={onTabClick("index")}
        data-testid="mobile-view-mode-index"
      >
        <BookOpen />
        <span>Index</span>
      </MobileTab>
      <MobileTab
        $active={sidebarViewMode === "chat"}
        onClick={onTabClick("chat")}
        data-testid="mobile-view-mode-chat"
      >
        <MessageSquare />
        <span>Chat</span>
      </MobileTab>
      <MobileTab
        $active={sidebarViewMode === "feed"}
        onClick={onTabClick("feed")}
        data-testid="mobile-view-mode-feed"
      >
        <Layers />
        <span>Feed</span>
      </MobileTab>
      {selectedExtract && (
        <MobileTab
          $active={sidebarViewMode === "extract"}
          onClick={onTabClick("extract")}
          data-testid="mobile-view-mode-extract"
        >
          <Database />
          <span>Extract</span>
        </MobileTab>
      )}
      {selectedAnalysis && (
        <MobileTab
          $active={sidebarViewMode === "analysis"}
          onClick={onTabClick("analysis")}
          data-testid="mobile-view-mode-analysis"
        >
          <BarChart3 />
          <span>Analysis</span>
        </MobileTab>
      )}
      <MobileTab
        $active={sidebarViewMode === "discussions"}
        onClick={onTabClick(
          "discussions",
          () => {
            setShowRightPanel(true);
            setMode("full");
          },
          true
        )}
        aria-label="Document discussions"
      >
        <MessagesSquare />
        <span>
          Discussions
          {threadCount > 0 ? ` (${threadCount})` : ""}
        </span>
      </MobileTab>
    </MobileTabBar>
  );
};
