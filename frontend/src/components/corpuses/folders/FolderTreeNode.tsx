import React, { useCallback } from "react";
import { useAtom, useAtomValue, useSetAtom } from "jotai";
import styled from "styled-components";
import { ChevronRight, ChevronDown, Folder, FolderOpen } from "lucide-react";
import { useDraggable, useDroppable } from "@dnd-kit/core";
import { CSS } from "@dnd-kit/utilities";
import {
  selectedFolderIdAtom,
  expandedFolderIdsAtom,
  toggleFolderExpansionAtom,
  selectAndExpandFolderAtom,
  openEditFolderModalAtom,
  openDeleteFolderModalAtom,
  openCreateFolderModalAtom,
  dropTargetFolderIdAtom,
  draggingFolderIdAtom,
} from "../../../atoms/folderAtoms";
import { FolderTreeNode as FolderTreeNodeType } from "../../../graphql/queries/folders";

/**
 * FolderTreeNode - Recursive tree node component for folder hierarchy
 *
 * Features:
 * - Expand/collapse with chevron icon
 * - Selection highlighting
 * - Context menu (right-click)
 * - Drag-and-drop support
 * - Recursive rendering of children
 * - Badge showing document count
 *
 * Props:
 * - folder: The folder data
 * - depth: Current nesting level (for indentation)
 * - onFolderSelect: Callback when folder is clicked
 */

interface FolderTreeNodeProps {
  folder: FolderTreeNodeType;
  depth?: number;
  onFolderSelect?: (folderId: string) => void;
}

const NodeContainer = styled.div<{
  $depth: number;
  $isSelected: boolean;
  $isDropTarget: boolean;
}>`
  display: flex;
  align-items: center;
  padding: 6px 8px;
  padding-left: ${(props) => props.$depth * 20 + 8}px;
  cursor: pointer;
  user-select: none;
  border-radius: 6px;
  margin: 2px 4px;
  min-width: fit-content;
  transition: all 0.15s ease;
  background-color: ${(props) =>
    props.$isSelected
      ? "rgba(59, 130, 246, 0.1)"
      : props.$isDropTarget
      ? "rgba(34, 197, 94, 0.1)"
      : "transparent"};
  border: 1px solid
    ${(props) =>
      props.$isSelected
        ? "rgba(59, 130, 246, 0.3)"
        : props.$isDropTarget
        ? "rgba(34, 197, 94, 0.3)"
        : "transparent"};

  &:hover {
    background-color: ${(props) =>
      props.$isSelected
        ? "rgba(59, 130, 246, 0.15)"
        : "rgba(148, 163, 184, 0.1)"};
  }

  &:active {
    background-color: rgba(59, 130, 246, 0.2);
  }
`;

const ChevronButton = styled.button<{ $isExpanded: boolean }>`
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  padding: 0;
  margin-right: 4px;
  background: none;
  border: none;
  cursor: pointer;
  color: #64748b;
  transition: transform 0.2s ease, color 0.15s ease;
  transform: rotate(${(props) => (props.$isExpanded ? 90 : 0)}deg);

  &:hover {
    color: #3b82f6;
  }

  &:focus {
    outline: none;
  }
`;

const IconPlaceholder = styled.div`
  width: 20px;
  height: 20px;
  margin-right: 4px;
`;

const FolderIconWrapper = styled.div<{ $color: string }>`
  display: flex;
  align-items: center;
  margin-right: 8px;
  color: ${(props) => props.$color};
`;

const FolderName = styled.span<{ $isSelected: boolean }>`
  flex: 1;
  font-size: 14px;
  color: ${(props) => (props.$isSelected ? "#1e40af" : "#1e293b")};
  font-weight: ${(props) => (props.$isSelected ? "600" : "400")};
  white-space: nowrap;
  min-width: 0;
`;

const DocumentCountBadge = styled.span`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 20px;
  height: 18px;
  padding: 0 6px;
  margin-left: 8px;
  background-color: #e2e8f0;
  color: #475569;
  font-size: 11px;
  font-weight: 600;
  border-radius: 9px;
  transition: all 0.15s ease;

  ${NodeContainer}:hover & {
    background-color: #cbd5e1;
    color: #334155;
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

  &.danger {
    color: #dc2626;

    &:hover {
      background-color: #fee2e2;
      color: #991b1b;
    }
  }
`;

export const FolderTreeNode: React.FC<FolderTreeNodeProps> = ({
  folder,
  depth = 0,
  onFolderSelect,
}) => {
  const [selectedFolderId, setSelectedFolderId] = useAtom(selectedFolderIdAtom);
  const expandedFolderIds = useAtomValue(expandedFolderIdsAtom);
  const toggleExpansion = useSetAtom(toggleFolderExpansionAtom);
  const selectAndExpand = useSetAtom(selectAndExpandFolderAtom);
  const dropTargetId = useAtomValue(dropTargetFolderIdAtom);
  const draggingFolderId = useAtomValue(draggingFolderIdAtom);

  const openEditModal = useSetAtom(openEditFolderModalAtom);
  const openDeleteModal = useSetAtom(openDeleteFolderModalAtom);
  const openCreateModal = useSetAtom(openCreateFolderModalAtom);

  const [contextMenu, setContextMenu] = React.useState<{
    x: number;
    y: number;
  } | null>(null);

  const hasChildren = folder.children.length > 0;
  const isExpanded = expandedFolderIds.has(folder.id);
  const isSelected = selectedFolderId === folder.id;
  const isDropTarget = dropTargetId === folder.id;
  const isDragging = draggingFolderId === folder.id;

  // Draggable setup
  const {
    attributes,
    listeners,
    setNodeRef: setDraggableRef,
    transform,
  } = useDraggable({
    id: folder.id,
  });

  // Droppable setup (folder can be a drop target)
  const { setNodeRef: setDroppableRef, isOver } = useDroppable({
    id: folder.id,
  });

  // Combine refs (node is both draggable and droppable)
  const setRefs = useCallback(
    (node: HTMLDivElement | null) => {
      setDraggableRef(node);
      setDroppableRef(node);
    },
    [setDraggableRef, setDroppableRef]
  );

  // Apply transform for drag preview
  const style = transform
    ? {
        transform: CSS.Translate.toString(transform),
        opacity: isDragging ? 0.5 : 1,
      }
    : undefined;

  const handleChevronClick = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      if (hasChildren) {
        toggleExpansion(folder.id);
      }
    },
    [hasChildren, folder.id, toggleExpansion]
  );

  const handleNodeClick = useCallback(() => {
    if (onFolderSelect) {
      onFolderSelect(folder.id);
    } else {
      selectAndExpand(folder.id);
    }
  }, [folder.id, onFolderSelect, selectAndExpand]);

  const handleContextMenu = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setContextMenu({ x: e.clientX, y: e.clientY });
  }, []);

  const closeContextMenu = useCallback(() => {
    setContextMenu(null);
  }, []);

  const handleEdit = useCallback(() => {
    openEditModal(folder.id);
    closeContextMenu();
  }, [folder.id, openEditModal, closeContextMenu]);

  const handleDelete = useCallback(() => {
    openDeleteModal(folder.id);
    closeContextMenu();
  }, [folder.id, openDeleteModal, closeContextMenu]);

  const handleCreateSubfolder = useCallback(() => {
    openCreateModal(folder.id);
    closeContextMenu();
  }, [folder.id, openCreateModal, closeContextMenu]);

  return (
    <>
      <NodeContainer
        ref={setRefs}
        $depth={depth}
        $isSelected={isSelected}
        $isDropTarget={isOver}
        onClick={handleNodeClick}
        onContextMenu={handleContextMenu}
        title={folder.path}
        style={style}
        {...attributes}
        {...listeners}
      >
        {hasChildren ? (
          <ChevronButton
            $isExpanded={isExpanded}
            onClick={handleChevronClick}
            aria-label={isExpanded ? "Collapse folder" : "Expand folder"}
          >
            <ChevronRight size={16} />
          </ChevronButton>
        ) : (
          <IconPlaceholder />
        )}

        <FolderIconWrapper $color={folder.color}>
          {isExpanded ? <FolderOpen size={18} /> : <Folder size={18} />}
        </FolderIconWrapper>

        <FolderName $isSelected={isSelected}>{folder.name}</FolderName>

        {folder.documentCount > 0 && (
          <DocumentCountBadge>{folder.documentCount}</DocumentCountBadge>
        )}
      </NodeContainer>

      {/* Render children recursively if expanded */}
      {hasChildren && isExpanded && (
        <>
          {folder.children.map((child) => (
            <FolderTreeNode
              key={child.id}
              folder={child}
              depth={depth + 1}
              onFolderSelect={onFolderSelect}
            />
          ))}
        </>
      )}

      {/* Context menu */}
      {contextMenu && (
        <>
          <ContextMenuOverlay onClick={closeContextMenu} />
          <ContextMenu $x={contextMenu.x} $y={contextMenu.y}>
            <ContextMenuItem onClick={handleNodeClick}>
              Open Folder
            </ContextMenuItem>
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
