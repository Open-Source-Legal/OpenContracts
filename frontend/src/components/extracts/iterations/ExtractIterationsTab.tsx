/**
 * ExtractIterationsTab
 *
 * Lists every extract in the current iteration series and lets the user
 * fork a new iteration along any of the three eval axes. When two
 * iterations are selected, the panel switches to {@link ExtractCompareView}
 * showing the cell-level diff.
 */

import React, { useMemo, useState } from "react";
import styled from "styled-components";
import { useMutation } from "@apollo/client";
import { toast } from "react-toastify";
import { Button, Chip } from "@os-legal/ui";
import { GitFork, Cpu, FileStack, Sliders, ArrowLeftRight } from "lucide-react";
import { OS_LEGAL_COLORS } from "../../../assets/configurations/osLegalStyles";
import { ExtractType } from "../../../types/graphql-api";
import {
  REQUEST_CREATE_EXTRACT_ITERATION,
  RequestCreateExtractIterationInputType,
  RequestCreateExtractIterationOutputType,
  ExtractIterationAxis,
} from "../../../graphql/mutations";
import { REQUEST_GET_EXTRACT } from "../../../graphql/queries";
import { NewIterationDialog } from "./NewIterationDialog";
import { ExtractCompareView } from "./ExtractCompareView";
import { formatExtractDate } from "../../../utils/extractUtils";

const Wrapper = styled.div`
  display: flex;
  flex-direction: column;
  gap: 16px;
`;

const Toolbar = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
`;

const ToolbarTitle = styled.span`
  font-size: 14px;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textSecondary};
  text-transform: uppercase;
  letter-spacing: 0.05em;
`;

const List = styled.div`
  display: flex;
  flex-direction: column;
  gap: 8px;
`;

const Row = styled.div<{ $selected: boolean }>`
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  background: white;
  border: 1px solid
    ${({ $selected }) =>
      $selected ? OS_LEGAL_COLORS.primaryBlue : OS_LEGAL_COLORS.border};
  border-radius: 10px;
  transition: border-color 0.15s, box-shadow 0.15s;
  cursor: pointer;

  &:hover {
    border-color: ${OS_LEGAL_COLORS.primaryBlue};
  }
`;

const Bullet = styled.span<{ $color: string }>`
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: ${({ $color }) => $color};
  flex-shrink: 0;
`;

const RowMain = styled.div`
  flex: 1;
  min-width: 0;
`;

const RowName = styled.div`
  font-size: 13px;
  font-weight: 600;
  color: ${OS_LEGAL_COLORS.textPrimary};
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
`;

const RowMeta = styled.div`
  font-size: 12px;
  color: ${OS_LEGAL_COLORS.textMuted};
  display: flex;
  gap: 8px;
  align-items: center;
  margin-top: 2px;
`;

const SelectionHint = styled.div`
  font-size: 12px;
  color: ${OS_LEGAL_COLORS.textMuted};
`;

// Visual axis -> color so users can scan iterations by what they tested.
const AXIS_BADGE: Record<
  ExtractIterationAxis,
  { color: string; Icon: typeof Cpu; label: string }
> = {
  MODEL: { color: "#3b82f6", Icon: Cpu, label: "Model" },
  DOCUMENT_VERSIONS: {
    color: "#10b981",
    Icon: FileStack,
    label: "Doc versions",
  },
  FIELDSET: { color: "#7c3aed", Icon: Sliders, label: "Schema" },
};

const statusColor = (e: ExtractType): string => {
  if (e.error) return OS_LEGAL_COLORS.dangerBorderHover;
  if (e.finished) return OS_LEGAL_COLORS.greenMedium;
  if (e.started) return OS_LEGAL_COLORS.folderIcon;
  return OS_LEGAL_COLORS.border;
};

export interface ExtractIterationsTabProps {
  extract: ExtractType;
  /** Refetch the current extract after a new iteration is created. */
  onIterationCreated?: () => void;
}

export const ExtractIterationsTab: React.FC<ExtractIterationsTabProps> = ({
  extract,
  onIterationCreated,
}) => {
  const [dialogOpen, setDialogOpen] = useState(false);
  const [selected, setSelected] = useState<string[]>([]); // ids picked for compare

  // Build the linear series: parent -> root, then root.iterations + this.
  // We render a flat list (parent above current above iterations) which is
  // the simplest mental model for "show me each run side by side".
  const series: ExtractType[] = useMemo(() => {
    const seen = new Set<string>();
    const out: ExtractType[] = [];
    const push = (e: ExtractType | null | undefined) => {
      if (!e || seen.has(e.id)) return;
      seen.add(e.id);
      out.push(e);
    };
    push(extract.parentExtract ?? undefined);
    push(extract);
    (extract.fullIterationList ?? []).forEach(push);
    return out;
  }, [extract]);

  const [createIteration, { loading: creating }] = useMutation<
    RequestCreateExtractIterationOutputType,
    RequestCreateExtractIterationInputType
  >(REQUEST_CREATE_EXTRACT_ITERATION, {
    refetchQueries: [
      { query: REQUEST_GET_EXTRACT, variables: { id: extract.id } },
    ],
    awaitRefetchQueries: true,
    onCompleted: (data) => {
      if (data.createExtractIteration.ok) {
        toast.success("Iteration queued.");
        setDialogOpen(false);
        onIterationCreated?.();
      } else {
        toast.error(
          data.createExtractIteration.message || "Could not create iteration."
        );
      }
    },
    onError: () => toast.error("Could not create iteration."),
  });

  const handleSubmit = (input: {
    axis: ExtractIterationAxis;
    name?: string;
    modelConfig?: Record<string, unknown>;
    autoStart: boolean;
  }) => {
    createIteration({
      variables: {
        sourceExtractId: extract.id,
        axis: input.axis,
        name: input.name,
        modelConfig: input.modelConfig,
        autoStart: input.autoStart,
      },
    });
  };

  const toggleSelect = (id: string) => {
    setSelected((prev) => {
      if (prev.includes(id)) return prev.filter((p) => p !== id);
      // Cap at 2 — older selection pops off so the most recent two clicks win.
      const next = [...prev, id];
      return next.slice(-2);
    });
  };

  const compareReady = selected.length === 2;

  return (
    <Wrapper>
      <Toolbar>
        <ToolbarTitle>Iterations ({series.length})</ToolbarTitle>
        <div style={{ display: "flex", gap: 8 }}>
          {compareReady && (
            <Chip variant="soft" color="info" size="sm">
              <ArrowLeftRight size={12} /> Comparing 2 iterations
            </Chip>
          )}
          <Button
            variant="primary"
            size="sm"
            leftIcon={<GitFork size={12} />}
            onClick={() => setDialogOpen(true)}
          >
            New iteration
          </Button>
        </div>
      </Toolbar>

      {!compareReady && (
        <SelectionHint>
          Pick two iterations to view a cell-level diff and heatmap.
        </SelectionHint>
      )}

      <List>
        {series.map((it) => {
          const axisKey = (it.iterationAxis ??
            null) as ExtractIterationAxis | null;
          const axisInfo = axisKey ? AXIS_BADGE[axisKey] : null;
          const isSelected = selected.includes(it.id);
          return (
            <Row
              key={it.id}
              $selected={isSelected}
              onClick={() => toggleSelect(it.id)}
              data-testid="iteration-row"
              data-iteration-id={it.id}
            >
              <Bullet $color={statusColor(it)} />
              <RowMain>
                <RowName>
                  {it.name}
                  {it.id === extract.id && (
                    <span
                      style={{
                        marginLeft: 8,
                        fontSize: 11,
                        color: OS_LEGAL_COLORS.textMuted,
                        fontWeight: 500,
                      }}
                    >
                      (current)
                    </span>
                  )}
                </RowName>
                <RowMeta>
                  {axisInfo && (
                    <Chip variant="outlined" size="sm">
                      <axisInfo.Icon size={11} /> {axisInfo.label}
                    </Chip>
                  )}
                  {it.modelConfig?.model && (
                    <Chip variant="outlined" size="sm">
                      {it.modelConfig.model}
                    </Chip>
                  )}
                  <span>{formatExtractDate(it.started ?? it.created)}</span>
                </RowMeta>
              </RowMain>
              {isSelected && (
                <Chip variant="soft" color="info" size="sm">
                  {selected.indexOf(it.id) === 0 ? "A" : "B"}
                </Chip>
              )}
            </Row>
          );
        })}
      </List>

      {compareReady && (
        <ExtractCompareView extractAId={selected[0]} extractBId={selected[1]} />
      )}

      <NewIterationDialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        onSubmit={handleSubmit}
        parentModel={(extract.modelConfig?.model as string | undefined) ?? null}
        loading={creating}
      />
    </Wrapper>
  );
};
