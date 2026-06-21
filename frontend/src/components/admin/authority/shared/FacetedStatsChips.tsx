/**
 * Faceted stats chips — the tone-coloured "All / <facet> (count)" chip row used
 * across the Authority Console (registry facets, discovery-state facets, source
 * facets). Extracted from the duplicated chip blocks in AuthorityMappings and
 * AuthoritySourcesMonitor so the one chip behaviour (toggle-off on re-click,
 * tabular-nums counts, active inset ring) has a single definition.
 */
import React from "react";
import styled from "styled-components";

import { OS_LEGAL_COLORS } from "../../../../assets/configurations/osLegalStyles";
import { CORPUS_RADII } from "../../../corpuses/styles/corpusDesignTokens";
import { TONE_COLORS, Tone } from "./tones";

export interface ChipDatum {
  value: string;
  count: number;
}

interface FacetedStatsChipsProps {
  chips: ChipDatum[];
  activeValue: string | null;
  onSelect: (value: string | null) => void;
  getTone: (value: string) => Tone;
  getLabel: (value: string) => string;
  totalCount?: number;
  testIdPrefix?: string;
  /** Hide chips with an empty-string value (e.g. null jurisdiction). */
  hideEmptyValues?: boolean;
}

const Chips = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-bottom: 1rem;
`;

const Chip = styled.button<{ $active: boolean; $tone: Tone }>`
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  padding: 0.34rem 0.7rem;
  border-radius: ${CORPUS_RADII.full};
  font-size: 0.78125rem;
  font-weight: 600;
  cursor: pointer;
  transition: filter 0.12s ease, box-shadow 0.12s ease;
  color: ${(p) => TONE_COLORS[p.$tone].fg};
  background: ${(p) => TONE_COLORS[p.$tone].bg};
  border: 1px solid
    ${(p) =>
      p.$active ? TONE_COLORS[p.$tone].fg : TONE_COLORS[p.$tone].border};
  box-shadow: ${(p) =>
    p.$active ? `inset 0 0 0 1px ${TONE_COLORS[p.$tone].fg}` : "none"};

  &:hover {
    filter: brightness(0.97);
  }

  .count {
    font-variant-numeric: tabular-nums;
    opacity: 0.85;
  }
`;

const AllChip = styled(Chip)`
  color: ${OS_LEGAL_COLORS.textSecondary};
  background: ${OS_LEGAL_COLORS.surfaceLight};
  border-color: ${(p) =>
    p.$active ? OS_LEGAL_COLORS.textSecondary : OS_LEGAL_COLORS.border};
  box-shadow: ${(p) =>
    p.$active ? `inset 0 0 0 1px ${OS_LEGAL_COLORS.textSecondary}` : "none"};
`;

export const FacetedStatsChips: React.FC<FacetedStatsChipsProps> = ({
  chips,
  activeValue,
  onSelect,
  getTone,
  getLabel,
  totalCount,
  testIdPrefix = "facet",
  hideEmptyValues = true,
}) => {
  const visible = hideEmptyValues ? chips.filter((c) => c.value !== "") : chips;
  return (
    <Chips data-testid={`${testIdPrefix}-chips`}>
      <AllChip
        type="button"
        $active={activeValue === null}
        $tone="neutral"
        onClick={() => onSelect(null)}
        data-testid={`${testIdPrefix}-chip-all`}
      >
        All
        {totalCount !== undefined ? (
          <span className="count">{totalCount}</span>
        ) : null}
      </AllChip>
      {visible.map(({ value, count }) => (
        <Chip
          key={value}
          type="button"
          $active={activeValue === value}
          $tone={getTone(value)}
          onClick={() => onSelect(activeValue === value ? null : value)}
          data-testid={`${testIdPrefix}-chip-${value}`}
        >
          {getLabel(value)}
          <span className="count">{count}</span>
        </Chip>
      ))}
    </Chips>
  );
};
