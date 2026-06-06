import React, { useRef, useState, MouseEvent } from "react";
import _ from "lodash";
import styled, { keyframes } from "styled-components";
import {
  Check,
  AlertTriangle,
  FileText,
  Globe,
  Lock,
  BookOpen,
  Eye,
  Download,
  Loader2,
  Edit,
  XCircle,
  RotateCw,
} from "lucide-react";
import { Spinner } from "@os-legal/ui";
import { DynamicIcon } from "../widgets/icon-picker/DynamicIcon";
import { useNavigate } from "react-router-dom";
import { useMutation } from "@apollo/client";
import { toast } from "react-toastify";
import { navigateToDocument } from "../../utils/navigationUtils";

import {
  editingDocument,
  selectedDocumentIds,
  showAddDocsToCorpusModal,
  showDeleteDocumentsModal,
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
import { downloadFile } from "../../utils/files";
import fallback_doc_icon from "../../assets/images/defaults/default_doc_icon.jpg";
import { getPermissions } from "../../utils/transform";
import { PermissionTypes } from "../types";
import {
  FAILURE_COLORS,
  PDF_MIME_TYPE,
} from "../../assets/configurations/constants";
import { useLazyPdfUrl } from "./useLazyPdfUrl";
import { OS_LEGAL_COLORS } from "../../assets/configurations/osLegalStyles";

// Animations
const shimmer = keyframes`
  0% {
    background-position: -1000px 0;
  }
  100% {
    background-position: 1000px 0;
  }
`;

const spin = keyframes`
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
`;

const slideIn = keyframes`
  from {
    opacity: 0;
    transform: translateX(-20px);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
`;

// Corporate styled card container
const StyledCard = styled.div`
  position: relative;
  background: #ffffff;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 12px;
  overflow: visible;
  transition: all 0.2s ease;
  cursor: pointer;
  min-height: 280px;
  max-height: 360px;
  display: flex;
  flex-direction: column;
  width: 100%;
  box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px 0 rgba(0, 0, 0, 0.06);

  &:hover {
    transform: translateY(-4px);
    box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1),
      0 10px 10px -5px rgba(0, 0, 0, 0.04);
    border-color: ${OS_LEGAL_COLORS.borderHover};

    .card-header {
      &::after {
        opacity: 1;
      }
    }

    .action-bar {
      opacity: 1;
      transform: translateY(0);
    }

    img:not(.fallback-icon) {
      transform: translateY(5%);
    }
  }

  &.is-selected {
    border-color: ${OS_LEGAL_COLORS.primaryBlue};
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1),
      0 10px 15px -3px rgba(0, 0, 0, 0.1);
  }

  &.is-open {
    border-color: #f59e0b;
    background: #fffbeb;
  }

  &.backend-locked {
    pointer-events: none;
    opacity: 0.6;
    background: ${OS_LEGAL_COLORS.gray50};
  }

  &.failed {
    border-color: ${FAILURE_COLORS.BORDER_LIGHT};
  }
`;

// Clean card header
const CardHeader = styled.div`
  position: relative;
  height: 140px;
  background: ${OS_LEGAL_COLORS.surfaceHover};
  border-radius: 12px 12px 0 0;
  overflow: hidden;
  border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
  transition: background 0.2s ease;

  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    object-position: top center;
    transition: transform 0.3s ease;
  }

  .fallback-icon {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    width: 50px;
    height: 50px;
    opacity: 0.2;
    object-fit: contain;
  }

  &::after {
    content: "";
    position: absolute;
    inset: 0;
    background: linear-gradient(
      180deg,
      transparent 0%,
      rgba(0, 0, 0, 0.1) 100%
    );
    opacity: 0.5;
    transition: opacity 0.2s ease;
    pointer-events: none;
  }
`;

// Content section
const ContentSection = styled.div`
  flex: 1;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  position: relative;
  min-height: 0;
  overflow: hidden;
`;

// Typography
const Title = styled.h3`
  margin: 0;
  font-size: 0.9375rem;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textPrimary};
  line-height: 1.4;
  letter-spacing: -0.01em;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  text-overflow: ellipsis;
`;

const Description = styled.p`
  margin: 0;
  font-size: 0.8125rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  text-overflow: ellipsis;
`;

// Metadata section
const MetadataSection = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: auto;
  padding-top: 8px;
`;

const MetaPill = styled.div`
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 3px 8px;
  background: ${OS_LEGAL_COLORS.surfaceLight};
  border-radius: 4px;
  font-size: 0.6875rem;
  font-weight: 500;
  color: ${OS_LEGAL_COLORS.textTertiary};
  transition: background 0.15s ease;

  .icon {
    opacity: 0.8;
    font-size: 0.7rem;
  }

  &:hover {
    background: ${OS_LEGAL_COLORS.border};
  }

  &.success {
    background: #dcfce7;
    color: ${OS_LEGAL_COLORS.successHover};
  }

  &.warning {
    background: #fed7aa;
    color: #c2410c;
  }
`;

// Action bar
const ActionBar = styled.div`
  position: absolute;
  bottom: 12px;
  right: 12px;
  display: flex;
  gap: 4px;
  opacity: 0;
  transform: translateY(8px);
  transition: all 0.2s ease;
`;

const ActionButton = styled.button`
  width: 32px;
  height: 32px;
  border-radius: 6px;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  background: white;
  box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s ease;
  color: ${OS_LEGAL_COLORS.textSecondary};
  position: relative;

  &:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    border-color: ${OS_LEGAL_COLORS.borderHover};
    color: ${OS_LEGAL_COLORS.textTertiary};
  }

  &:active {
    transform: scale(0.98);
  }

  &.primary {
    background: ${OS_LEGAL_COLORS.primaryBlue};
    border-color: ${OS_LEGAL_COLORS.primaryBlue};
    color: white;

    &:hover {
      background: ${OS_LEGAL_COLORS.primaryBlueHover};
      border-color: ${OS_LEGAL_COLORS.primaryBlueHover};
    }
  }

  &.danger:hover {
    background: ${OS_LEGAL_COLORS.danger};
    border-color: ${OS_LEGAL_COLORS.danger};
    color: white;
  }

  &.success:hover {
    background: ${OS_LEGAL_COLORS.greenMedium};
    border-color: ${OS_LEGAL_COLORS.greenMedium};
    color: white;
  }

  &.downloading {
    background: ${OS_LEGAL_COLORS.primaryBlue};
    border-color: ${OS_LEGAL_COLORS.primaryBlue};
    color: white;
    animation: pulse 1.5s ease-in-out infinite;

    @keyframes pulse {
      0%,
      100% {
        opacity: 1;
      }
      50% {
        opacity: 0.8;
      }
    }
  }

  .icon {
    margin: 0 !important;
    font-size: 13px;

    &.loading {
      animation: ${spin} 1s linear infinite;
    }
  }
`;

// Selection checkbox
const SelectionControl = styled.div`
  position: absolute;
  top: 12px;
  left: 12px;
  width: 20px;
  height: 20px;
  border-radius: 4px;
  background: white;
  border: 2px solid ${OS_LEGAL_COLORS.borderHover};
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.15s ease;
  z-index: 10;

  &:hover {
    border-color: ${OS_LEGAL_COLORS.primaryBlue};
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
  }

  &.selected {
    background: ${OS_LEGAL_COLORS.primaryBlue};
    border-color: ${OS_LEGAL_COLORS.primaryBlue};

    .icon {
      color: white;
      font-size: 0.75rem;
    }
  }
`;

// File type badge
const FileTypeBadge = styled.div`
  position: absolute;
  top: 12px;
  right: 12px;
  padding: 3px 8px;
  background: ${OS_LEGAL_COLORS.textPrimary};
  color: white;
  border-radius: 4px;
  font-size: 0.625rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
`;

// Tags container
const TagsContainer = styled.div`
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
`;

const Tag = styled.span`
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 3px 8px;
  background: ${OS_LEGAL_COLORS.surfaceHover};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 4px;
  font-size: 0.7rem;
  font-weight: 500;
  color: ${OS_LEGAL_COLORS.textTertiary};

  .icon {
    font-size: 0.65rem;
  }
`;

// ===============================================
// PROCESSING FAILURE COMPONENTS
// ===============================================
const ThumbnailFailureOverlay = styled.div`
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: ${FAILURE_COLORS.BG_OVERLAY};
  z-index: 5;
  border-radius: inherit;
`;

const FailureIconCircle = styled.div`
  width: 44px;
  height: 44px;
  border-radius: 50%;
  background: ${FAILURE_COLORS.ICON_BG};
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  box-shadow: 0 2px 8px ${FAILURE_COLORS.SHADOW};

  .icon {
    margin: 0 !important;
    font-size: 20px;
  }
`;

const FailureBadge = styled.div`
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  background: ${FAILURE_COLORS.BG};
  color: ${FAILURE_COLORS.TEXT};
  border: 1px solid ${FAILURE_COLORS.BORDER_LIGHTER};
  border-radius: 4px;
  font-size: 0.6875rem;
  font-weight: 600;
  letter-spacing: 0.02em;
`;

const FailureDescription = styled.div`
  font-size: 0.75rem;
  color: ${FAILURE_COLORS.TEXT_DARK};
  line-height: 1.3;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
`;

const ClassicRetryButton = styled.button`
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 16px;
  border: 1px solid ${FAILURE_COLORS.BORDER};
  border-radius: 6px;
  background: white;
  color: ${FAILURE_COLORS.TEXT};
  font-size: 0.75rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s ease;

  &:hover {
    background: ${FAILURE_COLORS.BORDER};
    color: white;
  }

  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
`;

interface DocumentItemProps {
  item: DocumentType;
  delete_caption?: string;
  download_caption?: string;
  edit_caption?: string;
  add_caption?: string;
  contextMenuOpen: string | null;
  onShiftClick?: (document: DocumentType) => void;
  onClick?: (document: DocumentType) => void;
  removeFromCorpus?: (doc_ids: string[]) => void | any;
  setContextMenuOpen: (args: any) => any | void;
}

export const DocumentItem: React.FC<DocumentItemProps> = ({
  item,
  add_caption = "Add to Corpus",
  edit_caption = "Edit",
  delete_caption = "Delete",
  download_caption = "Download",
  contextMenuOpen,
  onShiftClick,
  onClick,
  removeFromCorpus,
  setContextMenuOpen,
}) => {
  const navigate = useNavigate();
  const [isHovered, setIsHovered] = useState(false);
  const [isDownloading, setIsDownloading] = useState(false);

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

  const {
    id,
    icon,
    is_open,
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
  } = item;

  const isFailed = processingStatus === DocumentProcessingStatus.FAILED;
  const isProcessing =
    processingStatus != null &&
    processingStatus !== DocumentProcessingStatus.FAILED &&
    backendLock;

  const handleRetry = async (e: React.MouseEvent) => {
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
  };

  const cardClickHandler = (event: React.MouseEvent<HTMLDivElement>) => {
    if (
      (event.target as HTMLElement).closest(".action-button") ||
      (event.target as HTMLElement).closest(".selection-control")
    ) {
      return;
    }

    if (isFailed) {
      return;
    }

    event.stopPropagation();
    if (event.shiftKey) {
      if (onShiftClick && _.isFunction(onShiftClick)) {
        onShiftClick(item);
      }
    } else {
      if (onClick && _.isFunction(onClick)) {
        onClick(item);
      }
    }
  };

  const handleCheckboxClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (onShiftClick) {
      onShiftClick(item);
    }
  };

  const handleOpenKnowledgeBase = (e: React.MouseEvent) => {
    e.stopPropagation();
    const currentCorpus = openedCorpus();
    navigateToDocument(
      item as any,
      currentCorpus as any,
      navigate,
      window.location.pathname
    );
    if (onClick) onClick(item);
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
  // signed URL on demand, falling back to an in-hand ``pdfFile`` when a
  // caller's query still provides one.
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
    if (removeFromCorpus) {
      removeFromCorpus([item.id]);
    }
  };

  const my_permissions = getPermissions(
    item.myPermissions ? item.myPermissions : []
  );

  const canEdit = my_permissions.includes(PermissionTypes.CAN_UPDATE);
  const canDelete = my_permissions.includes(PermissionTypes.CAN_REMOVE);

  let doc_label_objs = item?.docTypeLabels
    ? item.docTypeLabels.filter((lbl): lbl is AnnotationLabelType => !!lbl)
    : [];

  return (
    <StyledCard
      className={`noselect ${is_open ? "is-open" : ""} ${
        is_selected ? "is-selected" : ""
      } ${isProcessing ? "backend-locked" : ""} ${isFailed ? "failed" : ""}`}
      onClick={isProcessing ? undefined : cardClickHandler}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      {isProcessing && (
        <div
          style={{
            position: "absolute",
            inset: 0,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            background: "rgba(255,255,255,0.85)",
            borderRadius: "12px",
            zIndex: 20,
          }}
        >
          <Spinner size="sm" />
          <span
            style={{
              marginTop: "0.5rem",
              fontSize: "0.8rem",
              color: OS_LEGAL_COLORS.textSecondary,
            }}
          >
            Processing...
          </span>
        </div>
      )}

      <SelectionControl
        className={`selection-control ${is_selected ? "selected" : ""}`}
        onClick={handleCheckboxClick}
      >
        {is_selected && <Check size={12} color="white" />}
      </SelectionControl>

      <CardHeader className="card-header">
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
              className="fallback-icon"
            />
          </>
        )}
        {isFailed && (
          <ThumbnailFailureOverlay role="alert" aria-label="Processing failed">
            <FailureIconCircle aria-hidden="true">
              <AlertTriangle size={20} />
            </FailureIconCircle>
          </ThumbnailFailureOverlay>
        )}
        {fileType && !isFailed && <FileTypeBadge>{fileType}</FileTypeBadge>}
      </CardHeader>

      <ContentSection>
        <Title>{title || "Untitled Document"}</Title>

        {isFailed ? (
          <FailureDescription>
            {processingError || "Document processing failed"}
          </FailureDescription>
        ) : (
          <Description>{description || "No description available"}</Description>
        )}

        <MetadataSection>
          {isFailed && <FailureBadge>Processing Failed</FailureBadge>}
          {pageCount && (
            <MetaPill>
              <FileText size={11} />
              {pageCount} pages
            </MetaPill>
          )}

          {isPublic && (
            <MetaPill className="success">
              <Globe size={11} />
              Public
            </MetaPill>
          )}

          {!canEdit && (
            <MetaPill className="warning">
              <Lock size={11} />
              Read-only
            </MetaPill>
          )}

          {doc_label_objs.length > 0 && (
            <TagsContainer>
              {doc_label_objs.slice(0, 2).map((label, index) => (
                <Tag key={`doc_${id}_label${index}`}>
                  <DynamicIcon
                    name={(label.icon as string) || "tag"}
                    size={11}
                    color={label.color || undefined}
                  />
                  {label.text}
                </Tag>
              ))}
            </TagsContainer>
          )}
        </MetadataSection>

        <ActionBar className="action-bar">
          <ActionButton
            className="action-button primary"
            onClick={handleOpenKnowledgeBase}
            disabled={backendLock}
            title="Open Knowledge Base"
          >
            <BookOpen size={13} />
          </ActionButton>

          <ActionButton
            className="action-button"
            onClick={handleView}
            disabled={backendLock}
            title="View Details"
          >
            <Eye size={13} />
          </ActionButton>

          {canDownload && (
            <ActionButton
              className={`action-button ${isDownloading ? "downloading" : ""}`}
              onClick={handleDownload}
              disabled={backendLock || isDownloading}
              title={isDownloading ? "Downloading..." : download_caption}
            >
              {isDownloading ? (
                <Loader2 size={13} className="loading" />
              ) : (
                <Download size={13} />
              )}
            </ActionButton>
          )}

          {canEdit && !backendLock && (
            <ActionButton
              className="action-button"
              onClick={handleEdit}
              title={edit_caption}
            >
              <Edit size={13} />
            </ActionButton>
          )}

          {removeFromCorpus && !backendLock && (
            <ActionButton
              className="action-button danger"
              onClick={handleRemoveFromCorpus}
              title="Remove from Corpus"
            >
              <XCircle size={13} />
            </ActionButton>
          )}

          {isFailed && canRetry && (
            <ClassicRetryButton
              onClick={handleRetry}
              disabled={retryLoading}
              aria-label="Retry processing this document"
            >
              <RotateCw size={13} aria-hidden="true" />
              {retryLoading ? "Retrying..." : "Retry"}
            </ClassicRetryButton>
          )}
        </ActionBar>
      </ContentSection>
    </StyledCard>
  );
};
