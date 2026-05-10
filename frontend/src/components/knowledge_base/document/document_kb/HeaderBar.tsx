import React from "react";
import { ArrowLeft, Calendar, FileType, Plus, User } from "lucide-react";
import { DocumentVersionSelector } from "../../../documents/DocumentVersionSelector";
import { HeaderContainer, MetadataRow } from "../styled/HeaderAndLayout";
import { HeaderButtonGroup, HeaderButton } from "./styles";
import { routingLogger } from "../../../../utils/routingLogger";
import { CreatorRef, getCreatorDisplay } from "../../../../utils/userDisplay";

export interface DocumentMetadata {
  title?: string | null;
  fileType?: string | null;
  // Privacy contract: viewers cross-user only see ``slug`` (or a
  // ``user_<pk-suffix>`` fallback). ``email`` is no longer rendered.
  creator?: CreatorRef | null;
  created?: string | null;
}

export interface HeaderBarProps {
  metadata: DocumentMetadata;
  documentId: string;
  corpusId?: string;
  /** True when the document is bound to a corpus (controls version selector + Add-to-Corpus button) */
  hasCorpus: boolean;
  readOnly: boolean;
  /** Open the AddToCorpus modal — only rendered when no corpus is bound and the user can edit */
  onAddToCorpus: () => void;
  /** Back-button handler. */
  onClose: () => void;
}

/**
 * Modal header bar: document title + metadata (filetype, creator, created
 * date, optional version selector) on the left, and the Add-to-Corpus /
 * back buttons on the right.
 */
export const HeaderBar: React.FC<HeaderBarProps> = ({
  metadata,
  documentId,
  corpusId,
  hasCorpus,
  readOnly,
  onAddToCorpus,
  onClose,
}) => {
  const title = metadata.title || "Untitled Document";

  return (
    <HeaderContainer>
      <div style={{ flex: 1, minWidth: 0, overflow: "hidden" }}>
        <h2
          style={{
            margin: 0,
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
            maxWidth: "100%",
            fontSize: "1.5rem",
            fontWeight: 700,
          }}
        >
          <span title={title}>{title}</span>
        </h2>
        <MetadataRow>
          <span>
            <FileType size={16} /> {metadata.fileType}
          </span>
          <span>
            <User size={16} /> {getCreatorDisplay(metadata.creator)}
          </span>
          <span>
            <Calendar size={16} /> Created:{" "}
            {metadata.created
              ? new Date(metadata.created).toLocaleDateString()
              : "—"}
          </span>
          {hasCorpus && corpusId && (
            <DocumentVersionSelector
              documentId={documentId}
              corpusId={corpusId}
            />
          )}
        </MetadataRow>
      </div>

      <HeaderButtonGroup>
        {!hasCorpus && !readOnly && (
          <HeaderButton
            $variant="primary"
            onClick={onAddToCorpus}
            title="Add this document to a corpus to unlock collaborative features"
            data-testid="add-to-corpus-button"
          >
            <Plus />
            Add to Corpus
          </HeaderButton>
        )}
        <HeaderButton
          onClick={(e) => {
            routingLogger.debug(
              `🖱️  [DocumentKnowledgeBase] ════════ BACK BUTTON CLICKED ════════`
            );
            routingLogger.debug("[DocumentKnowledgeBase] Button click event:", {
              timestamp: new Date().toISOString(),
              button: e.button,
              currentTarget: e.currentTarget,
              target: e.target,
              currentUrl: window.location.pathname + window.location.search,
            });
            onClose();
          }}
          title="Go back"
          data-testid="back-button"
        >
          <ArrowLeft />
        </HeaderButton>
      </HeaderButtonGroup>
    </HeaderContainer>
  );
};
