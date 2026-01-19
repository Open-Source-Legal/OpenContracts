import React, { useCallback, useEffect, useMemo } from "react";
import { useAtom, useAtomValue, useSetAtom } from "jotai";
import { useQuery } from "@apollo/client";
import styled from "styled-components";
import { Spinner } from "@os-legal/ui";
import { Home, Trash2 } from "lucide-react";
import { useDroppable } from "@dnd-kit/core";
import { FolderTreeNode } from "./FolderTreeNode";
import {
  folderTreeAtom,
  folderListAtom,
  folderCorpusIdAtom,
  selectedFolderIdAtom,
  folderSearchQueryAtom,
} from "../../../atoms/folderAtoms";
import {
  GET_CORPUS_FOLDERS,
  GetCorpusFoldersInputs,
  GetCorpusFoldersOutputs,
  FolderTreeNode as FolderTreeNodeType,
} from "../../../graphql/queries/folders";
import {
  OS_LEGAL_COLORS,
  OS_LEGAL_SPACING,
} from "../../../assets/configurations/osLegalStyles";

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
  background: ${OS_LEGAL_COLORS.surfaceHover};
  overflow: hidden;
`;

const SidebarHeader = styled.div`
  padding: 12px 16px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: ${OS_LEGAL_COLORS.textMuted};
  border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
  background: ${OS_LEGAL_COLORS.surface};
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
    background: ${OS_LEGAL_COLORS.surfaceHover};
  }

  &::-webkit-scrollbar-thumb {
    background: ${OS_LEGAL_COLORS.borderHover};
    border-radius: 4px;

    &:hover {
      background: ${OS_LEGAL_COLORS.textMuted};
    }
  }

  &::-webkit-scrollbar-corner {
    background: ${OS_LEGAL_COLORS.surfaceHover};
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
      ? OS_LEGAL_COLORS.selectedBg
      : props.$isOver
      ? OS_LEGAL_COLORS.dropTargetBg
      : "transparent"};
  border: 1px solid
    ${(props) =>
      props.$isSelected
        ? OS_LEGAL_COLORS.selectedBorder
        : props.$isOver
        ? OS_LEGAL_COLORS.dropTargetBorder
        : "transparent"};
  transition: all 0.15s ease;

  &:hover {
    background-color: ${(props) =>
      props.$isSelected
        ? OS_LEGAL_COLORS.accentLight
        : "rgba(148, 163, 184, 0.1)"};
  }
`;

const RootFolderIcon = styled.div`
  display: flex;
  align-items: center;
  margin-right: 10px;
  color: ${OS_LEGAL_COLORS.textSecondary};
`;

const RootFolderName = styled.span<{ $isSelected: boolean }>`
  font-size: 14px;
  font-weight: ${(props) => (props.$isSelected ? "600" : "500")};
  color: ${(props) =>
    props.$isSelected ? OS_LEGAL_COLORS.accent : OS_LEGAL_COLORS.textPrimary};
`;

const LoadingContainer = styled.div`
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  color: ${OS_LEGAL_COLORS.textSecondary};
`;

const ErrorContainer = styled.div`
  padding: 20px;
  color: ${OS_LEGAL_COLORS.danger};
  font-size: 14px;
  text-align: center;
`;

const EmptyState = styled.div`
  padding: 40px 20px;
  text-align: center;
  color: ${OS_LEGAL_COLORS.textMuted};
  font-size: 14px;
`;

// Component for making Documents root droppable
const DocumentsRootDropTarget: React.FC<{
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
      <RootFolderName $isSelected={isSelected}>Documents</RootFolderName>
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
  const [searchQuery] = useAtom(folderSearchQueryAtom);

  // Note: Drag-and-drop is now handled by FolderDocumentBrowser's unified DndContext
  // This component just renders droppable tree nodes

  // Fetch folders from server
  const { loading, error, data } = useQuery<
    GetCorpusFoldersOutputs,
    GetCorpusFoldersInputs
  >(GET_CORPUS_FOLDERS, {
    variables: { corpusId },
    fetchPolicy: "cache-and-network",
  });

  // Update atom whenever query data changes (more reliable than onCompleted)
  // This ensures the folder tree updates when cache is evicted and refetched
  useEffect(() => {
    if (data?.corpusFolders) {
      setFolderList(data.corpusFolders);
      setFolderCorpusId(corpusId);
    }
  }, [data, corpusId, setFolderList, setFolderCorpusId]);

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

  const handleTrashClick = useCallback(() => {
    if (onFolderSelect) {
      onFolderSelect("trash");
    } else {
      setSelectedFolderId("trash");
    }
  }, [onFolderSelect, setSelectedFolderId]);

  // Note: Drag-and-drop handlers are now in FolderDocumentBrowser's unified DndContext

  return (
    <SidebarContainer>
      <SidebarHeader>Folders</SidebarHeader>

      {/* TreeContainer is a droppable area - DndContext is provided by FolderDocumentBrowser */}
      <TreeContainer>
        {/* Documents Root Item (Droppable) */}
        <DocumentsRootDropTarget
          isSelected={selectedFolderId === null}
          onClick={handleRootClick}
        />

        {/* Trash Folder Item */}
        <TrashFolderItem
          isSelected={selectedFolderId === "trash"}
          onClick={handleTrashClick}
        />

        {/* Loading State */}
        {loading && (
          <LoadingContainer>
            <Spinner size={16} />
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
    </SidebarContainer>
  );
};
