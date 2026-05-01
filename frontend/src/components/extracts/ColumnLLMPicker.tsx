/**
 * Per-column LLM picker (Phase 4 / 5 of the LLM config system).
 *
 * Renders a <select> populated by the ``availableLlms`` resolver on the
 * Column GraphQL type (or by the standalone ``registeredLlms`` query
 * when no column id is available — i.e. during creation). The empty
 * value means "use LLMSettings.default_extract_llm".
 *
 * Resolvable rows are selectable; non-resolvable rows render disabled
 * with their ``unavailableReason`` as a tooltip — operators see *why*
 * the option is greyed out instead of guessing.
 */

import React from "react";
import { useQuery } from "@apollo/client";
import { gql } from "@apollo/client";

const LIST_REGISTERED_LLMS = gql`
  query ListRegisteredLLMsForPicker {
    registeredLlms(onlySelectable: true) {
      id
      modelId
      displayName
      pydanticAiModelString
      isResolvable
      unavailableReason
      provider {
        title
        pydanticAiPrefix
      }
    }
  }
`;

interface PickerLLM {
  id: string;
  modelId: string;
  displayName: string;
  pydanticAiModelString?: string | null;
  isResolvable: boolean;
  unavailableReason?: string | null;
  provider?: {
    title?: string | null;
    pydanticAiPrefix?: string | null;
  } | null;
}

interface ColumnLLMPickerProps {
  /** Currently-selected RegisteredLLM PK as a string. Empty / undefined
   *  means "use LLMSettings.default_extract_llm". */
  value: string | undefined;
  onChange: (preferredLlmId: string | undefined) => void;
  disabled?: boolean;
}

/**
 * Backend contract: pass the PK as `preferredLlmId` to
 * createColumn / updateColumn. Pass `"0"` to clear.
 */
export const ColumnLLMPicker: React.FC<ColumnLLMPickerProps> = ({
  value,
  onChange,
  disabled,
}) => {
  const { data, loading } = useQuery<{ registeredLlms: PickerLLM[] }>(
    LIST_REGISTERED_LLMS,
  );

  const selectStyle: React.CSSProperties = {
    width: "100%",
    padding: "8px 10px",
    borderRadius: 6,
    border: "1px solid #cbd5e1",
    fontSize: 14,
    background: "white",
  };

  if (loading) {
    return (
      <select style={selectStyle} disabled>
        <option>Loading…</option>
      </select>
    );
  }

  const rows = data?.registeredLlms || [];

  return (
    <select
      style={selectStyle}
      disabled={disabled}
      value={value || ""}
      onChange={(e) => onChange(e.target.value || undefined)}
    >
      <option value="">— Use system default —</option>
      {rows.map((rl) => (
        <option
          key={rl.id}
          value={rl.id}
          disabled={!rl.isResolvable}
          // Browsers expose <option title> as a tooltip on hover.
          title={
            rl.isResolvable
              ? rl.pydanticAiModelString || rl.modelId
              : rl.unavailableReason || "Currently unavailable"
          }
        >
          {rl.displayName}
          {rl.provider?.title ? ` · ${rl.provider.title}` : ""}
          {!rl.isResolvable ? " (unavailable)" : ""}
        </option>
      ))}
    </select>
  );
};
