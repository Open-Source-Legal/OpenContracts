import React, { useEffect } from "react";
import styled from "styled-components";
import { useAtomValue } from "jotai";
import { List } from "lucide-react";

import { OS_LEGAL_COLORS } from "../../../../../assets/configurations/osLegalStyles";
import { MOBILE_RADIUS, MOBILE_SHADOW } from "./mobileTheme";
import { structuralAnnotationsAtom } from "../../../../annotator/context/AnnotationAtoms";
import { showStructuralAnnotations } from "../../../../../graphql/cache";

export interface MobileSectionsSheetProps {
  /** Whether the sheet is open — gates the structural-annotation fetch. */
  open: boolean;
  /** Navigate the viewer to the tapped section, then close the sheet. */
  onNavigate: (annotationId: string) => void;
}

const List_ = styled.div`
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 16px 14px;
`;

const Row = styled.button`
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 13px 14px;
  border: none;
  border-radius: ${MOBILE_RADIUS.md};
  background: ${OS_LEGAL_COLORS.surface};
  box-shadow: ${MOBILE_SHADOW.subtle};
  text-align: left;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  color: ${OS_LEGAL_COLORS.textPrimary};
  -webkit-tap-highlight-color: transparent;
  transition: transform 0.12s ease, box-shadow 0.16s ease;

  &:active {
    transform: scale(0.985);
    box-shadow: ${MOBILE_SHADOW.raised};
  }
`;

/** Soft rounded tinted container holding the section icon. */
const RowIcon = styled.span`
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border-radius: ${MOBILE_RADIUS.sm};
  background: ${OS_LEGAL_COLORS.accentLight};
`;

const RowLabel = styled.span`
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
`;

const PageBadge = styled.span`
  flex-shrink: 0;
  padding: 3px 9px;
  border-radius: ${MOBILE_RADIUS.pill};
  background: ${OS_LEGAL_COLORS.surfaceLight};
  font-size: 11px;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textSecondary};
`;

const Empty = styled.div`
  padding: 24px 16px;
  font-size: 14px;
  text-align: center;
  color: ${OS_LEGAL_COLORS.textSecondary};
`;

/**
 * Body for the Document → Sections sheet.
 *
 * Renders the document's structural annotations (headers / sections) as a flat
 * tappable index. Tapping a row routes the viewer to that annotation via the
 * standard `?ann=` deep-link path. Opening the sheet flips the
 * `showStructuralAnnotations` reactive var so {@link useStructuralAnnotations}
 * (mounted by DocumentKnowledgeBase) lazily fetches the structural set.
 */
export const MobileSectionsSheet: React.FC<MobileSectionsSheetProps> = ({
  open,
  onNavigate,
}) => {
  const structuralAnnotations = useAtomValue(structuralAnnotationsAtom);

  // Opening the sheet is the user signalling intent to browse structure — use
  // it as the trigger to lazily load the structural annotation set.
  useEffect(() => {
    if (open) {
      showStructuralAnnotations(true);
    }
  }, [open]);

  if (structuralAnnotations.length === 0) {
    return (
      <Empty data-testid="mobile-sections-empty">
        No sections detected in this document.
      </Empty>
    );
  }

  return (
    <List_ data-testid="mobile-sections-list">
      {structuralAnnotations.map((ann) => {
        const label = (ann.rawText || ann.annotationLabel?.text || "Section")
          .trim()
          .replace(/\s+/g, " ");
        return (
          <Row key={ann.id} onClick={() => onNavigate(ann.id)}>
            <RowIcon>
              <List size={15} color={OS_LEGAL_COLORS.accent} />
            </RowIcon>
            <RowLabel>{label || "Section"}</RowLabel>
            <PageBadge>p.{ann.page + 1}</PageBadge>
          </Row>
        );
      })}
    </List_>
  );
};
