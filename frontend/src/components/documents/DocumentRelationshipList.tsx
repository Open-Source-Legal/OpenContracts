import React from "react";
import { ArrowRight, FileText, Link2 } from "lucide-react";
import { OS_LEGAL_COLORS } from "../../assets/configurations/osLegalStyles";
import {
  LinkedDocTitle,
  PopupContent,
  PopupHeader,
  RelationshipDetails,
  RelationshipDirection,
  RelationshipIcon,
  RelationshipItem,
  RelationshipLabel,
} from "./ModernDocumentItem.styles";

/**
 * Minimal shape consumed by the popup. Matches the projection returned by
 * `GET_DOC_RELATIONSHIPS_FOR_DOC` (no `creator` / `created` / `modified` etc.),
 * so the list view can render straight from query results.
 */
export interface RelationshipRow {
  id: string;
  relationshipType: string;
  sourceDocument?: { id: string; title?: string };
  targetDocument?: { id: string; title?: string };
  annotationLabel?: { id: string; text?: string; color?: string };
}

interface DocumentRelationshipListProps {
  /** ID of the document the popup is anchored to (used to determine direction). */
  documentId: string;
  /** Number of relationships to advertise in the header. */
  relationshipCount: number;
  /** Resolved relationship rows; may be undefined while still loading. */
  relationships?: RelationshipRow[];
  /** Truthy when the lazy relationship query failed; surfaces an error message. */
  error?: unknown;
}

/**
 * Shared relationship popup body used by both the card and list views of
 * `ModernDocumentItem`. Renders a header with the count plus a scrollable
 * list of linked documents (or a loading/error placeholder).
 */
export const DocumentRelationshipList: React.FC<
  DocumentRelationshipListProps
> = ({ documentId, relationshipCount, relationships, error }) => (
  <>
    <PopupHeader>
      <Link2 />
      <span>
        {relationshipCount} Linked Document
        {relationshipCount !== 1 ? "s" : ""}
      </span>
    </PopupHeader>
    <PopupContent>
      {relationships && relationships.length > 0 ? (
        relationships.map((rel) => {
          const isSource = rel.sourceDocument?.id === documentId;
          const linkedDoc = isSource ? rel.targetDocument : rel.sourceDocument;
          const labelColor = rel.annotationLabel?.color;

          return (
            <RelationshipItem key={rel.id}>
              <RelationshipIcon $color={labelColor || "#14b8a6"}>
                <FileText />
              </RelationshipIcon>
              <RelationshipDetails>
                {rel.annotationLabel?.text && (
                  <RelationshipLabel $color={labelColor}>
                    {rel.annotationLabel.text}
                  </RelationshipLabel>
                )}
                <LinkedDocTitle>
                  {linkedDoc?.title || "Untitled Document"}
                </LinkedDocTitle>
                <RelationshipDirection>
                  {isSource ? (
                    <>
                      This doc <ArrowRight size={10} /> linked doc
                    </>
                  ) : (
                    <>
                      Linked doc <ArrowRight size={10} /> this doc
                    </>
                  )}
                </RelationshipDirection>
              </RelationshipDetails>
            </RelationshipItem>
          );
        })
      ) : error ? (
        <div
          style={{
            color: OS_LEGAL_COLORS.textMuted,
            fontSize: "0.75rem",
          }}
        >
          Couldn't load relationships.
        </div>
      ) : (
        <div
          style={{
            color: OS_LEGAL_COLORS.textMuted,
            fontSize: "0.75rem",
          }}
        >
          Loading relationships...
        </div>
      )}
    </PopupContent>
  </>
);
