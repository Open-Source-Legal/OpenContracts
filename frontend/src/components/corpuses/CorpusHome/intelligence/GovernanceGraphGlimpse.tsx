import React, { useMemo, useState } from "react";
import styled from "styled-components";
import * as d3 from "d3";
import { Scale, ArrowRight } from "lucide-react";

import { OS_LEGAL_COLORS } from "../../../../assets/configurations/osLegalStyles";
import {
  GOVERNANCE_GRAPH_LAYOUT,
  GOVERNANCE_GRAPH_COLORS,
  GOVERNANCE_GRAPH_NODE_KINDS,
  GOVERNANCE_GRAPH_EDGE_TYPES,
  GOVERNANCE_GRAPH_AUTHORITY_CAPTIONS,
  GOVERNANCE_GRAPH_AUTHORITY_CAPTIONS_SHORT,
} from "../../../../assets/configurations/constants";
import {
  GovernanceGraphNode,
  GovernanceGraphEdge,
} from "../../../../graphql/queries";
import {
  computeGovernanceLayout,
  isLawKind,
  shortLawLabel,
  ghostLabel,
  shortFilingLabel,
  makeNodeFill,
  makeEdgeStroke,
  GovSimNode as SimNode,
} from "../../../../utils/governanceGraphLayout";
import {
  EmptyState,
  ExploreLink,
  GraphCard,
  GraphHeader,
  GraphMeta,
  GraphSkeleton,
  GraphTitle,
  Legend,
  LegendItem,
  SvgWrapper,
} from "./graphCardChrome";

/**
 * GovernanceGraphGlimpse — the reference web, rendered.
 *
 * A bipartite composition: filing documents float in an upper band (each
 * primary anchors its exhibits into a cluster), while the law sits below on a
 * pinned shelf — statute sections grouped by authority, in section order.
 * Every statutory citation arcs down from the filings to the exact section it
 * resolves to; citations without an in-system target fall to dashed "ghost"
 * keys. The layout makes the system's pitch literal: this is how a deal is
 * wired to the law.
 *
 * Like DocumentGraphGlimpse, the layout is computed synchronously with
 * d3-force from seeded positions (LCG, no Math.random) and rendered as plain
 * SVG — deterministic for a given input, no animation loop, test-friendly.
 */

const { VIEW_WIDTH, VIEW_HEIGHT, LAW_SHELF_Y, LAW_SHELF_INSET } =
  GOVERNANCE_GRAPH_LAYOUT;

const KINDS = GOVERNANCE_GRAPH_NODE_KINDS;
const EDGE_TYPES = GOVERNANCE_GRAPH_EDGE_TYPES;
const COLORS = GOVERNANCE_GRAPH_COLORS;

interface GovernanceGraphGlimpseProps {
  nodes: GovernanceGraphNode[];
  edges: GovernanceGraphEdge[];
  documentCount: number;
  externalKeyCount: number;
  mentionCount: number;
  truncated: boolean;
  loading?: boolean;
  error?: boolean;
  /** Click-through on a document/statute node (global DocumentType id). */
  onSelectDocument?: (documentId: string) => void;
  /** Escape hatch to the fuller view. */
  onExplore?: () => void;
  /**
   * Rendered inside the empty state — lets the live wrapper inject the
   * "Map the reference web" bootstrap CTA without this component knowing
   * anything about mutations.
   */
  emptyAction?: React.ReactNode;
  testId?: string;
}

// The governance empty state centers a motif + CTA stack, so it extends the
// shared chrome's plain text block into a column.
const CenteredEmptyState = styled(EmptyState)`
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
  padding: 1.75rem 1rem;
`;

/** Miniature of the graph motif for the empty state — two filings over a
 * three-section shelf — so the promise of the feature is visible before any
 * data exists. */
const EmptyMotif: React.FC = () => (
  <svg width="132" height="64" viewBox="0 0 132 64" aria-hidden="true">
    <path
      d="M36,16 A52,52 0 0,1 30,48"
      fill="none"
      stroke={COLORS.LAW_DEFAULT}
      strokeWidth="1.4"
      strokeOpacity="0.55"
    />
    <path
      d="M36,16 A66,66 0 0,1 66,48"
      fill="none"
      stroke={COLORS.LAW_DEFAULT}
      strokeWidth="1.4"
      strokeOpacity="0.55"
    />
    <path
      d="M96,20 A52,52 0 0,1 102,48"
      fill="none"
      stroke={COLORS.EXTERNAL}
      strokeWidth="1.2"
      strokeOpacity="0.6"
      strokeDasharray="3 4"
    />
    <circle
      cx="36"
      cy="14"
      r="8"
      fill={COLORS.CLUSTER_HUES[0]}
      fillOpacity="0.9"
    />
    <circle
      cx="96"
      cy="18"
      r="6.5"
      fill={COLORS.CLUSTER_HUES[1]}
      fillOpacity="0.9"
    />
    <circle cx="30" cy="50" r="4.5" fill={COLORS.LAW_DEFAULT} />
    <circle
      cx="66"
      cy="50"
      r="4.5"
      fill={COLORS.AUTHORITY_FILLS["securities-act"]}
    />
    <circle
      cx="102"
      cy="50"
      r="4.5"
      fill="none"
      stroke={COLORS.EXTERNAL}
      strokeWidth="1.2"
      strokeDasharray="2.5 2.5"
    />
  </svg>
);

export const GovernanceGraphGlimpse: React.FC<GovernanceGraphGlimpseProps> = ({
  nodes,
  edges,
  documentCount,
  externalKeyCount,
  mentionCount,
  truncated,
  loading = false,
  error = false,
  onSelectDocument,
  onExplore,
  emptyAction,
  testId = "governance-graph-glimpse",
}) => {
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  const {
    simNodes,
    nodeById,
    clusterColorById,
    shelfNodes,
    authorityGroups,
    dense,
    shelfMaxDegree,
  } = useMemo(() => computeGovernanceLayout(nodes, edges), [nodes, edges]);

  const nodeFill = makeNodeFill(clusterColorById);
  const edgeStroke = makeEdgeStroke(clusterColorById);

  // Hover focus: incident edges + endpoint nodes stay full strength, the rest
  // recede. Null hover = neutral (everything at base opacity).
  const edgeEmphasis = (e: GovernanceGraphEdge): number => {
    if (!hoveredId) return 1;
    return e.source === hoveredId || e.target === hoveredId ? 1.6 : 0.25;
  };
  // Neighbours of the hovered node, computed once per hover (O(edges)). Without
  // this, nodeEmphasis below would re-scan every edge for every node on each
  // render — O(nodes × edges), ~160k iterations at the 200-node / ~800-edge cap.
  const hoveredNeighborIds = useMemo(() => {
    if (!hoveredId) return null;
    const ids = new Set<string>();
    for (const e of edges) {
      if (e.source === hoveredId) ids.add(e.target);
      else if (e.target === hoveredId) ids.add(e.source);
    }
    return ids;
  }, [hoveredId, edges]);
  const nodeEmphasis = (n: SimNode): number => {
    if (!hoveredId) return 1;
    if (n.id === hoveredId) return 1;
    return hoveredNeighborIds?.has(n.id) ? 1 : 0.35;
  };

  // Static labels — gated against the SHELF-LOCAL degree scale (a dominant
  // S-1 primary would otherwise dwarf every statute and nothing on the shelf
  // would qualify): every statute when the shelf is sparse, only the
  // high-traffic ones when dense; ghosts always degree-gated.
  const primaries = simNodes.filter((n) => n.kind === KINDS.PRIMARY);
  const labeledIds = useMemo(() => {
    const ids = new Set<string>();
    const statuteGate = dense ? shelfMaxDegree * 0.3 : 0;
    const ghostGate = shelfMaxDegree * (dense ? 0.45 : 0.25);
    simNodes.forEach((n) => {
      if (n.kind === KINDS.STATUTE && n.degree >= statuteGate) ids.add(n.id);
      if (n.kind === KINDS.EXTERNAL && n.degree >= ghostGate) ids.add(n.id);
    });
    // Label every primary when there's room; in swarm corpora only the
    // anchor (highest-degree) primary per cluster keeps a label.
    const byCluster = new Map<number, SimNode>();
    primaries.forEach((p) => {
      const cur = byCluster.get(p.clusterIndex ?? 0);
      if (!cur || p.degree > cur.degree) byCluster.set(p.clusterIndex ?? 0, p);
    });
    primaries.forEach((p) => {
      if (primaries.length <= 8 || byCluster.get(p.clusterIndex ?? 0) === p) {
        ids.add(p.id);
      }
    });
    return ids;
  }, [simNodes, primaries, dense, shelfMaxDegree]);

  if (nodes.length === 0) {
    if (loading) {
      return (
        <GraphCard data-testid={testId}>
          <GraphHeader>
            <GraphTitle $iconColor={COLORS.LAW_DEFAULT}>
              <Scale size={16} />
              Governance graph
            </GraphTitle>
          </GraphHeader>
          <GraphSkeleton
            $viewWidth={VIEW_WIDTH}
            $viewHeight={VIEW_HEIGHT}
            data-testid={`${testId}-skeleton`}
          />
        </GraphCard>
      );
    }
    if (error) {
      return (
        <GraphCard data-testid={testId}>
          <GraphHeader>
            <GraphTitle $iconColor={COLORS.LAW_DEFAULT}>
              <Scale size={16} />
              Governance graph
            </GraphTitle>
          </GraphHeader>
          <CenteredEmptyState data-testid={`${testId}-error`}>
            Couldn't load the governance graph. Please try again.
          </CenteredEmptyState>
        </GraphCard>
      );
    }
    return (
      <GraphCard data-testid={testId}>
        <GraphHeader>
          <GraphTitle $iconColor={COLORS.LAW_DEFAULT}>
            <Scale size={16} />
            Governance graph
          </GraphTitle>
        </GraphHeader>
        <CenteredEmptyState data-testid={`${testId}-empty`}>
          <EmptyMotif />
          <span>
            This collection's reference web hasn't been mapped yet. Once mapped,
            every exhibit cross-reference and statutory citation — down to the
            section of the law — appears here.
          </span>
          {emptyAction}
        </CenteredEmptyState>
      </GraphCard>
    );
  }

  const statuteCount = nodes.filter((n) => n.kind === KINDS.STATUTE).length;
  const hasExternal = externalKeyCount > 0;
  const shelfY = VIEW_HEIGHT * LAW_SHELF_Y;

  return (
    <GraphCard data-testid={testId}>
      <GraphHeader>
        <GraphTitle $iconColor={COLORS.LAW_DEFAULT}>
          <Scale size={16} />
          How this collection is wired to the law
        </GraphTitle>
        <GraphMeta data-testid={`${testId}-meta`}>
          {documentCount} {documentCount === 1 ? "document" : "documents"}
          {statuteCount > 0 &&
            ` · ${statuteCount} statute ${
              statuteCount === 1 ? "section" : "sections"
            }`}
          {` · ${mentionCount} ${
            mentionCount === 1 ? "reference" : "references"
          } resolved`}
          {truncated ? " (showing the most connected)" : ""}
        </GraphMeta>
      </GraphHeader>

      <SvgWrapper>
        <svg
          viewBox={`0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`}
          role="img"
          aria-label="Governance graph: documents above, cited law below"
          data-testid={`${testId}-svg`}
          onMouseLeave={() => setHoveredId(null)}
        >
          <defs>
            {/* Soft halo behind primaries + busy statutes — light-mode glow. */}
            <filter
              id="governance-halo"
              x="-60%"
              y="-60%"
              width="220%"
              height="220%"
            >
              <feGaussianBlur stdDeviation="4" result="blur" />
              <feComponentTransfer in="blur" result="soft">
                <feFuncA type="linear" slope="0.45" />
              </feComponentTransfer>
              <feMerge>
                <feMergeNode in="soft" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
            {/* Whisper of atmosphere: a vertical wash from paper-white into
                the faintest slate, so the two layers read as sky/ground. */}
            <linearGradient id="governance-bg" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#ffffff" />
              <stop offset="62%" stopColor="#fdfdfb" />
              <stop offset="100%" stopColor="#faf6ee" />
            </linearGradient>
          </defs>

          <rect
            width={VIEW_WIDTH}
            height={VIEW_HEIGHT}
            fill="url(#governance-bg)"
          />

          {/* Layer captions — the composition's reading instructions. The
              FILINGS caption only renders when filings exist (a pure
              statute corpus is all shelf). */}
          {simNodes.some((n) => !isLawKind(n.kind)) && (
            <text
              x={VIEW_WIDTH * LAW_SHELF_INSET}
              y={30}
              fill={COLORS.LAYER_CAPTION}
              fontSize={11}
              letterSpacing="0.25em"
              fontWeight={600}
            >
              THE FILINGS
            </text>
          )}
          <text
            x={VIEW_WIDTH * LAW_SHELF_INSET}
            y={shelfY - 46}
            fill={COLORS.LAW_CAPTION}
            fontSize={11}
            letterSpacing="0.25em"
            fontWeight={600}
          >
            THE LAW
          </text>

          {/* The shelf itself: a hairline the sections sit on. */}
          <line
            x1={VIEW_WIDTH * LAW_SHELF_INSET - 8}
            y1={shelfY}
            x2={VIEW_WIDTH * (1 - LAW_SHELF_INSET) + 8}
            y2={shelfY}
            stroke={COLORS.LAW_DEFAULT}
            strokeOpacity={0.18}
            strokeWidth={1}
          />

          <g data-testid={`${testId}-edges`}>
            {edges.map((edge, i) => {
              const s = nodeById.get(edge.source);
              const t = nodeById.get(edge.target);
              if (!s || !t) return null;
              const dx = t.x - s.x;
              const dy = t.y - s.y;
              const dr = Math.hypot(dx, dy) * 1.8;
              const isDoc = edge.edgeType === EDGE_TYPES.DOCUMENT;
              const isExternal = edge.edgeType === EDGE_TYPES.LAW_EXTERNAL;
              // Dense graphs thin out so the citation cascade reads as
              // texture rather than a solid wash (mirrors the demo's
              // node-count-keyed stroke schedule).
              const baseOpacity = isDoc
                ? 0.3
                : isExternal
                ? dense
                  ? 0.25
                  : 0.35
                : dense
                ? 0.3
                : 0.45;
              const baseWidth = isDoc
                ? 1.1
                : Math.min(
                    1 + edge.weight * (dense ? 0.25 : 0.5),
                    dense ? 2.4 : 4.5
                  );
              return (
                <path
                  key={`${edge.source}->${edge.target}-${edge.edgeType}-${i}`}
                  d={`M${s.x},${s.y}A${dr},${dr} 0 0,1 ${t.x},${t.y}`}
                  fill="none"
                  stroke={edgeStroke(edge)}
                  strokeWidth={baseWidth}
                  strokeOpacity={Math.min(
                    baseOpacity * edgeEmphasis(edge),
                    0.9
                  )}
                  strokeDasharray={isExternal ? "4 5" : undefined}
                />
              );
            })}
          </g>

          <g data-testid={`${testId}-nodes`}>
            {simNodes.map((node) => {
              const fill = nodeFill(node);
              const isExternal = node.kind === KINDS.EXTERNAL;
              const clickable = Boolean(onSelectDocument && node.documentId);
              const halo =
                node.kind === KINDS.PRIMARY ||
                (node.kind === KINDS.STATUTE &&
                  node.degree >= shelfMaxDegree * 0.35);
              return (
                <circle
                  key={node.id}
                  cx={node.x}
                  cy={node.y}
                  r={node.r}
                  fill={isExternal ? "white" : fill}
                  fillOpacity={
                    (isExternal
                      ? 0.9
                      : node.kind === KINDS.EXHIBIT
                      ? 0.8
                      : 0.95) * nodeEmphasis(node)
                  }
                  stroke={
                    isExternal
                      ? COLORS.EXTERNAL
                      : d3.color(fill)?.darker(0.5)?.toString() || fill
                  }
                  strokeOpacity={nodeEmphasis(node)}
                  strokeWidth={node.kind === KINDS.PRIMARY ? 2 : 1.1}
                  strokeDasharray={isExternal ? "3 3" : undefined}
                  filter={halo ? "url(#governance-halo)" : undefined}
                  cursor={clickable ? "pointer" : undefined}
                  onMouseEnter={() => setHoveredId(node.id)}
                  onClick={
                    clickable
                      ? () => onSelectDocument?.(node.documentId!)
                      : undefined
                  }
                  data-testid={`${testId}-node`}
                  data-node-kind={node.kind}
                >
                  <title>
                    {(node.kind === KINDS.EXTERNAL
                      ? `${ghostLabel(node)} — cited, not yet ingested`
                      : node.title || "Untitled document") +
                      ` · ${node.degree} ${
                        node.degree === 1 ? "reference" : "references"
                      }`}
                  </title>
                </circle>
              );
            })}
          </g>

          <g data-testid={`${testId}-labels`}>
            {simNodes
              .filter((n) => labeledIds.has(n.id))
              .map((node) => {
                const law = isLawKind(node.kind);
                const r = node.r;
                const y = law
                  ? node.labelRow === 1
                    ? -(r + 7)
                    : node.labelRow === 2
                    ? r + 26
                    : r + 14
                  : r + 13;
                const fill =
                  node.kind === KINDS.EXTERNAL
                    ? COLORS.EXTERNAL
                    : d3
                        .color(nodeFill(node))
                        ?.darker(law ? 0.9 : 0.6)
                        ?.toString() || OS_LEGAL_COLORS.textSecondary;
                return (
                  <text
                    key={`label-${node.id}`}
                    x={node.x}
                    y={node.y + y}
                    textAnchor="middle"
                    fontSize={node.kind === KINDS.PRIMARY ? 12 : 9.5}
                    fontWeight={
                      node.kind === KINDS.PRIMARY || node.kind === KINDS.STATUTE
                        ? 600
                        : 400
                    }
                    fill={fill}
                    opacity={nodeEmphasis(node)}
                    paintOrder="stroke"
                    stroke="white"
                    strokeWidth={3}
                    pointerEvents="none"
                  >
                    {node.kind === KINDS.PRIMARY
                      ? shortFilingLabel(node)
                      : node.kind === KINDS.EXTERNAL
                      ? ghostLabel(node)
                      : shortLawLabel(node)}
                  </text>
                );
              })}
          </g>

          {/* Authority captions under the shelf — two staggered rows so
              adjacent groups never collide; abbreviated when dense. */}
          <g data-testid={`${testId}-authority-captions`}>
            {authorityGroups.map(({ authority, meanX }, i) => {
              const captions = dense
                ? GOVERNANCE_GRAPH_AUTHORITY_CAPTIONS_SHORT
                : GOVERNANCE_GRAPH_AUTHORITY_CAPTIONS;
              return (
                <text
                  key={`authority-${authority}`}
                  x={meanX}
                  y={VIEW_HEIGHT - (i % 2 === 0 ? 22 : 8)}
                  textAnchor="middle"
                  fontSize={9.5}
                  letterSpacing="0.18em"
                  fill={COLORS.LAW_CAPTION}
                  fontWeight={600}
                >
                  {captions[authority] || authority.toUpperCase()}
                </text>
              );
            })}
          </g>
        </svg>
      </SvgWrapper>

      <Legend data-testid={`${testId}-legend`}>
        <LegendItem>
          <svg width="12" height="12" aria-hidden="true">
            <circle
              cx="6"
              cy="6"
              r="5"
              fill={COLORS.CLUSTER_HUES[0]}
              fillOpacity="0.9"
            />
          </svg>
          Filing & exhibits
        </LegendItem>
        {statuteCount > 0 && (
          <LegendItem>
            <svg width="12" height="12" aria-hidden="true">
              <circle cx="6" cy="6" r="5" fill={COLORS.LAW_DEFAULT} />
            </svg>
            Statute section (full text in-system)
          </LegendItem>
        )}
        {hasExternal && (
          <LegendItem>
            <svg width="12" height="12" aria-hidden="true">
              <circle
                cx="6"
                cy="6"
                r="4.5"
                fill="white"
                stroke={COLORS.EXTERNAL}
                strokeWidth="1.2"
                strokeDasharray="2.5 2.5"
              />
            </svg>
            Cited, not yet ingested
          </LegendItem>
        )}
        <LegendItem>
          <svg width="22" height="8" aria-hidden="true">
            <line
              x1="1"
              y1="4"
              x2="21"
              y2="4"
              stroke={COLORS.LAW_DEFAULT}
              strokeWidth="2"
              strokeOpacity="0.7"
            />
          </svg>
          Statutory citation (thicker = more mentions)
        </LegendItem>
      </Legend>

      {onExplore && (
        <ExploreLink onClick={onExplore} data-testid={`${testId}-explore`}>
          Explore the full graph
          <ArrowRight />
        </ExploreLink>
      )}
    </GraphCard>
  );
};
