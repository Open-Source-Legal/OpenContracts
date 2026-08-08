import React, { useCallback, useMemo, useState } from "react";
import { useQuery, useReactiveVar } from "@apollo/client";
import { useNavigate } from "react-router-dom";
import styled, { keyframes } from "styled-components";
import { ArrowUpRight, ChevronDown } from "lucide-react";

import {
  OS_LEGAL_COLORS,
  OS_LEGAL_TYPOGRAPHY,
} from "../../../../assets/configurations/osLegalStyles";
import { CORPUS_DOCUMENTS_TOC_LIMIT } from "../../../../assets/configurations/constants";
import {
  GET_CORPUS_COLLECTION_DOCS,
  GetCorpusCollectionDocsInput,
  GetCorpusCollectionDocsOutput,
  GET_GOVERNANCE_GRAPH,
  GetGovernanceGraphInputType,
  GetGovernanceGraphOutputType,
} from "../../../../graphql/queries";
import { openedCorpus } from "../../../../graphql/cache";
import { useNavigateToDocumentById } from "../../../../hooks/useNavigateToDocumentById";
import { navigateToRelationshipDocument } from "../../../../utils/navigationUtils";
import { IntelligenceSetupBanner } from "./IntelligenceSetupBanner";

/**
 * IntelligencePanel — the "At a glance" of the corpus-home article, rebuilt as
 * an **editorial collection overview**.
 *
 * The earlier version led with raw counts ("1,097 annotations") and a
 * "dominant labels" list that surfaced the parser's own structural scaffolding
 * (text / picture / page-header / section-header). For a typical collection
 * that reads as noise dressed up as insight. This version answers the only
 * question that matters at a glance — *what is in this collection?* — with two
 * honest, universal moves:
 *
 *   1. A restrained metric band: documents, pages, and (when present) the
 *      number of law references the collection makes. No annotation-token count.
 *   2. A magazine-style **documents index**: every document as a numbered entry
 *      with its one-line description and page weight, click-through to the doc.
 *      This is simultaneously the insight (the collection, made legible) and the
 *      way to dive deeper (open any document).
 *
 * Both are derived from data every corpus has after ingest, so the panel never
 * degrades into an empty/parser-noise state regardless of subject matter.
 */

interface IntelligencePanelProps {
  corpusId: string;
  testId?: string;
}

// Keep the home a concise teaser: preview the first few documents and reveal
// the rest on demand. A 10-document index is fine to unfurl; a 200-document
// one should not dump the whole library onto the landing.
const INDEX_PREVIEW_CAP = 6;

// ---------------------------------------------------------------------------
// Motion
// ---------------------------------------------------------------------------

const fadeUp = keyframes`
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
`;

const shimmer = keyframes`
  0% { opacity: 0.45; }
  50% { opacity: 0.85; }
  100% { opacity: 0.45; }
`;

// ---------------------------------------------------------------------------
// Layout
// ---------------------------------------------------------------------------

const Panel = styled.div`
  display: flex;
  flex-direction: column;
  gap: 2rem;
  width: 100%;
`;

const MetricBand = styled.div`
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 2.5rem;
  padding-bottom: 0.25rem;

  @media (max-width: 600px) {
    gap: 1.75rem;
  }
`;

const Metric = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  animation: ${fadeUp} 0.5s ease both;
`;

const MetricValue = styled.span`
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySerif};
  font-size: clamp(2rem, 5vw, 2.6rem);
  font-weight: 600;
  line-height: 1;
  letter-spacing: -0.01em;
  color: ${OS_LEGAL_COLORS.textPrimary};
  font-variant-numeric: tabular-nums;
`;

const MetricLabel = styled.span`
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  color: ${OS_LEGAL_COLORS.textMuted};
`;

const Section = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
`;

const SectionEyebrow = styled.div`
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 1rem;
  padding-bottom: 0.5rem;
  border-bottom: 1px solid ${OS_LEGAL_COLORS.border};

  span:first-child {
    font-size: 0.72rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.16em;
    color: ${OS_LEGAL_COLORS.textMuted};
  }
  span:last-child {
    font-size: 0.72rem;
    color: ${OS_LEGAL_COLORS.textMuted};
    font-variant-numeric: tabular-nums;
  }
`;

const Index = styled.ul`
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
`;

const Entry = styled.li<{ $i: number }>`
  display: grid;
  grid-template-columns: 2.25rem 1fr auto;
  align-items: start;
  gap: 0 1rem;
  padding: 0.95rem 0.75rem 0.95rem 0.25rem;
  border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
  cursor: pointer;
  border-radius: 8px;
  transition: background 0.16s ease, box-shadow 0.16s ease;
  animation: ${fadeUp} 0.5s ease both;
  animation-delay: ${(p) => 0.04 * p.$i + 0.05}s;

  &:hover {
    background: ${OS_LEGAL_COLORS.surfaceHover};
    box-shadow: inset 3px 0 0 ${OS_LEGAL_COLORS.primaryBlue};
  }
  &:hover .ix {
    color: ${OS_LEGAL_COLORS.primaryBlue};
  }
  &:hover .open-cue {
    opacity: 1;
    transform: translate(0, 0);
  }
  &:focus-visible {
    outline: none;
    background: ${OS_LEGAL_COLORS.surfaceHover};
    box-shadow: inset 3px 0 0 ${OS_LEGAL_COLORS.primaryBlue};
  }
  &:last-child {
    border-bottom: none;
  }
`;

const EntryNum = styled.span`
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySerif};
  font-size: 1.05rem;
  font-weight: 500;
  line-height: 1.45;
  color: ${OS_LEGAL_COLORS.textMuted};
  font-variant-numeric: tabular-nums;
  padding-top: 0.05rem;
  transition: color 0.16s ease;
`;

const EntryBody = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  min-width: 0;
`;

const EntryTitle = styled.span`
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySerif};
  font-size: 1.02rem;
  font-weight: 600;
  line-height: 1.3;
  color: ${OS_LEGAL_COLORS.textPrimary};
`;

const EntryDesc = styled.p`
  margin: 0;
  font-size: 0.84rem;
  line-height: 1.5;
  color: ${OS_LEGAL_COLORS.textSecondary};
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
`;

const EntryMeta = styled.div`
  display: flex;
  align-items: center;
  gap: 0.6rem;
  margin-top: 0.1rem;
`;

const WeightTrack = styled.span`
  width: 56px;
  height: 4px;
  border-radius: 999px;
  background: ${OS_LEGAL_COLORS.surfaceHover};
  overflow: hidden;
`;

const WeightFill = styled.span<{ $pct: number }>`
  display: block;
  height: 100%;
  width: ${(p) => Math.max(8, p.$pct)}%;
  border-radius: 999px;
  background: ${OS_LEGAL_COLORS.primaryBlue};
  opacity: 0.5;
`;

const MetaText = styled.span`
  font-size: 0.72rem;
  color: ${OS_LEGAL_COLORS.textMuted};
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
`;

const OpenCue = styled.span`
  display: inline-flex;
  align-items: center;
  color: ${OS_LEGAL_COLORS.primaryBlue};
  opacity: 0;
  transform: translate(-3px, 2px);
  transition: opacity 0.16s ease, transform 0.16s ease;
  padding-top: 0.15rem;

  svg {
    width: 16px;
    height: 16px;
  }
`;

const SkeletonRow = styled.div`
  height: 64px;
  border-radius: 10px;
  background: ${OS_LEGAL_COLORS.surfaceHover};
  animation: ${shimmer} 1.2s ease-in-out infinite;
`;

const EmptyHint = styled.div`
  font-size: 0.8rem;
  color: ${OS_LEGAL_COLORS.textMuted};
  padding: 0.5rem 0;
`;

const ShowMore = styled.button`
  align-self: flex-start;
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  margin-top: 0.85rem;
  padding: 0.35rem 0;
  background: none;
  border: none;
  font-size: 0.8rem;
  font-weight: 600;
  letter-spacing: 0.01em;
  color: ${OS_LEGAL_COLORS.primaryBlue};
  cursor: pointer;

  svg {
    width: 15px;
    height: 15px;
    transition: transform 0.2s ease;
  }
  &:hover {
    text-decoration: underline;
  }
  &[data-open="true"] svg {
    transform: rotate(180deg);
  }
`;

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export const IntelligencePanel: React.FC<IntelligencePanelProps> = ({
  corpusId,
  testId = "corpus-intelligence-panel",
}) => {
  const navigateToDocumentById = useNavigateToDocumentById();
  const navigate = useNavigate();
  const activeCorpus = useReactiveVar(openedCorpus);
  const [showAll, setShowAll] = useState(false);
  const variables = useMemo(
    // ``documents(inCorpusWithId:)`` excludes markdown unless asked otherwise
    // (config/graphql/filters.py::filter_queryset) — a default meant for
    // extractors and analyzers. This panel's headline metric is the document
    // count, so without the flag a workspace holding only generated artifacts
    // (saved chat answers, research reports) reads "0 DOCUMENTS" and "No
    // documents in this collection yet" while the corpus header says 1.
    () => ({
      corpusId,
      limit: CORPUS_DOCUMENTS_TOC_LIMIT,
      includeCaml: true,
    }),
    [corpusId]
  );

  const { data, loading, error } = useQuery<
    GetCorpusCollectionDocsOutput,
    GetCorpusCollectionDocsInput
  >(GET_CORPUS_COLLECTION_DOCS, { variables });

  // References metric — shares the governance-graph query (same corpusId, no
  // limit) the graph embed below already issues, so Apollo serves it from cache.
  const { data: govData } = useQuery<
    GetGovernanceGraphOutputType,
    GetGovernanceGraphInputType
  >(GET_GOVERNANCE_GRAPH, {
    variables: useMemo(() => ({ corpusId }), [corpusId]),
  });

  // The backend issues no ORDER BY on this connection (see
  // GET_CORPUS_COLLECTION_DOCS), so Postgres is free to return rows in
  // arbitrary heap order — sort client-side so the "01 / 02 / ..." editorial
  // index below stays stable across reloads, matching the alphabetical sort
  // DocumentTableOfContents.tsx already uses for the same list.
  const docs = useMemo(
    () =>
      (data?.documents?.edges ?? [])
        .map((e) => e.node)
        .sort(
          (a, b) =>
            (a.title || "").localeCompare(b.title || "") ||
            a.id.localeCompare(b.id)
        ),
    [data]
  );

  const totalDocs = data?.documents?.totalCount ?? docs.length;
  const totalPages = useMemo(
    () => docs.reduce((sum, d) => sum + (d.pageCount ?? 0), 0),
    [docs]
  );
  const maxPages = useMemo(
    () => docs.reduce((m, d) => Math.max(m, d.pageCount ?? 0), 1),
    [docs]
  );
  const referenceCount = govData?.governanceGraph?.mentionCount ?? 0;

  const handleDocumentOpen = useCallback(
    (doc: { id: string; title: string; slug: string }) => {
      // The index is corpus-scoped. Keep that context in the document URL so
      // the viewer recognizes the document as already belonging to this corpus.
      if (activeCorpus?.id === corpusId) {
        navigateToRelationshipDocument(
          doc,
          activeCorpus,
          navigate,
          window.location.pathname
        );
        return;
      }

      // CAML embeds can also be rendered outside a loaded corpus route.
      void navigateToDocumentById(doc.id);
    },
    [activeCorpus, corpusId, navigate, navigateToDocumentById]
  );

  const shownDocs = showAll ? docs : docs.slice(0, INDEX_PREVIEW_CAP);

  const initialLoading = loading && docs.length === 0;
  const errored = !!error && docs.length === 0;

  const metrics: { value: number; label: string }[] = [
    { value: totalDocs, label: totalDocs === 1 ? "Document" : "Documents" },
    { value: totalPages, label: totalPages === 1 ? "Page" : "Pages" },
  ];
  if (referenceCount > 0) {
    metrics.push({
      value: referenceCount,
      label: referenceCount === 1 ? "Law reference" : "Law references",
    });
  }

  return (
    <Panel data-testid={testId}>
      {/* One-click bundle setup — silent for anon / fully-set-up corpora. */}
      <IntelligenceSetupBanner corpusId={corpusId} />

      <MetricBand data-testid={`${testId}-metrics`}>
        {metrics.map((m, i) => (
          <Metric key={m.label} style={{ animationDelay: `${0.05 * i}s` }}>
            <MetricValue>{m.value.toLocaleString()}</MetricValue>
            <MetricLabel>{m.label}</MetricLabel>
          </Metric>
        ))}
      </MetricBand>

      <Section>
        <SectionEyebrow>
          <span>The collection</span>
          {!initialLoading && !errored && (
            <span>
              {totalDocs} {totalDocs === 1 ? "document" : "documents"}
            </span>
          )}
        </SectionEyebrow>

        {initialLoading ? (
          <div
            style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}
          >
            {[0, 1, 2, 3].map((i) => (
              <SkeletonRow key={i} data-testid={`${testId}-skeleton-${i}`} />
            ))}
          </div>
        ) : errored ? (
          <EmptyHint data-testid={`${testId}-error`}>
            Couldn't load the collection. Please try again.
          </EmptyHint>
        ) : docs.length === 0 ? (
          <EmptyHint>No documents in this collection yet.</EmptyHint>
        ) : (
          <>
            <Index data-testid={`${testId}-index`}>
              {shownDocs.map((doc, i) => {
                const pages = doc.pageCount ?? 0;
                const pct = Math.round((pages / maxPages) * 100);
                const hasDesc =
                  !!doc.description && doc.description.trim().length > 0;
                return (
                  <Entry
                    key={doc.id}
                    $i={i}
                    onClick={() => handleDocumentOpen(doc)}
                    data-testid={`${testId}-entry`}
                    role="link"
                    tabIndex={0}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        handleDocumentOpen(doc);
                      }
                    }}
                  >
                    <EntryNum className="ix">
                      {String(i + 1).padStart(2, "0")}
                    </EntryNum>
                    <EntryBody>
                      <EntryTitle>
                        {doc.title || "Untitled document"}
                      </EntryTitle>
                      {hasDesc && <EntryDesc>{doc.description}</EntryDesc>}
                      <EntryMeta>
                        {pages > 0 && (
                          <>
                            <WeightTrack aria-hidden="true">
                              <WeightFill $pct={pct} />
                            </WeightTrack>
                            <MetaText>
                              {pages} {pages === 1 ? "page" : "pages"}
                            </MetaText>
                          </>
                        )}
                      </EntryMeta>
                    </EntryBody>
                    <OpenCue className="open-cue" aria-hidden="true">
                      <ArrowUpRight />
                    </OpenCue>
                  </Entry>
                );
              })}
            </Index>
            {docs.length > INDEX_PREVIEW_CAP && (
              <ShowMore
                data-open={showAll}
                onClick={() => setShowAll((v) => !v)}
                data-testid={`${testId}-show-more`}
              >
                {/* Label the loaded count, not the server total — the query
                    fetches at most 100, so "Show all" must not promise more
                    than expanding actually reveals. */}
                {showAll
                  ? "Show fewer"
                  : `Show all ${docs.length.toLocaleString()} documents`}
                <ChevronDown />
              </ShowMore>
            )}
          </>
        )}
      </Section>
    </Panel>
  );
};
