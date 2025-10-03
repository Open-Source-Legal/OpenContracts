import { App } from "./App";
import { BrowserRouter } from "react-router-dom";
import { createRoot } from "react-dom/client";
import { Auth0ProviderWithHistory } from "./utils/Auth0ProviderWithHistory";
import {
  ApolloClient,
  ApolloProvider,
  createHttpLink,
  ApolloLink,
  Observable,
} from "@apollo/client";
import { cache } from "./graphql/cache";
import { LooseObject } from "./components/types";
import { getRuntimeEnv } from "./utils/env";
import { getToken } from "./utils/tokenManager";
import { HelmetProvider } from "react-helmet-async";

import "./index.css";
import reportWebVitals from "./reportWebVitals";

// Can't use useEnv hook here; use the pure utility instead
const {
  REACT_APP_APPLICATION_DOMAIN,
  REACT_APP_APPLICATION_CLIENT_ID,
  REACT_APP_AUDIENCE,
  REACT_APP_API_ROOT_URL,
  REACT_APP_USE_AUTH0,
} = getRuntimeEnv();

const api_root_url = REACT_APP_API_ROOT_URL || "http://localhost:8000";

console.log("OpenContracts is using Auth0: ", REACT_APP_USE_AUTH0);
console.log("OpenContracts frontend target api root", api_root_url);

const authLink = new ApolloLink((operation, forward) => {
  // Async link: fetch fresh token on each request
  // For Auth0: calls getAccessTokenSilently() which auto-refreshes if needed
  // For non-Auth0: returns cached token from reactive var
  return new Observable((observer) => {
    let handle: any;

    getToken()
      .then((token) => {
        operation.setContext(({ headers }: { headers: LooseObject }) => ({
          headers: {
            Authorization: token ? `Bearer ${token}` : "",
            ...headers,
          },
        }));

        handle = forward(operation).subscribe({
          next: observer.next.bind(observer),
          error: observer.error.bind(observer),
          complete: observer.complete.bind(observer),
        });
      })
      .catch((error) => {
        console.error("[authLink] Error getting token:", error);
        observer.error(error);
      });

    return () => {
      if (handle) handle.unsubscribe();
    };
  });
});

console.log("api_root_url", api_root_url);
const httpLink = createHttpLink({
  uri: `${api_root_url}/graphql/`,
});

const client = new ApolloClient({
  link: authLink.concat(httpLink),
  cache,
});

const container = document.getElementById("root");
const root = createRoot(container!);

if (REACT_APP_USE_AUTH0) {
  console.log("Rendering with USE_AUTH0");

  const providerConfig = {
    domain: REACT_APP_APPLICATION_DOMAIN,
    clientId: REACT_APP_APPLICATION_CLIENT_ID,
    authorizationParams: {
      audience: REACT_APP_AUDIENCE || undefined,
      scope: "openid profile email",
      redirect_uri: window.location.origin,
    },
  };

  console.log("[index.tsx] Auth0 providerConfig:", providerConfig);
  console.log("[index.tsx] window.location.origin:", window.location.origin);

  root.render(
    <HelmetProvider>
      <BrowserRouter>
        <Auth0ProviderWithHistory {...providerConfig}>
          <ApolloProvider client={client}>
            <App />
          </ApolloProvider>
        </Auth0ProviderWithHistory>
      </BrowserRouter>
    </HelmetProvider>
  );
} else {
  console.log("Rendering with NO AUTH0");

  root.render(
    <HelmetProvider>
      <ApolloProvider client={client}>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </ApolloProvider>
    </HelmetProvider>
  );
}

// If you want to start measuring performance in your app, pass a function
// to log results (for example: reportWebVitals(console.log))
// or send to an analytics endpoint. Learn more: https://bit.ly/CRA-vitals
reportWebVitals();
