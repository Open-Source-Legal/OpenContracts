import { useMemo } from "react";
import styled from "styled-components";

import { RelationItem } from "../../sidebar/RelationItem";

import "../../sidebar/AnnotatorSidebar.css";
import { PlaceholderCard } from "../../../placeholders/PlaceholderCard";
import {
  RelationGroup,
  ServerSpanAnnotation,
  ServerTokenAnnotation,
} from "../../types/annotations";
import { useAnnotationRefs } from "../../hooks/useAnnotationRefs";
import {
  useAnnotationSelection,
  useAnnotationDisplay,
} from "../../context/UISettingsAtom";
import {
  usePdfAnnotations,
  useRemoveAnnotationFromRelationship,
  useRemoveRelationship,
  useStructuralAnnotations,
} from "../../hooks/AnnotationHooks";
import _ from "lodash";
import { RelationshipViewSettingsPopup } from "../../../widgets/popups/RelationshipViewSettingsPopup";

// Define the styled container for scrolling
const RelationshipListContainer = styled.div`
  display: flex;
  flex-direction: column;
  flex: 1; /* Allow this container to grow and shrink */
  min-height: 0; /* Essential for flex item to shrink and enable scrolling */
  overflow-y: auto; /* This container will scroll its content */
  padding: 0.5rem 0;

  /* Custom scrollbar styles (mirroring AnnotationListContainer) */
  &::-webkit-scrollbar {
    width: 8px;
  }

  &::-webkit-scrollbar-track {
    background: #f1f5f9; /* Light grey track */
  }

  &::-webkit-scrollbar-thumb {
    background: #cbd5e1; /* Medium grey thumb */
    border-radius: 4px;

    &:hover {
      background: #94a3b8; /* Darker grey thumb on hover */
    }
  }
`;

const CardGroup = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
`;

export const RelationshipList = ({ read_only }: { read_only: boolean }) => {
  const handleRemoveRelationship = useRemoveRelationship();
  const removeAnnotationFromRelation = useRemoveAnnotationFromRelationship();
  const {
    selectedAnnotations,
    selectedRelations,
    setSelectedAnnotations,
    setSelectedRelations,
  } = useAnnotationSelection();
  const { showStructuralRelationships } = useAnnotationDisplay();

  const { annotationElementRefs } = useAnnotationRefs();
  const { pdfAnnotations } = usePdfAnnotations();
  const { structuralAnnotations } = useStructuralAnnotations();

  // Combine regular and structural annotations
  const allAnnotations = useMemo(() => {
    const regularAnnotations = pdfAnnotations.annotations || [];
    const structural = structuralAnnotations || [];
    return [...regularAnnotations, ...structural] as (
      | ServerSpanAnnotation
      | ServerTokenAnnotation
    )[];
  }, [pdfAnnotations.annotations, structuralAnnotations]);

  const rawRelations = pdfAnnotations.relations;

  // Filter relations based on the showStructuralRelationships flag
  const relationsToDisplay = useMemo(() => {
    if (showStructuralRelationships) {
      return rawRelations; // Show all if the flag is true
    }
    // Otherwise, filter out structural relationships
    // This assumes RelationGroup has a `structural?: boolean` property.
    // If not, the logic to identify structural relationships needs to be defined here.
    return rawRelations.filter((relation) => !relation.structural);
  }, [rawRelations, showStructuralRelationships]);

  // If we have search results pane open... set index to last index
  const onRemoveAnnotationFromRelation = (
    annotationId: string,
    relationId: string
  ) => {
    removeAnnotationFromRelation(annotationId, relationId);
  };

  const onDeleteRelation = (relationId: string) => {
    handleRemoveRelationship(relationId);
  };

  const toggleSelectedAnnotation = (toggledId: string) => {
    if (selectedAnnotations.includes(toggledId)) {
      setSelectedAnnotations(
        selectedAnnotations.filter((annotationId) => annotationId !== toggledId)
      );
    }
    // If the toggle is flipping us over to SELECTED
    else {
      let annotation = pdfAnnotations.annotations.filter(
        (annotation_obj) => annotation_obj.id === toggledId
      )[0];
      // Check the proposed id is actually in the annotation store
      if (annotation) {
        // If it is, and we have a reference to it in our annotation reference obj
        if (annotationElementRefs?.current[annotation.id]) {
          // Scroll annotation into view.
          annotationElementRefs?.current[annotation.id]?.scrollIntoView({
            behavior: "smooth",
            block: "center",
          });
        }
      }
      setSelectedAnnotations([toggledId]);
    }
  };

  const toggleSelectedRelation = (
    toggled_relation: RelationGroup,
    implicated_annotations: string[]
  ) => {
    if (_.find(selectedRelations, { id: toggled_relation.id })) {
      setSelectedRelations(
        selectedRelations.filter(
          (relation) => relation.id !== toggled_relation.id
        )
      );
      setSelectedAnnotations([]);
    } else {
      setSelectedRelations([toggled_relation]);
      setSelectedAnnotations(implicated_annotations);
    }
  };

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        flex: 1, // Ensures RelationshipList component fills space given by its parent in DocumentKnowledgeBase
        minHeight: 0, // Allows it to shrink correctly
      }}
    >
      <RelationshipViewSettingsPopup />
      <RelationshipListContainer>
        <CardGroup>
          {relationsToDisplay && relationsToDisplay.length > 0 ? (
            relationsToDisplay.map((relation, index) => (
              <RelationItem
                key={`relation_item_${relation.id}`}
                relation={relation}
                read_only={read_only}
                selected={selectedRelations.includes(relation)}
                source_annotations={allAnnotations.filter((a) =>
                  relation.sourceIds.includes(a.id)
                )}
                target_annotations={allAnnotations.filter((a) =>
                  relation.targetIds.includes(a.id)
                )}
                onSelectAnnotation={toggleSelectedAnnotation}
                onSelectRelation={() =>
                  toggleSelectedRelation(relation, [
                    ...relation.sourceIds,
                    ...relation.targetIds,
                  ])
                }
                onRemoveAnnotationFromRelation={onRemoveAnnotationFromRelation}
                onDeleteRelation={onDeleteRelation}
              />
            ))
          ) : (
            <PlaceholderCard
              style={{ flex: 1 }}
              title="No Relations Found"
              description="Either no matching relations were created or you didn't create them yet."
            />
          )}
        </CardGroup>
      </RelationshipListContainer>
    </div>
  );
};
