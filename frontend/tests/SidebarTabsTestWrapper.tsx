import React, { useState } from "react";
import styled from "styled-components";
import { DesktopSidebarTabs } from "../src/components/knowledge_base/document/document_kb/SidebarTabs";
import {
  RailDivider,
  RightEdgeRail,
  SidebarTab,
} from "../src/components/knowledge_base/document/styled/SidebarTabs";
import { AnalysisType, ExtractType } from "../src/types/graphql-api";
import { ChatPanelWidthMode } from "../src/components/annotator/context/UISettingsAtom";
import { SidebarViewMode } from "../src/components/knowledge_base/document/unified_feed";
import { OS_LEGAL_COLORS } from "../src/assets/configurations/osLegalStyles";
import { Settings, BarChart3, Database, Plus } from "lucide-react";

type ViewMode = SidebarViewMode["mode"];

interface SidebarTabsHarnessProps {
  variant: "desktop";
  initialMode?: ViewMode;
  panelOpen?: boolean;
  initialShowRightPanel?: boolean;
  selectedAnalysis?: AnalysisType | null;
  selectedExtract?: ExtractType | null;
  threadCount?: number;
}

/**
 * Harness for the desktop sidebar tabs. Holds enough local state to exercise
 * the tab switching + panel-toggle behavior so tests can click and observe the
 * resulting active state.
 */
export const SidebarTabsHarness: React.FC<SidebarTabsHarnessProps> = ({
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
        width: 600,
        minHeight: 400,
        padding: "1rem",
        // Push the harness so DesktopSidebarTabs' `left: -48px` (when
        // panelOpen=true, position: absolute relative to this container)
        // still resolves to an on-screen x coordinate.
        marginLeft: 100,
        background: "#fff",
        position: "relative",
      }}
      data-testid="sidebar-tabs-harness"
    >
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
      <span data-testid="active-mode">{sidebarViewMode}</span>
      <span data-testid="panel-open">{showRightPanel ? "open" : "closed"}</span>
    </div>
  );
};

/**
 * Visual harness for the unified right-edge rail (issue #1734). Mirrors the
 * structure DesktopDocumentLayout renders when the right panel is closed —
 * `DesktopSidebarTabs` (bare) → divider → action buttons (extracts /
 * analyses / create / settings) — so we can capture a focused screenshot of
 * the consolidated control region without spinning up the full
 * DocumentKnowledgeBase test wrapper.
 *
 * Uses static `SidebarTab` pills for the action group rather than the real
 * `FloatingDocumentControls`, which depends on Apollo + Jotai + corpus
 * permissions setup; the visual contract (shared pill shape, icon-only,
 * tooltip on hover, accent color) is identical, which is what the
 * screenshot is verifying.
 *
 * The outer rail is the canonical `RightEdgeRail` styled primitive imported
 * from `styled/SidebarTabs.tsx` — same positioning + z-index as production.
 */
const RailMockBackdrop = styled.div`
  position: relative;
  width: 100%;
  height: 100vh;
  min-height: 720px;
  background: linear-gradient(180deg, #fafafa 0%, #f4f4f5 100%);
  overflow: hidden;
`;

const MockDocumentSurface = styled.div`
  position: absolute;
  inset: 16px 80px 16px 16px;
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 32px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);

  h2 {
    margin: 0 0 8px;
    font-size: 18px;
    color: #1e293b;
    font-weight: 600;
  }

  p {
    margin: 0;
    font-size: 14px;
    line-height: 1.6;
    color: #475569;
    max-width: 520px;
  }
`;

interface RightEdgeRailHarnessProps {
  /**
   * When true, render the optional Extract / Analysis navigation tabs so the
   * screenshot exercises the longest variant of the rail.
   */
  withSelections?: boolean;
  /**
   * Show the unread badge on Discussions.
   */
  threadCount?: number;
  /**
   * When true, render the create-analysis pill at the bottom of the action
   * group.
   */
  canCreateAnalysis?: boolean;
}

export const RightEdgeRailHarness: React.FC<RightEdgeRailHarnessProps> = ({
  withSelections = false,
  threadCount = 0,
  canCreateAnalysis = true,
}) => {
  const fakeAnalysis = withSelections
    ? ({
        id: "harness-analysis",
        analysisStarted: null,
        analysisCompleted: null,
        status: "COMPLETED",
      } as unknown as AnalysisType)
    : null;

  const fakeExtract = withSelections
    ? ({
        id: "harness-extract",
        name: "Harness Extract",
        started: null,
        finished: null,
      } as unknown as ExtractType)
    : null;

  return (
    <RailMockBackdrop data-testid="right-edge-rail-harness">
      <MockDocumentSurface>
        <h2>Sample Document</h2>
        <p>
          This harness reproduces the unified right-edge control rail —
          navigation tabs above, a divider, then the document-tool pills below —
          exactly as the desktop document knowledge base renders it when the
          right panel is closed.
        </p>
      </MockDocumentSurface>
      <RightEdgeRail data-testid="right-edge-rail">
        <DesktopSidebarTabs
          panelOpen={false}
          bareContainer
          sidebarViewMode="chat"
          setSidebarViewMode={() => {}}
          setShowRightPanel={() => {}}
          setMode={() => {}}
          selectedAnalysis={fakeAnalysis}
          selectedExtract={fakeExtract}
          threadCount={threadCount}
        />
        <RailDivider aria-hidden="true" />
        <SidebarTab
          $isActive={false}
          $panelOpen={false}
          data-tooltip="Annotation filters"
          aria-label="Annotation filters"
        >
          <Settings />
        </SidebarTab>
        <SidebarTab
          $isActive={false}
          $panelOpen={false}
          $accent="#8b5cf6"
          data-tooltip="View extracts"
          aria-label="View extracts"
        >
          <Database />
        </SidebarTab>
        <SidebarTab
          $isActive={false}
          $panelOpen={false}
          $accent={OS_LEGAL_COLORS.folderIcon}
          data-tooltip="View analyses"
          aria-label="View analyses"
        >
          <BarChart3 />
        </SidebarTab>
        {canCreateAnalysis && (
          <SidebarTab
            $isActive={false}
            $panelOpen={false}
            $accent={OS_LEGAL_COLORS.greenMedium}
            data-tooltip="Start new analysis"
            aria-label="Start new analysis"
          >
            <Plus />
          </SidebarTab>
        )}
      </RightEdgeRail>
    </RailMockBackdrop>
  );
};
