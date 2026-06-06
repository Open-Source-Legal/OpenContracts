import React, { useMemo } from "react";
import styled from "styled-components";
import { useQuery } from "@apollo/client";
import { List } from "lucide-react";

import { OS_LEGAL_COLORS } from "../../../../../assets/configurations/osLegalStyles";
import { MOBILE_RADIUS, MOBILE_SHADOW } from "./mobileTheme";
import {
  GET_DOCUMENT_ANNOTATION_INDEX,
  GetDocumentAnnotationIndexInput,
  GetDocumentAnnotationIndexOutput,
} from "../../../../../graphql/queries";
import {
  DOCUMENT_ANNOTATION_INDEX_LIMIT,
  OC_SECTION_LABEL,
} from "../../../../../assets/configurations/constants";

export interface MobileSectionsSheetProps {
  /** Whether the sheet is open — gates the (lazy) index fetch. */
  open: boolean;
  /** Document (relay global id) whose section index to load. */
  documentId: string;
  /** Optional corpus scope for the index query. */
  corpusId?: string;
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
 * Renders the document's **index** — the `OC_SECTION` annotations
 * (`structural: false`), i.e. the exact same set the desktop "Index" tab
 * ({@link DocumentAnnotationIndex}) shows — as a flat, document-order tappable
 * jump list. Tapping a row routes the viewer to that annotation via the
 * standard `?ann=` deep-link path (`onNavigate`).
 *
 * Historically this sheet read the *structural* annotation set
 * (`structural: true`). That set is disjoint from `OC_SECTION` (the enricher
 * marks index entries `structural=false` so users can edit them), so for an
 * OC_SECTION-indexed document the sheet rendered nothing at all while the
 * desktop index was full — issue: "mobile index loads nothing". Sourcing the
 * index query directly keeps the two surfaces consistent. The fetch is gated
 * on `open` so it stays lazy (no work until the user browses sections).
 */
export const MobileSectionsSheet: React.FC<MobileSectionsSheetProps> = ({
  open,
  documentId,
  corpusId,
  onNavigate,
}) => {
  const { data, loading, error } = useQuery<
    GetDocumentAnnotationIndexOutput,
    GetDocumentAnnotationIndexInput
  >(GET_DOCUMENT_ANNOTATION_INDEX, {
    variables: {
      documentId,
      corpusId,
      labelText: OC_SECTION_LABEL,
      first: DOCUMENT_ANNOTATION_INDEX_LIMIT,
    },
    skip: !open || !documentId,
    fetchPolicy: "cache-first",
  });

  // Flat, page-ordered list — the right shape for a mobile "jump to section"
  // sheet (the desktop tab renders the same nodes as an expandable tree).
  const sections = useMemo(() => {
    const nodes = (data?.annotations?.edges ?? []).map((edge) => edge.node);
    return [...nodes].sort(
      (a, b) =>
        (a.page ?? 0) - (b.page ?? 0) ||
        (a.rawText ?? "").localeCompare(b.rawText ?? "")
    );
  }, [data]);

  if (loading && sections.length === 0) {
    return (
      <Empty data-testid="mobile-sections-loading">Loading sections…</Empty>
    );
  }

  // Distinguish a fetch failure from a genuinely section-less document so the
  // user isn't told "no sections" when the index simply failed to load.
  if (error && sections.length === 0) {
    return (
      <Empty data-testid="mobile-sections-error">
        Failed to load sections.
      </Empty>
    );
  }

  if (sections.length === 0) {
    return (
      <Empty data-testid="mobile-sections-empty">
        No sections detected in this document.
      </Empty>
    );
  }

  return (
    <List_ data-testid="mobile-sections-list">
      {sections.map((node) => {
        const label = (node.rawText || "Section").trim().replace(/\s+/g, " ");
        return (
          <Row key={node.id} onClick={() => onNavigate(node.id)}>
            <RowIcon>
              <List size={15} color={OS_LEGAL_COLORS.accent} />
            </RowIcon>
            <RowLabel>{label || "Section"}</RowLabel>
            {/* Page value matches the desktop index (DocumentAnnotationIndex)
                exactly so the same section reads the same page on both. */}
            <PageBadge>p. {node.page}</PageBadge>
          </Row>
        );
      })}
    </List_>
  );
};
