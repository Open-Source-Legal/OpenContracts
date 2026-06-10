import React, { useMemo, useState } from "react";
import styled, { keyframes } from "styled-components";
import * as d3 from "d3";
import { Scale, ArrowRight } from "lucide-react";

import { OS_LEGAL_COLORS } from "../../../../assets/configurations/osLegalStyles";
import {
  GOVERNANCE_GRAPH_LAYOUT,
  GOVERNANCE_GRAPH_COLORS,
  GOVERNANCE_GRAPH_NODE_KINDS,
  GOVERNANCE_GRAPH_EDGE_TYPES,
  GOVERNANCE_GRAPH_AUTHORITY_ORDER,
  GOVERNANCE_GRAPH_AUTHORITY_CAPTIONS,
  GOVERNANCE_GRAPH_AUTHORITY_CAPTIONS_SHORT,
} from "../../../../assets/configurations/constants";
import {
  GovernanceGraphNode,
  GovernanceGraphEdge,
} from "../../../../graphql/queries";

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

const {
  VIEW_WIDTH,
  VIEW_HEIGHT,
  SIMULATION_TICKS,
  FILINGS_BAND_Y,
  LAW_SHELF_Y,
  LAW_SHELF_INSET,
  AUTHORITY_GROUP_GAP,
  MIN_NODE_RADIUS,
  MAX_NODE_RADIUS,
  MIN_PRIMARY_RADIUS,
  MAX_SHELF_RADIUS,
  LAYOUT_SEED,
  DENSE_NODE_THRESHOLD,
  SWARM_CLUSTER_SIZE,
} = GOVERNANCE_GRAPH_LAYOUT;

const KINDS = GOVERNANCE_GRAPH_NODE_KINDS;
const EDGE_TYPES = GOVERNANCE_GRAPH_EDGE_TYPES;
const COLORS = GOVERNANCE_GRAPH_COLORS;

interface SimNode extends GovernanceGraphNode {
  x: number;
  y: number;
  vx?: number;
  vy?: number;
  /** d3 honours fx/fy: shelf nodes are pinned and never move. */
  fx?: number;
  fy?: number;
  /** Index of this node's filing cluster (component over DOCUMENT edges). */
  clusterIndex?: number;
  /** 0/1/2 row stagger for shelf labels. */
  labelRow?: number;
  /** Render radius, computed during layout so collide can honour it. */
  r: number;
}

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

const isLawKind = (kind: string) =>
  kind === KINDS.STATUTE || kind === KINDS.EXTERNAL;

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
    color: ${COLORS.LAW_DEFAULT};
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
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
  padding: 1.75rem 1rem;
  text-align: center;
  font-size: 0.8125rem;
  color: ${OS_LEGAL_COLORS.textMuted};
`;

const shimmer = keyframes`
  0% { opacity: 0.45; }
  50% { opacity: 0.8; }
  100% { opacity: 0.45; }
`;

const GraphSkeleton = styled.div`
  width: 100%;
  aspect-ratio: ${VIEW_WIDTH} / ${VIEW_HEIGHT};
  border-radius: 10px;
  background: ${OS_LEGAL_COLORS.surfaceHover};
  animation: ${shimmer} 1.2s ease-in-out infinite;
`;

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

/** Shorten a statute/section title to its citation head:
 * "DGCL § 145 — Indemnification…" → "DGCL § 145". */
function shortLawLabel(node: GovernanceGraphNode): string {
  const title = node.title || node.id;
  return title.split("—")[0].split("(")[0].trim();
}

/** Display form for a ghost key: "dgcl:203" → "DGCL § 203". */
function ghostLabel(node: GovernanceGraphNode): string {
  const key = node.title || node.id.replace(/^key:/, "");
  const [prefix, section] = key.split(":", 2);
  const acronyms = new Set(["dgcl", "irc", "ica", "iaa", "usc"]);
  const display = prefix
    .split("-")
    .map((part) =>
      acronyms.has(part) || part === "sec"
        ? part.toUpperCase()
        : part.charAt(0).toUpperCase() + part.slice(1)
    )
    .join(" ");
  return section ? `${display} § ${section}` : display;
}

/** Shorten a filing title to a cluster-anchor label:
 * "Space Exploration Technologies Corp. S-1 (2025-12-19)" → "Space
 * Exploration Technologies Corp. S-1". Falls back to a hard cap. */
function shortFilingLabel(node: GovernanceGraphNode): string {
  const title = (node.title || "").trim();
  const m = title.match(/^(.+?\s(?:S-1(?:\/A)?|Form D|10-K|10-Q|8-K))\b/);
  const label = m ? m[1] : title;
  return label.length > 34 ? `${label.slice(0, 32)}…` : label;
}

interface Layout {
  simNodes: SimNode[];
  nodeById: Map<string, SimNode>;
  clusterColorById: Map<string, string>;
  shelfNodes: SimNode[];
  authorityGroups: { authority: string; meanX: number; size: number }[];
  /** Dense mode: degree-gated shelf labels, thinner edges, short captions. */
  dense: boolean;
  /** Highest degree among shelf nodes — the shelf-local emphasis scale. */
  shelfMaxDegree: number;
}

/**
 * Deterministic bipartite layout.
 *
 * Law nodes are PINNED on a shelf: authorities in fixed order (then
 * alphabetical for unregistered ones), sections in numeric order, with a gap
 * between authority groups. Filing nodes start jittered (seeded LCG) in the
 * upper band and settle under d3-force: short/strong DOCUMENT links pull
 * exhibits around their primary; long/weak LAW links let citations drape.
 */
function computeLayout(
  nodes: GovernanceGraphNode[],
  edges: GovernanceGraphEdge[]
): Layout {
  // Deterministic pseudo-random for reproducible layouts (mirrors the demo).
  let seed = LAYOUT_SEED;
  const rand = () => {
    seed = (seed * 16807) % 2147483647;
    return (seed - 1) / 2147483646;
  };

  const maxDegree = nodes.reduce((m, n) => Math.max(m, n.degree), 1);
  const nodeRadius = (n: GovernanceGraphNode): number => {
    const r =
      MIN_NODE_RADIUS +
      (MAX_NODE_RADIUS - MIN_NODE_RADIUS) * Math.sqrt(n.degree / maxDegree);
    if (n.kind === KINDS.PRIMARY) return Math.max(r, MIN_PRIMARY_RADIUS);
    if (isLawKind(n.kind)) return Math.min(r, MAX_SHELF_RADIUS);
    return r;
  };

  const simNodes: SimNode[] = nodes.map((node) => ({
    ...node,
    x: 0,
    y: 0,
    r: nodeRadius(node),
  }));
  const nodeById = new Map(simNodes.map((node) => [node.id, node]));

  // ---- Filing clusters: connected components over DOCUMENT edges ----------
  // Each primary + its exhibits forms one component; coloring by component
  // reproduces the demo's per-company hues from the data alone.
  const parent = new Map<string, string>();
  const find = (a: string): string => {
    let root = a;
    while (parent.get(root) !== root) root = parent.get(root)!;
    return root;
  };
  simNodes
    .filter((n) => !isLawKind(n.kind))
    .forEach((n) => parent.set(n.id, n.id));
  edges
    .filter(
      (e) =>
        e.edgeType === EDGE_TYPES.DOCUMENT &&
        parent.has(e.source) &&
        parent.has(e.target)
    )
    .forEach((e) => parent.set(find(e.source), find(e.target)));

  const componentMembers = new Map<string, SimNode[]>();
  simNodes
    .filter((n) => !isLawKind(n.kind))
    .forEach((n) => {
      const root = find(n.id);
      componentMembers.set(root, [...(componentMembers.get(root) || []), n]);
    });
  // Stable cluster order: by size desc, then by root id — big clusters claim
  // the leading palette hues.
  const componentRoots = [...componentMembers.keys()].sort((a, b) => {
    const sizeDiff =
      (componentMembers.get(b)?.length || 0) -
      (componentMembers.get(a)?.length || 0);
    return sizeDiff !== 0 ? sizeDiff : a.localeCompare(b);
  });
  const clusterColorById = new Map<string, string>();
  componentRoots.forEach((root, i) => {
    const hue = COLORS.CLUSTER_HUES[i % COLORS.CLUSTER_HUES.length];
    (componentMembers.get(root) || []).forEach((member) => {
      member.clusterIndex = i;
      clusterColorById.set(member.id, hue);
    });
  });

  // Cluster anchors spread across the filings band, alternating height so
  // several clusters don't cramp one row.
  const clusterCount = componentRoots.length;
  const anchors = componentRoots.map((_, i) => ({
    x:
      VIEW_WIDTH *
      (clusterCount === 1 ? 0.5 : 0.12 + 0.76 * (i / (clusterCount - 1))),
    y:
      VIEW_HEIGHT *
      (clusterCount <= 3
        ? FILINGS_BAND_Y
        : i % 2 === 0
        ? FILINGS_BAND_Y - 0.07
        : FILINGS_BAND_Y + 0.07),
  }));

  // ---- The law shelf -------------------------------------------------------
  const shelfNodes = simNodes.filter((n) => isLawKind(n.kind));
  const secNum = (n: SimNode) =>
    parseFloat(
      ((n.kind === KINDS.EXTERNAL ? ghostLabel(n) : shortLawLabel(n)).match(
        /\d+(\.\d+)?/
      ) || ["0"])[0]
    );
  const authorityRank = (n: SimNode) => {
    const i = GOVERNANCE_GRAPH_AUTHORITY_ORDER.indexOf(
      (n.authority || "") as (typeof GOVERNANCE_GRAPH_AUTHORITY_ORDER)[number]
    );
    return i === -1 ? GOVERNANCE_GRAPH_AUTHORITY_ORDER.length : i;
  };
  const shelfOrder = [...shelfNodes].sort(
    (a, b) =>
      authorityRank(a) - authorityRank(b) ||
      (a.authority || "").localeCompare(b.authority || "") ||
      secNum(a) - secNum(b)
  );
  let slot = 0;
  shelfOrder.forEach((n, i) => {
    if (i > 0 && shelfOrder[i - 1].authority !== n.authority) {
      slot += AUTHORITY_GROUP_GAP;
    }
    (n as SimNode & { slot: number }).slot = slot;
    slot += 1;
  });
  const totalSlots = Math.max(slot - 1, 1);
  const shelfLeft = VIEW_WIDTH * LAW_SHELF_INSET;
  const shelfRight = VIEW_WIDTH * (1 - LAW_SHELF_INSET);
  const shelfY = VIEW_HEIGHT * LAW_SHELF_Y;
  shelfOrder.forEach((n) => {
    const s = (n as SimNode & { slot: number }).slot;
    n.fx = shelfLeft + (s / totalSlots) * (shelfRight - shelfLeft);
    n.fy = shelfY;
    n.x = n.fx;
    n.y = n.fy;
  });

  // Seed filing positions (deterministic jitter). Swarm clusters seed across
  // the full band — each node then anchors to its OWN seed, and the link
  // force gathers exhibits around their primary into a wide constellation.
  const clusterSizes = new Map<number, number>();
  simNodes
    .filter((n) => !isLawKind(n.kind))
    .forEach((n) => {
      const idx = n.clusterIndex ?? 0;
      clusterSizes.set(idx, (clusterSizes.get(idx) || 0) + 1);
    });
  simNodes
    .filter((n) => !isLawKind(n.kind))
    .forEach((n) => {
      const idx = n.clusterIndex ?? 0;
      const swarm = (clusterSizes.get(idx) || 0) > SWARM_CLUSTER_SIZE;
      const anchor = anchors[idx] || {
        x: VIEW_WIDTH / 2,
        y: VIEW_HEIGHT * FILINGS_BAND_Y,
      };
      n.x = swarm
        ? VIEW_WIDTH * (0.1 + 0.8 * rand())
        : anchor.x + (rand() - 0.5) * 180;
      n.y = anchor.y + (rand() - 0.5) * 140;
      // Swarm nodes anchor to their own seed; cluster nodes to the anchor.
      (n as SimNode & { anchorX: number }).anchorX = swarm ? n.x : anchor.x;
      (n as SimNode & { anchorY: number }).anchorY = anchor.y;
    });

  // ---- Force simulation ----------------------------------------------------
  const links = edges
    .filter((e) => nodeById.has(e.source) && nodeById.has(e.target))
    .map((e) => ({ source: e.source, target: e.target, edgeType: e.edgeType }));

  const dense = simNodes.length > DENSE_NODE_THRESHOLD;
  const simulation = d3
    .forceSimulation<SimNode>(simNodes)
    .force(
      "link",
      d3
        .forceLink<
          SimNode,
          { source: string; target: string; edgeType: string }
        >(links)
        .id((d) => d.id)
        .distance((l) => (l.edgeType === EDGE_TYPES.DOCUMENT ? 55 : 130))
        .strength((l) => (l.edgeType === EDGE_TYPES.DOCUMENT ? 0.45 : 0.04))
    )
    .force("charge", d3.forceManyBody<SimNode>().strength(dense ? -58 : -90))
    .force(
      "collide",
      d3
        .forceCollide<SimNode>()
        // Honour actual render radii so dense filing clusters spread into a
        // readable texture instead of stacking into a blob; shelf nodes get
        // extra clearance for their labels.
        .radius((n) => n.r + (isLawKind(n.kind) ? 7 : 3))
        .iterations(2)
    )
    .force(
      "x",
      d3
        .forceX<SimNode>((n) =>
          isLawKind(n.kind)
            ? n.fx ?? VIEW_WIDTH / 2
            : (n as SimNode & { anchorX?: number }).anchorX ?? VIEW_WIDTH / 2
        )
        // Dense swarms hold their anchor loosely so charge can relax the
        // pack into a wide organic constellation instead of a packed disc.
        .strength((n) => (isLawKind(n.kind) ? 0.9 : dense ? 0.16 : 0.38))
    )
    .force(
      "y",
      d3
        .forceY<SimNode>((n) =>
          isLawKind(n.kind)
            ? shelfY
            : (n as SimNode & { anchorY?: number }).anchorY ??
              VIEW_HEIGHT * FILINGS_BAND_Y
        )
        .strength((n) => (isLawKind(n.kind) ? 0.9 : dense ? 0.1 : 0.18))
    )
    .stop();

  for (let i = 0; i < SIMULATION_TICKS; i += 1) {
    simulation.tick();
  }

  // Clamp filings into frame (the shelf is pinned and never strays). Leave
  // headroom below for shelf labels + authority captions.
  simNodes.forEach((n) => {
    if (isLawKind(n.kind)) return;
    n.x = Math.max(28, Math.min(VIEW_WIDTH - 28, n.x));
    n.y = Math.max(24, Math.min(shelfY - 70, n.y));
  });

  // Three-row label stagger by final x order so dense shelves stay legible.
  shelfNodes
    .slice()
    .sort((a, b) => a.x - b.x)
    .forEach((n, i) => {
      n.labelRow = i % 3;
    });

  // Authority caption positions (mean x of each group's sections).
  const authorityGroups = [
    ...new Set(shelfNodes.map((n) => n.authority || "")),
  ].map((authority) => {
    const xs = shelfNodes
      .filter((n) => (n.authority || "") === authority)
      .map((n) => n.x);
    return {
      authority,
      meanX: xs.reduce((s, x) => s + x, 0) / xs.length,
      size: xs.length,
    };
  });

  const shelfMaxDegree = shelfNodes.reduce((m, n) => Math.max(m, n.degree), 1);

  return {
    simNodes,
    nodeById,
    clusterColorById,
    shelfNodes,
    authorityGroups,
    dense,
    shelfMaxDegree,
  };
}

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
  } = useMemo(() => computeLayout(nodes, edges), [nodes, edges]);

  const nodeFill = (n: SimNode): string => {
    if (n.kind === KINDS.STATUTE) {
      return COLORS.AUTHORITY_FILLS[n.authority || ""] || COLORS.LAW_DEFAULT;
    }
    if (n.kind === KINDS.EXTERNAL) return COLORS.EXTERNAL;
    return clusterColorById.get(n.id) || COLORS.CLUSTER_HUES[0];
  };

  const edgeStroke = (e: GovernanceGraphEdge): string => {
    if (e.edgeType === EDGE_TYPES.LAW) return COLORS.LAW_DEFAULT;
    if (e.edgeType === EDGE_TYPES.LAW_EXTERNAL) return COLORS.EXTERNAL;
    return clusterColorById.get(e.source) || OS_LEGAL_COLORS.textMuted;
  };

  // Hover focus: incident edges + endpoint nodes stay full strength, the rest
  // recede. Null hover = neutral (everything at base opacity).
  const edgeEmphasis = (e: GovernanceGraphEdge): number => {
    if (!hoveredId) return 1;
    return e.source === hoveredId || e.target === hoveredId ? 1.6 : 0.25;
  };
  const nodeEmphasis = (n: SimNode): number => {
    if (!hoveredId) return 1;
    if (n.id === hoveredId) return 1;
    const incident = edges.some(
      (e) =>
        (e.source === hoveredId && e.target === n.id) ||
        (e.target === hoveredId && e.source === n.id)
    );
    return incident ? 1 : 0.35;
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
            <GraphTitle>
              <Scale size={16} />
              Governance graph
            </GraphTitle>
          </GraphHeader>
          <GraphSkeleton data-testid={`${testId}-skeleton`} />
        </GraphCard>
      );
    }
    if (error) {
      return (
        <GraphCard data-testid={testId}>
          <GraphHeader>
            <GraphTitle>
              <Scale size={16} />
              Governance graph
            </GraphTitle>
          </GraphHeader>
          <EmptyState data-testid={`${testId}-error`}>
            Couldn't load the governance graph. Please try again.
          </EmptyState>
        </GraphCard>
      );
    }
    return (
      <GraphCard data-testid={testId}>
        <GraphHeader>
          <GraphTitle>
            <Scale size={16} />
            Governance graph
          </GraphTitle>
        </GraphHeader>
        <EmptyState data-testid={`${testId}-empty`}>
          <EmptyMotif />
          <span>
            This collection's reference web hasn't been mapped yet. Once mapped,
            every exhibit cross-reference and statutory citation — down to the
            section of the law — appears here.
          </span>
          {emptyAction}
        </EmptyState>
      </GraphCard>
    );
  }

  const statuteCount = nodes.filter((n) => n.kind === KINDS.STATUTE).length;
  const hasExternal = externalKeyCount > 0;
  const shelfY = VIEW_HEIGHT * LAW_SHELF_Y;

  return (
    <GraphCard data-testid={testId}>
      <GraphHeader>
        <GraphTitle>
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
