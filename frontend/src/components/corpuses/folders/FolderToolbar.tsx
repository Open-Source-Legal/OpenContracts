import React, { useState, useCallback, useEffect, useRef } from "react";
import { useAtom, useAtomValue } from "jotai";
import styled from "styled-components";
import {
  FolderPlus,
  Upload,
  List,
  LayoutGrid,
  Table2,
  PanelLeftOpen,
  ChevronLeft,
  ChevronUp,
  MoreVertical,
  Link2,
  ChevronDown,
  FileArchive,
  CheckSquare,
  Square,
  X,
  Trash2,
} from "lucide-react";
import { FolderBreadcrumb } from "./FolderBreadcrumb";
import {
  sidebarCollapsedAtom,
  canCreateFoldersAtom,
  folderBreadcrumbAtom,
} from "../../../atoms/folderAtoms";
import {
  TABLET_BREAKPOINT,
  DESKTOP_BREAKPOINT,
} from "../../../assets/configurations/constants";
import {
  OS_LEGAL_COLORS,
  OS_LEGAL_SPACING,
  OS_LEGAL_SHADOWS,
} from "../../../assets/configurations/osLegalStyles";
import { Button } from "@os-legal/ui";
import { FolderViewMode } from "../../../types/ui";

// Re-export for backward compatibility with existing imports
export type ViewMode = FolderViewMode;

/**
 * FolderToolbar - Toolbar component for folder-based document browsing
 *
 * Features:
 * - Breadcrumb navigation
 * - Back/up navigation buttons
 * - New folder and upload actions
 * - View mode toggles (list/card/table)
 * - Sidebar toggle
 * - Mobile kebab menu
 */

interface FolderToolbarProps {
  showSidebar: boolean;
  selectedFolderId: string | null;
  canGoBack: boolean;
  viewMode: ViewMode;
  onViewModeChange?: (mode: ViewMode) => void;
  onFolderSelect: (folderId: string | null) => void;
  onGoBack: () => void;
  onGoUp: () => void;
  onNewFolder: () => void;
  onUpload: () => void;
  /** Callback for bulk import action */
  onBulkImport?: () => void;
  /** Number of currently selected documents (for multi-select actions) */
  selectedDocumentCount?: number;
  /** Total number of documents in current view (for Select All) */
  totalDocumentCount?: number;
  /** Callback when user clicks Link Documents button */
  onLinkDocuments?: () => void;
  /** Callback when user clicks Select All */
  onSelectAll?: () => void;
  /** Callback when user clicks Clear Selection */
  onClearSelection?: () => void;
  /** Callback when user clicks Remove from Corpus (bulk action) */
  onRemoveFromCorpus?: () => void;
  /**
   * Callback when user clicks "Empty Corpus" (move ALL documents to trash and
   * remove ALL folders). Omitted when the user lacks DELETE permission, which
   * hides the button entirely.
   */
  onEmptyCorpus?: () => void;
  /** Whether all documents in the current view are selected */
  allSelected?: boolean;
  /** Whether documents are currently loading (disables Select All) */
  isLoading?: boolean;
}

// ===============================================
// STYLED COMPONENTS
// ===============================================

const ToolbarContainer = styled.div`
  position: relative;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 20px;
  border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
  background: ${OS_LEGAL_COLORS.surface};
  flex-shrink: 0;

  @media (max-width: ${TABLET_BREAKPOINT}px) {
    padding: 10px 12px;
    gap: 8px;
  }
`;

const ToolbarBreadcrumb = styled.div`
  flex: 1;
  display: flex;
  align-items: center;
  min-width: 0;

  @media (max-width: ${TABLET_BREAKPOINT}px) {
    display: none;
  }
`;

// Mobile-only folder title - shows current folder name when breadcrumb is hidden
const MobileFolderTitle = styled.div`
  display: none;
  flex: 1;
  font-size: 14px;
  font-weight: 500;
  color: ${OS_LEGAL_COLORS.textPrimary};
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;

  @media (max-width: ${TABLET_BREAKPOINT}px) {
    display: block;
  }
`;

const ToolbarActions = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
`;

const NavButton = styled.button`
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  background: ${OS_LEGAL_COLORS.surface};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: ${OS_LEGAL_SPACING.borderRadiusButton};
  color: ${OS_LEGAL_COLORS.textSecondary};
  cursor: pointer;
  transition: all 0.15s ease;

  &:hover:not(:disabled) {
    background: ${OS_LEGAL_COLORS.surfaceHover};
    border-color: ${OS_LEGAL_COLORS.borderHover};
    color: ${OS_LEGAL_COLORS.textPrimary};
  }

  &:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }

  svg {
    width: 16px;
    height: 16px;
  }
`;

const ActionButton = styled.button`
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  background: ${OS_LEGAL_COLORS.surface};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: ${OS_LEGAL_SPACING.borderRadiusButton};
  font-size: 13px;
  font-weight: 500;
  color: ${OS_LEGAL_COLORS.textPrimary};
  cursor: pointer;
  transition: all 0.15s ease;

  &:hover {
    background: ${OS_LEGAL_COLORS.surfaceHover};
    border-color: ${OS_LEGAL_COLORS.borderHover};
  }

  svg {
    width: 16px;
    height: 16px;
    color: ${OS_LEGAL_COLORS.folderIcon};
  }

  @media (max-width: ${TABLET_BREAKPOINT}px) {
    padding: 8px;

    span {
      display: none;
    }
  }
`;

const PrimaryButton = styled.button`
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  background: ${OS_LEGAL_COLORS.accent};
  border: 1px solid ${OS_LEGAL_COLORS.accent};
  border-radius: ${OS_LEGAL_SPACING.borderRadiusButton};
  font-size: 13px;
  font-weight: 500;
  color: white;
  cursor: pointer;
  transition: all 0.15s ease;

  &:hover {
    background: ${OS_LEGAL_COLORS.accentHover};
    border-color: ${OS_LEGAL_COLORS.accentHover};
  }

  svg {
    width: 16px;
    height: 16px;
  }

  @media (max-width: ${TABLET_BREAKPOINT}px) {
    padding: 8px 12px;

    span {
      display: none;
    }
  }
`;

const ViewToggleGroup = styled.div`
  display: flex;
  align-items: center;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: ${OS_LEGAL_SPACING.borderRadiusButton};
  overflow: hidden;
`;

const ViewToggleButton = styled.button<{ $active: boolean }>`
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  background: ${(props) =>
    props.$active ? OS_LEGAL_COLORS.accent : OS_LEGAL_COLORS.surface};
  border: none;
  border-right: 1px solid ${OS_LEGAL_COLORS.border};
  color: ${(props) =>
    props.$active ? "white" : OS_LEGAL_COLORS.textSecondary};
  cursor: pointer;
  transition: all 0.15s ease;

  &:last-child {
    border-right: none;
  }

  &:hover:not(:disabled) {
    background: ${(props) =>
      props.$active
        ? OS_LEGAL_COLORS.accentHover
        : OS_LEGAL_COLORS.surfaceHover};
    color: ${(props) =>
      props.$active ? "white" : OS_LEGAL_COLORS.textPrimary};
  }

  svg {
    width: 16px;
    height: 16px;
  }
`;

// Selection controls group - shown when documents exist
const SelectionGroup = styled.div`
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  background: ${OS_LEGAL_COLORS.surfaceHover};
  border-radius: ${OS_LEGAL_SPACING.borderRadiusButton};
  border: 1px solid ${OS_LEGAL_COLORS.border};

  @media (max-width: ${TABLET_BREAKPOINT}px) {
    display: none;
  }
`;

const SelectAllButton = styled.button<{ $allSelected?: boolean }>`
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  background: ${(props) =>
    props.$allSelected ? OS_LEGAL_COLORS.accent : "transparent"};
  border: none;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
  color: ${(props) =>
    props.$allSelected ? "white" : OS_LEGAL_COLORS.textSecondary};
  cursor: pointer;
  transition: all 0.15s ease;

  &:hover:not(:disabled) {
    background: ${(props) =>
      props.$allSelected
        ? OS_LEGAL_COLORS.accentHover
        : OS_LEGAL_COLORS.border};
    color: ${(props) =>
      props.$allSelected ? "white" : OS_LEGAL_COLORS.textPrimary};
  }

  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  svg {
    width: 14px;
    height: 14px;
  }
`;

const SelectionCount = styled.span`
  font-size: 12px;
  font-weight: 500;
  color: ${OS_LEGAL_COLORS.textSecondary};
  padding: 0 4px;
`;

const SelectionDivider = styled.div`
  width: 1px;
  height: 16px;
  background: ${OS_LEGAL_COLORS.border};
`;

const ClearSelectionButton = styled.button`
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 4px;
  background: transparent;
  border: none;
  border-radius: 4px;
  color: ${OS_LEGAL_COLORS.textMuted};
  cursor: pointer;
  transition: all 0.15s ease;

  &:hover {
    background: ${OS_LEGAL_COLORS.border};
    color: ${OS_LEGAL_COLORS.textPrimary};
  }

  svg {
    width: 14px;
    height: 14px;
  }
`;

const SidebarToggleButton = styled.button`
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  background: ${OS_LEGAL_COLORS.surface};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: ${OS_LEGAL_SPACING.borderRadiusButton};
  color: ${OS_LEGAL_COLORS.textSecondary};
  cursor: pointer;
  transition: all 0.15s ease;
  margin-right: 8px;

  &:hover {
    background: ${OS_LEGAL_COLORS.surfaceHover};
    border-color: ${OS_LEGAL_COLORS.borderHover};
    color: ${OS_LEGAL_COLORS.textPrimary};
  }

  svg {
    width: 16px;
    height: 16px;
  }

  @media (max-width: ${TABLET_BREAKPOINT}px) {
    display: none;
  }
`;

const MobileKebabButton = styled.button`
  display: none;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  background: transparent;
  border: none;
  border-radius: ${OS_LEGAL_SPACING.borderRadiusButton};
  color: ${OS_LEGAL_COLORS.textSecondary};
  cursor: pointer;
  transition: all 0.15s ease;
  margin-left: auto;

  &:hover {
    background: ${OS_LEGAL_COLORS.surfaceHover};
    color: ${OS_LEGAL_COLORS.textPrimary};
  }

  svg {
    width: 20px;
    height: 20px;
  }

  @media (max-width: ${TABLET_BREAKPOINT}px) {
    display: flex;
  }
`;

const MobileMenuOverlay = styled.div<{ $visible: boolean }>`
  display: ${(props) => (props.$visible ? "block" : "none")};
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 99;

  @media (min-width: ${DESKTOP_BREAKPOINT}px) {
    display: none;
  }
`;

const MobileMenu = styled.div<{ $visible: boolean }>`
  display: ${(props) => (props.$visible ? "block" : "none")};
  position: absolute;
  top: 100%;
  right: 8px;
  background: ${OS_LEGAL_COLORS.surface};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: ${OS_LEGAL_SPACING.borderRadiusButton};
  box-shadow: ${OS_LEGAL_SHADOWS.cardHover};
  min-width: 180px;
  z-index: 100;
  overflow: hidden;

  @media (min-width: ${DESKTOP_BREAKPOINT}px) {
    display: none;
  }
`;

const MobileMenuItem = styled.button`
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 12px 16px;
  background: none;
  border: none;
  font-size: 14px;
  color: ${OS_LEGAL_COLORS.textPrimary};
  cursor: pointer;
  text-align: left;
  transition: background-color 0.15s ease;

  &:hover {
    background: ${OS_LEGAL_COLORS.surfaceHover};
  }

  &:active {
    background: ${OS_LEGAL_COLORS.border};
  }

  svg {
    width: 18px;
    height: 18px;
    color: ${OS_LEGAL_COLORS.textSecondary};
  }

  &:not(:last-child) {
    border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
  }
`;

// Upload button with dropdown - unified split button design
// NOTE: overflow is NOT hidden to allow dropdown menu to be visible
const UploadButtonGroup = styled.div`
  position: relative;
  display: inline-flex;
  align-items: stretch;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
`;

const UploadMainButton = styled.button`
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  background: ${OS_LEGAL_COLORS.accent};
  border: none;
  border-radius: ${OS_LEGAL_SPACING.borderRadiusButton} 0 0
    ${OS_LEGAL_SPACING.borderRadiusButton};
  font-size: 13px;
  font-weight: 500;
  color: white;
  cursor: pointer;
  transition: background 0.15s ease;

  &:hover {
    background: ${OS_LEGAL_COLORS.accentHover};
  }

  svg {
    width: 16px;
    height: 16px;
  }

  @media (max-width: ${TABLET_BREAKPOINT}px) {
    padding: 8px 10px;

    span {
      display: none;
    }
  }
`;

const UploadDropdownButton = styled.button`
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 8px 8px;
  background: ${OS_LEGAL_COLORS.accent};
  border: none;
  border-left: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 0 ${OS_LEGAL_SPACING.borderRadiusButton}
    ${OS_LEGAL_SPACING.borderRadiusButton} 0;
  color: white;
  cursor: pointer;
  transition: background 0.15s ease;

  &:hover {
    background: ${OS_LEGAL_COLORS.accentHover};
  }

  svg {
    width: 14px;
    height: 14px;
  }
`;

const UploadDropdownMenu = styled.div<{ $visible: boolean }>`
  display: ${(props) => (props.$visible ? "block" : "none")};
  position: absolute;
  top: 100%;
  right: 0;
  margin-top: 4px;
  background: ${OS_LEGAL_COLORS.surface};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: ${OS_LEGAL_SPACING.borderRadiusButton};
  box-shadow: ${OS_LEGAL_SHADOWS.cardHover};
  min-width: 180px;
  z-index: 100;
  overflow: hidden;
`;

const UploadDropdownItem = styled.button`
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 10px 14px;
  background: none;
  border: none;
  font-size: 13px;
  color: ${OS_LEGAL_COLORS.textPrimary};
  cursor: pointer;
  text-align: left;
  transition: background-color 0.15s ease;

  &:hover {
    background: ${OS_LEGAL_COLORS.surfaceHover};
  }

  svg {
    width: 16px;
    height: 16px;
    color: ${OS_LEGAL_COLORS.accent};
  }

  &:not(:last-child) {
    border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
  }
`;

const UploadDropdownOverlay = styled.div<{ $visible: boolean }>`
  display: ${(props) => (props.$visible ? "block" : "none")};
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 99;
`;

// ===============================================
// COMPONENT
// ===============================================

export const FolderToolbar: React.FC<FolderToolbarProps> = ({
  showSidebar,
  selectedFolderId,
  canGoBack,
  viewMode,
  onViewModeChange,
  onFolderSelect,
  onGoBack,
  onGoUp,
  onNewFolder,
  onUpload,
  onBulkImport,
  selectedDocumentCount = 0,
  totalDocumentCount = 0,
  onLinkDocuments,
  onSelectAll,
  onClearSelection,
  onRemoveFromCorpus,
  onEmptyCorpus,
  allSelected = false,
  isLoading = false,
}) => {
  const [sidebarCollapsed, setSidebarCollapsed] = useAtom(sidebarCollapsedAtom);
  const canCreateFolders = useAtomValue(canCreateFoldersAtom);
  const breadcrumbPath = useAtomValue(folderBreadcrumbAtom);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [uploadDropdownOpen, setUploadDropdownOpen] = useState(false);
  const uploadDropdownRef = useRef<HTMLDivElement>(null);

  // Get current folder name for mobile display
  const currentFolderName = selectedFolderId
    ? breadcrumbPath.length > 0
      ? breadcrumbPath[breadcrumbPath.length - 1].name
      : "Loading..."
    : "Documents";

  // Memoized view mode change handler to prevent unnecessary re-renders
  const handleViewModeChange = useCallback(
    (mode: ViewMode) => {
      onViewModeChange?.(mode);
    },
    [onViewModeChange]
  );

  // Close mobile menu handler
  const closeMobileMenu = useCallback(() => {
    setMobileMenuOpen(false);
  }, []);

  // Close upload dropdown handler
  const closeUploadDropdown = useCallback(() => {
    setUploadDropdownOpen(false);
  }, []);

  // Toggle upload dropdown
  const toggleUploadDropdown = useCallback(() => {
    setUploadDropdownOpen((prev) => !prev);
  }, []);

  // Handle upload document click
  const handleUploadDocuments = useCallback(() => {
    closeUploadDropdown();
    onUpload();
  }, [onUpload, closeUploadDropdown]);

  // Handle bulk import click
  const handleBulkImport = useCallback(() => {
    closeUploadDropdown();
    onBulkImport?.();
  }, [onBulkImport, closeUploadDropdown]);

  // Escape key handler for accessibility - closes mobile menu and upload dropdown
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (mobileMenuOpen) {
          closeMobileMenu();
        }
        if (uploadDropdownOpen) {
          closeUploadDropdown();
        }
      }
    };

    if (mobileMenuOpen || uploadDropdownOpen) {
      document.addEventListener("keydown", handleKeyDown);
      return () => document.removeEventListener("keydown", handleKeyDown);
    }
  }, [
    mobileMenuOpen,
    uploadDropdownOpen,
    closeMobileMenu,
    closeUploadDropdown,
  ]);

  return (
    <ToolbarContainer>
      {/* Desktop sidebar toggle */}
      {showSidebar && (
        <SidebarToggleButton
          onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
          aria-label={sidebarCollapsed ? "Show folders" : "Hide folders"}
          title={sidebarCollapsed ? "Show folders" : "Hide folders"}
        >
          <PanelLeftOpen />
        </SidebarToggleButton>
      )}

      <ToolbarBreadcrumb>
        <FolderBreadcrumb onFolderSelect={onFolderSelect} />
      </ToolbarBreadcrumb>

      {/* Mobile-only current folder name */}
      <MobileFolderTitle>{currentFolderName}</MobileFolderTitle>

      <ToolbarActions>
        {/* Navigation buttons */}
        <NavButton
          onClick={onGoBack}
          disabled={!canGoBack}
          title="Go back"
          aria-label="Go back"
        >
          <ChevronLeft />
        </NavButton>
        <NavButton
          onClick={onGoUp}
          disabled={selectedFolderId === null}
          title="Go to root"
          aria-label="Go to root"
        >
          <ChevronUp />
        </NavButton>

        {/* Selection controls - shown when documents exist */}
        {totalDocumentCount > 0 && onSelectAll && (
          <SelectionGroup>
            <SelectAllButton
              onClick={onSelectAll}
              $allSelected={allSelected}
              disabled={isLoading}
              title={
                isLoading
                  ? "Loading documents..."
                  : allSelected
                  ? "Deselect all"
                  : "Select all"
              }
              aria-label={
                isLoading
                  ? "Loading documents"
                  : allSelected
                  ? "Deselect all"
                  : "Select all"
              }
            >
              {allSelected ? <CheckSquare /> : <Square />}
              {allSelected ? "All" : "Select All"}
            </SelectAllButton>
            {selectedDocumentCount > 0 && (
              <>
                <SelectionDivider />
                <SelectionCount>
                  {selectedDocumentCount} of {totalDocumentCount}
                </SelectionCount>
                {onClearSelection && (
                  <ClearSelectionButton
                    onClick={onClearSelection}
                    title="Clear selection"
                    aria-label="Clear selection"
                  >
                    <X />
                  </ClearSelectionButton>
                )}
              </>
            )}
          </SelectionGroup>
        )}

        {/* Remove from Corpus button - visible when 1+ documents selected */}
        {selectedDocumentCount >= 1 && onRemoveFromCorpus && (
          <Button
            variant="danger"
            size="sm"
            leftIcon={<Trash2 size={16} />}
            onClick={onRemoveFromCorpus}
            title={`Remove ${selectedDocumentCount} document${
              selectedDocumentCount !== 1 ? "s" : ""
            } from corpus`}
          >
            Remove ({selectedDocumentCount})
          </Button>
        )}

        {/* Link Documents button - visible when 1+ documents selected */}
        {selectedDocumentCount >= 1 && onLinkDocuments && (
          <ActionButton
            onClick={onLinkDocuments}
            title={`Link ${selectedDocumentCount} selected document${
              selectedDocumentCount !== 1 ? "s" : ""
            }`}
          >
            <Link2 />
            <span>Link Document{selectedDocumentCount !== 1 ? "s" : ""}</span>
          </ActionButton>
        )}

        {/* Empty Corpus button - whole-corpus destructive action. Only shown
            when the user can delete (onEmptyCorpus provided) and there is
            something to empty. A confirmation modal guards the action. */}
        {onEmptyCorpus && totalDocumentCount > 0 && (
          <Button
            variant="secondary"
            size="sm"
            leftIcon={<Trash2 size={16} />}
            onClick={onEmptyCorpus}
            title="Move all documents to trash and remove all folders"
            style={{
              color: OS_LEGAL_COLORS.danger,
              borderColor: OS_LEGAL_COLORS.danger,
            }}
          >
            Empty Corpus
          </Button>
        )}

        {/* New Folder button */}
        {canCreateFolders && (
          <ActionButton onClick={onNewFolder} title="Create new folder">
            <FolderPlus />
            <span>New Folder</span>
          </ActionButton>
        )}

        {/* Upload button with dropdown */}
        <UploadButtonGroup ref={uploadDropdownRef}>
          <UploadMainButton onClick={onUpload} title="Upload documents">
            <Upload />
            <span>Upload</span>
          </UploadMainButton>
          <UploadDropdownButton
            onClick={toggleUploadDropdown}
            title="More upload options"
            aria-label="More upload options"
            aria-haspopup="true"
            aria-expanded={uploadDropdownOpen}
          >
            <ChevronDown />
          </UploadDropdownButton>

          {/* Upload dropdown overlay - click to close */}
          <UploadDropdownOverlay
            $visible={uploadDropdownOpen}
            onClick={closeUploadDropdown}
            role="presentation"
            aria-hidden="true"
          />

          {/* Upload dropdown menu */}
          <UploadDropdownMenu
            $visible={uploadDropdownOpen}
            role="menu"
            aria-label="Upload options menu"
          >
            <UploadDropdownItem role="menuitem" onClick={handleUploadDocuments}>
              <Upload />
              Upload Documents
            </UploadDropdownItem>
            {onBulkImport && (
              <UploadDropdownItem role="menuitem" onClick={handleBulkImport}>
                <FileArchive />
                Bulk Import (ZIP)
              </UploadDropdownItem>
            )}
          </UploadDropdownMenu>
        </UploadButtonGroup>

        {/* View toggle buttons */}
        {onViewModeChange && (
          <ViewToggleGroup>
            <ViewToggleButton
              $active={viewMode === "modern-list"}
              onClick={() => handleViewModeChange("modern-list")}
              title="List view"
              aria-label="List view"
              data-testid="list-view-button"
            >
              <List />
            </ViewToggleButton>
            <ViewToggleButton
              $active={viewMode === "modern-card"}
              onClick={() => handleViewModeChange("modern-card")}
              title="Card view"
              aria-label="Card view"
              data-testid="card-view-button"
            >
              <LayoutGrid />
            </ViewToggleButton>
            <ViewToggleButton
              $active={viewMode === "grid"}
              onClick={() => handleViewModeChange("grid")}
              title="Table view"
              aria-label="Table view"
              data-testid="grid-view-button"
            >
              <Table2 />
            </ViewToggleButton>
          </ViewToggleGroup>
        )}
      </ToolbarActions>

      {/* Mobile kebab menu */}
      {showSidebar && (
        <MobileKebabButton
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          aria-label="More options"
          title="More options"
        >
          <MoreVertical />
        </MobileKebabButton>
      )}

      {/* Mobile menu overlay - click to close */}
      <MobileMenuOverlay
        $visible={mobileMenuOpen}
        onClick={closeMobileMenu}
        role="presentation"
        aria-hidden="true"
      />

      {/* Mobile dropdown menu */}
      <MobileMenu
        $visible={mobileMenuOpen}
        role="menu"
        aria-label="Toolbar actions menu"
      >
        <MobileMenuItem
          role="menuitem"
          onClick={() => {
            setSidebarCollapsed(false);
            closeMobileMenu();
          }}
        >
          <PanelLeftOpen />
          Show Folders
        </MobileMenuItem>
        {/* Selection controls for mobile */}
        {totalDocumentCount > 0 && onSelectAll && (
          <MobileMenuItem
            role="menuitem"
            disabled={isLoading}
            onClick={() => {
              if (!isLoading) {
                onSelectAll();
                closeMobileMenu();
              }
            }}
            style={isLoading ? { opacity: 0.5, cursor: "not-allowed" } : {}}
          >
            {allSelected ? <CheckSquare /> : <Square />}
            {isLoading
              ? "Loading..."
              : `${
                  allSelected ? "Deselect All" : "Select All"
                } (${totalDocumentCount})`}
          </MobileMenuItem>
        )}
        {selectedDocumentCount > 0 && onClearSelection && (
          <MobileMenuItem
            role="menuitem"
            onClick={() => {
              onClearSelection();
              closeMobileMenu();
            }}
          >
            <X />
            Clear Selection ({selectedDocumentCount})
          </MobileMenuItem>
        )}
        {selectedDocumentCount >= 1 && onRemoveFromCorpus && (
          <MobileMenuItem
            role="menuitem"
            onClick={() => {
              onRemoveFromCorpus();
              closeMobileMenu();
            }}
            style={{ color: OS_LEGAL_COLORS.danger }}
          >
            <Trash2 />
            Remove from Corpus ({selectedDocumentCount})
          </MobileMenuItem>
        )}
        {selectedDocumentCount >= 1 && onLinkDocuments && (
          <MobileMenuItem
            role="menuitem"
            onClick={() => {
              onLinkDocuments();
              closeMobileMenu();
            }}
          >
            <Link2 />
            Link Document{selectedDocumentCount !== 1 ? "s" : ""} (
            {selectedDocumentCount})
          </MobileMenuItem>
        )}
        {canCreateFolders && (
          <MobileMenuItem
            role="menuitem"
            onClick={() => {
              onNewFolder();
              closeMobileMenu();
            }}
          >
            <FolderPlus />
            New Folder
          </MobileMenuItem>
        )}
        {onEmptyCorpus && totalDocumentCount > 0 && (
          <MobileMenuItem
            role="menuitem"
            onClick={() => {
              onEmptyCorpus();
              closeMobileMenu();
            }}
            style={{ color: OS_LEGAL_COLORS.danger }}
          >
            <Trash2 />
            Empty Corpus
          </MobileMenuItem>
        )}
        <MobileMenuItem
          role="menuitem"
          onClick={() => {
            onUpload();
            closeMobileMenu();
          }}
        >
          <Upload />
          Upload Documents
        </MobileMenuItem>
        {onBulkImport && (
          <MobileMenuItem
            role="menuitem"
            onClick={() => {
              onBulkImport();
              closeMobileMenu();
            }}
          >
            <FileArchive />
            Bulk Import (ZIP)
          </MobileMenuItem>
        )}
      </MobileMenu>
    </ToolbarContainer>
  );
};
