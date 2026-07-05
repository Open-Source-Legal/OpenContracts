import React from "react";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { MemoryRouter } from "react-router-dom";
import { ToastContainer } from "react-toastify";
import { GlobalSettingsPanel } from "../src/components/admin/GlobalSettingsPanel";
import { GlobalAgentManagement } from "../src/components/admin/GlobalAgentManagement";
import { CorpusAgentManagement } from "../src/components/corpuses/CorpusAgentManagement";
import { SystemSettings } from "../src/components/admin/SystemSettings";
import {
  GET_LLM_PROVIDERS,
  GET_SYSTEM_DEFAULT_LLM,
} from "../src/graphql/queries";

// Wrapper for GlobalSettingsPanel with routing context
export const GlobalSettingsPanelWrapper: React.FC = () => (
  <MemoryRouter>
    <GlobalSettingsPanel />
  </MemoryRouter>
);

// Both GlobalAgentManagement and CorpusAgentManagement fire these on mount to
// power the Preferred LLM picker (chip list + "inherited default" hint).
// Appended AFTER any test-supplied mocks so a test that cares about specific
// provider data can still declare its own mock (matched first) while every
// other test gets a harmless empty-providers fallback instead of a "no more
// mocked responses" console error.
const defaultLlmProvidersMock: MockedResponse = {
  request: { query: GET_LLM_PROVIDERS },
  result: { data: { pipelineComponents: { llmProviders: [] } } },
};
const defaultSystemDefaultLlmMock: MockedResponse = {
  request: { query: GET_SYSTEM_DEFAULT_LLM },
  result: { data: { pipelineSettings: { defaultLlm: null } } },
};

// Wrapper for GlobalAgentManagement with Apollo mocking
interface GlobalAgentManagementWrapperProps {
  mocks?: MockedResponse[];
}

export const GlobalAgentManagementWrapper: React.FC<
  GlobalAgentManagementWrapperProps
> = ({ mocks = [] }) => (
  <MockedProvider
    mocks={[...mocks, defaultLlmProvidersMock, defaultSystemDefaultLlmMock]}
    addTypename={false}
  >
    <GlobalAgentManagement />
  </MockedProvider>
);

// Wrapper variant that also mounts a ToastContainer so tests can assert on
// react-toastify notifications. Kept separate from GlobalAgentManagementWrapper
// to avoid changing the behavior of pre-existing tests that don't need toasts.
export const GlobalAgentManagementWithToastsWrapper: React.FC<
  GlobalAgentManagementWrapperProps
> = ({ mocks = [] }) => (
  <MockedProvider
    mocks={[...mocks, defaultLlmProvidersMock, defaultSystemDefaultLlmMock]}
    addTypename={false}
  >
    <MemoryRouter>
      <GlobalAgentManagement />
      <ToastContainer />
    </MemoryRouter>
  </MockedProvider>
);

// Wrapper for CorpusAgentManagement with Apollo mocking
interface CorpusAgentManagementWrapperProps {
  corpusId: string;
  canUpdate: boolean;
  mocks?: MockedResponse[];
  corpusPreferredLlm?: string | null;
}

export const CorpusAgentManagementWrapper: React.FC<
  CorpusAgentManagementWrapperProps
> = ({ corpusId, canUpdate, mocks = [], corpusPreferredLlm }) => (
  <MockedProvider
    mocks={[...mocks, defaultLlmProvidersMock]}
    addTypename={false}
  >
    <CorpusAgentManagement
      corpusId={corpusId}
      canUpdate={canUpdate}
      corpusPreferredLlm={corpusPreferredLlm}
    />
  </MockedProvider>
);

// Wrapper for SystemSettings with Apollo mocking and routing
interface SystemSettingsWrapperProps {
  mocks?: MockedResponse[];
}

export const SystemSettingsWrapper: React.FC<SystemSettingsWrapperProps> = ({
  mocks = [],
}) => (
  <MockedProvider mocks={mocks} addTypename={false}>
    <MemoryRouter>
      <SystemSettings />
      <ToastContainer />
    </MemoryRouter>
  </MockedProvider>
);
