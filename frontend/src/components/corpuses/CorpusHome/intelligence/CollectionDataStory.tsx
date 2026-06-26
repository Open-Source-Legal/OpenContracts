import React, { useMemo } from "react";
import { useQuery } from "@apollo/client";
import styled, { keyframes } from "styled-components";
import { BarChart3 } from "lucide-react";

import {
  OS_LEGAL_COLORS,
  OS_LEGAL_TYPOGRAPHY,
} from "../../../../assets/configurations/osLegalStyles";
import {
  GET_CORPUS_DATA_STORY,
  GetCorpusDataStoryInput,
  GetCorpusDataStoryOutput,
  CorpusDataStoryProfile,
} from "../../../../graphql/queries";

/**
 * CollectionDataStory — the "what the data says" surface of the corpus home.
 *
 * It reads the per-document structured profile (type / counterparty / effective
 * date / value) extracted by the default Collection Profile fieldset action and
 * turns it into an honest, compact data story: the collection's **composition**
 * by document type, its **shape over time** (a timeline of effective dates), and
 * its **money** (documents by value). Each panel is rendered only when that facet
 * actually has data, and the whole block self-hides until the extract has run —
 * so it adapts to whatever a collection happens to contain and never shows an
 * empty frame. As documents are added over time and their cells fill in, the
 * story fills in with them.
 */

interface CollectionDataStoryProps {
  corpusId: string;
  testId?: string;
}

// ---------------------------------------------------------------------------
// Aggregation
// ---------------------------------------------------------------------------

interface TypeSlice {
  label: string;
  count: number;
}
interface DatedDoc {
  title: string;
  t: number; // epoch ms
  iso: string;
}
interface ValuedDoc {
  title: string;
  party: string | null;
  value: number;
}

const cleanLabel = (s: string | null | undefined): string =>
  (s ?? "").trim().replace(/\.$/, "");

function parseIso(d: string | null | undefined): number | null {
  if (!d) return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(d.trim());
  if (!m) return null;
  const t = Date.parse(`${m[1]}-${m[2]}-${m[3]}T00:00:00Z`);
  return Number.isNaN(t) ? null : t;
}

const fmtMoney = (n: number): string => {
  if (n >= 1_000_000)
    return `$${(n / 1_000_000).toFixed(n >= 10_000_000 ? 0 : 1)}M`;
  if (n >= 1_000) return `$${Math.round(n / 1_000)}K`;
  return `$${Math.round(n)}`;
};

function aggregate(profiles: CorpusDataStoryProfile[]) {
  const typeMap = new Map<string, number>();
  const dated: DatedDoc[] = [];
  const valued: ValuedDoc[] = [];

  for (const p of profiles) {
    const type = cleanLabel(p.type);
    if (type) typeMap.set(type, (typeMap.get(type) ?? 0) + 1);

    const t = parseIso(p.effectiveDate);
    if (t !== null)
      dated.push({ title: p.title, t, iso: p.effectiveDate!.slice(0, 10) });

    if (typeof p.value === "number" && p.value > 0) {
      valued.push({
        title: p.title,
        party: cleanLabel(p.party) || null,
        value: p.value,
      });
    }
  }

  const types: TypeSlice[] = Array.from(typeMap.entries())
    .map(([label, count]) => ({ label, count }))
    .sort((a, b) => b.count - a.count);

  dated.sort((a, b) => a.t - b.t);
  valued.sort((a, b) => b.value - a.value);

  const totalValue = valued.reduce((s, v) => s + v.value, 0);

  return { types, dated, valued, totalValue };
}

// ---------------------------------------------------------------------------
// Styling
// ---------------------------------------------------------------------------

const fadeUp = keyframes`
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
`;

const Card = styled.section`
  display: flex;
  flex-direction: column;
  gap: 1.75rem;
  width: 100%;
  padding: 1.5rem 1.5rem 1.75rem;
  background: ${OS_LEGAL_COLORS.surfaceLight};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 14px;
  animation: ${fadeUp} 0.5s ease both;
`;

const Title = styled.div`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.875rem;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textPrimary};

  svg {
    width: 16px;
    height: 16px;
    color: ${OS_LEGAL_COLORS.primaryBlue};
  }
`;

const Figures = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 2.25rem;
`;

const Figure = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
`;

const FigureValue = styled.span`
  font-family: ${OS_LEGAL_TYPOGRAPHY.fontFamilySerif};
  font-size: clamp(1.65rem, 4vw, 2.1rem);
  font-weight: 600;
  line-height: 1;
  color: ${OS_LEGAL_COLORS.textPrimary};
  font-variant-numeric: tabular-nums;
`;

const FigureLabel = styled.span`
  font-size: 0.68rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: ${OS_LEGAL_COLORS.textMuted};
`;

const PanelLabel = styled.div`
  font-size: 0.7rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  color: ${OS_LEGAL_COLORS.textMuted};
  margin-bottom: 0.85rem;
`;

const Panel = styled.div`
  width: 100%;
`;

// --- composition bars ------------------------------------------------------

const Bars = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.55rem;
`;

const BarRow = styled.div`
  display: grid;
  grid-template-columns: minmax(120px, 38%) 1fr auto;
  align-items: center;
  gap: 0.75rem;
`;

const BarName = styled.span`
  font-size: 0.82rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
`;

const BarTrack = styled.div`
  height: 9px;
  border-radius: 999px;
  background: ${OS_LEGAL_COLORS.surfaceHover};
  overflow: hidden;
`;

const BarFill = styled.div<{ $pct: number }>`
  height: 100%;
  width: ${(p) => Math.max(4, p.$pct)}%;
  border-radius: 999px;
  background: ${OS_LEGAL_COLORS.primaryBlue};
  opacity: 0.62;
  transition: width 0.6s ease;
`;

const BarVal = styled.span`
  font-size: 0.78rem;
  color: ${OS_LEGAL_COLORS.textMuted};
  font-variant-numeric: tabular-nums;
  min-width: 2.5ch;
  text-align: right;
`;

// --- timeline --------------------------------------------------------------

const TimelineWrap = styled.div`
  width: 100%;
  svg {
    display: block;
    width: 100%;
    height: auto;
  }
`;

const TIMELINE_W = 720;
const TIMELINE_H = 86;

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export const CollectionDataStory: React.FC<CollectionDataStoryProps> = ({
  corpusId,
  testId = "collection-data-story",
}) => {
  const variables = useMemo(() => ({ corpusId }), [corpusId]);
  const { data, loading } = useQuery<
    GetCorpusDataStoryOutput,
    GetCorpusDataStoryInput
  >(GET_CORPUS_DATA_STORY, {
    variables,
    // Missing resolver / errors must self-hide, never crash the article.
    errorPolicy: "all",
    fetchPolicy: "cache-and-network",
  });

  const profiles = data?.corpusDataStory?.profiles ?? [];
  const { types, dated, valued, totalValue } = useMemo(
    () => aggregate(profiles),
    [profiles]
  );

  // Self-hide until there is at least one extracted facet to show.
  if (loading && profiles.length === 0) return null;
  if (types.length === 0 && dated.length === 0 && valued.length === 0)
    return null;

  const maxTypeCount = types.reduce((m, t) => Math.max(m, t.count), 1);
  const maxValue = valued.reduce((m, v) => Math.max(m, v.value), 1);

  // Date-span headline + timeline geometry.
  const tMin = dated.length ? dated[0].t : 0;
  const tMax = dated.length ? dated[dated.length - 1].t : 0;
  const spanDen = Math.max(1, tMax - tMin);
  const yearOf = (t: number) => new Date(t).getUTCFullYear();
  const baselineY = TIMELINE_H - 30;

  const figures: { value: string; label: string }[] = [];
  if (totalValue > 0)
    figures.push({ value: fmtMoney(totalValue), label: "Total value" });
  if (dated.length)
    figures.push({
      value:
        yearOf(tMin) === yearOf(tMax)
          ? `${yearOf(tMin)}`
          : `${yearOf(tMin)}–${yearOf(tMax)}`,
      label: dated.length === 1 ? "Effective" : "Spanning",
    });
  if (types.length)
    figures.push({
      value: String(types.length),
      label: types.length === 1 ? "Document type" : "Document types",
    });

  return (
    <Card data-testid={testId}>
      <Title>
        <BarChart3 />
        What the collection says
      </Title>

      {figures.length > 0 && (
        <Figures data-testid={`${testId}-figures`}>
          {figures.map((f) => (
            <Figure key={f.label}>
              <FigureValue>{f.value}</FigureValue>
              <FigureLabel>{f.label}</FigureLabel>
            </Figure>
          ))}
        </Figures>
      )}

      {types.length > 0 && (
        <Panel data-testid={`${testId}-types`}>
          <PanelLabel>By document type</PanelLabel>
          <Bars>
            {types.map((t) => (
              <BarRow key={t.label}>
                <BarName title={t.label}>{t.label}</BarName>
                <BarTrack>
                  <BarFill $pct={(t.count / maxTypeCount) * 100} />
                </BarTrack>
                <BarVal>{t.count}</BarVal>
              </BarRow>
            ))}
          </Bars>
        </Panel>
      )}

      {dated.length > 1 && (
        <Panel data-testid={`${testId}-timeline`}>
          <PanelLabel>Effective dates over time</PanelLabel>
          <TimelineWrap>
            <svg
              viewBox={`0 0 ${TIMELINE_W} ${TIMELINE_H}`}
              role="img"
              aria-label="Timeline of document effective dates"
            >
              {/* axis */}
              <line
                x1={8}
                y1={baselineY}
                x2={TIMELINE_W - 8}
                y2={baselineY}
                stroke={OS_LEGAL_COLORS.border}
                strokeWidth={1}
              />
              {/* end-year labels */}
              <text
                x={8}
                y={baselineY + 20}
                fontSize={11}
                fill={OS_LEGAL_COLORS.textMuted}
                fontWeight={600}
              >
                {yearOf(tMin)}
              </text>
              <text
                x={TIMELINE_W - 8}
                y={baselineY + 20}
                fontSize={11}
                textAnchor="end"
                fill={OS_LEGAL_COLORS.textMuted}
                fontWeight={600}
              >
                {yearOf(tMax)}
              </text>
              {/* a tick + dot per document */}
              {dated.map((d, i) => {
                const x = 8 + ((d.t - tMin) / spanDen) * (TIMELINE_W - 16);
                return (
                  <g key={`${d.iso}-${i}`}>
                    <line
                      x1={x}
                      y1={baselineY - 7}
                      x2={x}
                      y2={baselineY + 7}
                      stroke={OS_LEGAL_COLORS.border}
                      strokeWidth={1}
                    />
                    <circle
                      cx={x}
                      cy={baselineY}
                      r={5}
                      fill="white"
                      stroke={OS_LEGAL_COLORS.primaryBlue}
                      strokeWidth={2}
                    >
                      <title>
                        {d.title} · {d.iso}
                      </title>
                    </circle>
                  </g>
                );
              })}
            </svg>
          </TimelineWrap>
        </Panel>
      )}

      {valued.length > 0 && (
        <Panel data-testid={`${testId}-values`}>
          <PanelLabel>By value</PanelLabel>
          <Bars>
            {valued.slice(0, 6).map((v, i) => (
              <BarRow key={`${v.title}-${i}`}>
                <BarName title={v.party || v.title}>
                  {v.party || v.title}
                </BarName>
                <BarTrack>
                  <BarFill $pct={(v.value / maxValue) * 100} />
                </BarTrack>
                <BarVal>{fmtMoney(v.value)}</BarVal>
              </BarRow>
            ))}
          </Bars>
        </Panel>
      )}
    </Card>
  );
};
