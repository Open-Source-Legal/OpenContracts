import React, { useState } from "react";
import styled from "styled-components";

import { OS_LEGAL_COLORS } from "../../../../assets/configurations/osLegalStyles";
import { HeaderBar } from "../document_kb/HeaderBar";
import { MobileAskBar } from "./mobile/MobileAskBar";
import { MobileSheet } from "./mobile/MobileSheet";
import { MobileTabBar, MobileTabId } from "./mobile/MobileTabBar";
import { DesktopDocumentLayoutProps } from "./DesktopDocumentLayout";

/**
 * Root flex column: chrome (header / ask bar / tab bar) stays fixed while
 * only the surface area scrolls.
 */
const Root = styled.div`
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  background: ${OS_LEGAL_COLORS.background};
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

/** Placeholder body for the "More" sheet — replaced by Task 12. */
const SheetPlaceholder = styled.div`
  padding: 16px;
  font-size: 14px;
  color: ${OS_LEGAL_COLORS.textSecondary};
`;

/**
 * Mobile layout for the DocumentKnowledgeBase.
 *
 * Owns only local tab-switching state ({@link MobileTabId}); every other value
 * is threaded in via {@link DesktopDocumentLayoutProps} — the same interface
 * the desktop layout consumes. The two layouts are alternative presentations
 * of identical data/state.
 *
 * This is the Task 7 skeleton: chrome (header, ask bar, tab bar) plus tab
 * switching with placeholder surfaces. Tasks 8–12 fill in the real
 * Document / Summary / Annotations / Chat / More surfaces.
 */
export const MobileDocumentLayout: React.FC<DesktopDocumentLayoutProps> = (
  props
) => {
  const {
    documentId,
    corpusId,
    readOnly,
    metadata,
    hasCorpus,
    mainLayerContent,
    handleClose,
    setShowAddToCorpusModal,
    setActiveLayer,
    setSidebarViewMode,
    setShowRightPanel,
    setPendingChatMessage,
  } = props;

  const [activeTab, setActiveTab] = useState<MobileTabId>("document");
  const [moreSheetOpen, setMoreSheetOpen] = useState(false);

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
        {activeTab === "document" && (
          <div data-testid="mobile-surface-document">{mainLayerContent}</div>
        )}
        {activeTab === "summary" && (
          <div data-testid="mobile-surface-summary">{mainLayerContent}</div>
        )}
        {activeTab === "annotations" && (
          <div data-testid="mobile-surface-annotations">{mainLayerContent}</div>
        )}
      </Surface>

      <MobileAskBar
        onActivate={() => {
          setSidebarViewMode("chat");
          setShowRightPanel(true);
        }}
        onSubmit={(text) => {
          setPendingChatMessage(text);
          setSidebarViewMode("chat");
          setShowRightPanel(true);
        }}
      />

      <MobileTabBar active={activeTab} onSelect={handleSelectTab} />

      <MobileSheet
        open={moreSheetOpen}
        title="More"
        onClose={() => setMoreSheetOpen(false)}
      >
        <SheetPlaceholder data-testid="mobile-surface-more">
          More options coming soon.
        </SheetPlaceholder>
      </MobileSheet>
    </Root>
  );
};

export default MobileDocumentLayout;
