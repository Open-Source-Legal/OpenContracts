import React, { useEffect } from "react";
import { useSetAtom, useAtomValue, useAtom } from "jotai";
import { useReactiveVar } from "@apollo/client";
import { useLocation, useNavigate } from "react-router-dom";
import styled from "styled-components";
import { Folder, FolderOpen } from "lucide-react";
import { selectedFolderId as selectedFolderIdReactiveVar } from "../../../graphql/cache";
import { FolderTreeSidebar } from "./FolderTreeSidebar";
import { FolderBreadcrumb } from "./FolderBreadcrumb";
import { CreateFolderModal } from "./CreateFolderModal";
import { EditFolderModal } from "./EditFolderModal";
import { MoveFolderModal } from "./MoveFolderModal";
import { DeleteFolderModal } from "./DeleteFolderModal";
import { TrashFolderView } from "./TrashFolderView";
import {
  folderCorpusIdAtom,
  selectedFolderIdAtom,
  sidebarCollapsedAtom,
  openCreateFolderModalAtom,
} from "../../../atoms/folderAtoms";

/**
 * FolderDocumentBrowser - Main container for folder-based document browsing
 *
 * Features:
 * - Three-column layout: Sidebar | Breadcrumb + Content | Modals
 * - Folder tree navigation on left (collapsible)
 * - Breadcrumb navigation at top of content area
 * - Document list in main content area (passed as children)
 * - All folder modals mounted and controlled by atoms
 * - Responsive: sidebar collapses on mobile
 *
 * Props:
 * - corpusId: The corpus to browse
 * - initialFolderId: Optional initial folder selection
 * - onFolderChange: Optional callback when folder selection changes
 * - children: Main content area (typically CorpusDocumentCards)
 * - showSidebar: Whether to show folder sidebar (default: true)
 * - showBreadcrumb: Whether to show breadcrumb (default: true)
 */

interface FolderDocumentBrowserProps {
  corpusId: string;
  initialFolderId?: string | null;
  onFolderChange?: (folderId: string | null) => void;
  children?: React.ReactNode;
  showSidebar?: boolean;
  showBreadcrumb?: boolean;
}

const BrowserContainer = styled.div`
  position: relative;
  display: flex;
  height: 100%;
  overflow: hidden;
  background: #f8fafc;
`;

const Sidebar = styled.aside<{ $visible: boolean; $collapsed: boolean }>`
  width: ${(props) => (props.$collapsed ? "0px" : "320px")};
  min-width: ${(props) => (props.$collapsed ? "0px" : "320px")};
  height: 100%;
  display: ${(props) => (props.$visible ? "flex" : "none")};
  flex-direction: column;
  border-right: ${(props) => (props.$collapsed ? "none" : "1px solid #e2e8f0")};
  background: white;
  overflow: hidden;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

  @media (max-width: 768px) {
    position: absolute;
    left: ${(props) => (props.$visible && !props.$collapsed ? "0" : "-320px")};
    z-index: 100;
    width: 320px;
    min-width: 320px;
    box-shadow: ${(props) =>
      props.$visible && !props.$collapsed
        ? "4px 0 12px rgba(0, 0, 0, 0.1)"
        : "none"};
  }
`;

const MainContent = styled.main<{ $hasSidebar: boolean }>`
  flex: 1;
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  margin-left: ${(props) => (props.$hasSidebar ? "0" : "0")};

  @media (max-width: 768px) {
    margin-left: 0;
  }
`;

const BreadcrumbWrapper = styled.div<{ $visible: boolean }>`
  display: ${(props) => (props.$visible ? "block" : "none")};
  flex-shrink: 0;
`;

const ContentArea = styled.div`
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 0;
  background: white;

  /* Custom scrollbar */
  &::-webkit-scrollbar {
    width: 10px;
  }

  &::-webkit-scrollbar-track {
    background: #f1f5f9;
  }

  &::-webkit-scrollbar-thumb {
    background: #cbd5e1;
    border-radius: 5px;

    &:hover {
      background: #94a3b8;
    }
  }
`;

const ToggleButton = styled.button<{ $collapsed: boolean }>`
  position: absolute;
  left: ${(props) => (props.$collapsed ? "0" : "320px")};
  top: 50%;
  transform: translateY(-50%);
  width: ${(props) => (props.$collapsed ? "40px" : "32px")};
  height: ${(props) => (props.$collapsed ? "80px" : "60px")};
  background: ${(props) => (props.$collapsed ? "#3b82f6" : "#64748b")};
  border: 1px solid ${(props) => (props.$collapsed ? "#3b82f6" : "#64748b")};
  border-left: ${(props) => (props.$collapsed ? "1px solid #3b82f6" : "none")};
  border-radius: ${(props) =>
    props.$collapsed ? "0 8px 8px 0" : "0 8px 8px 0"};
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  z-index: 101;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  color: white;
  box-shadow: ${(props) =>
    props.$collapsed
      ? "4px 0 12px rgba(59, 130, 246, 0.4)"
      : "-4px 0 12px rgba(100, 116, 139, 0.3)"};

  &:hover {
    background: ${(props) => (props.$collapsed ? "#2563eb" : "#475569")};
    border-color: ${(props) => (props.$collapsed ? "#2563eb" : "#475569")};
    color: white;
    box-shadow: ${(props) =>
      props.$collapsed
        ? "4px 0 16px rgba(59, 130, 246, 0.5)"
        : "-4px 0 16px rgba(100, 116, 139, 0.4)"};
    transform: translateY(-50%)
      ${(props) => (props.$collapsed ? "translateX(2px)" : "translateX(-2px)")};
  }

  &:active {
    transform: translateY(-50%) scale(0.95);
  }

  svg {
    width: ${(props) => (props.$collapsed ? "24px" : "18px")};
    height: ${(props) => (props.$collapsed ? "24px" : "18px")};
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  }

  @media (max-width: 768px) {
    display: none;
  }
`;

const ContextMenuOverlay = styled.div`
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 999;
`;

const ContextMenu = styled.div<{ $x: number; $y: number }>`
  position: fixed;
  top: ${(props) => props.$y}px;
  left: ${(props) => props.$x}px;
  background: white;
  border-radius: 8px;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.07), 0 10px 24px rgba(0, 0, 0, 0.15);
  border: 1px solid #e2e8f0;
  padding: 4px;
  min-width: 180px;
  z-index: 1000;
`;

const ContextMenuItem = styled.button`
  display: flex;
  align-items: center;
  width: 100%;
  padding: 8px 12px;
  background: none;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  color: #334155;
  text-align: left;
  transition: all 0.15s ease;

  &:hover {
    background-color: #f1f5f9;
    color: #1e293b;
  }

  &:active {
    background-color: #e2e8f0;
  }
`;

export const FolderDocumentBrowser: React.FC<FolderDocumentBrowserProps> = ({
  corpusId,
  initialFolderId = null,
  onFolderChange,
  children,
  showSidebar = true,
  showBreadcrumb = true,
}) => {
  const setCorpusId = useSetAtom(folderCorpusIdAtom);
  const setSelectedFolderId = useSetAtom(selectedFolderIdAtom);
  const selectedFolderId = useReactiveVar(selectedFolderIdReactiveVar);
  const [sidebarCollapsed, setSidebarCollapsed] = useAtom(sidebarCollapsedAtom);
  const openCreateModal = useSetAtom(openCreateFolderModalAtom);
  const location = useLocation();
  const navigate = useNavigate();

  // Context menu state for right-clicking in content area
  const [contextMenu, setContextMenu] = React.useState<{
    x: number;
    y: number;
  } | null>(null);

  // Initialize corpus context
  useEffect(() => {
    setCorpusId(corpusId);
  }, [corpusId, setCorpusId]);

  // Sync reactive var to Jotai atom for UI components that still use it
  // (This is a temporary bridge until all folder components read from reactive var)
  useEffect(() => {
    setSelectedFolderId(selectedFolderId);
  }, [selectedFolderId, setSelectedFolderId]);

  // Call callback when folder changes
  useEffect(() => {
    if (onFolderChange) {
      onFolderChange(selectedFolderId);
    }
  }, [selectedFolderId, onFolderChange]);

  // Handle folder selection by updating URL (NOT reactive var directly!)
  // CentralRouteManager Phase 2 will detect URL change and set reactive var
  const handleFolderSelect = (folderId: string | null) => {
    const searchParams = new URLSearchParams(location.search);

    if (folderId) {
      searchParams.set("folder", folderId);
    } else {
      searchParams.delete("folder");
    }

    const newSearch = searchParams.toString();
    navigate({ search: newSearch ? `?${newSearch}` : "" }, { replace: true });
  };

  // Handle right-click in content area to create folder in current directory
  const handleContentAreaContextMenu = React.useCallback(
    (e: React.MouseEvent) => {
      // Check if the right-click target is a card or interactive element
      const target = e.target as HTMLElement;
      const isCard =
        target.closest('[role="button"]') ||
        target.closest(".folder-card") ||
        target.closest(".document-card") ||
        target.closest("button") ||
        target.closest("a");

      // Only show context menu if NOT clicking on a card or interactive element
      if (!isCard) {
        e.preventDefault();
        e.stopPropagation();
        setContextMenu({ x: e.clientX, y: e.clientY });
      }
    },
    []
  );

  const closeContextMenu = React.useCallback(() => {
    setContextMenu(null);
  }, []);

  const handleCreateFolderInCurrentDir = React.useCallback(() => {
    // Pass the current folder ID - creates subfolder of current directory
    // If selectedFolderId is null, creates folder at root level
    openCreateModal(selectedFolderId);
    closeContextMenu();
  }, [selectedFolderId, openCreateModal, closeContextMenu]);

  return (
    <>
      <BrowserContainer>
        {/* Folder Tree Sidebar */}
        <Sidebar $visible={showSidebar} $collapsed={sidebarCollapsed}>
          <FolderTreeSidebar
            corpusId={corpusId}
            onFolderSelect={handleFolderSelect}
          />
        </Sidebar>

        {/* Toggle Button */}
        {showSidebar && (
          <ToggleButton
            $collapsed={sidebarCollapsed}
            onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
            aria-label={sidebarCollapsed ? "Open folders" : "Close folders"}
            title={sidebarCollapsed ? "Open folders" : "Close folders"}
          >
            {sidebarCollapsed ? <Folder /> : <FolderOpen />}
          </ToggleButton>
        )}

        {/* Main Content Area */}
        <MainContent $hasSidebar={showSidebar && !sidebarCollapsed}>
          {/* Breadcrumb Navigation - hide for trash folder */}
          <BreadcrumbWrapper
            $visible={showBreadcrumb && selectedFolderId !== "trash"}
          >
            <FolderBreadcrumb onFolderSelect={handleFolderSelect} />
          </BreadcrumbWrapper>

          {/* Document List or Custom Content */}
          <ContentArea
            onContextMenu={
              selectedFolderId === "trash"
                ? undefined
                : handleContentAreaContextMenu
            }
          >
            {selectedFolderId === "trash" ? (
              <TrashFolderView
                corpusId={corpusId}
                onBack={() => handleFolderSelect(null)}
              />
            ) : (
              children
            )}
          </ContentArea>
        </MainContent>
      </BrowserContainer>

      {/* Folder Action Modals */}
      <CreateFolderModal />
      <EditFolderModal />
      <MoveFolderModal />
      <DeleteFolderModal />

      {/* Context menu for content area */}
      {contextMenu && (
        <>
          <ContextMenuOverlay onClick={closeContextMenu} />
          <ContextMenu $x={contextMenu.x} $y={contextMenu.y}>
            <ContextMenuItem onClick={handleCreateFolderInCurrentDir}>
              Create Folder Here
            </ContextMenuItem>
          </ContextMenu>
        </>
      )}
    </>
  );
};
