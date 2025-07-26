import React, { useState, useEffect, useRef } from "react";
import {
  BookOpen,
  GitBranch,
  ChevronLeft,
  ChevronRight,
  User as UserIcon,
  Clock,
  ArrowLeft,
  AlertCircle,
  EditIcon,
} from "lucide-react";
import { Button, Icon } from "semantic-ui-react";
import { format } from "date-fns";

import {
  KnowledgeLayerContainer,
  VersionHistorySidebar,
  CollapseSidebarButton,
  VersionHistoryHeader,
  VersionList,
  VersionItem,
  KnowledgeContent,
  KnowledgeHeader,
  KnowledgeBody,
  EditModeToolbar,
  MobileTabBar,
  MobileTab,
  MobileBackButton,
  LoadingPlaceholders,
  MarkdownEditor,
} from "../StyledContainers";
import { useSummaryVersions } from "../floating_summary_preview/hooks/useSummaryVersions";
import { SafeMarkdown } from "../../markdown/SafeMarkdown";
import { toast } from "react-toastify";

interface Props {
  documentId: string;
  corpusId: string;
  metadata: any;
  parentLoading: boolean; // loading flag from parent GraphQL query
  readOnly?: boolean;
}

const UnifiedKnowledgeLayer: React.FC<Props> = ({
  documentId,
  corpusId,
  metadata,
  parentLoading,
  readOnly = false,
}) => {
  /** local component state **/
  const [versionSidebarCollapsed, setVersionSidebarCollapsed] = useState(false);
  const [mobileView, setMobileView] = useState<"versions" | "content">(
    "content"
  );
  const [isEditingSummary, setIsEditingSummary] = useState(false);
  const [editedSummaryContent, setEditedSummaryContent] = useState<string>("");
  const [selectedSummaryVersion, setSelectedSummaryVersion] = useState<
    number | null
  >(null);
  const [selectedSummaryContent, setSelectedSummaryContent] = useState<
    string | null
  >(null);
  const editorRef = useRef<HTMLTextAreaElement>(null);

  /** fetch versions **/
  const {
    versions: summaryVersions,
    currentVersion: currentSummaryVersion,
    currentContent: currentSummaryContentFromHook,
    loading: summaryLoading,
    updateSummary,
    refetch: refetchSummary,
  } = useSummaryVersions(documentId, corpusId);

  // handle window resize -> reset to content panel on desktop
  useEffect(() => {
    const handleResize = () => {
      if (window.innerWidth > 768 && mobileView === "versions") {
        setMobileView("content");
      }
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, [mobileView]);

  /** derived **/
  const displayContent =
    selectedSummaryContent ??
    currentSummaryContentFromHook ??
    (summaryVersions && summaryVersions.length > 0
      ? summaryVersions[0].snapshot
      : undefined) ??
    "";

  const combinedLoading = parentLoading || summaryLoading;
  const isViewingCurrent =
    !selectedSummaryVersion || selectedSummaryVersion === currentSummaryVersion;

  /** handlers **/
  const handleEdit = () => {
    setIsEditingSummary(true);
    setEditedSummaryContent(displayContent);
  };

  const handleCancelEdit = () => {
    setIsEditingSummary(false);
    setEditedSummaryContent("");
  };

  const handleSaveEdit = async () => {
    if (!editedSummaryContent.trim()) {
      toast.error("Summary content cannot be empty");
      return;
    }
    try {
      await updateSummary(editedSummaryContent);
      setIsEditingSummary(false);
      setEditedSummaryContent("");
      toast.success("Summary saved successfully!");
      setSelectedSummaryVersion(null);
      setSelectedSummaryContent(null);
      await refetchSummary();
    } catch {
      toast.error("Failed to save summary");
    }
  };

  const sortedVersions = summaryVersions
    ? [...summaryVersions].sort((a, b) => b.version - a.version)
    : [];

  return (
    <KnowledgeLayerContainer>
      {/* mobile tab bar */}
      <MobileTabBar>
        <MobileTab
          $active={mobileView === "versions"}
          onClick={() => setMobileView("versions")}
        >
          <GitBranch size={16} /> Versions
        </MobileTab>
        <MobileTab
          $active={mobileView === "content"}
          onClick={() => setMobileView("content")}
        >
          <BookOpen size={16} /> Summary
        </MobileTab>
      </MobileTabBar>

      {/* sidebar */}
      <VersionHistorySidebar
        collapsed={versionSidebarCollapsed}
        $mobileVisible={mobileView === "versions"}
      >
        <CollapseSidebarButton
          onClick={() => setVersionSidebarCollapsed(!versionSidebarCollapsed)}
        >
          {versionSidebarCollapsed ? <ChevronRight /> : <ChevronLeft />}
        </CollapseSidebarButton>

        {!versionSidebarCollapsed && (
          <>
            <VersionHistoryHeader>
              <MobileBackButton onClick={() => setMobileView("content")}>
                <ArrowLeft size={16} /> Back to Summary
              </MobileBackButton>
              <h3>
                <GitBranch size={18} /> Version History
              </h3>
              <div className="version-count">
                {sortedVersions.length} version
                {sortedVersions.length !== 1 ? "s" : ""} total
              </div>
            </VersionHistoryHeader>

            <VersionList>
              {sortedVersions.map((version) => {
                const isCurrent = version.version === currentSummaryVersion;
                const isActive = selectedSummaryVersion === version.version;
                return (
                  <VersionItem
                    key={version.id}
                    $isActive={isActive}
                    $isCurrent={isCurrent}
                    onClick={() => {
                      setSelectedSummaryVersion(version.version);
                      setSelectedSummaryContent(version.snapshot || "");
                      if (window.innerWidth <= 768) {
                        setMobileView("content");
                      }
                    }}
                  >
                    <div className="version-header">
                      <div className="version-number">
                        Version {version.version}
                      </div>
                      {isCurrent && (
                        <span className="version-badge">Current</span>
                      )}
                    </div>
                    <div className="version-meta">
                      <div className="meta-row">
                        <UserIcon /> {version.author?.email || "Unknown"}
                      </div>
                      <div className="meta-row">
                        <Clock />
                        {format(
                          new Date(version.created),
                          "MMM d, yyyy 'at' h:mm a"
                        )}
                      </div>
                    </div>
                  </VersionItem>
                );
              })}
            </VersionList>
          </>
        )}
      </VersionHistorySidebar>

      {/* main content */}
      <KnowledgeContent $mobileVisible={mobileView === "content"}>
        <KnowledgeHeader>
          <div className="header-content">
            <h2>
              <BookOpen /> {metadata.title || "Untitled Document"} - Summary
            </h2>
            <div className="header-actions">
              {!isEditingSummary && isViewingCurrent && !readOnly && (
                <Button primary onClick={handleEdit}>
                  <Icon name="edit" /> Edit Summary
                </Button>
              )}
              {isEditingSummary && (
                <>
                  <Button positive onClick={handleSaveEdit}>
                    <Icon name="save" /> Save as New Version
                  </Button>
                  <Button onClick={handleCancelEdit}>
                    <Icon name="cancel" /> Cancel
                  </Button>
                </>
              )}
            </div>
          </div>
          <div className="version-info">
            <div className="info-item">
              <GitBranch /> Viewing: Version{" "}
              {selectedSummaryVersion || currentSummaryVersion || 1}
            </div>
            {!isViewingCurrent && (
              <div className="info-item" style={{ color: "#d97706" }}>
                <AlertCircle /> Viewing historical version - changes will create
                a new version
              </div>
            )}
          </div>
        </KnowledgeHeader>

        <KnowledgeBody $isEditing={isEditingSummary}>
          {isEditingSummary && (
            <EditModeToolbar>
              <div className="toolbar-left">
                <div className="edit-indicator">
                  <EditIcon /> Editing Mode
                </div>
              </div>
              <div className="toolbar-actions">
                <span style={{ fontSize: "0.875rem", color: "#64748b" }}>
                  {editedSummaryContent.length} characters
                </span>
              </div>
            </EditModeToolbar>
          )}

          {combinedLoading ? (
            <LoadingPlaceholders type="summary" />
          ) : isEditingSummary ? (
            <MarkdownEditor
              ref={editorRef}
              defaultValue={editedSummaryContent}
              onChange={(e) => {
                const val = e.target.value;
                if (editorRef.current) {
                  const elem: any = editorRef.current;
                  if (elem.__debounceTimer) clearTimeout(elem.__debounceTimer);
                  elem.__debounceTimer = setTimeout(() => {
                    setEditedSummaryContent(val);
                    delete elem.__debounceTimer;
                  }, 150);
                }
              }}
              placeholder="Enter your summary content in Markdown format..."
              autoFocus
            />
          ) : displayContent ? (
            <div className="prose max-w-none">
              <SafeMarkdown>{displayContent}</SafeMarkdown>
            </div>
          ) : (
            <LoadingPlaceholders type="summary" />
          )}
        </KnowledgeBody>
      </KnowledgeContent>
    </KnowledgeLayerContainer>
  );
};

export default UnifiedKnowledgeLayer;
