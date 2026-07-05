/**
 * Minimal mount-only vitest coverage for GlobalAgentManagement.
 *
 * The Playwright CT suite (`frontend/tests/global-agent-management.ct.tsx`)
 * covers behaviour end-to-end, but Istanbul attributes multi-line
 * `useMutation(CONST,\n  { ... })` calls to the call line rather than to
 * each argument line — which leaves the newly-renamed mutation constant
 * references (lines 191 / 208 / 225 in the diff for #1281) invisible to
 * Codecov's patch calc even though they are executed.
 *
 * A single render here lets v8 record a hit for every executable line in
 * the function body that runs on mount, closing that reporting gap.
 */
import React from "react";
import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { MockedProvider } from "@apollo/client/testing";
import { GlobalAgentManagement } from "../GlobalAgentManagement";
import { GET_GLOBAL_AGENTS } from "../global_agent_management.graphql";
import {
  GET_LLM_PROVIDERS,
  GET_SYSTEM_DEFAULT_LLM,
} from "../../../graphql/queries";

const agentsQueryMock = {
  request: { query: GET_GLOBAL_AGENTS },
  result: {
    data: {
      agentConfigurations: { edges: [] },
    },
  },
};

// GlobalAgentManagement also fires these to power the Preferred LLM picker's
// chip list + "inherited system default" hint. Mock them so the mount doesn't
// leave a dangling unmatched-mock error in the MockedProvider.
const llmProvidersMock = {
  request: { query: GET_LLM_PROVIDERS },
  result: {
    data: { pipelineComponents: { llmProviders: [] } },
  },
};

const systemDefaultLlmMock = {
  request: { query: GET_SYSTEM_DEFAULT_LLM },
  result: {
    data: { pipelineSettings: { defaultLlm: null } },
  },
};

describe("GlobalAgentManagement (mount smoke test)", () => {
  it("mounts without throwing under a MockedProvider", () => {
    const { container } = render(
      <MockedProvider
        mocks={[agentsQueryMock, llmProvidersMock, systemDefaultLlmMock]}
        addTypename={false}
      >
        <GlobalAgentManagement />
      </MockedProvider>
    );
    // The loading state renders a non-empty tree.
    expect(container.firstChild).not.toBeNull();
  });
});
