import React, { useCallback, useMemo, useState } from "react";
import { useAtom, useAtomValue, useSetAtom } from "jotai";
import { useQuery, useMutation } from "@apollo/client";
import styled from "styled-components";
import { Loader, Input, Button } from "semantic-ui-react";
import { toast } from "react-toastify";
import {
  FolderPlus,
  Search,
  ChevronDown,
  ChevronUp,
  Home,
  Trash2,
} from "lucide-react";
import {
  DndContext,
  DragEndEvent,
  DragOverlay,
  DragStartEvent,
  PointerSensor,
  useSensor,
  useSensors,
  closestCenter,
  useDroppable,
} from "@dnd-kit/core";
import { FolderTreeNode } from "./FolderTreeNode";
import {
  folderTreeAtom,
  folderListAtom,
  folderCorpusIdAtom,
  selectedFolderIdAtom,
  openCreateFolderModalAtom,
  folderSearchQueryAtom,
  expandAllFoldersAtom,
  collapseAllFoldersAtom,
  canCreateFoldersAtom,
} from "../../../atoms/folderAtoms";
import {
  GET_CORPUS_FOLDERS,
  GetCorpusFoldersInputs,
  GetCorpusFoldersOutputs,
  FolderTreeNode as FolderTreeNodeType,
  MOVE_CORPUS_FOLDER,
  MoveCorpusFolderInputs,
  MoveCorpusFolderOutputs,
  MOVE_DOCUMENT_TO_FOLDER,
  MoveDocumentToFolderInputs,
  MoveDocumentToFolderOutputs,
} from "../../../graphql/queries/folders";

/**
 * FolderTreeSidebar - Main folder tree navigation component
 *
 * Features:
 * - Loads and displays folder tree for current corpus
 * - Search/filter folders by name
 * - "Corpus Root" item at top for viewing all documents
 * - Create folder button (when permitted)
 * - Expand/collapse all actions
 * - Virtualization ready (can add react-window if performance needed)
 * - Loading and error states
 *
 * Props:
 * - corpusId: The corpus to load folders for
 * - onFolderSelect: Optional callback when folder selected
 */

interface FolderTreeSidebarProps {
  corpusId: string;
  onFolderSelect?: (folderId: string | null) => void;
}

const SidebarContainer = styled.div`
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #ffffff;
  border-right: 1px solid #e2e8f0;
  overflow: hidden;
`;

const SidebarHeader = styled.div`
  display: flex;
  flex-direction: column;
  padding: 16px;
  border-bottom: 1px solid #e2e8f0;
  background: #f8fafc;
`;

const HeaderRow = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
`;

const HeaderTitle = styled.h3`
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #1e293b;
`;

const CreateFolderButton = styled(Button)`
  &.ui.button {
    padding: 8px 12px;
    background: #3b82f6;
    color: white;
    font-size: 13px;
    border-radius: 6px;
    display: flex;
    align-items: center;
    gap: 6px;
    transition: all 0.15s ease;

    &:hover {
      background: #2563eb;
      transform: translateY(-1px);
    }

    &:active {
      transform: translateY(0);
    }
  }
`;

const SearchInputWrapper = styled.div`
  margin-bottom: 8px;

  .ui.input {
    width: 100%;

    input {
      border-radius: 6px;
      border: 1px solid #cbd5e1;
      padding: 8px 12px;
      font-size: 14px;

      &:focus {
        border-color: #3b82f6;
        box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
      }
    }
  }
`;

const ActionRow = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
`;

const ActionButton = styled.button`
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 10px;
  background: none;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  font-size: 12px;
  color: #64748b;
  cursor: pointer;
  transition: all 0.15s ease;

  &:hover {
    background: #f1f5f9;
    border-color: #94a3b8;
    color: #475569;
  }

  &:active {
    background: #e2e8f0;
  }
`;

const TreeContainer = styled.div`
  flex: 1;
  overflow-y: auto;
  overflow-x: auto;
  padding: 8px 0;

  /* Custom scrollbar - vertical */
  &::-webkit-scrollbar {
    width: 8px;
    height: 8px;
  }

  &::-webkit-scrollbar-track {
    background: #f1f5f9;
  }

  &::-webkit-scrollbar-thumb {
    background: #cbd5e1;
    border-radius: 4px;

    &:hover {
      background: #94a3b8;
    }
  }

  &::-webkit-scrollbar-corner {
    background: #f1f5f9;
  }
`;

const RootFolderItem = styled.div<{ $isSelected: boolean; $isOver?: boolean }>`
  display: flex;
  align-items: center;
  padding: 10px 12px;
  margin: 4px 8px;
  cursor: pointer;
  border-radius: 6px;
  background-color: ${(props) =>
    props.$isSelected
      ? "rgba(59, 130, 246, 0.1)"
      : props.$isOver
      ? "rgba(34, 197, 94, 0.1)"
      : "transparent"};
  border: 1px solid
    ${(props) =>
      props.$isSelected
        ? "rgba(59, 130, 246, 0.3)"
        : props.$isOver
        ? "rgba(34, 197, 94, 0.3)"
        : "transparent"};
  transition: all 0.15s ease;

  &:hover {
    background-color: ${(props) =>
      props.$isSelected
        ? "rgba(59, 130, 246, 0.15)"
        : "rgba(148, 163, 184, 0.1)"};
  }
`;

const RootFolderIcon = styled.div`
  display: flex;
  align-items: center;
  margin-right: 10px;
  color: #64748b;
`;

const RootFolderName = styled.span<{ $isSelected: boolean }>`
  font-size: 14px;
  font-weight: ${(props) => (props.$isSelected ? "600" : "500")};
  color: ${(props) => (props.$isSelected ? "#1e40af" : "#475569")};
`;

const LoadingContainer = styled.div`
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  color: #64748b;
`;

const ErrorContainer = styled.div`
  padding: 20px;
  color: #dc2626;
  font-size: 14px;
  text-align: center;
`;

const EmptyState = styled.div`
  padding: 40px 20px;
  text-align: center;
  color: #94a3b8;
  font-size: 14px;
`;

// Component for making Corpus Root droppable
const CorpusRootDropTarget: React.FC<{
  isSelected: boolean;
  onClick: () => void;
}> = ({ isSelected, onClick }) => {
  const { setNodeRef, isOver } = useDroppable({
    id: "root",
  });

  return (
    <RootFolderItem
      ref={setNodeRef}
      $isSelected={isSelected}
      $isOver={isOver}
      onClick={onClick}
    >
      <RootFolderIcon>
        <Home size={18} />
      </RootFolderIcon>
      <RootFolderName $isSelected={isSelected}>Corpus Root</RootFolderName>
    </RootFolderItem>
  );
};

// Component for Trash folder (virtual folder for deleted documents)
const TrashFolderItem: React.FC<{
  isSelected: boolean;
  onClick: () => void;
}> = ({ isSelected, onClick }) => {
  return (
    <RootFolderItem $isSelected={isSelected} onClick={onClick}>
      <RootFolderIcon>
        <Trash2 size={18} />
      </RootFolderIcon>
      <RootFolderName $isSelected={isSelected}>Trash</RootFolderName>
    </RootFolderItem>
  );
};

export const FolderTreeSidebar: React.FC<FolderTreeSidebarProps> = ({
  corpusId,
  onFolderSelect,
}) => {
  const [, setFolderList] = useAtom(folderListAtom);
  const [, setFolderCorpusId] = useAtom(folderCorpusIdAtom);
  const [selectedFolderId, setSelectedFolderId] = useAtom(selectedFolderIdAtom);
  const folderTree = useAtomValue(folderTreeAtom);
  const [searchQuery, setSearchQuery] = useAtom(folderSearchQueryAtom);
  const canCreateFolders = useAtomValue(canCreateFoldersAtom);

  const openCreateModal = useSetAtom(openCreateFolderModalAtom);
  const expandAll = useSetAtom(expandAllFoldersAtom);
  const collapseAll = useSetAtom(collapseAllFoldersAtom);

  // Drag-and-drop state
  const [activeDragId, setActiveDragId] = useState<string | null>(null);

  // Configure drag sensors
  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: {
        distance: 8, // Require 8px movement before drag starts
      },
    })
  );

  // Move folder mutation
  const [moveFolder] = useMutation<
    MoveCorpusFolderOutputs,
    MoveCorpusFolderInputs
  >(MOVE_CORPUS_FOLDER, {
    refetchQueries: [
      {
        query: GET_CORPUS_FOLDERS,
        variables: { corpusId },
      },
    ],
  });

  // Move document to folder mutation
  const [moveDocument] = useMutation<
    MoveDocumentToFolderOutputs,
    MoveDocumentToFolderInputs
  >(MOVE_DOCUMENT_TO_FOLDER, {
    refetchQueries: [
      {
        query: GET_CORPUS_FOLDERS,
        variables: { corpusId },
      },
    ],
  });

  // Fetch folders from server
  const { loading, error, data } = useQuery<
    GetCorpusFoldersOutputs,
    GetCorpusFoldersInputs
  >(GET_CORPUS_FOLDERS, {
    variables: { corpusId },
    onCompleted: (data) => {
      setFolderList(data.corpusFolders);
      setFolderCorpusId(corpusId);
    },
    fetchPolicy: "cache-and-network",
  });

  // Filter tree based on search query
  const filteredTree = useMemo(() => {
    if (!searchQuery.trim()) {
      return folderTree;
    }

    const query = searchQuery.toLowerCase();

    const filterNodes = (nodes: FolderTreeNodeType[]): FolderTreeNodeType[] => {
      return nodes
        .map((node) => {
          const matches = node.name.toLowerCase().includes(query);
          const filteredChildren = filterNodes(node.children);

          // Include node if it matches or has matching children
          if (matches || filteredChildren.length > 0) {
            return {
              ...node,
              children: filteredChildren,
            };
          }
          return null;
        })
        .filter((node): node is FolderTreeNodeType => node !== null);
    };

    return filterNodes(folderTree);
  }, [folderTree, searchQuery]);

  const handleRootClick = useCallback(() => {
    if (onFolderSelect) {
      onFolderSelect(null);
    } else {
      setSelectedFolderId(null);
    }
  }, [onFolderSelect, setSelectedFolderId]);

  const handleCreateFolder = useCallback(() => {
    openCreateModal(null); // null = create at root
  }, [openCreateModal]);

  const handleExpandAll = useCallback(() => {
    expandAll();
  }, [expandAll]);

  const handleCollapseAll = useCallback(() => {
    collapseAll();
  }, [collapseAll]);

  // Drag-and-drop handlers
  const handleDragStart = useCallback((event: DragStartEvent) => {
    setActiveDragId(event.active.id as string);
  }, []);

  const handleDragEnd = useCallback(
    (event: DragEndEvent) => {
      const { active, over } = event;
      setActiveDragId(null);

      if (!over || active.id === over.id) {
        return; // Dropped on itself or no drop target
      }

      const dragData = active.data.current;
      const dropData = over.data.current;

      // Determine what was dropped and where
      const isDraggingDocument = dragData?.type === "document";
      const isDraggingFolder = !isDraggingDocument;

      // Extract target folder ID (handle both folder tree nodes and folder cards)
      let targetFolderId: string | null;
      if (over.id === "root") {
        targetFolderId = null;
      } else if (dropData?.type === "folder") {
        targetFolderId = dropData.folderId;
      } else {
        targetFolderId = over.id as string;
      }

      if (isDraggingDocument) {
        // Moving document to folder
        const documentId = dragData.documentId;

        moveDocument({
          variables: {
            documentId,
            corpusId,
            folderId: targetFolderId,
          },
        })
          .then((result) => {
            if (result.data?.moveDocumentToFolder.ok) {
              toast.success(
                targetFolderId
                  ? "Document moved to folder"
                  : "Document moved to corpus root"
              );
            } else {
              toast.error(
                result.data?.moveDocumentToFolder.message ||
                  "Failed to move document"
              );
            }
          })
          .catch((error) => {
            toast.error(`Error moving document: ${error.message}`);
          });
      } else {
        // Moving folder to folder
        const draggedFolderId = active.id as string;

        // Prevent moving folder into itself
        if (draggedFolderId === targetFolderId) {
          toast.error("Cannot move a folder into itself");
          return;
        }

        moveFolder({
          variables: {
            folderId: draggedFolderId,
            newParentId: targetFolderId,
          },
        })
          .then((result) => {
            if (result.data?.moveCorpusFolder.ok) {
              toast.success("Folder moved successfully");
            } else {
              toast.error(
                result.data?.moveCorpusFolder.message || "Failed to move folder"
              );
            }
          })
          .catch((error) => {
            toast.error(`Error moving folder: ${error.message}`);
          });
      }
    },
    [moveFolder, moveDocument, corpusId]
  );

  return (
    <SidebarContainer>
      <SidebarHeader>
        <HeaderRow>
          <HeaderTitle>Folders</HeaderTitle>
          {canCreateFolders && (
            <CreateFolderButton size="mini" onClick={handleCreateFolder}>
              <FolderPlus size={14} />
              New
            </CreateFolderButton>
          )}
        </HeaderRow>

        <SearchInputWrapper>
          <Input
            icon={<Search size={14} />}
            iconPosition="left"
            placeholder="Search folders..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </SearchInputWrapper>

        <ActionRow>
          <ActionButton onClick={handleExpandAll}>
            <ChevronDown size={14} />
            Expand All
          </ActionButton>
          <ActionButton onClick={handleCollapseAll}>
            <ChevronUp size={14} />
            Collapse All
          </ActionButton>
        </ActionRow>
      </SidebarHeader>

      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragStart={handleDragStart}
        onDragEnd={handleDragEnd}
      >
        <TreeContainer>
          {/* Corpus Root Item (Droppable) */}
          <CorpusRootDropTarget
            isSelected={selectedFolderId === null}
            onClick={handleRootClick}
          />

          {/* Trash Folder Item */}
          <TrashFolderItem
            isSelected={selectedFolderId === "trash"}
            onClick={() => {
              setSelectedFolderId("trash");
              onFolderSelect?.("trash");
            }}
          />

          {/* Loading State */}
          {loading && (
            <LoadingContainer>
              <Loader active inline size="small" />
              <div style={{ marginTop: "12px" }}>Loading folders...</div>
            </LoadingContainer>
          )}

          {/* Error State */}
          {error && (
            <ErrorContainer>
              Failed to load folders: {error.message}
            </ErrorContainer>
          )}

          {/* Empty State */}
          {!loading && !error && filteredTree.length === 0 && !searchQuery && (
            <EmptyState>
              No folders yet. Click "New" to create your first folder.
            </EmptyState>
          )}

          {/* Search Empty State */}
          {!loading &&
            !error &&
            filteredTree.length === 0 &&
            searchQuery &&
            (data?.corpusFolders?.length ?? 0) > 0 && (
              <EmptyState>No folders match "{searchQuery}"</EmptyState>
            )}

          {/* Folder Tree */}
          {!loading &&
            !error &&
            filteredTree.map((folder) => (
              <FolderTreeNode
                key={folder.id}
                folder={folder}
                depth={0}
                onFolderSelect={onFolderSelect}
              />
            ))}
        </TreeContainer>
      </DndContext>
    </SidebarContainer>
  );
};
