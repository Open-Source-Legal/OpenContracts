import React, { useState } from "react";
import { useMutation } from "@apollo/client";
import styled from "styled-components";
import { ChevronRight } from "lucide-react";
import { toast } from "react-toastify";

import {
  RUN_CORPUS_ENRICHMENT,
  RunCorpusEnrichmentInputs,
  RunCorpusEnrichmentOutputs,
  EnrichmentAnalysisRow,
} from "../../../graphql/mutations";
import { OS_LEGAL_COLORS } from "../../../assets/configurations/osLegalStyles";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface EnrichmentRunnerProps {
  corpusId: string;
  /** Called with the optimistic analysis rows returned by the mutation. */
  onRan?: (rows: EnrichmentAnalysisRow[]) => void;
  /** Disable the Run button while a job is already in-flight. */
  runningJobExists?: boolean;
  /** Collapse the Advanced section by default (per-corpus card mode). */
  compact?: boolean;
}

// ---------------------------------------------------------------------------
// Styled components
// ---------------------------------------------------------------------------

const Container = styled.div`
  display: flex;
  flex-direction: column;
  gap: 1rem;
`;

const FieldGroup = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.625rem;
`;

const GroupLabel = styled.p`
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: ${OS_LEGAL_COLORS.textMuted};
  margin: 0 0 0.25rem 0;
`;

const CheckboxRow = styled.label<{ $disabled?: boolean }>`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.875rem;
  color: ${({ $disabled }) =>
    $disabled ? OS_LEGAL_COLORS.textMuted : OS_LEGAL_COLORS.textPrimary};
  cursor: ${({ $disabled }) => ($disabled ? "not-allowed" : "pointer")};
  user-select: none;
`;

const StyledCheckbox = styled.input`
  width: 1rem;
  height: 1rem;
  accent-color: ${OS_LEGAL_COLORS.accent};
  cursor: inherit;
  flex-shrink: 0;
`;

const ToggleRow = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
`;

const ToggleLabel = styled.label`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.875rem;
  color: ${OS_LEGAL_COLORS.textPrimary};
  cursor: pointer;
  user-select: none;
`;

const Caption = styled.span`
  font-size: 0.75rem;
  color: ${OS_LEGAL_COLORS.textSecondary};
  margin-left: 1.5rem;
`;

const AdvancedToggle = styled.button<{ $expanded: boolean }>`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  width: 100%;
  padding: 0.625rem 0.75rem;
  background: ${OS_LEGAL_COLORS.surfaceHover};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 8px;
  font-size: 0.8125rem;
  font-weight: 500;
  color: ${OS_LEGAL_COLORS.textSecondary};
  cursor: pointer;
  transition: all 0.15s ease;
  text-align: left;

  &:hover {
    background: ${OS_LEGAL_COLORS.surfaceLight};
    color: ${OS_LEGAL_COLORS.textPrimary};
  }

  svg {
    width: 14px;
    height: 14px;
    flex-shrink: 0;
    transition: transform 0.2s ease;
    transform: rotate(${({ $expanded }) => ($expanded ? "90deg" : "0deg")});
  }
`;

const AdvancedContent = styled.div<{ $expanded: boolean }>`
  display: ${({ $expanded }) => ($expanded ? "flex" : "none")};
  flex-direction: column;
  gap: 0.75rem;
  padding: 0.875rem;
  background: ${OS_LEGAL_COLORS.surface};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 8px;
`;

const BoundRow = styled.div`
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
`;

const BoundLabel = styled.label`
  font-size: 0.8125rem;
  font-weight: 500;
  color: ${OS_LEGAL_COLORS.textPrimary};
`;

const NumberInput = styled.input`
  width: 100%;
  padding: 0.4375rem 0.75rem;
  font-size: 0.8125rem;
  color: ${OS_LEGAL_COLORS.textPrimary};
  background: white;
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 6px;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
  box-sizing: border-box;

  &::placeholder {
    color: ${OS_LEGAL_COLORS.textMuted};
  }

  &:hover {
    border-color: ${OS_LEGAL_COLORS.borderHover};
  }

  &:focus {
    outline: none;
    border-color: ${OS_LEGAL_COLORS.accent};
    box-shadow: 0 0 0 2px ${OS_LEGAL_COLORS.accentMedium};
  }
`;

const RunButton = styled.button<{ $disabled: boolean }>`
  align-self: flex-start;
  padding: 0.5rem 1.25rem;
  font-size: 0.875rem;
  font-weight: 600;
  color: white;
  background: ${({ $disabled }) =>
    $disabled ? OS_LEGAL_COLORS.textMuted : OS_LEGAL_COLORS.accent};
  border: none;
  border-radius: 8px;
  cursor: ${({ $disabled }) => ($disabled ? "not-allowed" : "pointer")};
  transition: background 0.15s ease;

  &:hover:not(:disabled) {
    background: ${OS_LEGAL_COLORS.accentHover};
  }
`;

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const REFERENCE_TYPE_OPTIONS = [
  { value: "LAW", label: "LAW", alwaysOn: true },
  { value: "DOCUMENT", label: "DOCUMENT", alwaysOn: false },
  { value: "SECTION", label: "SECTION", alwaysOn: false },
] as const;

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export const EnrichmentRunner: React.FC<EnrichmentRunnerProps> = ({
  corpusId,
  onRan,
  runningJobExists = false,
  compact = false,
}) => {
  // Job checkboxes
  const [runEnrichment, setRunEnrichment] = useState(true);
  const [runCrawl, setRunCrawl] = useState(false);

  // Reference types (LAW always on)
  const [refTypeDocument, setRefTypeDocument] = useState(false);
  const [refTypeSection, setRefTypeSection] = useState(false);

  // LLM tier toggle
  const [useLlmTier, setUseLlmTier] = useState(false);

  // Advanced crawl bounds (empty string = use server default)
  const [advancedOpen, setAdvancedOpen] = useState(!compact);
  const [maxDepth, setMaxDepth] = useState("");
  const [minDemand, setMinDemand] = useState("");
  const [maxAuthorities, setMaxAuthorities] = useState("");
  const [perJurisdictionCap, setPerJurisdictionCap] = useState("");
  const [tokenBudget, setTokenBudget] = useState("");

  const [run, { loading }] = useMutation<
    RunCorpusEnrichmentOutputs,
    RunCorpusEnrichmentInputs
  >(RUN_CORPUS_ENRICHMENT);

  const neitherSelected = !runEnrichment && !runCrawl;
  const isDisabled = runningJobExists || loading || neitherSelected;

  const handleRun = async () => {
    if (isDisabled) return;

    // Build referenceTypes: LAW is always included
    const referenceTypes = ["LAW"];
    if (refTypeDocument) referenceTypes.push("DOCUMENT");
    if (refTypeSection) referenceTypes.push("SECTION");

    // Build options — only include a bound if the user typed a value
    const parsedMaxDepth = maxDepth !== "" ? Number(maxDepth) : undefined;
    const parsedMinDemand = minDemand !== "" ? Number(minDemand) : undefined;
    const parsedMaxAuthorities =
      maxAuthorities !== "" ? Number(maxAuthorities) : undefined;
    const parsedPerJurisdictionCap =
      perJurisdictionCap !== "" ? Number(perJurisdictionCap) : undefined;
    const parsedTokenBudget =
      tokenBudget !== "" ? Number(tokenBudget) : undefined;

    const hasOptions =
      referenceTypes.length > 1 ||
      useLlmTier ||
      parsedMaxDepth !== undefined ||
      parsedMinDemand !== undefined ||
      parsedMaxAuthorities !== undefined ||
      parsedPerJurisdictionCap !== undefined ||
      parsedTokenBudget !== undefined;

    const variables: RunCorpusEnrichmentInputs = {
      corpusId,
      runEnrichment,
      runCrawl,
      ...(hasOptions
        ? {
            options: {
              referenceTypes,
              ...(useLlmTier ? { useLlmTier } : {}),
              ...(parsedMaxDepth !== undefined
                ? { maxDepth: parsedMaxDepth }
                : {}),
              ...(parsedMinDemand !== undefined
                ? { minDemand: parsedMinDemand }
                : {}),
              ...(parsedMaxAuthorities !== undefined
                ? { maxAuthorities: parsedMaxAuthorities }
                : {}),
              ...(parsedPerJurisdictionCap !== undefined
                ? { perJurisdictionCap: parsedPerJurisdictionCap }
                : {}),
              ...(parsedTokenBudget !== undefined
                ? { tokenBudget: parsedTokenBudget }
                : {}),
            },
          }
        : {}),
    };

    try {
      const { data } = await run({ variables });
      if (data?.runCorpusEnrichment.ok) {
        toast.success("Enrichment started");
        onRan?.(data.runCorpusEnrichment.analyses);
      } else {
        toast.error(data?.runCorpusEnrichment.message ?? "Enrichment failed");
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Enrichment failed";
      toast.error(message);
    }
  };

  return (
    <Container data-testid="enrichment-runner">
      {/* Job selection */}
      <FieldGroup>
        <GroupLabel>Jobs to run</GroupLabel>
        <CheckboxRow>
          <StyledCheckbox
            type="checkbox"
            checked={runEnrichment}
            onChange={(e) => setRunEnrichment(e.target.checked)}
          />
          Run reference enrichment
        </CheckboxRow>
        <CheckboxRow>
          <StyledCheckbox
            type="checkbox"
            checked={runCrawl}
            onChange={(e) => setRunCrawl(e.target.checked)}
          />
          Run authority crawl
        </CheckboxRow>
      </FieldGroup>

      {/* Reference types */}
      <FieldGroup>
        <GroupLabel>Reference types</GroupLabel>
        {REFERENCE_TYPE_OPTIONS.map(({ value, label, alwaysOn }) => (
          <CheckboxRow key={value} $disabled={alwaysOn}>
            <StyledCheckbox
              type="checkbox"
              checked={
                alwaysOn
                  ? true
                  : value === "DOCUMENT"
                  ? refTypeDocument
                  : refTypeSection
              }
              disabled={alwaysOn}
              onChange={
                alwaysOn
                  ? undefined
                  : value === "DOCUMENT"
                  ? (e) => setRefTypeDocument(e.target.checked)
                  : (e) => setRefTypeSection(e.target.checked)
              }
            />
            {label}
          </CheckboxRow>
        ))}
      </FieldGroup>

      {/* LLM tier toggle */}
      <ToggleRow>
        <ToggleLabel>
          <StyledCheckbox
            type="checkbox"
            checked={useLlmTier}
            onChange={(e) => setUseLlmTier(e.target.checked)}
          />
          Use LLM detection tier
        </ToggleLabel>
        <Caption>Uses the LLM tier — incurs API cost.</Caption>
      </ToggleRow>

      {/* Advanced crawl bounds */}
      <div>
        <AdvancedToggle
          $expanded={advancedOpen}
          onClick={() => setAdvancedOpen((prev) => !prev)}
          type="button"
        >
          <ChevronRight />
          Advanced (crawl bounds)
        </AdvancedToggle>
        <AdvancedContent $expanded={advancedOpen}>
          {(
            [
              {
                id: "maxDepth",
                label: "Max depth",
                placeholder: "2",
                value: maxDepth,
                setter: setMaxDepth,
              },
              {
                id: "minDemand",
                label: "Min demand",
                placeholder: "2",
                value: minDemand,
                setter: setMinDemand,
              },
              {
                id: "maxAuthorities",
                label: "Max authorities",
                placeholder: "50",
                value: maxAuthorities,
                setter: setMaxAuthorities,
              },
              {
                id: "perJurisdictionCap",
                label: "Per-jurisdiction cap",
                placeholder: "15",
                value: perJurisdictionCap,
                setter: setPerJurisdictionCap,
              },
              {
                id: "tokenBudget",
                label: "Token budget",
                placeholder: "2000000",
                value: tokenBudget,
                setter: setTokenBudget,
              },
            ] as const
          ).map(({ id, label, placeholder, value, setter }) => (
            <BoundRow key={id}>
              <BoundLabel htmlFor={`enrichment-${id}`}>{label}</BoundLabel>
              <NumberInput
                id={`enrichment-${id}`}
                type="number"
                min={0}
                placeholder={placeholder}
                value={value}
                onChange={(e) => setter(e.target.value)}
              />
            </BoundRow>
          ))}
        </AdvancedContent>
      </div>

      {/* Run button */}
      <RunButton
        type="button"
        $disabled={isDisabled}
        disabled={isDisabled}
        onClick={handleRun}
        data-testid="enrichment-run-button"
      >
        {loading ? "Starting…" : "Run"}
      </RunButton>
    </Container>
  );
};
