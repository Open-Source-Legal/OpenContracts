import React, { useMemo } from "react";
import { useQuery } from "@apollo/client";
import styled from "styled-components";
import * as d3 from "d3";

import {
  OS_LEGAL_COLORS,
  OS_LEGAL_TYPOGRAPHY,
} from "../../../../assets/configurations/osLegalStyles";
import {
  GET_CORPUS_DATA_STORY,
  GetCorpusDataStoryInput,
  GetCorpusDataStoryOutput,
} from "../../../../graphql/queries";

/**
 * SpendingBeeswarm — a standalone, poster-grade "every contract, over time, by
 * value" visualization built to be screenshot and shared (the /r/dataisbeautiful
 * artifact), not to live inside the dashboard.
 *
 * Every document in the collection is a dot, positioned on a time axis by its
 * effective date (a deterministic d3-force beeswarm so dots never overlap),
 * coloured by document type, and sized by dollar value — so the whales (a $10M
 * grant) tower over the renewals, the type-mix is legible as colour, and the
 * temporal rhythm of the collection emerges from the packing. Reads the existing
 * ``corpusDataStory`` (no extra query); self-hides until there is dated data.
 */

interface SpendingBeeswarmProps {
  corpusId: string;
  /** Configurable headline; falls back to a generic auto-derived one. */
  title?: string;
  /** Configurable one-line subtitle/takeaway under the title. */
  takeaway?: string;
  /** Configurable credit/source line (bottom-right). Generic default. */
  byline?: string;
  /** What one dot is, for the auto-derived captions (plural). Default
   * "documents" so the template reads correctly for ANY collection — a
   * contracts corpus can pass "contracts", a filings corpus "filings", etc. */
  noun?: string;
  testId?: string;
}

// Poster canvas (scales to container width via viewBox).
const VIEW_W = 1200;
const VIEW_H = 740;
const MARGIN = { top: 132, right: 48, bottom: 64, left: 48 };
const TICKS = 200;

// A curated, harmonious categorical palette — distinct but restrained, sitting
// in the same register as the os-legal system (no neon category10).
const PALETTE = [
  "#0f766e", // teal (brand)
  "#b45309", // amber
  "#1e40af", // indigo
  "#9d174d", // rose
  "#4d7c0f", // sage
  "#7e22ce", // plum
  "#0369a1", // ocean
  "#c2410c", // terracotta
  "#a16207", // gold
  "#475569", // slate
  "#0e7490", // cyan
  "#86198f", // magenta
];

interface Pt {
  title: string;
  type: string;
  party: string | null;
  t: number;
  value: number; // 0 when unvalued
  x: number;
  y: number;
  r: number;
  color: string;
  labelRow?: number;
}

const fmtMoney = (n: number): string => {
  if (n >= 1_000_000)
    return `$${(n / 1_000_000).toFixed(n >= 10_000_000 ? 1 : 1)}M`;
  if (n >= 1_000) return `$${Math.round(n / 1_000)}K`;
  return `$${Math.round(n)}`;
};

function parseIso(d: string | null | undefined): number | null {
  if (!d) return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(d);
  if (!m) return null;
  const t = Date.parse(`${m[1]}-${m[2]}-${m[3]}T00:00:00Z`);
  return Number.isNaN(t) ? null : t;
}

const Frame = styled.div`
  width: 100%;
  background: ${OS_LEGAL_COLORS.surface};
  svg {
    display: block;
    width: 100%;
    height: auto;
  }
`;

export const SpendingBeeswarm: React.FC<SpendingBeeswarmProps> = ({
  corpusId,
  title,
  takeaway,
  byline,
  noun = "documents",
  testId = "spending-beeswarm",
}) => {
  const variables = useMemo(() => ({ corpusId }), [corpusId]);
  const { data, loading } = useQuery<
    GetCorpusDataStoryOutput,
    GetCorpusDataStoryInput
  >(GET_CORPUS_DATA_STORY, {
    variables,
    errorPolicy: "all",
    fetchPolicy: "cache-and-network",
  });

  const profiles = data?.corpusDataStory?.profiles ?? [];

  const model = useMemo(() => {
    // Build dated points; every dot needs an x (date). Value drives radius.
    let raw = profiles
      .map((p) => {
        const t = parseIso(p.effectiveDate);
        if (t === null) return null;
        return {
          title: p.title,
          type: (p.type || "Other").trim() || "Other",
          party: p.party,
          t,
          value: typeof p.value === "number" && p.value > 0 ? p.value : 0,
        };
      })
      .filter(Boolean) as Omit<Pt, "x" | "y" | "r" | "color">[];

    if (raw.length === 0) return null;

    // Drop isolated early date-outliers that would stretch the time axis — a
    // single contract 14 years older than the rest (or a mis-extracted date)
    // compresses the recent bulk into a sliver. Walk up from the oldest while
    // each leading point sits >3 years before the next; keep the rest.
    const YR = 365 * 24 * 3600 * 1000;
    const sortedT = [...raw].sort((a, b) => a.t - b.t);
    let startIdx = 0;
    while (
      startIdx < sortedT.length - 1 &&
      sortedT[startIdx + 1].t - sortedT[startIdx].t > 3 * YR
    )
      startIdx++;
    const droppedEarly = startIdx;
    raw = sortedT.slice(startIdx);

    // Type colour by frequency (most common → brand teal first).
    const typeCounts = new Map<string, number>();
    raw.forEach((d) =>
      typeCounts.set(d.type, (typeCounts.get(d.type) ?? 0) + 1)
    );
    const typesByFreq = Array.from(typeCounts.entries())
      .sort((a, b) => b[1] - a[1])
      .map(([t]) => t);
    const colorFor = new Map<string, string>();
    typesByFreq.forEach((t, i) => colorFor.set(t, PALETTE[i % PALETTE.length]));

    const tExtent = d3.extent(raw, (d) => d.t) as [number, number];
    // Pad the time domain so edge dots aren't clipped.
    const pad = Math.max(
      (tExtent[1] - tExtent[0]) * 0.04,
      1000 * 60 * 60 * 24 * 30
    );
    const xScale = d3
      .scaleLinear()
      .domain([tExtent[0] - pad, tExtent[1] + pad])
      .range([MARGIN.left, VIEW_W - MARGIN.right]);

    const maxVal = d3.max(raw, (d) => d.value) || 1;
    const rScale = d3.scaleSqrt().domain([0, maxVal]).range([4, 30]);

    const midY = MARGIN.top + (VIEW_H - MARGIN.top - MARGIN.bottom) / 2;

    const nodes: Pt[] = raw.map((d, i) => ({
      ...d,
      r: d.value > 0 ? rScale(d.value) : 4.5,
      color: colorFor.get(d.type) || PALETTE[0],
      x: xScale(d.t),
      // seed y deterministically around the midline (no RNG)
      y: midY + (i % 2 === 0 ? 1 : -1) * (i % 23) * 0.6,
    }));

    const sim = d3
      .forceSimulation(nodes)
      .force("x", d3.forceX<Pt>((d) => xScale(d.t)).strength(1))
      .force("y", d3.forceY<Pt>(midY).strength(0.045))
      .force("collide", d3.forceCollide<Pt>((d) => d.r + 1.4).iterations(3))
      .stop();
    for (let i = 0; i < TICKS; i++) sim.tick();

    // clamp into band
    const top = MARGIN.top + 6;
    const bot = VIEW_H - MARGIN.bottom - 6;
    nodes.forEach((n) => {
      n.y = Math.max(top + n.r, Math.min(bot - n.r, n.y));
    });

    const years = d3.range(
      new Date(tExtent[0]).getUTCFullYear(),
      new Date(tExtent[1]).getUTCFullYear() + 1
    );

    const totalValue = raw.reduce((s, d) => s + d.value, 0);
    const valuedCount = raw.filter((d) => d.value > 0).length;
    const whales = [...nodes]
      .filter((n) => n.value > 0)
      .sort((a, b) => b.value - a.value)
      .slice(0, 4);
    // Greedy row-pack the whale labels so close-in-time ones don't overprint:
    // each label claims ~[x-46, x+46]; overflow drops to the next row up.
    const rowEnds: number[] = [];
    [...whales]
      .sort((a, b) => a.x - b.x)
      .forEach((w) => {
        const half = 46;
        let row = 0;
        while (rowEnds[row] !== undefined && rowEnds[row] > w.x - half) row++;
        w.labelRow = row;
        rowEnds[row] = w.x + half;
      });
    const legend = typesByFreq.slice(0, 8).map((t) => ({
      type: t,
      color: colorFor.get(t)!,
      count: typeCounts.get(t)!,
    }));

    return {
      nodes,
      xScale,
      years,
      totalValue,
      valuedCount,
      whales,
      legend,
      count: raw.length,
      droppedEarly,
      yearStart: years[0],
      yearEnd: years[years.length - 1],
    };
  }, [profiles]);

  if (loading && profiles.length === 0) return null;
  if (!model) return null;

  const {
    nodes,
    xScale,
    years,
    totalValue,
    whales,
    legend,
    count,
    droppedEarly,
    yearStart,
    yearEnd,
  } = model;
  const axisY = VIEW_H - MARGIN.bottom;

  const nounSingular = noun.replace(/s$/i, "");
  const heading =
    title ?? `${count.toLocaleString()} ${noun}, ${yearStart}–${yearEnd}`;
  const sub =
    takeaway ??
    `${fmtMoney(
      totalValue
    )} in total value · each dot a ${nounSingular}, sized by dollar value` +
      (droppedEarly > 0 ? ` · ${droppedEarly} earlier omitted` : "");

  return (
    <Frame data-testid={testId}>
      <svg viewBox={`0 0 ${VIEW_W} ${VIEW_H}`} role="img" aria-label={heading}>
        <defs>
          <linearGradient id="bee-bg" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#ffffff" />
            <stop offset="100%" stopColor="#fbfaf7" />
          </linearGradient>
        </defs>
        <rect width={VIEW_W} height={VIEW_H} fill="url(#bee-bg)" />

        {/* Title block */}
        <text
          x={MARGIN.left}
          y={56}
          fontFamily={OS_LEGAL_TYPOGRAPHY.fontFamilySerif}
          fontSize={34}
          fontWeight={600}
          fill={OS_LEGAL_COLORS.textPrimary}
        >
          {heading}
        </text>
        <text
          x={MARGIN.left}
          y={86}
          fontFamily={OS_LEGAL_TYPOGRAPHY.fontFamilySans}
          fontSize={15}
          fill={OS_LEGAL_COLORS.textSecondary}
        >
          {sub}
        </text>

        {/* Legend (types) */}
        <g>
          {legend.map((l, i) => {
            const lx = MARGIN.left + i * 150;
            return (
              <g key={l.type} transform={`translate(${lx}, 106)`}>
                <circle
                  cx={5}
                  cy={-4}
                  r={5}
                  fill={l.color}
                  fillOpacity={0.85}
                />
                <text
                  x={16}
                  y={0}
                  fontFamily={OS_LEGAL_TYPOGRAPHY.fontFamilySans}
                  fontSize={11.5}
                  fill={OS_LEGAL_COLORS.textSecondary}
                >
                  {l.type.length > 16 ? l.type.slice(0, 15) + "…" : l.type}
                </text>
              </g>
            );
          })}
        </g>

        {/* x-axis */}
        <line
          x1={MARGIN.left}
          y1={axisY}
          x2={VIEW_W - MARGIN.right}
          y2={axisY}
          stroke={OS_LEGAL_COLORS.border}
          strokeWidth={1}
        />
        {years.map((y) => {
          const x = xScale(Date.UTC(y, 0, 1));
          if (x < MARGIN.left || x > VIEW_W - MARGIN.right) return null;
          return (
            <g key={y}>
              <line
                x1={x}
                y1={MARGIN.top}
                x2={x}
                y2={axisY}
                stroke={OS_LEGAL_COLORS.border}
                strokeOpacity={0.35}
                strokeDasharray="2 5"
              />
              <text
                x={x}
                y={axisY + 22}
                textAnchor="middle"
                fontFamily={OS_LEGAL_TYPOGRAPHY.fontFamilySans}
                fontSize={12}
                fontWeight={600}
                fill={OS_LEGAL_COLORS.textMuted}
              >
                {y}
              </text>
            </g>
          );
        })}

        {/* dots */}
        <g>
          {nodes.map((n, i) => (
            <circle
              key={i}
              cx={n.x}
              cy={n.y}
              r={n.r}
              fill={n.color}
              fillOpacity={n.value > 0 ? 0.82 : 0.5}
              stroke={d3.color(n.color)?.darker(0.6)?.toString() || n.color}
              strokeOpacity={0.5}
              strokeWidth={1}
            >
              <title>
                {n.title}
                {n.value > 0 ? ` · ${fmtMoney(n.value)}` : ""}
              </title>
            </circle>
          ))}
        </g>

        {/* whale labels — row-packed so close ones don't overprint */}
        <g>
          {whales.map((w, i) => {
            const off = 16 + (w.labelRow || 0) * 42;
            const leaderEnd = w.y - w.r - off;
            const label = w.party || w.title;
            return (
              <g key={i}>
                <line
                  x1={w.x}
                  y1={w.y - w.r}
                  x2={w.x}
                  y2={leaderEnd}
                  stroke={OS_LEGAL_COLORS.textMuted}
                  strokeWidth={1}
                  strokeOpacity={0.4}
                />
                <text
                  x={w.x}
                  y={leaderEnd - 16}
                  textAnchor="middle"
                  fontFamily={OS_LEGAL_TYPOGRAPHY.fontFamilySans}
                  fontSize={12.5}
                  fontWeight={700}
                  fill={OS_LEGAL_COLORS.textPrimary}
                  paintOrder="stroke"
                  stroke="#ffffff"
                  strokeWidth={3.5}
                  strokeLinejoin="round"
                >
                  {fmtMoney(w.value)}
                  <tspan
                    x={w.x}
                    dy={13}
                    fontWeight={500}
                    fontSize={10.5}
                    fill={OS_LEGAL_COLORS.textSecondary}
                  >
                    {label.length > 24 ? label.slice(0, 23) + "…" : label}
                  </tspan>
                </text>
              </g>
            );
          })}
        </g>

        {/* credit */}
        <text
          x={VIEW_W - MARGIN.right}
          y={VIEW_H - 14}
          textAnchor="end"
          fontFamily={OS_LEGAL_TYPOGRAPHY.fontFamilySans}
          fontSize={11}
          fill={OS_LEGAL_COLORS.textMuted}
        >
          {byline ?? "Made with OpenContracts"}
        </text>
      </svg>
    </Frame>
  );
};
