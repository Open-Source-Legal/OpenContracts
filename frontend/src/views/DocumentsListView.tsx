import React from "react";
import { MoreVertical } from "lucide-react";
import { Avatar, Chip } from "@os-legal/ui";
import { DocumentType } from "../types/graphql-api";
import { formatRelativeTime } from "../utils/formatters";
import { getCreatorInitials } from "../utils/userDisplay";
import { getDocumentTypeBadge } from "../utils/files";
import {
  CardMenuButton,
  DocumentsListContainer,
  ListHeader,
  ListItem,
  ListItemActions,
  ListItemName,
  ListItemSize,
  ListItemType,
  ListItemUploader,
} from "./Documents.styles";

interface DocumentsListViewProps {
  documents: DocumentType[];
  selectedIds: string[];
  activeContextMenuDocId?: string;
  allSelected: boolean;
  onDocumentClick: (doc: DocumentType) => void;
  onSelect: (docId: string) => void;
  onSelectAll: () => void;
  onContextMenu: (e: React.MouseEvent, doc: DocumentType) => void;
}

export const DocumentsListView: React.FC<DocumentsListViewProps> = ({
  documents,
  selectedIds,
  activeContextMenuDocId,
  allSelected,
  onDocumentClick,
  onSelect,
  onSelectAll,
  onContextMenu,
}) => (
  <DocumentsListContainer role="table" aria-label="Documents list">
    <ListHeader role="rowgroup">
      <input
        type="checkbox"
        aria-label="Select all documents"
        checked={allSelected}
        onChange={onSelectAll}
      />
      <span>Name</span>
      <span>Type</span>
      <span>Pages</span>
      <span>Status</span>
      <span>Uploaded</span>
      <span></span>
    </ListHeader>
    {documents.map((doc) => {
      const isSelected = selectedIds.includes(doc.id);
      return (
        <ListItem
          key={doc.id}
          role="row"
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
          <ListItemName title={doc.title || "Untitled"}>
            {doc.title || "Untitled"}
          </ListItemName>
          <ListItemType>
            {getDocumentTypeBadge(doc.fileType, doc.title)}
          </ListItemType>
          <ListItemSize>
            {doc.pageCount ? `${doc.pageCount} pages` : ""}
          </ListItemSize>
          <div>
            <Chip
              size="sm"
              variant="soft"
              color={doc.backendLock ? "warning" : "success"}
            >
              {doc.backendLock ? "Processing" : "Processed"}
            </Chip>
          </div>
          <ListItemUploader>
            <Avatar fallback={getCreatorInitials(doc.creator)} size="xs" />
            <span>{formatRelativeTime(doc.created)}</span>
          </ListItemUploader>
          <ListItemActions>
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
          </ListItemActions>
        </ListItem>
      );
    })}
  </DocumentsListContainer>
);
