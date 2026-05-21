import React from "react";
import styled from "styled-components";

import { OS_LEGAL_COLORS } from "../../../../../assets/configurations/osLegalStyles";
import { HighlightItem } from "../../../../annotator/sidebar/HighlightItem";
import { useAllAnnotations } from "../../../../annotator/hooks/useAllAnnotations";
import { useStructuralAnnotations } from "../../../../annotator/hooks/AnnotationHooks";
import { usePdfAnnotations } from "../../../../annotator/hooks/AnnotationHooks";
import { useDeleteAnnotation } from "../../../../annotator/hooks/AnnotationHooks";
import { useAnnotationSelection } from "../../../../annotator/context/UISettingsAtom";

const EmptyState = styled.div`
  padding: 24px 16px;
  font-size: 14px;
  color: ${OS_LEGAL_COLORS.textSecondary};
  text-align: center;
`;

interface MobileAnnotationDetailProps {
  /** Read-only mode disables editing capabilities (delete). */
  readOnly: boolean;
}

/**
 * Body of the mobile "Annotation" detail sheet.
 *
 * Renders the existing single-annotation detail card ({@link HighlightItem})
 * for the first entry of the shared {@link useAnnotationSelection} selection.
 * That selection is set from two places — tapping a feed row in the
 * Annotations surface and tapping a highlight in the Document-tab viewer — so
 * this component is the single rendering site for both open paths.
 *
 * Voting / approval for an annotation is surfaced by the in-viewer highlight
 * tooltip (see {@link Selection}); the feedback cloud appears on the highlight
 * itself, so it is not duplicated here. This component only presents the
 * label, quoted text, relationship badges, page reference and (when editable)
 * the delete control.
 */
export const MobileAnnotationDetail: React.FC<MobileAnnotationDetailProps> = ({
  readOnly,
}) => {
  const { selectedAnnotations } = useAnnotationSelection();
  const allAnnotations = useAllAnnotations();
  const { structuralAnnotations } = useStructuralAnnotations();
  const { pdfAnnotations } = usePdfAnnotations();
  const handleDeleteAnnotation = useDeleteAnnotation();

  const selectedId = selectedAnnotations[0];

  // Look across user-editable AND structural annotations so a highlight tapped
  // in the viewer (which may be structural) still resolves to a detail card.
  const annotation =
    [...allAnnotations, ...(structuralAnnotations || [])].find(
      (a) => a.id === selectedId
    ) ?? null;

  if (!annotation) {
    return <EmptyState>This annotation is no longer available.</EmptyState>;
  }

  return (
    <HighlightItem
      annotation={annotation}
      relations={pdfAnnotations.relations}
      read_only={readOnly}
      onSelect={() => {}}
      onDelete={readOnly ? undefined : handleDeleteAnnotation}
      contentModalities={annotation.contentModalities}
    />
  );
};

export default MobileAnnotationDetail;
