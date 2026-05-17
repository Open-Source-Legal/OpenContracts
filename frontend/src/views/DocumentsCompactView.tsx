import React from "react";
import { FileText, MoreVertical } from "lucide-react";
import { Chip } from "@os-legal/ui";
import { DocumentType } from "../types/graphql-api";
import {
  CardMenuButton,
  CompactItem,
  CompactItemMeta,
  CompactItemName,
  DocumentsCompactContainer,
  ListItemIcon,
} from "./Documents.styles";

interface DocumentsCompactViewProps {
  documents: DocumentType[];
  selectedIds: string[];
  activeContextMenuDocId?: string;
  onDocumentClick: (doc: DocumentType) => void;
  onSelect: (docId: string) => void;
  onContextMenu: (e: React.MouseEvent, doc: DocumentType) => void;
}

export const DocumentsCompactView: React.FC<DocumentsCompactViewProps> = ({
  documents,
  selectedIds,
  activeContextMenuDocId,
  onDocumentClick,
  onSelect,
  onContextMenu,
}) => (
  <DocumentsCompactContainer>
    {documents.map((doc) => {
      const isSelected = selectedIds.includes(doc.id);
      return (
        <CompactItem
          key={doc.id}
          role="listitem"
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
          <div onClick={(e) => e.stopPropagation()}>
            <input
              type="checkbox"
              aria-label={`Select ${doc.title || "Untitled"}`}
              checked={isSelected}
              onChange={() => onSelect(doc.id)}
            />
          </div>
          <ListItemIcon>
            <FileText size={20} />
          </ListItemIcon>
          <CompactItemName title={doc.title || "Untitled"}>
            {doc.title || "Untitled"}
          </CompactItemName>
          <CompactItemMeta>
            {doc.pageCount ? `${doc.pageCount} pages` : ""}
          </CompactItemMeta>
          <Chip
            size="sm"
            variant="soft"
            color={doc.backendLock ? "warning" : "success"}
          >
            {doc.backendLock ? "Processing" : "Processed"}
          </Chip>
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
        </CompactItem>
      );
    })}
  </DocumentsCompactContainer>
);
