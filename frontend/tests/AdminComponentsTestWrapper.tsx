import React from "react";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { MemoryRouter } from "react-router-dom";
import { ToastContainer } from "react-toastify";
import { GlobalSettingsPanel } from "../src/components/admin/GlobalSettingsPanel";
import { GlobalAgentManagement } from "../src/components/admin/GlobalAgentManagement";
import { CorpusAgentManagement } from "../src/components/corpuses/CorpusAgentManagement";
import { SystemSettings } from "../src/components/admin/SystemSettings";

// Wrapper for GlobalSettingsPanel with Apollo mocking and routing context
interface GlobalSettingsPanelWrapperProps {
  mocks?: MockedResponse[];
}

export const GlobalSettingsPanelWrapper: React.FC<
  GlobalSettingsPanelWrapperProps
> = ({ mocks = [] }) => (
  <MockedProvider mocks={mocks} addTypename={false}>
    <MemoryRouter>
      <GlobalSettingsPanel />
      <ToastContainer />
    </MemoryRouter>
  </MockedProvider>
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

// Wrapper for SystemSettings (standalone, for unit testing pipeline config)
interface SystemSettingsWrapperProps {
  mocks?: MockedResponse[];
}

export const SystemSettingsWrapper: React.FC<SystemSettingsWrapperProps> = ({
  mocks = [],
}) => (
  <MockedProvider mocks={mocks} addTypename={false}>
    <MemoryRouter>
      <div style={{ padding: "2rem", maxWidth: 900, margin: "0 auto" }}>
        <SystemSettings />
      </div>
      <ToastContainer />
    </MemoryRouter>
  </MockedProvider>
);
