import { useState } from "react";
import { useDropzone } from "react-dropzone";
import styled from "styled-components";
import { LoadingOverlay } from "../common/LoadingOverlay";

import { DocumentItem } from "./DocumentItem";
import { ModernDocumentItem } from "./ModernDocumentItem";
import { PlaceholderCard } from "../placeholders/PlaceholderCard";
import { DocumentType, PageInfo } from "../../types/graphql-api";
import { FetchMoreOnVisible } from "../widgets/infinite_scroll/FetchMoreOnVisible";

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
    max-width: 2000px;
    margin: 0 auto;
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
    max-width: 2000px;
    margin: 0 auto;
  }
`;

const ModernListContainer = styled.div`
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
  padding: 12px;
  max-width: 1200px;
  margin: 0 auto;

  @media (max-width: 640px) {
    padding: 8px;
    gap: 6px;
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
    color: #0f172a;
    letter-spacing: -0.02em;
  }

  p {
    margin: 0;
    color: #64748b;
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
  loading_message: string;
  onShiftClick?: (document: DocumentType) => void;
  onClick?: (document: DocumentType) => void;
  removeFromCorpus?: (doc_ids: string[]) => void | any;
  fetchMore: (args?: any) => void | any;
  onDrop: (acceptedFiles: File[]) => void;
  viewMode?: "classic" | "modern-card" | "modern-list";
  prefixItems?: React.ReactNode[]; // Items to render before documents (e.g., folders)
}

export const DocumentCards = ({
  containerStyle,
  style,
  items,
  pageInfo,
  loading,
  loading_message,
  onShiftClick,
  onClick,
  removeFromCorpus,
  fetchMore,
  onDrop,
  viewMode = "modern-card",
  prefixItems = [],
}: DocumentCardProps) => {
  const [contextMenuOpen, setContextMenuOpen] = useState<string | null>(null);

  const handleUpdate = () => {
    if (!loading && pageInfo?.hasNextPage) {
      console.log("cursor", pageInfo.endCursor);
      fetchMore({
        variables: {
          limit: 20,
          cursor: pageInfo.endCursor,
        },
      });
    }
  };

  let cards = [
    <PlaceholderCard
      key="PlaceholderCard"
      title="No Matching Documents"
      style={{
        minHeight: "240px",
        background: "#ffffff",
        border: "1px solid #e2e8f0",
        borderRadius: "12px",
      }}
    />,
  ];

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
          />
        );
      });
    }
  }

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    noClick: true,
    noKeyboard: true,
  });

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
        background: "#f8fafc",
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
      <LoadingOverlay
        active={loading}
        inverted
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
          ...style,
        }}
      >
        <GridContainer>
          {prefixItems}
          {cards}
        </GridContainer>
        <FetchMoreOnVisible fetchNextPage={handleUpdate} />
      </div>
    </div>
  );
};
