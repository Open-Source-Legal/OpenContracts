import React, { useMemo } from "react";
import styled, { keyframes } from "styled-components";
import * as d3 from "d3";
import { Share2, ArrowRight } from "lucide-react";

import { OS_LEGAL_COLORS } from "../../../../assets/configurations/osLegalStyles";
import {
  DOCUMENT_RELATIONSHIP_TYPES,
  DOCUMENT_RELATIONSHIP_TYPE_LABELS,
  DOCUMENT_GRAPH_LAYOUT,
} from "../../../../assets/configurations/constants";
import {
  CorpusDocumentGraphNode,
  CorpusDocumentGraphEdge,
} from "../../../../graphql/queries";

/**
 * DocumentGraphGlimpse — a static, deterministic force-directed rendering of
 * the corpus document-relationship graph (documents = nodes, relationships =
 * edges). This is the centerpiece of the Corpus Intelligence home: it makes
 * "how documents interact" literal, mirroring cite's pitch ("documents are
 * nodes, citations are edges").
 *
 * The layout is computed synchronously with d3-force and rendered as plain
 * SVG, so there is no animation loop and the output is deterministic for a
 * given input (initial positions are seeded on a circle and the simulation is
 * stepped a fixed number of ticks). This keeps it cheap and test-friendly.
 */

// Layout geometry lives in the shared constants file (no magic numbers);
// destructured here so the layout math below stays terse.
const {
  VIEW_WIDTH,
  VIEW_HEIGHT,
  SIMULATION_TICKS,
  MIN_NODE_RADIUS,
  MAX_NODE_RADIUS,
} = DOCUMENT_GRAPH_LAYOUT;

interface SimNode extends CorpusDocumentGraphNode {
  x: number;
  y: number;
  // d3 mutates these during simulation
  vx?: number;
  vy?: number;
}

interface DocumentGraphGlimpseProps {
  nodes: CorpusDocumentGraphNode[];
  edges: CorpusDocumentGraphEdge[];
  totalNodeCount: number;
  totalEdgeCount: number;
  truncated: boolean;
  /**
   * Graph query in flight. While loading with no data yet, a skeleton is
   * shown instead of the empty state — otherwise every page load flashes
   * "No relationships yet" before the data arrives.
   */
  loading?: boolean;
  /** Escape hatch to the fuller documents/relationships view. */
  onExplore?: () => void;
  testId?: string;
}

const GraphCard = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  width: 100%;
  padding: 1rem 1.25rem 1.25rem;
  background: ${OS_LEGAL_COLORS.surfaceLight};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 14px;
`;

const GraphHeader = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
`;

const GraphTitle = styled.div`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.875rem;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textPrimary};

  svg {
    color: ${OS_LEGAL_COLORS.primaryBlue};
  }
`;

const GraphMeta = styled.span`
  font-size: 0.75rem;
  color: ${OS_LEGAL_COLORS.textMuted};
  font-variant-numeric: tabular-nums;
`;

const SvgWrapper = styled.div`
  width: 100%;
  background: white;
  border-radius: 10px;
  overflow: hidden;

  svg {
    display: block;
    width: 100%;
    height: auto;
  }
`;

const ExploreLink = styled.button`
  align-self: flex-end;
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  background: none;
  border: none;
  padding: 0.25rem 0.25rem;
  font-size: 0.8125rem;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.primaryBlue};
  cursor: pointer;

  &:hover {
    text-decoration: underline;
  }

  svg {
    width: 14px;
    height: 14px;
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

// First-load placeholder matching the SVG's aspect ratio so the card doesn't
// reflow when the graph arrives. Mirrors IntelligencePanel's StatSkeleton.
const GraphSkeleton = styled.div`
  width: 100%;
  aspect-ratio: ${VIEW_WIDTH} / ${VIEW_HEIGHT};
  border-radius: 10px;
  background: ${OS_LEGAL_COLORS.surfaceHover};
  animation: ${shimmer} 1.2s ease-in-out infinite;
`;

// Legend — without it the graph is just blue dots and lines: a first-time
// viewer can't tell what an edge or a big node means. Entries are rendered
// conditionally on the edge types actually present so we never explain a
// dashed style the data doesn't use.
const Legend = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 0.3rem 1.1rem;
  font-size: 0.75rem;
  color: ${OS_LEGAL_COLORS.textMuted};
`;

const LegendItem = styled.span`
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  white-space: nowrap;
`;

/**
 * Compute a deterministic force-directed layout. Initial positions are seeded
 * on a circle (no RNG), then the simulation is run synchronously for a fixed
 * number of ticks with its internal alpha schedule. Sized for the ~60-node
 * cap (CORPUS_DOCUMENT_GRAPH_MAX_NODES) — the synchronous tick loop is cheap at
 * that scale; revisit for the Phase 2 interactive explorer if the cap grows.
 */
function computeLayout(
  nodes: CorpusDocumentGraphNode[],
  edges: CorpusDocumentGraphEdge[]
): { simNodes: SimNode[]; nodeById: Map<string, SimNode> } {
  const n = nodes.length;
  const cx = VIEW_WIDTH / 2;
  const cy = VIEW_HEIGHT / 2;
  const seedRadius = Math.min(VIEW_WIDTH, VIEW_HEIGHT) * 0.32;

  const simNodes: SimNode[] = nodes.map((node, i) => {
    const angle = (i / Math.max(1, n)) * Math.PI * 2;
    return {
      ...node,
      x: cx + Math.cos(angle) * seedRadius,
      y: cy + Math.sin(angle) * seedRadius,
    };
  });

  const nodeById = new Map(simNodes.map((node) => [node.id, node]));

  // Only keep edges whose endpoints are both present (defensive).
  const links = edges
    .filter((e) => nodeById.has(e.source) && nodeById.has(e.target))
    .map((e) => ({ source: e.source, target: e.target }));

  const simulation = d3
    .forceSimulation<SimNode>(simNodes)
    .force(
      "link",
      d3
        .forceLink<SimNode, { source: string; target: string }>(links)
        .id((d) => d.id)
        .distance(70)
        .strength(0.5)
    )
    .force("charge", d3.forceManyBody<SimNode>().strength(-180))
    .force("center", d3.forceCenter(cx, cy))
    .force("collide", d3.forceCollide<SimNode>().radius(MAX_NODE_RADIUS + 4))
    .stop();

  // Run synchronously — no animation frame, fully deterministic.
  for (let i = 0; i < SIMULATION_TICKS; i += 1) {
    simulation.tick();
  }

  // Clamp into the viewBox so nothing renders off-canvas.
  const pad = MAX_NODE_RADIUS + 2;
  simNodes.forEach((node) => {
    node.x = Math.max(pad, Math.min(VIEW_WIDTH - pad, node.x));
    node.y = Math.max(pad, Math.min(VIEW_HEIGHT - pad, node.y));
  });

  return { simNodes, nodeById };
}

export const DocumentGraphGlimpse: React.FC<DocumentGraphGlimpseProps> = ({
  nodes,
  edges,
  totalNodeCount,
  totalEdgeCount,
  truncated,
  loading = false,
  onExplore,
  testId = "document-graph-glimpse",
}) => {
  // Degree scale → node radius. Memoized on the node set.
  const radiusScale = useMemo(() => {
    const maxDegree = nodes.reduce((m, node) => Math.max(m, node.degree), 1);
    return d3
      .scaleSqrt()
      .domain([0, maxDegree])
      .range([MIN_NODE_RADIUS, MAX_NODE_RADIUS]);
  }, [nodes]);

  const { simNodes, nodeById } = useMemo(
    () => computeLayout(nodes, edges),
    [nodes, edges]
  );

  // Which edge styles are actually on screen — drives a legend that only
  // explains what's present (no dashed-line entry when there are no notes).
  const hasCitationEdge = edges.some(
    (e) => e.relationshipType !== DOCUMENT_RELATIONSHIP_TYPES.NOTES
  );
  const hasNoteEdge = edges.some(
    (e) => e.relationshipType === DOCUMENT_RELATIONSHIP_TYPES.NOTES
  );

  if (nodes.length === 0) {
    // While the query is in flight an empty node list means "unknown", not
    // "no relationships" — show a skeleton so first load doesn't flash the
    // misleading empty message.
    if (loading) {
      return (
        <GraphCard data-testid={testId}>
          <GraphHeader>
            <GraphTitle>
              <Share2 size={16} />
              Document graph
            </GraphTitle>
          </GraphHeader>
          <GraphSkeleton data-testid={`${testId}-skeleton`} />
        </GraphCard>
      );
    }
    return (
      <GraphCard data-testid={testId}>
        <GraphHeader>
          <GraphTitle>
            <Share2 size={16} />
            Document graph
          </GraphTitle>
        </GraphHeader>
        <EmptyState data-testid={`${testId}-empty`}>
          No relationships between documents yet. As citations and links are
          added, this collection's graph appears here.
        </EmptyState>
      </GraphCard>
    );
  }

  return (
    <GraphCard data-testid={testId}>
      <GraphHeader>
        <GraphTitle>
          <Share2 size={16} />
          How these documents interconnect
        </GraphTitle>
        <GraphMeta data-testid={`${testId}-meta`}>
          {/* "total" matters: when truncated, totalEdgeCount includes edges
              between documents that didn't make the node cap and therefore
              aren't drawn — without the qualifier the count looks wrong. */}
          {totalNodeCount} linked{" "}
          {totalNodeCount === 1 ? "document" : "documents"}
          {" · "}
          {totalEdgeCount} total{" "}
          {totalEdgeCount === 1 ? "connection" : "connections"}
          {truncated ? " (showing the most connected)" : ""}
        </GraphMeta>
      </GraphHeader>

      <SvgWrapper>
        <svg
          viewBox={`0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`}
          role="img"
          aria-label="Document relationship graph"
          data-testid={`${testId}-svg`}
        >
          <g data-testid={`${testId}-edges`}>
            {edges.map((edge) => {
              const s = nodeById.get(edge.source);
              const t = nodeById.get(edge.target);
              if (!s || !t) return null;
              const isNote =
                edge.relationshipType === DOCUMENT_RELATIONSHIP_TYPES.NOTES;
              return (
                <line
                  key={edge.id}
                  x1={s.x}
                  y1={s.y}
                  x2={t.x}
                  y2={t.y}
                  stroke={
                    isNote
                      ? OS_LEGAL_COLORS.border
                      : OS_LEGAL_COLORS.primaryBlue
                  }
                  strokeOpacity={isNote ? 0.5 : 0.35}
                  strokeWidth={isNote ? 1 : 1.5}
                  strokeDasharray={isNote ? "3 3" : undefined}
                />
              );
            })}
          </g>
          <g data-testid={`${testId}-nodes`}>
            {simNodes.map((node) => (
              <circle
                key={node.id}
                cx={node.x}
                cy={node.y}
                r={radiusScale(node.degree)}
                fill={OS_LEGAL_COLORS.primaryBlue}
                fillOpacity={0.85}
                stroke="white"
                strokeWidth={1.5}
                data-testid={`${testId}-node`}
              >
                <title>
                  {(node.title || "Untitled document") +
                    ` — ${node.degree} ${
                      node.degree === 1 ? "connection" : "connections"
                    }`}
                </title>
              </circle>
            ))}
          </g>
        </svg>
      </SvgWrapper>

      <Legend data-testid={`${testId}-legend`}>
        {hasCitationEdge && (
          <LegendItem>
            <svg width="22" height="8" aria-hidden="true">
              <line
                x1="1"
                y1="4"
                x2="21"
                y2="4"
                stroke={OS_LEGAL_COLORS.primaryBlue}
                strokeWidth="1.5"
              />
            </svg>
            {DOCUMENT_RELATIONSHIP_TYPE_LABELS.RELATIONSHIP}
          </LegendItem>
        )}
        {hasNoteEdge && (
          <LegendItem>
            <svg width="22" height="8" aria-hidden="true">
              <line
                x1="1"
                y1="4"
                x2="21"
                y2="4"
                stroke={OS_LEGAL_COLORS.border}
                strokeWidth="1"
                strokeDasharray="3 3"
              />
            </svg>
            {DOCUMENT_RELATIONSHIP_TYPE_LABELS.NOTES}
          </LegendItem>
        )}
        <LegendItem>
          <svg width="26" height="12" aria-hidden="true">
            <circle
              cx="5"
              cy="6"
              r="2.5"
              fill={OS_LEGAL_COLORS.primaryBlue}
              fillOpacity="0.85"
            />
            <circle
              cx="18"
              cy="6"
              r="5"
              fill={OS_LEGAL_COLORS.primaryBlue}
              fillOpacity="0.85"
            />
          </svg>
          Larger = more connections
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
