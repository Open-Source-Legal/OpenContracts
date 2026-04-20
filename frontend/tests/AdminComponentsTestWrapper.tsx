import React from "react";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { MemoryRouter } from "react-router-dom";
import { ToastContainer } from "react-toastify";
import { GlobalSettingsPanel } from "../src/components/admin/GlobalSettingsPanel";
import { GlobalAgentManagement } from "../src/components/admin/GlobalAgentManagement";
import { CorpusAgentManagement } from "../src/components/corpuses/CorpusAgentManagement";
import { SystemSettings } from "../src/components/admin/SystemSettings";

// Wrapper for GlobalSettingsPanel with routing context
export const GlobalSettingsPanelWrapper: React.FC = () => (
  <MemoryRouter>
    <GlobalSettingsPanel />
  </MemoryRouter>
);

// Wrapper for GlobalAgentManagement with Apollo mocking
interface GlobalAgentManagementWrapperProps {
  mocks?: MockedResponse[];
}

export const GlobalAgentManagementWrapper: React.FC<
  GlobalAgentManagementWrapperProps
> = ({ mocks = [] }) => (
  <MockedProvider mocks={mocks} addTypename={false}>
    <GlobalAgentManagement />
  </MockedProvider>
);

// Wrapper variant that also mounts a ToastContainer so tests can assert on
// react-toastify notifications. Kept separate from GlobalAgentManagementWrapper
// to avoid changing the behavior of pre-existing tests that don't need toasts.
export const GlobalAgentManagementWithToastsWrapper: React.FC<
  GlobalAgentManagementWrapperProps
> = ({ mocks = [] }) => (
  <MockedProvider mocks={mocks} addTypename={false}>
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
}

export const CorpusAgentManagementWrapper: React.FC<
  CorpusAgentManagementWrapperProps
> = ({ corpusId, canUpdate, mocks = [] }) => (
  <MockedProvider mocks={mocks} addTypename={false}>
    <CorpusAgentManagement corpusId={corpusId} canUpdate={canUpdate} />
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
