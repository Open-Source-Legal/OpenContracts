import React, { useMemo } from "react";
import styled from "styled-components";

import { OS_LEGAL_COLORS } from "../../../../../assets/configurations/osLegalStyles";
import { MOBILE_RADIUS, MOBILE_SHADOW } from "./mobileTheme";
import {
  HighlightItem,
  HighlightItemCard,
} from "../../../../annotator/sidebar/HighlightItem";
import { useAllAnnotations } from "../../../../annotator/hooks/useAllAnnotations";
import {
  useStructuralAnnotations,
  usePdfAnnotations,
  useDeleteAnnotation,
} from "../../../../annotator/hooks/AnnotationHooks";
import { useAnnotationSelection } from "../../../../annotator/context/UISettingsAtom";

const EmptyState = styled.div`
  padding: 24px 16px;
  font-size: 14px;
  color: ${OS_LEGAL_COLORS.textSecondary};
  text-align: center;
`;

/**
 * Mobile frame for the shared {@link HighlightItem} detail.
 *
 * `HighlightItem` always renders here in its `selected` state, which paints an
 * arbitrary green tint and green glow on its inner container. On mobile this
 * detail card should read as a calm white surface, so this wrapper neutralises
 * that tint and re-grounds the inner container as a clean elevated card —
 * scoped strictly to the mobile sheet, leaving the desktop sidebar untouched.
 * It also refines the quoted-text blockquote into a soft slate-tinted quote.
 *
 * The override targets the exported {@link HighlightItemCard} styled component
 * by reference rather than a positional `& > div`, so it stays correct if
 * `HighlightItem`'s internal markup changes. The reference selector also
 * out-specifies `HighlightItemCard`'s own (single-class) rules, so no
 * `!important` is needed on the container overrides.
 */
const Card = styled.div`
  padding: 8px 6px 16px;

  /* HighlightItem's outer container — drop the green selected tint/glow. */
  & > ${HighlightItemCard} {
    margin: 8px 8px 0;
    background-color: ${OS_LEGAL_COLORS.surface};
    border-radius: ${MOBILE_RADIUS.lg};
    box-shadow: ${MOBILE_SHADOW.raised};
    cursor: default;
  }

  & > ${HighlightItemCard}:hover {
    transform: none;
    background-color: ${OS_LEGAL_COLORS.surface};
    box-shadow: ${MOBILE_SHADOW.raised};
  }

  /* Quoted text — a refined soft slate blockquote. */
  & blockquote {
    background-color: ${OS_LEGAL_COLORS.surfaceLight} !important;
    border-radius: ${MOBILE_RADIUS.sm} !important;
  }
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
  const annotation = useMemo(
    () =>
      [...allAnnotations, ...(structuralAnnotations || [])].find(
        (a) => a.id === selectedId
      ) ?? null,
    [allAnnotations, structuralAnnotations, selectedId]
  );

  if (!annotation) {
    return <EmptyState>This annotation is no longer available.</EmptyState>;
  }

  return (
    <Card>
      <HighlightItem
        annotation={annotation}
        relations={pdfAnnotations.relations}
        read_only={readOnly}
        onSelect={() => {}}
        onDelete={readOnly ? undefined : handleDeleteAnnotation}
        contentModalities={annotation.contentModalities}
        compact
      />
    </Card>
  );
};
