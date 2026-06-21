/**
 * Shared deterministic layout for the corpus governance / reference web.
 *
 * The bipartite composition — filing documents floating in an upper band, the
 * law pinned on a shelf below, every statutory citation arcing down to the
 * exact section it resolves to — is the visual thesis of the reference web. It
 * is consumed at two scales:
 *
 *   - ``GovernanceGraphGlimpse`` — the small card on the corpus landing.
 *   - ``GovernanceGraphExplorer`` — the full-screen, zoomable explorer.
 *
 * Both render the SAME positions, so the explorer is a literal zoom-in on the
 * glimpse rather than a different picture. Extracting the layout here keeps a
 * single source of truth for the (intricate) geometry: the glimpse's pinned
 * screenshots stay pixel-identical because the math is unchanged — only its
 * home moved.
 *
 * Like the document glimpse, the layout is computed synchronously with
 * d3-force from seeded positions (LCG, no ``Math.random``) and consumed as
 * plain data — deterministic for a given input, no animation loop,
 * test-friendly.
 */
import * as d3 from "d3";

import {
  GOVERNANCE_GRAPH_LAYOUT,
  GOVERNANCE_GRAPH_NODE_KINDS,
  GOVERNANCE_GRAPH_EDGE_TYPES,
  GOVERNANCE_GRAPH_AUTHORITY_ORDER,
  GOVERNANCE_GRAPH_COLORS,
} from "../assets/configurations/constants";
import { GovernanceGraphNode, GovernanceGraphEdge } from "../graphql/queries";
import { OS_LEGAL_COLORS } from "../assets/configurations/osLegalStyles";
import { formatCanonicalLawKey } from "./formatters";
import { createSeededRandom, runSimulationTicks } from "./graphLayout";

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
const GOVERNANCE_GRAPH_CLUSTER_HUES = GOVERNANCE_GRAPH_COLORS.CLUSTER_HUES;

export interface GovSimNode extends GovernanceGraphNode {
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

export interface GovernanceLayout {
  simNodes: GovSimNode[];
  nodeById: Map<string, GovSimNode>;
  clusterColorById: Map<string, string>;
  shelfNodes: GovSimNode[];
  authorityGroups: { authority: string; meanX: number; size: number }[];
  /** Dense mode: degree-gated shelf labels, thinner edges, short captions. */
  dense: boolean;
  /** Highest degree among shelf nodes — the shelf-local emphasis scale. */
  shelfMaxDegree: number;
}

export const isLawKind = (kind: string): boolean =>
  kind === KINDS.STATUTE || kind === KINDS.EXTERNAL;

/** Shorten a statute/section title to its citation head:
 * "DGCL § 145 — Indemnification…" → "DGCL § 145". */
export function shortLawLabel(node: GovernanceGraphNode): string {
  const title = node.title || node.id;
  return title.split("—")[0].split("(")[0].trim();
}

/** Display form for a ghost key: "dgcl:203" → "DGCL § 203". */
export function ghostLabel(node: GovernanceGraphNode): string {
  return formatCanonicalLawKey(node.title || node.id.replace(/^key:/, ""));
}

/** Shorten a filing title to a cluster-anchor label:
 * "Space Exploration Technologies Corp. S-1 (2025-12-19)" → "Space
 * Exploration Technologies Corp. S-1". Falls back to a hard cap. */
export function shortFilingLabel(node: GovernanceGraphNode): string {
  const title = (node.title || "").trim();
  const m = title.match(/^(.+?\s(?:S-1(?:\/A)?|Form D|10-K|10-Q|8-K))\b/);
  const label = m ? m[1] : title;
  return label.length > 34 ? `${label.slice(0, 32)}…` : label;
}

/**
 * Node fill, keyed off the per-layout cluster colouring. Statutes take their
 * authority's amber, ghost (external) nodes the neutral slate, and every filing
 * its cluster hue. Shared by the glimpse and the explorer so both render the
 * same palette.
 */
export function makeNodeFill(
  clusterColorById: Map<string, string>
): (n: GovernanceGraphNode) => string {
  return (n) => {
    if (n.kind === KINDS.STATUTE) {
      return (
        GOVERNANCE_GRAPH_COLORS.AUTHORITY_FILLS[n.authority || ""] ||
        GOVERNANCE_GRAPH_COLORS.LAW_DEFAULT
      );
    }
    if (n.kind === KINDS.EXTERNAL) return GOVERNANCE_GRAPH_COLORS.EXTERNAL;
    return (
      clusterColorById.get(n.id) || GOVERNANCE_GRAPH_COLORS.CLUSTER_HUES[0]
    );
  };
}

/** Edge stroke: law citations amber, external (ghost) citations slate, and
 * document edges inherit their source cluster's hue. */
export function makeEdgeStroke(
  clusterColorById: Map<string, string>
): (e: GovernanceGraphEdge) => string {
  return (e) => {
    if (e.edgeType === EDGE_TYPES.LAW)
      return GOVERNANCE_GRAPH_COLORS.LAW_DEFAULT;
    if (e.edgeType === EDGE_TYPES.LAW_EXTERNAL)
      return GOVERNANCE_GRAPH_COLORS.EXTERNAL;
    return clusterColorById.get(e.source) || OS_LEGAL_COLORS.textMuted;
  };
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
export function computeGovernanceLayout(
  nodes: GovernanceGraphNode[],
  edges: GovernanceGraphEdge[]
): GovernanceLayout {
  // Deterministic pseudo-random for reproducible layouts (mirrors the demo).
  const rand = createSeededRandom(LAYOUT_SEED);

  const maxDegree = nodes.reduce((m, n) => Math.max(m, n.degree), 1);
  const nodeRadius = (n: GovernanceGraphNode): number => {
    const r =
      MIN_NODE_RADIUS +
      (MAX_NODE_RADIUS - MIN_NODE_RADIUS) * Math.sqrt(n.degree / maxDegree);
    if (n.kind === KINDS.PRIMARY) return Math.max(r, MIN_PRIMARY_RADIUS);
    if (isLawKind(n.kind)) return Math.min(r, MAX_SHELF_RADIUS);
    return r;
  };

  const simNodes: GovSimNode[] = nodes.map((node) => ({
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

  const componentMembers = new Map<string, GovSimNode[]>();
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
    const hue =
      GOVERNANCE_GRAPH_CLUSTER_HUES[i % GOVERNANCE_GRAPH_CLUSTER_HUES.length];
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
  const secNum = (n: GovSimNode) =>
    parseFloat(
      ((n.kind === KINDS.EXTERNAL ? ghostLabel(n) : shortLawLabel(n)).match(
        /\d+(\.\d+)?/
      ) || ["0"])[0]
    );
  const authorityRank = (n: GovSimNode) => {
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
    (n as GovSimNode & { slot: number }).slot = slot;
    slot += 1;
  });
  const totalSlots = Math.max(slot - 1, 1);
  const shelfLeft = VIEW_WIDTH * LAW_SHELF_INSET;
  const shelfRight = VIEW_WIDTH * (1 - LAW_SHELF_INSET);
  const shelfY = VIEW_HEIGHT * LAW_SHELF_Y;
  shelfOrder.forEach((n) => {
    const s = (n as GovSimNode & { slot: number }).slot;
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
      (n as GovSimNode & { anchorX: number }).anchorX = swarm ? n.x : anchor.x;
      (n as GovSimNode & { anchorY: number }).anchorY = anchor.y;
    });

  // ---- Force simulation ----------------------------------------------------
  const links = edges
    .filter((e) => nodeById.has(e.source) && nodeById.has(e.target))
    .map((e) => ({ source: e.source, target: e.target, edgeType: e.edgeType }));

  const dense = simNodes.length > DENSE_NODE_THRESHOLD;
  const simulation = d3
    .forceSimulation<GovSimNode>(simNodes)
    .force(
      "link",
      d3
        .forceLink<
          GovSimNode,
          { source: string; target: string; edgeType: string }
        >(links)
        .id((d) => d.id)
        .distance((l) => (l.edgeType === EDGE_TYPES.DOCUMENT ? 55 : 130))
        .strength((l) => (l.edgeType === EDGE_TYPES.DOCUMENT ? 0.45 : 0.04))
    )
    .force("charge", d3.forceManyBody<GovSimNode>().strength(dense ? -58 : -90))
    .force(
      "collide",
      d3
        .forceCollide<GovSimNode>()
        // Honour actual render radii so dense filing clusters spread into a
        // readable texture instead of stacking into a blob; shelf nodes get
        // extra clearance for their labels.
        .radius((n) => n.r + (isLawKind(n.kind) ? 7 : 3))
        .iterations(2)
    )
    .force(
      "x",
      d3
        .forceX<GovSimNode>((n) =>
          isLawKind(n.kind)
            ? n.fx ?? VIEW_WIDTH / 2
            : (n as GovSimNode & { anchorX?: number }).anchorX ?? VIEW_WIDTH / 2
        )
        // Dense swarms hold their anchor loosely so charge can relax the
        // pack into a wide organic constellation instead of a packed disc.
        .strength((n) => (isLawKind(n.kind) ? 0.9 : dense ? 0.16 : 0.38))
    )
    .force(
      "y",
      d3
        .forceY<GovSimNode>((n) =>
          isLawKind(n.kind)
            ? shelfY
            : (n as GovSimNode & { anchorY?: number }).anchorY ??
              VIEW_HEIGHT * FILINGS_BAND_Y
        )
        .strength((n) => (isLawKind(n.kind) ? 0.9 : dense ? 0.1 : 0.18))
    )
    .stop();

  runSimulationTicks(simulation, SIMULATION_TICKS);

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
