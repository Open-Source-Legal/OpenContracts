import React, { useMemo } from "react";
import styled, { keyframes } from "styled-components";
import { Loader2 } from "lucide-react";

import { OS_LEGAL_COLORS } from "../../../../../assets/configurations/osLegalStyles";
import { MOBILE_RADIUS, MOBILE_SHADOW, MOBILE_SPACING } from "./mobileTheme";
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
  padding: ${MOBILE_SPACING.blockCompact}px ${MOBILE_SPACING.inline}px;
  font-size: 14px;
  color: ${OS_LEGAL_COLORS.textSecondary};
  text-align: center;
`;

const spin = keyframes`
  to {
    transform: rotate(360deg);
  }
`;

/**
 * Subtle, calm loading affordance shown while the document (and its
 * annotations) are still being fetched — e.g. a deep-link straight to an
 * annotation before anything is cached. A quietly spinning icon over the
 * sheet's white surface, never a heavy full-bleed spinner.
 *
 * `role="status"` (implicit `aria-live="polite"`) makes the state audible to
 * assistive technology: a screen-reader user arriving via deep-link hears
 * "Loading annotation…" announced when the sheet opens. The spinner icon stays
 * `aria-hidden` so only the label is read.
 */
const LoadingState = styled(EmptyState).attrs({ role: "status" })`
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: ${MOBILE_SPACING.stackGap}px;
  /* A touch more vertical breathing room than EmptyState for the spinner. */
  padding: ${MOBILE_SPACING.blockRoomy}px ${MOBILE_SPACING.inline}px;

  svg {
    color: ${OS_LEGAL_COLORS.accent};
    animation: ${spin} 0.9s linear infinite;
  }
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
  /**
   * True while the document (and its annotations) are still being fetched.
   * Threaded from the document loader so a deep-link straight to an annotation
   * — before anything is cached — shows a loader instead of prematurely
   * claiming the annotation is gone.
   *
   * Optional; defaults to `false` (fall through to the not-found state) so a
   * future callsite that forgets to thread it degrades safely rather than
   * breaking at compile time.
   */
  loading?: boolean;
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
  loading = false,
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
    // While the document/annotations are still loading (e.g. a deep-link
    // straight to an annotation before anything is cached), the selected id
    // simply hasn't arrived yet — show a loader rather than wrongly reporting
    // the annotation as gone. Only once loading settles and it's still
    // unresolved do we treat it as unavailable.
    if (loading) {
      return (
        <LoadingState>
          <Loader2 size={22} aria-hidden />
          Loading annotation…
        </LoadingState>
      );
    }
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
