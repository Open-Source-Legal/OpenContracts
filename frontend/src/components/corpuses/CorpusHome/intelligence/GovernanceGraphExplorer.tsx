import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useQuery } from "@apollo/client";
import styled, { keyframes } from "styled-components";
import * as d3 from "d3";
import {
  ArrowLeft,
  Scale,
  Search,
  X,
  Loader2,
  ExternalLink,
  Plus,
  Minus,
  Maximize2,
  CircleSlash,
} from "lucide-react";

import { CorpusType } from "../../../../types/graphql-api";
import { OS_LEGAL_COLORS } from "../../../../assets/configurations/osLegalStyles";
import {
  CORPUS_BREAKPOINTS,
  CORPUS_RADII,
} from "../../styles/corpusDesignTokens";
import {
  GOVERNANCE_GRAPH_LAYOUT,
  GOVERNANCE_GRAPH_COLORS,
  GOVERNANCE_GRAPH_NODE_KINDS,
  GOVERNANCE_GRAPH_EDGE_TYPES,
  GOVERNANCE_GRAPH_AUTHORITY_ORDER,
  GOVERNANCE_GRAPH_AUTHORITY_CAPTIONS,
  GOVERNANCE_GRAPH_AUTHORITY_CAPTIONS_SHORT,
  GOVERNANCE_GRAPH_EXPLORER,
} from "../../../../assets/configurations/constants";
import {
  GET_GOVERNANCE_GRAPH,
  GetGovernanceGraphOutputType,
  GetGovernanceGraphInputType,
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
  GovSimNode,
} from "../../../../utils/governanceGraphLayout";
import { formatJurisdiction, titleCase } from "../../../../utils/formatters";
import { useNavigateToDocumentById } from "../../../../hooks/useNavigateToDocumentById";
import {
  BackButton,
  DetailsContainer,
  DetailsHeader,
  DetailsPage,
  DetailsTitle,
  DetailsTitleRow,
  DetailsTitleSection,
} from "../styles";

/**
 * GovernanceGraphExplorer — the reference web at full scale.
 *
 * The corpus landing shows a small, static glimpse of how the collection is
 * wired to the law; this is its destination. It renders the EXACT same
 * deterministic bipartite layout (``computeGovernanceLayout`` — filings above,
 * the law pinned on a shelf below) so the explorer reads as a literal zoom-in
 * on the glimpse, then layers on the things a glimpse can't afford:
 *
 *   - **Navigate** — pan + wheel-zoom (d3-zoom), fit/zoom controls.
 *   - **Find** — a search box that spotlights matching filings and statutes.
 *   - **Filter** — toggle filings / statute sections / cited-but-missing
 *     authorities, and isolate individual bodies of law. Filters DIM rather
 *     than remove, so nodes never jump — the map stays where you left it.
 *   - **Inspect** — click any node to open a detail drawer: its citations,
 *     jurisdiction, crawl status (for ghosts), and a jump into the document.
 *
 * Data + visibility are identical to the glimpse (``GET_GOVERNANCE_GRAPH``,
 * corpus-as-gate with per-document READ checks server-side); the backend caps
 * the graph at its most-connected 200 nodes, surfaced via ``truncated``.
 */

const { VIEW_WIDTH, VIEW_HEIGHT, LAW_SHELF_Y, LAW_SHELF_INSET } =
  GOVERNANCE_GRAPH_LAYOUT;
const KINDS = GOVERNANCE_GRAPH_NODE_KINDS;
const EDGE_TYPES = GOVERNANCE_GRAPH_EDGE_TYPES;
const COLORS = GOVERNANCE_GRAPH_COLORS;
const EXP = GOVERNANCE_GRAPH_EXPLORER; // short alias for the tuning knobs

/** The three filterable families the node kinds roll up into. */
type NodeGroup = "filings" | "statutes" | "wanted";
const ALL_GROUPS: NodeGroup[] = ["filings", "statutes", "wanted"];

const nodeGroup = (kind: string): NodeGroup =>
  kind === KINDS.STATUTE
    ? "statutes"
    : kind === KINDS.EXTERNAL
    ? "wanted"
    : "filings";

const GROUP_LABEL: Record<NodeGroup, string> = {
  filings: "Filings & exhibits",
  statutes: "Statute sections",
  wanted: "Cited — not ingested",
};

const KIND_LABEL: Record<string, string> = {
  [KINDS.PRIMARY]: "Filing",
  [KINDS.EXHIBIT]: "Exhibit",
  [KINDS.STATUTE]: "Statute section",
  [KINDS.EXTERNAL]: "Cited authority — not yet ingested",
};

/** Human labels for an authority-frontier crawl state (ghost nodes). */
const DISCOVERY_STATE_LABEL: Record<string, string> = {
  queued: "Queued for discovery",
  in_progress: "Discovery in progress",
  discovered: "Source located",
  ingested: "Ingested",
  resolved: "Resolved",
  failed: "Discovery failed",
  unsupported: "Unsupported source",
  blocked_license: "Blocked by license",
  unlocated: "Source not located",
  pending_approval: "Pending approval",
  deferred_cap: "Deferred (crawl cap reached)",
};

/** The display label a node shows on the canvas / in lists. */
function nodeLabel(n: GovernanceGraphNode): string {
  if (n.kind === KINDS.PRIMARY || n.kind === KINDS.EXHIBIT) {
    return shortFilingLabel(n) || n.title || "Untitled document";
  }
  if (n.kind === KINDS.EXTERNAL) return ghostLabel(n);
  return shortLawLabel(n);
}

/** Authority caption, e.g. "dgcl" → "Delaware Gen. Corp. Law". */
function authorityCaption(authority: string): string {
  const cap = GOVERNANCE_GRAPH_AUTHORITY_CAPTIONS[authority];
  // The shared captions are upper-cased for the shelf; soften to title case for
  // the rail/drawer where they read as prose.
  return cap
    ? cap
        .toLowerCase()
        .replace(/\b\w/g, (c) => c.toUpperCase())
        .replace(/Of/g, "of")
    : authority.toUpperCase();
}

const spin = keyframes`
  to { transform: rotate(360deg); }
`;
const slideIn = keyframes`
  from { transform: translateX(16px); opacity: 0; }
  to { transform: translateX(0); opacity: 1; }
`;

const HeaderSubtitle = styled.div`
  font-size: 0.8125rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
  margin-top: 0.15rem;
`;

const MetaRow = styled.div`
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.4rem 0.9rem;
  margin-top: 0.5rem;
  font-size: 0.75rem;
  color: ${OS_LEGAL_COLORS.textMuted};
  font-variant-numeric: tabular-nums;
`;

const TruncatedChip = styled.span`
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.1rem 0.5rem;
  border-radius: ${CORPUS_RADII.full};
  background: ${OS_LEGAL_COLORS.warningSurface};
  color: ${OS_LEGAL_COLORS.warningText};
  border: 1px solid ${OS_LEGAL_COLORS.warningBorder};
  font-weight: 600;
`;

const ExplorerBody = styled.div`
  flex: 1;
  min-height: 0;
  display: flex;
  position: relative;

  @media (max-width: ${CORPUS_BREAKPOINTS.tablet}px) {
    flex-direction: column;
  }
`;

const Rail = styled.aside`
  flex: 0 0 268px;
  width: 268px;
  display: flex;
  flex-direction: column;
  gap: 1.1rem;
  padding: 1.1rem 1.1rem 1.4rem;
  border-right: 1px solid ${OS_LEGAL_COLORS.border};
  background: ${OS_LEGAL_COLORS.surface};
  overflow-y: auto;

  @media (max-width: ${CORPUS_BREAKPOINTS.tablet}px) {
    flex: none;
    width: 100%;
    flex-direction: row;
    flex-wrap: wrap;
    gap: 0.75rem;
    border-right: none;
    border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
    overflow-y: visible;
  }
`;

const RailGroup = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.55rem;
`;

const RailLabel = styled.div`
  font-size: 0.6875rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: ${OS_LEGAL_COLORS.textMuted};
`;

const SearchBox = styled.div`
  position: relative;
  display: flex;
  align-items: center;

  svg.lead {
    position: absolute;
    left: 0.6rem;
    width: 14px;
    height: 14px;
    color: ${OS_LEGAL_COLORS.textMuted};
    pointer-events: none;
  }

  input {
    width: 100%;
    padding: 0.5rem 1.7rem 0.5rem 1.85rem;
    font-size: 0.8125rem;
    color: ${OS_LEGAL_COLORS.textPrimary};
    background: ${OS_LEGAL_COLORS.surfaceLight};
    border: 1px solid ${OS_LEGAL_COLORS.border};
    border-radius: 9px;
    outline: none;
    transition: border-color 0.15s ease, background 0.15s ease;

    &:focus {
      border-color: ${OS_LEGAL_COLORS.primaryBlue};
      background: ${OS_LEGAL_COLORS.surface};
    }

    &::placeholder {
      color: ${OS_LEGAL_COLORS.textMuted};
    }
  }

  button.clear {
    position: absolute;
    right: 0.45rem;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 18px;
    height: 18px;
    border: none;
    border-radius: ${CORPUS_RADII.full};
    background: transparent;
    color: ${OS_LEGAL_COLORS.textMuted};
    cursor: pointer;

    &:hover {
      background: ${OS_LEGAL_COLORS.surfaceLight};
      color: ${OS_LEGAL_COLORS.textSecondary};
    }

    svg {
      width: 12px;
      height: 12px;
    }
  }
`;

/** Pill toggle for a node-group / authority filter. */
const FilterChip = styled.button<{ $active: boolean; $dot?: string }>`
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  padding: 0.34rem 0.6rem;
  font-size: 0.78125rem;
  font-weight: 600;
  text-align: left;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.12s ease, border-color 0.12s ease, opacity 0.12s ease;
  border: 1px solid
    ${(p) => (p.$active ? OS_LEGAL_COLORS.borderHover : OS_LEGAL_COLORS.border)};
  background: ${(p) =>
    p.$active ? OS_LEGAL_COLORS.surfaceLight : OS_LEGAL_COLORS.surface};
  color: ${(p) =>
    p.$active ? OS_LEGAL_COLORS.textPrimary : OS_LEGAL_COLORS.textMuted};
  opacity: ${(p) => (p.$active ? 1 : 0.6)};

  &:hover {
    border-color: ${OS_LEGAL_COLORS.borderHover};
  }

  .dot {
    flex: 0 0 9px;
    width: 9px;
    height: 9px;
    border-radius: ${CORPUS_RADII.full};
    background: ${(p) => p.$dot || OS_LEGAL_COLORS.textMuted};
  }

  .ghost-dot {
    flex: 0 0 9px;
    width: 9px;
    height: 9px;
    border-radius: ${CORPUS_RADII.full};
    border: 1.5px dashed ${COLORS.EXTERNAL};
  }

  .count {
    margin-left: auto;
    font-weight: 500;
    color: ${OS_LEGAL_COLORS.textMuted};
    font-variant-numeric: tabular-nums;
  }
`;

const ChipWrap = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
`;

const LegendRow = styled.div`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.75rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
`;

const CanvasWrap = styled.div`
  position: relative;
  flex: 1;
  min-height: 0;
  overflow: hidden;
  background-color: ${OS_LEGAL_COLORS.canvasPaper};
  background-image: radial-gradient(
    ${OS_LEGAL_COLORS.border} 0.8px,
    transparent 0.8px
  );
  background-size: 22px 22px;

  svg.canvas {
    display: block;
    width: 100%;
    height: 100%;
    cursor: grab;
    touch-action: none;

    &:active {
      cursor: grabbing;
    }
  }
`;

const ZoomCluster = styled.div<{ $drawerOpen: boolean }>`
  position: absolute;
  /* Slide clear of the detail drawer (340px) when it is open so the controls
     are never occluded. */
  right: ${(p) => (p.$drawerOpen ? "calc(340px + 1rem)" : "1rem")};
  bottom: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  z-index: 6;
  transition: right 0.18s ease;

  @media (max-width: ${CORPUS_BREAKPOINTS.tablet}px) {
    right: 1rem;
    /* On mobile the drawer is a bottom sheet — lift the controls above it. */
    bottom: ${(p) => (p.$drawerOpen ? "calc(58% + 1rem)" : "1rem")};
  }
`;

const ZoomButton = styled.button`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 9px;
  background: rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(8px);
  color: ${OS_LEGAL_COLORS.textSecondary};
  cursor: pointer;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.08);
  transition: color 0.12s ease, border-color 0.12s ease;

  &:hover {
    color: ${OS_LEGAL_COLORS.primaryBlue};
    border-color: ${OS_LEGAL_COLORS.borderHover};
  }

  svg {
    width: 16px;
    height: 16px;
  }
`;

const Centered = styled.div`
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  text-align: center;
  padding: 2rem;
  color: ${OS_LEGAL_COLORS.textSecondary};

  svg.spin {
    width: 22px;
    height: 22px;
    color: ${OS_LEGAL_COLORS.primaryBlue};
    animation: ${spin} 1.1s linear infinite;
  }

  .title {
    font-size: 1rem;
    font-weight: 600;
    color: ${OS_LEGAL_COLORS.textPrimary};
  }

  .body {
    max-width: 26rem;
    font-size: 0.875rem;
    line-height: 1.55;
  }
`;

const Drawer = styled.div`
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  width: 340px;
  max-width: calc(100% - 1rem);
  display: flex;
  flex-direction: column;
  gap: 0.9rem;
  padding: 1.1rem 1.15rem 1.3rem;
  background: rgba(255, 255, 255, 0.97);
  backdrop-filter: blur(10px);
  border-left: 1px solid ${OS_LEGAL_COLORS.border};
  box-shadow: -8px 0 28px rgba(15, 23, 42, 0.08);
  overflow-y: auto;
  z-index: 5;
  animation: ${slideIn} 0.18s ease-out;

  @media (max-width: ${CORPUS_BREAKPOINTS.tablet}px) {
    width: 100%;
    max-width: 100%;
    top: auto;
    height: 58%;
    border-left: none;
    border-top: 1px solid ${OS_LEGAL_COLORS.border};
    box-shadow: 0 -8px 28px rgba(15, 23, 42, 0.1);
  }
`;

const DrawerHead = styled.div`
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.6rem;
`;

const KindBadge = styled.span<{ $fill: string; $ghost?: boolean }>`
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.6875rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: ${(p) => (p.$ghost ? COLORS.EXTERNAL : p.$fill)};

  .swatch {
    width: 10px;
    height: 10px;
    border-radius: ${CORPUS_RADII.full};
    background: ${(p) => (p.$ghost ? "transparent" : p.$fill)};
    border: ${(p) => (p.$ghost ? `1.5px dashed ${COLORS.EXTERNAL}` : "none")};
  }
`;

const DrawerClose = styled.button`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  flex: 0 0 26px;
  border: none;
  border-radius: ${CORPUS_RADII.full};
  background: ${OS_LEGAL_COLORS.surfaceLight};
  color: ${OS_LEGAL_COLORS.textMuted};
  cursor: pointer;

  &:hover {
    color: ${OS_LEGAL_COLORS.textSecondary};
    background: ${OS_LEGAL_COLORS.surfaceHover};
  }

  svg {
    width: 14px;
    height: 14px;
  }
`;

const DrawerTitle = styled.h3`
  margin: 0;
  font-size: 1.0625rem;
  line-height: 1.35;
  color: ${OS_LEGAL_COLORS.textPrimary};
  word-break: break-word;
`;

const FactList = styled.dl`
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 0.4rem 0.9rem;
  margin: 0;
  font-size: 0.8125rem;

  dt {
    color: ${OS_LEGAL_COLORS.textMuted};
    font-weight: 500;
  }
  dd {
    margin: 0;
    color: ${OS_LEGAL_COLORS.textPrimary};
    text-align: right;
    font-variant-numeric: tabular-nums;
  }
`;

const StatusChip = styled.span`
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.12rem 0.55rem;
  border-radius: ${CORPUS_RADII.full};
  font-size: 0.75rem;
  font-weight: 600;
  background: ${OS_LEGAL_COLORS.surfaceLight};
  color: ${OS_LEGAL_COLORS.textSecondary};
  border: 1px solid ${OS_LEGAL_COLORS.border};
`;

const OpenDocButton = styled.button`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  width: 100%;
  padding: 0.55rem 1rem;
  border: none;
  border-radius: 10px;
  background: ${OS_LEGAL_COLORS.primaryBlue};
  color: white;
  font-size: 0.8125rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s ease;

  &:hover {
    background: ${OS_LEGAL_COLORS.primaryBlueHover};
  }

  svg {
    width: 15px;
    height: 15px;
  }
`;

const NeighborList = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
`;

const NeighborRow = styled.button`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  width: 100%;
  padding: 0.4rem 0.5rem;
  border: none;
  border-radius: 8px;
  background: transparent;
  text-align: left;
  cursor: pointer;
  font-size: 0.8125rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
  transition: background 0.12s ease;

  &:hover {
    background: ${OS_LEGAL_COLORS.surfaceLight};
    color: ${OS_LEGAL_COLORS.textPrimary};
  }

  .ndot {
    flex: 0 0 9px;
    width: 9px;
    height: 9px;
    border-radius: ${CORPUS_RADII.full};
  }

  .nlabel {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .nweight {
    margin-left: auto;
    color: ${OS_LEGAL_COLORS.textMuted};
    font-variant-numeric: tabular-nums;
    font-size: 0.75rem;
  }
`;

// Stable empty references so the layout memo stays cached while loading.
const EMPTY_NODES: GovernanceGraphNode[] = [];
const EMPTY_EDGES: GovernanceGraphEdge[] = [];

export interface GovernanceGraphExplorerProps {
  corpus: CorpusType;
  /** Return to the corpus landing/overview. */
  onBack: () => void;
  testId?: string;
}

export const GovernanceGraphExplorer: React.FC<
  GovernanceGraphExplorerProps
> = ({ corpus, onBack, testId = "governance-graph-explorer" }) => {
  const navigateToDocument = useNavigateToDocumentById();

  const variables = useMemo<GetGovernanceGraphInputType>(
    () => ({ corpusId: corpus.id }),
    [corpus.id]
  );
  const { data, loading, error } = useQuery<
    GetGovernanceGraphOutputType,
    GetGovernanceGraphInputType
  >(GET_GOVERNANCE_GRAPH, { variables });

  const graph = data?.governanceGraph;
  const nodes = graph?.nodes ?? EMPTY_NODES;
  const edges = graph?.edges ?? EMPTY_EDGES;

  // ---- Interaction state --------------------------------------------------
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [enabledGroups, setEnabledGroups] = useState<Set<NodeGroup>>(
    () => new Set(ALL_GROUPS)
  );
  const [disabledAuthorities, setDisabledAuthorities] = useState<Set<string>>(
    () => new Set()
  );
  const [transform, setTransform] = useState<d3.ZoomTransform>(d3.zoomIdentity);

  const svgRef = useRef<SVGSVGElement | null>(null);
  const zoomRef = useRef<d3.ZoomBehavior<SVGSVGElement, unknown> | null>(null);

  // ---- Layout (computed once on the full graph; filters never reflow it) ---
  const layout = useMemo(
    () => computeGovernanceLayout(nodes, edges),
    [nodes, edges]
  );
  const { simNodes, nodeById, clusterColorById, authorityGroups, dense } =
    layout;
  const shelfMaxDegree = layout.shelfMaxDegree;

  // Authorities present, in canonical order (registered first, then alpha).
  const authorities = useMemo(() => {
    const present = new Map<string, number>();
    for (const n of simNodes) {
      if (isLawKind(n.kind) && n.authority) {
        present.set(n.authority, (present.get(n.authority) ?? 0) + 1);
      }
    }
    const rank = (a: string) => {
      const i = (GOVERNANCE_GRAPH_AUTHORITY_ORDER as readonly string[]).indexOf(
        a
      );
      return i === -1 ? GOVERNANCE_GRAPH_AUTHORITY_ORDER.length : i;
    };
    return [...present.entries()]
      .map(([authority, count]) => ({ authority, count }))
      .sort(
        (a, b) =>
          rank(a.authority) - rank(b.authority) ||
          a.authority.localeCompare(b.authority)
      );
  }, [simNodes]);

  const groupCounts = useMemo(() => {
    const c: Record<NodeGroup, number> = { filings: 0, statutes: 0, wanted: 0 };
    for (const n of simNodes) c[nodeGroup(n.kind)] += 1;
    return c;
  }, [simNodes]);

  // ---- Derived predicates -------------------------------------------------
  const filterPass = useCallback(
    (n: GovernanceGraphNode): boolean => {
      if (!enabledGroups.has(nodeGroup(n.kind))) return false;
      if (n.authority && disabledAuthorities.has(n.authority)) return false;
      return true;
    },
    [enabledGroups, disabledAuthorities]
  );

  const focusId = selectedId ?? hoveredId;
  const neighborIds = useMemo(() => {
    if (!focusId) return null;
    const s = new Set<string>();
    for (const e of edges) {
      if (e.source === focusId) s.add(e.target);
      else if (e.target === focusId) s.add(e.source);
    }
    return s;
  }, [focusId, edges]);

  const searchActive = search.trim().length > 0;
  const matchedIds = useMemo(() => {
    if (!searchActive) return null;
    const q = search.trim().toLowerCase();
    const s = new Set<string>();
    for (const n of simNodes) {
      const hay = `${nodeLabel(n)} ${n.title ?? ""} ${n.authority ?? ""} ${
        formatJurisdiction(n.jurisdiction) ?? ""
      }`.toLowerCase();
      if (hay.includes(q)) s.add(n.id);
    }
    return s;
  }, [search, simNodes, searchActive]);

  const selectedNode = selectedId ? nodeById.get(selectedId) ?? null : null;

  // ---- Opacity model ------------------------------------------------------
  const nodeAlpha = useCallback(
    (n: GovSimNode): number => {
      if (!filterPass(n)) return EXP.FILTERED_ALPHA;
      if (focusId)
        return n.id === focusId || neighborIds?.has(n.id)
          ? 1
          : EXP.UNFOCUSED_ALPHA;
      if (searchActive) return matchedIds?.has(n.id) ? 1 : EXP.UNMATCHED_ALPHA;
      return 1;
    },
    [filterPass, focusId, neighborIds, searchActive, matchedIds]
  );

  const edgeAlpha = useCallback(
    (e: GovernanceGraphEdge): number => {
      const s = nodeById.get(e.source);
      const t = nodeById.get(e.target);
      if (!s || !t || !filterPass(s) || !filterPass(t))
        return EXP.FILTERED_ALPHA;
      if (focusId)
        return e.source === focusId || e.target === focusId
          ? 1
          : EXP.UNFOCUSED_ALPHA * 0.5;
      if (searchActive)
        return matchedIds?.has(e.source) || matchedIds?.has(e.target)
          ? 1
          : EXP.UNMATCHED_ALPHA * 0.5;
      return 1;
    },
    [nodeById, filterPass, focusId, searchActive, matchedIds]
  );

  // Labels: spotlight + focus neighbourhood + search hits always; everything
  // else gates on shelf-local degree, with the gate easing open as you zoom in.
  const labelGate =
    shelfMaxDegree *
    Math.max(
      EXP.LABEL_DEGREE_FRACTION / transform.k,
      EXP.LABEL_DEGREE_FRACTION_MIN
    );
  const showLabel = useCallback(
    (n: GovSimNode): boolean => {
      if (!filterPass(n)) return false;
      if (focusId) return n.id === focusId || !!neighborIds?.has(n.id);
      if (searchActive) return !!matchedIds?.has(n.id);
      if (n.kind === KINDS.PRIMARY) return true;
      return n.degree >= labelGate;
    },
    [filterPass, focusId, neighborIds, searchActive, matchedIds, labelGate]
  );

  // ---- Colours (shared with the glimpse; keyed off this layout's clusters) -
  const nodeFill = useMemo(
    () => makeNodeFill(clusterColorById),
    [clusterColorById]
  );
  const edgeStroke = useMemo(
    () => makeEdgeStroke(clusterColorById),
    [clusterColorById]
  );

  // ---- d3-zoom wiring -----------------------------------------------------
  useEffect(() => {
    const svgEl = svgRef.current;
    if (!svgEl) return;
    const selection = d3.select<SVGSVGElement, unknown>(svgEl);
    const zoom = d3
      .zoom<SVGSVGElement, unknown>()
      .scaleExtent([EXP.ZOOM_MIN, EXP.ZOOM_MAX])
      .on("zoom", (event) => setTransform(event.transform));
    selection.call(zoom);
    // A double-click should reset the view, not punch a zoom step.
    selection.on("dblclick.zoom", null);
    zoomRef.current = zoom;
    return () => {
      // Cancel any in-flight zoom transition (zoomBy / resetView run 200–260ms
      // d3 transitions) before detaching, so a tween can't fire setTransform on
      // an unmounted component if the user navigates away mid-transition.
      d3.interrupt(svgEl);
      selection.on(".zoom", null);
    };
  }, []);

  // Escape closes the detail drawer — the expected dismissal gesture.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setSelectedId(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // If the selected node is filtered out of view (its layer or body of law
  // toggled off), close the drawer so the canvas and the inspector never
  // disagree about what's visible.
  useEffect(() => {
    if (selectedNode && !filterPass(selectedNode)) setSelectedId(null);
  }, [selectedNode, filterPass]);

  const zoomBy = useCallback((factor: number) => {
    const svgEl = svgRef.current;
    if (!svgEl || !zoomRef.current) return;
    d3.select<SVGSVGElement, unknown>(svgEl)
      .transition()
      .duration(200)
      .call(zoomRef.current.scaleBy, factor);
  }, []);

  const resetView = useCallback(() => {
    const svgEl = svgRef.current;
    if (!svgEl || !zoomRef.current) return;
    d3.select<SVGSVGElement, unknown>(svgEl)
      .transition()
      .duration(260)
      .call(zoomRef.current.transform, d3.zoomIdentity);
  }, []);

  // Selecting a node clears any hover so the drawer's neighbourhood wins.
  const handleSelect = useCallback((id: string) => {
    setHoveredId(null);
    setSelectedId(id);
  }, []);

  const toggleGroup = useCallback((g: NodeGroup) => {
    setEnabledGroups((prev) => {
      const next = new Set(prev);
      if (next.has(g)) next.delete(g);
      else next.add(g);
      return next;
    });
  }, []);

  const toggleAuthority = useCallback((a: string) => {
    setDisabledAuthorities((prev) => {
      const next = new Set(prev);
      if (next.has(a)) next.delete(a);
      else next.add(a);
      return next;
    });
  }, []);

  const handleOpenDocument = useCallback(
    (documentId: string) => {
      void navigateToDocument(documentId);
    },
    [navigateToDocument]
  );

  // ---- Header counts ------------------------------------------------------
  const documentCount = graph?.documentCount ?? 0;
  const externalKeyCount = graph?.externalKeyCount ?? 0;
  const mentionCount = graph?.mentionCount ?? 0;
  const truncated = graph?.truncated ?? false;
  const statuteCount = useMemo(
    () => simNodes.filter((n) => n.kind === KINDS.STATUTE).length,
    [simNodes]
  );
  const hasNodes = simNodes.length > 0;
  const shelfY = VIEW_HEIGHT * LAW_SHELF_Y;
  const zoomTransform = `translate(${transform.x},${transform.y}) scale(${transform.k})`;

  const renderCanvasOverlay = () => {
    if (loading && !graph)
      return (
        <Centered data-testid={`${testId}-loading`}>
          <Loader2 className="spin" />
          <div className="title">Loading the reference web…</div>
        </Centered>
      );
    if (error && !graph)
      return (
        <Centered data-testid={`${testId}-error`}>
          <CircleSlash size={26} color={OS_LEGAL_COLORS.danger} />
          <div className="title">Couldn&rsquo;t load the reference web</div>
          <div className="body">
            Something went wrong fetching this collection&rsquo;s citations. Try
            reloading the page.
          </div>
        </Centered>
      );
    if (!hasNodes)
      return (
        <Centered data-testid={`${testId}-empty`}>
          <Scale size={26} color={COLORS.LAW_DEFAULT} />
          <div className="title">No reference web yet</div>
          <div className="body">
            This collection&rsquo;s citations haven&rsquo;t been mapped. Return
            to the overview and choose <strong>Map the reference web</strong> to
            weave it — every statutory citation, down to the section, will
            appear here.
          </div>
        </Centered>
      );
    return null;
  };

  return (
    <DetailsContainer data-testid={testId}>
      <DetailsPage>
        <DetailsHeader>
          <BackButton
            onClick={onBack}
            data-testid={`${testId}-back`}
            whileTap={{ scale: 0.97 }}
          >
            <ArrowLeft aria-hidden="true" />
            Overview
          </BackButton>
          <DetailsTitleRow>
            <DetailsTitleSection>
              <DetailsTitle>Reference web</DetailsTitle>
              <HeaderSubtitle>
                How {corpus.title || "this collection"} is wired to the law
              </HeaderSubtitle>
              <MetaRow data-testid={`${testId}-meta`}>
                <span>
                  {documentCount}{" "}
                  {documentCount === 1 ? "document" : "documents"}
                </span>
                {statuteCount > 0 && (
                  <span>
                    {statuteCount} statute{" "}
                    {statuteCount === 1 ? "section" : "sections"}
                  </span>
                )}
                <span>
                  {mentionCount}{" "}
                  {mentionCount === 1 ? "reference" : "references"} resolved
                </span>
                {externalKeyCount > 0 && (
                  <span>{externalKeyCount} cited, not ingested</span>
                )}
                {truncated && (
                  <TruncatedChip data-testid={`${testId}-truncated`}>
                    showing the most-connected {simNodes.length}
                  </TruncatedChip>
                )}
              </MetaRow>
            </DetailsTitleSection>
          </DetailsTitleRow>
        </DetailsHeader>

        <ExplorerBody>
          {hasNodes && (
            <Rail data-testid={`${testId}-rail`}>
              <RailGroup>
                <RailLabel>Find</RailLabel>
                <SearchBox>
                  <Search className="lead" aria-hidden="true" />
                  <input
                    type="text"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="Search filings & statutes…"
                    aria-label="Search the reference web"
                    data-testid={`${testId}-search`}
                  />
                  {searchActive && (
                    <button
                      type="button"
                      className="clear"
                      onClick={() => setSearch("")}
                      aria-label="Clear search"
                    >
                      <X />
                    </button>
                  )}
                </SearchBox>
              </RailGroup>

              <RailGroup>
                <RailLabel>Layers</RailLabel>
                <ChipWrap>
                  {ALL_GROUPS.map((g) => (
                    <FilterChip
                      key={g}
                      type="button"
                      $active={enabledGroups.has(g)}
                      $dot={
                        g === "filings"
                          ? COLORS.CLUSTER_HUES[0]
                          : g === "statutes"
                          ? COLORS.LAW_DEFAULT
                          : undefined
                      }
                      onClick={() => toggleGroup(g)}
                      data-testid={`${testId}-group-${g}`}
                      aria-pressed={enabledGroups.has(g)}
                    >
                      {g === "wanted" ? (
                        <span className="ghost-dot" />
                      ) : (
                        <span className="dot" />
                      )}
                      {GROUP_LABEL[g]}
                      <span className="count">{groupCounts[g]}</span>
                    </FilterChip>
                  ))}
                </ChipWrap>
              </RailGroup>

              {authorities.length > 0 && (
                <RailGroup>
                  <RailLabel>Bodies of law</RailLabel>
                  <ChipWrap>
                    {authorities.map(({ authority, count }) => {
                      const active = !disabledAuthorities.has(authority);
                      return (
                        <FilterChip
                          key={authority}
                          type="button"
                          $active={active}
                          $dot={
                            COLORS.AUTHORITY_FILLS[authority] ||
                            COLORS.LAW_DEFAULT
                          }
                          onClick={() => toggleAuthority(authority)}
                          data-testid={`${testId}-authority-${authority}`}
                          aria-pressed={active}
                        >
                          <span className="dot" />
                          {authorityCaption(authority)}
                          <span className="count">{count}</span>
                        </FilterChip>
                      );
                    })}
                  </ChipWrap>
                </RailGroup>
              )}

              <RailGroup>
                <RailLabel>Legend</RailLabel>
                <LegendRow>
                  <svg width="13" height="13" aria-hidden="true">
                    <circle
                      cx="6.5"
                      cy="6.5"
                      r="5.5"
                      fill={COLORS.CLUSTER_HUES[0]}
                      fillOpacity="0.9"
                    />
                  </svg>
                  Filing &amp; its exhibits
                </LegendRow>
                <LegendRow>
                  <svg width="13" height="13" aria-hidden="true">
                    <circle
                      cx="6.5"
                      cy="6.5"
                      r="5.5"
                      fill={COLORS.LAW_DEFAULT}
                    />
                  </svg>
                  Statute section (in-system)
                </LegendRow>
                <LegendRow>
                  <svg width="13" height="13" aria-hidden="true">
                    <circle
                      cx="6.5"
                      cy="6.5"
                      r="5"
                      fill="white"
                      stroke={COLORS.EXTERNAL}
                      strokeWidth="1.3"
                      strokeDasharray="2.5 2.5"
                    />
                  </svg>
                  Cited, not yet ingested
                </LegendRow>
                <LegendRow>
                  <svg width="26" height="9" aria-hidden="true">
                    <line
                      x1="1"
                      y1="4.5"
                      x2="25"
                      y2="4.5"
                      stroke={COLORS.LAW_DEFAULT}
                      strokeWidth="2"
                      strokeOpacity="0.7"
                    />
                  </svg>
                  Citation (thicker = more)
                </LegendRow>
              </RailGroup>
            </Rail>
          )}

          <CanvasWrap data-testid={`${testId}-canvas`}>
            {hasNodes && (
              <svg
                ref={svgRef}
                className="canvas"
                viewBox={`0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`}
                preserveAspectRatio="xMidYMid meet"
                role="img"
                aria-label="Reference web: documents above, cited law below"
                data-testid={`${testId}-svg`}
              >
                <defs>
                  <filter
                    id="explorer-halo"
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
                  <linearGradient id="explorer-bg" x1="0" y1="0" x2="0" y2="1">
                    <stop
                      offset="0%"
                      stopColor={OS_LEGAL_COLORS.canvasVignetteInner}
                    />
                    <stop
                      offset="62%"
                      stopColor={OS_LEGAL_COLORS.canvasVignetteMid}
                    />
                    <stop
                      offset="100%"
                      stopColor={OS_LEGAL_COLORS.canvasVignetteOuter}
                    />
                  </linearGradient>
                </defs>

                <g transform={zoomTransform}>
                  {/* Paper sheet — a click on it clears the selection. */}
                  <rect
                    x={-VIEW_WIDTH}
                    y={-VIEW_HEIGHT}
                    width={VIEW_WIDTH * 3}
                    height={VIEW_HEIGHT * 3}
                    fill="url(#explorer-bg)"
                    onClick={() => setSelectedId(null)}
                  />

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
                      const isExternal =
                        edge.edgeType === EDGE_TYPES.LAW_EXTERNAL;
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
                            baseOpacity * edgeAlpha(edge),
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
                      const alpha = nodeAlpha(node);
                      const isSelected = node.id === selectedId;
                      const clickable = filterPass(node);
                      const halo =
                        node.kind === KINDS.PRIMARY ||
                        (node.kind === KINDS.STATUTE &&
                          node.degree >= shelfMaxDegree * 0.35);
                      return (
                        <g key={node.id}>
                          {isSelected && (
                            <circle
                              cx={node.x}
                              cy={node.y}
                              r={node.r + 5}
                              fill="none"
                              stroke={OS_LEGAL_COLORS.primaryBlue}
                              strokeWidth={2}
                              strokeOpacity={0.9}
                            />
                          )}
                          <circle
                            cx={node.x}
                            cy={node.y}
                            r={node.r}
                            fill={isExternal ? "white" : fill}
                            fillOpacity={
                              (isExternal
                                ? 0.9
                                : node.kind === KINDS.EXHIBIT
                                ? 0.8
                                : 0.95) * alpha
                            }
                            stroke={
                              isExternal
                                ? COLORS.EXTERNAL
                                : d3.color(fill)?.darker(0.5)?.toString() ||
                                  fill
                            }
                            strokeOpacity={alpha}
                            strokeWidth={node.kind === KINDS.PRIMARY ? 2 : 1.1}
                            strokeDasharray={isExternal ? "3 3" : undefined}
                            filter={halo ? "url(#explorer-halo)" : undefined}
                            cursor={clickable ? "pointer" : "default"}
                            onMouseEnter={() =>
                              clickable && setHoveredId(node.id)
                            }
                            onMouseLeave={() => setHoveredId(null)}
                            onClick={
                              clickable
                                ? (e) => {
                                    e.stopPropagation();
                                    handleSelect(node.id);
                                  }
                                : undefined
                            }
                            data-testid={`${testId}-node`}
                            data-node-kind={node.kind}
                          >
                            <title>
                              {(isExternal
                                ? `${ghostLabel(
                                    node
                                  )} — cited, not yet ingested`
                                : node.title || "Untitled document") +
                                ` · ${node.degree} ${
                                  node.degree === 1 ? "reference" : "references"
                                }`}
                            </title>
                          </circle>
                        </g>
                      );
                    })}
                  </g>

                  <g data-testid={`${testId}-labels`}>
                    {simNodes.filter(showLabel).map((node) => {
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
                            node.kind === KINDS.PRIMARY ||
                            node.kind === KINDS.STATUTE
                              ? 600
                              : 400
                          }
                          fill={fill}
                          opacity={nodeAlpha(node)}
                          paintOrder="stroke"
                          stroke="white"
                          strokeWidth={3}
                          pointerEvents="none"
                        >
                          {nodeLabel(node)}
                        </text>
                      );
                    })}
                  </g>

                  <g data-testid={`${testId}-authority-captions`}>
                    {authorityGroups.map(({ authority, meanX }, i) => (
                      <text
                        key={`authority-${authority}`}
                        x={meanX}
                        y={VIEW_HEIGHT - (i % 2 === 0 ? 22 : 8)}
                        textAnchor="middle"
                        fontSize={9.5}
                        letterSpacing="0.18em"
                        fill={COLORS.LAW_CAPTION}
                        fontWeight={600}
                        opacity={
                          disabledAuthorities.has(authority)
                            ? EXP.FILTERED_ALPHA
                            : 1
                        }
                      >
                        {/* Short forms on the shelf so adjacent groups never
                            collide; the rail carries the full names. */}
                        {GOVERNANCE_GRAPH_AUTHORITY_CAPTIONS_SHORT[authority] ||
                          GOVERNANCE_GRAPH_AUTHORITY_CAPTIONS[authority] ||
                          authority.toUpperCase()}
                      </text>
                    ))}
                  </g>
                </g>
              </svg>
            )}

            {renderCanvasOverlay()}

            {hasNodes && (
              <ZoomCluster $drawerOpen={!!selectedNode}>
                <ZoomButton
                  onClick={() => zoomBy(EXP.ZOOM_STEP)}
                  aria-label="Zoom in"
                  data-testid={`${testId}-zoom-in`}
                >
                  <Plus />
                </ZoomButton>
                <ZoomButton
                  onClick={() => zoomBy(1 / EXP.ZOOM_STEP)}
                  aria-label="Zoom out"
                  data-testid={`${testId}-zoom-out`}
                >
                  <Minus />
                </ZoomButton>
                <ZoomButton
                  onClick={resetView}
                  aria-label="Fit to view"
                  data-testid={`${testId}-zoom-reset`}
                >
                  <Maximize2 />
                </ZoomButton>
              </ZoomCluster>
            )}

            {selectedNode && (
              <NodeDetailDrawer
                node={selectedNode}
                edges={edges}
                nodeById={nodeById}
                nodeFill={nodeFill}
                onClose={() => setSelectedId(null)}
                onSelectNeighbor={handleSelect}
                onOpenDocument={handleOpenDocument}
                testId={testId}
              />
            )}
          </CanvasWrap>
        </ExplorerBody>
      </DetailsPage>
    </DetailsContainer>
  );
};

interface NodeDetailDrawerProps {
  node: GovSimNode;
  edges: GovernanceGraphEdge[];
  nodeById: Map<string, GovSimNode>;
  nodeFill: (n: GovSimNode) => string;
  onClose: () => void;
  onSelectNeighbor: (id: string) => void;
  onOpenDocument: (documentId: string) => void;
  testId: string;
}

/** The right-hand inspector for the selected node: what it is, where it sits in
 * the law, its crawl status (for ghosts), and the things it cites or is cited
 * by — each a jump deeper into the graph. */
const NodeDetailDrawer: React.FC<NodeDetailDrawerProps> = ({
  node,
  edges,
  nodeById,
  nodeFill,
  onClose,
  onSelectNeighbor,
  onOpenDocument,
  testId,
}) => {
  const isExternal = node.kind === KINDS.EXTERNAL;
  const fill = nodeFill(node);
  const jurisdiction = formatJurisdiction(node.jurisdiction);
  const discovery = node.discoveryState
    ? DISCOVERY_STATE_LABEL[node.discoveryState] ??
      titleCase(node.discoveryState)
    : null;

  // Neighbours, summed by weight and ranked — the node's place in the web.
  const neighbors = useMemo(() => {
    const acc = new Map<string, number>();
    for (const e of edges) {
      if (e.source === node.id)
        acc.set(e.target, (acc.get(e.target) ?? 0) + e.weight);
      else if (e.target === node.id)
        acc.set(e.source, (acc.get(e.source) ?? 0) + e.weight);
    }
    return [...acc.entries()]
      .map(([id, weight]) => ({ peer: nodeById.get(id), weight }))
      .filter((x): x is { peer: GovSimNode; weight: number } => !!x.peer)
      .sort((a, b) => b.weight - a.weight);
  }, [edges, node.id, nodeById]);

  return (
    <Drawer
      data-testid={`${testId}-detail`}
      role="dialog"
      aria-label="Node details"
    >
      <DrawerHead>
        <KindBadge $fill={fill} $ghost={isExternal}>
          <span className="swatch" />
          {KIND_LABEL[node.kind] ?? node.kind}
        </KindBadge>
        <DrawerClose
          onClick={onClose}
          aria-label="Close details"
          data-testid={`${testId}-detail-close`}
        >
          <X />
        </DrawerClose>
      </DrawerHead>

      <DrawerTitle data-testid={`${testId}-detail-title`}>
        {isExternal ? ghostLabel(node) : node.title || "Untitled document"}
      </DrawerTitle>

      <FactList>
        {node.authority && (
          <>
            <dt>Body of law</dt>
            <dd>{authorityCaption(node.authority)}</dd>
          </>
        )}
        {jurisdiction && (
          <>
            <dt>Jurisdiction</dt>
            <dd>{jurisdiction}</dd>
          </>
        )}
        {node.authorityType && (
          <>
            <dt>Type</dt>
            <dd>{titleCase(node.authorityType)}</dd>
          </>
        )}
        <dt>References</dt>
        <dd>{node.degree}</dd>
      </FactList>

      {discovery && (
        <StatusChip data-testid={`${testId}-detail-status`}>
          {discovery}
        </StatusChip>
      )}

      {node.documentId && (
        <OpenDocButton
          onClick={() => onOpenDocument(node.documentId as string)}
          data-testid={`${testId}-detail-open`}
        >
          <ExternalLink />
          Open document
        </OpenDocButton>
      )}

      {neighbors.length > 0 && (
        <RailGroup>
          <RailLabel>
            {isExternal ? "Cited by" : "Connections"} ({neighbors.length})
          </RailLabel>
          <NeighborList>
            {neighbors
              .slice(0, EXP.NEIGHBOR_LIST_CAP)
              .map(({ peer, weight }) => (
                <NeighborRow
                  key={peer.id}
                  onClick={() => onSelectNeighbor(peer.id)}
                  data-testid={`${testId}-detail-neighbor`}
                >
                  <span
                    className="ndot"
                    style={{
                      background:
                        peer.kind === KINDS.EXTERNAL
                          ? "transparent"
                          : nodeFill(peer),
                      border:
                        peer.kind === KINDS.EXTERNAL
                          ? `1.5px dashed ${COLORS.EXTERNAL}`
                          : "none",
                    }}
                  />
                  <span className="nlabel">{nodeLabel(peer)}</span>
                  <span className="nweight">{weight}</span>
                </NeighborRow>
              ))}
          </NeighborList>
        </RailGroup>
      )}
    </Drawer>
  );
};

export default GovernanceGraphExplorer;
