import { useState } from "react";
import { NetworkStatus } from "@apollo/client";
import { useDropzone } from "react-dropzone";
import styled from "styled-components";
import { OS_LEGAL_COLORS } from "../../assets/configurations/osLegalStyles";
import { FileText, Upload } from "lucide-react";
import { LoadingOverlay } from "../common/LoadingOverlay";

import { DocumentItem } from "./DocumentItem";
import { ModernDocumentItem } from "./ModernDocumentItem";
import { DocumentType, PageInfo } from "../../types/graphql-api";
import { FetchMoreOnVisible } from "../widgets/infinite_scroll/FetchMoreOnVisible";
import { FetchMoreFooter } from "../widgets/infinite_scroll/FetchMoreFooter";

const ResponsiveCardGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
  width: 100%;
  min-height: 100%;
  padding: 16px;
  align-content: start;
  background: transparent;

  @media (max-width: 640px) {
    grid-template-columns: 1fr;
    padding: 12px;
    gap: 12px;
  }

  @media (min-width: 641px) and (max-width: 900px) {
    grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
    padding: 14px;
    gap: 14px;
  }

  @media (min-width: 901px) and (max-width: 1200px) {
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  }

  @media (min-width: 1201px) and (max-width: 1600px) {
    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
    gap: 18px;
  }

  @media (min-width: 1601px) {
    grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
    gap: 20px;
  }
`;

const ModernCardGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 12px;
  width: 100%;
  min-height: 100%;
  padding: 16px;
  align-content: start;
  background: transparent;
  overflow: visible;

  @media (max-width: 640px) {
    grid-template-columns: 1fr;
    padding: 12px;
    gap: 10px;
  }

  @media (min-width: 641px) and (max-width: 900px) {
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    padding: 14px;
    gap: 12px;
  }

  @media (min-width: 901px) and (max-width: 1200px) {
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: 14px;
  }

  @media (min-width: 1201px) and (max-width: 1600px) {
    grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
    gap: 16px;
  }

  @media (min-width: 1601px) {
    grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
    gap: 18px;
  }
`;

const ModernListContainer = styled.div`
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
  padding: 12px 16px;

  @media (max-width: 640px) {
    padding: 8px;
    gap: 6px;
  }
`;

const EmptyStateContainer = styled.div`
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 100%;
  flex: 1;
  min-height: 400px;
  padding: 48px 24px;
  text-align: center;
  background: transparent;
`;

const EmptyStateIcon = styled.div`
  width: 80px;
  height: 80px;
  border-radius: 50%;
  background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 24px;
  color: ${OS_LEGAL_COLORS.primaryBlue};
  box-shadow: 0 4px 6px -1px rgba(59, 130, 246, 0.1),
    0 2px 4px -1px rgba(59, 130, 246, 0.06);

  svg {
    width: 36px;
    height: 36px;
    stroke-width: 1.5px;
  }
`;

const EmptyStateTitle = styled.h3`
  color: ${OS_LEGAL_COLORS.textPrimary};
  font-size: 1.25rem;
  font-weight: 600;
  margin: 0 0 8px;
  letter-spacing: -0.01em;
`;

const EmptyStateDescription = styled.p`
  color: ${OS_LEGAL_COLORS.textSecondary};
  font-size: 0.95rem;
  line-height: 1.6;
  margin: 0;
  max-width: 320px;
`;

const DropHint = styled.button`
  margin-top: 24px;
  padding: 12px 20px;
  background: ${OS_LEGAL_COLORS.surfaceHover};
  border: 1px dashed ${OS_LEGAL_COLORS.borderHover};
  border-radius: 8px;
  color: ${OS_LEGAL_COLORS.textSecondary};
  font-size: 0.875rem;
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  transition: all 0.2s ease;

  &:hover {
    background: ${OS_LEGAL_COLORS.blueSurface};
    border-color: ${OS_LEGAL_COLORS.primaryBlue};
    color: ${OS_LEGAL_COLORS.primaryBlue};

    svg {
      color: ${OS_LEGAL_COLORS.primaryBlue};
    }
  }

  svg {
    width: 18px;
    height: 18px;
    color: ${OS_LEGAL_COLORS.textMuted};
    transition: color 0.2s ease;
  }
`;

const DropZoneOverlay = styled.div`
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(15, 23, 42, 0.95);
  backdrop-filter: blur(12px);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 1000;
  animation: fadeIn 0.2s ease;

  @keyframes fadeIn {
    from {
      opacity: 0;
    }
    to {
      opacity: 1;
    }
  }
`;

const DropZoneContent = styled.div`
  padding: 48px;
  background: white;
  border-radius: 12px;
  box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
  text-align: center;
  animation: slideUp 0.2s ease;
  border: 1px solid rgba(255, 255, 255, 0.1);

  h3 {
    margin: 0 0 12px 0;
    font-size: 1.75rem;
    font-weight: 600;
    color: ${OS_LEGAL_COLORS.textPrimary};
    letter-spacing: -0.02em;
  }

  p {
    margin: 0;
    color: ${OS_LEGAL_COLORS.textSecondary};
    font-size: 1rem;
    font-weight: 400;
  }

  @keyframes slideUp {
    from {
      transform: translateY(16px);
      opacity: 0;
    }
    to {
      transform: translateY(0);
      opacity: 1;
    }
  }
`;

interface DocumentCardProps {
  style?: Record<string, any>;
  containerStyle?: React.CSSProperties;
  items: DocumentType[];
  pageInfo: PageInfo | undefined;
  loading: boolean;
  /** NetworkStatus from useQuery. When omitted, footer falls back to `loading && hasNextPage`. */
  networkStatus?: NetworkStatus;
  loading_message: string;
  onShiftClick?: (document: DocumentType) => void;
  onClick?: (document: DocumentType) => void;
  removeFromCorpus?: (doc_ids: string[]) => void | any;
  fetchMore: (args?: any) => void | any;
  onDrop: (acceptedFiles: File[]) => void;
  viewMode?: "classic" | "modern-card" | "modern-list";
  prefixItems?: React.ReactNode[]; // Items to render before documents (e.g., folders)
  /** Callback when user wants to link this document to another */
  onLinkToDocument?: (document: DocumentType) => void;
  /** Callback when a document is dropped onto another document (for creating relationships) */
  onDocumentDrop?: (sourceDocId: string, targetDocId: string) => void;
}

export const DocumentCards = ({
  containerStyle,
  style,
  items,
  pageInfo,
  loading,
  networkStatus,
  loading_message,
  onShiftClick,
  onClick,
  removeFromCorpus,
  fetchMore,
  onDrop,
  viewMode = "modern-card",
  prefixItems = [],
  onLinkToDocument,
  onDocumentDrop,
}: DocumentCardProps) => {
  const [contextMenuOpen, setContextMenuOpen] = useState<string | null>(null);

  const handleUpdate = () => {
    if (!loading && pageInfo?.hasNextPage) {
      fetchMore({
        variables: {
          limit: 20,
          cursor: pageInfo.endCursor,
        },
      });
    }
  };

  // Check if we should show the empty state (no items AND no folders)
  const showEmptyState =
    (!items || items.length === 0) && prefixItems.length === 0;

  let cards: React.ReactNode[] = [];

  if (items && items.length > 0) {
    if (viewMode === "classic") {
      // Use the original DocumentItem for backward compatibility
      cards = items.map((node, index: number) => {
        return (
          <DocumentItem
            key={node?.id ? node.id : `doc_item_${index}`}
            item={node}
            onClick={onClick}
            onShiftClick={onShiftClick}
            contextMenuOpen={contextMenuOpen}
            setContextMenuOpen={setContextMenuOpen}
            removeFromCorpus={removeFromCorpus}
          />
        );
      });
    } else {
      // Use the new ModernDocumentItem
      cards = items.map((node, index: number) => {
        return (
          <ModernDocumentItem
            key={node?.id ? node.id : `doc_item_${index}`}
            item={node}
            viewMode={viewMode === "modern-list" ? "list" : "card"}
            onClick={onClick}
            onShiftClick={onShiftClick}
            removeFromCorpus={removeFromCorpus}
            onLinkToDocument={onLinkToDocument}
            onDocumentDrop={onDocumentDrop}
          />
        );
      });
    }
  }

  const { getRootProps, getInputProps, isDragActive, open } = useDropzone({
    onDrop,
    noClick: true, // We handle click manually via the DropHint button
    noKeyboard: true,
  });

  // Handler to open file dialog when clicking the upload button
  const handleUploadClick = () => {
    open();
  };

  // Choose the appropriate container based on view mode
  const GridContainer =
    viewMode === "classic"
      ? ResponsiveCardGrid
      : viewMode === "modern-list"
      ? ModernListContainer
      : ModernCardGrid;

  return (
    <div
      {...getRootProps()}
      id="document-cards-container"
      style={{
        flex: 1,
        position: "relative",
        display: "flex",
        flexDirection: "column",
        background: OS_LEGAL_COLORS.surfaceHover,
        ...containerStyle,
      }}
    >
      <input {...getInputProps()} />
      {isDragActive && (
        <DropZoneOverlay>
          <DropZoneContent>
            <h3>Drop your files here</h3>
            <p>Release to upload documents to this corpus</p>
          </DropZoneContent>
        </DropZoneOverlay>
      )}
      {/* Initial-load overlay — `showEmptyState` (no docs and no folders) is the right gate because `prefixItems` folder rows keep the grid non-empty before any docs arrive. */}
      <LoadingOverlay
        active={loading && showEmptyState}
        size="large"
        content={loading_message}
      />
      <div
        className="DocumentCards"
        style={{
          width: "100%",
          flex: 1,
          overflowY: "auto",
          overflowX: "hidden",
          minHeight: 0,
          display: "flex",
          flexDirection: "column",
          ...style,
        }}
      >
        {showEmptyState ? (
          <EmptyStateContainer>
            <EmptyStateIcon>
              <FileText />
            </EmptyStateIcon>
            <EmptyStateTitle>No Documents Yet</EmptyStateTitle>
            <EmptyStateDescription>
              This folder is empty. Upload documents to get started with your
              document analysis.
            </EmptyStateDescription>
            <DropHint type="button" onClick={handleUploadClick}>
              <Upload />
              Drag and drop files here, or click to browse
            </DropHint>
          </EmptyStateContainer>
        ) : (
          <>
            <GridContainer>
              {prefixItems}
              {cards}
            </GridContainer>
            <FetchMoreOnVisible fetchNextPage={handleUpdate} />
            <FetchMoreFooter
              visible={
                networkStatus === NetworkStatus.fetchMore ||
                (networkStatus === undefined &&
                  loading &&
                  Boolean(pageInfo?.hasNextPage))
              }
              message="Loading more documents…"
              data-testid="document-cards-fetch-more-spinner"
            />
          </>
        )}
      </div>
    </div>
  );
};
