import React, { useEffect } from "react";
import { InMemoryCache } from "@apollo/client";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { MemoryRouter } from "react-router-dom";
import { ToastContainer } from "react-toastify";
import { backendUserObj } from "../src/graphql/cache";
import { IngestionMonitor } from "../src/components/admin/IngestionMonitor";
import {
  APP_CONTAINER_STYLE,
  APP_SHELL_FLEX_SHELL_STYLE,
  APP_SHELL_OUTER_STYLE,
} from "../src/styles/appShellLayout";

interface WrapperProps {
  mocks?: MockedResponse[];
  superuser?: boolean;
}

/**
 * Faithful stand-in for the real AppShell flex-column chain
 * (outer → flex-shell → #AppContainer). The page Container is a flex item of a
 * column-direction flex container, whose default `align-items: stretch` will NOT
 * shrink the item below the intrinsic width of its (wide, min-width-pinned) table
 * child. Mounting the monitor bare — as the earlier wrapper did — hid the mobile
 * horizontal-scroll regression because a plain block parent constrains width for
 * free. Reproducing the flex ancestors here is what lets the mobile-scroll test
 * actually exercise the failure. Uses the production layout constants so the test
 * tracks any future change to the shell's flex setup.
 */
const AppShellLayout: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => (
  <div style={APP_SHELL_OUTER_STYLE}>
    <div style={APP_SHELL_FLEX_SHELL_STYLE}>
      <div id="AppContainer" style={APP_CONTAINER_STYLE}>
        {children}
      </div>
    </div>
  </div>
);

export const IngestionMonitorTestWrapper: React.FC<WrapperProps> = ({
  mocks = [],
  superuser = true,
}) => {
  useEffect(() => {
    backendUserObj({ isSuperuser: superuser } as any);
    return () => {
      backendUserObj(null);
    };
  }, [superuser]);

  // Fresh cache per mount so InMemoryCache type policies never bleed between
  // tests (kept inside the wrapper per the project test-wrapper convention).
  // addTypename:false must match the MockedProvider prop — otherwise the cache
  // injects __typename into the queries and the typename-free mocks no longer
  // match.
  return (
    <MockedProvider
      mocks={mocks}
      addTypename={false}
      cache={new InMemoryCache({ addTypename: false })}
    >
      <MemoryRouter initialEntries={["/admin/ingestion"]}>
        <AppShellLayout>
          <IngestionMonitor />
        </AppShellLayout>
        <ToastContainer />
      </MemoryRouter>
    </MockedProvider>
  );
};
