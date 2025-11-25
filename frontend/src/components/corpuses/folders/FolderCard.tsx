import React, { useCallback } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import styled from "styled-components";
import { Folder, FolderOpen, FileText, MoreVertical } from "lucide-react";
import { useSetAtom } from "jotai";
import { useDroppable } from "@dnd-kit/core";
import {
  openEditFolderModalAtom,
  openDeleteFolderModalAtom,
  openCreateFolderModalAtom,
} from "../../../atoms/folderAtoms";
import { FolderTreeNode } from "../../../graphql/queries/folders";

/**
 * FolderCard - Card view component for folders in document grid
 *
 * Features:
 * - Displays folder info (name, document count, icon)
 * - Click to navigate into folder
 * - Context menu (right-click) for folder actions
 * - Droppable - accepts documents and folders
 * - Responsive card design matching ModernDocumentItem
 */

interface FolderCardProps {
  folder: FolderTreeNode;
  viewMode?: "modern-card" | "modern-list";
  onFolderSelect?: (folderId: string) => void;
}

// ===============================================
// CARD VIEW (Desktop)
// ===============================================
const CardContainer = styled.div<{ $isDropTarget: boolean }>`
  position: relative;
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  overflow: hidden;
  transition: all 0.2s ease;
  cursor: pointer;
  height: 200px;
  display: flex;
  flex-direction: column;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
  background-color: ${(props) =>
    props.$isDropTarget ? "rgba(34, 197, 94, 0.05)" : "white"};
  border-color: ${(props) =>
    props.$isDropTarget ? "rgba(34, 197, 94, 0.3)" : "#e2e8f0"};

  &:hover {
    border-color: ${(props) =>
      props.$isDropTarget ? "rgba(34, 197, 94, 0.5)" : "#cbd5e1"};
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
    transform: translateY(-2px);

    .action-button {
      opacity: 1;
    }
  }
`;

const CardPreview = styled.div<{ $color: string }>`
  position: relative;
  height: 90px;
  background: ${(props) => props.$color || "#f8fafc"};
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
`;

const FolderIconWrapper = styled.div`
  color: rgba(255, 255, 255, 0.9);
  display: flex;
  align-items: center;
  justify-content: center;
`;

const CardContent = styled.div`
  flex: 1;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-height: 0;
`;

const CardTitle = styled.div`
  font-size: 14px;
  font-weight: 600;
  color: #1e293b;
  line-height: 1.3;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  text-overflow: ellipsis;
  word-break: break-word;
`;

const CardStats = styled.div`
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: auto;
  font-size: 12px;
  color: #64748b;
`;

const Stat = styled.div`
  display: flex;
  align-items: center;
  gap: 4px;
`;

const ActionButton = styled.button`
  position: absolute;
  top: 8px;
  right: 8px;
  width: 28px;
  height: 28px;
  border-radius: 6px;
  border: none;
  background: rgba(255, 255, 255, 0.95);
  color: #64748b;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: all 0.15s ease;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  z-index: 10;

  &:hover {
    background: white;
    color: #1e293b;
    transform: scale(1.05);
  }

  &:active {
    transform: scale(0.98);
  }
`;

// ===============================================
// LIST VIEW (Mobile & Dense)
// ===============================================
const ListContainer = styled.div<{ $isDropTarget: boolean }>`
  position: relative;
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 12px 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  cursor: pointer;
  transition: all 0.15s ease;
  background-color: ${(props) =>
    props.$isDropTarget ? "rgba(34, 197, 94, 0.05)" : "white"};
  border-color: ${(props) =>
    props.$isDropTarget ? "rgba(34, 197, 94, 0.3)" : "#e2e8f0"};

  &:hover {
    border-color: ${(props) =>
      props.$isDropTarget ? "rgba(34, 197, 94, 0.5)" : "#cbd5e1"};
    background-color: ${(props) =>
      props.$isDropTarget ? "rgba(34, 197, 94, 0.08)" : "#f8fafc"};

    .action-button {
      opacity: 1;
    }
  }

  @media (max-width: 640px) {
    padding: 10px 12px;
    gap: 10px;
  }
`;

const ListIconWrapper = styled.div<{ $color: string }>`
  flex-shrink: 0;
  width: 48px;
  height: 48px;
  border-radius: 8px;
  background: ${(props) => props.$color || "#f8fafc"};
  display: flex;
  align-items: center;
  justify-content: center;
  color: rgba(255, 255, 255, 0.9);

  @media (max-width: 640px) {
    width: 40px;
    height: 40px;
  }
`;

const ListContent = styled.div`
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
`;

const ListTitle = styled.div`
  font-size: 14px;
  font-weight: 600;
  color: #1e293b;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;

  @media (max-width: 640px) {
    font-size: 13px;
  }
`;

const ListStats = styled.div`
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 12px;
  color: #64748b;

  @media (max-width: 640px) {
    font-size: 11px;
    gap: 8px;
  }
`;

const ListActionButton = styled(ActionButton)`
  position: relative;
  top: auto;
  right: auto;
  opacity: 0.7;

  @media (max-width: 640px) {
    width: 32px;
    height: 32px;
  }
`;

// ===============================================
// CONTEXT MENU
// ===============================================
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

  &.danger {
    color: #dc2626;

    &:hover {
      background-color: #fee2e2;
      color: #991b1b;
    }
  }
`;

export const FolderCard: React.FC<FolderCardProps> = ({
  folder,
  viewMode = "modern-card",
  onFolderSelect,
}) => {
  const navigate = useNavigate();
  const location = useLocation();

  const openEditModal = useSetAtom(openEditFolderModalAtom);
  const openDeleteModal = useSetAtom(openDeleteFolderModalAtom);
  const openCreateModal = useSetAtom(openCreateFolderModalAtom);

  const [contextMenu, setContextMenu] = React.useState<{
    x: number;
    y: number;
  } | null>(null);

  // Droppable setup (folder can accept documents and folders)
  const { setNodeRef, isOver } = useDroppable({
    id: `folder-card-${folder.id}`,
    data: {
      type: "folder",
      folderId: folder.id,
    },
  });

  const handleClick = useCallback(
    (e: React.MouseEvent) => {
      // Don't trigger if clicking action button
      if ((e.target as HTMLElement).closest(".action-button")) {
        return;
      }

      if (onFolderSelect) {
        onFolderSelect(folder.id);
      } else {
        // Update URL to navigate into folder
        const searchParams = new URLSearchParams(location.search);
        searchParams.set("folder", folder.id);
        navigate({ search: `?${searchParams.toString()}` }, { replace: true });
      }
    },
    [folder.id, onFolderSelect, navigate, location.search]
  );

  const handleContextMenu = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setContextMenu({ x: e.clientX, y: e.clientY });
  }, []);

  const closeContextMenu = useCallback(() => {
    setContextMenu(null);
  }, []);

  const handleEdit = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      openEditModal(folder.id);
      closeContextMenu();
    },
    [folder.id, openEditModal, closeContextMenu]
  );

  const handleDelete = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      openDeleteModal(folder.id);
      closeContextMenu();
    },
    [folder.id, openDeleteModal, closeContextMenu]
  );

  const handleCreateSubfolder = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      openCreateModal(folder.id);
      closeContextMenu();
    },
    [folder.id, openCreateModal, closeContextMenu]
  );

  const handleActionClick = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    setContextMenu({ x: e.clientX, y: e.clientY });
  }, []);

  const totalDocs = folder.documentCount + folder.descendantDocumentCount;
  const subfolderCount = folder.children?.length || 0;

  if (viewMode === "modern-list") {
    return (
      <>
        <ListContainer
          ref={setNodeRef}
          $isDropTarget={isOver}
          onClick={handleClick}
          onContextMenu={handleContextMenu}
        >
          <ListIconWrapper $color={folder.color}>
            <Folder size={24} />
          </ListIconWrapper>

          <ListContent>
            <ListTitle>{folder.name}</ListTitle>
            <ListStats>
              <Stat>
                <FileText size={12} />
                {totalDocs} {totalDocs === 1 ? "doc" : "docs"}
              </Stat>
              {subfolderCount > 0 && (
                <Stat>
                  <Folder size={12} />
                  {subfolderCount} {subfolderCount === 1 ? "folder" : "folders"}
                </Stat>
              )}
            </ListStats>
          </ListContent>

          <ListActionButton
            className="action-button"
            onClick={handleActionClick}
          >
            <MoreVertical size={16} />
          </ListActionButton>
        </ListContainer>

        {/* Context menu */}
        {contextMenu && (
          <>
            <ContextMenuOverlay onClick={closeContextMenu} />
            <ContextMenu $x={contextMenu.x} $y={contextMenu.y}>
              <ContextMenuItem onClick={handleClick}>
                Open Folder
              </ContextMenuItem>
              <ContextMenuItem onClick={handleCreateSubfolder}>
                Create Subfolder
              </ContextMenuItem>
              <ContextMenuItem onClick={handleEdit}>
                Edit Folder
              </ContextMenuItem>
              <ContextMenuItem onClick={handleDelete} className="danger">
                Delete Folder
              </ContextMenuItem>
            </ContextMenu>
          </>
        )}
      </>
    );
  }

  // Card view (default)
  return (
    <>
      <CardContainer
        ref={setNodeRef}
        $isDropTarget={isOver}
        onClick={handleClick}
        onContextMenu={handleContextMenu}
      >
        <CardPreview $color={folder.color}>
          <FolderIconWrapper>
            <Folder size={48} />
          </FolderIconWrapper>
        </CardPreview>

        <CardContent>
          <CardTitle>{folder.name}</CardTitle>

          <CardStats>
            <Stat>
              <FileText size={12} />
              {totalDocs}
            </Stat>
            {subfolderCount > 0 && (
              <Stat>
                <Folder size={12} />
                {subfolderCount}
              </Stat>
            )}
          </CardStats>
        </CardContent>

        <ActionButton className="action-button" onClick={handleActionClick}>
          <MoreVertical size={16} />
        </ActionButton>
      </CardContainer>

      {/* Context menu */}
      {contextMenu && (
        <>
          <ContextMenuOverlay onClick={closeContextMenu} />
          <ContextMenu $x={contextMenu.x} $y={contextMenu.y}>
            <ContextMenuItem onClick={handleClick}>Open Folder</ContextMenuItem>
            <ContextMenuItem onClick={handleCreateSubfolder}>
              Create Subfolder
            </ContextMenuItem>
            <ContextMenuItem onClick={handleEdit}>Edit Folder</ContextMenuItem>
            <ContextMenuItem onClick={handleDelete} className="danger">
              Delete Folder
            </ContextMenuItem>
          </ContextMenu>
        </>
      )}
    </>
  );
};
