import React, { useState, useRef, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useDraggable, useDroppable } from "@dnd-kit/core";
import { CSS } from "@dnd-kit/utilities";
import {
  Link2,
  FileText,
  RotateCcw,
  BookOpen,
  Eye,
  Download,
  Loader2,
  Edit,
  Trash2,
  Check,
  AlertTriangle,
  Globe,
  Tag,
  GitBranch,
  X,
} from "lucide-react";
import { useMutation, useLazyQuery, useReactiveVar } from "@apollo/client";
import { toast } from "react-toastify";
import { navigateToDocument } from "../../utils/navigationUtils";
import { LoadingOverlay } from "../common/LoadingOverlay";
import { OS_LEGAL_COLORS } from "../../assets/configurations/osLegalStyles";

import {
  editingDocument,
  viewingDocument,
  openedCorpus,
} from "../../graphql/cache";
import {
  AnnotationLabelType,
  DocumentType,
  DocumentProcessingStatus,
} from "../../types/graphql-api";
import {
  RETRY_DOCUMENT_PROCESSING,
  RetryDocumentProcessingOutputType,
  RetryDocumentProcessingInputType,
} from "../../graphql/mutations";
import {
  GET_DOC_RELATIONSHIPS_FOR_DOC,
  GetDocRelationshipsForDocInputs,
  GetDocRelationshipsForDocOutputs,
} from "../../graphql/queries";
import { downloadFile } from "../../utils/files";
import { PDF_MIME_TYPE } from "../../assets/configurations/constants";
import { useLazyPdfUrl } from "./useLazyPdfUrl";
import fallback_doc_icon from "../../assets/images/defaults/default_doc_icon.jpg";
import { getPermissions } from "../../utils/transform";
import { PermissionTypes } from "../types";
import { ModernContextMenu, ContextMenuItem } from "./ModernContextMenu";
import { VersionBadge } from "./VersionBadge";
import { VersionHistoryPanel } from "./VersionHistoryPanel";
import { DocumentRelationshipList } from "./DocumentRelationshipList";
import {
  ActionButton,
  ActionOverlay,
  CardCheckbox,
  CardContainer,
  CardContent,
  CardMeta,
  CardPreview,
  CardTitle,
  FailureBadge,
  FailureDescription,
  FailureIconCircle,
  FileTypeBadge,
  ListActions,
  ListCheckbox,
  ListContainer,
  ListContent,
  ListDescription,
  ListMeta,
  ListRelationshipBadge,
  ListRelationshipPopup,
  ListThumbnail,
  ListTitle,
  ProcessingDeleteButton,
  RelationshipBadge,
  RelationshipBadgeContainer,
  RelationshipPopup,
  RetryButton,
  ThumbnailFailureOverlay,
  VersionBadgeWrapper,
} from "./ModernDocumentItem.styles";

interface ModernDocumentItemProps {
  item: DocumentType;
  viewMode: "card" | "list";
  onShiftClick?: (document: DocumentType) => void;
  onClick?: (document: DocumentType) => void;
  removeFromCorpus?: (doc_ids: string[]) => void;
  /** Callback when user wants to link this document to another */
  onLinkToDocument?: (document: DocumentType) => void;
  /** Callback when a document is dropped onto this document (for creating relationships) */
  onDocumentDrop?: (sourceDocId: string, targetDocId: string) => void;
}

export const ModernDocumentItem: React.FC<ModernDocumentItemProps> = ({
  item,
  viewMode,
  onShiftClick,
  onClick,
  removeFromCorpus,
  onLinkToDocument,
  onDocumentDrop,
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

  const [retryProcessing, { loading: retryLoading }] = useMutation<
    RetryDocumentProcessingOutputType,
    RetryDocumentProcessingInputType
  >(RETRY_DOCUMENT_PROCESSING, {
    update: (cache, { data }) => {
      if (data?.retryDocumentProcessing?.ok) {
        // Optimistically set processing state — the Celery task updates the DB
        // asynchronously, so the mutation response still has the old values.
        cache.modify({
          id: cache.identify({ __typename: "DocumentType", id }),
          fields: {
            backendLock: () => true,
            processingStatus: () => "PENDING",
            processingError: () => null,
            canRetry: () => false,
          },
        });
      }
    },
  });

  // Draggable setup (documents can be dragged to folders)
  const {
    attributes,
    listeners,
    setNodeRef: setDraggableRef,
    transform,
    isDragging,
  } = useDraggable({
    id: `document-${item.id}`,
    data: {
      type: "document",
      documentId: item.id,
    },
  });

  // Droppable setup (documents can receive other documents for linking)
  const {
    setNodeRef: setDroppableRef,
    isOver,
    active,
  } = useDroppable({
    id: `document-drop-${item.id}`,
    data: {
      type: "document-drop-target",
      documentId: item.id,
    },
  });

  // Check if the active dragged item is a document (not a folder)
  const isDocumentDragOver =
    isOver && active?.data?.current?.type === "document";

  // Combine draggable and droppable refs
  const setNodeRef = (node: HTMLElement | null) => {
    setDraggableRef(node);
    setDroppableRef(node);
  };

  // Apply transform for drag preview + drop target highlight
  const style = transform
    ? {
        transform: CSS.Translate.toString(transform),
        opacity: isDragging ? 0.5 : 1,
      }
    : isDocumentDragOver
    ? {
        outline: `2px dashed ${OS_LEGAL_COLORS.primaryBlue}`,
        outlineOffset: "2px",
        background: OS_LEGAL_COLORS.blueSurface,
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
    processingStatus,
    processingError,
    canRetry,
    isPublic,
    myPermissions,
    fileType,
    pageCount,
    // Version metadata fields
    hasVersionHistory,
    versionCount,
    isLatestVersion,
    canViewHistory,
    // Relationship data
    docRelationshipCount,
  } = item;

  // Relationships are fetched lazily the first time the user hovers the
  // relationship badge. This keeps the document-list query cheap on corpora
  // with many documents.
  const [
    fetchDocRelationships,
    {
      data: relationshipsData,
      loading: relationshipsLoading,
      error: relationshipsError,
    },
  ] = useLazyQuery<
    GetDocRelationshipsForDocOutputs,
    GetDocRelationshipsForDocInputs
  >(GET_DOC_RELATIONSHIPS_FOR_DOC, { fetchPolicy: "cache-first" });

  const allDocRelationships = relationshipsData?.bulkDocRelationships;

  // Subscribe to the reactive var so this component re-renders when the
  // corpus changes — calling ``openedCorpus()`` directly would only sample
  // the value at render time and leave a stale ``corpusId`` baked into the
  // useCallback below until something else triggered a re-render.
  const currentOpenedCorpus = useReactiveVar(openedCorpus);
  const corpusIdForRelationships = currentOpenedCorpus?.id ?? null;
  const handleRelationshipHover = useCallback(() => {
    // Bail when count is zero, when the data has already loaded, when a
    // fetch is in-flight, OR when the previous attempt errored out — without
    // the error guard the popup falls through to the "Loading..." fallback
    // forever AND every subsequent hover retriggers the failing fetch.
    if (
      !docRelationshipCount ||
      relationshipsData ||
      relationshipsLoading ||
      relationshipsError
    ) {
      return;
    }
    fetchDocRelationships({
      variables: { documentId: id, corpusId: corpusIdForRelationships },
    });
  }, [
    docRelationshipCount,
    relationshipsData,
    relationshipsLoading,
    relationshipsError,
    fetchDocRelationships,
    id,
    corpusIdForRelationships,
  ]);

  const isFailed = processingStatus === DocumentProcessingStatus.FAILED;
  const isProcessing =
    processingStatus != null &&
    processingStatus !== DocumentProcessingStatus.FAILED &&
    backendLock;

  const handleRetry = useCallback(
    async (e: React.MouseEvent) => {
      e.stopPropagation();
      try {
        const result = await retryProcessing({
          variables: { documentId: id },
        });
        if (result.data?.retryDocumentProcessing?.ok) {
          toast.success("Document reprocessing has been queued");
        } else {
          toast.error(
            result.data?.retryDocumentProcessing?.message ||
              "Failed to retry processing"
          );
        }
      } catch (err) {
        console.error("Failed to retry document processing:", err);
        toast.error("Failed to retry document processing");
      }
    },
    [id, retryProcessing]
  );

  const handleClick = (event: React.MouseEvent) => {
    if (
      (event.target as HTMLElement).closest(".action-button") ||
      (event.target as HTMLElement).closest(".checkbox")
    ) {
      return;
    }

    if (isFailed) {
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

  // ``pdfFile`` is no longer fetched per card (see GET_DOCUMENTS); resolve the
  // signed URL on demand. Falls back to an in-hand ``pdfFile`` when a caller's
  // query still provides one.
  const resolvePdfUrl = useLazyPdfUrl();
  const canDownload = !!pdfFile || fileType === PDF_MIME_TYPE;

  const handleDownload = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (isDownloading || !canDownload) return;
    setIsDownloading(true);
    try {
      const url = await resolvePdfUrl(id, pdfFile);
      if (url) {
        await downloadFile(url);
      } else {
        // The card shows the download button for any PDF-typed document, but
        // the signed URL is resolved lazily — surface a toast instead of a
        // silent no-op when no downloadable file is available.
        toast.error("No downloadable file is available for this document.");
      }
    } catch {
      toast.error("Could not download the document. Please try again.");
    } finally {
      setTimeout(() => setIsDownloading(false), 1000);
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

  // Build context menu items. Order: primary action (Open) → view/download/edit
  // → linking/versioning → retry (failed only) → destructive (remove) → select.
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

  if (canDownload) {
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

  // Add link to document option if handler provided
  if (onLinkToDocument) {
    contextMenuItems.push({
      label: "Link to Document...",
      icon: "linkify",
      onClick: (e) => {
        e.stopPropagation();
        onLinkToDocument(item);
      },
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

  if (isFailed && canRetry) {
    contextMenuItems.push({
      label: retryLoading ? "Retrying..." : "Retry Processing",
      icon: "redo",
      onClick: handleRetry,
      disabled: retryLoading,
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

  const doc_label_objs = item?.docTypeLabels
    ? item.docTypeLabels.filter((lbl): lbl is AnnotationLabelType => !!lbl)
    : [];

  const renderThumbnail = (className?: string) => (
    <>
      {icon ? (
        <img src={icon} alt={title || "Document"} />
      ) : (
        <>
          <div
            style={{
              width: "100%",
              height: "100%",
              background: OS_LEGAL_COLORS.surfaceHover,
            }}
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
        <BookOpen size={14} />
      </ActionButton>

      {!inOverlay && (
        <>
          <ActionButton
            className="action-button"
            onClick={handleView}
            disabled={backendLock}
            title="View"
          >
            <Eye size={14} />
          </ActionButton>

          {canDownload && (
            <ActionButton
              className="action-button"
              onClick={handleDownload}
              disabled={backendLock || isDownloading}
              title="Download"
            >
              {isDownloading ? (
                <Loader2 size={14} className="loading" />
              ) : (
                <Download size={14} />
              )}
            </ActionButton>
          )}

          {canEdit && (
            <ActionButton
              className="action-button"
              onClick={handleEdit}
              disabled={backendLock}
              title="Edit"
            >
              <Edit size={14} />
            </ActionButton>
          )}

          {removeFromCorpus && (
            <ActionButton
              className="action-button"
              onClick={handleRemoveFromCorpus}
              disabled={backendLock}
              title="Remove"
            >
              <Trash2 size={14} />
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
          data-testid="document-card"
          className={`${is_selected ? "is-selected" : ""} ${
            isProcessing ? "backend-locked" : ""
          } ${isFailed ? "failed" : ""} ${
            isLongPressing ? "long-pressing" : ""
          }`}
          onClick={handleClick}
          onContextMenu={handleContextMenu}
          onTouchStart={handleTouchStart}
          onTouchMove={handleTouchMove}
          onTouchEnd={handleTouchEnd}
          style={style}
          {...attributes}
          {...listeners}
        >
          {isProcessing && (
            <LoadingOverlay
              active={true}
              inverted
              size="small"
              content="Processing..."
            />
          )}

          {isProcessing && removeFromCorpus && (
            <ProcessingDeleteButton
              onClick={handleRemoveFromCorpus}
              title="Remove processing document"
              aria-label="Remove processing document from corpus"
            >
              <X />
            </ProcessingDeleteButton>
          )}

          <CardCheckbox
            className={`checkbox ${is_selected ? "selected" : ""}`}
            onClick={handleCheckboxClick}
          >
            {is_selected && <Check size={12} />}
          </CardCheckbox>

          <CardPreview>
            {renderThumbnail()}
            {isFailed && (
              <ThumbnailFailureOverlay
                role="alert"
                aria-label="Processing failed"
              >
                <FailureIconCircle $size="large" aria-hidden="true">
                  <AlertTriangle size={16} />
                </FailureIconCircle>
              </ThumbnailFailureOverlay>
            )}
            {fileType && !isFailed && <FileTypeBadge>{fileType}</FileTypeBadge>}
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
            {!!docRelationshipCount && docRelationshipCount > 0 && (
              <RelationshipBadgeContainer
                onClick={(e) => {
                  e.stopPropagation();
                  // Cover touch devices: onMouseEnter doesn't fire on tap.
                  handleRelationshipHover();
                }}
                onMouseEnter={handleRelationshipHover}
                onFocus={handleRelationshipHover}
              >
                <RelationshipBadge>
                  <Link2 />
                  {docRelationshipCount}
                </RelationshipBadge>
                <RelationshipPopup>
                  <DocumentRelationshipList
                    documentId={id}
                    relationshipCount={docRelationshipCount}
                    relationships={allDocRelationships}
                    error={relationshipsError}
                  />
                </RelationshipPopup>
              </RelationshipBadgeContainer>
            )}
          </CardPreview>

          <CardContent>
            <CardTitle>{title || "Untitled Document"}</CardTitle>

            {isFailed ? (
              <CardMeta>
                <FailureBadge>Processing Failed</FailureBadge>
                {canRetry && (
                  <RetryButton
                    className="action-button"
                    onClick={handleRetry}
                    disabled={retryLoading}
                    aria-label="Retry processing this document"
                  >
                    <RotateCcw aria-hidden="true" />
                    {retryLoading ? "Retrying..." : "Retry"}
                  </RetryButton>
                )}
              </CardMeta>
            ) : (
              <CardMeta>
                {pageCount && (
                  <div className="meta-item">
                    <FileText size={12} />
                    {pageCount}p
                  </div>
                )}
                {isPublic && (
                  <div className="meta-item">
                    <Globe size={12} />
                    Public
                  </div>
                )}
                {doc_label_objs.length > 0 && (
                  <div className="meta-item">
                    <Tag size={12} />
                    {doc_label_objs.length}
                  </div>
                )}
              </CardMeta>
            )}
          </CardContent>

          {!isFailed && (
            <ActionOverlay className="action-overlay">
              {renderActions(true)}
            </ActionOverlay>
          )}
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
          onDownload={(_versionId) => {
            // Version download not yet implemented — requires a backend
            // endpoint that serves the file for a specific DocumentVersion.
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
        data-testid="document-card"
        className={`${is_selected ? "is-selected" : ""} ${
          isProcessing ? "backend-locked" : ""
        } ${isFailed ? "failed" : ""} ${isLongPressing ? "long-pressing" : ""}`}
        onClick={handleClick}
        onContextMenu={handleContextMenu}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
        style={style}
        {...attributes}
        {...listeners}
      >
        {isProcessing && (
          <LoadingOverlay
            active={true}
            inverted
            size="small"
            content="Processing..."
          />
        )}

        {isProcessing && removeFromCorpus && (
          <ProcessingDeleteButton
            onClick={handleRemoveFromCorpus}
            title="Remove processing document"
            aria-label="Remove processing document from corpus"
          >
            <X />
          </ProcessingDeleteButton>
        )}

        <ListCheckbox
          className={`checkbox ${is_selected ? "selected" : ""}`}
          onClick={handleCheckboxClick}
        >
          {is_selected && <Check size={12} />}
        </ListCheckbox>

        <ListThumbnail>
          {renderThumbnail()}
          {isFailed && (
            <ThumbnailFailureOverlay>
              <FailureIconCircle $size="small" aria-hidden="true">
                <AlertTriangle size={16} />
              </FailureIconCircle>
            </ThumbnailFailureOverlay>
          )}
        </ListThumbnail>

        <ListContent>
          <ListTitle>{title || "Untitled Document"}</ListTitle>
          {isFailed ? (
            <FailureDescription>
              {processingError || "Document processing failed"}
            </FailureDescription>
          ) : (
            description && <ListDescription>{description}</ListDescription>
          )}
          <ListMeta>
            {isFailed && <FailureBadge>Failed</FailureBadge>}
            {fileType && (
              <div className="meta-item">{fileType.toUpperCase()}</div>
            )}
            {pageCount && <div className="meta-item">{pageCount} pages</div>}
            {isPublic && (
              <div className="meta-item">
                <Globe size={12} />
                Public
              </div>
            )}
            {(hasVersionHistory || (versionCount && versionCount > 1)) && (
              <div
                className="meta-item"
                style={{
                  cursor: hasVersionHistory ? "pointer" : "default",
                  color:
                    isLatestVersion === false
                      ? "#c2410c"
                      : OS_LEGAL_COLORS.primaryBlueHover,
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
                <GitBranch size={12} />v{versionCount || 1}
                {hasVersionHistory && ` (${versionCount} versions)`}
              </div>
            )}
            {!!docRelationshipCount && docRelationshipCount > 0 && (
              <ListRelationshipBadge
                onClick={(e) => {
                  e.stopPropagation();
                  // Cover touch devices: onMouseEnter doesn't fire on tap.
                  handleRelationshipHover();
                }}
                onMouseEnter={handleRelationshipHover}
                onFocus={handleRelationshipHover}
              >
                <Link2 />
                {docRelationshipCount}
                <ListRelationshipPopup>
                  <DocumentRelationshipList
                    documentId={id}
                    relationshipCount={docRelationshipCount}
                    relationships={allDocRelationships}
                    error={relationshipsError}
                  />
                </ListRelationshipPopup>
              </ListRelationshipBadge>
            )}
          </ListMeta>
        </ListContent>

        <ListActions>
          {isFailed && canRetry ? (
            <RetryButton
              onClick={handleRetry}
              disabled={retryLoading}
              aria-label="Retry processing this document"
            >
              <RotateCcw aria-hidden="true" />
              {retryLoading ? "Retrying..." : "Retry"}
            </RetryButton>
          ) : !isFailed ? (
            renderActions()
          ) : null}
        </ListActions>
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
        onDownload={(_versionId) => {
          // Version download not yet implemented — requires a backend
          // endpoint that serves the file for a specific DocumentVersion.
        }}
      />
    </>
  );
};
