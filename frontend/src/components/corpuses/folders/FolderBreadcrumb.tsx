import React, { useCallback } from "react";
import { useAtomValue, useSetAtom } from "jotai";
import styled from "styled-components";
import { ChevronRight, Home } from "lucide-react";
import {
  folderBreadcrumbAtom,
  selectAndExpandFolderAtom,
  selectedFolderIdAtom,
} from "../../../atoms/folderAtoms";

/**
 * FolderBreadcrumb - Navigation breadcrumb showing path from root to current folder
 *
 * Features:
 * - Shows "Corpus Root" > Folder1 > Folder2 > ...
 * - Clickable segments to navigate up hierarchy
 * - Compact display with ellipsis for deep nesting
 * - Highlights current folder
 *
 * Props:
 * - maxDepth: Maximum folders to show before ellipsis (default: 5)
 * - onFolderSelect: Optional callback when breadcrumb item clicked
 */

interface FolderBreadcrumbProps {
  maxDepth?: number;
  onFolderSelect?: (folderId: string | null) => void;
}

const BreadcrumbContainer = styled.div`
  display: flex;
  align-items: center;
  padding: 12px 16px;
  background: #f8fafc;
  border-bottom: 1px solid #e2e8f0;
  overflow-x: auto;
  overflow-y: hidden;
  white-space: nowrap;

  /* Custom scrollbar for horizontal overflow */
  &::-webkit-scrollbar {
    height: 6px;
  }

  &::-webkit-scrollbar-track {
    background: #f1f5f9;
  }

  &::-webkit-scrollbar-thumb {
    background: #cbd5e1;
    border-radius: 3px;

    &:hover {
      background: #94a3b8;
    }
  }
`;

const BreadcrumbItem = styled.button<{ $isLast: boolean }>`
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  background: none;
  border: none;
  border-radius: 6px;
  font-size: 14px;
  font-weight: ${(props) => (props.$isLast ? "600" : "400")};
  color: ${(props) => (props.$isLast ? "#1e40af" : "#64748b")};
  cursor: ${(props) => (props.$isLast ? "default" : "pointer")};
  transition: all 0.15s ease;
  white-space: nowrap;

  &:hover {
    background: ${(props) =>
      props.$isLast ? "transparent" : "rgba(148, 163, 184, 0.1)"};
    color: ${(props) => (props.$isLast ? "#1e40af" : "#475569")};
  }

  &:active {
    background: ${(props) =>
      props.$isLast ? "transparent" : "rgba(148, 163, 184, 0.15)"};
  }
`;

const BreadcrumbSeparator = styled.div`
  display: flex;
  align-items: center;
  color: #cbd5e1;
  margin: 0 4px;
`;

const Ellipsis = styled.div`
  display: flex;
  align-items: center;
  padding: 6px 8px;
  color: #94a3b8;
  font-size: 14px;
  user-select: none;
`;

const HomeIcon = styled(Home)`
  flex-shrink: 0;
`;

const EmptyState = styled.div`
  color: #94a3b8;
  font-size: 14px;
  font-style: italic;
`;

export const FolderBreadcrumb: React.FC<FolderBreadcrumbProps> = ({
  maxDepth = 5,
  onFolderSelect,
}) => {
  const breadcrumbPath = useAtomValue(folderBreadcrumbAtom);
  const selectedFolderId = useAtomValue(selectedFolderIdAtom);
  const selectAndExpand = useSetAtom(selectAndExpandFolderAtom);

  const handleBreadcrumbClick = useCallback(
    (folderId: string | null) => {
      if (onFolderSelect) {
        onFolderSelect(folderId);
      } else {
        if (folderId) {
          selectAndExpand(folderId);
        } else {
          selectAndExpand(null);
        }
      }
    },
    [onFolderSelect, selectAndExpand]
  );

  // If no folder selected, show just root
  if (!selectedFolderId) {
    return (
      <BreadcrumbContainer>
        <BreadcrumbItem
          $isLast={true}
          onClick={() => handleBreadcrumbClick(null)}
        >
          <HomeIcon size={16} />
          Corpus Root
        </BreadcrumbItem>
      </BreadcrumbContainer>
    );
  }

  // If breadcrumb is empty but folder is selected, show loading state
  if (breadcrumbPath.length === 0) {
    return (
      <BreadcrumbContainer>
        <EmptyState>Loading path...</EmptyState>
      </BreadcrumbContainer>
    );
  }

  // Determine if we need to show ellipsis
  const needsEllipsis = breadcrumbPath.length > maxDepth;
  const visiblePath = needsEllipsis
    ? [
        breadcrumbPath[0], // Always show first folder
        ...breadcrumbPath.slice(-(maxDepth - 1)), // Show last N-1 folders
      ]
    : breadcrumbPath;

  return (
    <BreadcrumbContainer>
      {/* Corpus Root */}
      <BreadcrumbItem
        $isLast={false}
        onClick={() => handleBreadcrumbClick(null)}
      >
        <HomeIcon size={16} />
        Corpus Root
      </BreadcrumbItem>

      <BreadcrumbSeparator>
        <ChevronRight size={14} />
      </BreadcrumbSeparator>

      {/* Show first folder */}
      {needsEllipsis && (
        <>
          <BreadcrumbItem
            $isLast={false}
            onClick={() => handleBreadcrumbClick(visiblePath[0].id)}
            title={visiblePath[0].path}
          >
            {visiblePath[0].name}
          </BreadcrumbItem>

          <BreadcrumbSeparator>
            <ChevronRight size={14} />
          </BreadcrumbSeparator>

          {/* Ellipsis */}
          <Ellipsis
            title={`${breadcrumbPath.length - maxDepth + 1} folders hidden`}
          >
            ...
          </Ellipsis>

          <BreadcrumbSeparator>
            <ChevronRight size={14} />
          </BreadcrumbSeparator>
        </>
      )}

      {/* Show visible folders */}
      {(needsEllipsis ? visiblePath.slice(1) : visiblePath).map(
        (folder, index, arr) => {
          const isLast = index === arr.length - 1;

          return (
            <React.Fragment key={folder.id}>
              <BreadcrumbItem
                $isLast={isLast}
                onClick={() => !isLast && handleBreadcrumbClick(folder.id)}
                title={folder.path}
              >
                {folder.name}
              </BreadcrumbItem>

              {!isLast && (
                <BreadcrumbSeparator>
                  <ChevronRight size={14} />
                </BreadcrumbSeparator>
              )}
            </React.Fragment>
          );
        }
      )}
    </BreadcrumbContainer>
  );
};
