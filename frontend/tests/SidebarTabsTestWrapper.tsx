import React, { useState } from "react";
import {
  DesktopSidebarTabs,
  MobileSidebarTabs,
} from "../src/components/knowledge_base/document/document_kb/SidebarTabs";
import { AnalysisType, ExtractType } from "../src/types/graphql-api";
import { ChatPanelWidthMode } from "../src/components/annotator/context/UISettingsAtom";
import { SidebarViewMode } from "../src/components/knowledge_base/document/unified_feed";

type ViewMode = SidebarViewMode["mode"];

interface SidebarTabsHarnessProps {
  variant: "desktop" | "mobile";
  initialMode?: ViewMode;
  panelOpen?: boolean;
  initialShowRightPanel?: boolean;
  selectedAnalysis?: AnalysisType | null;
  selectedExtract?: ExtractType | null;
  threadCount?: number;
}

/**
 * Harness for the desktop / mobile sidebar tab variants. Holds enough local
 * state to exercise the tab switching + panel-toggle behavior so tests can
 * click and observe the resulting active state.
 */
export const SidebarTabsHarness: React.FC<SidebarTabsHarnessProps> = ({
  variant,
  initialMode = "index",
  panelOpen = false,
  initialShowRightPanel = false,
  selectedAnalysis = null,
  selectedExtract = null,
  threadCount = 0,
}) => {
  const [sidebarViewMode, setSidebarViewMode] = useState<ViewMode>(initialMode);
  const [showRightPanel, setShowRightPanel] = useState<boolean>(
    initialShowRightPanel
  );
  const setMode = (_m: ChatPanelWidthMode) => {};

  return (
    <div
      style={{
        width: variant === "mobile" ? 360 : 600,
        minHeight: 400,
        padding: "1rem",
        // Push the harness so DesktopSidebarTabs' `left: -48px` (when
        // panelOpen=true, position: absolute relative to this container)
        // still resolves to an on-screen x coordinate.
        marginLeft: variant === "desktop" ? 100 : 0,
        background: "#fff",
        position: "relative",
      }}
      data-testid="sidebar-tabs-harness"
    >
      {variant === "desktop" ? (
        <DesktopSidebarTabs
          panelOpen={panelOpen}
          sidebarViewMode={sidebarViewMode}
          setSidebarViewMode={setSidebarViewMode}
          setShowRightPanel={setShowRightPanel}
          setMode={setMode}
          selectedAnalysis={selectedAnalysis}
          selectedExtract={selectedExtract}
          threadCount={threadCount}
        />
      ) : (
        <MobileSidebarTabs
          sidebarViewMode={sidebarViewMode}
          setSidebarViewMode={setSidebarViewMode}
          showRightPanel={showRightPanel}
          setShowRightPanel={setShowRightPanel}
          setMode={setMode}
          selectedAnalysis={selectedAnalysis}
          selectedExtract={selectedExtract}
          threadCount={threadCount}
        />
      )}
      <span data-testid="active-mode">{sidebarViewMode}</span>
      <span data-testid="panel-open">{showRightPanel ? "open" : "closed"}</span>
    </div>
  );
};
