import React from "react";
import styled from "styled-components";
import { motion } from "framer-motion";
import { UnifiedContentItem, Note } from "./types";
import {
  ServerSpanAnnotation,
  ServerTokenAnnotation,
  RelationGroup,
} from "../../../annotator/types/annotations";
import { TextSearchTokenResult, TextSearchSpanResult } from "../../../types";
import { HighlightItem } from "../../../annotator/sidebar/HighlightItem";
import { RelationItem } from "../../../annotator/sidebar/RelationItem";
import { PostItNote } from "../StickyNotes";
import { SafeMarkdown } from "../../markdown/SafeMarkdown";
import { Edit3, Search } from "lucide-react";
import { TruncatedText } from "../../../widgets/data-display/TruncatedText";
import {
  useAnnotationSelection,
  useAnnotationDisplay,
} from "../../../annotator/context/UISettingsAtom";
import {
  usePdfAnnotations,
  useRemoveAnnotationFromRelationship,
  useRemoveRelationship,
  useDeleteAnnotation,
  useStructuralAnnotations,
} from "../../../annotator/hooks/AnnotationHooks";
import { useAnnotationRefs } from "../../../annotator/hooks/useAnnotationRefs";

interface ContentItemRendererProps {
  item: UnifiedContentItem;
  onSelect?: () => void;
  readOnly?: boolean;
}

/* Styled Components */
const ItemContainer = styled.div`
  margin-bottom: 0.5rem;
`;

const SearchResultCard = styled(motion.div)`
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 1rem;
  cursor: pointer;
  transition: all 0.2s ease;

  &:hover {
    background: #f8fafc;
    border-color: #cbd5e1;
    transform: translateY(-1px);
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
  }
`;

const SearchIcon = styled.div`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  background: #e0e7ff;
  border-radius: 6px;
  margin-right: 0.75rem;
  flex-shrink: 0;

  svg {
    width: 14px;
    height: 14px;
    color: #6366f1;
  }
`;

const SearchResultContent = styled.div`
  display: flex;
  align-items: flex-start;
`;

const SearchResultText = styled.div`
  flex: 1;
  font-size: 0.875rem;
  line-height: 1.5;
  color: #475569;

  .highlight {
    background: #fef3c7;
    padding: 0.125rem 0.25rem;
    border-radius: 3px;
    font-weight: 500;
  }
`;

const PageIndicator = styled.span`
  font-size: 0.75rem;
  color: #94a3b8;
  margin-left: 0.5rem;
`;

/**
 * Type guards for identifying content types
 */
function isNote(data: any): data is Note {
  return "content" in data && "creator" in data;
}

function isAnnotation(
  data: any
): data is ServerSpanAnnotation | ServerTokenAnnotation {
  return "annotationLabel" in data;
}

function isRelationGroup(data: any): data is RelationGroup {
  return "sourceIds" in data && "targetIds" in data && "label" in data;
}

function isSearchResult(
  data: any
): data is TextSearchTokenResult | TextSearchSpanResult {
  return (
    ("tokens" in data && "fullContext" in data) ||
    ("text" in data && !("annotationLabel" in data))
  );
}

/**
 * ContentItemRenderer renders individual items in the unified feed
 * using the appropriate component for each content type.
 */
export const ContentItemRenderer: React.FC<ContentItemRendererProps> = ({
  item,
  onSelect,
  readOnly = false,
}) => {
  const { annotationElementRefs } = useAnnotationRefs();
  const { pdfAnnotations } = usePdfAnnotations();
  const { structuralAnnotations } = useStructuralAnnotations();
  const {
    selectedAnnotations,
    selectedRelations,
    setSelectedAnnotations,
    setSelectedRelations,
  } = useAnnotationSelection();
  const { showStructuralRelationships } = useAnnotationDisplay();

  const handleDeleteAnnotation = useDeleteAnnotation();
  const handleRemoveRelationship = useRemoveRelationship();
  const removeAnnotationFromRelation = useRemoveAnnotationFromRelationship();

  /* Render note */
  if (item.type === "note" && isNote(item.data)) {
    const note = item.data as Note;
    return (
      <ItemContainer>
        <PostItNote
          onClick={readOnly ? undefined : onSelect}
          $readOnly={readOnly}
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3 }}
          whileHover={{
            y: -4,
            transition: { duration: 0.2 },
          }}
        >
          <div className="edit-indicator">
            <Edit3 size={14} />
          </div>
          {note.title && <div className="title">{note.title}</div>}
          <div className="content">
            <SafeMarkdown>{note.content}</SafeMarkdown>
          </div>
          <div className="meta">
            {note.creator.email} • {new Date(note.created).toLocaleDateString()}
          </div>
        </PostItNote>
      </ItemContainer>
    );
  }

  /* Render annotation */
  if (item.type === "annotation" && isAnnotation(item.data)) {
    const annotation = item.data as
      | ServerSpanAnnotation
      | ServerTokenAnnotation;

    const handleSelect = (annotationId: string) => {
      if (selectedAnnotations.includes(annotationId)) {
        setSelectedAnnotations(
          selectedAnnotations.filter((id) => id !== annotationId)
        );
      } else {
        setSelectedAnnotations([...selectedAnnotations, annotationId]);

        // Scroll to annotation
        const ref = annotationElementRefs?.current[annotationId];
        if (ref) {
          ref.scrollIntoView({ behavior: "smooth", block: "center" });
        }
      }
      onSelect?.();
    };

    return (
      <ItemContainer>
        <HighlightItem
          annotation={annotation}
          relations={pdfAnnotations.relations}
          read_only={readOnly}
          onSelect={handleSelect}
          onDelete={readOnly ? undefined : handleDeleteAnnotation}
        />
      </ItemContainer>
    );
  }

  /* Render relationship */
  if (item.type === "relationship" && isRelationGroup(item.data)) {
    const relation = item.data as RelationGroup;

    // Get all annotations for source/target lookup
    const allAnnotations = [
      ...(pdfAnnotations.annotations || []),
      ...(structuralAnnotations || []),
    ];

    const handleSelectAnnotation = (annotationId: string) => {
      if (selectedAnnotations.includes(annotationId)) {
        setSelectedAnnotations(
          selectedAnnotations.filter((id) => id !== annotationId)
        );
      } else {
        setSelectedAnnotations([annotationId]);

        // Scroll to annotation
        const ref = annotationElementRefs?.current[annotationId];
        if (ref) {
          ref.scrollIntoView({ behavior: "smooth", block: "center" });
        }
      }
    };

    const handleSelectRelation = () => {
      const isSelected = selectedRelations.some((r) => r.id === relation.id);
      if (isSelected) {
        setSelectedRelations(
          selectedRelations.filter((r) => r.id !== relation.id)
        );
        setSelectedAnnotations([]);
      } else {
        setSelectedRelations([relation]);
        setSelectedAnnotations([...relation.sourceIds, ...relation.targetIds]);
      }
      onSelect?.();
    };

    return (
      <ItemContainer>
        <RelationItem
          relation={relation}
          read_only={readOnly}
          selected={selectedRelations.some((r) => r.id === relation.id)}
          source_annotations={allAnnotations.filter((a) =>
            relation.sourceIds.includes(a.id)
          )}
          target_annotations={allAnnotations.filter((a) =>
            relation.targetIds.includes(a.id)
          )}
          onSelectAnnotation={handleSelectAnnotation}
          onSelectRelation={handleSelectRelation}
          onRemoveAnnotationFromRelation={
            readOnly
              ? () => {}
              : (annId, relId) => removeAnnotationFromRelation(annId, relId)
          }
          onDeleteRelation={readOnly ? () => {} : handleRemoveRelationship}
        />
      </ItemContainer>
    );
  }

  /* Render search result */
  if (item.type === "search" && isSearchResult(item.data)) {
    const result = item.data;
    const isTokenResult = "tokens" in result;

    return (
      <ItemContainer>
        <SearchResultCard
          onClick={onSelect}
          whileHover={{ scale: 1.01 }}
          whileTap={{ scale: 0.99 }}
        >
          <SearchResultContent>
            <SearchIcon>
              <Search />
            </SearchIcon>
            <SearchResultText>
              {isTokenResult ? (
                <>
                  {(result as TextSearchTokenResult).fullContext}
                  <PageIndicator>
                    Pages {(result as TextSearchTokenResult).start_page} -{" "}
                    {(result as TextSearchTokenResult).end_page}
                  </PageIndicator>
                </>
              ) : (
                <>
                  <TruncatedText
                    text={(result as TextSearchSpanResult).text}
                    limit={120}
                  />
                  <PageIndicator>Text match</PageIndicator>
                </>
              )}
            </SearchResultText>
          </SearchResultContent>
        </SearchResultCard>
      </ItemContainer>
    );
  }

  /* Fallback - should not happen */
  return null;
};
