import React, { useState } from "react";
import styled from "styled-components";
import {
  ArrowLeft,
  Calendar,
  ChevronRight,
  FileText,
  FileType,
  Info,
  MessagesSquare,
  StickyNote,
  User,
} from "lucide-react";

import { OS_LEGAL_COLORS } from "../../../../../assets/configurations/osLegalStyles";
import { getCreatorDisplay } from "../../../../../utils/userDisplay";
import { formatShortDate } from "../../../../../utils/formatters";
import {
  RightPanelContent,
  RightPanelContentProps,
} from "../../document_kb/RightPanelContent";
import type { DocumentMetadata } from "../../document_kb/HeaderBar";
import type { ContentFilters, ContentItemType } from "../../unified_feed/types";

/**
 * Which Tier-2 surface the More sheet is currently showing. `menu` is the
 * tappable list; the other values render a single surface with a back
 * affordance returning to `menu`.
 */
type MoreView = "menu" | "discussions" | "notes" | "info";

/**
 * Props for {@link MobileMoreSheet}. Mirrors the slice of
 * {@link RightPanelContentProps} the embedded surfaces need, plus the
 * document `metadata` used by the read-only info view.
 *
 * `feedFilters` / `setFeedFilters` etc. are threaded straight through to
 * {@link RightPanelContent}. The Notes surface, however, renders the unified
 * feed with a *fixed* notes-only filter (notes have no standalone
 * `SidebarViewMode`) so it does not disturb the live Annotations-tab filters.
 */
export interface MobileMoreSheetProps {
  /** Document metadata for the read-only info view. */
  metadata: DocumentMetadata;
  /** Setter for the shared sidebar view mode (kept in sync for Discussions). */
  setSidebarViewMode: RightPanelContentProps["setSidebarViewMode"];
  feedFilters: RightPanelContentProps["feedFilters"];
  setFeedFilters: RightPanelContentProps["setFeedFilters"];
  feedSortBy: RightPanelContentProps["feedSortBy"];
  setFeedSortBy: RightPanelContentProps["setFeedSortBy"];
  searchText: RightPanelContentProps["searchText"];
  selectedAnalysis: RightPanelContentProps["selectedAnalysis"];
  selectedExtract: RightPanelContentProps["selectedExtract"];
  dataCells: RightPanelContentProps["dataCells"];
  columns: RightPanelContentProps["columns"];
  notes: RightPanelContentProps["notes"];
  loading: RightPanelContentProps["loading"];
  readOnly: RightPanelContentProps["readOnly"];
  documentId: RightPanelContentProps["documentId"];
  corpusId: RightPanelContentProps["corpusId"];
  setActiveLayer: RightPanelContentProps["setActiveLayer"];
  setSelectedNote: RightPanelContentProps["setSelectedNote"];
}

/** Notes-only feed filter — the canonical surface for notes is the unified feed. */
const NOTES_ONLY_FILTER: ContentFilters = {
  contentTypes: new Set<ContentItemType>(["note"]),
};

const Container = styled.div`
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
`;

const Menu = styled.div`
  display: flex;
  flex-direction: column;
`;

const Row = styled.button`
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 16px;
  border: none;
  border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
  background: white;
  text-align: left;
  cursor: pointer;

  &:active {
    background: ${OS_LEGAL_COLORS.surfaceHover};
  }
`;

const RowText = styled.div`
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
`;

const RowLabel = styled.span`
  font-size: 15px;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textPrimary};
`;

const RowDescription = styled.span`
  font-size: 12px;
  color: ${OS_LEGAL_COLORS.textSecondary};
`;

/** Sub-view header with a back button returning to the menu list. */
const SubHeader = styled.div`
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
  background: white;
`;

const BackButton = styled.button`
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border: none;
  border-radius: 8px;
  background: ${OS_LEGAL_COLORS.surfaceHover};
  color: ${OS_LEGAL_COLORS.textSecondary};
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
`;

/** Wrapper that fills the sheet body so embedded `height: 100%` panels size. */
const SurfaceFill = styled.div`
  flex: 1;
  min-height: 0;
`;

const InfoList = styled.div`
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 8px 0;
`;

const InfoRow = styled.div`
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
`;

const InfoText = styled.div`
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
`;

const InfoLabel = styled.span`
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: ${OS_LEGAL_COLORS.textSecondary};
`;

const InfoValue = styled.span`
  font-size: 14px;
  color: ${OS_LEGAL_COLORS.textPrimary};
  word-break: break-word;
`;

const ICON_COLOR = OS_LEGAL_COLORS.primaryBlue;

/**
 * Body of the "More" {@link MobileSheet}: a tappable list of the Tier-2
 * surfaces. Tapping an entry swaps this body in place — one surface visible at
 * a time, with a back button returning to the menu. The host sheet stays open
 * throughout, so only one sheet is ever open.
 *
 * - **Discussions** → {@link RightPanelContent} in `discussions` mode
 *   (`DocumentDiscussionsContent`).
 * - **Notes** → {@link RightPanelContent} in `feed` mode with a fixed
 *   notes-only content filter — the unified feed is the canonical notes
 *   surface and there is no standalone `notes` view mode.
 * - **Document info & versions** → a minimal read-only view built from the
 *   `metadata` prop (title, file type, creator, created). No reusable in-sheet
 *   metadata component exists; `DocumentMetadataGrid` is a corpus-level editor.
 */
export const MobileMoreSheet: React.FC<MobileMoreSheetProps> = ({
  metadata,
  setSidebarViewMode,
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
  readOnly,
  documentId,
  corpusId,
  setActiveLayer,
  setSelectedNote,
}) => {
  const [view, setView] = useState<MoreView>("menu");

  // Shared props for the embedded RightPanelContent surfaces.
  const panelProps = {
    showRightPanel: true,
    setSidebarViewMode,
    feedSortBy,
    setFeedSortBy,
    searchText,
    selectedAnalysis,
    selectedExtract,
    dataCells,
    columns,
    notes,
    loading,
    readOnly,
    documentId,
    corpusId,
    setActiveLayer,
    setSelectedNote,
  } as const;

  if (view === "menu") {
    return (
      <Menu data-testid="mobile-more-menu">
        <Row
          data-testid="mobile-more-discussions"
          onClick={() => {
            setSidebarViewMode("discussions");
            setView("discussions");
          }}
        >
          <MessagesSquare size={20} color={ICON_COLOR} />
          <RowText>
            <RowLabel>Discussions</RowLabel>
            <RowDescription>
              Threaded conversations on this document
            </RowDescription>
          </RowText>
          <ChevronRight size={18} color={OS_LEGAL_COLORS.textSecondary} />
        </Row>

        <Row data-testid="mobile-more-notes" onClick={() => setView("notes")}>
          <StickyNote size={20} color={ICON_COLOR} />
          <RowText>
            <RowLabel>Notes</RowLabel>
            <RowDescription>Notes attached to this document</RowDescription>
          </RowText>
          <ChevronRight size={18} color={OS_LEGAL_COLORS.textSecondary} />
        </Row>

        <Row data-testid="mobile-more-info" onClick={() => setView("info")}>
          <Info size={20} color={ICON_COLOR} />
          <RowText>
            <RowLabel>Document info &amp; versions</RowLabel>
            <RowDescription>Metadata and version details</RowDescription>
          </RowText>
          <ChevronRight size={18} color={OS_LEGAL_COLORS.textSecondary} />
        </Row>
      </Menu>
    );
  }

  const backToMenu = (
    <SubHeader>
      <BackButton
        data-testid="mobile-more-back"
        onClick={() => setView("menu")}
      >
        <ArrowLeft size={14} />
        More
      </BackButton>
    </SubHeader>
  );

  if (view === "discussions") {
    return (
      <Container data-testid="mobile-more-discussions-surface">
        {backToMenu}
        <SurfaceFill>
          <RightPanelContent
            {...panelProps}
            sidebarViewMode="discussions"
            feedFilters={feedFilters}
            setFeedFilters={setFeedFilters}
          />
        </SurfaceFill>
      </Container>
    );
  }

  if (view === "notes") {
    return (
      <Container data-testid="mobile-more-notes-surface">
        {backToMenu}
        <SurfaceFill>
          {/* Fixed notes-only filter: the unified feed is the canonical notes
              surface, and we must not clobber the live Annotations filters. */}
          <RightPanelContent
            {...panelProps}
            sidebarViewMode="feed"
            feedFilters={NOTES_ONLY_FILTER}
            setFeedFilters={() => {}}
          />
        </SurfaceFill>
      </Container>
    );
  }

  // view === "info" — read-only metadata view built from the `metadata` prop.
  const creatorDisplay = getCreatorDisplay(metadata.creator);
  return (
    <Container data-testid="mobile-more-info-surface">
      {backToMenu}
      <InfoList>
        <InfoRow>
          <FileText size={18} color={ICON_COLOR} />
          <InfoText>
            <InfoLabel>Title</InfoLabel>
            <InfoValue>{metadata.title || "Untitled Document"}</InfoValue>
          </InfoText>
        </InfoRow>
        <InfoRow>
          <FileType size={18} color={ICON_COLOR} />
          <InfoText>
            <InfoLabel>File type</InfoLabel>
            <InfoValue>{metadata.fileType || "Unknown"}</InfoValue>
          </InfoText>
        </InfoRow>
        <InfoRow>
          <User size={18} color={ICON_COLOR} />
          <InfoText>
            <InfoLabel>Creator</InfoLabel>
            <InfoValue>{creatorDisplay || "Unknown"}</InfoValue>
          </InfoText>
        </InfoRow>
        <InfoRow>
          <Calendar size={18} color={ICON_COLOR} />
          <InfoText>
            <InfoLabel>Created</InfoLabel>
            <InfoValue>
              {metadata.created ? formatShortDate(metadata.created) : "Unknown"}
            </InfoValue>
          </InfoText>
        </InfoRow>
      </InfoList>
    </Container>
  );
};

export default MobileMoreSheet;
