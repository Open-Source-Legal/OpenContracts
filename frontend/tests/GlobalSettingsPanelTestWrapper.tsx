import React from "react";
import { MockedProvider } from "@apollo/client/testing";
import { MemoryRouter } from "react-router-dom";
import { GlobalSettingsPanel } from "../src/components/admin/GlobalSettingsPanel";

const GlobalSettingsPanelTestWrapper: React.FC = () => (
  <MockedProvider mocks={[]} addTypename={false}>
    <MemoryRouter>
      <GlobalSettingsPanel />
    </MemoryRouter>
  </MockedProvider>
);

export default GlobalSettingsPanelTestWrapper;
