import React from "react";
import { FileText, Loader2, MoreVertical } from "lucide-react";
import { Avatar, Chip } from "@os-legal/ui";
import { DocumentType } from "../types/graphql-api";
import { formatRelativeTime } from "../utils/formatters";
import { getCreatorInitials } from "../utils/userDisplay";
import { getDocumentTypeBadge } from "../utils/files";
import {
  CardBody,
  CardCheckbox,
  CardFooter,
  CardMenuButton,
  CardMeta,
  CardPreview,
  CardPreviewPlaceholder,
  CardThumbnail,
  CardTitle,
  CardUploader,
  DocumentCardWrapper,
  DocumentsGrid,
  PreviewLine,
  PreviewLines,
  ProcessingOverlay,
  ProcessingText,
  TypeBadge,
} from "./Documents.styles";

interface DocumentsGridViewProps {
  documents: DocumentType[];
  selectedIds: string[];
  activeContextMenuDocId?: string;
  onDocumentClick: (doc: DocumentType) => void;
  onSelect: (docId: string) => void;
  onContextMenu: (e: React.MouseEvent, doc: DocumentType) => void;
}

export const DocumentsGridView: React.FC<DocumentsGridViewProps> = ({
  documents,
  selectedIds,
  activeContextMenuDocId,
  onDocumentClick,
  onSelect,
  onContextMenu,
}) => (
  <DocumentsGrid>
    {documents.map((doc) => {
      const isSelected = selectedIds.includes(doc.id);
      return (
        <DocumentCardWrapper
          key={doc.id}
          role="button"
          tabIndex={0}
          data-testid="document-card"
          data-processing={String(Boolean(doc.backendLock))}
          aria-label={`Open document ${doc.title || "Untitled"}`}
          $selected={isSelected}
          onClick={() => onDocumentClick(doc)}
          onContextMenu={(e) => onContextMenu(e, doc)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              onDocumentClick(doc);
            }
          }}
        >
          <CardCheckbox
            $visible={isSelected}
            onClick={(e) => e.stopPropagation()}
          >
            <input
              type="checkbox"
              aria-label={`Select ${doc.title || "Untitled"}`}
              checked={isSelected}
              onChange={() => onSelect(doc.id)}
            />
          </CardCheckbox>

          <CardPreview>
            {doc.icon ? (
              <CardThumbnail src={doc.icon} alt={doc.title || "Document"} />
            ) : (
              <CardPreviewPlaceholder>
                <FileText size={48} />
                <PreviewLines>
                  <PreviewLine />
                  <PreviewLine $width="85%" />
                  <PreviewLine $width="90%" />
                  <PreviewLine $width="70%" />
                </PreviewLines>
              </CardPreviewPlaceholder>
            )}

            <TypeBadge>
              <Chip size="sm" variant="filled" color="default">
                {getDocumentTypeBadge(doc.fileType, doc.title)}
              </Chip>
            </TypeBadge>

            {doc.backendLock && (
              <ProcessingOverlay>
                <Loader2
                  size={24}
                  className="animate-spin"
                  style={{ animation: "spin 1s linear infinite" }}
                />
                <ProcessingText>Processing...</ProcessingText>
              </ProcessingOverlay>
            )}
          </CardPreview>

          <CardBody>
            <CardTitle title={doc.title || "Untitled"}>
              {doc.title || "Untitled"}
            </CardTitle>
            <CardMeta>
              {doc.pageCount ? (
                <span>{doc.pageCount} pages</span>
              ) : (
                <span>Document</span>
              )}
            </CardMeta>
          </CardBody>

          <CardFooter>
            <CardUploader>
              <Avatar fallback={getCreatorInitials(doc.creator)} size="xs" />
              <span>{formatRelativeTime(doc.created)}</span>
            </CardUploader>
            <CardMenuButton
              aria-label="Open menu"
              aria-haspopup="menu"
              aria-expanded={activeContextMenuDocId === doc.id}
              onClick={(e) => {
                e.stopPropagation();
                onContextMenu(e, doc);
              }}
            >
              <MoreVertical size={16} />
            </CardMenuButton>
          </CardFooter>
        </DocumentCardWrapper>
      );
    })}
  </DocumentsGrid>
);
