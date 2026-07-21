import React, { useState } from "react";
import { MockedProvider } from "@apollo/client/testing";
import { InMemoryCache } from "@apollo/client";
// Split-import rule (CLAUDE.md pitfall #16): JSX-component imports must live in
// their own statement, separate from the helper/constant imports below, or
// Playwright CT's babel transform leaves the component reference unrewritten
// and ``mount()`` throws.
import { CorpusMultiSelect } from "../src/components/widgets/selectors/CorpusMultiSelect";
import { AgentConfigurationSelect } from "../src/components/widgets/selectors/AgentConfigurationSelect";
import {
  corpusSearchMocks,
  agentSearchMocks,
} from "./CorpusGroupPickerFixtures";
import type { CorpusOption } from "../src/components/widgets/selectors/CorpusMultiSelect";
import type { AgentOption } from "../src/components/widgets/selectors/AgentConfigurationSelect";

/** ``inputId`` handed to the pickers so tests can address the text input. */
export const CORPUS_INPUT_ID = "corpus-picker-input";
export const AGENT_INPUT_ID = "agent-picker-input";

/** Readout test ids — see the note on ``CorpusMultiSelectTestWrapper``. */
export const CORPUS_SELECTION_TESTID = "corpus-selection";
export const CORPUS_CHANGE_COUNT_TESTID = "corpus-change-count";
export const AGENT_SELECTION_TESTID = "agent-selection";
export const AGENT_CHANGE_COUNT_TESTID = "agent-change-count";

interface CorpusWrapperProps {
  initialValue?: CorpusOption[];
  disabled?: boolean;
}

interface AgentWrapperProps {
  initialValue?: AgentOption | null;
  disabled?: boolean;
}

/**
 * Stateful host for ``CorpusMultiSelect``.
 *
 * Both pickers are CONTROLLED, so a wrapper that did not feed ``onChange`` back
 * into ``value`` would assert nothing about real usage — the chips would never
 * change. State therefore lives here, and the resulting value is serialised
 * into the DOM: callback arguments live in the browser realm and a Node-side
 * spy cannot observe them, so the rendered JSON is the only honest channel for
 * asserting the exact ``{id, title}`` shape a consumer receives.
 *
 * The change counter exists because ``onChange`` never firing and ``onChange``
 * firing with an empty/null selection both leave the same rendered value — only
 * the counter separates them.
 */
export const CorpusMultiSelectTestWrapper: React.FC<CorpusWrapperProps> = ({
  initialValue = [],
  disabled = false,
}) => {
  const [value, setValue] = useState<CorpusOption[]>(initialValue);
  const [changeCount, setChangeCount] = useState(0);

  // Defined inside the wrapper so Playwright CT's per-test serialization never
  // has to reach an Apollo cache instance — see CLAUDE.md pitfall #8.
  const cache = new InMemoryCache({ addTypename: false });

  return (
    <MockedProvider mocks={corpusSearchMocks} addTypename={false} cache={cache}>
      <div style={{ width: "100vw", padding: "1rem" }}>
        <CorpusMultiSelect
          id={CORPUS_INPUT_ID}
          value={value}
          disabled={disabled}
          onChange={(next) => {
            setValue(next);
            setChangeCount((count) => count + 1);
          }}
        />
        <div data-testid={CORPUS_SELECTION_TESTID}>{JSON.stringify(value)}</div>
        <div data-testid={CORPUS_CHANGE_COUNT_TESTID}>{changeCount}</div>
      </div>
    </MockedProvider>
  );
};

/** Stateful host for ``AgentConfigurationSelect`` — see the corpus wrapper. */
export const AgentConfigurationSelectTestWrapper: React.FC<
  AgentWrapperProps
> = ({ initialValue = null, disabled = false }) => {
  const [value, setValue] = useState<AgentOption | null>(initialValue);
  const [changeCount, setChangeCount] = useState(0);

  const cache = new InMemoryCache({ addTypename: false });

  return (
    <MockedProvider mocks={agentSearchMocks} addTypename={false} cache={cache}>
      <div style={{ width: "100vw", padding: "1rem" }}>
        <AgentConfigurationSelect
          id={AGENT_INPUT_ID}
          value={value}
          disabled={disabled}
          onChange={(next) => {
            setValue(next);
            setChangeCount((count) => count + 1);
          }}
        />
        <div data-testid={AGENT_SELECTION_TESTID}>{JSON.stringify(value)}</div>
        <div data-testid={AGENT_CHANGE_COUNT_TESTID}>{changeCount}</div>
      </div>
    </MockedProvider>
  );
};
