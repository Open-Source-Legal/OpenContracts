import React, { useMemo } from "react";
import { useQuery } from "@apollo/client";
import { useNavigate } from "react-router-dom";
import styled, { keyframes } from "styled-components";
import {
  ArrowDownLeft,
  ArrowUpRight,
  Check,
  CircleDashed,
  Clock,
  Link2,
} from "lucide-react";

import { OS_LEGAL_COLORS } from "../../../assets/configurations/osLegalStyles";
import {
  GOVERNANCE_GRAPH_COLORS,
  GOVERNANCE_GRAPH_EDGE_TYPES,
} from "../../../assets/configurations/constants";
import {
  GET_CORPUS_REFERENCES_FOR_DOCUMENT,
  GetCorpusReferencesForDocumentInputType,
  GetCorpusReferencesForDocumentOutputType,
  CorpusReferenceRow,
} from "../../../graphql/queries";
import { useNavigateToDocumentById } from "../../../hooks/useNavigateToDocumentById";
import { formatCanonicalLawKey } from "../../../utils/formatters";
import { openSafeUrl } from "../../annotator/utils/urlAnnotation";

/**
 * DocumentReferencesPanel — one document's slice of the corpus reference web.
 *
 * Two ledgers:
 *   • **Cites** (outbound)  — what this document points at: statutory
 *     citations grouped by canonical key (mention-counted), exhibit
 *     cross-references, internal section refs.
 *   • **Cited by** (inbound) — every document whose references resolve here
 *     (e.g. the S-1 primaries citing this exhibit, or every filing citing
 *     this statute section).
 *
 * Rows with an in-system target navigate on click: outbound law/document rows
 * follow the mention's canonical ``link_url``; inbound rows resolve the
 * source document's slugs and navigate there.
 */

const REFERENCE_TYPE_META: Record<string, { label: string; color: string }> = {
  LAW: { label: "Law", color: GOVERNANCE_GRAPH_COLORS.LAW_DEFAULT },
  DOCUMENT: { label: "Exhibit", color: OS_LEGAL_COLORS.primaryBlue },
  SECTION: { label: "Section", color: OS_LEGAL_COLORS.textSecondary },
  DEFINED_TERM: { label: "Term", color: GOVERNANCE_GRAPH_COLORS.DEFINED_TERM },
};

const TYPE_ORDER = ["LAW", "DOCUMENT", "SECTION", "DEFINED_TERM"];

interface DocumentReferencesPanelProps {
  documentId: string;
  corpusId?: string;
}

const PanelBody = styled.div`
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
  padding: 0.75rem 1rem 1.25rem;
`;

const SectionTitle = styled.div`
  display: flex;
  align-items: center;
  gap: 0.45rem;
  font-size: 0.75rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: ${OS_LEGAL_COLORS.textMuted};

  svg {
    width: 14px;
    height: 14px;
  }

  .count {
    font-weight: 600;
    color: ${OS_LEGAL_COLORS.textSecondary};
    font-variant-numeric: tabular-nums;
  }
`;

const RefList = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  margin-top: 0.5rem;
`;

const RefRow = styled.button<{ $clickable: boolean }>`
  display: flex;
  align-items: flex-start;
  gap: 0.6rem;
  width: 100%;
  text-align: left;
  padding: 0.55rem 0.7rem;
  background: white;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 10px;
  cursor: ${(p) => (p.$clickable ? "pointer" : "default")};
  transition: border-color 0.15s ease, background 0.15s ease;

  ${(p) =>
    p.$clickable &&
    `&:hover {
      border-color: ${OS_LEGAL_COLORS.borderHover};
      background: ${OS_LEGAL_COLORS.surfaceHover};
    }`}
`;

const TypeChip = styled.span<{ $color: string }>`
  flex-shrink: 0;
  margin-top: 1px;
  padding: 0.1rem 0.45rem;
  border-radius: 999px;
  font-size: 0.6875rem;
  font-weight: 700;
  color: white;
  background: ${(p) => p.$color};
`;

const RefContent = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  min-width: 0;
`;

const RefHead = styled.span`
  display: flex;
  align-items: baseline;
  gap: 0.45rem;
  font-size: 0.8125rem;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textPrimary};

  .mentions {
    font-weight: 600;
    font-size: 0.6875rem;
    color: ${OS_LEGAL_COLORS.textMuted};
    font-variant-numeric: tabular-nums;
  }
`;

const RefSnippet = styled.span`
  font-size: 0.75rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
`;

// Right-aligned status column: a "Linked" / "Awaiting source" chip makes a
// reference's resolution state scannable at a glance, instead of relying on a
// faint italic note + cursor change to tell a live link from a pending one.
const RefStatus = styled.div`
  flex-shrink: 0;
  align-self: center;
  margin-left: auto;
  padding-left: 0.4rem;
`;

const StatusChip = styled.span<{
  $variant: "linked" | "awaiting" | "provisional";
}>`
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.12rem 0.45rem 0.12rem 0.4rem;
  border-radius: 999px;
  font-size: 0.6875rem;
  font-weight: 600;
  white-space: nowrap;

  svg {
    width: 12px;
    height: 12px;
  }

  ${(p) =>
    p.$variant === "linked"
      ? `color: ${OS_LEGAL_COLORS.accent}; background: ${OS_LEGAL_COLORS.accentSurface};`
      : p.$variant === "provisional"
      ? `color: ${OS_LEGAL_COLORS.provisionalText}; background: ${OS_LEGAL_COLORS.provisionalSurface};`
      : `color: ${OS_LEGAL_COLORS.awaitingText}; background: ${OS_LEGAL_COLORS.awaitingSurface};`}
`;

// Compact linked/awaiting breakdown for the "Cites" section header.
const SummaryCounts = styled.span`
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  margin-left: auto;
  text-transform: none;
  letter-spacing: 0;
  font-weight: 600;
  font-size: 0.6875rem;

  .linked {
    color: ${OS_LEGAL_COLORS.accent};
  }
  .provisional {
    color: ${OS_LEGAL_COLORS.provisionalText};
  }
  .awaiting {
    color: ${OS_LEGAL_COLORS.awaitingText};
  }
  .dot {
    color: ${OS_LEGAL_COLORS.textMuted};
  }
`;

const EmptyState = styled.div`
  padding: 1.5rem 1rem;
  text-align: center;
  font-size: 0.8125rem;
  color: ${OS_LEGAL_COLORS.textMuted};
`;

const shimmer = keyframes`
  0% { opacity: 0.45; }
  50% { opacity: 0.8; }
  100% { opacity: 0.45; }
`;

const RowSkeleton = styled.div`
  height: 52px;
  border-radius: 10px;
  background: ${OS_LEGAL_COLORS.surfaceHover};
  animation: ${shimmer} 1.2s ease-in-out infinite;
`;

interface OutboundGroup {
  key: string;
  referenceType: string;
  head: string;
  snippet?: string | null;
  mentions: number;
  linkUrl?: string | null;
  resolved: boolean;
  // Any mention in the group written by an in-flight (not-yet-finalized)
  // enrichment run — drives the "In progress" badge.
  provisional: boolean;
}

export const DocumentReferencesPanel: React.FC<
  DocumentReferencesPanelProps
> = ({ documentId, corpusId }) => {
  const navigate = useNavigate();
  const navigateToDocument = useNavigateToDocumentById();

  const { data, loading, error } = useQuery<
    GetCorpusReferencesForDocumentOutputType,
    GetCorpusReferencesForDocumentInputType
  >(GET_CORPUS_REFERENCES_FOR_DOCUMENT, {
    variables: { corpusId: corpusId || "", documentId },
    skip: !corpusId,
  });

  const rows = useMemo(
    () => (data?.corpusReferences?.edges ?? []).map((e) => e.node),
    [data]
  );

  const { outbound, inbound } = useMemo(() => {
    const out: CorpusReferenceRow[] = [];
    const inn: CorpusReferenceRow[] = [];
    rows.forEach((row) => {
      if (row.sourceAnnotation?.document?.id === documentId) out.push(row);
      else if (row.targetDocument?.id === documentId) inn.push(row);
    });
    return { outbound: out, inbound: inn };
  }, [rows, documentId]);

  // Outbound rows group by (type, canonical key | target doc): "DGCL § 145
  // ×3" reads better than three identical rows.
  const outboundGroups = useMemo(() => {
    const groups = new Map<string, OutboundGroup>();
    outbound.forEach((row) => {
      const groupKey = `${row.referenceType}:${
        row.canonicalKey || row.targetDocument?.id || row.id
      }`;
      const existing = groups.get(groupKey);
      if (existing) {
        existing.mentions += 1;
        existing.linkUrl = existing.linkUrl || row.sourceAnnotation?.linkUrl;
        existing.provisional =
          existing.provisional || Boolean(row.isProvisional);
        return;
      }
      const head =
        row.referenceType === GOVERNANCE_GRAPH_EDGE_TYPES.LAW &&
        row.canonicalKey
          ? formatCanonicalLawKey(row.canonicalKey)
          : row.targetDocument?.title ||
            (row.canonicalKey
              ? formatCanonicalLawKey(row.canonicalKey)
              : null) ||
            row.sourceAnnotation?.rawText ||
            "Reference";
      groups.set(groupKey, {
        key: groupKey,
        referenceType: row.referenceType,
        head,
        snippet: row.sourceAnnotation?.rawText,
        mentions: 1,
        linkUrl: row.sourceAnnotation?.linkUrl,
        resolved: row.resolutionStatus === "RESOLVED",
        provisional: Boolean(row.isProvisional),
      });
    });
    return [...groups.values()].sort(
      (a, b) =>
        TYPE_ORDER.indexOf(a.referenceType) -
          TYPE_ORDER.indexOf(b.referenceType) || b.mentions - a.mentions
    );
  }, [outbound]);

  // Inbound rows group by source document.
  const inboundGroups = useMemo(() => {
    const groups = new Map<
      string,
      {
        docId: string;
        title: string;
        mentions: number;
        snippet?: string | null;
      }
    >();
    inbound.forEach((row) => {
      const doc = row.sourceAnnotation?.document;
      if (!doc) return;
      const existing = groups.get(doc.id);
      if (existing) {
        existing.mentions += 1;
        return;
      }
      groups.set(doc.id, {
        docId: doc.id,
        title: doc.title || "Untitled document",
        mentions: 1,
        snippet: row.sourceAnnotation?.rawText,
      });
    });
    return [...groups.values()].sort((a, b) => b.mentions - a.mentions);
  }, [inbound]);

  // Header summary, matching the per-row badge precedence: a provisional group
  // counts as "in progress" (not linked/awaiting); otherwise a group is "linked"
  // when it carries a navigable link_url, and a LAW row with no resolved target
  // is "awaiting" ingestion.
  const provisionalCount = outboundGroups.filter((g) => g.provisional).length;
  const linkedCount = outboundGroups.filter(
    (g) => !g.provisional && Boolean(g.linkUrl)
  ).length;
  const awaitingCount = outboundGroups.filter(
    (g) =>
      !g.provisional &&
      !g.resolved &&
      g.referenceType === GOVERNANCE_GRAPH_EDGE_TYPES.LAW
  ).length;

  if (!corpusId) {
    return (
      <EmptyState data-testid="references-panel-no-corpus">
        References are tracked per collection — open this document inside a
        corpus to see its reference web.
      </EmptyState>
    );
  }

  if (loading && rows.length === 0) {
    return (
      <PanelBody data-testid="references-panel-loading">
        <RowSkeleton />
        <RowSkeleton />
        <RowSkeleton />
      </PanelBody>
    );
  }

  if (error && rows.length === 0) {
    return (
      <EmptyState data-testid="references-panel-error">
        Couldn't load references. Please try again.
      </EmptyState>
    );
  }

  if (rows.length === 0) {
    return (
      <EmptyState data-testid="references-panel-empty">
        <Link2
          size={18}
          style={{ marginBottom: 6, color: OS_LEGAL_COLORS.textMuted }}
        />
        <div>
          No references mapped for this document yet. Run reference enrichment
          on the collection to weave its citation web.
        </div>
      </EmptyState>
    );
  }

  return (
    <PanelBody data-testid="references-panel">
      {outboundGroups.length > 0 && (
        <div>
          <SectionTitle>
            <ArrowUpRight />
            Cites
            <span className="count">{outboundGroups.length}</span>
            {linkedCount + provisionalCount + awaitingCount > 0 && (
              <SummaryCounts data-testid="references-panel-summary">
                {linkedCount > 0 && (
                  <span className="linked">{linkedCount} linked</span>
                )}
                {linkedCount > 0 && provisionalCount > 0 && (
                  <span className="dot">·</span>
                )}
                {provisionalCount > 0 && (
                  <span className="provisional">
                    {provisionalCount} in progress
                  </span>
                )}
                {(linkedCount > 0 || provisionalCount > 0) &&
                  awaitingCount > 0 && <span className="dot">·</span>}
                {awaitingCount > 0 && (
                  <span className="awaiting">{awaitingCount} awaiting</span>
                )}
              </SummaryCounts>
            )}
          </SectionTitle>
          <RefList>
            {outboundGroups.map((group) => {
              const meta =
                REFERENCE_TYPE_META[group.referenceType] ||
                REFERENCE_TYPE_META.SECTION;
              const clickable = Boolean(group.linkUrl);
              const awaiting =
                !clickable &&
                !group.resolved &&
                group.referenceType === GOVERNANCE_GRAPH_EDGE_TYPES.LAW;
              return (
                <RefRow
                  key={group.key}
                  $clickable={clickable}
                  onClick={
                    clickable
                      ? () => openSafeUrl(group.linkUrl, navigate)
                      : undefined
                  }
                  data-testid="references-panel-outbound-row"
                >
                  <TypeChip $color={meta.color}>{meta.label}</TypeChip>
                  <RefContent>
                    <RefHead>
                      {group.head}
                      {group.mentions > 1 && (
                        <span className="mentions">×{group.mentions}</span>
                      )}
                    </RefHead>
                    {group.snippet && <RefSnippet>{group.snippet}</RefSnippet>}
                  </RefContent>
                  {/* Provisional takes precedence: the reference is still being
                      written by an in-flight run, so its linked/awaiting state
                      is preliminary until the run finalizes. */}
                  {group.provisional ? (
                    <RefStatus>
                      <StatusChip
                        $variant="provisional"
                        title="Detected by an enrichment run still in progress — not finalized yet."
                        data-testid="references-panel-status-provisional"
                      >
                        <CircleDashed />
                        In progress
                      </StatusChip>
                    </RefStatus>
                  ) : clickable ? (
                    <RefStatus>
                      <StatusChip
                        $variant="linked"
                        title="Resolved — opens the cited authority"
                        data-testid="references-panel-status-linked"
                      >
                        <Check />
                        Linked
                      </StatusChip>
                    </RefStatus>
                  ) : awaiting ? (
                    <RefStatus>
                      <StatusChip
                        $variant="awaiting"
                        title="Citation detected, but the source authority is not ingested yet. Run the authority crawl to resolve it."
                        data-testid="references-panel-status-awaiting"
                      >
                        <Clock />
                        Awaiting source
                      </StatusChip>
                    </RefStatus>
                  ) : null}
                </RefRow>
              );
            })}
          </RefList>
        </div>
      )}

      {inboundGroups.length > 0 && (
        <div>
          <SectionTitle>
            <ArrowDownLeft />
            Cited by
            <span className="count">{inboundGroups.length}</span>
          </SectionTitle>
          <RefList>
            {inboundGroups.map((group) => (
              <RefRow
                key={group.docId}
                $clickable
                onClick={() => void navigateToDocument(group.docId)}
                data-testid="references-panel-inbound-row"
              >
                <TypeChip $color={OS_LEGAL_COLORS.primaryBlue}>Doc</TypeChip>
                <RefContent>
                  <RefHead>
                    {group.title}
                    {group.mentions > 1 && (
                      <span className="mentions">×{group.mentions}</span>
                    )}
                  </RefHead>
                  {group.snippet && <RefSnippet>{group.snippet}</RefSnippet>}
                </RefContent>
              </RefRow>
            ))}
          </RefList>
        </div>
      )}
    </PanelBody>
  );
};
