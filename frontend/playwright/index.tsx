// Import styles, initialize component theme here.
import "../src/App.css";
import "semantic-ui-css/semantic.min.css";
import "react-toastify/dist/ReactToastify.css";

import React from "react";
import {
  beforeMount,
  afterMount,
} from "@playwright/experimental-ct-react/hooks";
import { Provider as JotaiProvider, createStore } from "jotai";
import workerSrc from "pdfjs-dist/build/pdf.worker?worker&url";
import * as pdfjs from "pdfjs-dist";
import { ApolloClient, InMemoryCache, ApolloProvider } from "@apollo/client";
import { ThemeProvider } from "../src/theme/ThemeProvider";

// Create a type for the Jotai Store
type Store = ReturnType<typeof createStore>;

// Define window property for the store
declare global {
  interface Window {
    jotaiStore: Store;
    apolloClient: ApolloClient<any>;
  }
}

// Optional: Import global styles if needed by components
// import '../src/index.css';

// Explicitly type the parameter for beforeMount
type BeforeMountParams = {
  App: React.ComponentType;
  hooksConfig?: { component?: { name?: string } };
};

// This hook runs before each component is mounted
beforeMount(async ({ App }: BeforeMountParams) => {
  console.log(`[Playwright Hook] Before mounting component with providers`);

  // Configure PDF.js to use a worker - https://github.com/mozilla/pdf.js/issues/10478
  //GlobalWorkerOptions.workerSrc = '';
  pdfjs.GlobalWorkerOptions.workerSrc = workerSrc;

  // Create a fresh Jotai store for this test
  window.jotaiStore = createStore();

  // Create a mock Apollo Client for this test
  // No link needed as requests will be mocked by page.route or MockedProvider
  console.log(`[Playwright Hook] Creating Mock Apollo Client`);
  window.apolloClient = new ApolloClient({
    cache: new InMemoryCache(),
    // You could add default mocks here if needed, but page.route is handling it
  });

  // Return the Provider wrapping the component
  // Nest ApolloProvider inside JotaiProvider (or vice-versa, order usually doesn't matter)
  return (
    <JotaiProvider store={window.jotaiStore}>
      <ApolloProvider client={window.apolloClient}>
        <ThemeProvider>
          <App />
        </ThemeProvider>
      </ApolloProvider>
    </JotaiProvider>
  );
});

// This hook runs after each component is mounted
afterMount(async () => {
  console.log(`[Playwright Hook] After mounting component`);
});
