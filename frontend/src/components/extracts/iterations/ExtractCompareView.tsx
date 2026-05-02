/**
 * ExtractCompareView
 *
 * Renders the cell-level diff between two iterations of the same extract
 * series as a heatmap-style grid: rows are logical documents (aligned
 * across iterations by `version_tree_id`), columns are the union of column
 * names. Each cell is colored by its DiffStatus and clickable to open a
 * side panel with the full A/B values.
 *
 * Reuses the canonical `formatCellValue` formatter so the rendering of
 * datacell values stays identical to the main extract grid.
 */

import React, { useMemo, useState } from "react";
import styled from "styled-components";
import { useQuery } from "@apollo/client";
import { Tooltip } from "@os-legal/ui";
import { X } from "lucide-react";
import { OS_LEGAL_COLORS } from "../../../assets/configurations/osLegalStyles";
import { formatCellValue } from "../../../utils/formatters";
import {
  COMPARE_EXTRACTS,
  CompareExtractsInput,
  CompareExtractsOutput,
  ExtractCellDiff,
  ExtractDiffStatus,
} from "../../../graphql/queries";

// Centralised diff palette — referenced by both the cell overlay and the
// summary chips so the legend always matches the grid.
const DIFF_PALETTE: Record<
  ExtractDiffStatus,
  { bg: string; border: string; label: string }
> = {
  UNCHANGED: {
    bg: "transparent",
    border: OS_LEGAL_COLORS.border,
    label: "Unchanged",
  },
  CHANGED: {
    bg: "rgba(245, 158, 11, 0.18)",
    border: OS_LEGAL_COLORS.folderIcon,
    label: "Changed",
  },
  ONLY_IN_A: {
    bg: "rgba(239, 68, 68, 0.14)",
    border: OS_LEGAL_COLORS.dangerBorderHover,
    label: "Only in A",
  },
  ONLY_IN_B: {
    bg: "rgba(16, 185, 129, 0.14)",
    border: OS_LEGAL_COLORS.greenMedium,
    label: "Only in B",
  },
};

const Wrapper = styled.div`
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 0;
`;

const SummaryRow = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
`;

const SummaryChip = styled.div<{ $bg: string; $border: string }>`
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid ${({ $border }) => $border};
  background: ${({ $bg }) => $bg};
  font-size: 0.75rem;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textPrimary};
`;

const Dot = styled.span<{ $color: string }>`
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: ${({ $color }) => $color};
`;

const GridScroll = styled.div`
  overflow: auto;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 12px;
  background: white;
`;

const Grid = styled.table`
  border-collapse: separate;
  border-spacing: 0;
  width: 100%;
  font-size: 0.875rem;
  color: ${OS_LEGAL_COLORS.textPrimary};
`;

const HeaderCell = styled.th`
  position: sticky;
  top: 0;
  background: ${OS_LEGAL_COLORS.surfaceHover};
  border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
  padding: 10px 12px;
  text-align: left;
  font-weight: 700;
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: ${OS_LEGAL_COLORS.textPrimary};
  z-index: 1;
`;

const RowHeaderCell = styled.td`
  position: sticky;
  left: 0;
  background: white;
  border-right: 1px solid ${OS_LEGAL_COLORS.border};
  border-bottom: 1px solid ${OS_LEGAL_COLORS.surfaceLight};
  padding: 10px 12px;
  font-weight: 500;
  white-space: nowrap;
  max-width: 240px;
  overflow: hidden;
  text-overflow: ellipsis;
`;

const Cell = styled.td<{ $bg: string; $border: string; $clickable: boolean }>`
  background: ${({ $bg }) => $bg};
  border-bottom: 1px solid ${OS_LEGAL_COLORS.surfaceLight};
  border-left: 3px solid ${({ $border }) => $border};
  padding: 8px 10px;
  vertical-align: top;
  cursor: ${({ $clickable }) => ($clickable ? "pointer" : "default")};
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 0.8125rem;
  color: ${OS_LEGAL_COLORS.textPrimary};
  max-width: 320px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
`;

const SidePanel = styled.aside`
  position: fixed;
  top: 0;
  right: 0;
  width: 420px;
  max-width: 100vw;
  height: 100vh;
  background: white;
  border-left: 1px solid ${OS_LEGAL_COLORS.border};
  box-shadow: -8px 0 24px rgba(15, 23, 42, 0.08);
  display: flex;
  flex-direction: column;
  z-index: 900;
`;

const PanelHeader = styled.div`
  padding: 16px 20px;
  border-bottom: 1px solid ${OS_LEGAL_COLORS.border};
  display: flex;
  justify-content: space-between;
  align-items: center;
`;

const PanelBody = styled.div`
  padding: 16px 20px;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
`;

const SideLabel = styled.div`
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textMuted};
  margin-bottom: 4px;
`;

const Pre = styled.pre`
  background: ${OS_LEGAL_COLORS.gray50};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 8px;
  padding: 10px 12px;
  font-size: 0.8125rem;
  color: ${OS_LEGAL_COLORS.textPrimary};
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
`;

const ConfigBadge = styled.span`
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 2px 8px;
  background: rgba(124, 58, 237, 0.1);
  color: #6d28d9;
  border-radius: 999px;
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
`;

const cellEffectiveValue = (
  cell: ExtractCellDiff["cellA"] | ExtractCellDiff["cellB"]
): unknown => {
  if (!cell) return null;
  return cell.correctedData ?? cell.data;
};

const buildRowsAndColumns = (cells: ExtractCellDiff[]) => {
  // Stable ordering: rows by first appearance, columns alphabetical so two
  // diffs of the same series produce identical layouts (helpful for visual
  // recall when sweeping through several iterations).
  const rowOrder: string[] = [];
  const seenRows = new Set<string>();
  const rowLabel: Record<string, string> = {};
  const columnSet = new Set<string>();

  for (const c of cells) {
    if (!seenRows.has(c.rowKey)) {
      seenRows.add(c.rowKey);
      rowOrder.push(c.rowKey);
      rowLabel[c.rowKey] =
        c.document?.title ||
        c.documentB?.title ||
        c.documentA?.title ||
        c.rowKey;
    }
    columnSet.add(c.columnKey);
  }

  const columns = Array.from(columnSet).sort();
  return { rowOrder, rowLabel, columns };
};

export interface ExtractCompareViewProps {
  extractAId: string;
  extractBId: string;
}

export const ExtractCompareView: React.FC<ExtractCompareViewProps> = ({
  extractAId,
  extractBId,
}) => {
  const { data, loading, error } = useQuery<
    CompareExtractsOutput,
    CompareExtractsInput
  >(COMPARE_EXTRACTS, {
    variables: { extractAId, extractBId },
    fetchPolicy: "cache-and-network",
  });

  const [selected, setSelected] = useState<ExtractCellDiff | null>(null);

  const diff = data?.compareExtracts ?? null;

  const cellLookup = useMemo(() => {
    const map = new Map<string, ExtractCellDiff>();
    if (!diff) return map;
    for (const c of diff.cells) {
      map.set(`${c.rowKey}::${c.columnKey}`, c);
    }
    return map;
  }, [diff]);

  const layout = useMemo(
    () => (diff ? buildRowsAndColumns(diff.cells) : null),
    [diff]
  );

  if (loading && !diff) {
    return <div style={{ padding: 24 }}>Loading diff…</div>;
  }
  if (error) {
    return (
      <div style={{ padding: 24, color: OS_LEGAL_COLORS.dangerBorderHover }}>
        Could not load diff: {error.message}
      </div>
    );
  }
  if (!diff || !layout) {
    return null;
  }

  const summary = diff.summary;

  return (
    <Wrapper>
      <SummaryRow>
        {(
          [
            { key: "CHANGED", count: summary.changed },
            { key: "ONLY_IN_A", count: summary.onlyInA },
            { key: "ONLY_IN_B", count: summary.onlyInB },
            { key: "UNCHANGED", count: summary.unchanged },
          ] as Array<{ key: ExtractDiffStatus; count: number }>
        ).map(({ key, count }) => {
          const palette = DIFF_PALETTE[key];
          return (
            <SummaryChip key={key} $bg={palette.bg} $border={palette.border}>
              <Dot $color={palette.border} />
              {palette.label}: {count}
            </SummaryChip>
          );
        })}
        <span
          style={{
            marginLeft: "auto",
            fontSize: "0.75rem",
            color: OS_LEGAL_COLORS.textMuted,
          }}
        >
          {summary.total} cell{summary.total === 1 ? "" : "s"} compared
        </span>
      </SummaryRow>

      <GridScroll>
        <Grid>
          <thead>
            <tr>
              <HeaderCell style={{ left: 0, position: "sticky", zIndex: 2 }}>
                Document
              </HeaderCell>
              {layout.columns.map((col) => (
                <HeaderCell key={col}>{col}</HeaderCell>
              ))}
            </tr>
          </thead>
          <tbody>
            {layout.rowOrder.map((rowKey) => (
              <tr key={rowKey}>
                <RowHeaderCell>
                  <Tooltip content={layout.rowLabel[rowKey]}>
                    <span>{layout.rowLabel[rowKey]}</span>
                  </Tooltip>
                </RowHeaderCell>
                {layout.columns.map((col) => {
                  const c = cellLookup.get(`${rowKey}::${col}`);
                  if (!c) {
                    return (
                      <Cell
                        key={col}
                        $bg="transparent"
                        $border={OS_LEGAL_COLORS.border}
                        $clickable={false}
                      >
                        —
                      </Cell>
                    );
                  }
                  const palette = DIFF_PALETTE[c.status];
                  const display = formatCellValue(
                    cellEffectiveValue(c.cellB) as any
                  );
                  return (
                    <Cell
                      key={col}
                      $bg={palette.bg}
                      $border={palette.border}
                      $clickable={c.status !== "UNCHANGED"}
                      onClick={() =>
                        c.status === "UNCHANGED" ? null : setSelected(c)
                      }
                      title={
                        c.status === "UNCHANGED"
                          ? undefined
                          : `${palette.label} — click for details`
                      }
                    >
                      {display}
                    </Cell>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </Grid>
      </GridScroll>

      {selected && (
        <SidePanel role="dialog" aria-label="Cell diff details">
          <PanelHeader>
            <div>
              <SideLabel>{selected.columnKey}</SideLabel>
              <div style={{ fontSize: "0.875rem", fontWeight: 600 }}>
                {selected.document?.title || selected.rowKey}
              </div>
            </div>
            <button
              onClick={() => setSelected(null)}
              aria-label="Close"
              style={{
                background: "transparent",
                border: "none",
                cursor: "pointer",
                color: OS_LEGAL_COLORS.textMuted,
              }}
            >
              <X size={18} />
            </button>
          </PanelHeader>
          <PanelBody>
            {selected.columnConfigChanged && (
              <ConfigBadge>Schema changed for this column</ConfigBadge>
            )}
            <div>
              <SideLabel>Iteration A — {diff.extractA.name}</SideLabel>
              <Pre>
                {JSON.stringify(cellEffectiveValue(selected.cellA), null, 2)}
              </Pre>
              {selected.documentA?.title && (
                <div
                  style={{
                    fontSize: "0.75rem",
                    color: OS_LEGAL_COLORS.textMuted,
                    marginTop: 4,
                  }}
                >
                  Doc: {selected.documentA.title}
                </div>
              )}
            </div>
            <div>
              <SideLabel>Iteration B — {diff.extractB.name}</SideLabel>
              <Pre>
                {JSON.stringify(cellEffectiveValue(selected.cellB), null, 2)}
              </Pre>
              {selected.documentB?.title &&
                selected.documentB.id !== selected.documentA?.id && (
                  <div
                    style={{
                      fontSize: "0.75rem",
                      color: OS_LEGAL_COLORS.textMuted,
                      marginTop: 4,
                    }}
                  >
                    Doc: {selected.documentB.title}
                  </div>
                )}
            </div>
          </PanelBody>
        </SidePanel>
      )}
    </Wrapper>
  );
};
