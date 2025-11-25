import React, { useState, useRef, useEffect } from "react";
import { Icon } from "semantic-ui-react";
import styled, { keyframes } from "styled-components";
import { useNavigate } from "react-router-dom";
import { useDraggable } from "@dnd-kit/core";
import { CSS } from "@dnd-kit/utilities";
import { navigateToDocument } from "../../utils/navigationUtils";
import { LoadingOverlay } from "../common/LoadingOverlay";

import {
  editingDocument,
  viewingDocument,
  openedCorpus,
} from "../../graphql/cache";
import { AnnotationLabelType, DocumentType } from "../../types/graphql-api";
import { downloadFile } from "../../utils/files";
import fallback_doc_icon from "../../assets/images/defaults/default_doc_icon.jpg";
import { getPermissions } from "../../utils/transform";
import { PermissionTypes } from "../types";
import { ModernContextMenu, ContextMenuItem } from "./ModernContextMenu";
import { VersionBadge } from "./VersionBadge";
import { VersionHistoryPanel } from "./VersionHistoryPanel";

const spin = keyframes`
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
`;

// ===============================================
// CARD VIEW (Desktop)
// ===============================================
const CardContainer = styled.div<{ isLongPressing?: boolean }>`
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

  &:hover {
    border-color: #cbd5e1;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
    transform: translateY(-2px);

    .action-overlay {
      opacity: 1;
    }
  }

  &.is-selected {
    border-color: #3b82f6;
    box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
  }

  &.backend-locked {
    pointer-events: none;
    opacity: 0.6;
  }

  &.long-pressing {
    transform: scale(0.98);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.12);
    border-color: #94a3b8;
  }
`;

const CardPreview = styled.div`
  position: relative;
  height: 90px;
  background: #f8fafc;
  overflow: hidden;

  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .fallback-icon {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    width: 32px;
    height: 32px;
    opacity: 0.15;
  }
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
  font-size: 0.875rem;
  font-weight: 600;
  color: #0f172a;
  line-height: 1.3;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
`;

const CardMeta = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.75rem;
  color: #64748b;
  margin-top: auto;

  .meta-item {
    display: flex;
    align-items: center;
    gap: 3px;
  }
`;

const ActionOverlay = styled.div`
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  padding: 8px;
  background: linear-gradient(to top, rgba(0, 0, 0, 0.7), transparent);
  display: flex;
  gap: 4px;
  justify-content: flex-end;
  opacity: 0;
  transition: opacity 0.2s ease;
`;

const CardCheckbox = styled.div`
  position: absolute;
  top: 8px;
  left: 8px;
  width: 20px;
  height: 20px;
  border-radius: 4px;
  background: white;
  border: 2px solid #cbd5e1;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  z-index: 10;
  transition: all 0.15s ease;

  &:hover {
    border-color: #3b82f6;
  }

  &.selected {
    background: #3b82f6;
    border-color: #3b82f6;

    .icon {
      color: white;
      font-size: 0.7rem;
    }
  }
`;

const FileTypeBadge = styled.div`
  position: absolute;
  top: 8px;
  right: 8px;
  padding: 2px 6px;
  background: rgba(15, 23, 42, 0.8);
  backdrop-filter: blur(4px);
  color: white;
  border-radius: 3px;
  font-size: 0.625rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
`;

// Positioned version badge that doesn't conflict with FileTypeBadge
const VersionBadgeWrapper = styled.div`
  position: absolute;
  top: 8px;
  left: 32px; /* After the checkbox */

  /* Override the internal absolute positioning */
  > div {
    position: relative !important;
    top: auto !important;
    right: auto !important;
  }
`;

// ===============================================
// LIST VIEW (Mobile)
// ===============================================
const ListContainer = styled.div<{ isLongPressing?: boolean }>`
  position: relative;
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 12px;
  display: flex;
  gap: 12px;
  align-items: center;
  cursor: pointer;
  transition: all 0.2s ease;
  min-height: 80px;

  &:hover {
    border-color: #cbd5e1;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  }

  &.is-selected {
    border-color: #3b82f6;
    background: #eff6ff;
  }

  &.backend-locked {
    pointer-events: none;
    opacity: 0.6;
  }

  &.long-pressing {
    transform: scale(0.99);
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.1);
    border-color: #94a3b8;
    background: #f8fafc;
  }
`;

const ListThumbnail = styled.div`
  position: relative;
  width: 56px;
  height: 56px;
  flex-shrink: 0;
  border-radius: 6px;
  overflow: hidden;
  background: #f8fafc;
  border: 1px solid #e2e8f0;

  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .fallback-icon {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    width: 24px;
    height: 24px;
    opacity: 0.2;
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
  font-size: 0.875rem;
  font-weight: 600;
  color: #0f172a;
  line-height: 1.3;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
`;

const ListDescription = styled.div`
  font-size: 0.75rem;
  color: #64748b;
  line-height: 1.3;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
`;

const ListMeta = styled.div`
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.7rem;
  color: #94a3b8;

  .meta-item {
    display: flex;
    align-items: center;
    gap: 3px;
  }
`;

const ListActions = styled.div`
  display: flex;
  gap: 4px;
  flex-shrink: 0;
`;

const ListCheckbox = styled.div`
  width: 20px;
  height: 20px;
  flex-shrink: 0;
  border-radius: 4px;
  background: white;
  border: 2px solid #cbd5e1;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.15s ease;

  &:hover {
    border-color: #3b82f6;
  }

  &.selected {
    background: #3b82f6;
    border-color: #3b82f6;

    .icon {
      color: white;
      font-size: 0.7rem;
    }
  }
`;

// ===============================================
// SHARED COMPONENTS
// ===============================================
const ActionButton = styled.button`
  width: 28px;
  height: 28px;
  border-radius: 4px;
  border: none;
  background: rgba(255, 255, 255, 0.9);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.15s ease;
  color: #64748b;

  &:hover {
    background: white;
    color: #0f172a;
    transform: scale(1.05);
  }

  &:active {
    transform: scale(0.95);
  }

  &.primary {
    background: #3b82f6;
    color: white;

    &:hover {
      background: #2563eb;
    }
  }

  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .icon {
    margin: 0 !important;
    font-size: 12px;

    &.loading {
      animation: ${spin} 1s linear infinite;
    }
  }
`;

interface ModernDocumentItemProps {
  item: DocumentType;
  viewMode: "card" | "list";
  onShiftClick?: (document: DocumentType) => void;
  onClick?: (document: DocumentType) => void;
  removeFromCorpus?: (doc_ids: string[]) => void;
}

export const ModernDocumentItem: React.FC<ModernDocumentItemProps> = ({
  item,
  viewMode,
  onShiftClick,
  onClick,
  removeFromCorpus,
}) => {
  const navigate = useNavigate();
  const [isDownloading, setIsDownloading] = useState(false);
  const [contextMenu, setContextMenu] = useState<{
    x: number;
    y: number;
  } | null>(null);
  const [isLongPressing, setIsLongPressing] = useState(false);
  const [versionHistoryOpen, setVersionHistoryOpen] = useState(false);
  const longPressTimer = useRef<NodeJS.Timeout | null>(null);
  const longPressStartPos = useRef<{ x: number; y: number } | null>(null);

  // Draggable setup (documents can be dragged to folders)
  const { attributes, listeners, setNodeRef, transform, isDragging } =
    useDraggable({
      id: `document-${item.id}`,
      data: {
        type: "document",
        documentId: item.id,
      },
    });

  // Apply transform for drag preview
  const style = transform
    ? {
        transform: CSS.Translate.toString(transform),
        opacity: isDragging ? 0.5 : 1,
      }
    : undefined;

  const {
    id,
    icon,
    is_selected,
    title,
    description,
    pdfFile,
    backendLock,
    isPublic,
    myPermissions,
    fileType,
    pageCount,
    // Version metadata fields
    hasVersionHistory,
    versionCount,
    isLatestVersion,
    canViewHistory,
  } = item;

  const handleClick = (event: React.MouseEvent) => {
    if (
      (event.target as HTMLElement).closest(".action-button") ||
      (event.target as HTMLElement).closest(".checkbox")
    ) {
      return;
    }

    event.stopPropagation();
    if (event.shiftKey) {
      onShiftClick?.(item);
    } else {
      onClick?.(item);
    }
  };

  const handleCheckboxClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    onShiftClick?.(item);
  };

  const handleOpen = (e: React.MouseEvent) => {
    e.stopPropagation();
    const currentCorpus = openedCorpus();
    navigateToDocument(
      item as any,
      currentCorpus as any,
      navigate,
      window.location.pathname
    );
    onClick?.(item);
  };

  const handleView = (e: React.MouseEvent) => {
    e.stopPropagation();
    viewingDocument(item);
  };

  const handleEdit = (e: React.MouseEvent) => {
    e.stopPropagation();
    editingDocument(item);
  };

  const handleDownload = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (pdfFile && !isDownloading) {
      setIsDownloading(true);
      try {
        await downloadFile(pdfFile);
      } finally {
        setTimeout(() => setIsDownloading(false), 1000);
      }
    }
  };

  const handleRemoveFromCorpus = (e: React.MouseEvent) => {
    e.stopPropagation();
    removeFromCorpus?.([item.id]);
  };

  // Context menu handlers
  const handleContextMenu = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setContextMenu({ x: e.clientX, y: e.clientY });
  };

  // Long press handlers for mobile
  const handleTouchStart = (e: React.TouchEvent) => {
    const touch = e.touches[0];
    longPressStartPos.current = { x: touch.clientX, y: touch.clientY };
    setIsLongPressing(true);

    longPressTimer.current = setTimeout(() => {
      if (longPressStartPos.current) {
        setContextMenu({
          x: longPressStartPos.current.x,
          y: longPressStartPos.current.y,
        });
        setIsLongPressing(false);
        // Haptic feedback if available
        if (navigator.vibrate) {
          navigator.vibrate(50);
        }
      }
    }, 500); // 500ms long press
  };

  const handleTouchMove = (e: React.TouchEvent) => {
    // Cancel long press if finger moves too much
    if (longPressStartPos.current && longPressTimer.current) {
      const touch = e.touches[0];
      const deltaX = Math.abs(touch.clientX - longPressStartPos.current.x);
      const deltaY = Math.abs(touch.clientY - longPressStartPos.current.y);

      if (deltaX > 10 || deltaY > 10) {
        clearTimeout(longPressTimer.current);
        longPressTimer.current = null;
        longPressStartPos.current = null;
        setIsLongPressing(false);
      }
    }
  };

  const handleTouchEnd = () => {
    if (longPressTimer.current) {
      clearTimeout(longPressTimer.current);
      longPressTimer.current = null;
    }
    longPressStartPos.current = null;
    setIsLongPressing(false);
  };

  // Cleanup timer on unmount
  useEffect(() => {
    return () => {
      if (longPressTimer.current) {
        clearTimeout(longPressTimer.current);
      }
    };
  }, []);

  const my_permissions = getPermissions(myPermissions ?? []);
  const canEdit = my_permissions.includes(PermissionTypes.CAN_UPDATE);

  // Build context menu items
  const contextMenuItems: ContextMenuItem[] = [
    {
      label: "Open Document",
      icon: "book",
      onClick: handleOpen,
      variant: "primary",
      disabled: backendLock,
      dividerAfter: true,
    },
    {
      label: "View Details",
      icon: "eye",
      onClick: handleView,
      disabled: backendLock,
    },
  ];

  if (pdfFile) {
    contextMenuItems.push({
      label: isDownloading ? "Downloading..." : "Download PDF",
      icon: isDownloading ? "spinner" : "download",
      onClick: handleDownload,
      disabled: backendLock || isDownloading,
    });
  }

  if (canEdit) {
    contextMenuItems.push({
      label: "Edit Document",
      icon: "edit",
      onClick: handleEdit,
      disabled: backendLock,
    });
  }

  // Add version history option if document has history
  if (hasVersionHistory && canViewHistory) {
    contextMenuItems.push({
      label: "View Version History",
      icon: "code branch",
      onClick: (e) => {
        e.stopPropagation();
        setVersionHistoryOpen(true);
      },
      disabled: backendLock,
      dividerAfter: true,
    });
  }

  if (removeFromCorpus) {
    contextMenuItems.push({
      label: "Remove from Corpus",
      icon: "trash",
      onClick: handleRemoveFromCorpus,
      variant: "danger",
      disabled: backendLock,
      dividerAfter: contextMenuItems.length > 0,
    });
  }

  contextMenuItems.push({
    label: is_selected ? "Deselect" : "Select",
    icon: is_selected ? "check square outline" : "square outline",
    onClick: (e) => {
      e.stopPropagation();
      onShiftClick?.(item);
    },
  });

  const doc_label_objs =
    item?.docLabelAnnotations?.edges
      .map((edge) => edge?.node?.annotationLabel)
      .filter((lbl): lbl is AnnotationLabelType => !!lbl) ?? [];

  const renderThumbnail = (className?: string) => (
    <>
      {icon ? (
        <img src={icon} alt={title || "Document"} />
      ) : (
        <>
          <div
            style={{ width: "100%", height: "100%", background: "#f8fafc" }}
          />
          <img
            src={fallback_doc_icon}
            alt="Document"
            className={`fallback-icon ${className || ""}`}
          />
        </>
      )}
    </>
  );

  const renderActions = (inOverlay = false) => (
    <>
      <ActionButton
        className={`action-button ${inOverlay ? "primary" : ""}`}
        onClick={handleOpen}
        disabled={backendLock}
        title="Open"
      >
        <Icon name="book" />
      </ActionButton>

      {!inOverlay && (
        <>
          <ActionButton
            className="action-button"
            onClick={handleView}
            disabled={backendLock}
            title="View"
          >
            <Icon name="eye" />
          </ActionButton>

          {pdfFile && (
            <ActionButton
              className="action-button"
              onClick={handleDownload}
              disabled={backendLock || isDownloading}
              title="Download"
            >
              <Icon
                name={isDownloading ? "spinner" : "download"}
                className={isDownloading ? "loading" : ""}
              />
            </ActionButton>
          )}

          {canEdit && (
            <ActionButton
              className="action-button"
              onClick={handleEdit}
              disabled={backendLock}
              title="Edit"
            >
              <Icon name="edit" />
            </ActionButton>
          )}

          {removeFromCorpus && (
            <ActionButton
              className="action-button"
              onClick={handleRemoveFromCorpus}
              disabled={backendLock}
              title="Remove"
            >
              <Icon name="trash" />
            </ActionButton>
          )}
        </>
      )}
    </>
  );

  // CARD VIEW
  if (viewMode === "card") {
    return (
      <>
        <CardContainer
          ref={setNodeRef}
          className={`${is_selected ? "is-selected" : ""} ${
            backendLock ? "backend-locked" : ""
          } ${isLongPressing ? "long-pressing" : ""}`}
          onClick={handleClick}
          onContextMenu={handleContextMenu}
          onTouchStart={handleTouchStart}
          onTouchMove={handleTouchMove}
          onTouchEnd={handleTouchEnd}
          style={style}
          {...attributes}
          {...listeners}
        >
          {backendLock && (
            <LoadingOverlay
              active={true}
              inverted
              size="small"
              content="Processing..."
            />
          )}

          <CardCheckbox
            className={`checkbox ${is_selected ? "selected" : ""}`}
            onClick={handleCheckboxClick}
          >
            {is_selected && <Icon name="check" />}
          </CardCheckbox>

          <CardPreview>
            {renderThumbnail()}
            {fileType && <FileTypeBadge>{fileType}</FileTypeBadge>}
            {(hasVersionHistory || (versionCount && versionCount > 1)) && (
              <VersionBadgeWrapper>
                <VersionBadge
                  versionNumber={versionCount || 1}
                  hasHistory={hasVersionHistory ?? false}
                  isLatest={isLatestVersion ?? true}
                  versionCount={versionCount || 1}
                  onClick={() => setVersionHistoryOpen(true)}
                />
              </VersionBadgeWrapper>
            )}
          </CardPreview>

          <CardContent>
            <CardTitle>{title || "Untitled Document"}</CardTitle>

            <CardMeta>
              {pageCount && (
                <div className="meta-item">
                  <Icon name="file outline" />
                  {pageCount}p
                </div>
              )}
              {isPublic && (
                <div className="meta-item">
                  <Icon name="globe" />
                  Public
                </div>
              )}
              {doc_label_objs.length > 0 && (
                <div className="meta-item">
                  <Icon name="tag" />
                  {doc_label_objs.length}
                </div>
              )}
            </CardMeta>
          </CardContent>

          <ActionOverlay className="action-overlay">
            {renderActions(true)}
          </ActionOverlay>
        </CardContainer>

        {contextMenu && (
          <ModernContextMenu
            x={contextMenu.x}
            y={contextMenu.y}
            items={contextMenuItems}
            onClose={() => setContextMenu(null)}
            title={title || "Document Actions"}
          />
        )}

        <VersionHistoryPanel
          documentId={id}
          corpusId={openedCorpus()?.id || ""}
          documentTitle={title || "Document"}
          isOpen={versionHistoryOpen}
          onClose={() => setVersionHistoryOpen(false)}
          onDownload={(versionId) => {
            console.log("Download version", versionId);
            // TODO: Implement version download
          }}
        />
      </>
    );
  }

  // LIST VIEW
  return (
    <>
      <ListContainer
        ref={setNodeRef}
        className={`${is_selected ? "is-selected" : ""} ${
          backendLock ? "backend-locked" : ""
        } ${isLongPressing ? "long-pressing" : ""}`}
        onClick={handleClick}
        onContextMenu={handleContextMenu}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
        style={style}
        {...attributes}
        {...listeners}
      >
        {backendLock && (
          <LoadingOverlay
            active={true}
            inverted
            size="small"
            content="Processing..."
          />
        )}

        <ListCheckbox
          className={`checkbox ${is_selected ? "selected" : ""}`}
          onClick={handleCheckboxClick}
        >
          {is_selected && <Icon name="check" />}
        </ListCheckbox>

        <ListThumbnail>{renderThumbnail()}</ListThumbnail>

        <ListContent>
          <ListTitle>{title || "Untitled Document"}</ListTitle>
          {description && <ListDescription>{description}</ListDescription>}
          <ListMeta>
            {fileType && (
              <div className="meta-item">{fileType.toUpperCase()}</div>
            )}
            {pageCount && <div className="meta-item">{pageCount} pages</div>}
            {isPublic && (
              <div className="meta-item">
                <Icon name="globe" />
                Public
              </div>
            )}
            {(hasVersionHistory || (versionCount && versionCount > 1)) && (
              <div
                className="meta-item"
                style={{
                  cursor: hasVersionHistory ? "pointer" : "default",
                  color: isLatestVersion === false ? "#c2410c" : "#1d4ed8",
                }}
                onClick={
                  hasVersionHistory
                    ? (e) => {
                        e.stopPropagation();
                        setVersionHistoryOpen(true);
                      }
                    : undefined
                }
              >
                <Icon name="code branch" />v{versionCount || 1}
                {hasVersionHistory && ` (${versionCount} versions)`}
              </div>
            )}
          </ListMeta>
        </ListContent>

        <ListActions>{renderActions()}</ListActions>
      </ListContainer>

      {contextMenu && (
        <ModernContextMenu
          x={contextMenu.x}
          y={contextMenu.y}
          items={contextMenuItems}
          onClose={() => setContextMenu(null)}
          title={title || "Document Actions"}
        />
      )}

      <VersionHistoryPanel
        documentId={id}
        corpusId={openedCorpus()?.id || ""}
        documentTitle={title || "Document"}
        isOpen={versionHistoryOpen}
        onClose={() => setVersionHistoryOpen(false)}
        onDownload={(versionId) => {
          console.log("Download version", versionId);
          // TODO: Implement version download
        }}
      />
    </>
  );
};
